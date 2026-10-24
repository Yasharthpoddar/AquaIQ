"""Causal physical weather paths for conditional monthly groundwater models.

No live weather forecast is available in this repository. The default path is
therefore an explicit same-calendar-month climatology assumption. Missing
weather is never replaced with zero, and groundwater observation flags are not
mistaken for weather observation flags.
"""
import hashlib
import math

import numpy as np
import pandas as pd

WEATHER_COLUMNS = ["rainfall", "temperature", "evapotranspiration"]
WEATHER_UNITS = {"rainfall": "mm/month", "temperature": "degC", "evapotranspiration": "mm/month"}
MONTHLY_FEATURE_COLUMNS = [
    "horizon_months", "origin_month_sin", "origin_month_cos",
    "target_month_sin", "target_month_cos", "target_rainfall",
    "target_temperature", "target_evapotranspiration", "cumulative_rainfall",
    "cumulative_evapotranspiration", "mean_temperature",
]
MIN_REFERENCE_YEARS = 3
MAX_REFERENCE_YEARS = 10


def _timestamp(value):
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("A valid date is required for weather inputs.") from exc
    if pd.isna(timestamp):
        raise ValueError("A valid date is required for weather inputs.")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_localize(None)
    return timestamp.normalize()


def _completed_month(as_of):
    month = as_of.to_period("M")
    if as_of.day != as_of.days_in_month:
        month -= 1
    return month.to_timestamp()


def _next_months(as_of, months):
    if isinstance(months, bool) or not isinstance(months, (int, np.integer)) or months < 1:
        raise ValueError("Weather path months must be a positive integer.")
    return pd.period_range(as_of.to_period("M") + 1, periods=int(months), freq="M").to_timestamp()


def validate_weather_path(path, origin=None, months=None):
    """Return physical finite monthly inputs, rejecting gaps and bad units.

    A path must begin the calendar month immediately after origin, when origin
    is supplied. Temperatures are degrees Celsius; precipitation and ET are
    nonnegative millimetres per month, including legitimate measured zeros.
    """
    path = pd.DataFrame(path).copy()
    required = {"date", *WEATHER_COLUMNS}
    if required - set(path.columns):
        raise ValueError(f"Weather path is missing fields: {sorted(required - set(path.columns))}.")
    if path.empty:
        raise ValueError("Weather path cannot be empty.")
    try:
        dates = pd.to_datetime(path["date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("Weather path dates must be valid calendar month starts.") from exc
    if dates.isna().any() or (dates.dt.day != 1).any() or (dates != dates.dt.normalize()).any():
        raise ValueError("Weather path dates must be valid calendar month starts.")
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("Weather path months must be unique and chronological.")
    start = _timestamp(origin) if origin is not None else dates.iloc[0] - pd.DateOffset(months=1)
    count = len(path) if months is None else months
    expected = _next_months(start, count)
    if len(path) != len(expected) or not pd.DatetimeIndex(dates).equals(expected):
        raise ValueError("Weather path must contain exactly the consecutive next calendar months.")
    result = pd.DataFrame({"date": dates.to_numpy()})
    for column in WEATHER_COLUMNS:
        numeric = pd.to_numeric(path[column], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(numeric).all():
            raise ValueError(f"Weather path {column} must be finite for every month.")
        if column != "temperature" and (numeric < 0).any():
            raise ValueError(f"Weather path {column} cannot be negative.")
        if column == "temperature" and ((numeric < -100) | (numeric > 70)).any():
            raise ValueError("Weather path temperature must use physical degrees Celsius.")
        result[column] = numeric
    return result


def _weather_history(frame, cutoff):
    frame = pd.DataFrame(frame)
    if frame.empty or "date" not in frame:
        return pd.DataFrame(columns=["date", *WEATHER_COLUMNS])
    dates = pd.to_datetime(frame["date"], errors="coerce")
    valid = dates.notna() & (dates <= cutoff)
    dates = dates[valid]
    if (dates.dt.day != 1).any() or (dates != dates.dt.normalize()).any():
        raise ValueError("Weather history must use calendar month starts.")
    if dates.duplicated().any():
        raise ValueError("Weather history contains duplicate months; select one district or aggregate first.")
    result = pd.DataFrame({"date": dates})
    may_include_filled_values = False
    for column in WEATHER_COLUMNS:
        source = "rainfall_current" if column == "rainfall" and "rainfall_current" in frame else column
        numeric = pd.to_numeric(frame.loc[valid, source], errors="coerce") if source in frame else pd.Series(np.nan, index=dates.index)
        finite = np.isfinite(numeric.to_numpy(dtype=float))
        numeric = numeric.where(finite)
        if column != "temperature":
            numeric = numeric.where(numeric >= 0)
        else:
            numeric = numeric.where(numeric.between(-100, 70))
        # These flags, unlike is_observed/is_imputed, refer specifically to weather.
        imputed_flag = f"{source}_is_imputed"
        if imputed_flag not in frame:
            imputed_flag = f"{column}_is_imputed"
        if imputed_flag in frame:
            known = frame.loc[valid, imputed_flag].astype("string").str.lower().str.strip()
            numeric = numeric.where(known.isin(["false", "0"]))
        else:
            may_include_filled_values = True
        result[column] = numeric
    result = result.sort_values("date").reset_index(drop=True)
    result.attrs["may_include_filled_values"] = may_include_filled_values
    return result


def forecast_weather(frame, as_of, months=6, overrides=None):
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


def climatology_path(history, origin, months=12):
    """Assumed future monthly weather from prior same-month records only.

    For every target month, each field is the mean of the most recent usable
    same-calendar-month records available at or before the forecast origin's
    completed month, using at most MAX_REFERENCE_YEARS distinct prior years and
    requiring at least MIN_REFERENCE_YEARS of them. This is the numeric core of
    forecast_weather without its serving metadata, so training and evaluation
    share one definition of "weather information available at the origin".
    Returns None when any needed feature lacks enough reference years; the
    caller decides whether that makes an origin ineligible.
    """
    return DistrictClimatology(history).path(origin, months)


class DistrictClimatology:
    """Vectorized per-district engine behind climatology_path."""

    def __init__(self, history):
        history = pd.DataFrame(history)
        if history.empty or "date" not in history or not set(WEATHER_COLUMNS) <= set(history.columns):
            raise ValueError("District weather history requires date and weather fields.")
        dindex = pd.DatetimeIndex(history["date"])
        valid = dindex.notna()
        if not valid.any():
            self._months = {}
            self._cache = {}
            return
        dates_arr = history["date"].loc[valid].to_numpy(dtype='datetime64[D]')
        months_arr = dindex[valid].month.to_numpy()
        years_arr = dindex[valid].year.to_numpy()
        self._months = {}
        for column in WEATHER_COLUMNS:
            numeric = pd.to_numeric(history.loc[valid, column], errors="coerce").to_numpy(dtype=float)
            if column == "temperature":
                finite = np.isfinite(numeric) & (numeric >= -100) & (numeric <= 70)
            else:
                finite = np.isfinite(numeric) & (numeric >= 0)
            for m in range(1, 13):
                mask = finite & (months_arr == m)
                if m not in self._months:
                    self._months[m] = {}
                self._months[m][column] = {
                    "dates": dates_arr[mask],
                    "values": numeric[mask],
                    "years": years_arr[mask],
                }
        self._cache = {}

    def path(self, origin, months=12):
        origin = _timestamp(origin)
        completed = _completed_month(origin)
        completed_day = np.datetime64(completed, 'D')
        cache_key = (completed_day, int(months))
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return cached.copy() if cached is not None else None
        targets = _next_months(origin, months)
        data = {"date": targets}
        for column in WEATHER_COLUMNS:
            vals = np.empty(months, dtype=float)
            for i, target in enumerate(targets):
                fields = self._months.get(int(target.month), {}).get(column)
                if fields is None:
                    self._cache[cache_key] = None
                    return None
                cutoff = int(np.searchsorted(fields["dates"], completed_day, side='right'))
                start = max(0, cutoff - MAX_REFERENCE_YEARS)
                samples = fields["values"][start:cutoff]
                sample_years = fields["years"][start:cutoff]
                if len(sample_years) < MIN_REFERENCE_YEARS or len(np.unique(sample_years)) < MIN_REFERENCE_YEARS:
                    self._cache[cache_key] = None
                    return None
                vals[i] = samples.mean()
            data[column] = vals
        result = pd.DataFrame(data)
        validated = validate_weather_path(result, origin, months)
        self._cache[cache_key] = validated
        return validated.copy()

    def array_path(self, origin, months=12):
        origin = _timestamp(origin)
        completed = _completed_month(origin)
        completed_day = np.datetime64(completed, 'D')
        cache_key = ("array", completed_day, int(months))
        if cache_key in self._cache:
            return self._cache[cache_key]
        targets = _next_months(origin, months)
        arrays = {}
        for column in WEATHER_COLUMNS:
            vals = np.empty(months, dtype=float)
            for i, target in enumerate(targets):
                fields = self._months.get(int(target.month), {}).get(column)
                if fields is None:
                    self._cache[cache_key] = None
                    return None
                cutoff = int(np.searchsorted(fields["dates"], completed_day, side='right'))
                start = max(0, cutoff - MAX_REFERENCE_YEARS)
                samples = fields["values"][start:cutoff]
                sample_years = fields["years"][start:cutoff]
                if len(sample_years) < MIN_REFERENCE_YEARS or len(np.unique(sample_years)) < MIN_REFERENCE_YEARS:
                    self._cache[cache_key] = None
                    return None
                vals[i] = samples.mean()
            arrays[column] = vals
        res = (targets, arrays["rainfall"], arrays["temperature"], arrays["evapotranspiration"])
        self._cache[cache_key] = res
        return res


def monthly_features(origin, target_weather_path):
    """Encode every monthly horizon and cumulative weather from an origin.

    Training can pass actual post-origin weather as *conditional* covariates;
    that evaluation must be labelled as known-weather evaluation rather than
    weather forecast skill. Serving passes forecast_weather's assumed path.
    Current groundwater depth and its evidence are added by the caller.
    """
    origin = _timestamp(origin)
    path = validate_weather_path(target_weather_path, origin)
    horizons = np.arange(1, len(path) + 1, dtype=float)
    origin_phase = 2 * math.pi * origin.month / 12
    target_phase = 2 * math.pi * path.date.dt.month.to_numpy() / 12
    result = pd.DataFrame({
        "date": path.date,
        "horizon_months": horizons,
        "origin_month_sin": math.sin(origin_phase), "origin_month_cos": math.cos(origin_phase),
        "target_month_sin": np.sin(target_phase), "target_month_cos": np.cos(target_phase),
        "target_rainfall": path.rainfall, "target_temperature": path.temperature,
        "target_evapotranspiration": path.evapotranspiration,
        "cumulative_rainfall": path.rainfall.cumsum(),
        "cumulative_evapotranspiration": path.evapotranspiration.cumsum(),
        "mean_temperature": path.temperature.expanding().mean(),
    })
    if not np.isfinite(result[MONTHLY_FEATURE_COLUMNS].to_numpy(dtype=float)).all():
        raise ValueError("Weather feature totals must remain finite.")
    return result
