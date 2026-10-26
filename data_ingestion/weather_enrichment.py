"""Bounded, explicit acquisition of official IMD comparison products.

This offline CLI keeps new source files immutable and separate from the active
weather/features. A download is not authorization to substitute a predictor.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = {
    "rainfall_netcdf": {
        "page": "https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html",
        "url": "https://www.imdpune.gov.in/cmpg/Griddata/RF25.php",
        "form_field": "RF25", "max_bytes": 40 * 1024 * 1024,
        "suffix": ".nc", "units": "mm/day", "resolution_degrees": 0.25,
        "first_year": 1901,
        "citation": "Pai et al. (2014), MAUSAM 65(1), 1-18",
    },
    "temperature_max": {
        "page": "https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html",
        "url": "https://www.imdpune.gov.in/cmpg/Griddata/maxtemp.php",
        "form_field": "maxtemp", "max_bytes": 2 * 1024 * 1024,
        "suffix": ".grd", "units": "degC daily maximum", "resolution_degrees": 1.0,
        "first_year": 1951,
        "citation": "Srivastava, Rajeevan and Kshirsagar (2009), DOI:10.1002/asl.232",
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def publish_new_file(source, target):
    """Publish a complete same-directory file atomically without replacing any path.

    Windows rename fails when the target already exists and works inside the
    restricted workspace, where hard-link creation may be unavailable. POSIX
    rename replaces targets, so use an exclusive hard link there instead.
    """
    source, target = Path(source), Path(target)
    if os.name == "nt":
        source.rename(target)
    else:
        target.hardlink_to(source)


def validate_product(path, product, year):
    """Check the provider's calendar, grid and physical units before accepting."""
    path = Path(path)
    days = 366 if calendar.isleap(year) else 365
    if product == "temperature_max":
        expected = days * 31 * 31 * 4
        if path.stat().st_size != expected:
            raise ValueError("IMD temperature byte count differs from documented 31x31 calendar grid")
        values = np.fromfile(path, dtype="<f4").reshape(days, 31, 31)
        missing = np.isclose(values, 99.9, atol=1e-5)
        valid = ~missing & np.isfinite(values) & (values >= -90) & (values <= 65)
        if not (valid | missing).all() or not valid.any() or not valid.any(axis=(1, 2)).all():
            raise ValueError("IMD temperature contains invalid values or completely missing days")
        return {"days": days, "grid": [31, 31], "dtype": "little-endian float32",
                "units": "degC daily maximum", "missing_sentinel": 99.9,
                "valid_grid_day_values": int(valid.sum()), "missing_grid_day_values": int(missing.sum()),
                "minimum_degC": float(values[valid].min()), "maximum_degC": float(values[valid].max()),
                "first_grid_point_lat_lon": [7.5, 67.5], "last_grid_point_lat_lon": [37.5, 97.5]}
    if product != "rainfall_netcdf":
        raise ValueError("Unknown IMD comparison product")
    import xarray as xr

    with xr.open_dataset(path, engine="netcdf4") as dataset:
        if set(dataset.data_vars) != {"RAINFALL"} or not {"TIME", "LATITUDE", "LONGITUDE"}.issubset(dataset.coords):
            raise ValueError("Unrecognized IMD rainfall NetCDF schema")
        if dataset.RAINFALL.dims != ("TIME", "LATITUDE", "LONGITUDE"):
            raise ValueError("Unexpected IMD rainfall dimension order")
        if dataset.RAINFALL.attrs.get("units", "").upper() != "MM":
            raise ValueError("Unverified IMD rainfall units")
        times = pd.DatetimeIndex(dataset.TIME.values)
        expected_times = pd.date_range(f"{year}-01-01", periods=days)
        if not times.equals(expected_times):
            raise ValueError("IMD rainfall time axis differs from requested complete calendar year")
        if not (np.array_equal(dataset.LATITUDE.values, np.arange(129) * .25 + 6.5)
                and np.array_equal(dataset.LONGITUDE.values, np.arange(135) * .25 + 66.5)):
            raise ValueError("IMD rainfall grid differs from documented 0.25 degree grid")
        values = dataset.RAINFALL.values
        valid = np.isfinite(values) & (values >= 0) & (values <= 10000)
        if np.any(np.isfinite(values) & ~valid) or not valid.any(axis=(1, 2)).all():
            raise ValueError("Invalid IMD rainfall values or completely missing day")
        return {"days": days, "grid": [129, 135], "units": "mm/day", "variable": "RAINFALL",
                "valid_grid_day_values": int(valid.sum()), "missing_grid_day_values": int((~valid).sum()),
                "maximum_daily_rainfall_mm": float(values[valid].max()),
                "last_observation_date": str(times[-1].date())}


def download_product(product, year, out_dir, *, session=None, as_of=None, attempts=2):
    """Acquire an inspected official form product with a bounded retry budget.

    Output directories are explicit, source files are never overwritten, and no
    credentials are requested. Existing complete verified pairs can be reused.
    """
    import requests

    if product not in PRODUCTS or not isinstance(year, int) or isinstance(year, bool):
        raise ValueError("Unknown product or invalid year")
    if not PRODUCTS[product]["first_year"] <= year < (as_of or date.today()).year:
        raise ValueError("Download only a complete historical calendar year")
    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 3:
        raise ValueError("Attempts must be between 1 and 3")
    out_dir = Path(out_dir).resolve()
    if not out_dir.is_relative_to((ROOT / "data/raw/official_enrichment").resolve()):
        raise ValueError("Comparison products must be staged under data/raw/official_enrichment")
    spec = PRODUCTS[product]
    target = out_dir / f"imd_{product}_{year}{spec['suffix']}"
    sidecar = target.with_suffix(target.suffix + ".download.json")
    if target.exists() or sidecar.exists():
        if not target.is_file() or not sidecar.is_file():
            raise ValueError("Existing source/manifest pair is incomplete; choose a new directory")
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        if (metadata.get("generator") != "weather_enrichment-v1" or metadata.get("sha256") != sha256(target)
                or metadata.get("product") != product or metadata.get("year") != year):
            raise ValueError("Existing source has unrelated or changed provenance")
        validate_product(target, product, year)
        return {**metadata, "already_present": True}
    out_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    try:
        for attempt in range(1, attempts + 1):
            partial = None
            try:
                with client.post(spec["url"], data={spec["form_field"]: str(year)},
                                 stream=True, timeout=(15, 30), allow_redirects=False) as response:
                    if response.status_code != 200 or response.url != spec["url"]:
                        raise ValueError(f"Unexpected IMD download response: HTTP {response.status_code}")
                    if "html" in response.headers.get("Content-Type", "").lower():
                        raise ValueError("IMD returned HTML instead of the requested data product")
                    size = 0
                    with tempfile.NamedTemporaryFile(dir=out_dir, suffix=".partial", delete=False) as stream:
                        partial = Path(stream.name)
                        for block in response.iter_content(256 * 1024):
                            if not block:
                                continue
                            size += len(block)
                            if size > spec["max_bytes"]:
                                raise ValueError("IMD response exceeds the bounded product size")
                            stream.write(block)
                    details = validate_product(partial, product, year)
                    metadata = {"generator": "weather_enrichment-v1", "product": product, "year": year,
                                "publisher": "India Meteorological Department", "source_page": spec["page"],
                                "resource_url": spec["url"], "request_method": "POST",
                                "request_form": {spec["form_field"]: str(year)},
                                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                                "sha256": sha256(partial), "size_bytes": size, "attempts": attempt,
                                "content_type": response.headers.get("Content-Type"),
                                "content_disposition": response.headers.get("Content-Disposition"),
                                "citation": spec["citation"], "license": "No explicit open redistribution license found on product page; attribution requested",
                                "candidate_only": True, "path": str(target.relative_to(ROOT)), **details}
                    publish_new_file(partial, target)
                    with sidecar.open("x", encoding="utf-8") as stream:
                        json.dump(metadata, stream, indent=2)
                        stream.write("\n")
                    return metadata
            except requests.RequestException:
                if attempt == attempts:
                    raise
            finally:
                if partial is not None:
                    partial.unlink(missing_ok=True)
    finally:
        if session is None:
            client.close()


def compare_rainfall_netcdf_binary(netcdf, binary, year):
    """Identify mirrored observations by complete calendar/grid/value equality."""
    import xarray as xr
    from data_ingestion.update_weather_sources import validate_imd

    validate_product(netcdf, "rainfall_netcdf", year)
    validate_imd(Path(binary), year)
    days = 366 if calendar.isleap(year) else 365
    binary_values = np.fromfile(binary, dtype="<f4").reshape(days, 129, 135)
    with xr.open_dataset(netcdf, engine="netcdf4") as dataset:
        netcdf_values = dataset.RAINFALL.values
        valid_binary = binary_values >= 0
        valid_netcdf = np.isfinite(netcdf_values)
        shared = valid_binary & valid_netcdf
        differences = np.abs(binary_values[shared] - netcdf_values[shared])
        result = {"year": year, "binary_sha256": sha256(binary), "netcdf_sha256": sha256(netcdf),
                  "valid_grid_day_values_binary": int(valid_binary.sum()),
                  "valid_grid_day_values_netcdf": int(valid_netcdf.sum()),
                  "mask_differences": int((valid_binary != valid_netcdf).sum()),
                  "identical_shared_values": int((differences == 0).sum()),
                  "differing_shared_values": int((differences != 0).sum()),
                  "maximum_absolute_difference_mm": float(differences.max()) if len(differences) else None,
                  "new_valid_grid_day_values": int((valid_netcdf & ~valid_binary).sum()),
                  "same_product_observations": bool(np.array_equal(valid_binary, valid_netcdf)
                                                    and np.array_equal(binary_values[shared], netcdf_values[shared]))}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", choices=PRODUCTS)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--compare-binary", type=Path,
                        help="Compare the staged rainfall NetCDF against this existing immutable annual binary")
    parser.add_argument("--report", type=Path, help="Explicit new comparison JSON; no source data are changed")
    args = parser.parse_args(argv)
    if args.compare_binary:
        if args.product or not args.report:
            parser.error("--compare-binary requires --report and cannot accompany --product")
        source = args.out_dir / f"imd_rainfall_netcdf_{args.year}.nc"
        report = compare_rainfall_netcdf_binary(source, args.compare_binary, args.year)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        print(json.dumps(report, indent=2))
    elif args.product and not args.report:
        print(json.dumps(download_product(args.product, args.year, args.out_dir), indent=2))
    else:
        parser.error("Choose --product, or --compare-binary with --report")


if __name__ == "__main__":
    main()
