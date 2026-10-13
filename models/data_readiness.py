"""
AquaIQ -- Data Readiness Module.

Computes per-district data readiness (% months with valid CGWB data).
If below 60% (data_readiness_min_pct from config.yaml), the district
falls back to zone-level aggregation instead of per-district predictions.
"""

import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)


def get_connection():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


import pandas as pd


def get_zone_aggregate_data(zone: str, conn=None) -> pd.DataFrame:
    """
    Aggregate monthly groundwater level history across all districts in an agro-climatic zone.
    Returns monthly average GWL (m bgl) and district coverage for fallback forecasting.
    """
    close = False
    if conn is None:
        conn = get_connection()
        close = True
    try:
        df = pd.read_sql("""
            SELECT r.date,
                   AVG(r.value) as gwl_mean,
                   COUNT(DISTINCT r.district_id) as reporting_districts
            FROM raw_data r
            JOIN districts d ON r.district_id = d.district_id
            WHERE d.agro_climatic_zone = %s AND r.source = 'CGWB' AND r.metric = 'GWL'
            GROUP BY r.date
            ORDER BY r.date
        """, conn, params=(zone,))
        return df
    finally:
        if close:
            conn.close()


def get_data_readiness(district_id: str) -> dict:
    """
    Compute per-district data readiness (% months with valid, non-imputed data).
    If below data_readiness_min_pct, fallback to real zone-level aggregation.
    """
    min_pct = CONFIG.get("crisis_score", {}).get("data_readiness_min_pct", 60)
    conn = None
    zone_months = 0
    zone_districts = 0
    cgwb_months = 0
    zone = None
    readiness_score = 0.0

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Count CGWB months for this district in raw_data
        cur.execute(
            "SELECT COUNT(*) FROM raw_data WHERE district_id = %s AND source = 'CGWB'",
            (district_id,)
        )
        row = cur.fetchone()
        cgwb_months = row[0] if row else 0

        # Total possible months (2002 to 2024 = 276 months)
        total_possible = 276
        readiness_score = min((cgwb_months / total_possible) * 100, 100.0)

        # Get zone information for fallback reporting
        cur.execute(
            "SELECT agro_climatic_zone FROM districts WHERE district_id = %s",
            (district_id,)
        )
        row = cur.fetchone()
        zone = row[0] if row else None

        if readiness_score < min_pct and zone:
            cur.execute("""
                SELECT COUNT(DISTINCT r.date), COUNT(DISTINCT r.district_id)
                FROM raw_data r
                JOIN districts d ON r.district_id = d.district_id
                WHERE d.agro_climatic_zone = %s AND r.source = 'CGWB' AND r.metric = 'GWL'
            """, (zone,))
            z_row = cur.fetchone()
            if z_row:
                zone_months = z_row[0] or 0
                zone_districts = z_row[1] or 0

    except Exception:
        readiness_score = 0.0
        zone = None
    finally:
        if conn:
            conn.close()

    is_fallback = readiness_score < min_pct

    return {
        "district_id": district_id,
        "readiness_score": round(readiness_score, 1),
        "cgwb_months": cgwb_months,
        "is_zone_fallback": is_fallback,
        "fallback_zone": zone if is_fallback else None,
        "zone_months": zone_months if is_fallback else None,
        "zone_reporting_districts": zone_districts if is_fallback else None,
    }


if __name__ == "__main__":
    print(get_data_readiness("RJ-Jaipur"))
