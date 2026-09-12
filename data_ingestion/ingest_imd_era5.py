"""
AquaIQ — IMD + ERA5 → PostgreSQL raw_data ingestion (Week 3)
--------------------------------------------------------------
Reads the already-processed CSV files and loads them into the raw_data table:
  - IMD district-monthly rainfall  → metric='rainfall'
  - ERA5 district-monthly temp/ET  → metric='temperature', 'evapotranspiration'

Prerequisites:
  - imd_district_climatology.py has been run (creates imd_rainfall_district_monthly.csv)
  - era5_to_district.py has been run (creates era5_district_monthly.csv)
  - districts table is populated (run ingest_cgwb.py first)

Run:
    python data_ingestion/ingest_imd_era5.py
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

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

IMD_CSV = ROOT / CONFIG["paths"]["data_processed"] / "imd_rainfall_district_monthly.csv"
ERA5_CSV = ROOT / CONFIG["paths"]["data_processed"] / "era5_district_monthly.csv"


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def load_district_lookup(conn) -> dict:
    """Build a lookup from district_name (lowercase) → district_id."""
    with conn.cursor() as cur:
        cur.execute("SELECT district_id, district_name FROM districts")
        rows = cur.fetchall()
    # Build both exact and normalized lookups
    lookup = {}
    for did, dname in rows:
        lookup[dname.strip().lower()] = did
        # Also try title-cased
        lookup[dname.strip().title().lower()] = did
    return lookup


def ingest_imd(conn, district_lookup: dict):
    """Load IMD district-monthly rainfall into raw_data."""
    print("[1/2] Ingesting IMD rainfall...")

    if not IMD_CSV.exists():
        print(f"    SKIP: {IMD_CSV} not found. Run imd_district_climatology.py first.")
        return 0

    df = pd.read_csv(IMD_CSV)
    print(f"    Loaded {len(df):,} rows from {IMD_CSV.name}")

    # Build date column (first of month)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
    )

    # Match district names to district_ids
    df["district_norm"] = df["district"].str.strip().str.lower()
    df["district_id"] = df["district_norm"].map(district_lookup)

    matched = df["district_id"].notna().sum()
    total = len(df)
    print(f"    Matched {matched:,} / {total:,} rows to district_ids ({matched/total*100:.0f}%)")

    df = df.dropna(subset=["district_id", "rainfall_mm"])

    rows = [
        (row["district_id"], row["date"].date(), "IMD", "rainfall", float(row["rainfall_mm"]))
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO raw_data (district_id, date, source, metric, value)
            VALUES %s
            ON CONFLICT (district_id, date, source, metric) DO NOTHING
            """,
            rows,
            page_size=2000,
        )
    conn.commit()
    print(f"    Inserted {len(rows):,} IMD rainfall rows.")
    return len(rows)


def ingest_era5(conn, district_lookup: dict):
    """Load ERA5 district-monthly temperature + ET into raw_data."""
    print("[2/2] Ingesting ERA5 temperature + evapotranspiration...")

    if not ERA5_CSV.exists():
        print(f"    SKIP: {ERA5_CSV} not found. Run era5_to_district.py first.")
        return 0

    df = pd.read_csv(ERA5_CSV)
    print(f"    Loaded {len(df):,} rows from {ERA5_CSV.name}")

    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2) + "-01"
    )

    df["district_norm"] = df["district"].str.strip().str.lower()
    df["district_id"] = df["district_norm"].map(district_lookup)

    matched = df["district_id"].notna().sum()
    total = len(df)
    print(f"    Matched {matched:,} / {total:,} rows to district_ids ({matched/total*100:.0f}%)")

    df = df.dropna(subset=["district_id"])

    # Two metrics from ERA5: temperature and evapotranspiration
    rows_temp = [
        (row["district_id"], row["date"].date(), "ERA5", "temperature", float(row["temperature"]))
        for _, row in df.iterrows()
        if pd.notna(row.get("temperature"))
    ]
    rows_et = [
        (row["district_id"], row["date"].date(), "ERA5", "evapotranspiration", float(row["evapotranspiration"]))
        for _, row in df.iterrows()
        if pd.notna(row.get("evapotranspiration"))
    ]

    all_rows = rows_temp + rows_et

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO raw_data (district_id, date, source, metric, value)
            VALUES %s
            ON CONFLICT (district_id, date, source, metric) DO NOTHING
            """,
            all_rows,
            page_size=2000,
        )
    conn.commit()
    print(f"    Inserted {len(rows_temp):,} temperature + {len(rows_et):,} ET rows.")
    return len(all_rows)


def verify(conn):
    """Quick sanity check on raw_data."""
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


def main():
    print("AquaIQ -- IMD + ERA5 PostgreSQL Ingestion\n")

    conn = get_connection()
    try:
        district_lookup = load_district_lookup(conn)
        print(f"  District lookup: {len(district_lookup)} entries\n")

        if not district_lookup:
            print("ERROR: districts table is empty. Run ingest_cgwb.py first.")
            sys.exit(1)

        ingest_imd(conn, district_lookup)
        print()
        ingest_era5(conn, district_lookup)
        verify(conn)
    finally:
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
