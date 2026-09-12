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

import os
import sys
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
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


def normalize(name: str) -> str:
    """Normalize district/state names for matching."""
    return name.strip().lower().replace("&", "and").replace("-", " ")


def fuzzy_match(name: str, candidates: list[str], threshold: float = 0.7) -> str | None:
    """Find the best fuzzy match for a name in a list of candidates."""
    best_match = None
    best_score = 0.0
    name_norm = normalize(name)
    for c in candidates:
        score = SequenceMatcher(None, name_norm, normalize(c)).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = c
    return best_match


def get_connection():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


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
            # Try exact match first, then title-cased
            zone = STATE_TO_ZONE.get(state)
            if zone is None:
                zone = STATE_TO_ZONE.get(state.strip().title())
            if zone is None:
                # Try fuzzy match
                matched_state = fuzzy_match(state, list(STATE_TO_ZONE.keys()), 0.8)
                if matched_state:
                    zone = STATE_TO_ZONE[matched_state]

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
    geo_names = gdf["district"].tolist() if "district" in gdf.columns else []
    if not geo_names:
        print("    SKIP: GeoJSON has no 'district' column.")
        return

    print(f"    GeoJSON has {len(geo_names)} district names.")

    with conn.cursor() as cur:
        cur.execute("SELECT district_id, district_name FROM districts WHERE geojson_name IS NULL")
        rows = cur.fetchall()

    if not rows:
        print("    All districts already have geojson_name assigned.")
        return

    matched = 0
    unmatched = []
    with conn.cursor() as cur:
        for district_id, district_name in rows:
            # Try exact match (case-insensitive)
            geo_match = None
            for gn in geo_names:
                if normalize(gn) == normalize(district_name):
                    geo_match = gn
                    break

            # Fuzzy match fallback
            if geo_match is None:
                geo_match = fuzzy_match(district_name, geo_names, 0.75)

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
