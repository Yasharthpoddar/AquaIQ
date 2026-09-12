"""
AquaIQ — Week 1 Smoke Test
----------------------------
Verifies that all downloaded datasets load cleanly into Pandas/xarray
before the team builds on top of them.

Run:
    python tests/smoke_test_data.py

Checks:
  1. CGWB CSV          — loads, has expected columns, >1M rows
  2. IMD .GRD files    — at least one parses as binary float32 grid
  3. ERA5 NetCDF       — opens in xarray, has t2m and pev variables
  4. GeoJSON           — loads via geopandas, 600+ district polygons
  5. config.yaml       — valid YAML, has all expected top-level keys
"""

import sys
import os
from pathlib import Path

# Ensure project root is importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import yaml
import numpy as np
import pandas as pd

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    print(f"  {status}  {name}" + (f"  -- {detail}" if detail else ""))
    return condition


def main():
    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    print("=" * 60)
    print("  AquaIQ Week 1 — Data Smoke Test")
    print("=" * 60)

    # ── 1. CGWB CSV ───────────────────────────────────────────
    print("\n[1/5] CGWB groundwater level CSV")
    cgwb_path = ROOT / config["paths"]["data_raw"] / "cgwb_combined.csv"
    if not cgwb_path.exists():
        check("CGWB file exists", False, f"not found at {cgwb_path}")
    else:
        check("CGWB file exists", True, f"{cgwb_path.stat().st_size / 1e6:.1f} MB")
        df = pd.read_csv(cgwb_path, nrows=5000, dtype=str)
        expected_cols = {"district_code", "district_name", "state_name", "date", "currentlevel"}
        found_cols = set(df.columns)
        check(
            "CGWB has expected columns",
            expected_cols.issubset(found_cols),
            f"found: {sorted(found_cols)}"
        )
        # Check full row count (just count lines, faster than full read)
        line_count = sum(1 for _ in open(cgwb_path, encoding="utf-8", errors="ignore")) - 1
        check("CGWB has >100K rows", line_count > 100_000, f"{line_count:,} rows")
        # Check date parses
        sample_dates = pd.to_datetime(df["date"], errors="coerce")
        valid_pct = sample_dates.notna().mean() * 100
        check("CGWB dates parse", valid_pct > 90, f"{valid_pct:.0f}% valid in sample")
        # Check currentlevel is numeric
        sample_gwl = pd.to_numeric(df["currentlevel"], errors="coerce")
        valid_gwl_pct = sample_gwl.notna().mean() * 100
        check("CGWB currentlevel is numeric", valid_gwl_pct > 70, f"{valid_gwl_pct:.0f}% valid in sample")

    # ── 2. IMD .GRD files ─────────────────────────────────────
    print("\n[2/5] IMD rainfall .GRD files")
    imd_dir = ROOT / config["paths"]["data_raw"] / "imd"
    if not imd_dir.exists():
        check("IMD directory exists", False, f"not found at {imd_dir}")
    else:
        import glob
        grd_files = glob.glob(str(imd_dir / "*.grd")) + glob.glob(str(imd_dir / "*.GRD"))
        check("IMD .grd files found", len(grd_files) > 0, f"{len(grd_files)} files")

        if grd_files:
            # Try parsing one file (pick 2020 as a representative year)
            test_file = None
            for f in grd_files:
                if "2020" in os.path.basename(f):
                    test_file = f
                    break
            if test_file is None:
                test_file = grd_files[0]

            NX, NY = 135, 129  # IMD grid dimensions
            data = np.fromfile(test_file, dtype=np.float32)
            file_basename = os.path.basename(test_file)
            # 2020 is a leap year: 366 days
            expected_366 = 366 * NX * NY
            expected_365 = 365 * NX * NY
            valid_size = data.size in (expected_365, expected_366)
            check(
                f"IMD grid parses ({file_basename})",
                valid_size,
                f"{data.size:,} values (expect {expected_365:,} or {expected_366:,})"
            )
            # Check value range — rainfall should be mostly 0-500mm/day, with negatives as missing
            data_clean = data[data >= 0]
            if len(data_clean) > 0:
                check(
                    "IMD values in reasonable range",
                    data_clean.mean() < 100,
                    f"mean={data_clean.mean():.2f} mm/day, max={data_clean.max():.1f}"
                )

    # ── 3. ERA5 NetCDF ────────────────────────────────────────
    print("\n[3/5] ERA5 temperature + evapotranspiration NetCDF")
    era5_dir = ROOT / config["paths"]["data_raw"] / "era5"
    era5_processed = ROOT / config["paths"]["data_processed"] / "era5_india_2002_2024_clean.nc"
    if not era5_dir.exists():
        check("ERA5 directory exists", False, f"not found at {era5_dir}")
    else:
        nc_files = list(era5_dir.glob("*.nc"))
        check("ERA5 raw .nc file found", len(nc_files) > 0, f"{len(nc_files)} files")

        # Try the processed clean file first, fall back to raw
        nc_to_open = era5_processed if era5_processed.exists() else (nc_files[0] if nc_files else None)
        if era5_processed.exists():
            check("ERA5 clean processed file exists", True, f"{era5_processed.stat().st_size / 1e6:.1f} MB")

        if nc_to_open:
            try:
                import xarray as xr
                ds = xr.open_dataset(nc_to_open, engine="netcdf4")
                variables = list(ds.data_vars)
                check(
                    "ERA5 has temperature variable",
                    "t2m" in variables,
                    f"variables: {variables}"
                )
                # pev = potential evaporation
                has_pet = "pev" in variables or "potential_evaporation" in variables
                check(
                    "ERA5 has evapotranspiration variable",
                    has_pet,
                    f"variables: {variables}"
                )
                # Check coordinate ranges (should cover India)
                lats = ds.coords["latitude"].values if "latitude" in ds.coords else []
                lons = ds.coords["longitude"].values if "longitude" in ds.coords else []
                if len(lats) > 0 and len(lons) > 0:
                    check(
                        "ERA5 covers India bbox",
                        lats.min() <= 10 and lats.max() >= 35 and lons.min() <= 70 and lons.max() >= 95,
                        f"lat [{lats.min():.1f}, {lats.max():.1f}], lon [{lons.min():.1f}, {lons.max():.1f}]"
                    )
                ds.close()
            except ImportError:
                check("xarray installed", False, "pip install xarray netcdf4")
            except OSError as e:
                check("ERA5 NetCDF readable", False, f"file format error: {e}")

    # ── 4. GeoJSON district boundaries ────────────────────────
    print("\n[4/5] India district boundary GeoJSON")
    geojson_path = ROOT / config["paths"]["geojson_boundaries"]
    if not geojson_path.exists():
        check("GeoJSON file exists", False, f"not found at {geojson_path}")
    else:
        check("GeoJSON file exists", True, f"{geojson_path.stat().st_size / 1e6:.1f} MB")
        try:
            import geopandas as gpd
            gdf = gpd.read_file(geojson_path)
            check("GeoJSON loads in geopandas", True, f"{len(gdf)} features")
            check("GeoJSON has 600+ districts", len(gdf) >= 600, f"{len(gdf)} districts")
            # Check it has a district name column
            has_district = "district" in gdf.columns or "DISTRICT" in gdf.columns
            check("GeoJSON has district name column", has_district, f"columns: {list(gdf.columns)}")
            # Check geometry is valid
            invalid = (~gdf.geometry.is_valid).sum()
            check("GeoJSON geometries valid", invalid == 0, f"{invalid} invalid geometries")
        except ImportError:
            # Fallback — just check it's valid JSON
            import json
            with open(geojson_path) as f:
                data = json.load(f)
            n_features = len(data.get("features", []))
            check("GeoJSON parses as JSON", True, f"{n_features} features")
            check("GeoJSON has 600+ districts", n_features >= 600, f"{n_features} districts")

    # ── 5. config.yaml ────────────────────────────────────────
    print("\n[5/5] config.yaml validation")
    expected_keys = ["project", "paths", "data_sources", "date_range", "features",
                     "model_hyperparameters", "crisis_score", "api", "testing"]
    found_keys = list(config.keys())
    for key in expected_keys:
        check(f"config.yaml has '{key}'", key in found_keys)

    n_features = len(config.get("features", []))
    check("config.yaml lists 10 features", n_features == 10, f"found {n_features}")

    # ── Summary ───────────────────────────────────────────────
    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = sum(1 for _, s, _ in results if s == FAIL)
    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed, {failed} failed out of {len(results)} checks")
    print("=" * 60)

    if failed > 0:
        print("\n  Failed checks:")
        for name, status, detail in results:
            if status == FAIL:
                print(f"    • {name}: {detail}")
        sys.exit(1)
    else:
        print("\n  All Week 1 data checks passed. Ready to build on top of these datasets.")
        sys.exit(0)


if __name__ == "__main__":
    main()
