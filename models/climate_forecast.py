"""Monthly conditional XGBoost outlook with explicit future weather inputs.

The model learns depth changes conditional on rainfall, temperature and ET.
Historical realized weather is used to fit that relationship. Evaluation and
serving instead use weather assumptions available at the forecast origin.
An old groundwater reading still needs a separately labelled current estimate.
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
from models.monthly_projection import fit_projection, predict_depth, _design, projection_from_evidence
from models.xgboost_model import (observed_mask, sha256_file, _json_hash,
                                 _write_json, load_feature_matrix, metrics, DEFAULT_TRAIN_CUTOFF)

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_PATH = ROOT / 'models/checkpoints/aquaiq_monthly_climate.json'
MODEL_VERSION = '1.0-climate-conditioned-monthly-xgb'
FEATURES = ['origin_gwl', 'origin_gwl_lag_3mo', 'origin_gwl_lag_6mo',
            'origin_rainfall', 'origin_temperature', 'origin_evapotranspiration'] + MONTHLY_FEATURE_COLUMNS
UNITS = {'gwl': 'm_bgl', **WEATHER_UNITS}
PARAMETERS = {'n_estimators': 240, 'max_depth': 3, 'learning_rate': .04,
              'min_child_weight': 30, 'reg_lambda': 20., 'reg_alpha': .1,
              'subsample': .85, 'colsample_bytree': .9, 'random_state': 42,
              'n_jobs': 4, 'tree_method': 'hist', 'objective': 'reg:squarederror'}
_CACHE = {}


def prepare_pairs(frame):
    """Join observed labels at t+h calendar months with complete weather paths."""
    required = {'district_id', 'date', 'gwl_current', 'rainfall_current',
                'temperature', 'evapotranspiration'}
    if required - set(frame):
        raise ValueError(f'Monthly climate training fields missing: {sorted(required-set(frame))}')
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
    for horizon in range(1, 7):
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
        for source, name in [('rainfall_current','rainfall'), ('temperature','temperature'), ('evapotranspiration','evapotranspiration')]:
            rows['origin_'+name] = rows[source]
        rows['horizon_months'] = float(horizon)
        for prefix, dates in [('origin', rows.origin_date), ('target', rows.target_date)]:
            phase = 2 * np.pi * dates.dt.month / 12
            rows[prefix+'_month_sin'], rows[prefix+'_month_cos'] = np.sin(phase), np.cos(phase)
        rows['target_rainfall'], rows['target_temperature'] = rows[f'rain_{horizon}'], rows[f'temp_{horizon}']
        rows['target_evapotranspiration'] = rows[f'et_{horizon}']
        rows['cumulative_rainfall'] = rows[[f'rain_{step}' for step in range(1,horizon+1)]].sum(axis=1)
        rows['cumulative_evapotranspiration'] = rows[[f'et_{step}' for step in range(1,horizon+1)]].sum(axis=1)
        rows['mean_temperature'] = rows[[f'temp_{step}' for step in range(1,horizon+1)]].mean(axis=1)
        rows['target_delta'] = rows.actual_gwl - rows.origin_gwl
        pairs.append(rows[['district_id', 'origin_date', 'target_date', 'actual_gwl', 'target_delta']+FEATURES])
    result = pd.concat(pairs, ignore_index=True)
    result.attrs.update(frame.attrs)
    return result


def split_pairs(pairs, train_cutoff=DEFAULT_TRAIN_CUTOFF):
    cutoff = pd.Timestamp(train_cutoff)
    first_origin = (cutoff.to_period('M') + 7).to_timestamp()
    train = pairs.loc[pairs.target_date <= cutoff].copy()
    test = pairs.loc[pairs.origin_date >= first_origin].copy()
    return train, test


def origin_inputs(frame, origin, cutoff, depth, lags=None):
    """Use known origin weather, or label a climatology assumption if missing."""
    origin = pd.Timestamp(origin).to_period('M').to_timestamp()
    available = _completed_feature_month(pd.Timestamp(cutoff))
    current = frame.loc[pd.to_datetime(frame.date) == origin]
    row = current.iloc[-1] if len(current) and origin <= available else None
    weather_names = ['rainfall_current', 'temperature', 'evapotranspiration']
    present = pd.to_numeric(pd.Series({name: row.get(name, np.nan) for name in weather_names}), errors='coerce') if row is not None else None
    if present is not None and np.isfinite(present.to_numpy()).all():
        values = {name: float(row[name]) for name in weather_names}
        basis = 'historical_origin_weather'
    else:
        # Estimate this month's conditions using information from prior months.
        reference = origin - pd.Timedelta(days=1)
        assumed = forecast_weather(frame, min(reference, pd.Timestamp(cutoff)), months=1)
        if assumed['status'] != 'available':
            return None, {'method': 'unavailable_origin_weather'}
        first = assumed['path'].iloc[0]
        values = {'rainfall_current': first.rainfall, 'temperature': first.temperature,
                  'evapotranspiration': first.evapotranspiration}
        basis = 'historical_monthly_climatology'
    result = {'origin_gwl': float(depth), 'origin_rainfall': float(values['rainfall_current']),
              'origin_temperature': float(values['temperature']),
              'origin_evapotranspiration': float(values['evapotranspiration'])}
    for lag in (3, 6):
        result[f'origin_gwl_lag_{lag}mo'] = float(lags[lag]) if lags and lag in lags else float(row.get(f'gwl_lag_{lag}mo', np.nan)) if row is not None else np.nan
    return result, {'method': basis, 'rainfall_mm': result['origin_rainfall'],
                    'temperature_c': result['origin_temperature'],
                    'evapotranspiration_mm': result['origin_evapotranspiration']}


def feature_rows(origin, path, inputs):
    rows = monthly_features(origin, path)
    for name, value in inputs.items():
        rows[name] = value
    result = rows[FEATURES].astype(float)
    if np.isinf(result.to_numpy()).any():
        raise ValueError('Monthly climate inputs contain infinite values.')
    return result


def evaluate_assumed_weather(model, frame, pairs):
    """Held-out weather is replaced by origin-available assumptions, never truth."""
    weather_frames = {key: values.copy() for key, values in frame.groupby('district_id')}
    records, skipped = [], 0
    for (district_id, origin), labels in pairs.groupby(['district_id', 'origin_date'], sort=True):
        district = weather_frames[district_id]
        cutoff = pd.Timestamp(origin) + pd.offsets.MonthEnd(0)
        weather = forecast_weather(district, cutoff)
        depth = float(labels.iloc[0].origin_gwl)
        inputs, _ = origin_inputs(district, origin, cutoff, depth)
        if weather['status'] != 'available' or inputs is None:
            skipped += len(labels)
            continue
        prediction = np.maximum(0., depth + model.predict(feature_rows(origin, weather['path'], inputs)))
        known = district.loc[(pd.to_datetime(district.date) <= origin) & observed_mask(district)].sort_values('date').set_index('date').gwl_current
        for label in labels.itertuples():
            horizon = int(label.horizon_months)
            same_month = known[known.index.month == label.target_date.month]
            seasonal = float(same_month.iloc[-1]) if len(same_month) else np.nan
            records.append({'district_id': district_id, 'origin_date': origin, 'target_date': label.target_date,
                            'horizon': horizon, 'actual': label.actual_gwl,
                            'predicted': float(prediction[horizon-1]), 'persistence': depth, 'seasonal': seasonal})
    table = pd.DataFrame(records)
    if table.empty:
        return {'status': 'unavailable', 'n': 0, 'skipped_labels': skipped}
    def summarize(part):
        paired = part.loc[np.isfinite(part.seasonal)]
        return {'n': len(part), 'districts': int(part.district_id.nunique()),
                'xgboost': metrics(part.actual, part.predicted),
                'persistence': metrics(part.actual, part.persistence),
                'seasonal_paired': {'n': len(paired),
                    'xgboost': metrics(paired.actual, paired.predicted) if len(paired) else None,
                    'baseline': metrics(paired.actual, paired.seasonal) if len(paired) else None}}
    return {'status': 'evaluated_assumed_weather', 'skipped_labels': skipped, **summarize(table),
            'origin_start': table.origin_date.min().date().isoformat(),
            'origin_end': table.origin_date.max().date().isoformat(),
            'target_start': table.target_date.min().date().isoformat(),
            'target_end': table.target_date.max().date().isoformat(),
            'by_district': {str(district): summarize(part) for district, part in table.groupby('district_id', sort=True)},
            'by_horizon': {str(h): summarize(table.loc[table.horizon == h]) if (table.horizon == h).any() else {'n':0}
                           for h in range(1,7)},
            'weather_policy': 'Historical same-month weather means available at each origin, not realized future weather.',
            'groundwater_origin_policy': 'Observed origins; this does not validate estimated current levels after multi-year gaps.'}


def _load_files(pointer, checkpoint, generation=None):
    assets = []
    for name in ['model_path', 'card_path']:
        path = (checkpoint.parent / pointer[name]).resolve()
        if not path.is_relative_to(checkpoint.parent.resolve()):
            raise ValueError('Climate model asset path escapes checkpoint directory.')
        assets.append(path)
    model_path, card_path = assets
    if sha256_file(model_path) != pointer['model_sha256'] or sha256_file(card_path) != pointer['card_sha256']:
        raise ValueError('Monthly climate checkpoint/card checksum mismatch.')
    card = json.loads(card_path.read_text(encoding='utf-8'))
    if card.get('bundle_schema_version') != 1 or card.get('version') != MODEL_VERSION:
        raise ValueError('Monthly climate model/card version is incompatible.')
    if card.get('features') != FEATURES or card.get('feature_schema_sha256') != _json_hash(FEATURES):
        raise ValueError('Monthly climate feature schema differs from serving.')
    if card.get('units') != UNITS or card.get('horizons_months') != list(range(1,7)) or card.get('target') != 'gwl_change_from_origin':
        raise ValueError('Monthly climate units/horizons/target differ from serving.')
    if (not card.get('feature_generation_id') or (generation and card['feature_generation_id'] != generation)
            or card.get('data_source') in (None, 'synthetic', 'unknown')
            or card.get('model_sha256') != pointer['model_sha256'] or not card.get('train_target_cutoff')):
        raise ValueError('Monthly climate bundle has incompatible data provenance.')
    if pd.Timestamp(card.get('max_train_target_date')) > pd.Timestamp(card['train_target_cutoff']) or not card.get('max_train_target_date'):
        raise ValueError('Monthly climate training labels extend beyond the model cutoff.')
    import xgboost as xgb
    model = xgb.XGBRegressor()
    model.load_model(str(model_path))
    if model.get_booster().feature_names != FEATURES or model.n_features_in_ != len(FEATURES):
        raise ValueError('Stored monthly model feature order differs from its card.')
    return model, card


def load_bundle(checkpoint=None, expected_generation=None):
    checkpoint = Path(checkpoint or CHECKPOINT_PATH)
    generation = expected_generation or feature_generation()
    try:
        pointer = json.loads(checkpoint.read_text(encoding='utf-8'))
        if pointer.get('bundle_schema_version') != 1:
            raise ValueError('Unverified monthly climate checkpoint.')
        paths = [(checkpoint.parent / pointer[name]).resolve() for name in ['model_path','card_path']]
        if any(not path.is_relative_to(checkpoint.parent.resolve()) for path in paths):
            raise ValueError('Climate model asset path escapes checkpoint directory.')
        key = (str(checkpoint.resolve()), generation,
               tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in [checkpoint]+paths))
        if key not in _CACHE:
            loaded = _load_files(pointer, checkpoint, generation)
            _CACHE.clear()
            _CACHE[key] = loaded
        return _CACHE[key]
    except (OSError, ValueError, KeyError) as error:
        raise RuntimeError('Monthly climate model is unavailable or incompatible; train a verified bundle.') from error


def publish_bundle(model, card, checkpoint=None):
    checkpoint = Path(checkpoint or CHECKPOINT_PATH)
    directory = checkpoint.parent / 'climate_bundles' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:10])
    directory.mkdir(parents=True, exist_ok=False)
    model_path, card_path = directory/'model.json', directory/'model_card.json'
    model.save_model(str(model_path))
    card = {**card, 'bundle_schema_version': 1, 'model_sha256': sha256_file(model_path)}
    _write_json(card_path, card)
    pointer = {'bundle_schema_version': 1, 'model_path': model_path.relative_to(checkpoint.parent).as_posix(),
               'card_path': card_path.relative_to(checkpoint.parent).as_posix(),
               'model_sha256': card['model_sha256'], 'card_sha256': sha256_file(card_path)}
    _load_files(pointer, checkpoint, card['feature_generation_id'])
    _write_json(checkpoint, pointer)
    _write_json(checkpoint.with_name(checkpoint.stem+'_model_card.json'), card)
    return card


def train(frame, cutoff=DEFAULT_TRAIN_CUTOFF, checkpoint=None, parameters=None):
    if not frame.attrs.get('feature_generation_id') or frame.attrs.get('data_source') in (None,'unknown','synthetic'):
        raise ValueError('Monthly climate training requires verified real features.')
    pairs = prepare_pairs(frame)
    training, heldout = split_pairs(pairs, cutoff)
    if training.empty or heldout.empty or set(training.horizon_months) != set(range(1,7)):
        raise ValueError('Training and independent observed labels are required for all six horizons.')
    import xgboost as xgb
    settings = {**PARAMETERS, **(parameters or {})}
    model = xgb.XGBRegressor(**settings)
    print(f'Training monthly climate XGBoost on {len(training):,} observed pairs.', flush=True)
    model.fit(training[FEATURES], training.target_delta)
    evaluation = evaluate_assumed_weather(model, frame, heldout)
    if evaluation['status'] != 'evaluated_assumed_weather':
        raise ValueError('No usable independent assumed-weather evaluation labels.')
    importance = {name: float(value) for name,value in zip(FEATURES,model.feature_importances_)}
    card = {'version': MODEL_VERSION, 'features': FEATURES, 'feature_schema_sha256': _json_hash(FEATURES),
            'units': UNITS, 'target': 'gwl_change_from_origin', 'horizons_months': list(range(1,7)),
            'created_at': datetime.now(timezone.utc).isoformat(), 'parameters': settings,
            'feature_generation_id': frame.attrs['feature_generation_id'], 'data_source': frame.attrs['data_source'],
            'data_sha256': frame.attrs.get('data_sha256'), 'train_target_cutoff': str(pd.Timestamp(cutoff).date()),
            'max_train_target_date': str(training.target_date.max().date()),
            'max_train_origin': str(training.origin_date.max().date()),
            'n_train_observed_pairs': len(training), 'training_districts': int(training.district_id.nunique()),
            'training_counts_by_horizon': {str(int(h)): int(n) for h,n in training.groupby('horizon_months').size().items()},
            'feature_importance': importance, 'evaluation': evaluation,
            'evaluation_protocol': {'embargo_months':6, 'training_weather':'Realized historical weather conditions as conditional covariates.',
                'evaluation_weather':'Climatology calculated only from origin-available historical weather; future weather observations excluded.',
                'target_policy':'Both origin and target groundwater values explicitly observed; exact calendar-date joins.'},
            'validation_assessment': {'status':'unvalidated_current_projection', 'sufficient_for_operational_use':False,
                'limitations':['Current groundwater is estimated when observations are old; training and holdout use observed origins.',
                    'Future weather is assumed from historical monthly averages, not a live meteorological forecast.',
                    'Pumping/extraction is not included.', 'Some monthly holdouts cover very few districts.',
                    'Historical source publication and revision times are unavailable.']}}
    return model, publish_bundle(model, card, checkpoint)


def forecast_from_evidence(evidence, weather_override=None):
    result = projection_from_evidence(evidence)
    result.update(projection_method='climate_conditioned_xgboost_monthly', model_version=MODEL_VERSION,
                  weather_basis=None, input_features=FEATURES,
                  limitations=['Rainfall, temperature and evapotranspiration are inputs to the monthly XGBoost model.',
                      'Future weather uses explicit assumptions; it is not a live weather forecast.',
                      'Current groundwater depth is estimated across the old observation gap; fresh measurements are needed.',
                      'Pumping/extraction is not included in this forecast.',
                      'The current-period climate-conditioned outlook has not been independently validated.'])
    if not result['forecast']:
        return result
    cutoff = _as_of(evidence['as_of'])
    origin = cutoff.to_period('M').to_timestamp()
    model, card = load_bundle(expected_generation=evidence['generation'])
    if cutoff < pd.Timestamp(card['train_target_cutoff']):
        result.update(status='insufficient_data', forecast=[], estimated_current_gwl=None,
                      message='This monthly checkpoint was trained after the requested cutoff; causal prediction is unavailable.')
        return result
    weather = forecast_weather(evidence['frame'], cutoff, overrides=weather_override)
    metadata = weather['metadata']
    result['weather_basis'] = {**metadata,
        'method':'historical_monthly_climatology' if weather_override is None else 'specified_weather_scenario',
        'latest_usable_weather_date': metadata.get('latest_historical_weather_date'),
        'description':'Assumed future monthly rainfall, temperature and evapotranspiration from historical same-month averages.'
                      if weather_override is None else 'Specified future monthly weather scenario.'}
    if weather['status'] != 'available':
        result.update(status='insufficient_data', forecast=[], estimated_current_gwl=None,
                      message='Not enough historical rainfall, temperature or evapotranspiration for all future months.')
        return result
    fit = fit_projection(evidence['history'], cutoff)
    def estimate(month, require_observed=False):
        rows = evidence['frame'].loc[pd.to_datetime(evidence['frame'].date) == month]
        if len(rows) and month <= _completed_feature_month(cutoff):
            value = pd.to_numeric(pd.Series([rows.iloc[-1].gwl_current]), errors='coerce').iloc[0]
            if np.isfinite(value) and (not require_observed or bool(observed_mask(rows).iloc[-1])):
                return float(value)
        if month >= fit['origin']:
            return float(predict_depth(fit,[month])[0])
        return float(max(0.,(_design([month],fit['origin'],fit['seasonal']) @ fit['coefficients'] + fit['level_offset'])[0]))
    current = estimate(origin, require_observed=True)
    lags = {lag: estimate(origin-pd.DateOffset(months=lag)) for lag in (3,6)}
    inputs, origin_basis = origin_inputs(evidence['frame'], origin, cutoff, current, lags)
    result['weather_basis']['origin_weather'] = origin_basis
    if inputs is None:
        result.update(status='insufficient_data', forecast=[], estimated_current_gwl=None,
                      message='Origin-month weather inputs are unavailable for the monthly model.')
        return result
    rows = feature_rows(origin, weather['path'], inputs)
    deltas = np.asarray(model.predict(rows), dtype=float)
    if len(deltas) != 6 or not np.isfinite(deltas).all():
        raise RuntimeError('Monthly climate model returned invalid depth changes.')
    depths = np.maximum(0., current+deltas)
    result.update(estimated_current_gwl=round(current,4),
        current_depth_basis='estimated_from_historical_groundwater' if origin>fit['origin'] else 'observed_month',
        model_sha256=card['model_sha256'], model_train_target_cutoff=card['train_target_cutoff'],
        model_validation=card['validation_assessment'],
        forecast=[{'month': row.date.strftime('%Y-%m'), 'date': row.date.date().isoformat(),
                   'predicted_gwl': round(float(depth),4),
                   'weather': {'rainfall_mm': round(float(row.rainfall),4),
                               'temperature_c': round(float(row.temperature),4),
                               'evapotranspiration_mm': round(float(row.evapotranspiration),4)}}
                  for row,depth in zip(weather['path'].itertuples(),depths)])
    return finite_json(result)


def forecast_next_six_months(district_id, as_of=None, weather_override=None):
    return forecast_from_evidence(select_evidence(district_id,as_of), weather_override)


def evaluate_saved_checkpoint(frame, checkpoint=None):
    """Evaluate a verified bundle at its recorded cutoff without fitting or publishing."""
    generation = frame.attrs.get('feature_generation_id')
    if not generation or frame.attrs.get('data_source') in (None, 'unknown', 'synthetic'):
        raise ValueError('Monthly climate evaluation requires verified real features.')
    model, card = load_bundle(checkpoint, expected_generation=generation)
    cutoff = card['train_target_cutoff']
    _, heldout = split_pairs(prepare_pairs(frame), cutoff)
    return {'evaluation_only': True, 'created_at': datetime.now(timezone.utc).isoformat(),
            'version': card['version'], 'model_sha256': card['model_sha256'],
            'feature_generation_id': generation, 'data_source': frame.attrs['data_source'],
            'data_sha256': frame.attrs.get('data_sha256'), 'train_target_cutoff': cutoff,
            'evaluation_protocol': {'embargo_months': 6,
                'cutoff_source': 'verified_checkpoint_model_card',
                'first_eligible_origin': str((pd.Timestamp(cutoff).to_period('M')+7).start_time.date())},
            'evaluation': evaluate_assumed_weather(model, frame, heldout),
            'validation_assessment': card.get('validation_assessment')}


def _validate_cli_outputs(parser, checkpoint, report, candidate=False, evaluation=False):
    """Refuse report/candidate aliases that could replace active data or model assets."""
    active = CHECKPOINT_PATH.resolve()
    historical = (ROOT/CONFIG['paths']['xgboost_checkpoint']).resolve()
    source = Path(checkpoint or CHECKPOINT_PATH).resolve()
    training_report = (ROOT/'reports/climate_forecast_evaluation.json').resolve()
    protected = {active, active.with_name(active.stem+'_model_card.json'),
                 historical, historical.with_name(historical.stem+'_model_card.json'),
                 (ROOT/'data/processed/feature_manifest.json').resolve(),
                 (ROOT/'data/processed/features_matrix.csv').resolve()}
    immutable = {active.parent/'climate_bundles', source.parent/'climate_bundles', historical.parent/'bundles'}
    if candidate:
        protected.add(training_report)
        writes = [source, source.with_name(source.stem+'_model_card.json'), report.resolve()]
    else:
        writes = [report.resolve()]
        if evaluation:
            protected.update({source, source.with_name(source.stem+'_model_card.json'), training_report})
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
                      help='Train into a separate candidate pointer instead of the active checkpoint.')
    parser.add_argument('--checkpoint', type=Path, help='Input bundle pointer for --eval; defaults to the active model.')
    parser.add_argument('--train-cutoff', help=f'Training label cutoff (default: {DEFAULT_TRAIN_CUTOFF}); invalid with --eval.')
    parser.add_argument('--output', type=Path, help='JSON report output; evaluation and candidates have separate defaults.')
    args = parser.parse_args(argv)
    if args.eval and args.train_cutoff is not None:
        parser.error('--eval uses the verified model card cutoff; --train-cutoff cannot be supplied.')
    if args.checkpoint is not None and not args.eval:
        parser.error('--checkpoint is an evaluation input; use --candidate-checkpoint for training experiments.')
    checkpoint = args.checkpoint if args.eval else args.candidate_checkpoint
    if args.eval:
        default_report = ROOT/'reports/climate_forecast_saved_evaluation.json'
    elif args.candidate_checkpoint is not None:
        default_report = checkpoint.with_name(checkpoint.stem+'_evaluation.json')
    else:
        default_report = ROOT/'reports/climate_forecast_evaluation.json'
    report = args.output or default_report
    _validate_cli_outputs(parser, checkpoint, report,
                          candidate=args.candidate_checkpoint is not None, evaluation=args.eval)
    frame = load_feature_matrix()
    if args.eval:
        result = evaluate_saved_checkpoint(frame, checkpoint)
        summary = result
    else:
        _, result = train(frame, args.train_cutoff or DEFAULT_TRAIN_CUTOFF, checkpoint=checkpoint)
        summary = {'training_pairs':result['n_train_observed_pairs'],
                   'evaluation':result['evaluation'], 'feature_importance':result['feature_importance']}
    _write_json(report, result)
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
    return result


if __name__ == '__main__':
    main()
