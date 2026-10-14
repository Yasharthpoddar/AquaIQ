"""Export complete staged IMD real-time months into offline candidate artifacts.

A revalidated sampled overlap report is required before export. The rainfall
remains provisional: sampled agreement does not establish all dates or model
accuracy. Outputs are restricted to candidate/update folders; this module never
downloads, ingests, replaces production files, or trains models.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from data_ingestion.imd_district_climatology import (
    DISTRICT_COL, STATE_COL, assign_district, _sha256,
)
from data_ingestion.imd_realtime import (
    _atomic_json, completed_month_dates, complete_month_grid, monthly_grid_points,
)
from data_ingestion.imd_realtime_comparison import validate_verified_overlap_report

ROOT = Path(__file__).resolve().parents[1]


def configured_geojson_path() -> Path:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return ROOT / config["paths"]["geojson_boundaries"]


def _output_paths(output, normals_output, protected):
    csv_paths = [Path(output).resolve(), Path(normals_output).resolve()]
    if any(path.suffix.lower() != ".csv" for path in csv_paths):
        raise ValueError("Candidate rainfall and normals outputs must use .csv filenames")
    paths = csv_paths + [path.with_suffix(".manifest.json") for path in csv_paths]
    if len(paths) != len(set(paths)):
        raise ValueError("Candidate CSV and manifest output paths must be distinct")
    roots = [(ROOT / "reports/candidates").resolve(), (ROOT / "data/raw/updates").resolve()]
    roots = [root for root in roots if root.is_relative_to(ROOT.resolve())]
    protected = {Path(path).resolve() for path in protected}
    for path in paths:
        if not any(path.is_relative_to(root) for root in roots):
            raise ValueError("Outputs must remain under reports/candidates or data/raw/updates")
        if path in protected:
            raise ValueError("Candidate outputs cannot overwrite source inputs or provenance")
    # A staging directory also contains downloaded inputs and older merged
    # artifacts. Its location does not establish ownership of existing files.
    for path in csv_paths:
        manifest_path = path.with_suffix(".manifest.json")
        if not path.exists() and not manifest_path.exists():
            continue
        if not path.is_file() or not manifest_path.is_file():
            raise ValueError("Existing outputs require a complete own-generator candidate CSV/manifest pair; choose new output paths")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise ValueError("Existing candidate manifest is unreadable; choose new output paths") from error
        if (not isinstance(manifest, dict) or manifest.get("generator") != "imd_realtime_monthly"
                or manifest.get("artifact_version") != "weather-v3"
                or manifest.get("candidate_only") is not True
                or manifest.get("product_status") != "provisional_real_time"
                or manifest.get("csv_sha256") != _sha256(path)):
            raise ValueError("Existing outputs are unrelated or tampered candidate artifacts; choose new output paths")
    return csv_paths


def _atomic_csv(path, frame):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, prefix=path.name + ".",
                                         suffix=".partial", delete=False) as stream:
            temporary = Path(stream.name)
            frame.to_csv(stream, index=False)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def export_monthly(start, end, staged_dir, overlap_report, output, normals_output,
                   geojson=None, *, as_of: date | None = None):
    """Validate the complete requested range before writing any candidate output."""
    days = completed_month_dates(start, end, as_of)
    staged_dir, overlap_report = Path(staged_dir).resolve(), Path(overlap_report).resolve()
    canonical = configured_geojson_path().resolve()
    geojson = Path(geojson).resolve() if geojson is not None else canonical
    protected = [overlap_report, geojson, canonical]
    for day in days:
        stem = staged_dir / ("rain_" + day.strftime("%d%m%Y"))
        protected.extend([stem.with_suffix(".bin"), stem.with_suffix(".download.json")])
    output, normals_output = _output_paths(output, normals_output, protected)

    # This gate rechecks annual/daily source hashes and reruns sampled agreement.
    overlap = validate_verified_overlap_report(overlap_report, as_of=as_of)
    if overlap.get("sampled_overlap_ready") is not True:
        raise ValueError("A revalidated sampled overlap report is required")
    report_hash = _sha256(overlap_report)
    if report_hash != overlap["report_sha256"]:
        raise ValueError("Overlap report changed during verification")
    report = json.loads(overlap_report.read_text(encoding="utf-8-sig"))
    annual = report["annual_source"]
    protected.extend([annual["path"], annual["sidecar_path"]])
    for item in report["comparisons"]:
        protected.extend([item["realtime_path"], item["realtime_sidecar_path"]])
    _output_paths(output, normals_output, protected)

    boundary_hash = _sha256(geojson)
    canonical_hash = _sha256(canonical)
    if boundary_hash != canonical_hash:
        raise ValueError("Candidate rainfall requires the configured canonical boundary provenance")
    periods = sorted({(day.year, day.month) for day in days})
    grids, sources = [], []
    for year, month in periods:
        grid, monthly_sources = complete_month_grid(staged_dir, year, month, as_of)
        expected = [day for day in days if (day.year, day.month) == (year, month)]
        if [item["date"] for item in monthly_sources] != [day.isoformat() for day in expected]:
            raise ValueError("Monthly source provenance must contain every requested calendar day")
        for item, day in zip(monthly_sources, expected):
            path = staged_dir / ("rain_" + day.strftime("%d%m%Y") + ".bin")
            if Path(item["path"]).resolve() != path or _sha256(path) != item["sha256"]:
                raise ValueError("Daily source provenance changed during monthly aggregation")
            sidecar = path.with_suffix(".download.json")
            sources.append({**item, "year": year, "month": month, "path": str(path),
                            "sidecar_path": str(sidecar), "sidecar_sha256": _sha256(sidecar),
                            "units": "mm/day", "product_status": "provisional_real_time"})
        grids.append((year, month, grid))

    districts = gpd.read_file(geojson)
    required = [DISTRICT_COL, STATE_COL]
    if any(column not in districts for column in required):
        raise ValueError("District boundaries lack district and state identifiers")
    usable = districts[required].notna().all(axis=1)
    for column in required:
        usable &= districts[column].astype(str).str.strip().ne("")
    districts = districts.loc[usable].copy()
    if districts.empty:
        raise ValueError("No named district polygons available")
    frames = []
    for year, month, grid in grids:
        joined = assign_district(monthly_grid_points(grid, year, month), districts)
        aggregated = joined.groupby([DISTRICT_COL, STATE_COL, "year", "month"]).agg(
            rainfall_mm=("rainfall_mm", "mean"), spatial_method=("spatial_method", "first"),
            distance_m=("distance_m", "max"), n_cells=("_grid_index", "nunique")).reset_index()
        if (aggregated.empty or not aggregated.year.eq(year).all() or not aggregated.month.eq(month).all()
                or not np.isfinite(aggregated.rainfall_mm).all() or aggregated.rainfall_mm.lt(0).any()
                or aggregated.n_cells.lt(1).any() or not np.isfinite(aggregated.distance_m).all()
                or aggregated.distance_m.lt(0).any()):
            raise ValueError("Invalid district monthly rainfall candidate")
        frames.append(aggregated)
    monthly = pd.concat(frames, ignore_index=True)
    if monthly.duplicated([DISTRICT_COL, STATE_COL, "year", "month"]).any():
        raise ValueError("Duplicate district-month rainfall candidate")
    normals = monthly.groupby([DISTRICT_COL, STATE_COL, "month"]).agg(
        climatological_normal_mm=("rainfall_mm", "mean"), n_years=("year", "nunique"),
        baseline_start=("year", "min"), baseline_end=("year", "max")).reset_index()
    normals["purpose"] = "descriptive_all_years_not_historical_model_features"

    # Detect inputs changing while the offline spatial aggregation was running.
    if (_sha256(geojson) != boundary_hash or _sha256(canonical) != canonical_hash
            or _sha256(overlap_report) != report_hash):
        raise ValueError("Boundary or overlap provenance changed before candidate export")
    overlap_inputs = [(annual["path"], annual["sha256"]),
                      (annual["sidecar_path"], annual["sidecar_sha256"])]
    for item in report["comparisons"]:
        overlap_inputs.extend([(item["realtime_path"], item["realtime_sha256"]),
                               (item["realtime_sidecar_path"], item["realtime_sidecar_sha256"])])
    if any(_sha256(path) != digest for path, digest in overlap_inputs):
        raise ValueError("Sampled overlap sources or provenance changed before candidate export")
    for item in sources:
        if (_sha256(item["path"]) != item["sha256"]
                or _sha256(item["sidecar_path"]) != item["sidecar_sha256"]):
            raise ValueError("Daily source or provenance changed before candidate export")
    metadata = {"artifact_version": "weather-v3", "generator": "imd_realtime_monthly",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "sources": sources, "geojson_sha256": boundary_hash,
                "units": {"rainfall_mm": "mm/month"},
                "daily_aggregation": "sum_all_calendar_days_required",
                "spatial_fallback": "district_to_nearest_usable_land_cell",
                "baseline_start": min(day.year for day in days),
                "baseline_end": max(day.year for day in days), "n_years": len({day.year for day in days}),
                "calendar_months": [f"{year:04d}-{month:02d}" for year, month in periods],
                "n_days": len(days), "climatology_purpose": "descriptive_only",
                "descriptive_normal_warning": "Only exported months contribute; this is not a long-term climate normal or a historical feature baseline.",
                "product_status": "provisional_real_time", "candidate_only": True,
                "sampled_overlap": {**overlap, "annual_source": annual, "thresholds": report["thresholds"],
                                    "date_coverage": report["date_coverage"]},
                "network_requests_made": 0, "production_changes_made": False}
    _output_paths(output, normals_output, protected)
    _atomic_csv(output, monthly)
    _atomic_csv(normals_output, normals)
    _atomic_json(output.with_suffix(".manifest.json"), {**metadata, "csv_sha256": _sha256(output)})
    _atomic_json(normals_output.with_suffix(".manifest.json"), {**metadata, "csv_sha256": _sha256(normals_output)})
    return {"status": "candidate_exported", "output": str(output), "normals_output": str(normals_output),
            "district_month_rows": len(monthly), "months": metadata["calendar_months"], "days": len(days),
            "product_status": "provisional_real_time", "sampled_overlap": overlap,
            "network_requests_made": 0, "production_changes_made": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="First completed month, YYYY-MM")
    parser.add_argument("--end", required=True, help="Last completed month, YYYY-MM")
    parser.add_argument("--staged-dir", required=True, type=Path)
    parser.add_argument("--overlap-report", required=True, type=Path)
    parser.add_argument("--geojson", type=Path, help="Defaults to the configured canonical district boundaries")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--normals-output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = export_monthly(args.start, args.end, args.staged_dir, args.overlap_report,
                            args.output, args.normals_output, args.geojson)
    print(json.dumps(result, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    main()
