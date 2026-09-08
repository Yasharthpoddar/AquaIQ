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
import glob
import os
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

RAW_DIR = "data/raw/imd"
GEOJSON_PATH = "data/raw/india_districts.geojson"

OUT_DISTRICT_MONTHLY = "data/processed/imd_rainfall_district_monthly.csv"
OUT_CLIMATOLOGY = "data/processed/imd_climatological_normal.csv"

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
        monthly_total = np.where(valid_count == 0, np.nan, monthly_total)
        df = pd.DataFrame(
            {
                "latitude": lat_grid.ravel(),
                "longitude": lon_grid.ravel(),
                "rainfall_mm": monthly_total.ravel(),
            }
        )
        df["year"] = year
        df["month"] = month
        frames.append(df.dropna(subset=["rainfall_mm"]))
    return pd.concat(frames, ignore_index=True)


def assign_district(points_df: pd.DataFrame, districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    geometry = [Point(xy) for xy in zip(points_df["longitude"], points_df["latitude"])]
    gdf = gpd.GeoDataFrame(points_df, geometry=geometry, crs="EPSG:4326")
    return gpd.sjoin(gdf, districts[[DISTRICT_COL, STATE_COL, "geometry"]], how="inner", predicate="within")


if __name__ == "__main__":
    year_files = find_grd_files(RAW_DIR)
    if not year_files:
        raise SystemExit(f"No .grd files found in {RAW_DIR} -- download them first.")
    print(f"Found {len(year_files)} year files: {[y for y, _ in year_files]}")

    print("\nReading + collapsing to monthly grids...")
    all_points = []
    for year, filepath in year_files:
        grid = read_grd_file(filepath, year)
        all_points.append(grid_to_long_monthly(grid, year))
    points_df = pd.concat(all_points, ignore_index=True)
    print(f"  {len(points_df):,} grid-point-months total")

    print("\nLoading district boundaries...")
    districts = gpd.read_file(GEOJSON_PATH)
    print(f"  {len(districts)} districts loaded")

    print("\nSpatial join (grid points -> districts)...")
    joined = assign_district(points_df, districts)

    print("Aggregating to district-monthly rainfall...")
    district_monthly = (
        joined.groupby([DISTRICT_COL, STATE_COL, "year", "month"])["rainfall_mm"]
        .mean()
        .reset_index()
    )
    os.makedirs(os.path.dirname(OUT_DISTRICT_MONTHLY), exist_ok=True)
    district_monthly.to_csv(OUT_DISTRICT_MONTHLY, index=False)
    print(f"  saved {len(district_monthly):,} rows to {OUT_DISTRICT_MONTHLY}")

    print("\nComputing climatological normal (mean per district per calendar month)...")
    climatology = (
        district_monthly.groupby([DISTRICT_COL, STATE_COL, "month"])
        .agg(
            climatological_normal_mm=("rainfall_mm", "mean"),
            n_years=("year", "nunique"),
        )
        .reset_index()
    )
    climatology.to_csv(OUT_CLIMATOLOGY, index=False)
    print(f"  saved {len(climatology):,} rows to {OUT_CLIMATOLOGY}")
    print(f"\nDone. Baseline period: {year_files[0][0]}-{year_files[-1][0]} "
          f"({len(year_files)} years) -- note this in your report as the scoping decision.")
