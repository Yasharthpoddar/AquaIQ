"""
AquaIQ — District Master Table Enrichment (Week 2 Task)
---------------------------------------------------------
Enriches the `districts` table with:
  1. agro_climatic_zone — mapped from state + region using the NARP classification
  2. geojson_name       — matched district name from the GeoJSON file (datameet.org)

The agro_climatic_zone is critical for the zone-level fallback strategy
(config.yaml crisis_score.fallback_strategy): districts without enough
CGWB data get aggregated by zone instead of being silently dropped.

Run:
    python data_ingestion/enrich_districts.py

Prerequisites:
    - districts table must be populated (run ingest_cgwb.py first)
    - data/raw/india_districts.geojson must exist
"""

from pathlib import Path
import sys

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)


# ── Agro-Climatic Zone mapping ─────────────────────────────────────────────
# India's 15 agro-climatic zones (NARP / Planning Commission classification).
# Each state is mapped to its primary zone. Multi-zone states use the dominant
# zone — a more granular mapping (district-level) would need a separate
# lookup file, but state-level is sufficient for the fallback aggregation.
STATE_TO_ZONE = {
    # Western Himalayan Region
    "Jammu And Kashmir": "Western Himalayan",
    "Jammu & Kashmir": "Western Himalayan",
    "Ladakh": "Western Himalayan",
    "Himachal Pradesh": "Western Himalayan",
    "Uttarakhand": "Western Himalayan",

    # Eastern Himalayan Region
    "Arunachal Pradesh": "Eastern Himalayan",
    "Sikkim": "Eastern Himalayan",
    "Meghalaya": "Eastern Himalayan",
    "Nagaland": "Eastern Himalayan",
    "Manipur": "Eastern Himalayan",
    "Mizoram": "Eastern Himalayan",
    "Tripura": "Eastern Himalayan",
    "Assam": "Eastern Himalayan",

    # Lower Gangetic Plains
    "West Bengal": "Lower Gangetic Plains",

    # Middle Gangetic Plains
    "Bihar": "Middle Gangetic Plains",
    "Jharkhand": "Middle Gangetic Plains",
    "Eastern Uttar Pradesh": "Middle Gangetic Plains",

    # Upper Gangetic Plains
    "Uttar Pradesh": "Upper Gangetic Plains",

    # Trans-Gangetic Plains
    "Punjab": "Trans-Gangetic Plains",
    "Haryana": "Trans-Gangetic Plains",
    "Delhi": "Trans-Gangetic Plains",
    "Chandigarh": "Trans-Gangetic Plains",
    "Nct Of Delhi": "Trans-Gangetic Plains",
    "NCT of Delhi": "Trans-Gangetic Plains",

    # Eastern Plateau and Hills
    "Chhattisgarh": "Eastern Plateau and Hills",
    "Odisha": "Eastern Plateau and Hills",
    "Orissa": "Eastern Plateau and Hills",

    # Central Plateau and Hills
    "Madhya Pradesh": "Central Plateau and Hills",
    "Rajasthan": "Western Dry Region",  # Rajasthan is primarily Western Dry
    "Bundelkhand": "Central Plateau and Hills",

    # Western Plateau and Hills
    "Maharashtra": "Western Plateau and Hills",

    # Southern Plateau and Hills
    "Karnataka": "Southern Plateau and Hills",
    "Andhra Pradesh": "Southern Plateau and Hills",
    "Telangana": "Southern Plateau and Hills",

    # East Coast Plains and Hills
    "Tamil Nadu": "East Coast Plains and Hills",
    "Puducherry": "East Coast Plains and Hills",
    "Pondicherry": "East Coast Plains and Hills",

    # West Coast Plains and Ghats
    "Goa": "West Coast Plains and Ghats",
    "Kerala": "West Coast Plains and Ghats",

    # Gujarat Plains and Hills
    "Gujarat": "Gujarat Plains and Hills",
    "Dadra And Nagar Haveli": "Gujarat Plains and Hills",
    "Dadra & Nagar Haveli": "Gujarat Plains and Hills",
    "Daman And Diu": "Gujarat Plains and Hills",
    "Daman & Diu": "Gujarat Plains and Hills",
    "Dadra And Nagar Haveli And Daman And Diu": "Gujarat Plains and Hills",

    # Island Region
    "Andaman And Nicobar": "Island Region",
    "Andaman & Nicobar": "Island Region",
    "Andaman And Nicobar Islands": "Island Region",
    "Lakshadweep": "Island Region",
}


def get_connection():
    from db.connection import get_connection as connect
    return connect()


def zone_for_state(state):
    """Use only an explicit state alias; never guess an administrative identity."""
    from data_ingestion.ingest_imd_era5 import norm_state
    zones = {norm_state(name): zone for name, zone in STATE_TO_ZONE.items()}
    return zones.get(norm_state(state))


def match_geojson_name(district_name, state, boundaries):
    """Resolve one recorded name/alias inside the same normalized state."""
    from data_ingestion.ingest_imd_era5 import norm_str, norm_state, NAME_ALIASES
    district = norm_str(district_name)
    names = {district, *(norm_str(alias) for alias in NAME_ALIASES.get(district, []))}
    matches = {row.district for row in boundaries.itertuples(index=False)
               if norm_state(row.st_nm) == norm_state(state) and norm_str(row.district) in names}
    return next(iter(matches)) if len(matches) == 1 else None


def enrich_zones(conn):
    """Fill agro_climatic_zone based on state name."""
    print("[1/2] Enriching agro_climatic_zone from state mapping...")

    with conn.cursor() as cur:
        cur.execute("SELECT district_id, state FROM districts WHERE agro_climatic_zone IS NULL")
        rows = cur.fetchall()

    if not rows:
        print("    All districts already have zones assigned.")
        return

    updated = 0
    unmatched_states = set()
    with conn.cursor() as cur:
        for district_id, state in rows:
            zone = zone_for_state(state)

            if zone:
                cur.execute(
                    "UPDATE districts SET agro_climatic_zone = %s WHERE district_id = %s",
                    (zone, district_id)
                )
                updated += 1
            else:
                unmatched_states.add(state)

    conn.commit()
    print(f"    Updated {updated} / {len(rows)} districts.")
    if unmatched_states:
        print(f"    WARNING: {len(unmatched_states)} unmatched states: {sorted(unmatched_states)}")
        print("    Add these to STATE_TO_ZONE mapping in this script.")


def enrich_geojson_names(conn):
    """Match district names to GeoJSON feature names for the dashboard map."""
    print("[2/2] Matching district names to GeoJSON names...")

    try:
        import geopandas as gpd
    except ImportError:
        print("    SKIP: geopandas not installed. Run: pip install geopandas")
        return

    geojson_path = ROOT / CONFIG["paths"]["geojson_boundaries"]
    if not geojson_path.exists():
        print(f"    SKIP: GeoJSON not found at {geojson_path}")
        return

    gdf = gpd.read_file(geojson_path)
    if not {"district", "st_nm"}.issubset(gdf.columns):
        print("    SKIP: GeoJSON must contain district and state (st_nm) columns.")
        return
    boundaries = gdf[["district", "st_nm"]].dropna().drop_duplicates()

    print(f"    GeoJSON has {len(boundaries)} state-qualified district names.")

    with conn.cursor() as cur:
        cur.execute("SELECT district_id, district_name, state FROM districts WHERE geojson_name IS NULL")
        rows = cur.fetchall()

    if not rows:
        print("    All districts already have geojson_name assigned.")
        return

    matched = 0
    unmatched = []
    with conn.cursor() as cur:
        for district_id, district_name, state in rows:
            geo_match = match_geojson_name(district_name, state, boundaries)

            if geo_match:
                cur.execute(
                    "UPDATE districts SET geojson_name = %s WHERE district_id = %s",
                    (geo_match, district_id)
                )
                matched += 1
            else:
                unmatched.append(district_name)

    conn.commit()
    match_pct = matched / len(rows) * 100 if rows else 0
    print(f"    Matched {matched} / {len(rows)} districts ({match_pct:.0f}%).")
    if unmatched and len(unmatched) <= 20:
        print(f"    Unmatched: {unmatched}")
    elif unmatched:
        print(f"    {len(unmatched)} unmatched districts (showing first 10): {unmatched[:10]}")


def verify(conn):
    """Print summary stats after enrichment."""
    print("\n  Summary:")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM districts")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM districts WHERE agro_climatic_zone IS NOT NULL")
        with_zone = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM districts WHERE geojson_name IS NOT NULL")
        with_geojson = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT agro_climatic_zone) FROM districts WHERE agro_climatic_zone IS NOT NULL")
        n_zones = cur.fetchone()[0]

    print(f"    Total districts          : {total}")
    print(f"    With agro_climatic_zone  : {with_zone} / {total} ({with_zone/total*100:.0f}%)")
    print(f"    With geojson_name        : {with_geojson} / {total} ({with_geojson/total*100:.0f}%)")
    print(f"    Distinct zones           : {n_zones}")


def main():
    print("AquaIQ — District Master Table Enrichment\n")
    conn = get_connection()
    try:
        enrich_zones(conn)
        enrich_geojson_names(conn)
        verify(conn)
    finally:
        conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
