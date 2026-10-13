"""
AquaIQ -- IMD Rainfall -> District Climatological Normal (Yash, Week 2, Task 3)
--------------------------------------------------------------------------------
Full pipeline in one script:
  1. Read every downloaded IMD .GRD binary file (2002-2024) in data/raw/imd/
  2. Collapse daily -> monthly mean, per grid point
  3. Spatial join grid points to district polygons (Ayush's GeoJSON)
  4. Aggregate to district-monthly rainfall
  5. Compute the climatological normal: for each district, the average
     rainfall for each calendar month (Jan..Dec) across all years available.
     This is what monsoon_deficit_pct compares against in Week 4.

Also saves the intermediate district-monthly table -- useful again for
Task 2 (correlation with GWL) once Yasharth's CGWB data is ready.

NOTE on "30-year": we only have 2002-2024 downloaded (23 years), not a full
WMO 30-year window (e.g. 1991-2020). Given the timeline, this script treats
2002-2024 as the baseline period -- document this explicitly in the report
as a scoping decision, not silently claim a true 30-year WMO normal. If you
have time later, download 1991-2001 the same way (same dropdown) and rerun.
"""

import calendar
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data_ingestion.spatial import assign_grid_cells

RAW_DIR = ROOT / "data/raw/imd"
GEOJSON_PATH = ROOT / "data/raw/india_districts.geojson"

OUT_DISTRICT_MONTHLY = ROOT / "data/processed/imd_rainfall_district_monthly.csv"
OUT_CLIMATOLOGY = ROOT / "data/processed/imd_climatological_normal.csv"

NX, NY = 135, 129  # IMD grid dimensions
LAT_START, LON_START = 6.5, 66.5
GRID_STEP = 0.25

DISTRICT_COL = "district"   # confirmed from the uploaded GeoJSON's properties
STATE_COL = "st_nm"         # keeps same-named districts in different states separate


def find_grd_files(raw_dir):
    """Glob every .grd/.GRD file and pull the year out of the filename."""
    files = glob.glob(os.path.join(raw_dir, "*.[Gg][Rr][Dd]"))
    year_files = []
    for f in files:
        match = re.search(r"(19|20)\d{2}", os.path.basename(f))
        if match:
            year_files.append((int(match.group()), f))
    return sorted(year_files)


def read_grd_file(filepath: str, year: int) -> np.ndarray:
    n_days = 366 if calendar.isleap(year) else 365
    data = np.fromfile(filepath, dtype=np.float32)
    expected = n_days * NX * NY
    if data.size != expected:
        raise ValueError(
            f"{filepath}: expected {expected} values for {n_days} days, "
            f"got {data.size}. Check the file downloaded correctly."
        )
    data = data.reshape(n_days, NY, NX)
    data[data < 0] = np.nan  # IMD's missing/ocean sentinel
    return data


def grid_to_long_monthly(data: np.ndarray, year: int) -> pd.DataFrame:
    n_days = data.shape[0]
    dates = pd.date_range(f"{year}-01-01", periods=n_days, freq="D")
    lats = LAT_START + np.arange(NY) * GRID_STEP
    lons = LON_START + np.arange(NX) * GRID_STEP
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    frames = []
    for month in range(1, 13):
        mask = dates.month == month
        month_data = data[mask]
        valid_count = np.sum(~np.isnan(month_data), axis=0)
        monthly_total = np.nansum(month_data, axis=0)
        # A partial daily sum is not a complete monthly rainfall total.
        monthly_total = np.where(valid_count == month_data.shape[0], monthly_total, np.nan)
        df = pd.DataFrame(
            {
                "latitude": lat_grid.ravel(),
                "longitude": lon_grid.ravel(),
                "rainfall_mm": monthly_total.ravel(),
                "lat_idx": np.repeat(np.arange(NY), NX),
                "lon_idx": np.tile(np.arange(NX), NY),
            }
        )
        df["year"] = year
        df["month"] = month
        frames.append(df.dropna(subset=["rainfall_mm"]))
    return pd.concat(frames, ignore_index=True)


def assign_district(points_df: pd.DataFrame, districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    geometry = [Point(xy) for xy in zip(points_df["longitude"], points_df["latitude"])]
    gdf = gpd.GeoDataFrame(points_df, geometry=geometry, crs="EPSG:4326")
    
    period_cols = [c for c in ("year", "month") if c in gdf]
    if period_cols:
        assignments = [assign_grid_cells(frame, districts) for _, frame in gdf.groupby(period_cols, sort=True)]
        return gpd.GeoDataFrame(pd.concat(assignments, ignore_index=True), geometry="geometry", crs=gdf.crs)
    return assign_grid_cells(gdf, districts)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regenerate_imd(raw_dir=RAW_DIR, geojson_path=GEOJSON_PATH,
                   out_path=OUT_DISTRICT_MONTHLY, normal_path=OUT_CLIMATOLOGY):
    """Aggregate one year/month at a time; never materialize all grid years.

    GRD inputs are read only. The normals artifact is descriptive all-years
    climatology with explicit baseline metadata; modeling uses causal expanding
    prior-year normals instead of this future-containing descriptive artifact.
    """
    raw_dir, out_path, normal_path = Path(raw_dir), Path(out_path), Path(normal_path)
    year_files = find_grd_files(raw_dir)
    if not year_files:
        raise ValueError(f"No .grd files found in {raw_dir}")
    if len({year for year, _ in year_files}) != len(year_files):
        raise ValueError("Duplicate input files for an IMD year; resolve source provenance first")
    print(f"Found {len(year_files)} year files: {[y for y, _ in year_files]}")
    districts = gpd.read_file(geojson_path)
    district_frames = []
    source_metadata = []
    for year, filepath in year_files:
        print(f"  Processing IMD {year}...")
        grid = read_grd_file(filepath, year)
        points = grid_to_long_monthly(grid, year)
        del grid
        for month, monthly_points in points.groupby("month", sort=True):
            if monthly_points.empty:
                continue
            joined = assign_district(monthly_points, districts)
            aggregated = joined.groupby([DISTRICT_COL, STATE_COL, "year", "month"]).agg(
                rainfall_mm=("rainfall_mm", "mean"), spatial_method=("spatial_method", "first"),
                distance_m=("distance_m", "max"), n_cells=("_grid_index", "nunique")).reset_index()
            district_frames.append(aggregated)
        source_metadata.append({"year": year, "path": str(filepath), "sha256": _sha256(filepath)})
    district_monthly = pd.concat(district_frames, ignore_index=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    district_monthly.to_csv(out_path, index=False)
    print(f"  saved {len(district_monthly):,} rows to {out_path}")

    print("\nComputing climatological normal (mean per district per calendar month)...")
    climatology = (
        district_monthly.groupby([DISTRICT_COL, STATE_COL, "month"])
        .agg(
            climatological_normal_mm=("rainfall_mm", "mean"),
            n_years=("year", "nunique"),
            baseline_start=("year", "min"),
            baseline_end=("year", "max"),
        )
        .reset_index()
    )
    climatology["purpose"] = "descriptive_all_years_not_historical_model_features"
    normal_path.parent.mkdir(parents=True, exist_ok=True)
    climatology.to_csv(normal_path, index=False)
    metadata = {"artifact_version": "weather-v3", "sources": source_metadata,
                "geojson_sha256": _sha256(geojson_path), "csv_sha256": _sha256(out_path),
                "units": {"rainfall_mm": "mm/month"}, "daily_aggregation": "sum_all_calendar_days_required",
                "spatial_fallback": "district_to_nearest_usable_land_cell",
                "baseline_start": year_files[0][0], "baseline_end": year_files[-1][0],
                "n_years": len(year_files), "climatology_purpose": "descriptive_only"}
    out_path.with_suffix(".manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    normal_path.with_suffix(".manifest.json").write_text(json.dumps({**metadata, "csv_sha256": _sha256(normal_path)}, indent=2), encoding="utf-8")
    print(f"  saved {len(climatology):,} rows to {normal_path}")
    print(f"\nDone. Baseline period: {year_files[0][0]}-{year_files[-1][0]} "
          f"({len(year_files)} years) -- note this in your report as the scoping decision.")
    return district_monthly


def main(argv=None):
    parser = argparse.ArgumentParser(description="Regenerate monthly IMD totals without materializing all grid years")
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--geojson", default=str(GEOJSON_PATH))
    parser.add_argument("--out", default=str(OUT_DISTRICT_MONTHLY))
    parser.add_argument("--normals-out", default=str(OUT_CLIMATOLOGY))
    args = parser.parse_args(argv)
    regenerate_imd(args.raw_dir, args.geojson, args.out, args.normals_out)


if __name__ == "__main__":
    main()
