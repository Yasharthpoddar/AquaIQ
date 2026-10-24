"""Tests for twelve-month climate-conditioned XGBoost forecasting pipeline."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from models import climate_forecast_12m as climate12m
from models import climate_forecast as climate6m
from api.app import create_app


def physical_frame(start="2010-01-01", end="2024-12-01", observed_end="2021-01-01"):
    dates = pd.date_range(start, end, freq="MS")
    elapsed = np.arange(len(dates), dtype=float)
    groundwater = 20 + elapsed * .02 + 2 * np.sin(dates.month * 2 * np.pi / 12)
    observed = dates <= pd.Timestamp(observed_end)
    frame = pd.DataFrame({
        "district_id": "fixture-district",
        "date": dates,
        "gwl_current": np.where(observed, groundwater, np.nan),
        "rainfall_current": 30 + dates.month * 10.0,
        "temperature": 15 + dates.month * .8,
        "evapotranspiration": 35 + dates.month * 2.0,
        "is_observed": observed,
        "is_imputed": False,
    })
    frame["gwl_lag_3mo"] = frame.gwl_current.shift(3)
    frame["gwl_lag_6mo"] = frame.gwl_current.shift(6)
    frame.attrs.update(feature_generation_id="fixture-physical-generation", data_source="observed_schema_fixture")
    return frame


@pytest.fixture(autouse=True)
def reset_bundle_cache():
    climate12m._CACHE.clear()
    yield
    climate12m._CACHE.clear()


@pytest.fixture(scope="module")
def tiny_12m_model():
    random = np.random.default_rng(42)
    values = pd.DataFrame(random.uniform(.1, 100, (240, len(climate12m.FEATURES))), columns=climate12m.FEATURES)
    delta = -.02 * values.cumulative_rainfall + .03 * values.cumulative_evapotranspiration + .04 * values.mean_temperature
    model = xgb.XGBRegressor(n_estimators=10, max_depth=2, min_child_weight=1, n_jobs=1, random_state=42)
    model.fit(values, delta)
    return model


def test_prepare_pairs_exact_calendar_months_and_12_horizons():
    frame = physical_frame("2016-01-01", "2020-12-01", "2020-12-01")
    pairs = climate12m.prepare_pairs(frame)
    assert set(pairs.horizon_months.astype(int)) == set(range(1, 13))
    elapsed_months = (pairs.target_date.dt.year - pairs.origin_date.dt.year) * 12 + (pairs.target_date.dt.month - pairs.origin_date.dt.month)
    assert (elapsed_months == pairs.horizon_months).all()
    assert (pairs.target_delta == pairs.actual_gwl - pairs.origin_gwl).all()


def test_distinct_district_ids_never_mix():
    frame1 = physical_frame("2018-01-01", "2020-12-01", "2020-12-01")
    frame2 = physical_frame("2018-01-01", "2020-12-01", "2020-12-01")
    frame2["district_id"] = "district-two"
    frame = pd.concat([frame1, frame2], ignore_index=True)
    frame.attrs.update(frame1.attrs)
    pairs = climate12m.prepare_pairs(frame)
    for district_id in ["fixture-district", "district-two"]:
        sub = pairs[pairs.district_id == district_id]
        assert len(sub) > 0
        assert (sub.district_id == district_id).all()


@pytest.mark.parametrize("flag", [False, None, "False"])
def test_unobserved_or_imputed_targets_excluded(flag):
    frame = physical_frame("2018-01-01", "2020-12-01", "2020-12-01")
    frame["is_observed"] = frame.is_observed.astype(object)
    unavailable = pd.Timestamp("2019-06-01")
    frame.loc[frame.date == unavailable, "is_observed"] = flag
    frame.loc[frame.date == unavailable, "is_imputed"] = flag is False
    frame.loc[frame.date == unavailable, "gwl_current"] = 999.0
    pairs = climate12m.prepare_pairs(frame)
    assert not (pairs.origin_date == unavailable).any()
    assert not (pairs.target_date == unavailable).any()
    assert not (pairs.origin_gwl == 999.0).any()
    assert not (pairs.actual_gwl == 999.0).any()


def test_12m_temporal_embargo_prevents_target_leakage():
    frame = physical_frame("2015-01-01", "2023-12-01", "2023-12-01")
    pairs = climate12m.prepare_pairs(frame)
    cutoff = "2019-12-31"
    train, test = climate12m.split_pairs(pairs, cutoff)
    assert train.target_date.max() <= pd.Timestamp(cutoff)
    # 12-month embargo: first test origin is at least cutoff + 13 months
    first_test_origin = (pd.Timestamp(cutoff).to_period("M") + 13).to_timestamp()
    assert test.origin_date.min() >= first_test_origin
    # No training target overlaps with evaluation origins
    assert train.target_date.max() < test.origin_date.min()


def test_missing_weather_in_path_omits_pair():
    frame = physical_frame("2018-01-01", "2020-12-01", "2020-12-01")
    # Missing temperature in 2018-06
    frame.loc[frame.date == "2018-06-01", "temperature"] = np.nan
    pairs = climate12m.prepare_pairs(frame)
    # All weather columns must remain strictly finite
    weather_cols = [c for c in climate12m.FEATURES if "rain" in c or "temp" in c or "evap" in c]
    assert np.isfinite(pairs[weather_cols].to_numpy()).all()
    # No pair with horizon reaching exactly 2018-06 can exist
    assert not (pairs.target_date == pd.Timestamp("2018-06-01")).any()


def test_separate_12m_checkpoint_cannot_be_confused_with_6m():
    assert climate12m.CHECKPOINT_PATH != climate6m.CHECKPOINT_PATH
    assert climate12m.MODEL_VERSION != climate6m.MODEL_VERSION
    assert climate12m.HORIZONS_MONTHS == list(range(1, 13))


def test_12m_checkpoint_loader_rejects_6m_bundle(tmp_path):
    # Create fake pointer pointing to 6m card
    bad_card = {
        "bundle_schema_version": 1,
        "version": climate6m.MODEL_VERSION, # 6m version
        "features": climate12m.FEATURES,
        "feature_schema_sha256": climate12m._json_hash(climate12m.FEATURES),
        "units": climate12m.UNITS,
        "target": "gwl_change_from_origin",
        "horizons_months": [1, 2, 3, 4, 5, 6], # 6m horizon
        "feature_generation_id": "test-gen",
        "data_source": "test",
        "train_target_cutoff": "2019-12-31",
        "max_train_target_date": "2019-12-01",
        "model_sha256": "fake-sha",
    }
    card_path = tmp_path / "model_card.json"
    card_path.write_text(json.dumps(bad_card), encoding="utf-8")
    model_path = tmp_path / "model.json"
    model_path.write_text("{}", encoding="utf-8")
    pointer = {
        "bundle_schema_version": 1,
        "model_path": "model.json",
        "card_path": "model_card.json",
        "model_sha256": climate12m.sha256_file(model_path),
        "card_sha256": climate12m.sha256_file(card_path)
    }
    ckpt_path = tmp_path / "checkpoint.json"
    ckpt_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(RuntimeError, match="12-month climate model is unavailable or incompatible"):
        climate12m.load_bundle(ckpt_path, expected_generation="test-gen")


def test_forecast_next_twelve_months_returns_exact_12_points():
    res = climate12m.forecast_next_twelve_months("DL-Delhi")
    assert res["status"] == "forecast"
    assert res["product"] == "climate_informed_12m_forecast"
    assert res["model_version"] == "1.0-climate-conditioned-12m-xgb"
    assert res["horizon_months"] == 12
    assert len(res["forecast"]) == 12
    for idx, item in enumerate(res["forecast"], start=1):
        assert item["horizon"] == idx
        assert item["predicted_gwl"] >= 0
        assert "weather" in item
        for field in ("rainfall_mm", "temperature_c", "evapotranspiration_mm"):
            assert np.isfinite(item["weather"][field])


def test_api_12m_prediction_success():
    client = create_app().test_client()
    res = client.get("/api/predict/climate-12m/DL-Delhi")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "forecast"
    assert data["product"] == "climate_informed_12m_forecast"
    assert data["horizon_months"] == 12
    assert len(data["forecast"]) == 12
    assert data["forecast_start"] == data["forecast"][0]["month"]
    assert data["forecast_end"] == data["forecast"][11]["month"]


def test_api_12m_prediction_rejects_invalid_months_or_window():
    client = create_app().test_client()
    r1 = client.get("/api/predict/climate-12m/DL-Delhi?months=6")
    assert r1.status_code == 400
    assert "Only a twelve-month prediction horizon is supported" in r1.get_json()["error"]

    r2 = client.get("/api/predict/climate-12m/DL-Delhi?window=next_six_months")
    assert r2.status_code == 400
    assert "Unsupported parameter" in r2.get_json()["error"]


def test_api_12m_prediction_not_found():
    client = create_app().test_client()
    res = client.get("/api/predict/climate-12m/NONEXISTENT_DISTRICT_XYZ")
    assert res.status_code == 404


def test_legacy_6m_prediction_remains_compatible():
    client = create_app().test_client()
    res = client.get("/api/predict/DL-Delhi?window=next_six_months")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "projection"
    assert len(data["forecast"]) == 6
