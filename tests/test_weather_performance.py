"""Exact-equivalence checks against the pre-optimization weather calculation.

The reference retains the former per-month/per-field pandas implementation.
It is intentionally independent of the optimized selection loop and needs no
model artifact, database, downloaded data, or scratch snapshot to run.
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models.climate_inputs import (
    MAX_REFERENCE_YEARS, MIN_REFERENCE_YEARS, WEATHER_COLUMNS, WEATHER_UNITS,
    _completed_month, _next_months, _timestamp, _weather_history,
    forecast_weather, validate_weather_path,
)


def _reference_forecast_weather(frame, as_of, months=6, overrides=None):
    """Return {status, path, metadata} for explicit future weather assumptions.

    Default means use at most ten most recent usable years for each field and
    calendar month, with at least three distinct prior years. Only complete
    calendar months available by as_of enter those means. If any monthly field
    lacks evidence, status is unavailable and path is empty. Full overrides are
    validated scenarios, not misrepresented as verified weather forecasts.
    """
    as_of = _timestamp(as_of)
    targets = _next_months(as_of, months)
    completed = _completed_month(as_of)
    metadata = {
        "source": "historical_weather_climatology", "units": dict(WEATHER_UNITS),
        "as_of": as_of.date().isoformat(), "completed_through": completed.date().isoformat(),
        "minimum_reference_years": MIN_REFERENCE_YEARS,
        "maximum_reference_years": MAX_REFERENCE_YEARS,
        "future_weather_is_observed": False, "reference_months": [], "missing_inputs": [],
        "assumptions": [
            "Future weather repeats the historical same-month mean; no live weather forecast is used.",
        ],
    }
    if overrides is not None:
        path = validate_weather_path(overrides, as_of, months)
        metadata.update(source="specified_weather_scenario", assumptions=[
            "Monthly weather inputs are a supplied scenario; they are not verified observations or a fetched weather forecast."
        ])
        return {"status": "available", "path": path, "metadata": metadata}

    history = _weather_history(frame, completed)
    populated = history[WEATHER_COLUMNS].notna().any(axis=1)
    latest = history.loc[populated, "date"].max() if populated.any() else None
    metadata["latest_historical_weather_date"] = latest.date().isoformat() if latest is not None else None
    metadata["weather_data_age_months"] = int((as_of.year - latest.year) * 12 + as_of.month - latest.month) if latest is not None else None
    # A refreshed rainfall series must not imply equally recent temperature/ET.
    # These dates describe usable feature history, which may include causal fills.
    latest_by_field = {column: history.loc[history[column].notna(), "date"].max()
                       for column in WEATHER_COLUMNS}
    metadata["latest_historical_weather_dates"] = {
        column: value.date().isoformat() if pd.notna(value) else None
        for column, value in latest_by_field.items()
    }
    metadata["weather_data_age_months_by_field"] = {
        column: int((as_of.year - value.year) * 12 + as_of.month - value.month)
        if pd.notna(value) else None for column, value in latest_by_field.items()
    }
    metadata["weather_history_may_include_filled_values"] = history.attrs.get("may_include_filled_values", True)
    if metadata["weather_history_may_include_filled_values"]:
        metadata["assumptions"].append(
            "Usable weather history may include limited causal fills; its end dates do not establish fresh measurement dates."
        )
    rows = []
    for target in targets:
        row = {"date": target}
        references = {"date": target.date().isoformat(), "fields": {}}
        matching = history[history.date.dt.month == target.month] if len(history) else history
        for column in WEATHER_COLUMNS:
            samples = matching.loc[matching[column].notna(), ["date", column]].tail(MAX_REFERENCE_YEARS)
            years = samples.date.dt.year.nunique() if len(samples) else 0
            references["fields"][column] = {
                "sample_years": int(years),
                "reference_start": samples.date.min().date().isoformat() if len(samples) else None,
                "reference_end": samples.date.max().date().isoformat() if len(samples) else None,
            }
            if years < MIN_REFERENCE_YEARS:
                metadata["missing_inputs"].append({"date": target.date().isoformat(), "field": column,
                                                    "sample_years": int(years), "required_years": MIN_REFERENCE_YEARS})
                row[column] = np.nan
            else:
                row[column] = float(samples[column].mean())
        rows.append(row)
        metadata["reference_months"].append(references)
    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(history, index=False).values.tobytes())
    metadata["weather_history_sha256"] = digest.hexdigest()
    if metadata["missing_inputs"]:
        return {"status": "unavailable", "path": pd.DataFrame(columns=["date", *WEATHER_COLUMNS]), "metadata": metadata}
    return {"status": "available", "path": validate_weather_path(rows, as_of, months), "metadata": metadata}


def _history(dtype="float64"):
    dates = pd.date_range("2004-01-01", "2026-12-01", freq="MS")
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "date": dates,
        "rainfall_current": rng.uniform(0, 700, len(dates)).astype(dtype),
        "temperature": rng.uniform(-10, 45, len(dates)).astype(dtype),
        "evapotranspiration": rng.uniform(0, 250, len(dates)).astype(dtype),
        "rainfall_current_is_imputed": False,
        "temperature_is_imputed": False,
        "evapotranspiration_is_imputed": False,
    })


def _assert_equivalent(frame, as_of, months, overrides=None):
    before = frame.copy(deep=True)
    expected = _reference_forecast_weather(frame, as_of, months, overrides)
    actual = forecast_weather(frame, as_of, months, overrides)
    assert actual["status"] == expected["status"]
    assert actual["metadata"] == expected["metadata"]
    pd.testing.assert_frame_equal(actual["path"], expected["path"], check_exact=True)
    pd.testing.assert_frame_equal(frame, before, check_exact=True)
    return actual


@pytest.mark.parametrize("months", [1, 6, 12])
@pytest.mark.parametrize("as_of", [
    "2023-02-27", "2023-02-28", "2024-02-29", "2024-03-01",
    "2025-12-31", "2026-01-01", "2026-10-25T12:30:00+05:30",
])
def test_indexed_weather_exactly_preserves_calendar_cutoffs_and_metadata(months, as_of):
    _assert_equivalent(_history(), as_of, months)


@pytest.mark.parametrize("months", [1, 6, 12])
@pytest.mark.parametrize("dtype", ["float32", "float64"])
def test_weather_mean_preserves_dtype_reduction_and_sorted_sample_order(months, dtype):
    frame = _history(dtype).sample(frac=1, random_state=91)
    # Non-default row labels and input order must not alter the history selection.
    frame.index = np.arange(len(frame)) * 3 + 7
    _assert_equivalent(frame, "2026-10-25", months)


@pytest.mark.parametrize("months", [1, 6, 12])
@pytest.mark.parametrize("condition", [
    "missing_flags", "mixed_flags", "rainfall_alias", "missing_field",
    "empty", "invalid_values", "insufficient_years", "all_future",
])
def test_weather_missing_and_invalid_evidence_remains_exactly_equivalent(months, condition):
    frame = _history()
    if condition == "missing_flags":
        frame = frame.drop(columns=[column for column in frame if column.endswith("_is_imputed")])
    elif condition == "mixed_flags":
        variants = [False, True, "false", " true ", "0", "1", "unknown", None]
        for offset, column in enumerate(WEATHER_COLUMNS):
            flag = "rainfall_current_is_imputed" if column == "rainfall" else f"{column}_is_imputed"
            frame[flag] = [variants[(index + offset) % len(variants)] for index in range(len(frame))]
    elif condition == "rainfall_alias":
        frame = frame.rename(columns={"rainfall_current": "rainfall",
                                      "rainfall_current_is_imputed": "rainfall_is_imputed"})
    elif condition == "missing_field":
        frame = frame.drop(columns="temperature")
    elif condition == "empty":
        frame = pd.DataFrame()
    elif condition == "invalid_values":
        frame.loc[frame.index % 5 == 0, "rainfall_current"] = np.inf
        frame.loc[frame.index % 7 == 0, "rainfall_current"] = -1
        frame.loc[frame.index % 4 == 0, "temperature"] = 71
        frame.loc[frame.index % 9 == 0, "temperature"] = -101
        frame.loc[frame.index % 3 == 0, "evapotranspiration"] = np.nan
        frame.loc[frame.index % 11 == 0, "evapotranspiration"] = -1
        frame.loc[frame.index % 13 == 0, "rainfall_current"] = 0
        frame.loc[frame.index % 17 == 0, "evapotranspiration"] = 0
    elif condition == "insufficient_years":
        frame = frame[frame.date >= "2025-01-01"]
    else:
        frame["date"] = frame.date + pd.DateOffset(years=30)
    _assert_equivalent(frame, "2026-10-25", months)


@pytest.mark.parametrize("months", [1, 6, 12])
def test_supplied_weather_scenarios_keep_the_original_metadata_and_path(months):
    dates = pd.date_range("2026-11-01", periods=months, freq="MS")
    path = pd.DataFrame({"date": dates, "rainfall": 0.0,
                         "temperature": 25.0, "evapotranspiration": 80.0})
    _assert_equivalent(pd.DataFrame(), "2026-10-25", months, path)


@pytest.mark.parametrize("condition", ["duplicate", "not_month_start", "invalid_override"])
def test_invalid_inputs_keep_the_same_exception(condition):
    frame = _history()
    overrides = None
    if condition == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    elif condition == "not_month_start":
        frame.loc[0, "date"] += pd.Timedelta(days=1)
    else:
        overrides = [{"date": "2026-11-01", "rainfall": -1,
                      "temperature": 25, "evapotranspiration": 50}]
    with pytest.raises(ValueError) as expected:
        _reference_forecast_weather(frame, "2026-10-25", 1, overrides)
    with pytest.raises(ValueError) as actual:
        forecast_weather(frame, "2026-10-25", 1, overrides)
    assert str(actual.value) == str(expected.value)


@pytest.fixture(scope="module")
def local_district_weather():
    path = Path(__file__).resolve().parents[1] / "data/processed/features_matrix.csv"
    if not path.is_file():
        pytest.skip("Existing local feature matrix is not present; no data is fetched.")
    fields = {"district_id", "date", "rainfall_current", *WEATHER_COLUMNS}
    fields.update(f"{field}_is_imputed" for field in list(fields))
    frame = pd.read_csv(path, usecols=lambda column: column in fields, low_memory=False)
    district_ids = frame.district_id.drop_duplicates().tolist()
    selected = set(district_ids[:2] + district_ids[-2:] + [
        "HR-Kaithal", "HR-Kurukshetra", "TS-Adilabad", "TN-Chennai",
    ])
    return [(district_id, history.copy()) for district_id, history in frame.groupby("district_id")
            if district_id in selected]


@pytest.mark.parametrize("months", [1, 6, 12])
def test_existing_local_district_weather_is_exactly_equivalent(local_district_weather, months):
    assert local_district_weather
    for district_id, history in local_district_weather:
        try:
            _assert_equivalent(history, "2026-10-25", months)
        except AssertionError as exc:
            raise AssertionError(f"Weather equivalence failed for {district_id}, horizon={months}") from exc
