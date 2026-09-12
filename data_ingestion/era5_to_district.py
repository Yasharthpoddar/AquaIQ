"""
AquaIQ -- ERA5 NetCDF -> District Monthly (Yash, Week 3 prep)
--------------------------------------------------------------------
Takes the ERA5 file downloaded in Week 1 and collapses it to district-monthly
temperature + evapotranspiration, same pattern as imd_district_climatology.py
did for rainfall. Needed before the PostgreSQL ingestion script can load ERA5.

Auto-handles the .zip if you haven't extracted it yet.
"""

import glob
import os
import zipfile

import geopandas as gpd
import pandas as pd
import xarray as xr
from shapely.geometry import Point

ERA5_DIR = "data/raw/era5"
GEOJSON_PATH = "data/raw/india_districts.geojson"
OUT_PATH = "data/processed/era5_district_monthly.csv"

DISTRICT_COL = "district"
STATE_COL = "st_nm"


def ensure_extracted(era5_dir):
    nc_files = glob.glob(os.path.join(era5_dir, "*.nc"))
    if nc_files:
        return nc_files[0]
    zip_files = glob.glob(os.path.join(era5_dir, "*.zip"))
    if not zip_files:
        raise SystemExit(f"No .nc or .zip file found in {era5_dir} -- check the download finished.")
    print(f"Extracting {zip_files[0]}...")
    with zipfile.ZipFile(zip_files[0], "r") as z:
        z.extractall(era5_dir)
    nc_files = glob.glob(os.path.join(era5_dir, "*.nc"))
    if not nc_files:
        raise SystemExit("Extracted the zip but found no .nc file inside -- check contents manually.")
    return nc_files[0]


def load_era5_as_points(nc_path: str) -> pd.DataFrame:
    ds = xr.open_dataset(nc_path, engine="netcdf4")
    df = ds.to_dataframe().reset_index()
    df = df.rename(columns={"t2m": "temperature_k", "pev": "pet_raw"})
    df["temperature"] = df["temperature_k"] - 273.15
    df["evapotranspiration"] = df["pet_raw"] * -1000  # sign flip, m -> mm

    time_col = "valid_time" if "valid_time" in df.columns else "time"
    df["year"] = df[time_col].dt.year
    df["month"] = df[time_col].dt.month
    return df[["latitude", "longitude", "year", "month", "temperature", "evapotranspiration"]]


def assign_district(df: pd.DataFrame, districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    geometry = [Point(xy) for xy in zip(df["longitude"], df["latitude"])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    return gpd.sjoin(gdf, districts[[DISTRICT_COL, STATE_COL, "geometry"]], how="inner", predicate="within")


if __name__ == "__main__":
    nc_path = ensure_extracted(ERA5_DIR)
    print(f"Using {nc_path}")

    print("Loading ERA5 grid points...")
    points = load_era5_as_points(nc_path)
    print(f"  {len(points):,} grid-point-months")

    print("Loading district boundaries...")
    districts = gpd.read_file(GEOJSON_PATH)

    print("Spatial join...")
    joined = assign_district(points, districts)

    print("Aggregating to district-monthly...")
    district_monthly = (
        joined.groupby([DISTRICT_COL, STATE_COL, "year", "month"])
        .agg(temperature=("temperature", "mean"), evapotranspiration=("evapotranspiration", "mean"))
        .reset_index()
    )
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    district_monthly.to_csv(OUT_PATH, index=False)
    print(f"Saved {len(district_monthly):,} rows to {OUT_PATH}")
