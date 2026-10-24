"""Build verified India states GeoJSON by dissolving Datameet district boundaries.

Creates dashboard/public/india_states.geojson with exact boundary alignment to
the project's canonical district GeoJSON.
"""
from pathlib import Path
import geopandas as gpd
import json

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.state_mapping import resolve_state_id, STATES_REGISTRY

district_geojson_path = ROOT / 'dashboard/public/india_districts.geojson'
output_path = ROOT / 'dashboard/public/india_states.geojson'

gdf = gpd.read_file(district_geojson_path)
state_gdf = gdf.dissolve(by=['st_nm', 'st_code']).reset_index()

# Map st_nm to verified 2-letter state_id
state_gdf['state_id'] = state_gdf['st_nm'].apply(resolve_state_id)
state_gdf['state_name'] = state_gdf['state_id'].map(lambda sid: STATES_REGISTRY[sid]['name'])
state_gdf['st_code'] = state_gdf['state_id'].map(lambda sid: STATES_REGISTRY[sid]['st_code'])

clean_gdf = state_gdf[['state_id', 'state_name', 'st_code', 'geometry']].sort_values('state_name')

# Verify exactly 36 states
assert len(clean_gdf) == 36, f"Expected 36 states, got {len(clean_gdf)}"
assert clean_gdf['state_id'].nunique() == 36, "Duplicate state IDs found"
assert set(clean_gdf['state_id']) == set(STATES_REGISTRY.keys()), "Mismatch with registry"

# Save GeoJSON
clean_gdf.to_file(output_path, driver='GeoJSON')
size_kb = output_path.stat().st_size / 1024
print(f"Successfully created {output_path} ({size_kb:.1f} KB, 36 states verified).")
