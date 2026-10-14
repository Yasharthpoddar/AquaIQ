from datetime import date
import json

import numpy as np
import pytest

from data_ingestion.imd_realtime import DOWNLOAD_URL, NY, NX
from data_ingestion import imd_realtime_comparison as comparison
from data_ingestion.imd_realtime_comparison import (
    DEFAULT_ATOL_MM, DEFAULT_RTOL, compare_staged_days, main,
    validate_verified_overlap_report,
)
from data_ingestion.update_weather_sources import (
    IMD_ARCHIVE_DOWNLOAD, IMD_ARCHIVE_PAGE, sha256,
)

AS_OF = date(2026, 10, 14)
SAMPLE_DATES = [date(2025, 1, 1), date(2025, 6, 15), date(2025, 9, 30)]


@pytest.fixture
def sources(tmp_path):
    annual = tmp_path / "annual.grd"
    binary = np.memmap(annual, dtype="<f4", mode="w+", shape=(365, NY, NX))
    binary[:] = -999.0
    spatial = (np.arange(49, dtype=np.float32)[:, None] * 0.1
               + np.arange(100, dtype=np.float32)[None, :] * 0.01)
    for index in range(365):
        binary[index, :49, :100] = spatial + index / 10.0
    binary.flush()
    del binary
    metadata = {
        "year": 2025, "days": 365, "grid": [NY, NX],
        "dtype": "little-endian float32", "size_bytes": annual.stat().st_size,
        "units": "mm/day", "first_grid_point": [6.5, 66.5],
        "grid_step_degrees": 0.25, "negative_values_are_missing": True,
        "complete_day_records": True, "sha256": sha256(annual),
        "download_url": IMD_ARCHIVE_DOWNLOAD, "source_page": IMD_ARCHIVE_PAGE,
        "response_content_type": "application/octet-stream",
        "response_content_disposition": "attachment; filename=Rainfall/ind2025_rfp25.grd",
        "request_method": "POST", "request_form": {"rain": "2025"},
    }
    annual.with_suffix(".download.json").write_text(json.dumps(metadata))
    staged = tmp_path / "daily"
    staged.mkdir()
    reader = np.memmap(annual, dtype="<f4", mode="r", shape=(365, NY, NX))
    for day in SAMPLE_DATES:
        _stage(staged, day, reader[day.timetuple().tm_yday - 1])
    del reader
    return annual, staged


def _stage(directory, day, grid):
    path = directory / ("rain_" + day.strftime("%d%m%Y") + ".bin")
    np.asarray(grid, dtype="<f4").tofile(path)
    metadata = {
        "url": DOWNLOAD_URL, "form": {"rain": day.strftime("%d%m%Y")},
        "content_type": "application/octet-stream", "size_bytes": path.stat().st_size,
        "content_disposition": "attachment; filename=" + day.strftime("rain_ind0.25_%y_%m_%d.grd"),
        "sha256": sha256(path),
    }
    path.with_suffix(".download.json").write_text(json.dumps(metadata))
    return path


def _compare(sources, dates=SAMPLE_DATES, **kwargs):
    annual, staged = sources
    return compare_staged_days(annual, 2025, staged, dates, as_of=AS_OF, **kwargs)


def _report(sources, tmp_path):
    report = tmp_path / "overlap.json"
    report.write_text(json.dumps(_compare(sources)))
    return report


def test_matching_daily_dates_have_documented_sampled_overlap(sources):
    result = _compare(sources)
    assert result["status"] == "verified_overlap"
    assert result["verified_overlap"] is True
    assert result["date_coverage"]["date_diversity_passed"] is True
    assert result["thresholds"]["absolute_tolerance_mm"] == DEFAULT_ATOL_MM
    assert result["thresholds"]["relative_tolerance"] == DEFAULT_RTOL
    assert result["annual_source"]["sha256"] == sha256(sources[0])
    assert result["network_requests_made"] == 0
    assert result["production_changes_made"] is False
    assert "sampled dates" in result["scope_limit"]
    for item, day in zip(result["comparisons"], SAMPLE_DATES):
        assert item["date"] == day.isoformat()
        assert item["annual_day_index_zero_based"] == day.timetuple().tm_yday - 1
        assert item["shared_usable_cells"] == 4900
        assert item["fraction_matching_tolerance"] == 1.0
        assert item["maximum_absolute_difference_mm"] == 0
        assert item["mean_absolute_difference_mm"] == 0
        assert item["both_missing_cells"] == NY * NX - 4900


def test_small_float_roundtrip_difference_passes_declared_tolerance(sources):
    _, staged = sources
    day = SAMPLE_DATES[1]
    path = staged / ("rain_" + day.strftime("%d%m%Y") + ".bin")
    grid = np.fromfile(path, dtype="<f4").reshape(NY, NX)
    grid[0, 0] += 0.0005
    _stage(staged, day, grid)
    result = _compare(sources)
    assert result["verified_overlap"]
    assert 0 < result["comparisons"][1]["maximum_absolute_difference_mm"] < 0.001


def test_same_dimensions_with_wrong_values_require_review_and_do_not_rewrite(sources):
    _, staged = sources
    day = SAMPLE_DATES[1]
    path = staged / ("rain_" + day.strftime("%d%m%Y") + ".bin")
    grid = np.fromfile(path, dtype="<f4").reshape(NY, NX)
    grid[0, 0] += 12.0
    _stage(staged, day, grid)
    before = sha256(path)
    result = _compare(sources)
    assert result["status"] == "review_required"
    assert not result["verified_overlap"]
    item = result["comparisons"][1]
    assert item["maximum_absolute_difference_mm"] == 12.0
    assert item["cells_outside_tolerance"] == 1
    assert item["mean_absolute_difference_mm"] == pytest.approx(12 / 4900)
    assert item["fraction_matching_tolerance"] == pytest.approx(4899 / 4900)
    assert sha256(path) == before


def test_mask_mismatch_is_reported_even_when_shared_values_match(sources):
    _, staged = sources
    day = SAMPLE_DATES[0]
    path = staged / ("rain_" + day.strftime("%d%m%Y") + ".bin")
    grid = np.fromfile(path, dtype="<f4").reshape(NY, NX)
    grid[0, 0] = -999
    grid[100, 100] = 1.0
    _stage(staged, day, grid)
    result = _compare(sources)
    item = result["comparisons"][0]
    assert item["rainfall_values_passed"]
    assert item["mask_mismatch_cells"] == 2
    assert item["annual_only_usable_cells"] == 1
    assert item["realtime_only_usable_cells"] == 1
    assert not item["usable_masks_passed"]
    assert not result["verified_overlap"]


def test_insufficient_shared_cells_require_review(sources):
    result = _compare(sources, min_shared_cells=5000)
    assert not result["verified_overlap"]
    assert all(not item["grid_coverage_passed"] for item in result["comparisons"])


def test_two_dates_cannot_verify_product_overlap(sources):
    result = _compare(sources, SAMPLE_DATES[:2])
    assert all(item["passed"] for item in result["comparisons"])
    assert result["status"] == "review_required"
    assert result["review_reasons"] == ["insufficient_date_and_month_diversity"]


def test_three_monsoon_dates_do_not_meet_date_diversity(sources):
    annual, staged = sources
    days = [date(2025, 6, 1), date(2025, 7, 1), date(2025, 8, 1)]
    archive = np.memmap(annual, dtype="<f4", mode="r", shape=(365, NY, NX))
    for day in days:
        _stage(staged, day, archive[day.timetuple().tm_yday - 1])
    del archive
    result = _compare(sources, days)
    assert not result["date_coverage"]["has_sample_outside_june_to_september"]
    assert not result["verified_overlap"]


@pytest.mark.parametrize("dates", [["2025-1-01"], ["2026-01-01"],
                                   ["2025-01-01", "2025-01-01"], []])
def test_bad_or_duplicate_dates_are_rejected(sources, dates):
    with pytest.raises(ValueError):
        _compare(sources, dates)


@pytest.mark.parametrize("field,value", [
    ("download_url", "https://example.invalid/rainfall.php"),
    ("request_form", {"rain": "2024"}), ("year", 2024),
    ("units", "anomaly"), ("sha256", "changed"), ("grid", [135, 129]),
    ("response_content_disposition", "attachment; filename=ind2024_rfp25.grd"),
])
def test_annual_source_provenance_is_required(sources, field, value):
    sidecar = sources[0].with_suffix(".download.json")
    metadata = json.loads(sidecar.read_text())
    metadata[field] = value
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        _compare(sources)


@pytest.mark.parametrize("missing", ["annual", "annual_sidecar", "daily", "daily_sidecar"])
def test_missing_source_or_provenance_is_rejected(sources, missing):
    annual, staged = sources
    target = {
        "annual": annual, "annual_sidecar": annual.with_suffix(".download.json"),
        "daily": staged / "rain_01012025.bin",
        "daily_sidecar": staged / "rain_01012025.download.json",
    }[missing]
    target.unlink()
    with pytest.raises(ValueError, match="missing"):
        _compare(sources)


def test_offline_cli_writes_report_only(sources, tmp_path, capsys):
    annual, staged = sources
    output = tmp_path / "reports" / "comparison.json"
    annual_before = sha256(annual)
    result = main(["--annual-file", str(annual), "--annual-year", "2025",
                   "--staged-dir", str(staged), "--dates",
                   *[day.isoformat() for day in SAMPLE_DATES], "--output", str(output)])
    assert result["verified_overlap"]
    assert json.loads(output.read_text()) == json.loads(capsys.readouterr().out)
    assert sha256(annual) == annual_before


@pytest.mark.parametrize("source", ["annual", "annual_sidecar", "daily", "daily_sidecar"])
def test_report_cannot_overwrite_sources(sources, source):
    annual, staged = sources
    output = {"annual": annual, "annual_sidecar": annual.with_suffix(".download.json"),
              "daily": staged / "rain_01012025.bin",
              "daily_sidecar": staged / "rain_01012025.download.json"}[source]
    with pytest.raises(ValueError, match="overwrite"):
        main(["--annual-file", str(annual), "--annual-year", "2025",
              "--staged-dir", str(staged), "--dates", "2025-01-01", "--output", str(output)])


@pytest.mark.parametrize("filename", ["rain_01012026.bin", "rain_01012026.download.json",
                                      "rain_01012026.json", "annual.download.json"])
def test_report_rejects_nonsampled_sources_before_comparison(sources, filename, monkeypatch):
    annual, staged = sources
    output = staged / filename
    before = b'{"source": "preserve this non-sampled data"}'
    output.write_bytes(before)
    monkeypatch.setattr(comparison, "compare_staged_days", lambda *args, **kwargs: pytest.fail(
        "Unsafe output must be rejected before reading/comparing source data"))
    with pytest.raises(ValueError):
        main(["--annual-file", str(annual), "--annual-year", "2025",
              "--staged-dir", str(staged), "--dates",
              *[day.isoformat() for day in SAMPLE_DATES], "--output", str(output)])
    assert output.read_bytes() == before


@pytest.mark.parametrize("directory", ["data/processed", "models/checkpoints"])
def test_report_rejects_production_paths_before_comparison(sources, tmp_path, monkeypatch, directory):
    annual, staged = sources
    project = tmp_path / "project"
    monkeypatch.setattr(comparison, "ROOT", project)
    output = project / directory / "existing.json"
    output.parent.mkdir(parents=True)
    before = b'{"schema_version": "imd-realtime-overlap-v1", "purpose": "production data"}'
    output.write_bytes(before)
    monkeypatch.setattr(comparison, "compare_staged_days", lambda *args, **kwargs: pytest.fail(
        "Production output must be rejected before source comparison"))
    with pytest.raises(ValueError, match="production"):
        main(["--annual-file", str(annual), "--annual-year", "2025",
              "--staged-dir", str(staged), "--dates", "2025-01-01", "--output", str(output)])
    assert output.read_bytes() == before


def test_report_rejects_existing_unrelated_json_before_comparison(sources, tmp_path, monkeypatch):
    annual, staged = sources
    output = tmp_path / "unrelated.json"
    before = b'{"configuration": "preserve"}'
    output.write_bytes(before)
    monkeypatch.setattr(comparison, "compare_staged_days", lambda *args, **kwargs: pytest.fail(
        "Unrelated existing output must be rejected before source comparison"))
    with pytest.raises(ValueError, match="existing output"):
        main(["--annual-file", str(annual), "--annual-year", "2025",
              "--staged-dir", str(staged), "--dates", "2025-01-01", "--output", str(output)])
    assert output.read_bytes() == before


def test_existing_overlap_report_can_be_atomically_replaced(sources, tmp_path, capsys):
    annual, staged = sources
    output = tmp_path / "comparison.json"
    output.write_text(json.dumps({"schema_version": "imd-realtime-overlap-v1", "old": True}))
    main(["--annual-file", str(annual), "--annual-year", "2025", "--staged-dir", str(staged),
          "--dates", *[day.isoformat() for day in SAMPLE_DATES], "--output", str(output)])
    result = json.loads(output.read_text())
    assert result["verified_overlap"]
    assert "old" not in result
    assert json.loads(capsys.readouterr().out) == result
    assert not list(tmp_path.glob("comparison.json.*.partial"))


def test_readiness_gate_rechecks_default_thresholds_and_source_hashes(sources, tmp_path):
    report = _report(sources, tmp_path)
    result = validate_verified_overlap_report(report, as_of=AS_OF)
    assert result["sampled_overlap_ready"]
    assert result["report_sha256"] == sha256(report)
    assert result["sampled_dates"] == [day.isoformat() for day in SAMPLE_DATES]
    assert "all dated source files" in result["additional_requirement"]


@pytest.mark.parametrize("source", ["annual", "annual_sidecar", "daily", "daily_sidecar"])
def test_readiness_gate_rejects_changed_sources_or_sidecars(sources, tmp_path, source):
    report = _report(sources, tmp_path)
    annual, staged = sources
    path = {"annual": annual, "annual_sidecar": annual.with_suffix(".download.json"),
            "daily": staged / "rain_01012025.bin",
            "daily_sidecar": staged / "rain_01012025.download.json"}[source]
    with path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="changed"):
        validate_verified_overlap_report(report, as_of=AS_OF)


def test_readiness_gate_rejects_manually_changed_review_status(sources, tmp_path):
    result = _compare(sources, SAMPLE_DATES[:2])
    result["status"] = "verified_overlap"
    result["verified_overlap"] = True
    report = tmp_path / "forged.json"
    report.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="no longer passes"):
        validate_verified_overlap_report(report, as_of=AS_OF)


def test_permissive_experimental_tolerances_cannot_grant_readiness(sources, tmp_path):
    result = _compare(sources, atol_mm=10.0)
    assert result["verified_overlap"]
    report = tmp_path / "permissive.json"
    report.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="thresholds"):
        validate_verified_overlap_report(report, as_of=AS_OF)


@pytest.mark.parametrize("kwargs", [{"atol_mm": -1}, {"rtol": float("nan")},
                                    {"min_shared_fraction": 0}, {"min_shared_cells": 0}])
def test_invalid_comparison_thresholds_are_rejected(sources, kwargs):
    with pytest.raises(ValueError):
        _compare(sources, **kwargs)
