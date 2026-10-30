"""Supplemental full observed history pinned to an immutable forecast snapshot.

This read-only path expands display history without changing released forecast
payloads, model bytes, coverage gates or publication state. It never predicts,
trains, accesses a database or treats filled groundwater as an observation.
"""
from collections import OrderedDict
from copy import deepcopy
import os
from pathlib import Path
import re
from threading import RLock

import pandas as pd

from db.connection import finite_json
from models import state_median_forecast as median
from models.district_registry import get_registry, registry_hash
from models.ensemble import _as_of, _completed_feature_month
from models.state_mapping import resolve_state_id, STATES_REGISTRY
from models.xgboost_model import load_feature_matrix, sha256_file

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_NAME = 'state_median_groundwater_history'
HISTORY_VERSION = '1.0-full-state-observed-history'
SOURCE_ENV = 'AQUAIQ_STATE_MEDIAN_HISTORY_SOURCE_DIR'
_HISTORY_CACHE = OrderedDict()
_CACHE_LOCK = RLock()
_CACHE_SIZE = 3
_FIELDS = ('gwl_m_bgl', 'training_eligible', 'contributing_districts_count',
    'total_districts_in_state', 'district_coverage_pct', 'coverage_ratio',
    'observation_count', 'observation_quality')


def clear_history_cache():
    with _CACHE_LOCK:
        _HISTORY_CACHE.clear()


def _hash(path):
    try:
        return sha256_file(path)
    except OSError as error:
        raise RuntimeError('The verified full-history source files are unavailable.') from error


def _source_directory(manifest, processed_dir=None):
    expected = manifest['source_manifest_sha256']
    override = processed_dir if processed_dir is not None else os.getenv(SOURCE_ENV)
    if override is not None:
        directory = Path(override).expanduser().resolve()
        if _hash(directory/'feature_manifest.json') != expected:
            raise RuntimeError('The configured history source differs from the published snapshot manifest.')
        return directory
    base = ROOT/'data/processed'
    candidates = [base/'feature_manifest.json']
    candidates.extend(sorted((base/'enrichment').glob('*/feature_manifest.json')))
    matches = {path.parent.resolve() for path in candidates if path.is_file() and _hash(path) == expected}
    if not matches:
        raise RuntimeError('The published full-history source is not installed; configure its verified snapshot directory.')
    if len(matches) != 1:
        raise RuntimeError('More than one matching full-history source is installed; configure an explicit snapshot directory.')
    return next(iter(matches))


def _validate_context(code, forecast, manifest):
    required_hashes = ('source_manifest_sha256', 'source_csv_sha256', 'data_sha256',
                       'registry_sha256', 'model_algorithm_sha256')
    if any(not re.fullmatch(r'[a-f0-9]{64}', str(manifest.get(key, ''))) for key in required_hashes):
        raise RuntimeError('Full history requires complete verified source identities.')
    pairs = (('feature_generation', 'feature_generation_id'), ('source_data_sha256', 'data_sha256'),
             ('registry_sha256', 'registry_sha256'), ('model_version', 'model_version'),
             ('model_name', 'model_name'), ('artifact_release', 'artifact_release'), ('min_coverage', 'min_coverage'))
    if any(forecast.get(left) != manifest.get(right) for left, right in pairs):
        raise RuntimeError('Published forecast and full-history manifest identities differ.')
    if (forecast.get('state_id') != code or forecast.get('product') != median.PRODUCT_NAME
            or forecast.get('status') not in ('forecast', 'insufficient_data')
            or not isinstance(forecast.get('generation_id'), str) or not forecast['generation_id']
            or not re.fullmatch(r'[a-f0-9]{64}', str(forecast.get('release_manifest_sha256', '')))):
        raise RuntimeError('Full history requires a pinned, usable state forecast context.')
    proportion = manifest.get('min_coverage')
    if isinstance(proportion, bool) or not isinstance(proportion, (float, int)) or not 0 < proportion <= 1:
        raise RuntimeError('Published history coverage criteria are invalid.')
    if registry_hash() != manifest['registry_sha256']:
        raise RuntimeError('The installed district registry differs from the published history snapshot.')
    if _hash(median.__file__) != manifest['model_algorithm_sha256']:
        raise RuntimeError('The installed observation aggregation differs from the published implementation.')
    try:
        stamp = _as_of(forecast['as_of'])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError('The pinned forecast vintage is invalid.') from error
    completed = _completed_feature_month(stamp)
    if forecast.get('input_cutoff', completed.date().isoformat()) != completed.date().isoformat():
        raise RuntimeError('Forecast and historical completed-input months differ.')
    return stamp, completed


def _verify_source_files(directory, manifest):
    # Content hashes are checked even for a warm cache. Timestamp/size-only
    # memoization would miss an in-place edit preserving filesystem metadata.
    if (_hash(directory/'feature_manifest.json') != manifest['source_manifest_sha256']
            or _hash(directory/'features_matrix.csv') != manifest['source_csv_sha256']):
        raise RuntimeError('The installed full-history source content differs from the published snapshot.')


def _verified_history(directory, forecast, manifest, stamp, completed):
    _verify_source_files(directory, manifest)
    key = (manifest['source_manifest_sha256'], manifest['source_csv_sha256'],
           manifest['data_sha256'], manifest['registry_sha256'], manifest['model_algorithm_sha256'],
           manifest['min_coverage'], completed.date().isoformat())
    with _CACHE_LOCK:
        if key in _HISTORY_CACHE:
            _HISTORY_CACHE.move_to_end(key)
            return _HISTORY_CACHE[key]
        try:
            frame = load_feature_matrix(directory)
        except (OSError, ValueError, KeyError) as error:
            raise RuntimeError('The full-history snapshot could not be verified.') from error
        if (frame.attrs.get('feature_generation_id') != manifest['feature_generation_id']
                or frame.attrs.get('data_sha256') != manifest['data_sha256']
                or frame.attrs.get('feature_manifest', {}).get('feature_csv_sha256') != manifest['source_csv_sha256']):
            raise RuntimeError('The verified history dataframe identity differs from the published snapshot.')
        if frame.date.max() < completed:
            raise RuntimeError('The verified source calendar does not reach the published input cutoff.')
        registry = get_registry()
        try:
            history = median.build_state_history(frame, registry=registry,
                min_coverage=manifest['min_coverage'], as_of=stamp)
        except (ValueError, KeyError) as error:
            raise RuntimeError('The published full-history observations could not be aggregated.') from error
        if history.attrs.get('registry_sha256') != manifest['registry_sha256']:
            raise RuntimeError('The registry changed during full-history aggregation.')
        _verify_source_files(directory, manifest)
        result = (history, dict(start=frame.date.min().date().isoformat(),
                    end=min(frame.date.max(), completed).date().isoformat(),
                    source_calendar_end=frame.date.max().date().isoformat(),
                    completed_input_month=completed.date().isoformat()))
        _HISTORY_CACHE[key] = result
        while len(_HISTORY_CACHE) > _CACHE_SIZE:
            _HISTORY_CACHE.popitem(last=False)
        return result


def get_full_state_history(state_id, forecast, manifest, processed_dir=None):
    """Return all source-supported history for the caller's selected snapshot.

    The caller selects a published (or explicitly labelled local preview)
    context first. This function cannot select or publish a forecast vintage.
    Explicit source overrides fail closed; discovery accepts one exact manifest
    match and never substitutes a different generation.
    """
    code = resolve_state_id(state_id)
    stamp, completed = _validate_context(code, forecast, manifest)
    directory = _source_directory(manifest, processed_dir)
    history, source_window = _verified_history(directory, forecast, manifest, stamp, completed)
    state = history.loc[history.state_id.eq(code) & history.date.le(completed)].sort_values('date')
    genuine = state.loc[state.gwl_m_bgl.notna()]
    qualified = state.loc[state.training_eligible]
    first = genuine.iloc[0].date if len(genuine) else None
    selected = state.loc[state.date.ge(first)] if first is not None else state.iloc[:0]
    records = []
    for row in selected.to_dict('records'):
        observed = bool(pd.notna(row['gwl_m_bgl']))
        records.append(dict(date=row['date'].date().isoformat(),
            **{key: row[key] for key in _FIELDS}, is_observed=observed,
            is_imputed=False, is_forecast=False, is_forward_filled_display=False,
            value_type='observed_historical_median' if row['training_eligible'] else
                       'low_coverage_observed_median' if observed else 'missing'))
    result = dict(product=PRODUCT_NAME, history_version=HISTORY_VERSION,
        status='available' if len(genuine) else 'no_observations', state_id=code,
        state_name=STATES_REGISTRY[code]['name'], units='m_bgl', as_of=forecast['as_of'],
        generation_id=forecast['generation_id'], release_id=forecast.get('release_id', forecast['generation_id']),
        artifact_release=forecast['artifact_release'], release_manifest_sha256=forecast['release_manifest_sha256'],
        publication_status=forecast.get('publication_status'),
        model_name=forecast['model_name'], model_version=forecast['model_version'],
        feature_generation=manifest['feature_generation_id'], source_data_sha256=manifest['data_sha256'],
        source_csv_sha256=manifest['source_csv_sha256'], source_manifest_sha256=manifest['source_manifest_sha256'],
        registry_sha256=manifest['registry_sha256'], min_coverage=manifest['min_coverage'],
        aggregation_method='median_of_observed_district_month_means',
        earliest_observation_date=first.date().isoformat() if first is not None else None,
        earliest_eligible_date=qualified.iloc[0].date.date().isoformat() if len(qualified) else None,
        latest_observation_date=genuine.iloc[-1].date.date().isoformat() if len(genuine) else None,
        observed_state_months=len(genuine), qualified_state_months=len(qualified),
        history_start=first.date().isoformat() if first is not None else None,
        history_end=completed.date().isoformat() if first is not None else None,
        source_window=deepcopy(source_window), history=records)
    return finite_json(result)
