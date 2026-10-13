"""
AquaIQ — IMD + ERA5 → PostgreSQL raw_data ingestion
--------------------------------------------------------------
Reads processed CSV files and loads them into the raw_data table:
  - IMD district-monthly rainfall  → metric='rainfall', source='IMD'
  - ERA5 district-monthly temp/ET  → metric='temperature', 'evapotranspiration', source='ERA5'

Uses strictly state-aware district matching to canonical district IDs and
requires hashed source manifests to correct old weather units safely.
"""

import os
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extras
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

IMD_CSV = ROOT / CONFIG["paths"]["data_processed"] / "imd_rainfall_district_monthly.csv"
ERA5_CSV = ROOT / CONFIG["paths"]["data_processed"] / "era5_district_monthly.csv"

# Historical and alternative name aliases
NAME_ALIASES = {
    "prayagraj": ["allahabad"], "allahabad": ["prayagraj"],
    "ayodhya": ["faizabad"], "faizabad": ["ayodhya"],
    "gurugram": ["gurgaon"], "gurgaon": ["gurugram"],
    "kalaburagi": ["gulbarga"], "gulbarga": ["kalaburagi"],
    "mysuru": ["mysore"], "mysore": ["mysuru"],
    "belagavi": ["belgaum"], "belgaum": ["belagavi"],
    "ballari": ["bellary"], "bellary": ["ballari"],
    "shivamogga": ["shimoga"], "shimoga": ["shivamogga"],
    "tumakuru": ["tumkur"], "tumkur": ["tumakuru"],
    "kutch": ["kachchh"], "kachchh": ["kutch"],
    "nuh": ["mewat"], "mewat": ["nuh"],
    "chhatrapati sambhajinagar": ["aurangabad"], "aurangabad": ["chhatrapati sambhajinagar"],
    "dharashiv": ["osmanabad"], "osmanabad": ["dharashiv"],
    "narmadapuram": ["hoshangabad"], "hoshangabad": ["narmadapuram"],
    "khandwa": ["east nimar"], "east nimar": ["khandwa"],
    "khargone": ["west nimar"], "west nimar": ["khargone"],
    "beed": ["bid"], "bid": ["beed"],
    "dahod": ["dohad"], "dohad": ["dahod"],
    "dang": ["the dangs"], "the dangs": ["dang"],
    "barabanki": ["bara banki"], "bara banki": ["barabanki"],
    "s.p.s. nellore": ["sri potti sriramulu nellore", "nellore"],
    "y.s.r.": ["kadapa", "cuddapah"],
}


def get_connection():
    from db.connection import get_connection as connect
    return connect()


def norm_str(s: str) -> str:
    if not s or pd.isna(s):
        return ""
    return re.sub(r"\s+", " ", str(s).strip().lower().replace("_", " ").replace("-", " ").replace("&", "and"))


STATE_ALIASES = {"orissa": "odisha", "uttaranchal": "uttarakhand",
                 "pondicherry": "puducherry", "nct of delhi": "delhi",
                 "andaman and nicobar": "andaman and nicobar islands",
                 "dadra and nagar haveli": "dadra and nagar haveli and daman and diu",
                 "daman and diu": "dadra and nagar haveli and daman and diu"}


def norm_state(s):
    normalized = norm_str(s)
    return STATE_ALIASES.get(normalized, normalized)


def load_district_lookup(conn) -> dict:
    """
    Build lookups from:
      1. (norm_district, norm_state) -> set of matching district_ids
      2. norm_district -> set of matching district_ids (fallback)
    """
    with conn.cursor() as cur:
        cur.execute("SELECT district_id, district_name, state FROM districts")
        rows = cur.fetchall()

    lookup_state_aware = {}
    lookup_name_only = {}

    for did, dname, st in rows:
        dn = norm_str(dname)
        sn = norm_state(st)

        names = [dn]
        for alias in NAME_ALIASES.get(dn, []):
            names.append(norm_str(alias))

        for n in names:
            lookup_state_aware.setdefault((n, sn), set()).add(did)
            lookup_name_only.setdefault(n, set()).add(did)

    return {
        "state_aware": lookup_state_aware,
        "name_only": lookup_name_only,
    }


def find_target_ids(dist_name: str, state_name: str, lookups: dict) -> set:
    dn = norm_str(dist_name)
    sn = norm_state(state_name)

    # 1. Try state-aware match
    matches = lookups["state_aware"].get((dn, sn))
    if matches:
        return matches if len(matches) == 1 else set()

    # Check aliases with state
    for alias in NAME_ALIASES.get(dn, []):
        matches = lookups["state_aware"].get((norm_str(alias), sn))
        if matches:
            return matches if len(matches) == 1 else set()

    # An unrecognized state must never borrow a same-named other-state district.
    return set()


def validate_weather_artifact(path, required_units):
    path = Path(path)
    sidecar = path.with_suffix(".manifest.json")
    if not path.exists() or not sidecar.exists():
        raise ValueError(f"Regenerate verified weather artifact and manifest: {path}")
    manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    if manifest.get("artifact_version") != "weather-v3":
        raise ValueError(f"Legacy weather generation refused: {path}")
    if manifest.get("csv_sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError(f"Weather CSV hash does not match manifest: {path}")
    for metric, units in required_units.items():
        if manifest.get("units", {}).get(metric) != units:
            raise ValueError(f"Unverified {metric} units in {path}")
    return manifest


def _persist_weather(conn, rows, source, manifest):
    """Record corrections before an idempotent upsert; caller owns transaction."""
    if not rows:
        raise ValueError(f"No state-resolved {source} weather rows")
    frame = pd.DataFrame(rows, columns=["district_id", "date", "source", "metric", "value"])
    keys = ["district_id", "date", "source", "metric"]
    if (frame.groupby(keys)["value"].nunique() > 1).any():
        raise ValueError(f"Conflicting {source} values resolve to the same canonical district month")
    frame = frame.drop_duplicates(keys)
    with conn.cursor() as cur:
        cur.execute("SELECT district_id, date, source, metric, value FROM raw_data WHERE source = %s", (source,))
        old = pd.DataFrame(cur.fetchall(), columns=keys + ["old_value"])
        audit = frame.merge(old, on=keys, how="left", validate="one_to_one")
        corrected = audit[audit["old_value"].notna() & ((audit["old_value"] - audit["value"]).abs() > 1e-9)].copy()
        corrected["artifact_sha256"] = manifest["csv_sha256"]
        audit_dir = ROOT / CONFIG["paths"]["data_processed"] / "weather_corrections"
        audit_dir.mkdir(parents=True, exist_ok=True)
        corrected.to_csv(audit_dir / f"{source}_{manifest['csv_sha256'][:12]}.csv", index=False)
        psycopg2.extras.execute_values(cur, """
            INSERT INTO raw_data (district_id, date, source, metric, value) VALUES %s
            ON CONFLICT (district_id, date, source, metric) DO UPDATE SET value = EXCLUDED.value
            WHERE raw_data.value IS DISTINCT FROM EXCLUDED.value
        """, list(frame.itertuples(index=False, name=None)), page_size=5000)
    print(f"    {len(frame):,} verified {source} rows; {len(corrected):,} old values corrected (audit CSV saved)")
    return len(frame)


def sync_cgwb_to_composite_ids(conn, lookups: dict):
    """
    Ensure composite IDs (e.g., 'RJ-Jaipur') have the CGWB GWL records that
    were originally ingested under numeric IDs (e.g., '102').
    """
    print("[Sync] Synchronizing CGWB readings to composite district IDs...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT r.district_id, d.district_name, d.state, r.date, r.value
            FROM raw_data r
            JOIN districts d ON r.district_id = d.district_id
            WHERE r.source = 'CGWB' AND r.metric = 'GWL'
              AND r.district_id ~ '^[0-9]+$'
        """)
        rows = cur.fetchall()

    sync_rows = []
    for num_id, dname, st, dt, val in rows:
        target_ids = find_target_ids(dname, st, lookups)
        for tid in target_ids:
            if tid != num_id and tid.startswith(tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")):
                sync_rows.append((tid, dt, "CGWB", "GWL", val))

    if sync_rows:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO raw_data (district_id, date, source, metric, value)
                VALUES %s
                ON CONFLICT (district_id, date, source, metric) DO NOTHING
                """,
                sync_rows,
                page_size=5000,
            )
        conn.commit()
    print(f"    Synced {len(sync_rows):,} CGWB readings to composite district IDs.")


def ingest_imd(conn, lookups: dict):
    """Load IMD district-monthly rainfall into raw_data."""
    print("[1/2] Ingesting IMD rainfall...")
    manifest = validate_weather_artifact(IMD_CSV, {"rainfall_mm": "mm/month"})

    df = pd.read_csv(IMD_CSV)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
    )

    rows = []
    state_col = "st_nm" if "st_nm" in df.columns else "state"

    for _, row in df.iterrows():
        st = row.get(state_col, "")
        dist = row["district"]
        val = row["rainfall_mm"]
        if pd.isna(val) or not np.isfinite(val):
            continue

        target_ids = find_target_ids(dist, st, lookups)
        dt = row["date"].date()
        for did in target_ids:
            rows.append((did, dt, "IMD", "rainfall", float(val)))

    return _persist_weather(conn, rows, "IMD", manifest)


def ingest_era5(conn, lookups: dict):
    """Load ERA5 district-monthly temperature + ET into raw_data."""
    print("[2/2] Ingesting ERA5 temperature + evapotranspiration...")
    manifest = validate_weather_artifact(ERA5_CSV, {"temperature": "degC", "evapotranspiration": "mm/month"})

    df = pd.read_csv(ERA5_CSV)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
    )

    state_col = "st_nm" if "st_nm" in df.columns else "state"
    all_rows = []

    for _, row in df.iterrows():
        st = row.get(state_col, "")
        dist = row["district"]
        dt = row["date"].date()
        target_ids = find_target_ids(dist, st, lookups)

        temp = row.get("temperature")
        et = row.get("evapotranspiration")

        for did in target_ids:
            if pd.notna(temp) and np.isfinite(temp):
                all_rows.append((did, dt, "ERA5", "temperature", float(temp)))
            if pd.notna(et) and np.isfinite(et):
                all_rows.append((did, dt, "ERA5", "evapotranspiration", float(et)))

    return _persist_weather(conn, all_rows, "ERA5", manifest)


def verify(conn):
    print("\n  Verification:")
    with conn.cursor() as cur:
        for source in ["CGWB", "IMD", "ERA5"]:
            cur.execute(
                "SELECT COUNT(*), COUNT(DISTINCT district_id), MIN(date), MAX(date) "
                "FROM raw_data WHERE source = %s",
                (source,)
            )
            count, n_districts, date_min, date_max = cur.fetchone()
            print(f"    {source:5s}: {count:>8,} rows | {n_districts or 0:>4} districts | {date_min} to {date_max}")


def main(argv=None):
    print("AquaIQ -- IMD + ERA5 PostgreSQL Ingestion\n")
    # Preflight both artifacts before making any database change.
    validate_weather_artifact(IMD_CSV, {"rainfall_mm": "mm/month"})
    validate_weather_artifact(ERA5_CSV, {"temperature": "degC", "evapotranspiration": "mm/month"})
    conn = get_connection()
    try:
        lookups = load_district_lookup(conn)
        print(f"  District lookup initialized: {len(lookups['state_aware'])} state-district keys")
        with conn:
            ingest_imd(conn, lookups)
            ingest_era5(conn, lookups)
            verify(conn)
    finally:
        conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
