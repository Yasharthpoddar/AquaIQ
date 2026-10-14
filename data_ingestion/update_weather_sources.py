"""Download incremental official weather sources into an isolated staging folder.

No client, authentication, HTTP request or filesystem write happens on import.
This command never changes production weather CSVs, features or the database.
"""

from __future__ import annotations

import argparse
import calendar
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IMD_ARCHIVE_PAGE = "https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html"
IMD_ARCHIVE_DOWNLOAD = "https://imdpune.gov.in/cmpg/Griddata/rainfall.php"
ERA5_DATASET = "reanalysis-era5-single-levels-monthly-means"
INDIA_AREA = [38, 68, 6, 98]
IMD_NY, IMD_NX = 129, 135


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _month(value: str) -> pd.Timestamp:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("Months must use YYYY-MM format")
    return pd.Timestamp(value + "-01")


def era5_requests(start: str, end: str, as_of: date | None = None) -> list[dict]:
    """Keep year-specific month lists so no Cartesian future months are requested."""
    first, last = _month(start), _month(end)
    today = pd.Timestamp(as_of or date.today()).normalize()
    if first > last:
        raise ValueError("Start month must precede end month")
    if last >= today.replace(day=1):
        raise ValueError("Only completed calendar months may be downloaded")
    if first < pd.Timestamp("1940-01-01"):
        raise ValueError("ERA5 monthly data starts in 1940")
    months = pd.date_range(first, last, freq="MS")
    requests = []
    for year in sorted(set(months.year)):
        requests.append({
            "product_type": ["monthly_averaged_reanalysis"],
            "variable": ["2m_temperature", "potential_evaporation"],
            "year": [str(year)],
            "month": [f"{month:02d}" for month in months[months.year == year].month],
            "time": ["00:00"], "area": INDIA_AREA.copy(),
            "data_format": "netcdf", "download_format": "unarchived",
        })
    return requests


def expected_imd_bytes(year: int) -> int:
    if not 1901 <= year < date.today().year:
        raise ValueError("Annual IMD downloads must cover a completed year from 1901 onward")
    return (366 if calendar.isleap(year) else 365) * IMD_NY * IMD_NX * 4


def validate_imd(path: Path, year: int) -> dict:
    expected = expected_imd_bytes(year)
    if path.stat().st_size != expected:
        raise ValueError(f"IMD {year} must contain exactly {expected} bytes")
    values = np.memmap(path, dtype="<f4", mode="r", shape=((366 if calendar.isleap(year) else 365), IMD_NY, IMD_NX))
    finite = np.isfinite(values)
    usable = finite & (values >= 0)
    if not finite.all() or not usable.any() or np.any(values[usable] > 10000):
        raise ValueError("IMD binary has non-finite, implausible or entirely missing rainfall")
    usable_per_day = usable.sum(axis=(1, 2))
    if np.any(usable_per_day == 0):
        raise ValueError("IMD annual file has a completely missing calendar day")
    result = {
        "year": year, "days": int(values.shape[0]), "grid": [IMD_NY, IMD_NX],
        "dtype": "little-endian float32", "size_bytes": expected,
        "units": "mm/day", "first_grid_point": [6.5, 66.5], "grid_step_degrees": 0.25,
        "negative_values_are_missing": True, "complete_day_records": True,
        "min_usable_grid_cells_per_day": int(usable_per_day.min()),
        "complete_cells_all_days": int(usable.all(axis=0).sum()),
        "maximum_daily_rainfall_mm": float(values[usable].max()),
        "sha256": sha256(path),
    }
    del values
    return result


def download_imd(year: int, out_dir: Path, *, session=None) -> dict:
    """Bound the public form download to the expected annual grid size."""
    import requests

    expected = expected_imd_bytes(year)
    target = out_dir / f"Rainfall_ind{year}_rfp25.grd"
    if target.exists():
        details = validate_imd(target, year)
        details["already_present"] = True
        return details
    out_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".grd.partial")
    client = session or requests.Session()
    try:
        with client.post(IMD_ARCHIVE_DOWNLOAD, data={"rain": str(year)},
                         stream=True, timeout=(30, 60)) as response:
            response.raise_for_status()
            if "html" in response.headers.get("Content-Type", "").lower():
                raise ValueError("IMD returned an HTML page instead of binary rainfall")
            size = 0
            with partial.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    if not block:
                        continue
                    size += len(block)
                    if size > expected:
                        raise ValueError("IMD response exceeds the expected annual binary size")
                    stream.write(block)
            details = validate_imd(partial, year)
            details.update({"download_url": response.url,
                            "response_content_type": response.headers.get("Content-Type"),
                            "response_content_disposition": response.headers.get("Content-Disposition")})
        partial.replace(target)
    finally:
        if partial.exists():
            partial.unlink()
        if session is None:
            client.close()
    details.update({"source": "IMD 0.25 degree annual gauge rainfall archive",
                    "source_page": IMD_ARCHIVE_PAGE, "request_method": "POST",
                    "request_form": {"rain": str(year)},
                    "retrieved_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                    "staging_only": True, "path": str(target)})
    target.with_suffix(".download.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    return details


def validate_era5(path: Path, request: dict) -> dict:
    """Verify source fields, units, grid and exact requested calendar coverage.

    Split-variable ZIP responses remain ZIPs: no member extraction is needed.
    Source attributes are recorded without inventing GRIB aggregation metadata.
    """
    import xarray as xr

    dates = {pd.Timestamp(f"{request['year'][0]}-{month}-01") for month in request["month"]}
    fields = {}

    def inspect(nc_source):
        engine = "store" if isinstance(nc_source, xr.backends.NetCDF4DataStore) else "netcdf4"
        with xr.open_dataset(nc_source, engine=engine) as dataset:
            time_name = "valid_time" if "valid_time" in dataset else "time"
            if time_name not in dataset or not {"latitude", "longitude"}.issubset(dataset.coords):
                raise ValueError("ERA5 response lacks expected time/latitude/longitude coordinates")
            actual = [pd.Timestamp(value) for value in dataset[time_name].values]
            if len(actual) != len(dates) or set(actual) != dates:
                raise ValueError("ERA5 response calendar coverage differs from the requested complete months")
            if not (np.isclose(dataset.latitude.max(), 38) and np.isclose(dataset.latitude.min(), 6)
                    and np.isclose(dataset.longitude.min(), 68) and np.isclose(dataset.longitude.max(), 98)):
                raise ValueError("ERA5 response does not cover the requested India bounding box")
            for name, units in (("t2m", "K"), ("pev", "m")):
                if name not in dataset:
                    continue
                if name in fields:
                    raise ValueError(f"Duplicate ERA5 variable {name}")
                if dataset[name].attrs.get("units") != units:
                    raise ValueError(f"Unexpected ERA5 {name} units")
                values = dataset[name].values
                if not np.isfinite(values).any():
                    raise ValueError(f"ERA5 {name} is entirely missing")
                fields[name] = {
                    "units": units, "dimensions": list(dataset[name].dims),
                    "GRIB_stepType": dataset[name].attrs.get("GRIB_stepType"),
                    "GRIB_stream": dataset[name].attrs.get("GRIB_stream"),
                    "min": float(np.nanmin(values)), "max": float(np.nanmax(values)),
                }

    if zipfile.is_zipfile(path):
        import netCDF4

        with zipfile.ZipFile(path) as archive:
            members = [member for member in archive.infolist() if member.filename.endswith(".nc")]
            if not members or sum(member.file_size for member in members) > 128 * 1024 * 1024:
                raise ValueError("ERA5 ZIP has missing or unexpectedly large NetCDF contents")
            for index, member in enumerate(members):
                # Open the bounded NC member in memory; never extract archive paths.
                nc_handle = netCDF4.Dataset(f"field-{index}.nc", memory=archive.read(member))
                inspect(xr.backends.NetCDF4DataStore(nc_handle))
    else:
        inspect(path)
    if set(fields) != {"t2m", "pev"}:
        raise ValueError("ERA5 response must contain both 2m temperature and potential evaporation")
    return {"variables": fields, "date_start": str(min(dates).date()),
            "date_end": str(max(dates).date()), "months": len(dates),
            "source_accumulation_basis": "monthly_averaged_reanalysis_daily_effective_accumulation",
            "conversion_required": {"temperature": "t2m_K - 273.15",
                                    "evapotranspiration": "max(0, -pev_m * 1000 * days_in_month)"},
            "sha256": sha256(path)}


def download_era5(requests: list[dict], out_dir: Path) -> list[dict]:
    import cdsapi

    client = cdsapi.Client()  # Reads existing user-managed credentials only here.
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for request in requests:
        year = request["year"][0]
        stem = f"era5_temp_pev_india_{year}_{request['month'][0]}_{request['month'][-1]}"
        partial = out_dir / f"{stem}.partial"
        if any((out_dir / f"{stem}{suffix}").exists() for suffix in (".nc", ".zip")):
            raise FileExistsError(f"Staged ERA5 artifact already exists: {stem}; verify it before reuse")
        try:
            client.retrieve(ERA5_DATASET, request, str(partial))
            details = validate_era5(partial, request)
            target = out_dir / f"{stem}{'.zip' if zipfile.is_zipfile(partial) else '.nc'}"
            partial.replace(target)
        finally:
            if partial.exists():
                partial.unlink()
        details.update({"dataset": ERA5_DATASET, "request": request,
                        "retrieved_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                        "path": str(target), "staging_only": True,
                        "recent_months_may_be_preliminary_ERA5T": True})
        target.with_suffix(".download.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
        results.append(details)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="source", required=True)
    imd = subparsers.add_parser("imd", help="Stage a complete annual IMD binary")
    imd.add_argument("--year", type=int, required=True)
    era5 = subparsers.add_parser("era5", help="Stage complete monthly ERA5 temperature and potential evaporation")
    era5.add_argument("--start", required=True, help="YYYY-MM")
    era5.add_argument("--end", required=True, help="YYYY-MM; completed months only")
    for command in (imd, era5):
        command.add_argument("--out-dir", type=Path, required=True)
        command.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.source == "imd":
        plan = {"url": IMD_ARCHIVE_DOWNLOAD, "method": "POST", "form": {"rain": str(args.year)},
                "expected_bytes": expected_imd_bytes(args.year), "out_dir": str(args.out_dir)}
        result = plan if args.dry_run else download_imd(args.year, args.out_dir)
    else:
        requests = era5_requests(args.start, args.end)
        plan = {"dataset": ERA5_DATASET, "requests": requests, "out_dir": str(args.out_dir)}
        result = plan if args.dry_run else download_era5(requests, args.out_dir)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
