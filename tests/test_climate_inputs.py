"""No-hindsight weather assumptions and actual rainfall/ET input sensitivity."""
import json

import numpy as np
import pandas as pd
import pytest

from models.climate_inputs import (
    MONTHLY_FEATURE_COLUMNS, forecast_weather, monthly_features, validate_weather_path,
)


def weather_history(start="2002-01-01", end="2024-12-01"):
    dates = pd.date_range(start, end, freq="MS")
    return pd.DataFrame({
        "date": dates, "rainfall_current": dates.month * 10.0 + dates.year - 2000,
        "temperature": 10.0 + dates.month, "evapotranspiration": 40.0 + dates.month,
        "is_observed": False, "is_imputed": True,
    })


def weather_path(as_of="2026-10-13", months=6):
    dates = pd.period_range(pd.Timestamp(as_of).to_period("M") + 1, periods=months, freq="M").to_timestamp()
    return pd.DataFrame({"date": dates, "rainfall": 10.0, "temperature": 20.0,
                         "evapotranspiration": 40.0})


def test_climatology_uses_recent_ten_same_month_years_with_units_and_provenance():
    result = forecast_weather(weather_history(), "2026-10-13")
    assert result["status"] == "available"
    assert list(result["path"].date.dt.strftime("%Y-%m")) == [
        "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04",
    ]
    # November 2015..2024 averages 110 mm plus a 19.5 mm year offset.
    assert result["path"].iloc[0].rainfall == pytest.approx(129.5)
    assert result["path"].iloc[0].temperature == pytest.approx(21.0)
    assert result["path"].iloc[0].evapotranspiration == pytest.approx(51.0)
    metadata = result["metadata"]
    assert metadata["latest_historical_weather_date"] == "2024-12-01"
    assert metadata["weather_data_age_months"] == 22
    assert metadata["reference_months"][0]["fields"]["rainfall"] == {
        "sample_years": 10, "reference_start": "2015-11-01", "reference_end": "2024-11-01",
    }
    assert metadata["units"] == {"rainfall": "mm/month", "temperature": "degC", "evapotranspiration": "mm/month"}
    assert metadata["future_weather_is_observed"] is False
    # Groundwater imputation flags are deliberately unrelated to measured weather.
    assert len(result["path"]) == 6
    json.dumps(metadata, allow_nan=False)


@pytest.mark.parametrize("as_of,cutoff", [
    ("2024-02-15", "2024-01-01"), ("2024-02-29", "2024-02-01"),
    ("2023-02-28", "2023-02-01"), ("2023-02-27", "2023-01-01"),
])
def test_only_completed_calendar_months_are_available(as_of, cutoff):
    result = forecast_weather(weather_history(), as_of)
    assert result["metadata"]["completed_through"] == cutoff
    assert result["metadata"]["latest_historical_weather_date"] == cutoff


def test_partial_current_and_future_weather_cannot_change_forecast_or_identity():
    frame = weather_history()
    baseline = forecast_weather(frame, "2020-11-13")
    revised = frame.copy()
    revised.loc[revised.date >= "2020-11-01", ["rainfall_current", "temperature", "evapotranspiration"]] = [99999.0, 65.0, 99999.0]
    result = forecast_weather(revised, "2020-11-13")
    pd.testing.assert_frame_equal(result["path"], baseline["path"])
    assert result["metadata"] == baseline["metadata"]


@pytest.mark.parametrize("column", ["rainfall_current", "temperature", "evapotranspiration"])
def test_missing_calendar_phase_is_explicitly_unavailable_not_zero(column):
    frame = weather_history()
    frame.loc[frame.date.dt.month == 11, column] = np.nan
    result = forecast_weather(frame, "2026-10-13")
    assert result["status"] == "unavailable"
    assert result["path"].empty
    expected = "rainfall" if column == "rainfall_current" else column
    assert result["metadata"]["missing_inputs"] == [{
        "date": "2026-11-01", "field": expected, "sample_years": 0, "required_years": 3,
    }]


def test_three_distinct_years_are_required_and_zero_rain_is_valid():
    frame = weather_history("2023-01-01", "2024-12-01")
    assert forecast_weather(frame, "2026-10-13")["status"] == "unavailable"
    frame = weather_history("2022-01-01", "2024-12-01")
    frame["rainfall_current"] = 0.0
    frame["evapotranspiration"] = 0.0
    result = forecast_weather(frame, "2026-10-13")
    assert result["status"] == "available"
    assert (result["path"].rainfall == 0.0).all()


def test_invalid_weather_and_explicit_weather_imputation_are_excluded():
    frame = weather_history("2020-01-01", "2024-12-01")
    november = frame.date.dt.month == 11
    frame.loc[november & (frame.date.dt.year == 2024), "rainfall_current"] = np.inf
    frame.loc[november & (frame.date.dt.year == 2023), "rainfall_current"] = -1.0
    frame["temperature_is_imputed"] = False
    frame.loc[november & frame.date.dt.year.isin([2023, 2024]), "temperature_is_imputed"] = True
    result = forecast_weather(frame, "2026-10-13")
    assert result["status"] == "available"
    assert result["metadata"]["reference_months"][0]["fields"]["rainfall"]["sample_years"] == 3
    assert result["metadata"]["reference_months"][0]["fields"]["temperature"]["sample_years"] == 3
    frame.loc[november & (frame.date.dt.year == 2022), "evapotranspiration"] = np.nan
    frame.loc[november & (frame.date.dt.year == 2023), "evapotranspiration"] = np.nan
    frame.loc[november & (frame.date.dt.year == 2024), "evapotranspiration"] = np.nan
    assert forecast_weather(frame, "2026-10-13")["status"] == "unavailable"


def test_empty_history_has_json_safe_missing_evidence():
    result = forecast_weather(pd.DataFrame(), "2026-10-13")
    assert result["status"] == "unavailable" and result["path"].empty
    assert result["metadata"]["latest_historical_weather_date"] is None
    assert len(result["metadata"]["missing_inputs"]) == 18
    json.dumps(result["metadata"], allow_nan=False)


def test_duplicate_history_cannot_double_count_reference_years():
    frame = weather_history()
    with pytest.raises(ValueError, match="duplicate months"):
        forecast_weather(pd.concat([frame, frame.iloc[:1]]), "2026-10-13")


def test_full_weather_scenario_is_validated_and_labelled_as_assumed():
    scenario = weather_path()
    result = forecast_weather(pd.DataFrame(), "2026-10-13", overrides=scenario.to_dict("records"))
    pd.testing.assert_frame_equal(result["path"], scenario)
    assert result["metadata"]["source"] == "specified_weather_scenario"
    assert result["metadata"]["future_weather_is_observed"] is False


@pytest.mark.parametrize("mutation", ["nan", "infinite", "negative_rain", "negative_et", "kelvin", "gap", "reversed", "duplicate", "wrong_start", "missing_field", "not_month_start"])
def test_bad_weather_scenarios_are_rejected(mutation):
    path = weather_path()
    if mutation == "nan":
        path.loc[0, "rainfall"] = np.nan
    elif mutation == "infinite":
        path.loc[0, "temperature"] = np.inf
    elif mutation == "negative_rain":
        path.loc[0, "rainfall"] = -1
    elif mutation == "negative_et":
        path.loc[0, "evapotranspiration"] = -1
    elif mutation == "kelvin":
        path.loc[0, "temperature"] = 300
    elif mutation == "gap":
        path = path.drop(index=1)
    elif mutation == "reversed":
        path = path.iloc[::-1]
    elif mutation == "duplicate":
        path.loc[1, "date"] = path.loc[0, "date"]
    elif mutation == "wrong_start":
        path["date"] = path.date + pd.DateOffset(months=1)
    elif mutation == "missing_field":
        path = path.drop(columns="temperature")
    else:
        path.loc[0, "date"] = pd.Timestamp("2026-11-02")
    with pytest.raises(ValueError):
        forecast_weather(pd.DataFrame(), "2026-10-13", overrides=path)


def test_monthly_features_capture_calendar_and_cumulative_weather_sensitivity():
    path = weather_path()
    baseline = monthly_features("2026-10-13", path)
    assert list(baseline.columns) == ["date", *MONTHLY_FEATURE_COLUMNS]
    assert list(baseline.horizon_months) == [1, 2, 3, 4, 5, 6]
    assert list(baseline.cumulative_rainfall) == [10, 20, 30, 40, 50, 60]
    assert list(baseline.cumulative_evapotranspiration) == [40, 80, 120, 160, 200, 240]
    assert baseline.iloc[0].origin_month_sin == pytest.approx(np.sin(10 * 2 * np.pi / 12))
    assert baseline.iloc[0].target_month_cos == pytest.approx(np.cos(11 * 2 * np.pi / 12))
    wet = path.copy()
    wet.loc[1, "rainfall"] = 100
    wet.loc[1, "temperature"] = 25
    wet.loc[1, "evapotranspiration"] = 60
    changed = monthly_features("2026-10-13", wet)
    assert changed.iloc[0].equals(baseline.iloc[0])
    assert changed.iloc[1].target_rainfall == 100
    assert changed.iloc[-1].cumulative_rainfall == 150
    assert changed.iloc[-1].cumulative_evapotranspiration == 260
    assert changed.iloc[-1].mean_temperature == pytest.approx(20 + 5 / 6)
    assert np.isfinite(changed[MONTHLY_FEATURE_COLUMNS].to_numpy()).all()


def test_historical_realized_weather_path_uses_exact_calendar_horizon():
    path = weather_path("2018-12-01")
    result = monthly_features("2018-12-01", path)
    assert result.iloc[0].date == pd.Timestamp("2019-01-01")
    assert result.iloc[-1].date == pd.Timestamp("2019-06-01")
    assert result.iloc[-1].horizon_months == 6
    with pytest.raises(ValueError, match="consecutive"):
        monthly_features("2018-11-01", path)


@pytest.mark.parametrize("months", [0, -1, 6.5, True])
def test_invalid_path_lengths_are_rejected(months):
    with pytest.raises(ValueError, match="positive integer"):
        forecast_weather(weather_history(), "2026-10-13", months=months)
