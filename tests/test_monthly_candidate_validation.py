"""Candidate development work cannot train on the final period or publish."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts import validate_monthly_candidates as runner


def physical_frame(start="2006-01-01", end="2026-09-01", districts=("A", "B")):
    frames = []
    for index, district in enumerate(districts):
        dates = pd.date_range(start, end, freq="MS")
        frame = pd.DataFrame({
            "district_id": district, "date": dates,
            "gwl_current": 10 + index + np.arange(len(dates)) * .01,
            "rainfall_current": 30 + dates.month * 2.0,
            "temperature": 20 + dates.month * .4,
            "evapotranspiration": 40 + dates.month * 1.0,
            "is_observed": True, "is_imputed": False,
        })
        frame["gwl_lag_3mo"] = frame.gwl_current.shift(3)
        frame["gwl_lag_6mo"] = frame.gwl_current.shift(6)
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    result.attrs.update(feature_generation_id="verified-fixture-generation", data_source="observed_schema_fixture")
    return result


class Candidate:
    def __init__(self, fit_calls, **parameters):
        self.parameters = parameters
        self.fit_calls = fit_calls

    def fit(self, features, target):
        self.fit_calls.append((self.parameters.copy(), features.copy(), target.copy()))
        return self

    def predict(self, features):
        return np.zeros(len(features))

    def save_model(self, *args, **kwargs):
        pytest.fail("Development validation must never save or publish models")


def fake_components():
    fits, evaluations = [], []

    def factory(**parameters):
        return Candidate(fits, **parameters)

    def evaluator(model, frame, pairs):
        evaluations.append((frame.copy(), pairs.copy()))
        return {"status": "evaluated_assumed_weather", "n": len(pairs),
                "xgboost": {"rmse": 1.0}, "persistence": {"rmse": 1.1},
                "seasonal_paired": {"n": len(pairs), "baseline": {"rmse": .9}}}

    return factory, evaluator, fits, evaluations


def test_fixed_panel_folds_keep_target_cutoff_and_six_month_embargo():
    frame = runner.development_frame(physical_frame())
    pairs = runner.climate.prepare_pairs(frame)
    for fold in runner.FOLDS:
        training, evaluation = runner.fold_pairs(pairs, fold)
        assert len(training) and len(evaluation)
        assert training.target_date.max() <= pd.Timestamp(fold["train_target_cutoff"])
        assert evaluation.origin_date.min() == pd.Timestamp(fold["evaluation_origin_start"])
        assert evaluation.target_date.max() <= pd.Timestamp(fold["evaluation_target_end"])
        assert evaluation.target_date.max() < runner.FINAL_PERIOD_START
        earliest = (pd.Timestamp(fold["train_target_cutoff"]).to_period("M") + 7).to_timestamp()
        assert (evaluation.origin_date >= earliest).all()
        assert set(training.horizon_months) == set(range(1, 7))
        assert set(evaluation.horizon_months) == set(range(1, 7))
        assert not set(zip(training.district_id, training.origin_date, training.target_date)) & set(
            zip(evaluation.district_id, evaluation.origin_date, evaluation.target_date))


def test_final_period_removed_before_pair_builder_or_evaluator(monkeypatch):
    seen = []
    original = runner.climate.prepare_pairs

    def checked_pairs(frame):
        seen.append(frame.copy())
        assert frame.date.max() < runner.FINAL_PERIOD_START
        return original(frame)

    monkeypatch.setattr(runner.climate, "prepare_pairs", checked_pairs)
    factory, evaluator, fits, evaluations = fake_components()
    result = runner.validate_candidates(physical_frame(), model_factory=factory, evaluator=evaluator)
    assert len(seen) == 1
    assert len(fits) == len(evaluations) == 3
    assert result["development_end"] == "2019-12-01"
    for fold, (frame, pairs) in zip(runner.FOLDS, evaluations):
        assert frame.date.max() <= pd.Timestamp(fold["evaluation_target_end"])
        assert pairs.target_date.max() < runner.FINAL_PERIOD_START


def test_final_holdout_changes_do_not_change_training_inputs_cases_or_parameters():
    original = physical_frame()
    revised = original.copy()
    future = revised.date >= runner.FINAL_PERIOD_START
    revised.loc[future, ["gwl_current", "rainfall_current", "temperature", "evapotranspiration"]] = [9000, 90000, -90, 90000]
    revised.loc[future, "is_observed"] = False
    factory1, evaluator1, fits1, evaluations1 = fake_components()
    factory2, evaluator2, fits2, evaluations2 = fake_components()
    result1 = runner.validate_candidates(original, model_factory=factory1, evaluator=evaluator1)
    result2 = runner.validate_candidates(revised, model_factory=factory2, evaluator=evaluator2)
    assert result1["parameters"] == result2["parameters"]
    assert result1["development_pairs_sha256"] == result2["development_pairs_sha256"]
    for first, second in zip(fits1, fits2):
        assert first[0] == second[0]
        pd.testing.assert_frame_equal(first[1], second[1])
        pd.testing.assert_series_equal(first[2], second[2])
    for first, second in zip(evaluations1, evaluations2):
        pd.testing.assert_frame_equal(first[0], second[0])
        pd.testing.assert_frame_equal(first[1], second[1])
    for first, second in zip(result1["folds"], result2["folds"]):
        assert first["training_inputs_sha256"] == second["training_inputs_sha256"]
        assert first["evaluation_cases_sha256"] == second["evaluation_cases_sha256"]


def test_later_development_period_cannot_enter_an_earlier_fold_training_or_evaluation():
    first = physical_frame()
    changed = first.copy()
    changed.loc[changed.date >= "2014-01-01", ["gwl_current", "rainfall_current"]] = [5000., 1000.]
    factory1, evaluator1, fits1, evaluations1 = fake_components()
    factory2, evaluator2, fits2, evaluations2 = fake_components()
    runner.validate_candidates(first, fold="1", model_factory=factory1, evaluator=evaluator1)
    runner.validate_candidates(changed, fold="1", model_factory=factory2, evaluator=evaluator2)
    pd.testing.assert_frame_equal(fits1[0][1], fits2[0][1])
    pd.testing.assert_series_equal(fits1[0][2], fits2[0][2])
    pd.testing.assert_frame_equal(evaluations1[0][0], evaluations2[0][0])
    pd.testing.assert_frame_equal(evaluations1[0][1], evaluations2[0][1])


def test_missing_training_horizons_are_explicitly_skipped_without_fitting():
    frame = physical_frame()
    frame["is_observed"] = frame.date.dt.month.isin([1, 4, 7, 10])
    factory, evaluator, fits, evaluations = fake_components()
    result = runner.validate_candidates(frame, fold="1", model_factory=factory, evaluator=evaluator)
    fold = result["folds"][0]
    assert fold["status"] == "skipped"
    assert "missing_training_horizons" in fold["reasons"]
    assert fold["missing_training_horizons"] == [1, 2, 4, 5]
    assert fits == evaluations == []


def test_sparse_evaluation_is_reported_without_fitting():
    frame = physical_frame(end="2011-07-01")
    factory, evaluator, fits, evaluations = fake_components()
    result = runner.validate_candidates(frame, fold="1", model_factory=factory, evaluator=evaluator)
    assert result["folds"][0]["status"] == "skipped"
    assert "insufficient_evaluation_pairs" in result["folds"][0]["reasons"]
    assert fits == evaluations == []


def test_missing_weather_evaluation_is_unavailable_without_validity_claim():
    factory, _, fits, _ = fake_components()
    result = runner.validate_candidates(physical_frame(), fold="1", model_factory=factory,
                                        evaluator=lambda *args: {"status": "unavailable", "n": 0})
    assert len(fits) == 1
    assert result["folds"][0]["status"] == "unavailable"
    assert result["validation_assessment"]["sufficient_for_operational_use"] is False
    assert result["model_published"] is False
    assert result["production_changes_made"] is False


def test_model_parameters_are_resource_bounded_and_do_not_mutate_serving_defaults():
    before = runner.climate.PARAMETERS.copy()
    factory, evaluator, fits, _ = fake_components()
    report = runner.validate_candidates(physical_frame(), fold="2", trees=8,
                                        model_factory=factory, evaluator=evaluator)
    assert len(fits) == 1
    assert fits[0][0]["n_jobs"] == 1
    assert fits[0][0]["n_estimators"] == 8
    assert report["parameters"] == fits[0][0]
    assert runner.climate.PARAMETERS == before


@pytest.mark.parametrize("n_jobs,trees", [(0, 240), (5, 240), (True, 240), (1, 0), (1, 2001), (1, True)])
def test_unsafe_job_or_tree_counts_are_rejected(n_jobs, trees):
    with pytest.raises(ValueError):
        runner.model_parameters(n_jobs, trees)


def test_default_cli_prints_plan_without_loading_fitting_or_writing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "_load_verified_features", lambda: pytest.fail("Offline plan loaded features"))
    monkeypatch.setattr(runner, "_default_model", lambda **kwargs: pytest.fail("Offline plan constructed model"))
    assert runner.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "offline_plan"
    assert result["feature_loading_performed"] is False
    assert result["model_fitting_performed"] is False
    assert result["production_changes_made"] is False
    assert result["parameters"]["n_jobs"] == 1
    assert result["parameters"]["n_estimators"] == 240
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("relative", [
    "models/checkpoints/aquaiq_monthly_climate.json",
    "models/checkpoints/aquaiq_monthly_climate_model_card.json",
    "models/checkpoints/climate_bundles/candidate/model.json",
    "data/processed/features_matrix.csv",
    "data/processed/feature_manifest.json",
    "reports/climate_forecast_evaluation.json",
    "reports/candidates/monthly_validation/results.csv",
    "reports/candidates/monthly_validation/../escaped.json",
])
def test_outputs_cannot_replace_active_assets_data_or_training_reports(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="protected"):
        runner.candidate_output(tmp_path / relative)


def test_explicit_run_writes_only_experimental_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "_load_verified_features", physical_frame)
    factory, evaluator, fits, _ = fake_components()
    monkeypatch.setattr(runner, "_default_model", factory)
    monkeypatch.setattr(runner.climate, "evaluate_assumed_weather", evaluator)
    monkeypatch.setattr(runner.climate, "publish_bundle", lambda *args, **kwargs: pytest.fail("Published candidate"))
    result = runner.main(["--run", "--fold", "1", "--trees", "8"])
    assert result == 0
    assert len(fits) == 1
    files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert len(files) == 1
    assert files[0].name == "development_evaluation.json"
    report = json.loads(files[0].read_text())
    assert report["mode"] == "development_only"
    assert report["model_published"] is False
    assert report["folds"][0]["status"] == "evaluated_development"
    assert json.loads(capsys.readouterr().out)["model_published"] is False


def test_missing_local_csv_never_invokes_shared_loader_or_database(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.source_model, "ROOT", tmp_path)
    monkeypatch.setattr(runner.source_model, "CONFIG", {"paths": {"data_processed": "data/processed"}})
    monkeypatch.setattr(runner, "load_feature_matrix", lambda: pytest.fail("Attempted loader/database fallback"))
    with pytest.raises(ValueError, match="database fallback is disabled"):
        runner._load_verified_features()


def test_real_feature_provenance_is_required_before_training():
    frame = physical_frame()
    frame.attrs["data_source"] = "synthetic"
    factory, evaluator, fits, _ = fake_components()
    with pytest.raises(ValueError, match="verified real"):
        runner.validate_candidates(frame, model_factory=factory, evaluator=evaluator)
    assert fits == []


def test_case_export_matches_existing_evaluator_and_ignores_realized_future_weather():
    frame = runner.development_frame(physical_frame(end="2013-12-01", districts=("A",)))
    pairs = runner.climate.prepare_pairs(frame)
    pairs = pairs.loc[pairs.origin_date == pd.Timestamp("2012-01-01")].copy()
    model = Candidate([])
    summary = runner.climate.evaluate_assumed_weather(model, frame, pairs)
    records = runner.assumed_weather_cases(model, frame, pairs, 1)
    assert len(records) == summary["n"] == 6
    assert all(record["split"] == "development_evaluation" for record in records)
    assert all(record["target_date"] < "2020-01-01" for record in records)
    revised = frame.copy()
    revised.loc[revised.date > "2012-01-01", ["rainfall_current", "temperature", "evapotranspiration"]] = [99999., 60., 99999.]
    assert runner.assumed_weather_cases(model, revised, pairs, 1) == records
