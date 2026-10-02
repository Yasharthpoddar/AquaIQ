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


def get_data_readiness(district_id: str) -> dict:
    """
    Compute per-district data readiness (% months with valid, non-imputed data).
    If below data_readiness_min_pct, fallback to zone-level aggregation.
    """
    min_pct = CONFIG.get("crisis_score", {}).get("data_readiness_min_pct", 60)
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Count CGWB months for this district in raw_data
        cur.execute(
            "SELECT COUNT(*) FROM raw_data WHERE district_id = %s AND source = 'CGWB'",
            (district_id,)
        )
        cgwb_months = cur.fetchone()[0]

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
        "cgwb_months": cgwb_months if 'cgwb_months' in dir() else 0,
        "is_zone_fallback": is_fallback,
        "fallback_zone": zone if is_fallback else None,
    }


if __name__ == "__main__":
    print(get_data_readiness("102"))
