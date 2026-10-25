"""Canonical project registry, derived from the checked-in state-qualified crosswalk.

This is the repository's registration snapshot, not a claim to be the latest LGD
administrative inventory. Multiple source aliases must agree on one identity.
"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import hashlib
import pandas as pd
from models.state_mapping import STATES_REGISTRY, resolve_state_id

PATH = Path(__file__).resolve().parents[1] / 'data_ingestion/district_crosswalk.csv'


def validate_registry(crosswalk):
    required = ['canonical_district_id', 'canonical_name', 'canonical_state']
    if set(required) - set(crosswalk):
        raise ValueError('Incomplete canonical district registry.')
    if crosswalk[required].isna().any().any():
        raise ValueError('Missing registry identity.')
    crosswalk = crosswalk.copy()
    for field in required:
        if crosswalk[field].str.strip().eq('').any():
            raise ValueError('Empty registry identity.')
        crosswalk[field] = crosswalk[field].str.strip()
    crosswalk['canonical_state'] = crosswalk.canonical_state.map(lambda s: STATES_REGISTRY[resolve_state_id(s)]['name'])
    if crosswalk.groupby(required[0])[required[1:]].nunique().gt(1).any().any():
        raise ValueError('Conflicting district names or state membership.')
    if 'legacy_district_id' in crosswalk and crosswalk.groupby('legacy_district_id')[required[0]].nunique().gt(1).any():
        raise ValueError('Ambiguous legacy district mapping.')
    registry = crosswalk[required].drop_duplicates().rename(columns={
        required[0]: 'district_id', required[1]: 'district_name', required[2]: 'state_name'})
    for row in registry.itertuples():
        if (not isinstance(row.district_id, str) or '-' not in row.district_id
                or row.district_id.split('-', 1)[0] not in STATES_REGISTRY
                or resolve_state_id(row.state_name) != row.district_id[:2]):
            raise ValueError('Invalid district ID or state membership.')
    registry['state_id'] = registry.district_id.str[:2]
    if registry.duplicated(['state_id', 'district_name']).any():
        raise ValueError('Duplicate district within a state.')
    return registry.sort_values('district_id').reset_index(drop=True)


@lru_cache(maxsize=2)
def _snapshot(raw):
    registry = validate_registry(pd.read_csv(BytesIO(raw), dtype=str))
    return tuple(registry.to_dict('records'))


def get_registry():
    return [dict(row) for row in _snapshot(PATH.read_bytes())]


def registry_hash():
    return hashlib.sha256(PATH.read_bytes()).hexdigest()


def reconcile_features(frame, registry=None):
    ids = {r['district_id'] for r in (registry or get_registry())}
    unknown = set(frame.district_id) - ids
    if unknown:
        raise ValueError(f'Feature districts absent from registry: {sorted(unknown)}')
    if frame.duplicated(['district_id', 'date']).any():
        raise ValueError('Duplicate district-month feature keys.')
    return {'registry_districts': len(ids), 'feature_districts': frame.district_id.nunique(),
            'districts_without_feature_rows': sorted(ids - set(frame.district_id))}
