"""
AquaIQ — CGWB data ingestion script.

Reads:  data/raw/cgwb_combined.csv  (1.5M rows, 1996–2023)
        data_ingestion/district_crosswalk.csv
Writes:
  • districts  — ensures canonical districts exist
  • raw_data   — one row per canonical district per month, metric='GWL', source='CGWB'
                 (all well readings per district-month are averaged across the full dataset)

Run:
    py data_ingestion/ingest_cgwb.py

The script is idempotent — safe to re-run. Existing rows are updated via
ON CONFLICT (district_id, date, source, metric) DO UPDATE SET value = EXCLUDED.value.
"""

import sys
import time
from pathlib import Path

import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extras
import yaml
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

CSV_PATH = ROOT / CONFIG["paths"]["data_raw"] / "cgwb_combined.csv"
CROSSWALK_PATH = ROOT / "data_ingestion" / "district_crosswalk.csv"


# ── DB connection ─────────────────────────────────────────────────────────────
def get_connection():
    from db.connection import get_connection as connect
    return connect()


# ── Crosswalk Helper ──────────────────────────────────────────────────────────
def get_crosswalk_mapping() -> dict[str, str]:
    """Load legacy_district_id -> canonical_district_id mapping from CSV."""
    if not CROSSWALK_PATH.exists():
        raise FileNotFoundError(f"Crosswalk CSV not found at {CROSSWALK_PATH}")
    df = pd.read_csv(CROSSWALK_PATH, dtype=str)
    keys = ["legacy_district_id", "canonical_district_id"]
    if df[keys].isna().any().any():
        raise ValueError("Crosswalk identities cannot be missing")
    df[keys] = df[keys].apply(lambda column: column.str.strip())
    if df[keys].eq("").any().any():
        raise ValueError("Crosswalk identities cannot be empty")
    if df.groupby("legacy_district_id")["canonical_district_id"].nunique().gt(1).any():
        raise ValueError("Ambiguous legacy district identity in crosswalk")
    return dict(zip(df[keys[0]], df[keys[1]]))


# ── Step 1: Ensure Canonical Districts Exist ─────────────────────────────────
def load_canonical_districts(conn):
    """
    Ensure every canonical district in district_crosswalk.csv exists in the districts table.
    """
    print("[1/3] Verifying and inserting canonical districts from crosswalk...")
    df = pd.read_csv(CROSSWALK_PATH, dtype=str)
    unique_districts = df.drop_duplicates("canonical_district_id")

    rows = [
        (
            row["canonical_district_id"].strip(),
            row["canonical_name"].strip(),
            row["canonical_state"].strip(),
        )
        for _, row in unique_districts.iterrows()
    ]

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO districts (district_id, district_name, state)
            VALUES %s
            ON CONFLICT (district_id) DO NOTHING
            """,
            rows,
            page_size=500,
        )
        from db.migrations.run_migration_001 import MAPPING_TABLE_SQL, validate_crosswalk
        cur.execute(MAPPING_TABLE_SQL)
        cur.execute("SELECT district_id,district_name,state,agro_climatic_zone,geojson_name FROM districts")
        master = [dict(zip(["district_id", "district_name", "state", "agro_climatic_zone", "geojson_name"], row))
                  for row in cur.fetchall()]
        cur.execute("SELECT legacy_id,canonical_id FROM legacy_district_ids")
        recorded = [dict(zip(["legacy_id", "canonical_id"], row)) for row in cur.fetchall()]
        validated, _ = validate_crosswalk(df.to_dict("records"), master, recorded)
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO legacy_district_ids(legacy_id,canonical_id,canonical_name,canonical_state,source,match_type,notes)
            VALUES (%(legacy_district_id)s,%(canonical_district_id)s,%(canonical_name)s,%(canonical_state)s,
                    %(source)s,%(match_type)s,%(notes)s)
            ON CONFLICT(legacy_id) DO NOTHING
        """, [{**row, "notes": row.get("notes", "")} for row in validated])
    conn.commit()
    print(f"    Canonical districts verified: {len(rows)} distinct districts.")


# ── Step 2: Aggregate Well Readings ───────────────────────────────────────────
def aggregate_well_readings(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """
    Aggregate well readings to canonical district-month means.
    1. Parse numeric currentlevel and drop NaNs.
    2. Normalize date to first of the month.
    3. Map legacy district_code to canonical_id.
    4. Group by (district_id, date) and compute exact arithmetic mean.
    """
    df = df.copy()
    df["currentlevel"] = pd.to_numeric(df["currentlevel"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    df["district_code"] = df["district_code"].astype(str).str.strip()
    df.dropna(subset=["currentlevel", "district_code", "date"], inplace=True)

    df["month_date"] = pd.to_datetime(df["date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    df.dropna(subset=["month_date"], inplace=True)

    # Map to canonical ID
    df["district_id"] = df["district_code"].map(mapping)
    df.dropna(subset=["district_id"], inplace=True)

    agg = (
        df.groupby(["district_id", "month_date"], as_index=False)
        .agg(gwl_mean=("currentlevel", "mean"), well_count=("currentlevel", "count"))
        .rename(columns={"month_date": "date"})
    )
    return agg


# ── Step 3: Ingest Aggregated Rows into raw_data ──────────────────────────────
def ingest_raw_data(conn):
    """
    Read full cgwb_combined.csv, aggregate globally across all well readings,
    and bulk-upsert into raw_data with ON CONFLICT DO UPDATE.
    """
    print("[2/3] Loading and aggregating CGWB well observations...")
    t0 = time.time()
    mapping = get_crosswalk_mapping()

    usecols = ["district_code", "date", "currentlevel"]
    # Reading 1.5M rows takes <2 seconds in pandas
    df = pd.read_csv(CSV_PATH, usecols=usecols, dtype=str)
    print(f"    Loaded {len(df):,} raw records from {CSV_PATH.name} ({time.time() - t0:.1f}s)")

    agg = aggregate_well_readings(df, mapping)
    print(f"    Aggregated into {len(agg):,} canonical district-months ({time.time() - t0:.1f}s)")

    rows = [
        (
            str(row["district_id"]),
            row["date"].date(),
            "CGWB",
            "GWL",
            float(row["gwl_mean"]),
        )
        for _, row in agg.iterrows()
    ]

    print("    Upserting into raw_data table...")
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO raw_data (district_id, date, source, metric, value)
            VALUES %s
            ON CONFLICT (district_id, date, source, metric)
            DO UPDATE SET value = EXCLUDED.value
            """,
            rows,
            page_size=2000,
        )
    conn.commit()
    print(f"    raw_data: {len(rows):,} district-month GWL records upserted.")
    return len(rows)


# ── Verification ─────────────────────────────────────────────────────────────
def verify(conn):
    print("[3/3] Verification...")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM districts")
        n_districts = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM raw_data WHERE source = 'CGWB' AND metric = 'GWL'")
        n_gwl = cur.fetchone()[0]

        cur.execute("""
            SELECT MIN(date), MAX(date) FROM raw_data
            WHERE source = 'CGWB' AND metric = 'GWL'
        """)
        date_min, date_max = cur.fetchone()

        cur.execute("""
            SELECT COUNT(DISTINCT district_id) FROM raw_data
            WHERE source = 'CGWB' AND metric = 'GWL'
        """)
        n_covered = cur.fetchone()[0]

        # Verify no numeric IDs in CGWB data
        cur.execute("""
            SELECT COUNT(*) FROM raw_data
            WHERE source = 'CGWB' AND district_id ~ '^[0-9]+$'
        """)
        n_numeric = cur.fetchone()[0]

    print(f"    districts table       : {n_districts:,} rows")
    print(f"    raw_data (CGWB GWL)  : {n_gwl:,} district-month rows")
    print(f"    Date range            : {date_min} to {date_max}")
    print(f"    Districts with data   : {n_covered:,} / {n_districts:,}")
    print(f"    Numeric IDs remaining : {n_numeric}")
    assert n_numeric == 0, f"Error: found {n_numeric} numeric district IDs in raw_data!"


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"AquaIQ CGWB Ingestion (Canonical ID & Full-Aggregation Engine)")
    print(f"  Source : {CSV_PATH.name} ({CSV_PATH.stat().st_size / 1_000_000:.1f} MB)")
    print()

    t_start = time.time()
    conn = get_connection()

    try:
        load_canonical_districts(conn)
        ingest_raw_data(conn)
        verify(conn)
    finally:
        conn.close()

    elapsed = time.time() - t_start
    print()
    print(f"Done in {elapsed:.1f}s [OK]")


if __name__ == "__main__":
    main()
