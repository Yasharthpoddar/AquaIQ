"""Compare staged provisional IMD days with a provenanced annual archive.

This offline check writes only an optional comparison report. Matching grid
dimensions do not establish product identity. A passing report is evidence of
agreement on the sampled dates, not proof for all dates or all of India.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re

import numpy as np

from data_ingestion.imd_realtime import NY, NX, _atomic_json, read_staged_daily
from data_ingestion.update_weather_sources import (
    IMD_ARCHIVE_DOWNLOAD, IMD_ARCHIVE_PAGE, ROOT, sha256, validate_imd,
)

DEFAULT_ATOL_MM = 0.001
DEFAULT_RTOL = 0.00001
DEFAULT_MIN_SHARED_CELLS = 1000
DEFAULT_MIN_SHARED_FRACTION = 0.95
MIN_DATES = 3
MONSOON_SAMPLE_MONTHS = frozenset({6, 7, 8, 9})


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"Required source provenance is missing: {path}")
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError(f"Source provenance must be a JSON object: {path}")
    return result


def validate_annual_source(path: Path, year: int) -> dict:
    """Validate bytes and the actual annual downloader's sidecar schema."""
    if not path.is_file():
        raise ValueError(f"Annual rainfall file is missing: {path}")
    sidecar = path.with_suffix(".download.json")
    metadata = _load_json(sidecar)
    required = {
        "download_url": IMD_ARCHIVE_DOWNLOAD,
        "source_page": IMD_ARCHIVE_PAGE,
        "request_method": "POST",
        "request_form": {"rain": str(year)},
        "year": year,
        "days": 366 if calendar.isleap(year) else 365,
        "grid": [NY, NX],
        "dtype": "little-endian float32",
        "units": "mm/day",
        "first_grid_point": [6.5, 66.5],
        "grid_step_degrees": 0.25,
        "negative_values_are_missing": True,
        "complete_day_records": True,
    }
    for key, expected in required.items():
        if metadata.get(key) != expected:
            raise ValueError(f"Annual provenance has unexpected {key}")
    if "html" in str(metadata.get("response_content_type", "")).lower():
        raise ValueError("Annual source provenance identifies HTML rather than rainfall")
    disposition = str(metadata.get("response_content_disposition", ""))
    match = re.search(r'filename\s*=\s*"?([^";\s]+)', disposition, re.I)
    # The actual official response includes a Rainfall/ prefix in its filename.
    if not match or match.group(1).replace("\\", "/").split("/")[-1] != f"ind{year}_rfp25.grd":
        raise ValueError("Annual response filename does not identify the requested year/product")
    details = validate_imd(path, year)
    if metadata.get("size_bytes") != details["size_bytes"]:
        raise ValueError("Annual rainfall size differs from its source provenance")
    if metadata.get("sha256") != details["sha256"]:
        raise ValueError("Annual rainfall checksum differs from its source provenance")
    return {
        "path": str(path.resolve()), "sidecar_path": str(sidecar.resolve()),
        "sidecar_sha256": sha256(sidecar),
        "download_url": metadata["download_url"],
        "source_page": metadata["source_page"],
        "request_method": metadata["request_method"],
        "request_form": metadata["request_form"],
        "response_content_disposition": disposition,
        "retrieved_at_utc": metadata.get("retrieved_at_utc"),
        **details,
    }


def _parse_dates(values: list[str | date], year: int) -> list[date]:
    parsed = []
    for value in values:
        if isinstance(value, datetime):
            raise ValueError("Comparison dates must be calendar dates, not timestamps")
        if isinstance(value, date):
            day = value
        else:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Comparison dates must use YYYY-MM-DD format")
            day = date.fromisoformat(value)
        if day.year != year:
            raise ValueError("Every comparison date must belong to the annual archive year")
        parsed.append(day)
    if not parsed:
        raise ValueError("At least one comparison date must be specified")
    if len(set(parsed)) != len(parsed):
        raise ValueError("Duplicate comparison dates cannot increase verification coverage")
    return sorted(parsed)


def compare_staged_days(annual_file: Path, annual_year: int, staged_dir: Path,
                        dates: list[str | date], *, atol_mm: float = DEFAULT_ATOL_MM,
                        rtol: float = DEFAULT_RTOL,
                        min_shared_cells: int = DEFAULT_MIN_SHARED_CELLS,
                        min_shared_fraction: float = DEFAULT_MIN_SHARED_FRACTION,
                        as_of: date | None = None) -> dict:
    """Return sampled agreement or review_required; never modify source grids.

    Dates must include three different months and both a Jun-Sep sample and a
    sample outside those months. This calendar diversity is not a declaration
    that all Indian districts have the same wet/dry season.
    """
    if not np.isfinite([atol_mm, rtol, min_shared_fraction]).all():
        raise ValueError("Comparison thresholds must be finite")
    if atol_mm < 0 or rtol < 0:
        raise ValueError("Rainfall comparison tolerances cannot be negative")
    if isinstance(min_shared_cells, bool) or not isinstance(min_shared_cells, int) or not 1 <= min_shared_cells <= NY * NX:
        raise ValueError("Minimum shared cell count must be within the grid")
    if not 0 < min_shared_fraction <= 1:
        raise ValueError("Minimum shared fraction must be greater than zero and at most one")
    annual_file, staged_dir = Path(annual_file), Path(staged_dir)
    sampled_dates = _parse_dates(dates, annual_year)
    annual_source = validate_annual_source(annual_file, annual_year)
    months = {day.month for day in sampled_dates}
    coverage = {
        "minimum_dates": MIN_DATES,
        "requested_dates": len(sampled_dates), "unique_months": sorted(months),
        "minimum_distinct_months": 3,
        "monsoon_sample_months": sorted(MONSOON_SAMPLE_MONTHS),
        "has_june_to_september_sample": bool(months & MONSOON_SAMPLE_MONTHS),
        "has_sample_outside_june_to_september": bool(months - MONSOON_SAMPLE_MONTHS),
    }
    coverage["date_diversity_passed"] = (
        len(sampled_dates) >= MIN_DATES and len(months) >= 3
        and coverage["has_june_to_september_sample"]
        and coverage["has_sample_outside_june_to_september"]
    )
    annual = np.memmap(annual_file, dtype="<f4", mode="r",
                       shape=(annual_source["days"], NY, NX))
    comparisons = []
    try:
        for day in sampled_dates:
            stem = staged_dir / ("rain_" + day.strftime("%d%m%Y"))
            daily_path = stem.with_suffix(".bin")
            daily_sidecar = stem.with_suffix(".download.json")
            if not daily_path.is_file() or not daily_sidecar.is_file():
                raise ValueError(f"Staged daily rainfall or provenance is missing for {day.isoformat()}")
            realtime = read_staged_daily(staged_dir, day, as_of)
            archived = np.asarray(annual[day.timetuple().tm_yday - 1], dtype=np.float64)
            annual_valid = np.isfinite(archived) & (archived >= 0)
            daily_valid = np.isfinite(realtime)
            common = annual_valid & daily_valid
            union = annual_valid | daily_valid
            common_count, union_count = int(common.sum()), int(union.sum())
            shared_fraction = common_count / union_count if union_count else 0.0
            mask_mismatches = int(np.count_nonzero(annual_valid != daily_valid))
            difference = np.abs(realtime[common].astype(np.float64) - archived[common])
            matching = np.isclose(realtime[common], archived[common], atol=atol_mm, rtol=rtol)
            value_passed = bool(common_count and matching.all())
            grid_coverage_passed = (common_count >= min_shared_cells
                                    and shared_fraction >= min_shared_fraction)
            mask_passed = mask_mismatches == 0
            reasons = []
            if not grid_coverage_passed:
                reasons.append("insufficient_shared_grid_coverage")
            if not mask_passed:
                reasons.append("usable_grid_masks_differ")
            if not value_passed:
                reasons.append("rainfall_values_differ_beyond_predeclared_tolerance")
            comparisons.append({
                "date": day.isoformat(), "annual_day_index_zero_based": day.timetuple().tm_yday - 1,
                "realtime_path": str(daily_path.resolve()),
                "realtime_sha256": sha256(daily_path),
                "realtime_sidecar_path": str(daily_sidecar.resolve()),
                "realtime_sidecar_sha256": sha256(daily_sidecar),
                "annual_usable_cells": int(annual_valid.sum()),
                "realtime_usable_cells": int(daily_valid.sum()),
                "shared_usable_cells": common_count, "union_usable_cells": union_count,
                "shared_usable_fraction_of_union": shared_fraction,
                "annual_only_usable_cells": int((annual_valid & ~daily_valid).sum()),
                "realtime_only_usable_cells": int((daily_valid & ~annual_valid).sum()),
                "mask_mismatch_cells": mask_mismatches,
                "both_missing_cells": int((~annual_valid & ~daily_valid).sum()),
                "mean_absolute_difference_mm": float(difference.mean()) if common_count else None,
                "maximum_absolute_difference_mm": float(difference.max()) if common_count else None,
                "fraction_matching_tolerance": float(matching.mean()) if common_count else 0.0,
                "cells_outside_tolerance": int(common_count - matching.sum()),
                "rainfall_values_passed": value_passed,
                "grid_coverage_passed": grid_coverage_passed,
                "usable_masks_passed": mask_passed,
                "passed": not reasons, "review_reasons": reasons,
            })
    finally:
        del annual
    passed = bool(coverage["date_diversity_passed"] and all(item["passed"] for item in comparisons))
    reasons = [] if coverage["date_diversity_passed"] else ["insufficient_date_and_month_diversity"]
    reasons += [f"{item['date']}: {reason}" for item in comparisons for reason in item["review_reasons"]]
    return {
        "schema_version": "imd-realtime-overlap-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified_overlap" if passed else "review_required",
        "verified_overlap": passed, "review_reasons": reasons,
        "annual_source": annual_source,
        "units": "mm/day", "grid": [NY, NX],
        "grid_orientation": "south_to_north_latitude; longitude_varies_fastest",
        "first_grid_point": [6.5, 66.5], "grid_step_degrees": 0.25,
        "thresholds": {
            "absolute_tolerance_mm": atol_mm, "relative_tolerance": rtol,
            "relative_tolerance_reference": "annual_archive_value",
            "minimum_shared_cells_per_date": min_shared_cells,
            "minimum_shared_fraction_of_union_per_date": min_shared_fraction,
            "require_identical_usable_masks": True,
            "required_fraction_matching_tolerance": 1.0,
        },
        "date_coverage": coverage, "comparisons": comparisons,
        "scope_limit": "Agreement covers only the sampled dates and shared grid cells. It does not prove countrywide product identity, all remaining dates, or current-year accuracy.",
        "product_warning": "Real-time rainfall is provisional; the annual archive can contain quality-control revisions. Differences require review and are never rewritten automatically.",
        "network_requests_made": 0, "source_data_modified": False,
        "production_changes_made": False,
    }


def validate_verified_overlap_report(report_file: Path, *, as_of: date | None = None) -> dict:
    """Recheck an existing report and immutable sources before a later export.

    Format validation or a manually changed status cannot grant readiness.
    More permissive experimental tolerances also cannot grant this default gate.
    The caller still has to validate every day of each proposed complete month;
    this helper neither promotes data nor validates any prediction model.
    """
    report_file = Path(report_file)
    report = _load_json(report_file)
    if report.get("schema_version") != "imd-realtime-overlap-v1" or report.get("status") != "verified_overlap" or report.get("verified_overlap") is not True:
        raise ValueError("An existing verified sampled-overlap report is required")
    thresholds = report.get("thresholds", {})
    try:
        atol = float(thresholds["absolute_tolerance_mm"])
        rtol = float(thresholds["relative_tolerance"])
        minimum_cells = thresholds["minimum_shared_cells_per_date"]
        minimum_fraction = float(thresholds["minimum_shared_fraction_of_union_per_date"])
        if (not np.isfinite([atol, rtol, minimum_fraction]).all()
                or not 0 <= atol <= DEFAULT_ATOL_MM or not 0 <= rtol <= DEFAULT_RTOL
                or isinstance(minimum_cells, bool) or not isinstance(minimum_cells, int)
                or minimum_cells < DEFAULT_MIN_SHARED_CELLS
                or not DEFAULT_MIN_SHARED_FRACTION <= minimum_fraction <= 1
                or thresholds.get("require_identical_usable_masks") is not True
                or thresholds.get("required_fraction_matching_tolerance") != 1.0
                or thresholds.get("relative_tolerance_reference") != "annual_archive_value"):
            raise ValueError("Report thresholds do not satisfy the default overlap gate")
        annual_source = report["annual_source"]
        annual_file = Path(annual_source["path"])
        annual_sidecar = annual_file.with_suffix(".download.json")
        if str(annual_sidecar.resolve()) != annual_source["sidecar_path"]:
            raise ValueError("Report annual provenance path differs from the source sidecar")
        if sha256(annual_file) != annual_source["sha256"] or sha256(annual_sidecar) != annual_source["sidecar_sha256"]:
            raise ValueError("Annual source or provenance changed after overlap verification")
        comparisons = report["comparisons"]
        if not isinstance(comparisons, list) or not comparisons:
            raise ValueError("The report lacks sampled comparisons")
        directories = set()
        dates = []
        for item in comparisons:
            daily_file = Path(item["realtime_path"])
            daily_sidecar = daily_file.with_suffix(".download.json")
            if str(daily_sidecar.resolve()) != item["realtime_sidecar_path"]:
                raise ValueError("Report daily provenance path differs from the source sidecar")
            if sha256(daily_file) != item["realtime_sha256"] or sha256(daily_sidecar) != item["realtime_sidecar_sha256"]:
                raise ValueError("A sampled daily source or provenance changed after verification")
            directories.add(daily_file.parent.resolve())
            dates.append(item["date"])
        if len(directories) != 1:
            raise ValueError("Sampled daily sources must come from one staged directory")
        checked = compare_staged_days(annual_file, annual_source["year"], directories.pop(), dates,
                                      atol_mm=atol, rtol=rtol, min_shared_cells=minimum_cells,
                                      min_shared_fraction=minimum_fraction, as_of=as_of)
        if not checked["verified_overlap"]:
            raise ValueError("The report no longer passes sampled overlap verification")
    except (KeyError, TypeError, OSError) as error:
        raise ValueError("Overlap report is incomplete or its source files are missing") from error
    return {
        "sampled_overlap_ready": True, "report_path": str(report_file.resolve()),
        "report_sha256": sha256(report_file), "status": checked["status"],
        "annual_sha256": checked["annual_source"]["sha256"],
        "sampled_dates": [item["date"] for item in checked["comparisons"]],
        "scope_limit": checked["scope_limit"],
        "additional_requirement": "Validate all dated source files and complete calendar months before export. This gate does not establish operational model accuracy.",
        "production_changes_made": False,
    }


def _validate_report_output(output: Path, protected: list[Path]) -> None:
    """Allow only a report destination; never overwrite staged/production data."""
    resolved = output.resolve()
    if resolved in {path.resolve() for path in protected}:
        raise ValueError("Comparison output cannot overwrite a source or provenance file")
    if output.suffix.lower() != ".json":
        raise ValueError("Comparison output must be a .json report")
    if (output.name.lower().endswith(".download.json")
            or re.fullmatch(r"rain_\d{8}(?:\..*)?", output.name, re.I)):
        raise ValueError("Comparison output cannot overwrite reserved daily source/provenance filenames")
    for directory in (ROOT / "data" / "processed", ROOT / "models" / "checkpoints"):
        if resolved.is_relative_to(directory.resolve()):
            raise ValueError("Comparison output cannot overwrite production data or model paths")
    if output.exists():
        existing = _load_json(output)
        if existing.get("schema_version") != "imd-realtime-overlap-v1":
            raise ValueError("An existing output may be overwritten only if it is an IMD overlap report")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annual-file", required=True, type=Path)
    parser.add_argument("--annual-year", required=True, type=int)
    parser.add_argument("--staged-dir", required=True, type=Path)
    parser.add_argument("--dates", required=True, nargs="+", help="YYYY-MM-DD dates in the annual archive year")
    parser.add_argument("--output", type=Path, help="Optional JSON comparison report")
    parser.add_argument("--atol-mm", type=float, default=DEFAULT_ATOL_MM)
    parser.add_argument("--rtol", type=float, default=DEFAULT_RTOL)
    args = parser.parse_args(argv)
    # An explicit report path must never overwrite a source or its provenance.
    if args.output is not None:
        days = _parse_dates(args.dates, args.annual_year)
        protected = [args.annual_file, args.annual_file.with_suffix(".download.json")]
        for day in days:
            stem = args.staged_dir / ("rain_" + day.strftime("%d%m%Y"))
            protected.extend([stem.with_suffix(".bin"), stem.with_suffix(".download.json")])
        _validate_report_output(args.output, protected)
    result = compare_staged_days(args.annual_file, args.annual_year, args.staged_dir, args.dates,
                                 atol_mm=args.atol_mm, rtol=args.rtol)
    payload = json.dumps(result, indent=2, allow_nan=False)
    if args.output is not None:
        _atomic_json(args.output, result)
    print(payload)
    return result


if __name__ == "__main__":
    raise SystemExit(0 if main()["verified_overlap"] else 2)
