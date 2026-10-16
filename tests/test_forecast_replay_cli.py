"""Candidate CLI is offline by default and cannot overwrite active artifacts."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tested_forecast_replay_cli", BASE/"scripts/evaluate_forecast_replay.py")
cli = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cli
_original_path = list(sys.path)
try:
    spec.loader.exec_module(cli)
finally:
    sys.path[:] = _original_path


def test_default_plan_does_not_load_model_data_or_protocol(monkeypatch):
    monkeypatch.setattr(cli, "_json", lambda *args: pytest.fail("Offline plan read a file."))
    monkeypatch.setattr(cli, "load_local_features", lambda *args: pytest.fail("Offline plan loaded features."))
    report = cli.main([])
    assert report["mode"] == "offline_plan"
    assert report["database_used"] is False
    assert report["network_used"] is False
    assert report["production_changes_made"] is False


def test_printed_protocol_example_parses_and_real_run_checks_fit_lower_bound(tmp_path, monkeypatch):
    import pandas as pd
    from models import climate_forecast as climate
    original_root = cli.ROOT
    uncertainty = _load_uncertainty(original_root)
    example = cli.main([])["protocol_example"]
    parsed = uncertainty.TemporalProtocol(**example)
    assert parsed.fit_start == "2002-01-01"
    protocol_file = tmp_path/"protocol.json"
    protocol_file.write_text(json.dumps(example), encoding="utf-8")
    # A model fits before calibration, but earlier available feature history
    # makes the declared fit lower bound incomplete: fail before forecasting.
    frame = pd.DataFrame({"date": pd.to_datetime(["2001-01-01"])})
    frame.attrs["feature_generation_id"] = "verified_generation"
    card = {"model_sha256": "verified_hash", "feature_generation_id": "verified_generation",
            "train_target_cutoff": "2010-12-31"}
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "_uncertainty_module", lambda: uncertainty)
    monkeypatch.setattr(cli, "load_local_features", lambda *args: frame)
    monkeypatch.setattr(climate, "load_bundle", lambda *args, **kwargs: (object(), card))
    with pytest.raises(ValueError, match="Fit window must include the feature-history start"):
        cli.main(["--run", "--protocol", str(protocol_file), "--output",
                  str(tmp_path/"reports/candidates/forecast_replay/unwritten.json")])
    assert not (tmp_path/"reports").exists()


def test_run_requires_explicit_protocol():
    with pytest.raises(SystemExit):
        cli.main(["--run"])


@pytest.mark.parametrize("relative", ["models/checkpoints/active.json", "data/processed/data.json",
    "reports/replay.json", "reports/candidates/forecast_replay/output.csv"])
def test_candidate_output_refuses_other_destinations(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        cli.candidate_output(tmp_path/relative)


def test_candidate_output_and_write_never_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    output = cli.candidate_output(tmp_path/"reports/candidates/forecast_replay/new.json")
    cli._write_new(output, {"candidate": True})
    assert json.loads(output.read_text())["candidate"] is True
    with pytest.raises(ValueError):
        cli.candidate_output(output)
    with pytest.raises(FileExistsError):
        cli._write_new(output, {"different": True})
    assert json.loads(output.read_text()) == {"candidate": True}


def test_zone_mapping_checks_duplicate_and_unknown_ids(tmp_path):
    zone = tmp_path/"zones.csv"
    zone.write_text("district_id,agro_climatic_zone\nA,Z\nB,Z\n", encoding="utf-8")
    assert cli.load_zones(zone, ["A", "B"]) == {"A": "Z", "B": "Z"}
    assert cli.load_zones(None, ["A"]) == {}
    zone.write_text("district_id,agro_climatic_zone\nA,Z\nA,Z\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cli.load_zones(zone, ["A"])
    zone.write_text("district_id,agro_climatic_zone\nUNKNOWN,Z\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cli.load_zones(zone, ["A"])


def test_empty_replay_can_be_reported_but_never_claims_coverage(tmp_path, monkeypatch):
    original_root = cli.ROOT
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "_uncertainty_module", lambda: _load_uncertainty(original_root))
    protocol = {"fit_start": "2002-01-01", "fit_end": "2010-12-31", "development_start": "2011-07-01", "development_end": "2011-12-31",
        "calibration_start": "2012-01-01", "calibration_end": "2012-12-31",
        "evaluation_start": "2013-01-01", "evaluation_end": "2013-12-31"}
    protocol_file, cases_file = tmp_path/"protocol.json", tmp_path/"cases.json"
    protocol_file.write_text(json.dumps(protocol), encoding="utf-8")
    cases_file.write_text(json.dumps({"version": "1.1-gap-source-zone-forecast-replay", "mode": "candidate_full_path_replay",
        "protocol": protocol, "model": {"model_sha256": "verified", "feature_generation_id": "fixture",
        "train_target_cutoff": "2010-12-31"}, "cases": []}), encoding="utf-8")
    result = cli.main(["--run", "--protocol", str(protocol_file), "--cases", str(cases_file),
        "--output", str(tmp_path/"reports/candidates/forecast_replay/intervals.json")])
    assert result["evaluation"]["empirical_coverage"] is None
    assert result["intervals"]["groups"] == {}
    assert result["intervals"]["current_period_uncertainty_established"] is False


def test_csv_cases_have_explicit_model_metadata_and_preserve_sparse_status(tmp_path, monkeypatch):
    import pandas as pd
    original_root = cli.ROOT
    uncertainty = _load_uncertainty(original_root)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "_uncertainty_module", lambda: uncertainty)
    protocol = cli.main([])["protocol_example"]
    parsed = uncertainty.TemporalProtocol(**protocol)
    metadata = {"model_sha256": "verified", "feature_generation_id": "fixture", "train_target_cutoff": "2010-12-31"}
    row = {"split": "calibration", "district_id": "A", "origin_date": "2014-01-01", "target_date": "2014-02-01",
        "horizon_months": 1, "requested_gap_months": 0, "last_observed_date": "2014-01-01",
        "groundwater_visible_through": "2014-01-01", "data_age_months": 0, "estimate_type": "district_level",
        "target_is_observed": True, "target_basis": "observed_district_depth", "actual_gwl_m_bgl": 5.,
        "predicted_gwl_m_bgl": 4., "model_sha256": "verified", "feature_generation_id": "fixture",
        "protocol_sha256": parsed.sha256}
    protocol_file, metadata_file, cases_file = tmp_path/"ranges.json", tmp_path/"model.json", tmp_path/"cases.csv"
    protocol_file.write_text(json.dumps(protocol), encoding="utf-8")
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
    pd.DataFrame([row]).to_csv(cases_file, index=False)
    result = cli.main(["--run", "--protocol", str(protocol_file), "--cases", str(cases_file),
        "--model-metadata", str(metadata_file), "--output", str(tmp_path/"reports/candidates/forecast_replay/csv.json")])
    assert result["intervals"]["calibration_cases"] == 1
    assert result["intervals"]["groups"]["h1|district_level|age_0"]["status"] == "uncertainty_not_established"
    assert result["evaluation"]["empirical_coverage"] is None


def _load_uncertainty(root):
    spec = importlib.util.spec_from_file_location("cli_uncertainty_fixture", root/"models/uncertainty.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
