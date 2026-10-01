"""
AquaIQ — CGWB data ingestion script.

Reads:  data/raw/cgwb_combined.csv  (1.5M rows, 1996–2023)
Writes:
  • districts  — one row per unique district (district_code as district_id)
  • raw_data   — one row per district per month, metric='GWL', source='CGWB'
                 (multiple well readings per district-month are averaged)

Run:
    py data_ingestion/ingest_cgwb.py

The script is idempotent — safe to re-run. Existing rows are skipped via
ON CONFLICT DO NOTHING on both tables.

Performance: processes 1.5M rows in chunks (pandas) and bulk-inserts with
psycopg2 executemany. Expect ~2–5 minutes on a laptop.
"""

import os
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
import yaml
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

CSV_PATH = ROOT / CONFIG["paths"]["data_raw"] / "cgwb_combined.csv"
CHUNK_SIZE = 100_000   # rows per pandas chunk — tunes memory vs speed


# ── DB connection ─────────────────────────────────────────────────────────────
def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


# ── Step 1: build districts from the full CSV in one pass ────────────────────
def load_districts(conn):
    """
    Collect every unique (district_code, district_name, state_name) triple
    from the CSV and upsert into the districts table.
    district_code is used as district_id (stored as VARCHAR).
    agro_climatic_zone and geojson_name are filled in Week 2 / separately.
    """
    print("[1/4] Scanning CSV for unique districts...")
    seen: dict[str, tuple] = {}   # district_code → (district_name, state_name)

    for chunk in pd.read_csv(CSV_PATH, usecols=["district_code", "district_name", "state_name"],
                             chunksize=CHUNK_SIZE, dtype=str):
        chunk.dropna(subset=["district_code"], inplace=True)
        for _, row in chunk.drop_duplicates("district_code").iterrows():
            code = row["district_code"].strip()
            if code not in seen:
                seen[code] = (row["district_name"].strip(), row["state_name"].strip())

    rows = [(code, name, state) for code, (name, state) in seen.items()]
    print(f"    Found {len(rows)} unique districts from CGWB CSV.")

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
    conn.commit()
    print(f"    districts table: {len(rows)} rows upserted from CGWB.")


# ── Step 1b: fill gaps from GeoJSON so all 640+ districts are present ────────
def load_districts_from_geojson(conn):
    """
    CGWB's CSV only contains districts with borewell readings — typically
    ~568. The remaining ~72 districts (mostly remote/hilly with only
    pre-2013 or no CGWB coverage) are still real administrative units
    and must exist in the districts table so that:
      - FK constraints don't fail when IMD/ERA5 data references them
      - enrich_districts.py can assign agro_climatic_zone to all of them
      - the dashboard can show 'insufficient_data' instead of a silent gap

    This function reads the GeoJSON and inserts any district not already
    present. district_id is synthesised as '{state_code}-{district_name}'
    to match the convention used elsewhere.
    """
    print("[1b/4] Filling district gaps from GeoJSON...")

    geojson_path = ROOT / CONFIG["paths"]["geojson_boundaries"]
    if not geojson_path.exists():
        print(f"    SKIP: GeoJSON not found at {geojson_path}")
        return

    try:
        import json
        with open(geojson_path, encoding="utf-8") as f:
            geojson = json.load(f)
    except Exception as e:
        print(f"    SKIP: Failed to load GeoJSON: {e}")
        return

    # Build state abbreviation map
    STATE_ABBREV = {
        "Andhra Pradesh": "AP", "Arunachal Pradesh": "AR", "Assam": "AS",
        "Bihar": "BR", "Chhattisgarh": "CG", "Goa": "GA", "Gujarat": "GJ",
        "Haryana": "HR", "Himachal Pradesh": "HP", "Jharkhand": "JH",
        "Karnataka": "KA", "Kerala": "KL", "Madhya Pradesh": "MP",
        "Maharashtra": "MH", "Manipur": "MN", "Meghalaya": "ML",
        "Mizoram": "MZ", "Nagaland": "NL", "Odisha": "OD", "Punjab": "PB",
        "Rajasthan": "RJ", "Sikkim": "SK", "Tamil Nadu": "TN",
        "Telangana": "TS", "Tripura": "TR", "Uttar Pradesh": "UP",
        "Uttarakhand": "UK", "West Bengal": "WB", "Delhi": "DL",
        "Jammu And Kashmir": "JK", "Jammu & Kashmir": "JK", "Ladakh": "LA",
        "Puducherry": "PY", "Chandigarh": "CH",
        "Andaman And Nicobar Islands": "AN", "Andaman & Nicobar Islands": "AN",
        "Dadra And Nagar Haveli And Daman And Diu": "DD",
        "Dadra And Nagar Haveli": "DN", "Daman And Diu": "DD",
        "Lakshadweep": "LD", "Orissa": "OD",
        "Nct Of Delhi": "DL", "NCT of Delhi": "DL",
    }

    rows = []
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        district_name = props.get("district", props.get("DISTRICT", props.get("name", "")))
        state_name = props.get("st_nm", props.get("STATE", props.get("state", "")))

        if not district_name or not state_name:
            continue

        district_name = district_name.strip()
        state_name = state_name.strip()
        abbrev = STATE_ABBREV.get(state_name, STATE_ABBREV.get(state_name.title(), state_name[:2].upper()))
        district_id = f"{abbrev}-{district_name.replace(' ', '_')}"
        rows.append((district_id, district_name, state_name))

    if not rows:
        print("    SKIP: No districts parsed from GeoJSON.")
        return

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
    conn.commit()

    # Count how many were actually new
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM districts")
        total = cur.fetchone()[0]

    print(f"    GeoJSON provided {len(rows)} districts; total in table now: {total}.")



# ── Step 2: aggregate well readings → district-month means ───────────────────
def aggregate_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """
    Given a raw chunk of well readings, return district-month aggregates.

    • date       → truncated to YYYY-MM-01 (first of month)
    • currentlevel → converted to float, NaN rows dropped
    • group by (district_code, month_date) → mean(currentlevel)
    """
    chunk = chunk.copy()
    chunk["currentlevel"] = pd.to_numeric(chunk["currentlevel"], errors="coerce")
    chunk.dropna(subset=["currentlevel", "district_code"], inplace=True)

    # Normalize to first of month
    chunk["month_date"] = pd.to_datetime(chunk["date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    chunk.dropna(subset=["month_date"], inplace=True)

    agg = (
        chunk.groupby(["district_code", "month_date"], as_index=False)["currentlevel"]
        .mean()
        .rename(columns={"currentlevel": "gwl_mean"})
    )
    return agg


# ── Step 3: insert aggregated rows into raw_data ─────────────────────────────
def ingest_raw_data(conn):
    """
    Stream cgwb_combined.csv in chunks, aggregate per district-month,
    and bulk-insert into raw_data. ON CONFLICT DO NOTHING keeps it idempotent.
    """
    print("[2/4] Ingesting raw_data (district-month GWL means)...")

    usecols = ["district_code", "date", "currentlevel"]
    total_inserted = 0
    chunk_num = 0
    t0 = time.time()

    with conn.cursor() as cur:
        for chunk in pd.read_csv(CSV_PATH, usecols=usecols,
                                 chunksize=CHUNK_SIZE, dtype=str):
            chunk_num += 1
            agg = aggregate_chunk(chunk)

            if agg.empty:
                continue

            rows = [
                (
                    str(row["district_code"]).strip(),   # district_id
                    row["month_date"].date(),             # date (DATE type)
                    "CGWB",                              # source
                    "GWL",                               # metric
                    float(row["gwl_mean"]),              # value
                )
                for _, row in agg.iterrows()
            ]

            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO raw_data (district_id, date, source, metric, value)
                VALUES %s
                ON CONFLICT (district_id, date, source, metric) DO NOTHING
                """,
                rows,
                page_size=1000,
            )
            total_inserted += len(rows)

            elapsed = time.time() - t0
            rows_processed = chunk_num * CHUNK_SIZE
            print(
                f"    Chunk {chunk_num:>3} | ~{rows_processed:>9,} rows read | "
                f"{total_inserted:>7,} district-months inserted | {elapsed:.1f}s",
                end="\r",
            )

        conn.commit()

    print()   # newline after \r progress
    print(f"    raw_data: {total_inserted:,} district-month rows inserted.")
    return total_inserted


# ── Step 4: quick sanity check ───────────────────────────────────────────────
def verify(conn):
    print("[4/4] Verification...")
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

    print(f"    districts table       : {n_districts:,} rows")
    print(f"    raw_data (CGWB GWL)  : {n_gwl:,} district-month rows")
    print(f"    Date range            : {date_min} → {date_max}")
    print(f"    Districts with data   : {n_covered:,} / {n_districts:,}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"AquaIQ CGWB Ingestion")
    print(f"  Source : {CSV_PATH.name}")
    print(f"  Size   : {CSV_PATH.stat().st_size / 1_000_000:.1f} MB")
    print()

    t_start = time.time()
    conn = get_connection()

    try:
        load_districts(conn)
        load_districts_from_geojson(conn)
        ingest_raw_data(conn)
        verify(conn)
    finally:
        conn.close()

    elapsed = time.time() - t_start
    print()
    print(f"Done in {elapsed:.1f}s ✓")


if __name__ == "__main__":
    main()
