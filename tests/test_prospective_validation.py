import copy
import importlib.util
import json
from pathlib import Path
import sys

import pandas as pd
import pytest

BASE = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    original_path = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
    return module

p = load("test_prospective_validation_module", BASE/"models/prospective_validation.py")
cli = load("test_record_live_forecasts_module", BASE/"scripts/record_live_forecasts.py")
ISSUED = "2026-10-15T10:00:00+00:00"
LATER = "2027-06-01T10:00:00+00:00"


@pytest.fixture
def archive():
    forecast = {"district_id": "GJ-Gandhinagar", "status": "projection", "units": "m_bgl",
        "as_of": "2026-10-15", "estimate_type": "district_level", "source_zone": None,
        "last_observed_date": "2026-01-01", "data_age_months": 9, "last_observed_gwl": 6.,
        "weather_basis": {"method": "historical_monthly_climatology"}, "feature_generation": "fixture_generation",
        "model_sha256": "a"*64,
        "forecast": [{"date": date.date().isoformat(), "predicted_gwl": 5.+index}
                     for index, date in enumerate(pd.date_range("2026-11-01", periods=6, freq="MS"))]}
    provenance = {key: "a"*64 for key in p.HASHES}
    provenance.update(district_id="GJ-Gandhinagar", feature_generation_id="fixture_generation")
    card = {"model_sha256": "a"*64, "feature_generation_id": "fixture_generation", "train_target_cutoff": "2019-12-31"}
    return p.create_record(forecast, card, provenance, issued_at=ISSUED)


@pytest.fixture
def label():
    return {"district_id": "GJ-Gandhinagar", "month": "2026-11", "depth_m_bgl": 7.,
        "is_observed": True, "is_imputed": False, "units": "m_bgl",
        "observed_at": "2026-11-20T10:00:00+00:00", "available_at": "2026-12-10T10:00:00+00:00",
        "source": "independent_fixture_source", "source_record_id": "fixture-record-1",
        "source_sha256": "b"*64, "geography_sha256": "a"*64, "evidence_origin": "independent_measurement"}


def rehash(record):
    record["record_sha256"] = p.checksum({key: value for key, value in record.items() if key != "record_sha256"})
    return record


def test_archive_preserves_full_evidence_and_validates_checksum(archive):
    assert p.validate_record(archive, now=ISSUED) is archive
    assert archive["forecast"]["weather_basis"]["method"] == "historical_monthly_climatology"
    changed = copy.deepcopy(archive)
    changed["forecast"]["forecast"][0]["predicted_gwl"] = 10.
    with pytest.raises(ValueError, match="checksum"):
        p.validate_record(changed, now=ISSUED)


@pytest.mark.parametrize("field,value", [("as_of", "2026-10-14"), ("as_of", "2026-10-16"),
    ("units", "cm"), ("status", "insufficient_data"), ("estimate_type", "unknown"),
    ("data_age_months", 8), ("last_observed_date", "2026-11-01"), ("weather_basis", None)])
def test_archive_rejects_backdates_bad_evidence_and_units(archive, field, value):
    archive["forecast"][field] = value
    with pytest.raises(ValueError):
        p.validate_record(rehash(archive), now=ISSUED)


def test_zone_requires_zone_and_six_future_months(archive):
    archive["forecast"]["estimate_type"] = "zone_fallback"
    with pytest.raises(ValueError, match="source zone"):
        p.validate_record(rehash(archive), now=ISSUED)
    archive["forecast"]["source_zone"] = "Z"
    assert p.validate_record(rehash(archive), now=ISSUED)
    archive["forecast"]["forecast"][0]["date"] = "2026-10-01"
    with pytest.raises(ValueError, match="Six monthly targets"):
        p.validate_record(rehash(archive), now=ISSUED)


def test_archive_checks_model_card_and_future_issue(archive):
    with pytest.raises(ValueError, match="future"):
        p.validate_record(archive, now="2026-10-14T10:00:00Z")
    archive["model_card"]["model_sha256"] = "c"*64
    with pytest.raises(ValueError, match="identities"):
        p.validate_record(rehash(archive), now=ISSUED)


def test_unmeasured_targets_stay_pending(archive):
    report = p.evaluate_records([archive], [], now=ISSUED)
    assert report["status"] == "awaiting_independent_labels"
    assert report["matched_targets"] == 0 and report["pending_targets"] == 6
    assert report["errors"]["rmse_m"] is None
    assert report["sufficient_for_operational_use"] is False


def test_later_matching_observation_reports_paired_baseline(archive, label):
    report = p.evaluate_records([archive], pd.DataFrame([label]), now=LATER)
    assert report["matched_targets"] == 1 and report["pending_targets"] == 5
    assert report["errors"]["rmse_m"] == 2.
    assert report["errors"]["persistence_rmse_m"] == 1.
    assert report["errors"]["paired_forecast_rmse_m"] == 2.
    assert report["cases"][0]["horizon_months"] == 1
    assert report["cases"][0]["data_age_months"] == 9


@pytest.mark.parametrize("field,value", [("is_observed", False), ("is_imputed", True),
    ("units", "cm"), ("depth_m_bgl", -1), ("depth_m_bgl", float("inf")),
    ("depth_m_bgl", "bad"), ("evidence_origin", "model_output"), ("source", ""),
    ("source_record_id", ""), ("source_sha256", "unknown"), ("geography_sha256", "c"*64),
    ("observed_at", "2026-10-20T10:00:00Z"), ("available_at", "2026-11-01T10:00:00Z"),
    ("available_at", "2028-01-01T00:00:00Z"), ("available_at", "2026-12-10"),
    ("month", "2026-01"), ("district_id", "UNKNOWN")])
def test_actual_labels_reject_imputation_future_misalignment_and_missing_provenance(archive, label, field, value):
    label[field] = value
    with pytest.raises(ValueError):
        p.evaluate_records([archive], [label], now=LATER)


def test_duplicate_archives_and_duplicate_labels_rejected(archive, label):
    with pytest.raises(ValueError, match="Duplicate forecast"):
        p.evaluate_records([archive, archive], [], now=LATER)
    second = copy.deepcopy(archive)
    second["issued_at_utc"] = "2026-10-15T11:00:00Z"
    with pytest.raises(ValueError, match="Duplicate forecast"):
        p.evaluate_records([archive, rehash(second)], [], now=LATER)
    with pytest.raises(ValueError, match="Duplicate or misaligned"):
        p.evaluate_records([archive], [label, label], now=LATER)


def test_live_cli_is_offline_by_default_and_refuses_backdate_option(monkeypatch):
    monkeypatch.setattr(cli, "validation_module", lambda: pytest.fail("Offline plan loaded live evidence."))
    report = cli.main([])
    assert report["database_used"] is False
    assert report["production_changes_made"] is False
    with pytest.raises(SystemExit):
        cli.main(["--run", "--district", "GJ-Gandhinagar", "--as-of", "2020-01-01"])


def test_candidate_files_never_overwrite_or_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    directory = cli.candidate_directory()
    file = cli.write_new(directory, "record.json", {"example": True})
    with pytest.raises(FileExistsError):
        cli.write_new(directory, "record.json", {"other": True})
    with pytest.raises(ValueError):
        cli.write_new(directory, "../outside.json", {})
    assert json.loads(file.read_text()) == {"example": True}


def test_current_live_readonly_session_and_canonical_selection(tmp_path, monkeypatch, archive):
    from unittest.mock import Mock
    from models import climate_forecast as climate
    from models import ensemble
    import db.connection
    import yaml
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    processed = tmp_path/"data/processed"
    processed.mkdir(parents=True)
    (processed/"features_matrix.csv").write_text("fixture")
    manifest = {"generation_id": "fixture_generation", "feature_csv_sha256": cli.file_sha(processed/"features_matrix.csv")}
    (processed/"feature_manifest.json").write_text(json.dumps(manifest))
    (tmp_path/"geo.json").write_text("fixture boundaries")
    (tmp_path/"config.yaml").write_text(yaml.safe_dump({"fixture": True}))
    checkpoint = tmp_path/"model.json"
    checkpoint.write_text(json.dumps({"model_sha256": "a"*64, "card_sha256": "a"*64}))
    monkeypatch.setattr(climate, "CHECKPOINT_PATH", checkpoint)
    monkeypatch.setattr(climate, "load_bundle", lambda *args, **kwargs: (object(), archive["model_card"]))
    monkeypatch.setattr(climate, "forecast_from_evidence", lambda evidence: archive["forecast"])
    monkeypatch.setattr(ensemble, "feature_generation", lambda: "fixture_generation")
    monkeypatch.setattr(ensemble, "CONFIG", {"paths": {"data_processed": "data/processed", "geojson_boundaries": "geo.json"}})
    selection = Mock(return_value={"district_id": "GJ-Gandhinagar"})
    monkeypatch.setattr(ensemble, "select_evidence", selection)
    connection = Mock()
    monkeypatch.setattr(db.connection, "get_connection", lambda: connection)
    result = cli.archive_current(["GJ-Gandhinagar"], p, now=ISSUED)
    connection.set_session.assert_called_once_with(readonly=True, autocommit=False)
    connection.close.assert_called_once()
    assert selection.call_args.kwargs["as_of"] == "2026-10-15"
    assert result["accuracy_evaluated"] is False
    assert len(result["archives"]) == 1
