"""Observed calendar labels, verified climate models, and weather-dependent curves."""
import json
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from models import climate_forecast as climate


def physical_frame(start="2010-01-01", end="2024-12-01", observed_end="2021-01-01"):
    dates = pd.date_range(start, end, freq="MS")
    elapsed = np.arange(len(dates), dtype=float)
    groundwater = 20 + elapsed * .02 + 2 * np.sin(dates.month * 2 * np.pi / 12)
    observed = dates <= pd.Timestamp(observed_end)
    frame = pd.DataFrame({
        "district_id": "fixture-district", "date": dates,
        "gwl_current": np.where(observed, groundwater, np.nan),
        "rainfall_current": 30 + dates.month * 10.0,
        "temperature": 15 + dates.month * .8,
        "evapotranspiration": 35 + dates.month * 2.0,
        "is_observed": observed, "is_imputed": False,
    })
    frame["gwl_lag_3mo"] = frame.gwl_current.shift(3)
    frame["gwl_lag_6mo"] = frame.gwl_current.shift(6)
    frame.attrs.update(feature_generation_id="fixture-physical-generation", data_source="observed_schema_fixture")
    return frame


def serving_evidence(frame=None, as_of="2026-10-13"):
    frame = physical_frame() if frame is None else frame
    return {
        "district_id": "fixture-district", "as_of": pd.Timestamp(as_of),
        "origin": pd.Timestamp("2021-01-01"), "generation": "fixture-physical-generation",
        "estimate_type": "district_level", "zone": None, "reason": None,
        "frame": frame, "history": frame.copy(),
    }


def model_card():
    return {
        "version": climate.MODEL_VERSION, "features": climate.FEATURES,
        "feature_schema_sha256": climate._json_hash(climate.FEATURES),
        "units": climate.UNITS, "target": "gwl_change_from_origin",
        "horizons_months": [1, 2, 3, 4, 5, 6],
        "feature_generation_id": "fixture-physical-generation",
        "data_source": "observed_schema_fixture", "train_target_cutoff": "2019-12-31",
        "max_train_target_date": "2019-12-01",
        "validation_assessment": {"status": "unvalidated_current_projection", "sufficient_for_operational_use": False},
        "model_sha256": "fixture-sha",
    }


@pytest.fixture(autouse=True)
def reset_bundle_cache():
    climate._CACHE.clear()
    yield
    climate._CACHE.clear()


@pytest.fixture(scope="module")
def tiny_model():
    random = np.random.default_rng(42)
    values = pd.DataFrame(random.uniform(.1, 100, (180, len(climate.FEATURES))), columns=climate.FEATURES)
    delta = -.02 * values.cumulative_rainfall + .03 * values.cumulative_evapotranspiration + .04 * values.mean_temperature
    model = xgb.XGBRegressor(n_estimators=18, max_depth=2, min_child_weight=1, n_jobs=1, random_state=42)
    model.fit(values, delta)
    return model


def test_pairs_use_exact_calendar_months_and_complete_intermediate_weather():
    frame = physical_frame("2018-01-01", "2020-12-01", "2020-12-01")
    # Removing March must not turn January -> April into a two-row target.
    frame = frame.loc[frame.date != pd.Timestamp("2018-03-01")]
    pairs = climate.prepare_pairs(frame)
    january = pairs.loc[pairs.origin_date == "2018-01-01"]
    assert list(january.horizon_months) == [1.0]
    assert january.iloc[0].target_date == pd.Timestamp("2018-02-01")
    elapsed_months = pairs.target_date.dt.to_period("M").astype("int64") - pairs.origin_date.dt.to_period("M").astype("int64")
    assert (elapsed_months == pairs.horizon_months).all()
    assert (pairs.target_delta == pairs.actual_gwl - pairs.origin_gwl).all()
    assert set(pairs.horizon_months) == set(range(1, 7))


@pytest.mark.parametrize("flag", [False, None, "False"])
def test_unobserved_or_unknown_values_cannot_be_origins_or_labels(flag):
    frame = physical_frame("2018-01-01", "2020-12-01", "2020-12-01")
    frame["is_observed"] = frame.is_observed.astype(object)
    unavailable = pd.Timestamp("2019-01-01")
    frame.loc[frame.date == unavailable, "is_observed"] = flag
    frame.loc[frame.date == unavailable, "is_imputed"] = flag is False
    frame.loc[frame.date == unavailable, "gwl_current"] = 900.0
    pairs = climate.prepare_pairs(frame)
    assert not (pairs.origin_date == unavailable).any()
    assert not (pairs.target_date == unavailable).any()
    assert not (pairs.origin_gwl == 900).any()
    assert not (pairs.actual_gwl == 900).any()


@pytest.mark.parametrize("field,value", [("rainfall_current", np.nan), ("temperature", np.inf), ("evapotranspiration", -1.0)])
def test_invalid_intermediate_weather_excludes_longer_pairs(field, value):
    frame = physical_frame("2018-01-01", "2020-12-01", "2020-12-01")
    frame.loc[frame.date == "2018-03-01", field] = value
    pairs = climate.prepare_pairs(frame)
    january = pairs.loc[pairs.origin_date == "2018-01-01"]
    assert list(january.horizon_months) == [1.0]


def test_duplicate_district_months_are_rejected_before_training():
    frame = physical_frame()
    with pytest.raises(ValueError, match="Duplicate"):
        climate.prepare_pairs(pd.concat([frame, frame.iloc[:1]]))


def test_training_and_holdout_are_separated_by_target_date_and_six_month_embargo():
    pairs = climate.prepare_pairs(physical_frame("2016-01-01", "2022-12-01", "2022-12-01"))
    train, heldout = climate.split_pairs(pairs, "2019-12-31")
    assert set(train.horizon_months) == set(range(1, 7))
    assert set(heldout.horizon_months) == set(range(1, 7))
    assert train.target_date.max() == pd.Timestamp("2019-12-01")
    assert heldout.origin_date.min() == pd.Timestamp("2020-07-01")
    for horizon in range(1, 7):
        latest_origin = train.loc[train.horizon_months == horizon].origin_date.max()
        assert latest_origin + pd.DateOffset(months=horizon) <= pd.Timestamp("2019-12-31")
    assert not set(zip(train.origin_date, train.target_date)) & set(zip(heldout.origin_date, heldout.target_date))


def test_real_xgboost_round_trip_preserves_named_feature_order_and_predictions(tmp_path, tiny_model):
    checkpoint = tmp_path / "monthly.json"
    card = climate.publish_bundle(tiny_model, model_card(), checkpoint)
    loaded, loaded_card = climate.load_bundle(checkpoint, "fixture-physical-generation")
    values = pd.DataFrame(np.ones((2, len(climate.FEATURES))), columns=climate.FEATURES)
    assert loaded.get_booster().feature_names == climate.FEATURES
    np.testing.assert_allclose(loaded.predict(values), tiny_model.predict(values))
    assert loaded_card == card
    assert climate.load_bundle(checkpoint, "fixture-physical-generation")[0] is loaded
    with pytest.raises(RuntimeError, match="incompatible"):
        climate.load_bundle(checkpoint, "a-different-generation")


@pytest.mark.parametrize("asset", ["card_path", "model_path"])
def test_cached_bundle_cannot_ignore_changed_asset_checksums(tmp_path, tiny_model, asset):
    checkpoint = tmp_path / "monthly.json"
    climate.publish_bundle(tiny_model, model_card(), checkpoint)
    climate.load_bundle(checkpoint, "fixture-physical-generation")
    pointer = json.loads(checkpoint.read_text())
    path = checkpoint.parent / pointer[asset]
    path.write_text(path.read_text() + "\n tampered", encoding="utf-8")
    with pytest.raises(RuntimeError, match="incompatible"):
        climate.load_bundle(checkpoint, "fixture-physical-generation")


@pytest.mark.parametrize("field,value", [
    ("version", "old-version"), ("features", ["incorrect"]),
    ("units", {"gwl": "feet"}), ("horizons_months", [6]),
    ("data_source", "synthetic"), ("feature_generation_id", ""),
    ("max_train_target_date", "2020-01-01"),
])
def test_rehashed_card_with_wrong_contract_still_fails(tmp_path, tiny_model, field, value):
    checkpoint = tmp_path / "monthly.json"
    climate.publish_bundle(tiny_model, model_card(), checkpoint)
    pointer = json.loads(checkpoint.read_text())
    path = checkpoint.parent / pointer["card_path"]
    card = json.loads(path.read_text())
    card[field] = value
    path.write_text(json.dumps(card), encoding="utf-8")
    pointer["card_sha256"] = climate.sha256_file(path)
    checkpoint.write_text(json.dumps(pointer), encoding="utf-8")
    with pytest.raises(RuntimeError, match="incompatible"):
        climate.load_bundle(checkpoint, "fixture-physical-generation")


def test_tiny_training_publishes_all_six_horizons_with_origin_available_evaluation(tmp_path):
    frame = physical_frame("2010-01-01", "2017-01-01", "2017-01-01")
    _, card = climate.train(frame, "2015-12-31", tmp_path / "trained.json", {
        "n_estimators": 8, "max_depth": 2, "min_child_weight": 1, "n_jobs": 1,
    })
    assert set(card["training_counts_by_horizon"]) == {str(h) for h in range(1, 7)}
    assert card["max_train_target_date"] <= card["train_target_cutoff"]
    assert card["evaluation"]["status"] == "evaluated_assumed_weather"
    assert card["evaluation"]["n"] == 21
    assert card["evaluation_protocol"]["embargo_months"] == 6
    assert card["validation_assessment"]["sufficient_for_operational_use"] is False


def test_holdout_uses_origin_available_weather_instead_of_realized_future_weather():
    frame = physical_frame("2010-01-01", "2020-12-01", "2020-12-01")
    labels = climate.prepare_pairs(frame)
    labels = labels.loc[labels.origin_date == pd.Timestamp("2016-01-01")]
    model = weather_predictor()
    baseline = climate.evaluate_assumed_weather(model, frame, labels)
    first_inputs = model.predict.call_args.args[0].copy()
    revised = frame.copy()
    revised.loc[revised.date > "2016-01-01", ["rainfall_current", "temperature", "evapotranspiration"]] = [99999., 65., 99999.]
    result = climate.evaluate_assumed_weather(model, revised, labels)
    pd.testing.assert_frame_equal(model.predict.call_args.args[0], first_inputs)
    assert result == baseline
    assert result["n"] == 6


def weather_predictor():
    model = Mock()
    model.predict.side_effect = lambda rows: (
        -.001 * rows.cumulative_rainfall + .005 * rows.cumulative_evapotranspiration
        + .02 * rows.mean_temperature
    ).to_numpy()
    return model


def install_serving_model(monkeypatch, model=None, card=None):
    model = weather_predictor() if model is None else model
    card = model_card() if card is None else card
    loader = Mock(return_value=(model, card))
    monkeypatch.setattr(climate, "load_bundle", loader)
    return model, loader


def test_six_current_future_months_include_weather_values_and_stale_source_provenance(monkeypatch):
    model, loader = install_serving_model(monkeypatch)
    result = climate.forecast_from_evidence(serving_evidence())
    assert [row["month"] for row in result["forecast"]] == ["2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04"]
    assert result["forecast_origin"] == "2026-10-13"
    assert result["last_observed_date"] == "2021-01-01"
    assert result["data_age_months"] == 69
    assert result["current_depth_basis"] == "estimated_from_historical_groundwater"
    assert result["weather_basis"]["method"] == "historical_monthly_climatology"
    assert result["weather_basis"]["last_observed_weather_date"] == "2024-12-01"
    assert result["weather_basis"]["future_weather_is_observed"] is False
    assert result["model_validation"]["sufficient_for_operational_use"] is False
    assert set(result["forecast"][0]["weather"]) == {"rainfall_mm", "temperature_c", "evapotranspiration_mm"}
    assert list(model.predict.call_args.args[0].columns) == climate.FEATURES
    loader.assert_called_once_with(expected_generation="fixture-physical-generation")
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field,delta", [("rainfall", 100.), ("temperature", 5.), ("evapotranspiration", 40.)])
def test_weather_scenarios_change_the_plotted_predictions(monkeypatch, field, delta):
    install_serving_model(monkeypatch)
    evidence = serving_evidence()
    baseline = climate.forecast_from_evidence(evidence)
    path = pd.DataFrame({"date": [point["date"] for point in baseline["forecast"]],
                         "rainfall": [point["weather"]["rainfall_mm"] for point in baseline["forecast"]],
                         "temperature": [point["weather"]["temperature_c"] for point in baseline["forecast"]],
                         "evapotranspiration": [point["weather"]["evapotranspiration_mm"] for point in baseline["forecast"]]})
    path[field] += delta
    changed = climate.forecast_from_evidence(evidence, weather_override=path)
    assert changed["weather_basis"]["method"] == "specified_weather_scenario"
    before = np.array([point["predicted_gwl"] for point in baseline["forecast"]])
    after = np.array([point["predicted_gwl"] for point in changed["forecast"]])
    assert np.all(after != before)
    assert changed["estimated_current_gwl"] == baseline["estimated_current_gwl"]


def test_imputed_completed_current_depth_is_not_passed_off_as_observed(monkeypatch):
    model, _ = install_serving_model(monkeypatch)
    frame = physical_frame()
    artificial = frame.iloc[-1:].copy()
    artificial["date"] = pd.Timestamp("2025-01-01")
    artificial["gwl_current"] = 900.0
    artificial["is_observed"], artificial["is_imputed"] = False, True
    frame = pd.concat([frame, artificial], ignore_index=True)
    evidence = serving_evidence(frame, "2025-01-31")
    result = climate.forecast_from_evidence(evidence)
    fit = climate.fit_projection(evidence["history"], pd.Timestamp("2025-01-31"))
    expected_current = climate.predict_depth(fit, [pd.Timestamp("2025-01-01")])[0]
    assert result["estimated_current_gwl"] == pytest.approx(expected_current, abs=.0001)
    assert result["current_depth_basis"] == "estimated_from_historical_groundwater"
    assert model.predict.call_args.args[0].iloc[0].origin_gwl != 900.0


def test_completed_current_observation_is_preserved_without_an_inferred_anchor(monkeypatch):
    model, _ = install_serving_model(monkeypatch)
    evidence = serving_evidence(as_of="2021-01-31")
    result = climate.forecast_from_evidence(evidence)
    measured = evidence["frame"].loc[evidence["frame"].date == "2021-01-01", "gwl_current"].iloc[0]
    assert result["current_depth_basis"] == "observed_month"
    assert result["estimated_current_gwl"] == pytest.approx(measured, abs=.0001)
    assert model.predict.call_args.args[0].iloc[0].origin_gwl == measured


def test_incomplete_future_weather_returns_no_curve_and_never_predicts(monkeypatch):
    model, _ = install_serving_model(monkeypatch)
    frame = physical_frame()
    frame.loc[frame.date.dt.month == 11, "evapotranspiration"] = np.nan
    result = climate.forecast_from_evidence(serving_evidence(frame))
    assert result["status"] == "insufficient_data"
    assert result["forecast"] == [] and result["estimated_current_gwl"] is None
    assert result["weather_basis"]["missing_inputs"][0]["field"] == "evapotranspiration"
    model.predict.assert_not_called()


def test_hindsight_checkpoint_does_not_produce_a_retrospective_curve(monkeypatch):
    model, _ = install_serving_model(monkeypatch, card={**model_card(), "train_target_cutoff": "2025-12-31"})
    result = climate.forecast_from_evidence(serving_evidence(as_of="2025-01-31"))
    assert result["status"] == "insufficient_data" and result["forecast"] == []
    model.predict.assert_not_called()


@pytest.mark.parametrize("bad_prediction", [[np.nan] * 6, [1.] * 5, [np.inf] * 6])
def test_invalid_model_outputs_cannot_become_a_plotted_curve(monkeypatch, bad_prediction):
    model = Mock()
    model.predict.return_value = bad_prediction
    install_serving_model(monkeypatch, model)
    with pytest.raises(RuntimeError, match="invalid depth changes"):
        climate.forecast_from_evidence(serving_evidence())


def test_health_fails_if_monthly_climate_bundle_is_corrupt(monkeypatch):
    from api.app import create_app
    from api.routes import health
    connection = Mock()
    connection.cursor.return_value.__enter__ = Mock(return_value=Mock())
    connection.cursor.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(health, "get_connection", lambda: connection)
    monkeypatch.setattr(health, "feature_generation", lambda: "fixture-physical-generation")
    monkeypatch.setattr(health, "load_model_bundle", Mock(return_value=(Mock(), {})))
    monkeypatch.setattr(health, "load_climate_bundle", Mock(side_effect=RuntimeError("Corrupt monthly climate card")))
    result = create_app({"TESTING": True}).test_client().get("/api/health")
    assert result.status_code == 503
    assert result.json["database"] == "connected"
    assert result.json["model_loaded"] is True
    assert result.json["monthly_climate_model_loaded"] is False
    connection.close.assert_called_once()


def test_pipeline_training_dispatches_both_models_and_honours_dry_run(monkeypatch):
    from models import xgboost_model
    from scripts import run_pipeline
    calls = []
    monkeypatch.setattr(xgboost_model, "main", lambda args: calls.append(("endpoint", args)))
    monkeypatch.setattr(climate, "main", lambda args: calls.append(("monthly_climate", args)))
    assert run_pipeline.step_train(dry_run=True)
    assert calls == []
    assert run_pipeline.step_train()
    assert calls == [("endpoint", []), ("monthly_climate", [])]
