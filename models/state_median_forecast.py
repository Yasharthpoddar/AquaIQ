"""Experimental, independent state XGBoost models of observed district medians.

No district model, feature export or production forecast is written by this module.
Origins use completed monthly inputs; targets are genuine, coverage-qualified
state medians. Direct horizons avoid inventing groundwater or future weather.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
import xgboost
from xgboost import XGBRegressor

from db.connection import finite_json
from models.district_registry import get_registry, registry_hash
from models.ensemble import _as_of, _completed_feature_month
from models.state_forecast import state_observed_mask
from models.state_mapping import STATES_REGISTRY, resolve_state_id
from models.xgboost_model import load_feature_matrix, sha256_file

MODEL_VERSION = '1.0-state-median-xgboost'
MODEL_NAME = 'state_median_xgboost'
PRODUCT_NAME = 'state_median_groundwater_12m_forecast'
MIN_COVERAGE = .5
MIN_HISTORY = 36
MIN_SPAN_MONTHS = 60
MIN_TRAINING_TARGETS = 24
MAX_REFERENCE_AGE_MONTHS = 12
PARAMETERS = dict(n_estimators=120, max_depth=2, learning_rate=.04,
                  objective='reg:squarederror', subsample=1., colsample_bytree=1.,
                  random_state=42, n_jobs=1, tree_method='hist')
CLIMATE = ['rainfall_current', 'temperature', 'evapotranspiration']
FEATURES = (['horizon', 'target_month_sin', 'target_month_cos',
             'origin_month_sin', 'origin_month_cos', 'last_depth', 'observation_age_months',
             'previous_month_depth', 'previous_month_coverage'] +
            [f'lag_{n}' for n in (1, 2, 3, 6, 12)] +
            [f'rolling_{stat}_{n}' for n in (3, 6, 12) for stat in ('median', 'mean', 'std')] +
            ['change_3'] + [f'{c}_lag1' for c in CLIMATE])
LIMITATIONS = [
    'Experimental: no production promotion or prospective accuracy claim.',
    'Median of equally weighted observed district-month means: the typical reporting district, not groundwater volume, total availability or the most depleted district.',
    'The reporting district and underlying well composition can change between months.',
    'Counts represent source-marked district-month aggregates; original well-reading counts are unavailable in the feature export.',
    'Missing and low-coverage months are not training targets; no interpolated groundwater targets or other-state donors are used.',
    'Only origin-available historical climate features are used, including source-pipeline causal fills. No future weather or climatology is supplied to this candidate.',
    'Model features always stop at the previous calendar month, even for month-end requests, to match partial-month serving availability.',
    'Source month labels do not establish publication or acquisition dates; retrospective availability is assumed after calendar month end.',
    'Predictions are clipped at zero metres below ground; uncertainty intervals are not calibrated.',
]


def _month(value):
    return pd.Timestamp(value).to_period('M').to_timestamp()


def _distance(a, b):
    return (a.year-b.year)*12 + a.month-b.month


def build_state_history(frame, registry=None, min_coverage=MIN_COVERAGE, as_of=None):
    """District-month mean first, then equal-district median on a full calendar.

    Production input is the verified unique district-month export. For explicitly
    supplied repeated observations, exact district/date/value/flag duplicates are
    removed, then valid readings are averaged per district-month (the ingestion
    convention). This never weights a district by its sampling frequency.
    """
    if not 0 < min_coverage <= 1:
        raise ValueError('min_coverage must be greater than zero and at most one.')
    registry = get_registry() if registry is None else registry
    mapping = {r['district_id']: r['state_id'] for r in registry}
    if len(mapping) != len(registry) or any(resolve_state_id(d) != s for d, s in mapping.items()):
        raise ValueError('Invalid or duplicate canonical district/state mapping.')
    required = {'district_id', 'date', 'gwl_current'}
    if required - set(frame):
        raise ValueError('Missing district observation columns.')
    if set(frame.district_id) - set(mapping):
        raise ValueError('Observations contain unregistered district identities.')
    data = frame.copy()
    data.attrs = {}
    data['date'] = pd.to_datetime(data.date, errors='raise')
    if data.date.isna().any():
        raise ValueError('Observation timestamp is missing.')
    if 'state_id' in data and (data.state_id != data.district_id.map(mapping)).any():
        raise ValueError('Observation state disagrees with canonical registry.')
    if as_of is not None:
        # Filter original dates before normalization: a later reading must not
        # enter an earlier partial-month snapshot.
        data = data.loc[data.date.le(_completed_feature_month(_as_of(as_of)) + pd.offsets.MonthEnd(0))]
    if data.empty:
        raise ValueError('No input calendar is available.')
    # Verified exports fail on duplicates before reaching here. Explicit raw
    # input deduplication concerns observed payload only, not unrelated features.
    keys = ['district_id', 'date', 'gwl_current'] + [c for c in ('is_observed', 'is_imputed') if c in data]
    data = data.drop_duplicates(keys)
    data['date'] = data.date.dt.to_period('M').dt.to_timestamp()
    depth = pd.to_numeric(data.gwl_current, errors='coerce')
    valid = state_observed_mask(data) & np.isfinite(depth) & depth.ge(0)
    observations = data.loc[valid, ['district_id', 'date']].assign(depth=depth[valid])
    district = observations.groupby(['district_id', 'date']).agg(
        depth=('depth', 'mean'), observation_count=('depth', 'size')).reset_index()
    district['state_id'] = district.district_id.map(mapping)
    grouped = district.groupby(['state_id', 'date']).agg(gwl_m_bgl=('depth', 'median'),
        contributing_districts_count=('district_id', 'nunique'), observation_count=('observation_count', 'sum'))
    end = _completed_feature_month(_as_of(as_of)) if as_of is not None else data.date.max()
    calendar = pd.date_range(data.date.min(), end, freq='MS')
    states = sorted(set(mapping.values()))
    index = pd.MultiIndex.from_product([states, calendar], names=['state_id', 'date'])
    result = grouped.reindex(index).reset_index()
    totals = pd.Series(list(mapping.values())).value_counts()
    result['total_districts_in_state'] = result.state_id.map(totals).astype(int)
    for c in ('contributing_districts_count', 'observation_count'):
        result[c] = result[c].fillna(0).astype(int)
    result['coverage_ratio'] = result.contributing_districts_count / result.total_districts_in_state
    result['district_coverage_pct'] = 100 * result.coverage_ratio
    result['training_eligible'] = (result.coverage_ratio.ge(min_coverage) &
        result.contributing_districts_count.ge(np.minimum(2, result.total_districts_in_state)) & result.gwl_m_bgl.notna())
    result['observation_quality'] = np.select(
        [result.contributing_districts_count.eq(0), result.training_eligible],
        ['missing', 'coverage_qualified'], default='low_coverage')
    # Equal district means of historical climate; low coverage remains missing.
    # Future target-month climate is never a feature.
    for c in CLIMATE:
        result[c] = np.nan
        if c not in data:
            continue
        values = pd.to_numeric(data[c], errors='coerce').replace([np.inf, -np.inf], np.nan)
        if c != 'temperature':
            values = values.where(values.ge(0))
        climate = data[['district_id', 'date']].assign(value=values).groupby(['district_id', 'date']).value.mean().reset_index()
        climate['state_id'] = climate.district_id.map(mapping)
        climate = climate.groupby(['state_id', 'date']).value.agg(['mean', 'count'])
        climate['mean'] = climate['mean'].where(climate['count'] / climate.index.get_level_values(0).map(totals) >= min_coverage)
        result[c] = climate['mean'].reindex(index).to_numpy()
    result.attrs.update(feature_generation_id=frame.attrs.get('feature_generation_id'),
        data_sha256=frame.attrs.get('data_sha256'), registry_sha256=registry_hash(),
        min_coverage=min_coverage, observation_count_basis='deduplicated_source_marked_district_month_aggregates')
    return result


def load_history(processed_dir=None, min_coverage=MIN_COVERAGE):
    return build_state_history(load_feature_matrix(processed_dir), min_coverage=min_coverage)


def state_features(history, origin, horizon):
    """Features stop strictly before the origin month, including month-end requests.

    This conservative fixed lag makes month-end training identical to mid-month
    serving. Forecast M+1 is the month after origin, not after the input cutoff.
    """
    if horizon not in range(1, 13):
        raise ValueError('horizon must be in 1..12.')
    if history.state_id.nunique() > 1 or history.date.duplicated().any():
        raise ValueError('Features require one unique state calendar.')
    origin = _month(origin)
    feature_month = origin-pd.DateOffset(months=1)
    past = history.loc[history.date.lt(origin)].sort_values('date').set_index('date')
    values = past.gwl_m_bgl.where(past.training_eligible)
    observed = values.dropna()
    target = origin + pd.DateOffset(months=horizon)
    row = dict(horizon=horizon, target_month_sin=np.sin(2*np.pi*target.month/12),
        target_month_cos=np.cos(2*np.pi*target.month/12),
        origin_month_sin=np.sin(2*np.pi*origin.month/12), origin_month_cos=np.cos(2*np.pi*origin.month/12),
        last_depth=float(observed.iloc[-1]) if len(observed) else np.nan,
        observation_age_months=_distance(origin, observed.index[-1]) if len(observed) else np.nan,
        previous_month_depth=values.get(feature_month, np.nan),
        previous_month_coverage=past.coverage_ratio.get(feature_month, np.nan))
    for n in (1, 2, 3, 6, 12):
        row[f'lag_{n}'] = values.get(origin-pd.DateOffset(months=n), np.nan)
    for n in (3, 6, 12):
        window = values.loc[values.index >= origin-pd.DateOffset(months=n)].dropna()
        for stat in ('median', 'mean', 'std'):
            row[f'rolling_{stat}_{n}'] = getattr(window, stat)(ddof=0) if stat == 'std' and len(window) else getattr(window, stat)() if len(window) else np.nan
    row['change_3'] = row['last_depth']-row['lag_3']
    for c in CLIMATE:
        row[f'{c}_lag1'] = past[c].get(feature_month, np.nan) if c in past else np.nan
    return row


def training_examples(history, cutoff):
    """Direct horizon rows with origin < target <= cutoff; no random split."""
    cutoff = _month(cutoff)
    h = history.loc[history.date.le(cutoff)].sort_values('date')
    targets = h.loc[h.training_eligible].set_index('date').gwl_m_bgl
    rows = []
    for origin in h.date:
        known = targets.loc[targets.index < origin]
        if len(known) < 12 or _distance(origin, known.index[-1]) > MAX_REFERENCE_AGE_MONTHS:
            continue
        base = state_features(h, origin, 1)
        for horizon in range(1, 13):
            target = origin + pd.DateOffset(months=horizon)
            if target not in targets.index:
                continue
            features = dict(base, horizon=horizon,
                target_month_sin=np.sin(2*np.pi*target.month/12), target_month_cos=np.cos(2*np.pi*target.month/12))
            rows.append(dict(**features, origin=origin, target_date=target, target=float(targets.loc[target])))
    return pd.DataFrame(rows, columns=FEATURES+['origin', 'target_date', 'target'])


def _eligibility(history, minimum=MIN_HISTORY):
    valid = history.loc[history.training_eligible].sort_values('date')
    span = _distance(valid.date.iloc[-1], valid.date.iloc[0])+1 if len(valid) else 0
    return len(valid) >= minimum and span >= MIN_SPAN_MONTHS, len(valid), span


def train_state_models(history, artifact_dir, train_cutoff, validation_start='2017-01-01'):
    """Fixed parameters, chronological diagnostic validation, then refit to cutoff.

    Validation origins begin after all fit labels. Test labels are not accessed.
    The final fit includes validation history, so validation errors are never
    served as forecast-accuracy evidence. An independent backtest is required.
    """
    directory = Path(artifact_dir)
    cutoff, val_start = _month(train_cutoff), _month(validation_start)
    if val_start >= cutoff or val_start <= history.date.min():
        raise ValueError('Validation must follow training and precede the final label cutoff.')
    directory.mkdir(parents=True, exist_ok=False)
    fit_end = val_start-pd.DateOffset(months=1)
    metadata = dict(model_name=MODEL_NAME, model_version=MODEL_VERSION, product=PRODUCT_NAME,
        promotion_status='experimental', train_target_cutoff=cutoff.date().isoformat(), training_cutoff=cutoff.date().isoformat(),
        validation_start=val_start.date().isoformat(), initial_fit_target_cutoff=fit_end.date().isoformat(),
        features=FEATURES, parameters=PARAMETERS, xgboost_version=xgboost.__version__,
        min_coverage=history.attrs.get('min_coverage', MIN_COVERAGE),
        min_history=MIN_HISTORY, min_span_months=MIN_SPAN_MONTHS, min_training_targets=MIN_TRAINING_TARGETS,
        max_reference_age_months=MAX_REFERENCE_AGE_MONTHS,
        feature_generation_id=history.attrs.get('feature_generation_id'), data_sha256=history.attrs.get('data_sha256'),
        registry_sha256=history.attrs.get('registry_sha256'),
        implementation_sha256=sha256_file(__file__), created_at=datetime.now(timezone.utc).isoformat(), states={})
    for code, state in history.groupby('state_id', sort=True):
        state = state.loc[state.date.le(cutoff)]
        eligible, n, span = _eligibility(state)
        examples = training_examples(state, cutoff) if eligible else pd.DataFrame()
        entry = dict(status='insufficient_data', observed_months=n, span_months=span,
            reason='Requires 36 coverage-qualified months spanning 60 months, 24 supervised target months, and chronological validation evidence.')
        metadata['states'][code] = entry
        if examples.empty or examples.target_date.nunique() < MIN_TRAINING_TARGETS:
            continue
        fit = examples.loc[examples.target_date.lt(val_start)]
        # Only origins AFTER fit labels can provide a multi-step validation.
        val = examples.loc[examples.origin.ge(val_start) & examples.target_date.ge(val_start)]
        if fit.target_date.nunique() < MIN_TRAINING_TARGETS or val.target_date.nunique() < 3:
            continue
        model = XGBRegressor(**PARAMETERS).fit(fit[FEATURES], fit.target)
        error = np.maximum(0., model.predict(val[FEATURES]))-val.target.to_numpy()
        validation = dict(n=len(val), unique_target_months=int(val.target_date.nunique()),
            mae_m=float(np.abs(error).mean()), rmse_m=float(np.sqrt(np.mean(error**2))),
            period_start=val.target_date.min().date().isoformat(), period_end=val.target_date.max().date().isoformat(),
            role='development_diagnostic_only_not_test_accuracy')
        model = XGBRegressor(**PARAMETERS).fit(examples[FEATURES], examples.target)
        path = directory / f'{code}.json'
        model.save_model(path)
        entry.update(status='trained', reason=None, file=path.name, model_sha256=sha256_file(path),
            training_rows=len(examples), training_target_months=int(examples.target_date.nunique()),
            first_training_target=examples.target_date.min().date().isoformat(),
            last_training_target=examples.target_date.max().date().isoformat(), validation=validation)
    (directory/'model_card.json').write_text(json.dumps(finite_json(metadata), indent=2, allow_nan=False), encoding='utf-8')
    return load_models(directory)


def load_models(artifact_dir):
    directory = Path(artifact_dir)
    card = json.loads((directory/'model_card.json').read_text(encoding='utf-8'))
    if (card.get('model_version') != MODEL_VERSION or card.get('features') != FEATURES
            or card.get('implementation_sha256') != sha256_file(__file__)):
        raise ValueError('Incompatible state median artifact implementation or schema.')
    models = {}
    for code, entry in card['states'].items():
        if entry['status'] != 'trained':
            continue
        path = (directory / entry['file']).resolve()
        if path.parent != directory.resolve() or sha256_file(path) != entry['model_sha256']:
            raise ValueError('Candidate artifact path or checksum mismatch.')
        model = XGBRegressor()
        model.load_model(path)
        models[code] = model
    return models, card


def forecast_state(state_id, history, models, card, as_of, evaluation=None):
    code, cutoff = resolve_state_id(state_id), _as_of(as_of)
    origin, completed = _month(cutoff), _completed_feature_month(cutoff)
    state = history.loc[history.state_id.eq(code) & history.date.le(completed)].sort_values('date')
    entry = card.get('states', {}).get(code, {})
    total = int(state.total_districts_in_state.iloc[-1]) if len(state) else 0
    eligible = state.loc[state.training_eligible]
    references = eligible.loc[eligible.date.lt(origin)]
    latest = references.iloc[-1] if len(references) else None
    result = dict(product=PRODUCT_NAME, model_version=MODEL_VERSION, model_name=MODEL_NAME,
        promotion_status='experimental', state_id=code, state_name=STATES_REGISTRY[code]['name'],
        status='insufficient_data', units='m_bgl', horizon_months=12, as_of=cutoff.date().isoformat(),
        forecast_origin=origin.date().isoformat(), input_cutoff=completed.date().isoformat(),
        computed_at=datetime.now(timezone.utc).isoformat(), training_cutoff=card['training_cutoff'],
        model_sha256=entry.get('model_sha256'), feature_generation=history.attrs.get('feature_generation_id'),
        source_data_sha256=history.attrs.get('data_sha256'), registry_sha256=history.attrs.get('registry_sha256'),
        min_coverage=card['min_coverage'], features=FEATURES, total_districts_in_state=total,
        contributing_districts_count=int(latest.contributing_districts_count) if latest is not None else 0,
        district_coverage_pct=float(latest.district_coverage_pct) if latest is not None else 0.,
        historical_reference_date=latest.date.date().isoformat() if latest is not None else None,
        last_observed_gwl_m_bgl=float(latest.gwl_m_bgl) if latest is not None else None,
        aggregation_method='median_of_observed_district_month_means',
        observation_count_basis='source_marked_district_month_aggregates_not_wells',
        evaluation=evaluation or dict(status='not_evaluated', n=0, mae_m=None, rmse_m=None,
            period_start=None, period_end=None, description='No independent held-out comparison attached.'),
        limitations=LIMITATIONS, forecast=[], history=[])
    for row in state.tail(60).to_dict('records'):
        result['history'].append(dict(date=row['date'].date().isoformat(), **{k: row[k] for k in ('gwl_m_bgl', 'training_eligible',
            'contributing_districts_count', 'total_districts_in_state', 'district_coverage_pct',
            'coverage_ratio', 'observation_count', 'observation_quality')},
            is_observed=bool(pd.notna(row['gwl_m_bgl'])), is_forecast=False))
    if (history.attrs.get('feature_generation_id') != card.get('feature_generation_id')
            or history.attrs.get('data_sha256') != card.get('data_sha256')
            or history.attrs.get('registry_sha256') != card.get('registry_sha256')
            or history.attrs.get('min_coverage', MIN_COVERAGE) != card['min_coverage']):
        result.update(status='model_unavailable', message='Candidate model and historical source identities or coverage rules differ.')
    elif _month(card['training_cutoff']) > completed:
        result.update(status='model_unavailable', message='Candidate training labels extend beyond the available origin inputs.')
    elif code not in models:
        result['message'] = entry.get('reason') or 'Insufficient coverage-qualified state history for a separate model.'
    elif latest is None or _distance(origin, latest.date) > MAX_REFERENCE_AGE_MONTHS:
        result['message'] = 'No coverage-qualified state median within the last 12 months.'
    else:
        features = pd.DataFrame([state_features(state, origin, h) for h in range(1, 13)], columns=FEATURES)
        predictions = np.maximum(0., models[code].predict(features))
        if not np.isfinite(predictions).all():
            raise ValueError('Candidate returned a nonfinite forecast.')
        result.update(status='forecast', forecast=[dict(horizon=h,
            target_date=(origin+pd.DateOffset(months=h)).date().isoformat(), predicted_gwl=float(p),
            units='m_bgl', is_observed=False, is_forecast=True) for h, p in enumerate(predictions, 1)])
    return finite_json(result)
