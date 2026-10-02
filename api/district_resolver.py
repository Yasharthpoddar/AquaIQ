"""
AquaIQ -- District ID resolver.

The districts table has two kinds of IDs:
  - Numeric IDs from CGWB CSV (e.g., '102' for Jaipur)
  - Composite IDs from GeoJSON (e.g., 'RJ-Jaipur')

The API, frontend, and tests all use the human-readable composite format.
This module resolves a composite ID to the CGWB numeric ID that actually
has data in raw_data and features, so queries return real results.
"""

import os
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


def get_connection():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


@lru_cache(maxsize=2000)
def resolve_district_id(district_id: str) -> str:
    """
    Given any district_id (numeric or composite), return the district_id
    that has actual CGWB data in the features table.

    Resolution order:
      1. If the given ID itself has features data, return it.
      2. If it looks composite (e.g., 'RJ-Jaipur'), extract the district
         name and find a numeric-ID row in districts with the same name.
      3. If it looks numeric, find the composite equivalent.
      4. Fall back to the given ID as-is.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Step 1: Does this ID already have feature data?
        cur.execute(
            "SELECT COUNT(*) FROM features WHERE district_id = %s AND gwl_current IS NOT NULL",
            (district_id,)
        )
        if cur.fetchone()[0] > 0:
            conn.close()
            return district_id

        # Step 2: Extract district name and search for an alternative ID
        # Composite format: 'RJ-Jaipur' or 'RJ-Jaipur_City'
        parts = district_id.split("-", 1)
        if len(parts) == 2:
            district_name = parts[1].replace("_", " ")
        else:
            district_name = district_id

        # Find all IDs for this district name
        cur.execute(
            "SELECT district_id FROM districts WHERE LOWER(district_name) = LOWER(%s)",
            (district_name,)
        )
        candidates = [row[0] for row in cur.fetchall()]

        # Among candidates, find the one with actual feature data
        for cid in candidates:
            if cid == district_id:
                continue
            cur.execute(
                "SELECT COUNT(*) FROM features WHERE district_id = %s AND gwl_current IS NOT NULL",
                (cid,)
            )
            if cur.fetchone()[0] > 0:
                conn.close()
                return cid

        conn.close()
    except Exception:
        pass

    # Fallback: return as-is
    return district_id


def get_district_metadata(district_id: str) -> dict:
    """Get district name, state, and zone from the districts table."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT district_name, state, agro_climatic_zone FROM districts WHERE district_id = %s",
            (district_id,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "name": row[0],
                "state": row[1],
                "agro_climatic_zone": row[2],
            }
    except Exception:
        pass

    # Fallback: parse from composite ID
    parts = district_id.split("-", 1)
    return {
        "name": parts[1].replace("_", " ") if len(parts) == 2 else district_id,
        "state": parts[0] if len(parts) == 2 else "Unknown",
        "agro_climatic_zone": None,
    }
