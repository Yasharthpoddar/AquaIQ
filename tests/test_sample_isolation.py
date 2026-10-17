"""Smoke and candidate runs must never replace the active feature generation."""
import hashlib
import json

import pandas as pd
import pytest

from preprocessing import features, pipeline
from models import xgboost_model


def _snapshot(directory):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.iterdir() if path.is_file()}


@pytest.fixture
def isolated_project(tmp_path, monkeypatch):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    dates = pd.date_range("2002-01-01", periods=4, freq="MS")
    frame = pd.DataFrame([
        {"district_id": district, "date": month, "gwl": 8.0,
         "rainfall": 100.0, "temperature": 25.0, "evapotranspiration": 90.0,
         "is_observed": True, "is_imputed": False, "months_since_observation": 0,
         "feature_generation": "physical-v3-causal-monthly-fixture"}
        for district in ("RJ-Jaipur", "RJ-Ajmer") for month in dates
    ])
    path = processed / "preprocessed_wide.csv"
    frame.to_csv(path, index=False)
    manifest = {
        "generation_id": "physical-v3-causal-monthly-fixture",
        "preprocessed_csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "causal_preprocessing": True, "units": xgboost_model.FEATURE_UNITS,
        "date_start": "2002-01-01", "date_end": "2002-04-01", "sample_only": False,
    }
    (processed / "preprocessed_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (processed / "features_matrix.csv").write_text("active feature CSV", encoding="utf-8")
    (processed / "feature_manifest.json").write_text("active manifest", encoding="utf-8")
    for module in (pipeline, features):
        monkeypatch.setattr(module, "ROOT", tmp_path)
        monkeypatch.setattr(module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(features, "load_prior_rainfall_history", lambda: None)
    raw = pd.DataFrame([
        {"district_id": row.district_id, "date": row.date,
         "source": source, "metric": metric, "value": getattr(row, column)}
        for row in frame.itertuples(index=False)
        for source, metric, column in (("CGWB", "GWL", "gwl"), ("IMD", "rainfall", "rainfall"),
                                      ("ERA5", "temperature", "temperature"),
                                      ("ERA5", "evapotranspiration", "evapotranspiration"))
    ])
    monkeypatch.setattr(pipeline, "load_raw_data", lambda: raw.copy())
    writes = []
    monkeypatch.setattr(features, "write_to_db", lambda data: writes.append(data.copy()))
    return tmp_path, processed, writes


def test_sample_preprocessing_then_explicit_features_preserves_production(isolated_project):
    root, processed, writes = isolated_project
    before = _snapshot(processed)
    pipeline.main(["--sample", "1"])
    samples = root / "reports" / "samples"
    assert _snapshot(processed) == before
    assert json.loads((samples / "preprocessed_manifest.json").read_text())["sample_only"] is True
    features.main(["--input-dir", str(samples)])
    assert _snapshot(processed) == before
    assert not writes
    output = pd.read_csv(samples / "features_matrix.csv")
    assert output.district_id.nunique() == 1
    assert json.loads((samples / "feature_manifest.json").read_text())["sample_only"] is True


@pytest.mark.parametrize("args, directory, expected_districts", [
    (["--sample", "1"], "samples", 1),
    (["--csv-only"], "candidates", 2),
])
def test_feature_inspection_commands_preserve_production(isolated_project, args, directory, expected_districts):
    root, processed, writes = isolated_project
    before = _snapshot(processed)
    features.main(args)
    assert _snapshot(processed) == before
    assert not writes
    output = pd.read_csv(root / "reports" / directory / "features_matrix.csv")
    assert output.district_id.nunique() == expected_districts


def test_default_features_still_publish_full_generation(isolated_project):
    _, processed, writes = isolated_project
    features.main([])
    assert len(writes) == 1
    assert writes[0].district_id.nunique() == 2
    assert json.loads((processed / "feature_manifest.json").read_text())["sample_only"] is False


def test_failed_database_publish_preserves_active_feature_files(isolated_project, monkeypatch):
    _, processed, _ = isolated_project
    before = _snapshot(processed)
    def reject_generation(frame):
        raise RuntimeError("database rejected generation")
    monkeypatch.setattr(features, "write_to_db", reject_generation)
    with pytest.raises(RuntimeError, match="database rejected"):
        features.main([])
    assert _snapshot(processed) == before
    assert not list(processed.glob(".features-*"))


def test_production_validation_refuses_sample_artifacts():
    with pytest.raises(ValueError, match="Sample-only"):
        xgboost_model.validate_feature_generation(pd.DataFrame(), {"sample_only": True})


def test_production_loader_refuses_a_verified_sample_csv(isolated_project, monkeypatch):
    root, _, _ = isolated_project
    features.main(["--sample", "1"])
    monkeypatch.setattr(xgboost_model, "ROOT", root)
    config = {**xgboost_model.CONFIG, "paths": {**xgboost_model.CONFIG["paths"], "data_processed": "reports/samples"}}
    monkeypatch.setattr(xgboost_model, "CONFIG", config)
    with pytest.raises(ValueError, match="Sample-only"):
        xgboost_model.load_feature_matrix()


@pytest.mark.parametrize("module", [pipeline, features])
@pytest.mark.parametrize("count", ["0", "-1"])
def test_invalid_sample_size_fails_before_replacing_artifacts(isolated_project, module, count):
    _, processed, writes = isolated_project
    before = _snapshot(processed)
    with pytest.raises(SystemExit):
        module.main(["--sample", count])
    assert _snapshot(processed) == before
    assert not writes
