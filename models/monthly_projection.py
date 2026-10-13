"""Six future calendar-month estimates from the requested date.

The XGBoost checkpoint supports one endpoint from an observed origin. This
separate statistical model fits actual observations, estimates the unobserved
gap, and continues a damped trend with an annual seasonal cycle. Its current
outlook is exploratory, not a validated operational forecast.
"""
import hashlib
import math

import numpy as np
import pandas as pd

from db.connection import finite_json
from models.ensemble import _as_of, _completed_feature_month, select_evidence
from models.xgboost_model import observed_mask

MIN_OBSERVATIONS = 24
MIN_SPAN_MONTHS = 36
LOOKBACK_MONTHS = 120
TREND_DAMPING_MONTHS = 36.0
MODEL_VERSION = '1.0-observed-seasonal-trend'


def _month_number(dates):
    dates = pd.DatetimeIndex(dates)
    return (dates.year * 12 + dates.month).to_numpy(dtype=float)


def _observed_history(history, cutoff):
    if history.empty:
        return pd.DataFrame(columns=['date', 'gwl_current'])
    dates = pd.to_datetime(history['date'], errors='coerce')
    depths = pd.to_numeric(history['gwl_current'], errors='coerce')
    valid = (observed_mask(history) & dates.notna() & np.isfinite(depths)
             & (depths >= 0) & (dates <= _completed_feature_month(cutoff)))
    frame = pd.DataFrame({'date': dates[valid], 'gwl_current': depths[valid]}).sort_values('date')
    if frame.date.duplicated().any():
        raise ValueError('Projection history contains duplicate observation months.')
    if (frame.date.dt.day != 1).any():
        raise ValueError('Projection observations must use calendar month starts.')
    return frame.reset_index(drop=True)


def _design(dates, origin, seasonal):
    month = _month_number(dates)
    elapsed_years = (month - _month_number([origin])[0]) / 12.0
    columns = [np.ones(len(month)), elapsed_years]
    if seasonal:
        phase = 2.0 * np.pi * pd.DatetimeIndex(dates).month.to_numpy() / 12.0
        columns.extend([np.sin(phase), np.cos(phase)])
    return np.column_stack(columns)


def fit_projection(history, cutoff):
    """Fit only observations available at cutoff, preserving calendar gaps."""
    cutoff = pd.Timestamp(cutoff).normalize()
    history = _observed_history(history, cutoff)
    if len(history) < MIN_OBSERVATIONS:
        return None
    origin = pd.Timestamp(history.date.iloc[-1])
    recent = history[history.date >= origin - pd.DateOffset(months=LOOKBACK_MONTHS)]
    if len(recent) >= MIN_OBSERVATIONS:
        history = recent.reset_index(drop=True)
    span = int(_month_number([origin])[0] - _month_number([history.date.iloc[0]])[0])
    if span < MIN_SPAN_MONTHS:
        return None
    phase_counts = history.date.dt.month.value_counts()
    seasonal = int((phase_counts >= 3).sum()) >= 3 and history.date.dt.year.nunique() >= 3
    design = _design(history.date, origin, seasonal)
    if seasonal and np.linalg.matrix_rank(design) < design.shape[1]:
        seasonal = False
        design = _design(history.date, origin, seasonal)
    y = history.gwl_current.to_numpy(dtype=float)
    ages = _month_number([origin])[0] - _month_number(history.date)
    # Downweight older evidence and shrink the trend/seasonal coefficients.
    weights = np.exp(-math.log(2.0) * ages / 60.0)
    penalty = np.diag([0.0, 0.1] + ([1.0, 1.0] if seasonal else []))
    robust = np.ones(len(history))
    for _ in range(4):
        weighted = weights * robust
        coefficients = np.linalg.solve(design.T @ (weighted[:, None] * design) + penalty,
                                       design.T @ (weighted * y))
        residuals = y - design @ coefficients
        scale = 1.4826 * np.median(np.abs(residuals - np.median(residuals)))
        if scale < 1e-8:
            break
        robust = np.minimum(1.0, 1.345 * scale / np.maximum(np.abs(residuals), 1e-12))
    # Recent residuals align the level without treating inferred values as data.
    anchor = history.date >= origin - pd.DateOffset(months=12)
    offset = float(np.median((y - design @ coefficients)[anchor.to_numpy()][-3:]))
    if not np.isfinite(coefficients).all() or not math.isfinite(offset):
        raise RuntimeError('Monthly projection fit produced non-finite parameters.')
    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(history, index=False).values.tobytes())
    fitted = design @ coefficients + offset
    return {'origin': origin, 'coefficients': coefficients, 'level_offset': offset,
            'seasonal': seasonal, 'observation_count': len(history),
            'history_start': history.date.iloc[0].date().isoformat(),
            'history_sha256': digest.hexdigest(), 'span_months': span,
            'fit_rmse_m': float(np.sqrt(np.mean((y - fitted) ** 2))),
            'last_observed_gwl': float(history.gwl_current.iloc[-1])}


def predict_depth(fit, dates):
    """Damp across the entire gap from the last observation, including today."""
    dates = pd.DatetimeIndex(dates)
    horizons = _month_number(dates) - _month_number([fit['origin']])[0]
    if (horizons < 0).any():
        raise ValueError('Projection targets cannot precede the fitted origin.')
    design = _design(dates, fit['origin'], fit['seasonal'])
    design[:, 1] = TREND_DAMPING_MONTHS / 12.0 * (-np.expm1(-horizons / TREND_DAMPING_MONTHS))
    predicted = design @ fit['coefficients'] + fit['level_offset']
    if not np.isfinite(predicted).all():
        raise RuntimeError('Monthly projection produced non-finite depths.')
    return np.maximum(0.0, predicted)


def projection_from_evidence(evidence):
    cutoff = _as_of(evidence['as_of'])
    history = _observed_history(evidence['history'], cutoff)
    origin = pd.Timestamp(history.date.iloc[-1]) if len(history) else None
    result = {'district_id': evidence['district_id'], 'status': 'insufficient_data',
              'forecast': [], 'as_of': cutoff.date().isoformat(),
              'forecast_origin': cutoff.date().isoformat(), 'horizon_months': 6,
              'forecast_horizon': 'next six full calendar months', 'units': 'm_bgl',
              'last_observed_date': origin.date().isoformat() if origin is not None else None,
              'estimate_type': evidence['estimate_type'], 'source_zone': evidence['zone'],
              'zone_fallback_reason': evidence['reason'], 'feature_generation': evidence['generation'],
              'projection_method': 'damped_seasonal_trend', 'model_version': MODEL_VERSION,
              'estimated_current_gwl': None, 'data_age_months': None,
              'validation': {'status': 'unvalidated_current_projection',
                             'sufficient_for_operational_use': False},
              'limitations': [
                  'These are statistical monthly depth estimates, not actual measurements.',
                  'The unobserved gap is estimated from historical trend and seasonality; fresh readings are needed to verify current conditions.',
                  'Future rainfall, pumping and weather are not known or included in this projection.',
                  'Monthly projections and the estimated current level have not been independently validated for operational use.'
              ]}
    if evidence['estimate_type'] == 'insufficient_data':
        result['message'] = 'Not enough district or zone observations for a monthly projection.'
        return result
    fit = fit_projection(history.assign(is_observed=True, is_imputed=False), cutoff)
    if fit is None:
        result['message'] = f'Monthly projections need at least {MIN_OBSERVATIONS} real observations spanning {MIN_SPAN_MONTHS} months.'
        return result
    months = pd.period_range(cutoff.to_period('M') + 1, periods=6, freq='M').to_timestamp()
    predicted = predict_depth(fit, months)
    current_month = cutoff.to_period('M').to_timestamp()
    age = int(_month_number([current_month])[0] - _month_number([fit['origin']])[0])
    result.update(status='projection', forecast_start=months[0].strftime('%Y-%m'),
                  forecast_end=months[-1].strftime('%Y-%m'),
                  last_observed_date=fit['origin'].date().isoformat(), data_age_months=age,
                  feature_cutoff=fit['origin'].date().isoformat(),
                  estimated_current_gwl=round(float(predict_depth(fit, [current_month])[0]), 4),
                  last_observed_gwl=fit['last_observed_gwl'],
                  forecast=[{'month': month.strftime('%Y-%m'), 'date': month.date().isoformat(),
                             'predicted_gwl': round(float(depth), 4)} for month, depth in zip(months, predicted)],
                  fit_details={'observed_months': fit['observation_count'],
                               'history_start': fit['history_start'], 'history_end': fit['origin'].date().isoformat(),
                               'annual_seasonality': fit['seasonal'],
                               'trend_m_per_year': float(fit['coefficients'][1]),
                               'trend_damping_months': TREND_DAMPING_MONTHS,
                               'history_sha256': fit['history_sha256']})
    return finite_json(result)


def forecast_next_six_months(district_id, as_of=None):
    # The seasonal fit now provides only the estimated current groundwater base.
    # Six future points are produced by the weather-conditioned monthly model.
    from models.climate_forecast import forecast_next_six_months as climate_forecast
    return climate_forecast(district_id, as_of)
