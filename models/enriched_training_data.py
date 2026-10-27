"""Candidate-only observed pairs with the production weather/lag encoding.

Callers must load the immutable snapshot with ``load_feature_matrix`` first.
This pure builder neither changes that snapshot nor publishes a model. Training
anchors are genuine observed depths; production may instead estimate its anchor
across a measurement gap. Matching feature encoding does not remove that gap's
uncertainty or establish the source's historical publication time.
"""
from __future__ import annotations

from copy import deepcopy
import math

import numpy as np
import pandas as pd

from models.climate_forecast import origin_inputs
from models.climate_forecast_12m import FEATURES
from models.climate_inputs import DistrictClimatology, _weather_history
from models.monthly_projection import _design, fit_projection, predict_depth


PAIR_COLUMNS = ['district_id', 'origin_date', 'target_date', 'actual_gwl', 'target_delta'] + FEATURES
VERSION = 'enriched-observed-pairs-month-end-v1'
_SOURCE_PROHIBITED = ('synthetic', 'forecast', 'predict', 'simulat')


def _flags(values, name):
    result = values.astype('string').str.strip().str.lower().map(
        {'true': True, 'false': False, '1': True, '0': False})
    if result.isna().any():
        raise ValueError(f'Unknown observation provenance in {name}.')
    return result.astype(bool)


def _validated(frame):
    required = {'district_id', 'date', 'gwl_current', 'rainfall_current',
                'temperature', 'evapotranspiration', 'is_observed', 'is_imputed'}
    if required - set(frame):
        raise ValueError(f'Enriched pair fields missing: {sorted(required - set(frame))}')
    source = frame.attrs.get('data_source')
    generation = frame.attrs.get('feature_generation_id')
    if (not isinstance(generation, str) or not generation.strip()
            or not isinstance(source, str) or not source.strip()
            or source.strip().lower() == 'unknown'
            or any(word in source.lower() for word in _SOURCE_PROHIBITED)):
        raise ValueError('Training requires an identified real feature generation and data source.')
    # Drop metadata only on our copy: otherwise pandas repeatedly deep-copies
    # the potentially large raw-resource manifest during column operations.
    values = frame.copy()
    values.attrs = {}
    if values.empty or values.district_id.isna().any() or values.district_id.astype(str).str.strip().eq('').any():
        raise ValueError('Training requires nonempty district identities.')
    values['district_id'] = values.district_id.astype(str)
    values['date'] = pd.to_datetime(values.date, errors='raise')
    if (values.date.isna().any() or values.date.dt.tz is not None
            or not values.date.dt.is_month_start.all()
            or not values.date.eq(values.date.dt.normalize()).all()):
        raise ValueError('Training requires naive calendar month starts.')
    if values.duplicated(['district_id', 'date']).any():
        raise ValueError('Duplicate district-month keys cannot form training pairs.')
    for name in ('is_observed', 'is_imputed'):
        values[name] = _flags(values[name], name)
    if (values.is_observed & values.is_imputed).any():
        raise ValueError('A training row cannot be both observed and imputed.')
    for name in ('gwl_current', 'rainfall_current', 'temperature', 'evapotranspiration'):
        try:
            values[name] = pd.to_numeric(values[name], errors='raise').astype(float)
        except (TypeError, ValueError) as error:
            raise ValueError(f'Training field {name} must be numeric or missing.') from error
    observed = values.is_observed & ~values.is_imputed
    if (~np.isfinite(values.loc[observed, 'gwl_current']) | values.loc[observed, 'gwl_current'].lt(0)).any():
        raise ValueError('Observed training depths must be finite nonnegative metres below ground.')
    if 'source_type' in values:
        bad = values.source_type.astype('string').str.lower().fillna('').map(
            lambda text: any(word in text for word in _SOURCE_PROHIBITED))
        if (observed & bad).any():
            raise ValueError('Synthetic or predicted source rows cannot be observed training labels.')
        # Known predictions do not become lag covariates either.
        values.loc[bad, 'gwl_current'] = np.nan
    for name in ('rainfall_current', 'evapotranspiration'):
        finite = values[name].dropna()
        if not np.isfinite(finite).all() or finite.lt(0).any():
            raise ValueError(f'Invalid physical weather values in {name}.')
    temperature = values.temperature.dropna()
    if not np.isfinite(temperature).all() or not temperature.between(-100, 70).all():
        raise ValueError('Temperature must use physical degrees Celsius.')
    return values.sort_values(['district_id', 'date']).reset_index(drop=True)


def _origin_lags(row_map, origin, history):
    """The same available-value/projection fallback used by production.

    Persisted lag columns are deliberately not trusted: exact calendar lookups
    into the causal source values prevent cross-district/row-order lag errors.
    A sparse origin without a fit keeps a missing lag as native XGBoost NaN.
    """
    lags = {}
    missing = []
    for lag in (3, 6):
        month = origin - pd.DateOffset(months=lag)
        value = row_map.get(month, np.nan)
        if np.isfinite(value) and value >= 0:
            lags[lag] = float(value)
        else:
            lags[lag] = np.nan
            missing.append((lag, month))
    if not missing:
        return lags, False, False
    fit = fit_projection(history, origin + pd.offsets.MonthEnd(0))
    if fit is None:
        return lags, True, False
    for lag, month in missing:
        if month >= fit['origin']:
            lags[lag] = float(predict_depth(fit, [month])[0])
        else:
            lags[lag] = float(max(0., (_design([month], fit['origin'], fit['seasonal'])
                @ fit['coefficients'] + fit['level_offset'])[0]))
    return lags, True, True


def _feature_array(origin, array_path, inputs):
    """Exact numeric core of production feature_rows for twelve finite months.

    The climatology engine has already applied the physical-value/reference
    policy. Preserve math.sin for origin phase, NumPy for target phase, and
    pandas' compensated expanding mean rather than a different cumsum mean.
    Tests compare all 17 fields bitwise with the production encoder.
    """
    dates, rainfall, temperature, evaporation = array_path
    phase = 2 * math.pi * origin.month / 12
    target_phase = 2 * math.pi * dates.month.to_numpy() / 12
    columns = {**inputs,
        'horizon_months': np.arange(1, 13, dtype=float),
        'origin_month_sin': math.sin(phase), 'origin_month_cos': math.cos(phase),
        'target_month_sin': np.sin(target_phase), 'target_month_cos': np.cos(target_phase),
        'target_rainfall': rainfall, 'target_temperature': temperature,
        'target_evapotranspiration': evaporation,
        'cumulative_rainfall': np.cumsum(rainfall),
        'cumulative_evapotranspiration': np.cumsum(evaporation),
        'mean_temperature': pd.Series(temperature).expanding().mean().to_numpy()}
    result = np.column_stack([np.broadcast_to(columns[name], 12) for name in FEATURES])
    if np.isinf(result).any():
        raise ValueError('Candidate climate features contain infinite values.')
    return result


def prepare_pairs(frame):
    """Return exact observed t+h pairs (h=1..12) in serving feature order.

    Future source rows are used only to identify genuine measured targets.
    Origin groundwater, lag fallback fits and weather climatology all use the
    origin-available prefix. Pair eligibility never converts a filled value into
    a target. No scaler, imputer or global statistic is learned on future rows.
    """
    values = _validated(frame)
    audit = {'version': VERSION, 'source_rows': len(values),
        'source_districts': int(values.district_id.nunique()),
        'observed_rows': int(values.is_observed.sum()),
        'origins_with_later_target': 0, 'origins_without_later_target': 0,
        'origins_unavailable_weather': 0, 'origins_unavailable_origin_inputs': 0,
        'origins_with_missing_calendar_lags': 0, 'origins_with_projection_lag_fallback': 0,
        'origins_without_fit_retaining_native_nan_lags': 0,
        'training_anchor': 'genuine observed origin depth',
        'production_anchor_caveat': 'Production may estimate current depth across gaps; identical encoding does not validate that estimated anchor.',
        'weather_cutoff': 'origin calendar month end; future weather observations excluded',
        'lag_policy': 'finite causal exact-calendar value, then origin-available production projection, otherwise native NaN'}
    records = []
    calendar_targets = {}
    for district_id, district in values.groupby('district_id', sort=True):
        district = district.reset_index(drop=True)
        district.attrs = {}
        observed = district.loc[district.is_observed & ~district.is_imputed].reset_index(drop=True)
        labels = dict(zip(observed.date, observed.gwl_current))
        row_map = dict(zip(district.date, district.gwl_current))
        history = _weather_history(district, district.date.max())
        climatology = DistrictClimatology(history)
        for position, row in enumerate(observed.itertuples(index=False)):
            origin = pd.Timestamp(row.date)
            if origin not in calendar_targets:
                calendar_targets[origin] = pd.date_range(origin + pd.offsets.MonthBegin(1), periods=12, freq='MS')
            target_dates = calendar_targets[origin]
            keep = [h for h, date in enumerate(target_dates) if date in labels]
            if not keep:
                audit['origins_without_later_target'] += 1
                continue
            audit['origins_with_later_target'] += 1
            cutoff = origin + pd.offsets.MonthEnd(0)
            array_path = climatology.array_path(cutoff, 12)
            if array_path is None:
                audit['origins_unavailable_weather'] += 1
                continue
            lags, missing, fitted = _origin_lags(row_map, origin, observed.iloc[:position + 1])
            audit['origins_with_missing_calendar_lags'] += int(missing)
            audit['origins_with_projection_lag_fallback'] += int(fitted)
            audit['origins_without_fit_retaining_native_nan_lags'] += int(missing and not fitted)
            # Same finite-origin branch as origin_inputs; missing origin weather
            # uses the production fallback rather than any ad-hoc fill.
            if np.isfinite([row.rainfall_current, row.temperature, row.evapotranspiration]).all():
                inputs = {'origin_gwl': float(row.gwl_current),
                    'origin_rainfall': float(row.rainfall_current),
                    'origin_temperature': float(row.temperature),
                    'origin_evapotranspiration': float(row.evapotranspiration),
                    'origin_gwl_lag_3mo': lags[3], 'origin_gwl_lag_6mo': lags[6]}
            else:
                inputs, _ = origin_inputs(district, origin, cutoff, float(row.gwl_current), lags)
            if inputs is None:
                audit['origins_unavailable_origin_inputs'] += 1
                continue
            features = _feature_array(origin, array_path, inputs)
            for h in keep:
                actual = float(labels[target_dates[h]])
                records.append({'district_id': district_id, 'origin_date': origin,
                    'target_date': target_dates[h], 'actual_gwl': actual,
                    'target_delta': actual - float(row.gwl_current),
                    **dict(zip(FEATURES, features[h]))})
    # One materialization avoids tens of thousands of small DataFrames.
    result = pd.DataFrame.from_records(records, columns=PAIR_COLUMNS)
    audit.update(pair_rows=len(result), pair_districts=int(result.district_id.nunique()),
        pairs_by_horizon={str(int(h)): int(n) for h, n in result.groupby('horizon_months').size().items()},
        target_date_counts={str(date.date()): int(n) for date, n in result.groupby('target_date').size().items()})
    result.attrs.update(deepcopy(frame.attrs))
    result.attrs['pair_audit'] = audit
    return result
