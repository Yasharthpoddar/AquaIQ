"""
AquaIQ -- ERA5 NetCDF -> District Monthly
--------------------------------------------------------------------
Collapses gridded ERA5 NetCDF temperature + evapotranspiration to district-monthly
aggregates using Datameet GeoJSON district boundaries.
Includes:
- Robust spatial join fallback using representative nearest points for small/boundary districts (D7).
- PEV conversion to mm/month: pev * -1000 * days_in_month (D3).
Produces data/processed/era5_district_monthly.csv for database ingestion.
"""

import glob
import argparse
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data_ingestion.spatial import assign_grid_cells
ERA5_DIR = ROOT / "data" / "raw" / "era5"
CLEAN_NC_PATH = ROOT / "data" / "processed" / "era5_india_2002_2024_clean.nc"
GEOJSON_PATH = ROOT / "data" / "raw" / "india_districts.geojson"
OUT_PATH = ROOT / "data" / "processed" / "era5_district_monthly.csv"

DISTRICT_COL = "district"
STATE_COL = "st_nm"


def convert_pev_to_mm_per_month(pev_rate: float, dt: pd.Timestamp) -> float:
    """
    Convert ERA5 PEV rate (m/day avgad) to mm/month.
    Multiply by -1000 (sign flip for evaporative flux away from surface + m -> mm)
    and by days in the calendar month.
    """
    days = dt.days_in_month
    val = pev_rate * -1000.0 * days
    return max(0.0, float(val))


def assign_districts_with_fallback(
    pts_gdf: gpd.GeoDataFrame, districts_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """
    Spatially joins grid points to district polygons.
    For small or boundary districts containing zero grid points under 'within',
    falls back to nearest grid point from the district's representative point (D7).
    """
    return assign_grid_cells(pts_gdf, districts_gdf)


def evaporation_monthly(values, attrs, times):
    """Convert a documented ERA5 daily rate or monthly total exactly once.

    ERA5 moda/avgad accumulated fields tagged m are daily means. A processed
    mm/month field is already accumulated and is not multiplied a second time.
    Unknown units/aggregation must be resolved at source, never guessed.
    """
    units = str(attrs.get("units", attrs.get("GRIB_units", ""))).strip().lower()
    step = str(attrs.get("GRIB_stepType", attrs.get("step_type", ""))).lower()
    stream = str(attrs.get("GRIB_stream", attrs.get("stream", ""))).lower()
    daily = step == "avgad" or stream == "moda"
    days = np.asarray(pd.DatetimeIndex(times).days_in_month, dtype=float)[:, None, None]
    if units in {"mm/month", "mm month-1", "mm month^-1"}:
        result = np.asarray(values, dtype=float)
    elif units in {"mm/day", "mm day-1", "mm d-1"}:
        result = np.asarray(values, dtype=float) * days
    elif units in {"m/day", "m day-1", "m d-1"} or units == "m" and daily:
        result = np.asarray(values, dtype=float) * -1000.0 * days
    elif units in {"m/month", "m month-1"}:
        result = np.asarray(values, dtype=float) * -1000.0
    else:
        raise ValueError(f"Unknown ERA5 evaporation units/aggregation: {units!r}, step={step!r}, stream={stream!r}")
    return np.maximum(0.0, result)


def find_or_extract_nc():
    """Locate a valid NetCDF dataset, extracting zip files if necessary."""
    if CLEAN_NC_PATH.exists():
        try:
            ds = xr.open_dataset(CLEAN_NC_PATH, engine="netcdf4")
            ds.close()
            return str(CLEAN_NC_PATH)
        except Exception:
            pass

    # Look in raw era5 dir
    candidates = glob.glob(str(ERA5_DIR / "*"))
    for cand in candidates:
        if cand.endswith((".nc", ".zip")):
            with open(cand, "rb") as f:
                header = f.read(4)
            if header.startswith(b"PK"):
                print(f"Extracting zip archive {cand}...")
                with zipfile.ZipFile(cand, "r") as z:
                    z.extractall(ERA5_DIR)
                extracted_ncs = [f for f in glob.glob(str(ERA5_DIR / "*.nc")) if f != cand]
                if extracted_ncs:
                    return extracted_ncs[0]
            elif header.startswith((b"CDF", b"\x89HDF")):
                return cand

    raise SystemExit("No valid NetCDF or zip archive found in ERA5 directories.")


def process_era5_to_districts(nc_path=None, geojson_path=None, out_path=None):
    nc_path = Path(nc_path or find_or_extract_nc())
    geojson_path = Path(geojson_path or GEOJSON_PATH)
    out_path = Path(out_path or OUT_PATH)
    print(f"Using NetCDF dataset: {nc_path}")

    ds = xr.open_dataset(nc_path, engine="netcdf4")
    lats = ds["latitude"].values
    lons = ds["longitude"].values

    time_col = "valid_time" if "valid_time" in ds.coords or "valid_time" in ds.variables else "time"
    times = pd.to_datetime(ds[time_col].values)

    lat_map = {v: i for i, v in enumerate(lats)}
    lon_map = {v: i for i, v in enumerate(lons)}

    lon_grid, lat_grid = np.meshgrid(lons, lats)
    pts_df = pd.DataFrame({
        "longitude": lon_grid.flatten(),
        "latitude": lat_grid.flatten(),
    })
    pts_df["lat_idx"] = pts_df["latitude"].map(lat_map)
    pts_df["lon_idx"] = pts_df["longitude"].map(lon_map)

    pts_gdf = gpd.GeoDataFrame(
        pts_df,
        geometry=[Point(x, y) for x, y in zip(pts_df["longitude"], pts_df["latitude"])],
        crs="EPSG:4326"
    )

    print("Loading district boundaries from GeoJSON...")
    districts_gdf = gpd.read_file(geojson_path)
    districts_gdf = districts_gdf.dropna(subset=[DISTRICT_COL])

    # Resolve temperature (Celsius)
    if "t2m_celsius" in ds:
        t2m = ds["t2m_celsius"].values
    elif "t2m" in ds:
        t2m = ds["t2m"].values - 273.15
    else:
        raise ValueError("Temperature variable not found in dataset")

    # Resolve evapotranspiration in mm/month: pev * -1000 * days_in_month (D3, Plan Change G)
    n_times = len(times)
    et_name = "pev" if "pev" in ds else "pet" if "pet" in ds else None
    if et_name is None:
        raise ValueError("Evaporation variable missing: cannot fabricate zero ET")
    et_attrs = dict(ds[et_name].attrs)
    et = evaporation_monthly(ds[et_name].values, et_attrs, times)
    ds.close()
    # Use only usable cells on district land, excluding offshore cells in the
    # nearest fallback. Preserve original indices used to access the arrays.
    usable = np.isfinite(t2m).any(axis=0) & np.isfinite(et).any(axis=0)
    pts_gdf = pts_gdf[usable[pts_gdf["lat_idx"], pts_gdf["lon_idx"]]]
    on_land = gpd.sjoin(pts_gdf, districts_gdf[["geometry"]].to_crs(pts_gdf.crs), how="inner", predicate="within")
    pts_gdf = pts_gdf.loc[on_land.index.unique()]
    print("Performing spatial join using usable land cells...")
    joined = assign_districts_with_fallback(pts_gdf, districts_gdf)

    lat_indices = joined["lat_idx"].values
    lon_indices = joined["lon_idx"].values

    t2m_extracted = t2m[:, lat_indices, lon_indices]
    et_extracted = et[:, lat_indices, lon_indices]

    # Use unique (state, district) key
    joined["key"] = joined[STATE_COL].astype(str) + "___" + joined[DISTRICT_COL].astype(str)
    keys = joined["key"].values
    unique_keys, key_inverse = np.unique(keys, return_inverse=True)
    n_keys = len(unique_keys)

    district_t2m = np.zeros((n_times, n_keys))
    district_et = np.zeros((n_times, n_keys))

    print(f"Aggregating {n_keys} districts across {n_times} monthly timestamps...")
    for t in range(n_times):
        for extracted, output in ((t2m_extracted, district_t2m), (et_extracted, district_et)):
            valid = np.isfinite(extracted[t])
            counts = np.bincount(key_inverse[valid], minlength=n_keys)
            sums = np.bincount(key_inverse[valid], weights=extracted[t, valid], minlength=n_keys)
            output[t] = np.divide(sums, counts, out=np.full(n_keys, np.nan), where=counts > 0)

    # Reshape into DataFrame rows
    records = []
    for k_idx, key in enumerate(unique_keys):
        st_name, dist_name = key.split("___", 1)
        for t_idx, dt in enumerate(times):
            records.append({
                "district": dist_name,
                "st_nm": st_name,
                "year": dt.year,
                "month": dt.month,
                "temperature": round(float(district_t2m[t_idx, k_idx]), 2),
                "evapotranspiration": round(float(district_et[t_idx, k_idx]), 2),
            })

    out_df = pd.DataFrame(records)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    metadata = {
        "artifact_version": "weather-v3", "source": str(nc_path),
        "source_sha256": hashlib.sha256(nc_path.read_bytes()).hexdigest(),
        "geojson_sha256": hashlib.sha256(geojson_path.read_bytes()).hexdigest(),
        "csv_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "units": {"temperature": "degC", "evapotranspiration": "mm/month"},
        "source_evaporation_variable": et_name,
        "source_evaporation_units": str(et_attrs.get("units", "")),
        "source_evaporation_step_type": str(et_attrs.get("GRIB_stepType", "")),
        "et_conversion": "source_metadata_to_monthly_total_once", "spatial_fallback": "district_to_nearest_usable_land_cell",
        "nearest_district_count": int(joined[joined["spatial_method"] != "within"]["_dist_key"].nunique()),
        "date_start": str(times.min().date()), "date_end": str(times.max().date()),
    }
    out_path.with_suffix(".manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Successfully saved {len(out_df):,} district-monthly rows to {out_path}")
    return out_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate ERA5 district climate with verified monthly units")
    parser.add_argument("--nc")
    parser.add_argument("--geojson")
    parser.add_argument("--out")
    args = parser.parse_args()
    process_era5_to_districts(args.nc, args.geojson, args.out)
