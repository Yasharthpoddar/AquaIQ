"""Fixed-panel state summaries of the existing district XGBoost forecasts."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
from threading import RLock
import hashlib
import json
import numpy as np
import pandas as pd

from db.connection import finite_json
from models import climate_forecast_12m as climate
from models.ensemble import _as_of, _completed_feature_month, _readiness
from models.state_mapping import resolve_state_id, get_state_metadata, STATES_REGISTRY
from models.xgboost_model import load_feature_matrix, observed_mask
from models.forecast_cache import ForecastCache
from models.ensemble import CONFIG

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = '2.0-state-district-xgboost'
PRODUCT_NAME = 'state_groundwater_12m_forecast'
MODEL_NAME = 'district_xgboost_equal_weight'
MIN_COVERAGE = .5
EVALUATION_METRICS = {'status': 'experimental', 'prospective_skill_verified': False,
                      'historical_report': 'reports/xgboost_only_states_20261025/evaluation.json'}
STATE_LIMITATIONS = [
    'Equal weights apply to a fixed panel of eligible district XGBoost forecasts; this is not an area- or well-weighted state estimate.',
    'Districts without sufficient individual evidence are excluded; zone fallback estimates never enter the state panel.',
    'Current district depths are estimated across observation gaps; future weather uses historical climatology assumptions.',
    'Observed history uses the districts reporting in each month, whose composition can differ from the forecast panel.',
    'Depth in metres below ground is not groundwater volume. State-wide and prospective forecasting accuracy remain unverified.',
    'Month labels and source observation flags do not establish acquisition/publication dates or stable well panels.',
]
_CACHED_FEATURE_MATRIX = None
_FEATURE_SIGNATURE = None
_FORECAST_CACHE = ForecastCache(80)
_DISTRICT_CACHE = ForecastCache(1500)
_INPUT_LOCK = RLock()
_REGISTRY_SNAPSHOT = None


def _file_signature(paths):
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_ctime_ns, p.stat().st_size) for p in paths)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def clear_caches():
    """Discard memoized predictions; source/model verification still precedes reuse."""
    _FORECAST_CACHE.clear()
    _DISTRICT_CACHE.clear()


def state_observed_mask(frame):
    """Conflicting or unknown imputation flags cannot establish a measurement."""
    mask = observed_mask(frame)
    if 'is_imputed' in frame:
        mask &= observed_mask(frame.drop(columns=['is_observed'], errors='ignore'))
    return mask


def get_feature_matrix():
    """Fail closed on missing/changed/unverified exports; never bypass a manifest."""
    global _CACHED_FEATURE_MATRIX, _FEATURE_SIGNATURE
    paths = [ROOT / 'data/processed/features_matrix.csv', ROOT / 'data/processed/feature_manifest.json']
    with _INPUT_LOCK:
        signature = _file_signature(paths)
        if _CACHED_FEATURE_MATRIX is None or signature != _FEATURE_SIGNATURE:
            frame = load_feature_matrix()
            if frame.duplicated(['district_id', 'date']).any():
                raise ValueError('Duplicate district-month keys in state inputs.')
            if signature != _file_signature(paths):
                raise RuntimeError('Feature export changed during verification; retry with a stable snapshot.')
            identities = {d: resolve_state_id(d) for d in frame.district_id.unique()}
            frame['state_id'] = frame.district_id.map(identities)
            _CACHED_FEATURE_MATRIX, _FEATURE_SIGNATURE = frame, signature
            clear_caches()
        return _CACHED_FEATURE_MATRIX


def get_state_districts(state_id):
    global _REGISTRY_SNAPSHOT
    code = resolve_state_id(state_id)
    path = ROOT / 'data_ingestion/district_crosswalk.csv'
    with _INPUT_LOCK:
        signature = _file_signature([path])
        if _REGISTRY_SNAPSHOT is None or _REGISTRY_SNAPSHOT[0] != signature:
            raw = path.read_bytes()
            crosswalk = pd.read_csv(BytesIO(raw), usecols=['canonical_district_id'])
            if signature != _file_signature([path]):
                raise RuntimeError('District registry changed during verification.')
            districts = tuple(sorted(crosswalk.canonical_district_id.unique()))
            _REGISTRY_SNAPSHOT = (signature, hashlib.sha256(raw).hexdigest(), districts)
        return [d for d in _REGISTRY_SNAPSHOT[2] if str(d).startswith(code + '-')]


def _state_frame(code, frame=None):
    frame = get_feature_matrix() if frame is None else frame
    selected = frame.loc[frame.district_id.str.startswith(code + '-')].copy()
    selected.attrs.update(frame.attrs)
    if selected.duplicated(['district_id', 'date']).any():
        raise ValueError('Duplicate district-month keys in state inputs.')
    return selected


def aggregate_state_observations(state_id, as_of=None, weighting='equal', *, _frame=None, _districts=None):
    if weighting != 'equal':
        raise ValueError('Only equal district weighting is supported.')
    code = resolve_state_id(state_id)
    frame = _state_frame(code) if _frame is None else _frame
    cutoff = _completed_feature_month(_as_of(as_of))
    values = pd.to_numeric(frame.gwl_current, errors='coerce')
    valid = state_observed_mask(frame) & np.isfinite(values) & values.ge(0) & frame.date.le(cutoff)
    observations = frame.loc[valid].assign(gwl_valid=values[valid])
    total = len(get_state_districts(code) if _districts is None else _districts)
    grouped = observations.groupby('date').agg(gwl_m_bgl=('gwl_valid', 'mean'),
                    contributing_districts_count=('district_id', 'nunique')).reset_index().sort_values('date')
    grouped['state_id'] = code
    grouped['total_districts_in_state'] = total
    grouped['district_coverage_pct'] = (100 * grouped.contributing_districts_count / total).round(1) if total else 0.
    grouped['weighting_method'] = 'equal'
    grouped['is_observed'] = True
    return grouped


def _validate_district_forecast(value, district_id, origin, model_sha, cutoff, generation):
    expected = pd.date_range(origin + pd.offsets.MonthBegin(1), periods=12, freq='MS')
    if (value.get('district_id') != district_id or value.get('product') != climate.PRODUCT_NAME
            or value.get('model_version') != climate.MODEL_VERSION or value.get('model_sha256') != model_sha
            or value.get('units') != 'm_bgl' or value.get('estimate_type') != 'district_level'
            or value.get('as_of') != cutoff.date().isoformat() or value.get('feature_generation') != generation
            or value.get('horizon_months') != 12 or len(value.get('forecast', [])) != 12):
        raise RuntimeError('Invalid district XGBoost model, identity or horizon.')
    anchor = value.get('estimated_current_gwl')
    if isinstance(anchor, bool) or not isinstance(anchor, (float, int)) or not np.isfinite(anchor) or anchor < 0:
        raise RuntimeError('Invalid district anchor.')
    for h, (row, target) in enumerate(zip(value['forecast'], expected), 1):
        depth = row.get('predicted_gwl')
        if (row.get('horizon') != h or row.get('date') != target.strftime('%Y-%m-%d')
                or row.get('month') != target.strftime('%Y-%m') or isinstance(depth, bool)
                or not isinstance(depth, (float, int)) or not np.isfinite(depth) or depth < 0):
            raise RuntimeError('Invalid district XGBoost calendar path or depth.')


def _request_context(cutoff):
    """One verified source/model snapshot for a request, including all state rows."""
    frame = get_feature_matrix()
    # The bundle loader verifies hashes on source changes, even on a warm request.
    with _INPUT_LOCK:
        bundle = climate.load_bundle(expected_generation=frame.attrs.get('feature_generation_id'))
        get_state_districts(next(iter(STATES_REGISTRY)))
        registry_snapshot = _REGISTRY_SNAPSHOT
        registry = {code: tuple(get_state_districts(code)) for code in STATES_REGISTRY}
        if _REGISTRY_SNAPSHOT is not registry_snapshot:
            raise RuntimeError('District registry changed while preparing a request.')
    identity = (MODEL_VERSION, climate.MODEL_VERSION, 12, cutoff.isoformat(),
                _digest(bundle[1]), bundle[1]['model_sha256'],
                frame.attrs.get('feature_generation_id'), frame.attrs.get('data_sha256'), id(frame),
                _digest(registry), _digest(STATES_REGISTRY),
                registry_snapshot[1] if registry_snapshot else None,
                MIN_COVERAGE, _digest(CONFIG))
    return dict(frame=frame, bundle=bundle, registry=registry, identity=identity)


def forecast_state_twelve_months(state_id, as_of=None, weighting='equal', *, _context=None, _allow_storage=True):
    if weighting != 'equal':
        raise ValueError('Only equal district weighting is supported.')
    code, cutoff = resolve_state_id(state_id), _as_of(as_of)
    if _allow_storage and _context is None:
        from models import forecast_storage
        stored = forecast_storage.get_state_forecast(code, cutoff)
        if stored is not None:
            return deepcopy(stored)
    origin = cutoff.to_period('M').to_timestamp()
    meta = get_state_metadata(code)
    districts = get_state_districts(code)
    result = dict(product=PRODUCT_NAME, model_version=MODEL_VERSION, model_name=MODEL_NAME,
        state_id=code, state_name=meta['name'], state_type=meta['type'], st_code=meta['st_code'],
        units='m_bgl', horizon_months=12, forecast_origin=origin.date().isoformat(),
        as_of=cutoff.date().isoformat(), computed_at=datetime.now(timezone.utc).isoformat(),
        status='insufficient_data', forecast=[], history=[], districts=districts,
        total_districts_in_state=len(districts), contributing_districts_count=0,
        contributing_district_ids=[], excluded_districts=[], district_coverage_pct=0.,
        estimated_current_gwl_m_bgl=None, current_depth_basis='estimated_district_inputs',
        aggregation_method='equal_weight_fixed_district_xgboost_panel',
        evaluation_status='experimental_state_outlook', evaluation=deepcopy(EVALUATION_METRICS),
        limitations=deepcopy(STATE_LIMITATIONS))
    try:
        context = _context or _request_context(cutoff)
        districts = list(context['registry'][code])
        result.update(districts=districts, total_districts_in_state=len(districts))
        card = context['bundle'][1]
    except (OSError, RuntimeError, ValueError) as error:
        result.update(status='model_unavailable', message='Verified XGBoost model or matching feature data is unavailable.',
                      unavailable_reason=type(error).__name__)
        return result
    result.update(model_sha256=card['model_sha256'], model_train_target_cutoff=card['train_target_cutoff'],
                  feature_generation=context['frame'].attrs.get('feature_generation_id'))
    key = (code, context['identity'], tuple(districts))
    return _FORECAST_CACHE.get_or_compute(key, lambda: _compute_state(result, cutoff, context))


def _compute_state(result, cutoff, context):
    code, districts = result['state_id'], result['districts']
    origin = cutoff.to_period('M').to_timestamp()
    card = context['bundle'][1]
    try:
        frame = _state_frame(code, context['frame'])
    except (OSError, RuntimeError, ValueError) as error:
        result.update(status='model_unavailable', message='Verified XGBoost model or matching feature data is unavailable.',
                      unavailable_reason=type(error).__name__)
        return result
    available = frame.loc[frame.date.le(_completed_feature_month(cutoff))]
    history = aggregate_state_observations(code, cutoff, _frame=frame, _districts=districts)
    result['history'] = [dict(date=r.date.date().isoformat(), gwl_m_bgl=float(r.gwl_m_bgl),
        contributing_districts_count=int(r.contributing_districts_count), total_districts_in_state=len(districts),
        district_coverage_pct=float(r.district_coverage_pct), is_observed=True, is_forecast=False)
        for r in history.tail(24).itertuples()]
    if len(history):
        result.update(last_observed_date=history.iloc[-1].date.date().isoformat(),
                      last_observed_gwl_m_bgl=float(history.iloc[-1].gwl_m_bgl))
    panel = []
    district_groups = {district_id: group for district_id, group in available.groupby('district_id', sort=False)}
    for district_id in districts:
        district = district_groups.get(district_id, available.iloc[:0]).copy()
        if district.empty:
            result['excluded_districts'].append(dict(district_id=district_id, reason='No district feature history.'))
            continue
        readiness = _readiness(district, cutoff)
        if not readiness['eligible']:
            result['excluded_districts'].append(dict(district_id=district_id, reason='Insufficient individual district observation coverage.'))
            continue
        observed = district.loc[state_observed_mask(district) & np.isfinite(district.gwl_current) & district.gwl_current.ge(0)]
        if observed.empty:
            result['excluded_districts'].append(dict(district_id=district_id, reason='No unambiguous observed district history.'))
            continue
        evidence = dict(district_id=district_id, as_of=cutoff, generation=result['feature_generation'],
                        frame=district, history=observed, estimate_type='district_level', zone=None, reason=None,
                        readiness=readiness, origin=observed.date.max())
        def compute_district():
            value = climate.forecast_from_evidence(evidence, _verified_bundle=context['bundle'])
            if value.get('status') == 'forecast':
                _validate_district_forecast(value, district_id, origin, card['model_sha256'], cutoff, result['feature_generation'])
            elif value.get('status') not in ('insufficient_data', 'model_unavailable'):
                raise RuntimeError('District XGBoost returned an invalid availability status.')
            return value
        value = _DISTRICT_CACHE.get_or_compute((context['identity'], code, tuple(districts), district_id), compute_district)
        if value.get('status') == 'model_unavailable':
            result.update(status='model_unavailable', message='The XGBoost model became unavailable; no state forecast was substituted.')
            return result
        if value.get('status') != 'forecast':
            result['excluded_districts'].append(dict(district_id=district_id, reason=value.get('message', 'District XGBoost inputs unavailable.')))
            continue
        _validate_district_forecast(value, district_id, origin, card['model_sha256'], cutoff, result['feature_generation'])
        panel.append(value)
    ids = [p['district_id'] for p in panel]
    coverage = len(panel) / len(districts) if districts else 0.
    result.update(contributing_district_ids=ids, contributing_districts_count=len(ids), district_coverage_pct=round(coverage * 100, 1))
    if not districts or coverage < MIN_COVERAGE or len(panel) < min(2, len(districts)):
        result['message'] = 'Insufficient district XGBoost coverage: at least 50% and two districts are required (one for a single-district state).'
        return result
    anchor = float(np.mean([p['estimated_current_gwl'] for p in panel]))
    depths = np.mean([[row['predicted_gwl'] for row in p['forecast']] for p in panel], axis=0)
    result.update(status='forecast', estimated_current_gwl_m_bgl=round(anchor, 4),
        panel_id=hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest(),
        forecast=[dict(horizon=h, target_date=(origin + pd.DateOffset(months=h)).date().isoformat(),
            predicted_gwl=round(float(depth), 4), delta_from_current_m=round(float(depth-anchor), 4),
            units='m_bgl', is_observed=False, is_forecast=True) for h, depth in enumerate(depths, 1)])
    return finite_json(result)


def get_all_states_summary(horizon=12, as_of=None, *, _context=None, _allow_storage=True):
    if horizon != 12:
        raise ValueError('Only horizon=12 is supported for state forecasting.')
    cutoff = _as_of(as_of)
    if _allow_storage and _context is None:
        from models import forecast_storage
        stored = forecast_storage.get_nationwide_summary(cutoff)
        if stored is not None:
            return deepcopy(stored)
    try:
        context = _context or _request_context(cutoff)
    except (OSError, RuntimeError, ValueError) as error:
        raise RuntimeError('Verified state XGBoost inputs are unavailable.') from error
    states = []
    for code, meta in sorted(STATES_REGISTRY.items(), key=lambda item: item[1]['name']):
        value = forecast_state_twelve_months(code, cutoff, _context=context)
        if value['status'] == 'model_unavailable':
            raise RuntimeError('State XGBoost computation failed; the nationwide summary is unavailable.')
        end = value['forecast'][-1] if value['status'] == 'forecast' else None
        states.append(dict(state_id=code, state_name=meta['name'], state_type=meta['type'], st_code=meta['st_code'],
            status='available' if end else value['status'], total_districts=value['total_districts_in_state'],
            contributing_districts=value['contributing_districts_count'], district_coverage_pct=value['district_coverage_pct'],
            last_observed_date=value.get('last_observed_date'), current_gwl_m_bgl=value['estimated_current_gwl_m_bgl'],
            estimated_current_gwl_m_bgl=value['estimated_current_gwl_m_bgl'],
            forecast_12m_gwl_m_bgl=end['predicted_gwl'] if end else None,
            projected_change_12m_m=end['delta_from_current_m'] if end else None,
            unavailable_reason=value.get('message')))
    count = sum(row['status'] == 'available' for row in states)
    return dict(product='state_groundwater_summary', model_version=MODEL_VERSION, horizon_months=12,
        as_of=cutoff.date().isoformat(), computed_at=datetime.now(timezone.utc).isoformat(), total_states=len(states),
        available_states_count=count, insufficient_data_states_count=len(states)-count, states=states,
        evaluation_summary=EVALUATION_METRICS, limitations=STATE_LIMITATIONS)
