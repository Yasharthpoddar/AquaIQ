"""Twelve-month climate-conditioned XGBoost forecasting pipeline.

Predicts 12 consecutive monthly groundwater-depth changes (M+1 through M+12)
conditioned on rainfall, temperature, and evapotranspiration.
Uses a separate 12-month model checkpoint, explicit future weather policy,
and leakage-safe chronological evaluation with a 12-month embargo.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

import numpy as np
import pandas as pd

from db.connection import finite_json
from models.climate_inputs import (forecast_weather, monthly_features,
                                  MONTHLY_FEATURE_COLUMNS, WEATHER_UNITS)
from models.ensemble import CONFIG, _as_of, _completed_feature_month, feature_generation, select_evidence
from models.monthly_projection import (fit_projection, predict_depth, _design,
                                       _observed_history, _month_number,
                                       MIN_OBSERVATIONS, MIN_SPAN_MONTHS, TREND_DAMPING_MONTHS)
from models.xgboost_model import (observed_mask, sha256_file, _json_hash,
                                 _write_json, load_feature_matrix, metrics, DEFAULT_TRAIN_CUTOFF)
from models.climate_forecast import origin_inputs, feature_rows

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_PATH = ROOT / 'models/checkpoints/aquaiq_climate_12m.json'
MODEL_VERSION = '1.0-climate-conditioned-12m-xgb'
PRODUCT_NAME = 'climate_informed_12m_forecast'
HORIZONS_MONTHS = list(range(1, 13))
FEATURES = ['origin_gwl', 'origin_gwl_lag_3mo', 'origin_gwl_lag_6mo',
            'origin_rainfall', 'origin_temperature', 'origin_evapotranspiration'] + MONTHLY_FEATURE_COLUMNS
UNITS = {'gwl': 'm_bgl', **WEATHER_UNITS}
PARAMETERS = {'n_estimators': 240, 'max_depth': 3, 'learning_rate': .04,
              'min_child_weight': 30, 'reg_lambda': 20., 'reg_alpha': .1,
              'subsample': .85, 'colsample_bytree': .9, 'random_state': 42,
              'n_jobs': 4, 'tree_method': 'hist', 'objective': 'reg:squarederror'}
_CACHE = {}


def prepare_pairs(frame):
    """Join observed labels at t+h calendar months (h=1..12) with complete weather paths."""
    required = {'district_id', 'date', 'gwl_current', 'rainfall_current',
                'temperature', 'evapotranspiration'}
    if required - set(frame):
        raise ValueError(f'12-month climate training fields missing: {sorted(required - set(frame))}')
    frame = frame.copy()
    frame['date'] = pd.to_datetime(frame.date)
    if frame.duplicated(['district_id', 'date']).any():
        raise ValueError('Duplicate district-month keys cannot form monthly labels.')
    if frame.date.isna().any() or (frame.date.dt.day != 1).any():
        raise ValueError('Training requires calendar month starts.')
    observed = observed_mask(frame) & np.isfinite(frame.gwl_current) & (frame.gwl_current >= 0)
    origins = frame.loc[observed].copy().rename(columns={'date': 'origin_date'})
    target = frame.loc[observed, ['district_id', 'date', 'gwl_current']].rename(
        columns={'date': 'target_date', 'gwl_current': 'actual_gwl'})
    weather = frame[['district_id', 'date', 'rainfall_current', 'temperature', 'evapotranspiration']]
    pairs = []
    for horizon in HORIZONS_MONTHS:
        rows = origins.copy()
        rows['target_date'] = rows.origin_date + pd.DateOffset(months=horizon)
        rows = rows.merge(target, on=['district_id', 'target_date'], how='inner', validate='one_to_one')
        for step in range(1, horizon + 1):
            lookup = weather.copy()
            lookup['origin_date'] = lookup.date - pd.DateOffset(months=step)
            lookup = lookup.drop(columns='date').rename(columns={
                'rainfall_current': f'rain_{step}', 'temperature': f'temp_{step}',
                'evapotranspiration': f'et_{step}'})
            rows = rows.merge(lookup, on=['district_id', 'origin_date'], how='left', validate='one_to_one')
        future_columns = [f'{field}_{step}' for step in range(1, horizon + 1) for field in ('rain', 'temp', 'et')]
        valid = np.isfinite(rows[future_columns].to_numpy()).all(axis=1)
        valid &= np.isfinite(rows[['rainfall_current', 'temperature', 'evapotranspiration']].to_numpy()).all(axis=1)
        valid &= (rows[[f'{field}_{step}' for step in range(1, horizon + 1) for field in ('rain', 'et')]] >= 0).all(axis=1)
        rows = rows.loc[valid].copy()
        rows['origin_gwl'] = rows.gwl_current
        for lag in (3, 6):
            rows[f'origin_gwl_lag_{lag}mo'] = rows.get(f'gwl_lag_{lag}mo', np.nan)
        for source, name in [('rainfall_current', 'rainfall'), ('temperature', 'temperature'), ('evapotranspiration', 'evapotranspiration')]:
            rows['origin_' + name] = rows[source]
        rows['horizon_months'] = float(horizon)
        for prefix, dates in [('origin', rows.origin_date), ('target', rows.target_date)]:
            phase = 2 * np.pi * dates.dt.month / 12
            rows[prefix + '_month_sin'], rows[prefix + '_month_cos'] = np.sin(phase), np.cos(phase)
        rows['target_rainfall'], rows['target_temperature'] = rows[f'rain_{horizon}'], rows[f'temp_{horizon}']
        rows['target_evapotranspiration'] = rows[f'et_{horizon}']
        rows['cumulative_rainfall'] = rows[[f'rain_{step}' for step in range(1, horizon + 1)]].sum(axis=1)
        rows['cumulative_evapotranspiration'] = rows[[f'et_{step}' for step in range(1, horizon + 1)]].sum(axis=1)
        rows['mean_temperature'] = rows[[f'temp_{step}' for step in range(1, horizon + 1)]].mean(axis=1)
        rows['target_delta'] = rows.actual_gwl - rows.origin_gwl
        pairs.append(rows[['district_id', 'origin_date', 'target_date', 'actual_gwl', 'target_delta'] + FEATURES])
    result = pd.concat(pairs, ignore_index=True)
    result.attrs.update(frame.attrs)
    return result


def split_pairs(pairs, train_cutoff=DEFAULT_TRAIN_CUTOFF):
    """Split pairs applying a strict 12-month temporal embargo."""
    cutoff = pd.Timestamp(train_cutoff)
    first_origin = (cutoff.to_period('M') + 13).to_timestamp()
    train = pairs.loc[pairs.target_date <= cutoff].copy()
    test = pairs.loc[pairs.origin_date >= first_origin].copy()
    return train, test


def evaluate_assumed_weather(model, frame, pairs):
    """Held-out weather is replaced by origin-available assumptions for all 12 horizons."""
    weather_frames = {key: values.copy() for key, values in frame.groupby('district_id')}
    records, skipped = [], 0
    for (district_id, origin), labels in pairs.groupby(['district_id', 'origin_date'], sort=True):
        district = weather_frames[district_id]
        cutoff = pd.Timestamp(origin) + pd.offsets.MonthEnd(0)
        weather = forecast_weather(district, cutoff, months=12)
        depth = float(labels.iloc[0].origin_gwl)
        inputs, _ = origin_inputs(district, origin, cutoff, depth)
        if weather['status'] != 'available' or inputs is None:
            skipped += len(labels)
            continue
        rows = feature_rows(origin, weather['path'], inputs)
        prediction = np.maximum(0., depth + model.predict(rows))
        known = district.loc[(pd.to_datetime(district.date) <= origin) & observed_mask(district)].sort_values('date').set_index('date').gwl_current
        for label in labels.itertuples():
            horizon = int(label.horizon_months)
            same_month = known[known.index.month == label.target_date.month]
            seasonal = float(same_month.iloc[-1]) if len(same_month) else np.nan
            records.append({'district_id': district_id, 'origin_date': origin, 'target_date': label.target_date,
                            'horizon': horizon, 'actual': label.actual_gwl,
                            'predicted': float(prediction[horizon - 1]), 'persistence': depth, 'seasonal': seasonal})
    table = pd.DataFrame(records)
    if table.empty:
        return {'status': 'unavailable', 'n': 0, 'skipped_labels': skipped}

    def summarize(part):
        paired_seasonal = part.loc[np.isfinite(part.seasonal)]
        m_xgb = metrics(part.actual, part.predicted)
        m_pers = metrics(part.actual, part.persistence)
        res = {
            'n': len(part),
            'districts': int(part.district_id.nunique()),
            'xgboost': m_xgb,
            'persistence': m_pers,
            'diff_vs_persistence': {
                'mae_diff_m': round(float(m_xgb['mae_m'] - m_pers['mae_m']), 4),
                'rmse_diff_m': round(float(m_xgb['rmse_m'] - m_pers['rmse_m']), 4),
                'xgb_beats_persistence': bool(m_xgb['mae_m'] < m_pers['mae_m'])
            }
        }
        if len(paired_seasonal) > 0:
            m_paired_xgb = metrics(paired_seasonal.actual, paired_seasonal.predicted)
            m_seas = metrics(paired_seasonal.actual, paired_seasonal.seasonal)
            res['seasonal_paired'] = {
                'n': len(paired_seasonal),
                'xgboost': m_paired_xgb,
                'baseline': m_seas,
                'diff_vs_seasonal': {
                    'mae_diff_m': round(float(m_paired_xgb['mae_m'] - m_seas['mae_m']), 4),
                    'rmse_diff_m': round(float(m_paired_xgb['rmse_m'] - m_seas['rmse_m']), 4),
                    'xgb_beats_seasonal': bool(m_paired_xgb['mae_m'] < m_seas['mae_m'])
                }
            }
        else:
            res['seasonal_paired'] = None
        return res

    return {
        'status': 'evaluated_assumed_weather',
        'skipped_labels': skipped,
        **summarize(table),
        'origin_start': table.origin_date.min().date().isoformat(),
        'origin_end': table.origin_date.max().date().isoformat(),
        'target_start': table.target_date.min().date().isoformat(),
        'target_end': table.target_date.max().date().isoformat(),
        'by_district': {str(district): summarize(part) for district, part in table.groupby('district_id', sort=True)},
        'by_horizon': {str(h): summarize(table.loc[table.horizon == h]) if (table.horizon == h).any() else {'n': 0}
                       for h in HORIZONS_MONTHS},
        'weather_policy': 'Historical same-month weather means available at each origin, not realized future weather.',
        'groundwater_origin_policy': 'Observed origins; this does not validate estimated current levels after multi-year gaps.'
    }


def _load_files(pointer, checkpoint, generation=None):
    assets = []
    for name in ['model_path', 'card_path']:
        path = (checkpoint.parent / pointer[name]).resolve()
        if not path.is_relative_to(checkpoint.parent.resolve()):
            raise ValueError('12-month climate model asset path escapes checkpoint directory.')
        assets.append(path)
    model_path, card_path = assets
    if sha256_file(model_path) != pointer['model_sha256'] or sha256_file(card_path) != pointer['card_sha256']:
        raise ValueError('12-month climate checkpoint/card checksum mismatch.')
    card = json.loads(card_path.read_text(encoding='utf-8'))
    if card.get('bundle_schema_version') != 1 or card.get('version') != MODEL_VERSION:
        raise ValueError('12-month climate model/card version is incompatible.')
    if card.get('features') != FEATURES or card.get('feature_schema_sha256') != _json_hash(FEATURES):
        raise ValueError('12-month climate feature schema differs from serving.')
    if card.get('units') != UNITS or card.get('horizons_months') != HORIZONS_MONTHS or card.get('target') != 'gwl_change_from_origin':
        raise ValueError('12-month climate units/horizons/target differ from serving.')
    if (not card.get('feature_generation_id') or (generation and card['feature_generation_id'] != generation)
            or card.get('data_source') in (None, 'synthetic', 'unknown')
            or card.get('model_sha256') != pointer['model_sha256'] or not card.get('train_target_cutoff')):
        raise ValueError('12-month climate bundle has incompatible data provenance.')
    if pd.Timestamp(card.get('max_train_target_date')) > pd.Timestamp(card['train_target_cutoff']) or not card.get('max_train_target_date'):
        raise ValueError('12-month climate training labels extend beyond the model cutoff.')
    import xgboost as xgb
    model = xgb.XGBRegressor()
    model.load_model(str(model_path))
    if model.get_booster().feature_names != FEATURES or model.n_features_in_ != len(FEATURES):
        raise ValueError('Stored 12-month model feature order differs from its card.')
    return model, card


def load_bundle(checkpoint=None, expected_generation=None):
    checkpoint = Path(checkpoint or CHECKPOINT_PATH)
    generation = expected_generation or feature_generation()
    try:
        pointer = json.loads(checkpoint.read_text(encoding='utf-8'))
        if pointer.get('bundle_schema_version') != 1:
            raise ValueError('Unverified 12-month climate checkpoint.')
        paths = [(checkpoint.parent / pointer[name]).resolve() for name in ['model_path', 'card_path']]
        if any(not path.is_relative_to(checkpoint.parent.resolve()) for path in paths):
            raise ValueError('12-month climate model asset path escapes checkpoint directory.')
        key = (str(checkpoint.resolve()), generation,
               tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in [checkpoint] + paths))
        if key not in _CACHE:
            loaded = _load_files(pointer, checkpoint, generation)
            _CACHE.clear()
            _CACHE[key] = loaded
        return _CACHE[key]
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError('12-month climate model is unavailable or incompatible; train a verified bundle.') from error


def publish_bundle(model, card, checkpoint=None):
    checkpoint = Path(checkpoint or CHECKPOINT_PATH)
    directory = checkpoint.parent / 'climate_12m_bundles' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:10])
    directory.mkdir(parents=True, exist_ok=False)
    model_path, card_path = directory / 'model.json', directory / 'model_card.json'
    model.save_model(str(model_path))
    card = {**card, 'bundle_schema_version': 1, 'model_sha256': sha256_file(model_path)}
    _write_json(card_path, card)
    card_sha = sha256_file(card_path)
    card['card_sha256'] = card_sha
    pointer = {'bundle_schema_version': 1, 'model_path': model_path.relative_to(checkpoint.parent).as_posix(),
               'card_path': card_path.relative_to(checkpoint.parent).as_posix(),
               'model_sha256': card['model_sha256'], 'card_sha256': card_sha}
    _load_files(pointer, checkpoint, card['feature_generation_id'])
    _write_json(checkpoint, pointer)
    _write_json(checkpoint.with_name(checkpoint.stem + '_model_card.json'), card)
    return card


def train(frame, cutoff=DEFAULT_TRAIN_CUTOFF, checkpoint=None, parameters=None):
    if not frame.attrs.get('feature_generation_id') or frame.attrs.get('data_source') in (None, 'unknown', 'synthetic'):
        raise ValueError('12-month climate training requires verified real features.')
    pairs = prepare_pairs(frame)
    training, heldout = split_pairs(pairs, cutoff)
    if training.empty or heldout.empty or set(training.horizon_months.astype(int)) != set(HORIZONS_MONTHS):
        raise ValueError('Training and independent observed labels are required for all twelve horizons.')
    import xgboost as xgb
    settings = {**PARAMETERS, **(parameters or {})}
    model = xgb.XGBRegressor(**settings)
    print(f'Training 12-month climate XGBoost on {len(training):,} observed pairs across horizons 1..12.', flush=True)
    model.fit(training[FEATURES], training.target_delta)
    evaluation = evaluate_assumed_weather(model, frame, heldout)
    if evaluation['status'] != 'evaluated_assumed_weather':
        raise ValueError('No usable independent assumed-weather evaluation labels for 12 months.')
    importance = {name: float(value) for name, value in zip(FEATURES, model.feature_importances_)}
    card = {'version': MODEL_VERSION, 'features': FEATURES, 'feature_schema_sha256': _json_hash(FEATURES),
            'units': UNITS, 'target': 'gwl_change_from_origin', 'horizons_months': HORIZONS_MONTHS,
            'created_at': datetime.now(timezone.utc).isoformat(), 'parameters': settings,
            'feature_generation_id': frame.attrs['feature_generation_id'], 'data_source': frame.attrs['data_source'],
            'data_sha256': frame.attrs.get('data_sha256'), 'train_target_cutoff': str(pd.Timestamp(cutoff).date()),
            'max_train_target_date': str(training.target_date.max().date()),
            'max_train_origin': str(training.origin_date.max().date()),
            'n_train_observed_pairs': len(training), 'training_districts': int(training.district_id.nunique()),
            'training_counts_by_horizon': {str(int(h)): int(n) for h, n in training.groupby('horizon_months').size().items()},
            'feature_importance': importance, 'evaluation': evaluation,
            'evaluation_protocol': {
                'embargo_months': 12,
                'training_weather': 'Realized historical weather conditions as conditional covariates.',
                'evaluation_weather': 'Climatology calculated only from origin-available historical weather; future weather observations excluded.',
                'target_policy': 'Both origin and target groundwater values explicitly observed; exact calendar-date joins.'
            },
            'validation_assessment': {
                'status': 'experimental_climate_12m_outlook',
                'sufficient_for_operational_use': False,
                'limitations': [
                    'Current groundwater is estimated when observations are old; training and holdout use observed origins.',
                    'Future weather uses historical monthly averages available at origin, not live weather predictions.',
                    'Pumping and extraction are not included in the feature set.',
                    'Empirical evaluation shows persistence and seasonal-naive baselines match or outperform XGBoost at several horizons.',
                    'Experimental research pipeline; unvalidated for operational water allocation.'
                ]
            }}
    return model, publish_bundle(model, card, checkpoint)


def forecast_from_evidence(evidence, weather_override=None):
    """Forecast exactly 12 monthly points from district evidence and origin weather assumptions."""
    cutoff = _as_of(evidence['as_of'])
    origin = cutoff.to_period('M').to_timestamp()
    history = _observed_history(evidence['history'], cutoff)
    last_obs_date = pd.Timestamp(history.date.iloc[-1]).date().isoformat() if len(history) else None

    result = {
        'product': PRODUCT_NAME,
        'model_version': MODEL_VERSION,
        'district_id': evidence['district_id'],
        'status': 'insufficient_data',
        'forecast': [],
        'as_of': cutoff.date().isoformat(),
        'forecast_origin': cutoff.date().isoformat(),
        'timezone': 'Asia/Kolkata',
        'horizon_months': 12,
        'forecast_horizon': 'next twelve full calendar months',
        'units': 'm_bgl',
        'last_observed_date': last_obs_date,
        'estimate_type': evidence['estimate_type'],
        'source_zone': evidence['zone'],
        'zone_fallback_reason': evidence['reason'],
        'feature_generation': evidence['generation'],
        'projection_method': 'climate_conditioned_xgboost_12m',
        'input_features': FEATURES,
        'estimated_current_gwl': None,
        'data_age_months': None,
        'computed_at': datetime.now(timezone.utc).isoformat(),
        'weather_basis': None,
        'validation': {
            'status': 'experimental_climate_12m_outlook',
            'sufficient_for_operational_use': False
        },
        'limitations': [
            'Rainfall, temperature and evapotranspiration are inputs to the 12-month XGBoost model.',
            'Future weather uses explicit historical climatology assumptions; it is not a live weather forecast.',
            'Current groundwater depth is estimated across the unobserved observation gap; fresh measurements are needed.',
            'Pumping and groundwater extraction are not included in this model.',
            'Evaluation shows persistence and seasonal-naive baselines outperform XGBoost at several horizons.',
            'The 12-month climate-conditioned outlook is an experimental research prototype and not validated for operational allocation.'
        ]
    }

    if evidence['estimate_type'] == 'insufficient_data':
        result['message'] = 'Not enough district or zone observations for a 12-month monthly projection.'
        return result

    fit = fit_projection(history.assign(is_observed=True, is_imputed=False), cutoff)
    if fit is None:
        result['message'] = f'Monthly projections need at least {MIN_OBSERVATIONS} real observations spanning {MIN_SPAN_MONTHS} months.'
        return result

    try:
        model, card = load_bundle(expected_generation=evidence['generation'])
    except Exception as exc:
        result.update(status='model_unavailable', message=str(exc))
        return result

    if cutoff < pd.Timestamp(card['train_target_cutoff']):
        result.update(status='insufficient_data', message='This 12-month checkpoint was trained after the requested cutoff; causal prediction is unavailable.')
        return result

    weather = forecast_weather(evidence['frame'], cutoff, months=12, overrides=weather_override)
    metadata = weather['metadata']
    result['weather_basis'] = {
        **metadata,
        'method': 'historical_monthly_climatology' if weather_override is None else 'specified_weather_scenario',
        'latest_usable_weather_date': metadata.get('latest_historical_weather_date'),
        'description': ('Assumed future monthly rainfall, temperature and evapotranspiration from historical same-month averages.'
                        if weather_override is None else 'Specified future monthly weather scenario.')
    }

    if weather['status'] != 'available':
        result.update(status='insufficient_data',
                      message='Not enough historical rainfall, temperature or evapotranspiration for all 12 future months.')
        return result

    def estimate(month, require_observed=False):
        rows = evidence['frame'].loc[pd.to_datetime(evidence['frame'].date) == month]
        if len(rows) and month <= _completed_feature_month(cutoff):
            value = pd.to_numeric(pd.Series([rows.iloc[-1].gwl_current]), errors='coerce').iloc[0]
            if np.isfinite(value) and (not require_observed or bool(observed_mask(rows).iloc[-1])):
                return float(value)
        if month >= fit['origin']:
            return float(predict_depth(fit, [month])[0])
        return float(max(0., (_design([month], fit['origin'], fit['seasonal']) @ fit['coefficients'] + fit['level_offset'])[0]))

    current = estimate(origin, require_observed=True)
    lags = {lag: estimate(origin - pd.DateOffset(months=lag)) for lag in (3, 6)}
    inputs, origin_basis = origin_inputs(evidence['frame'], origin, cutoff, current, lags)
    result['weather_basis']['origin_weather'] = origin_basis
    if inputs is None:
        result.update(status='insufficient_data',
                      message='Origin-month weather inputs are unavailable for the 12-month monthly model.')
        return result

    rows = feature_rows(origin, weather['path'], inputs)
    deltas = np.asarray(model.predict(rows), dtype=float)
    if len(deltas) != 12 or not np.isfinite(deltas).all():
        raise RuntimeError('12-month climate model returned invalid depth changes.')

    depths = np.maximum(0., current + deltas)
    path = weather['path']
    age = int(_month_number([origin])[0] - _month_number([fit['origin']])[0])

    result.update(
        status='forecast',
        forecast_start=path.date.iloc[0].strftime('%Y-%m'),
        forecast_end=path.date.iloc[-1].strftime('%Y-%m'),
        last_observed_date=fit['origin'].date().isoformat(),
        last_observed_gwl=fit['last_observed_gwl'],
        data_age_months=age,
        feature_cutoff=fit['origin'].date().isoformat(),
        estimated_current_gwl=round(current, 4),
        current_depth_basis='estimated_from_historical_groundwater' if origin > fit['origin'] else 'observed_month',
        model_sha256=card['model_sha256'],
        model_train_target_cutoff=card['train_target_cutoff'],
        model_validation=card.get('validation_assessment', {}),
        forecast=[
            {
                'month': row.date.strftime('%Y-%m'),
                'date': row.date.date().isoformat(),
                'horizon': horizon_num,
                'predicted_gwl': round(float(depth), 4),
                'delta_from_current_m': round(float(depth - current), 4),
                'weather': {
                    'rainfall_mm': round(float(row.rainfall), 4),
                    'temperature_c': round(float(row.temperature), 4),
                    'evapotranspiration_mm': round(float(row.evapotranspiration), 4)
                }
            }
            for horizon_num, (row, depth) in enumerate(zip(path.itertuples(), depths), start=1)
        ]
    )
    return finite_json(result)


def forecast_next_twelve_months(district_id, as_of=None, weather_override=None):
    """Entrypoint to forecast next twelve months for a given district."""
    return forecast_from_evidence(select_evidence(district_id, as_of), weather_override)


def evaluate_saved_checkpoint(frame, checkpoint=None):
    """Evaluate a verified 12-month bundle at its recorded cutoff without retraining."""
    generation = frame.attrs.get('feature_generation_id')
    if not generation or frame.attrs.get('data_source') in (None, 'unknown', 'synthetic'):
        raise ValueError('12-month climate evaluation requires verified real features.')
    model, card = load_bundle(checkpoint, expected_generation=generation)
    cutoff = card['train_target_cutoff']
    _, heldout = split_pairs(prepare_pairs(frame), cutoff)
    return {'evaluation_only': True, 'created_at': datetime.now(timezone.utc).isoformat(),
            'version': card['version'], 'model_sha256': card['model_sha256'],
            'feature_generation_id': generation, 'data_source': frame.attrs['data_source'],
            'data_sha256': frame.attrs.get('data_sha256'), 'train_target_cutoff': cutoff,
            'evaluation_protocol': {
                'embargo_months': 12,
                'cutoff_source': 'verified_checkpoint_model_card',
                'first_eligible_origin': str((pd.Timestamp(cutoff).to_period('M') + 13).start_time.date())
            },
            'evaluation': evaluate_assumed_weather(model, frame, heldout),
            'validation_assessment': card.get('validation_assessment')}


def _validate_cli_outputs(parser, checkpoint, report, candidate=False, evaluation=False):
    """Refuse report/candidate aliases that could replace active data or model assets."""
    active_6m = (ROOT / 'models/checkpoints/aquaiq_monthly_climate.json').resolve()
    active_12m = CHECKPOINT_PATH.resolve()
    historical = (ROOT / CONFIG['paths']['xgboost_checkpoint']).resolve()
    source = Path(checkpoint or CHECKPOINT_PATH).resolve()
    training_report = (ROOT / 'reports/climate_forecast_12m_evaluation.json').resolve()
    protected = {
        active_6m, active_6m.with_name(active_6m.stem + '_model_card.json'),
        active_12m, active_12m.with_name(active_12m.stem + '_model_card.json'),
        historical, historical.with_name(historical.stem + '_model_card.json'),
        (ROOT / 'data/processed/feature_manifest.json').resolve(),
        (ROOT / 'data/processed/features_matrix.csv').resolve()
    }
    immutable = {active_6m.parent / 'climate_bundles', active_12m.parent / 'climate_12m_bundles', historical.parent / 'bundles'}
    if candidate:
        protected.add(training_report)
        writes = [source, source.with_name(source.stem + '_model_card.json'), report.resolve()]
    else:
        writes = [report.resolve()]
        if evaluation:
            protected.update({source, source.with_name(source.stem + '_model_card.json'), training_report})
    if len(writes) != len(set(writes)):
        parser.error('Checkpoint, model card and report output paths must be distinct.')
    for path in writes:
        if path.suffix.lower() != '.json':
            parser.error('Checkpoint and report outputs must use a .json extension.')
        if path in protected or any(path.is_relative_to(directory) for directory in immutable):
            parser.error('Output would overwrite protected input, active model or training report.')


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--eval', action='store_true', help='Evaluate a verified bundle without fitting or publishing.')
    mode.add_argument('--candidate-checkpoint', type=Path,
                      help='Train into a separate candidate pointer instead of the active 12-month checkpoint.')
    parser.add_argument('--checkpoint', type=Path, help='Input bundle pointer for --eval; defaults to the active 12-month model.')
    parser.add_argument('--train-cutoff', help=f'Training label cutoff (default: {DEFAULT_TRAIN_CUTOFF}); invalid with --eval.')
    parser.add_argument('--output', type=Path, help='JSON report output; evaluation and candidates have separate defaults.')
    args = parser.parse_args(argv)
    if args.eval and args.train_cutoff is not None:
        parser.error('--eval uses the verified model card cutoff; --train-cutoff cannot be supplied.')
    if args.checkpoint is not None and not args.eval:
        parser.error('--checkpoint is an evaluation input; use --candidate-checkpoint for training experiments.')
    checkpoint = args.checkpoint if args.eval else args.candidate_checkpoint
    if args.eval:
        default_report = ROOT / 'reports/climate_forecast_12m_saved_evaluation.json'
    elif args.candidate_checkpoint is not None:
        default_report = checkpoint.with_name(checkpoint.stem + '_evaluation.json')
    else:
        default_report = ROOT / 'reports/climate_forecast_12m_evaluation.json'
    report = args.output or default_report
    _validate_cli_outputs(parser, checkpoint, report,
                          candidate=args.candidate_checkpoint is not None, evaluation=args.eval)
    frame = load_feature_matrix()
    if args.eval:
        result = evaluate_saved_checkpoint(frame, checkpoint)
        summary = result
    else:
        _, result = train(frame, args.train_cutoff or DEFAULT_TRAIN_CUTOFF, checkpoint=checkpoint)
        summary = {
            'training_pairs': result['n_train_observed_pairs'],
            'evaluation': result['evaluation'],
            'feature_importance': result['feature_importance']
        }
    _write_json(report, result)
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
    return result


if __name__ == '__main__':
    main()
