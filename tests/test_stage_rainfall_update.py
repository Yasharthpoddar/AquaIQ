"""Offline orchestration contracts; these tests never access HTTP or a database."""
from datetime import date
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import stage_rainfall_update as staging


@pytest.fixture
def project(tmp_path):
    (tmp_path / "config.yaml").write_text("project: AquaIQ\n")
    return tmp_path


@pytest.fixture
def plan(project):
    return staging.make_plan(project, "2026-01", "2026-09", as_of=date(2026, 10, 15))


def test_offline_plan_has_completed_days_without_writes(project):
    plan = staging.make_plan(project, "2026-01", as_of=date(2026, 10, 15))
    assert plan["end"] == "2026-09" and plan["planned_days"] == 273
    assert not (project / "data").exists()
    assert not (project / "reports").exists()


def test_current_month_and_inverted_range_rejected(project):
    for start, end in [("2026-10", "2026-10"), ("2026-09", "2026-01")]:
        with pytest.raises(ValueError):
            staging.make_plan(project, start, end, as_of=date(2026, 10, 15))


def test_main_defaults_offline(project, monkeypatch, capsys):
    run = Mock(side_effect=AssertionError("Run must be explicit"))
    monkeypatch.setattr(staging, "run_staging", run)
    assert staging.main(["--project-root", str(project), "--start", "2026-01", "--end", "2026-09"]) == 0
    assert json.loads(capsys.readouterr().out)["network_requests_made"] == 0
    run.assert_not_called()


def test_lock_rejects_overlap_and_releases_after_error(tmp_path):
    path = tmp_path / "job.lock"
    with pytest.raises(RuntimeError, match="test crash"):
        with staging.job_lock(path):
            with pytest.raises(staging.JobAlreadyRunning):
                with staging.job_lock(path):
                    pass
            raise RuntimeError("test crash")
    with staging.job_lock(path):
        pass


def mocks(monkeypatch, overlap_download="complete", verified=True, target="complete"):
    functions = {
        "download_dates": Mock(return_value={"status": overlap_download}),
        "compare_staged_days": Mock(return_value={"verified_overlap": verified}),
        "download_range": Mock(return_value={"status": target}),
        "export_monthly": Mock(return_value={"status": "candidate_exported"}),
        "_merged_candidate": Mock(return_value={"status": "candidate_merged"}),
    }
    for name, function in functions.items():
        monkeypatch.setattr(staging, name, function)
    return functions


def test_source_failure_stops_before_target_batch(plan, monkeypatch):
    functions = mocks(monkeypatch, overlap_download="incomplete")
    result = staging.run_staging(plan)
    assert result["status"] == "waiting_for_overlap_source"
    functions["compare_staged_days"].assert_not_called()
    functions["download_range"].assert_not_called()
    functions["export_monthly"].assert_not_called()


def test_failed_product_identity_never_exports(plan, monkeypatch):
    functions = mocks(monkeypatch, verified=False)
    result = staging.run_staging(plan)
    assert result["status"] == "overlap_requires_review"
    functions["download_range"].assert_not_called()
    functions["export_monthly"].assert_not_called()


def test_missing_target_days_never_export(plan, monkeypatch):
    functions = mocks(monkeypatch, target="incomplete")
    result = staging.run_staging(plan)
    assert result["status"] == "waiting_for_complete_months"
    functions["export_monthly"].assert_not_called()


def test_complete_pipeline_records_candidate_only_and_bounds(plan, monkeypatch):
    functions = mocks(monkeypatch)
    result = staging.run_staging(plan, max_days=4, attempts=1)
    assert result["status"] == "candidate_ready_for_review"
    assert result["production_changes_made"] is False
    assert functions["download_range"].call_args.kwargs["max_days"] == 4
    assert functions["download_dates"].call_args.kwargs["max_consecutive_failures"] == 1
    saved = json.loads((Path(plan["candidate_directory"]) / "progress.json").read_text())
    assert saved["status"] == result["status"]


def test_exception_checkpoints_and_next_run_resumes(plan, monkeypatch):
    functions = mocks(monkeypatch)
    functions["compare_staged_days"].side_effect = ValueError("bad annual provenance")
    with pytest.raises(ValueError, match="bad annual"):
        staging.run_staging(plan)
    saved = json.loads((Path(plan["candidate_directory"]) / "progress.json").read_text())
    assert saved["status"] == "failed" and saved["error"]["type"] == "ValueError"
    functions["compare_staged_days"].side_effect = None
    assert staging.run_staging(plan)["status"] == "candidate_ready_for_review"


def test_progress_of_another_plan_not_overwritten(plan, monkeypatch):
    directory = Path(plan["candidate_directory"])
    directory.mkdir(parents=True)
    output = directory / "progress.json"
    output.write_text('{"schema_version":"someone-else"}')
    calls = mocks(monkeypatch)
    before = output.read_bytes()
    with pytest.raises(ValueError, match="another staging plan"):
        staging.run_staging(plan)
    assert output.read_bytes() == before
    calls["download_dates"].assert_not_called()


def test_merge_refuses_unrelated_or_partial_output(tmp_path):
    (tmp_path / "combined.csv").write_text("unrelated data")
    with pytest.raises(ValueError, match="Partial"):
        staging._merged_candidate(tmp_path / "existing.csv", tmp_path / "monthly.csv", tmp_path)


def test_merge_reuses_only_verified_own_pair(tmp_path, monkeypatch):
    old, update = tmp_path / "old.csv", tmp_path / "monthly.csv"
    old.write_text("old"); update.write_text("new")
    for item in (old, update):
        item.with_suffix(".manifest.json").write_text('{"sources":[]}')
    for name in ("combined.csv", "combined_normals.csv"):
        csv = tmp_path / name
        csv.write_text("combined")
        csv.with_suffix(".manifest.json").write_text(json.dumps({
            "generator": "merge_rainfall_update", "sources": [], "csv_sha256": staging.digest(csv),
            "append_provenance": {"existing_csv_sha256": staging.digest(old), "update_csv_sha256": staging.digest(update)}}))
    merge = Mock(side_effect=AssertionError("Must reuse"))
    monkeypatch.setattr(staging, "merge_rainfall", merge)
    assert staging._merged_candidate(old, update, tmp_path)["status"] == "already_present"
    update.write_text("changed")
    with pytest.raises(ValueError, match="differs"):
        staging._merged_candidate(old, update, tmp_path)


def test_comparison_retry_preserves_provenance_hash(tmp_path):
    output = tmp_path / "overlap.json"
    original = {"verified_overlap": True, "created_at_utc": "yesterday", "sources": ["hash"]}
    staging._save_comparison(output, original)
    before = output.read_bytes()
    current = {**original, "created_at_utc": "today"}
    assert staging._save_comparison(output, current) == original
    assert output.read_bytes() == before
    with pytest.raises(ValueError, match="evidence changed"):
        staging._save_comparison(output, {**current, "sources": ["changed"]})
    assert output.read_bytes() == before


def published_rainfall(project, periods, *, drop_last=False):
    import pandas as pd
    import yaml
    canonical = project / "districts.geojson"
    canonical.write_text('{"type":"FeatureCollection","features":[]}')
    (project / "config.yaml").write_text(yaml.safe_dump({"paths": {"geojson_boundaries": "districts.geojson"}}))
    path = project / "data/processed/imd_rainfall_district_monthly.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"district": district, "st_nm": "State", "year": int(month[:4]), "month": int(month[-2:]), "rainfall_mm": 1.}
            for district in ("A", "B") for month in periods]
    pd.DataFrame(rows[:-1] if drop_last else rows).to_csv(path, index=False)
    manifest = {"artifact_version": "weather-v3", "csv_sha256": staging.digest(path),
                "units": {"rainfall_mm": "mm/month"}, "geojson_sha256": staging.digest(canonical),
                "daily_aggregation": "sum_all_calendar_days_required", "sources": [{"sha256": "a" * 64}]}
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest))
    return path


def test_auto_start_advances_after_verified_promotion(project):
    path = published_rainfall(project, ["2025-11", "2025-12"])
    plan = staging.make_plan(project, as_of=date(2026, 10, 15))
    assert plan["start"] == "2026-01"
    assert plan["automatic_start"]["csv_sha256"] == staging.digest(path)
    published_rainfall(project, ["2025-11", "2025-12", "2026-01"])
    assert staging.make_plan(project, as_of=date(2026, 10, 15))["start"] == "2026-02"


def test_auto_start_refuses_global_and_district_month_holes(project):
    published_rainfall(project, ["2026-01", "2026-03"])
    with pytest.raises(ValueError, match="holes"):
        staging.make_plan(project, as_of=date(2026, 10, 15))
    published_rainfall(project, ["2026-01", "2026-02"], drop_last=True)
    with pytest.raises(ValueError, match="holes"):
        staging.make_plan(project, as_of=date(2026, 10, 15))


def test_auto_start_refuses_tampered_csv_and_boundary(project):
    path = published_rainfall(project, ["2026-01"])
    path.write_text(path.read_text().replace("1.0", "2.0"))
    with pytest.raises(ValueError, match="hash"):
        staging.make_plan(project, as_of=date(2026, 10, 15))
    published_rainfall(project, ["2026-01"])
    (project / "districts.geojson").write_text("changed")
    with pytest.raises(ValueError, match="provenance"):
        staging.make_plan(project, as_of=date(2026, 10, 15))


def test_auto_start_no_work_does_not_lock_download_or_write(project, monkeypatch):
    published_rainfall(project, ["2026-08", "2026-09"])
    plan = staging.make_plan(project, as_of=date(2026, 10, 15))
    assert plan["status"] == "no_new_completed_months" and plan["planned_days"] == 0
    calls = mocks(monkeypatch)
    assert staging.run_staging(plan) == plan
    calls["download_dates"].assert_not_called()
    assert not (project / "reports").exists()
