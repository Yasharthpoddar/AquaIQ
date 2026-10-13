"""Regression checks for leakage, provenance, data identity and artifact ownership."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models import backtest
from models import xgboost_model as forecast
from models import xgboost_gridsearch as gridsearch


def monthly_features(start="2002-01-01", periods=270):
    dates = pd.date_range(start, periods=periods, freq="MS")
    depth = 8 + np.arange(periods) * .01 + np.sin(np.arange(periods) * 2 * np.pi / 12)
    data = {"district_id": "RJ-Jaipur", "date": dates, "gwl_current": depth,
            "gwl_lag_3mo": pd.Series(depth).shift(3), "gwl_lag_6mo": pd.Series(depth).shift(6),
            "rainfall_current": 100., "rainfall_3mo_avg": 100., "monsoon_deficit_pct": -10.,
            "temperature": 25., "evapotranspiration": 90., "water_balance_proxy": 10.,
            "crop_season_flag": ["Kharif" if 6 <= date.month <= 10 else "Rabi" if date.month >= 11 or date.month <= 3 else "Zaid" for date in dates],
            "is_observed": True, "is_imputed": False, "feature_generation": "physical-v3-fixture"}
    df = pd.DataFrame(data)
    df.attrs.update(feature_generation_id="physical-v3-fixture", data_source="verified fixture", data_sha256="fixture-hash")
    return df


def test_exact_calendar_targets_survive_missing_months():
    df = monthly_features(periods=24)
    df = df[df.date != pd.Timestamp("2002-03-01")]
    prepared = forecast.create_target(df)
    january = prepared.loc[prepared.date == pd.Timestamp("2002-01-01")].iloc[0]
    expected = df.loc[df.date == pd.Timestamp("2002-07-01"), "gwl_current"].iloc[0]
    assert january.target_date == pd.Timestamp("2002-07-01")
    assert january.target_gwl_6mo == pytest.approx(expected)
    # Missing March makes September's seasonal baseline unknown, not February.
    september = prepared.loc[prepared.date == pd.Timestamp("2002-09-01")].iloc[0]
    assert np.isnan(september.seasonal_naive_6mo)


def test_unknown_or_imputed_labels_are_never_observed():
    df = monthly_features(periods=24)
    df["is_observed"] = df["is_observed"].astype(object)
    df.loc[df.date == pd.Timestamp("2002-07-01"), "is_observed"] = None
    df.loc[df.date == pd.Timestamp("2002-08-01"), ["is_observed", "is_imputed"]] = [False, True]
    prepared = forecast.create_target(df)
    assert not prepared.loc[prepared.date.isin(pd.to_datetime(["2002-01-01", "2002-02-01"])), "target_is_observed"].any()
    assert not forecast.observed_mask(df.drop(columns=["is_observed", "is_imputed"])).any()
    assert forecast.observed_mask(pd.DataFrame({"is_imputed": ["False", "True", None]})).tolist() == [True, False, False]


def test_train_labels_are_available_before_true_origin_embargo():
    df = forecast.create_target(monthly_features())
    train, test = forecast.temporal_split(df, "2013-06-30", "2014-01-01", "2015-12-31")
    assert train.target_date.max() <= pd.Timestamp("2013-06-30")
    assert train.date.max() <= pd.Timestamp("2012-12-01")
    assert test.date.min() >= pd.Timestamp("2014-01-01")
    assert train.target_date.max() < test.date.min()
    with pytest.raises(ValueError, match="embargo"):
        forecast.temporal_split(df, "2013-06-30", "2013-07-01", "2014-12-31")


def test_generation_rejects_mixed_units_unknown_provenance_and_stale_rows():
    df = monthly_features(periods=24)
    manifest = {"units": forecast.FEATURE_UNITS, "causal_preprocessing": True,
                "generation_id": "physical-v3-fixture", "date_start": "2002-01-01", "date_end": "2024-12-31"}
    assert forecast.validate_feature_generation(df, manifest) == "physical-v3-fixture"
    bad = df.copy()
    bad.loc[0, "feature_generation"] = "legacy-normalized"
    with pytest.raises(ValueError, match="mixed"):
        forecast.validate_feature_generation(bad, manifest)
    bad = df.copy()
    bad.loc[0, "date"] = pd.Timestamp("1996-01-01")
    with pytest.raises(ValueError, match="range"):
        forecast.validate_feature_generation(bad, manifest)
    with pytest.raises(ValueError, match="physical-unit"):
        forecast.validate_feature_generation(df, {**manifest, "units": {**forecast.FEATURE_UNITS, "evapotranspiration": "mm/day"}})


def test_same_sample_baseline_comparison():
    prepared = forecast.create_target(forecast.encode_crop_season(monthly_features(periods=24)))
    prepared.loc[prepared.index[1:], "seasonal_naive_6mo"] = np.nan
    prepared.loc[prepared.index[0], "seasonal_naive_6mo"] = prepared.iloc[0].target_gwl_6mo
    class Predictor:
        def predict(self, frame):
            return frame.gwl_current.to_numpy()
    result = forecast.evaluate_model(Predictor(), prepared, forecast.CANONICAL_FEATURE_COLS)
    paired = result["seasonal_comparison"]
    assert paired["n"] == 1
    assert {paired[key]["n"] for key in ["xgboost", "persistence_baseline", "seasonal_naive_baseline"]} == {1}
    json.dumps(result, allow_nan=False)


def test_production_bundle_and_eval_use_matching_cutoff(monkeypatch, tmp_path):
    monkeypatch.setattr(forecast, "XGB_PARAMS", {"n_estimators": 3, "max_depth": 2, "random_state": 42})
    prepared = forecast.create_target(forecast.encode_crop_season(monthly_features()))
    checkpoint = tmp_path / "aquaiq_xgb.json"
    _, card = forecast.train_production_model(prepared, forecast.CANONICAL_FEATURE_COLS, "2019-12-31", checkpoint_path=checkpoint)
    model, loaded = forecast.load_model_bundle(checkpoint, "physical-v3-fixture")
    assert loaded["bundle_id"] == card["bundle_id"]
    assert loaded["max_train_target_date"] <= "2019-12-31"
    evaluation = forecast.evaluate_saved_checkpoint(prepared, checkpoint)
    assert evaluation["evaluation"]["origin_start"] >= "2022-07-01"
    assert evaluation["evaluation"]["target_start"] >= "2023-01-01"
    with pytest.raises(ValueError, match="different feature generation"):
        forecast.load_model_bundle(checkpoint, "different-generation")
    pointer = json.loads(checkpoint.read_text())
    card_path = checkpoint.parent / pointer["card_path"]
    card_path.write_text(card_path.read_text() + " ")
    with pytest.raises(ValueError, match="checksum"):
        forecast.load_model_bundle(checkpoint)


def test_unverified_checkpoint_and_synthetic_training_cannot_publish(tmp_path):
    checkpoint = tmp_path / "aquaiq_xgb.json"
    checkpoint.write_text('{"learner": {}}')
    with pytest.raises(ValueError, match="Legacy"):
        forecast.load_model_bundle(checkpoint)
    data = forecast.create_target(forecast.encode_crop_season(monthly_features()))
    data.attrs["data_source"] = "synthetic"
    with pytest.raises(ValueError, match="verified real"):
        forecast.train_production_model(data, forecast.CANONICAL_FEATURE_COLS, checkpoint_path=checkpoint)
    assert checkpoint.read_text() == '{"learner": {}}'


def test_grid_search_cannot_use_final_test_or_unavailable_train_labels():
    train, val, _ = gridsearch.prepare_data(monthly_features())
    assert train.target_date.max() <= pd.Timestamp("2019-12-31")
    assert val.date.min() >= pd.Timestamp("2020-07-01")
    assert val.target_date.max() < pd.Timestamp("2023-01-01")


def test_backtest_without_actual_predictions_retains_uncalibrated_initial_weights():
    data = monthly_features(periods=180)
    assert backtest._compute_component_scores(data).empty
    assert backtest.fit_ensemble_weights(data) == backtest._normalized_initial()


def test_backtest_reports_are_isolated_from_production(monkeypatch, tmp_path):
    monkeypatch.setattr(backtest, "ROOT", tmp_path)
    checkpoint = tmp_path / "models" / "checkpoints" / "aquaiq_xgb.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("production sentinel")
    config = tmp_path / "config.yaml"
    config.write_text("config sentinel")
    backtest.save_to_config(backtest._normalized_initial(), [], "synthetic")
    assert checkpoint.read_text() == "production sentinel"
    assert config.read_text() == "config sentinel"
    assert (tmp_path / "reports" / "synthetic_backtest_smoke.json").exists()
    assert not (tmp_path / "reports" / "backtest_results.json").exists()
    assert backtest.should_write_config("verified real features") is False


def test_causal_calibration_records_actual_fitted_predictions(monkeypatch):
    fitted = []
    class Predictor:
        def fit(self, X, y):
            fitted.append(len(y))
        def predict(self, X):
            return np.full(len(X), 12.345)
    monkeypatch.setattr(forecast, "new_model", lambda params=None: Predictor())
    result = backtest.causal_calibration_predictions(monthly_features(), years=[2015])
    selected = result[result.predicted_gwl_6mo.notna()]
    assert fitted and not selected.empty
    assert (selected.predicted_gwl_6mo == 12.345).all()
    assert (selected.prediction_train_target_cutoff == pd.Timestamp("2014-06-30")).all()
    assert (selected.date >= pd.Timestamp("2015-01-01")).all()
