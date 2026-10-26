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

import argparse
import hashlib
import json
import sys
import tempfile
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
from data_ingestion.weather_enrichment import publish_new_file
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


def _validate_era5_dataset(dataset):
    """Require complete, aligned source fields; do not infer aggregation units."""
    time_name = "valid_time" if "valid_time" in dataset.coords else "time"
    required = {time_name, "latitude", "longitude"}
    if not required.issubset(dataset.coords) or not {"t2m", "pev"}.issubset(dataset.data_vars):
        raise ValueError("ERA5 must contain both t2m and pev with time/latitude/longitude coordinates")
    times = pd.DatetimeIndex(dataset[time_name].values)
    if (times.empty or times.has_duplicates or not times.is_monotonic_increasing
            or not times.equals(pd.date_range(times[0], periods=len(times), freq="MS"))):
        raise ValueError("ERA5 source must contain unique consecutive calendar-month timestamps")
    for name in ("latitude", "longitude"):
        values = np.asarray(dataset[name].values)
        if (values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all()
                or len(np.unique(values)) != len(values)):
            raise ValueError("ERA5 has invalid spatial coordinates")
    for name in ("t2m", "pev"):
        if dataset[name].dims != (time_name, "latitude", "longitude"):
            raise ValueError(f"ERA5 {name} has incompatible dimensions")
        values = np.asarray(dataset[name].values)
        if np.isinf(values).any() or not np.isfinite(values).any(axis=(1, 2)).all():
            raise ValueError(f"ERA5 {name} has infinite values or completely missing months")
    if dataset.t2m.attrs.get("units") != "K":
        raise ValueError("ERA5 t2m source units must be Kelvin")
    # This routine validates the documented evaporation conversion once. It
    # never applies the conversion to the stored raw daily-average source field.
    evaporation_monthly(dataset.pev.values, dict(dataset.pev.attrs), times)
    return time_name


def _canonical_month_axis(dataset):
    """Map inspected monthly timestamp labels to month starts, without shifting months.

    The CDS moda avgad evaporation member labels monthly means at 06:00 on
    day one, whereas the avgua temperature member labels them at 00:00. This
    is a source representation difference, not an extra six hours of rainfall
    or a daily observation. Other sub-month timestamp conventions fail closed.
    """
    time_name = "valid_time" if "valid_time" in dataset.coords else "time"
    if time_name not in dataset.coords:
        raise ValueError("ERA5 source member has no monthly time coordinate")
    times = pd.DatetimeIndex(dataset[time_name].values)
    if (times.empty or times.has_duplicates or not times.is_monotonic_increasing
            or (times.day != 1).any() or (times.minute != 0).any()
            or (times.second != 0).any() or (times.microsecond != 0).any()
            or (times.nanosecond != 0).any()):
        raise ValueError("ERA5 source member has an unverified monthly timestamp convention")
    hours = set(times.hour)
    if hours != {0}:
        if not (hours == {6} and set(dataset.data_vars) == {"pev"}
                and dataset.pev.attrs.get("GRIB_stepType") == "avgad"
                and dataset.pev.attrs.get("units") == "m"):
            raise ValueError("Unverified sub-day label for an ERA5 monthly field")
    metadata = {"time_name": time_name, "original_first": str(times[0]),
                "original_last": str(times[-1]), "source_hour_utc": next(iter(hours)),
                "mapping": "same_calendar_month_start; inspected CDS moda monthly product"}
    return dataset.assign_coords({time_name: times.to_period("M").to_timestamp()}), metadata


def prepare_era5_nc(source, output, *, max_uncompressed_bytes=128 * 1024 * 1024):
    """Merge split CDS ZIP responses without extracting archive paths.

    The immutable download may be a ZIP despite its .nc extension. Read only
    bounded NetCDF members in memory, demand identical spatial/calendar axes
    and reject duplicate variables. The inspected monthly 00/06 UTC labels
    map to the same calendar month. Existing files are never overwritten.
    """
    import netCDF4

    source, output = Path(source).resolve(), Path(output).resolve()
    sidecar = output.with_suffix(".prepare.json")
    if source == output or output.exists() or sidecar.exists():
        raise FileExistsError("Choose a new ERA5 output path; source and existing artifacts are immutable")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    loaded, member_metadata = [], []
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if (not members or len(members) > 8 or any(member.is_dir() for member in members)
                    or sum(member.file_size for member in members) > max_uncompressed_bytes
                    or len({member.filename for member in members}) != len(members)):
                raise ValueError("ERA5 archive is empty, duplicated or exceeds bounded member/size limits")
            for index, member in enumerate(members):
                # No archive path is ever written, including unexpected members.
                if (Path(member.filename).name != member.filename or "\\" in member.filename
                        or not member.filename.lower().endswith(".nc") or member.flag_bits & 1):
                    raise ValueError("ERA5 archive contains an unverified member path/type")
                payload = archive.read(member)
                handle = netCDF4.Dataset(f"era5-member-{index}.nc", memory=payload)
                try:
                    with xr.open_dataset(xr.backends.NetCDF4DataStore(handle)) as dataset:
                        loaded.append(dataset.load())
                finally:
                    # Xarray owns and normally closes the NetCDF4 handle.
                    if handle.isopen():
                        handle.close()
                member_metadata.append({"name": member.filename, "size_bytes": member.file_size,
                                        "sha256": hashlib.sha256(payload).hexdigest()})
    else:
        if source.stat().st_size > max_uncompressed_bytes:
            raise ValueError("ERA5 source exceeds bounded NetCDF size")
        with xr.open_dataset(source, engine="netcdf4") as dataset:
            loaded.append(dataset.load())
    variable_names = [name for dataset in loaded for name in dataset.data_vars]
    if len(variable_names) != len(set(variable_names)):
        raise ValueError("Duplicate ERA5 variables across archive members")
    normalized, time_mappings = [], []
    for dataset in loaded:
        normalized_dataset, mapping = _canonical_month_axis(dataset)
        normalized.append(normalized_dataset)
        time_mappings.append(mapping)
    try:
        merged = xr.merge(normalized, join="exact", compat="equals", combine_attrs="override")
    except (ValueError, TypeError) as error:
        raise ValueError("ERA5 archive members have conflicting coordinate axes") from error
    time_name = _validate_era5_dataset(merged)
    converted = merged.t2m - np.float32(273.15)
    if "t2m_celsius" in merged:
        if not np.array_equal(merged.t2m_celsius.values, converted.values, equal_nan=True):
            raise ValueError("Existing Celsius field disagrees with the Kelvin source")
    else:
        merged["t2m_celsius"] = converted
    merged.t2m_celsius.attrs.update(units="degC", conversion="t2m_K - 273.15")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".nc.partial", delete=False) as stream:
            temporary = Path(stream.name)
        merged.to_netcdf(temporary, engine="netcdf4")
        with xr.open_dataset(temporary, engine="netcdf4") as checked:
            _validate_era5_dataset(checked)
        if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
            raise ValueError("ERA5 source changed during preparation")
        metadata = {"generator": "era5-split-zip-v1", "source_sha256": source_hash,
                    "source_file": source.name, "source_size_bytes": source.stat().st_size,
                    "members": member_metadata, "csv_or_netcdf_sha256": hashlib.sha256(temporary.read_bytes()).hexdigest(),
                    "monthly_timestamp_mappings": time_mappings,
                    "variables": sorted(merged.data_vars), "months": merged.sizes[time_name],
                    "date_start": str(pd.Timestamp(merged[time_name].values[0]).date()),
                    "date_end": str(pd.Timestamp(merged[time_name].values[-1]).date()),
                    "raw_source_modified": False, "evaporation_source_units_preserved": True}
        # Atomic no-clobber publication also protects a file created after the
        # initial path check. No downloaded/derived artifact is replaced.
        publish_new_file(temporary, output)
        with sidecar.open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)
            stream.write("\n")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        merged.close()
        for dataset in loaded:
            dataset.close()
    return str(output)


def find_or_extract_nc():
    """Locate a complete dataset, safely merging the one raw CDS source if needed."""
    if CLEAN_NC_PATH.exists():
        # An unrelated or incomplete existing artifact must not be overwritten.
        with xr.open_dataset(CLEAN_NC_PATH, engine="netcdf4") as dataset:
            _validate_era5_dataset(dataset)
        return str(CLEAN_NC_PATH)
    candidates = sorted(path for path in ERA5_DIR.glob("*") if path.suffix.lower() in {".nc", ".zip"})
    if len(candidates) != 1:
        raise ValueError("Select one immutable ERA5 source explicitly; none or multiple raw sources were found")
    return prepare_era5_nc(candidates[0], CLEAN_NC_PATH)


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
    parser.add_argument("--prepare-source", type=Path, help="Prepare one immutable CDS NetCDF/ZIP without district aggregation")
    parser.add_argument("--prepared-out", type=Path, help="Explicit new clean NetCDF path for --prepare-source")
    args = parser.parse_args()
    if args.prepare_source:
        if not args.prepared_out or any((args.nc, args.geojson, args.out)):
            parser.error("--prepare-source requires --prepared-out and cannot accompany aggregation options")
        print(prepare_era5_nc(args.prepare_source, args.prepared_out))
    elif args.prepared_out:
        parser.error("--prepared-out requires --prepare-source")
    else:
        process_era5_to_districts(args.nc, args.geojson, args.out)
