"""Paired retrospective evaluation of verified frozen and retrained bundles.

Both bundles see one identical feature snapshot and the production district
forecast path. This module never fits, selects, calibrates or publishes a model.
Previously inspected targets remain retrospective evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from models import climate_forecast_12m as climate
from models import tiered_forecast as tiered
from models.district_registry import get_registry
from models.ensemble import _as_of, _completed_feature_month
from models.xgboost_model import load_feature_matrix, sha256_file

CASE_KEYS = ['district_id', 'origin', 'target_date', 'horizon']
COLUMNS = ['district_id', 'state_id', 'origin', 'target_date', 'horizon',
           'actual', 'frozen', 'retrained', 'tier', 'observation_count', 'age',
           'persistence', 'seasonal', 'newly_enriched', 'frozen_method',
           'retrained_method', 'frozen_eligible', 'retrained_eligible']
AGE_GROUPS = ('0-3', '4-12', '13-36', '37+', 'no_local_history')


def _finite_number(value):
    return (not isinstance(value, (bool, np.bool_))
            and isinstance(value, (int, float, np.integer, np.floating))
            and np.isfinite(value))


def _check_forecast(value, district_id, cutoff, targets, local):
    """Reject a failed model or path; never drop its difficult cases."""
    if (value.get('status') != 'forecast' or value.get('district_id') != district_id
            or value.get('units') != 'm_bgl' or value.get('as_of') != cutoff.date().isoformat()
            or value.get('evidence_tier') not in tiered.TIERS
            or len(value.get('forecast', [])) != 12):
        raise ValueError(f'Invalid complete forecast for {district_id}.')
    expected_method = ('climate_conditioned_xgboost_12m' if value['evidence_tier'] == 'A'
                       else 'regional_seasonal_reference' if value['evidence_tier'] == 'C'
                       else 'local_persistence')
    count = value.get('observation_count')
    eligible = value.get('data_readiness', {}).get('eligible')
    expected_age = ((cutoff.year - local.date.iloc[-1].year) * 12
                    + cutoff.month - local.date.iloc[-1].month) if len(local) else None
    if (value.get('forecast_method') != expected_method or isinstance(count, bool)
            or not isinstance(count, int) or count != len(local)
            or (value['evidence_tier'] == 'C') != (count == 0)
            or value.get('data_age_months') != expected_age
            or not isinstance(eligible, (bool, np.bool_))):
        raise ValueError(f'Invalid forecast evidence for {district_id}.')
    for h, (row, target) in enumerate(zip(value['forecast'], targets), 1):
        if (isinstance(row.get('horizon'), bool) or row.get('horizon') != h
                or row.get('date') != target.date().isoformat()
                or not _finite_number(row.get('predicted_gwl')) or row['predicted_gwl'] < 0):
            raise ValueError(f'Invalid finite calendar forecast for {district_id} M+{h}.')


def evaluate(frame, frozen_bundle, candidate_bundle, origins, added_districts=None):
    """Return identical observed cases from the two production serving paths.

    ``added_districts`` identifies districts gaining accepted history, supplied
    by the separate data audit. It does not alter eligibility or sample choice.
    Origins can be any explicit valid as-of dates; normal completed-month rules
    determine what was available. Every retained origin/district requires both
    complete twelve-month paths, including horizons without observed targets.
    """
    required = {'district_id', 'date', 'gwl_current', 'is_observed', 'is_imputed'}
    if required - set(frame):
        raise ValueError(f'Evaluation feature fields missing: {sorted(required - set(frame))}')
    generation = frame.attrs.get('feature_generation_id')
    if not generation:
        raise ValueError('Evaluation requires a verified feature generation identity.')
    data = frame.copy(deep=False)
    data.attrs = {}
    data = data.assign(date=pd.to_datetime(data.date, errors='raise'))
    if (data.date.isna().any() or (data.date.dt.day != 1).any()
            or data.duplicated(['district_id', 'date']).any()):
        raise ValueError('Evaluation requires unique calendar district-month keys.')
    registry = get_registry()
    identifiers = [row['district_id'] for row in registry]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Evaluation registry contains duplicate districts.')
    if set(data.district_id) - set(identifiers):
        raise ValueError('Feature districts are absent from the canonical registry.')
    added = set(added_districts or ())
    if added - set(identifiers):
        raise ValueError('Newly enriched districts are absent from the canonical registry.')
    cutoffs = []
    for origin in origins:
        parsed = pd.Timestamp(origin)
        if pd.isna(parsed) or parsed.tzinfo is not None:
            raise ValueError('Evaluation origins must be known timezone-free calendar dates.')
        cutoffs.append(_as_of(parsed))
    if not cutoffs or len(set(cutoffs)) != len(cutoffs):
        raise ValueError('Evaluation origins must be nonempty, unique calendar dates.')
    for bundle in (frozen_bundle, candidate_bundle):
        card = bundle[1]
        if card.get('feature_generation_id') != generation:
            raise ValueError('Both model bundles must match the same feature generation.')
        train_cutoff = pd.Timestamp(card.get('train_target_cutoff'))
        if pd.isna(train_cutoff) or any(c < train_cutoff for c in cutoffs):
            raise ValueError('A model training cutoff occurs after an evaluation origin.')
        fingerprint = frame.attrs.get('data_sha256')
        if fingerprint and card.get('data_sha256') != fingerprint:
            raise ValueError('Model card and evaluation feature fingerprints differ.')
    groups = {did: group for did, group in data.groupby('district_id', sort=True)}
    last_month = data.date.max()
    labels = (tiered.observations(data, last_month + pd.offsets.MonthEnd(0))
              if not data.empty else data)
    labels = labels.set_index(['district_id', 'date']).gwl_current
    records, forecasted = [], 0
    for cutoff in sorted(cutoffs):
        origin_month = cutoff.to_period('M').to_timestamp()
        targets = pd.date_range(origin_month + pd.offsets.MonthBegin(1), periods=12, freq='MS')
        reference = None
        for metadata in registry:
            district_id = metadata['district_id']
            available = [(h, target, float(labels.loc[(district_id, target)]))
                         for h, target in enumerate(targets, 1)
                         if (district_id, target) in labels.index]
            if not available:
                continue
            if reference is None:
                reference = tiered.RegionalReference(data, cutoff)
            district = groups.get(district_id, data.iloc[:0])
            local = tiered.observations(district, cutoff)
            results = [tiered.forecast_district(district_id, district, cutoff,
                       generation, bundle, reference, calibration=None)
                       for bundle in (frozen_bundle, candidate_bundle)]
            for value in results:
                _check_forecast(value, district_id, cutoff, targets, local)
            left, right = results
            for field in ('evidence_tier', 'forecast_method', 'observation_count', 'data_age_months'):
                if left.get(field) != right.get(field):
                    raise ValueError(f'Paired forecast eligibility differs for {district_id}: {field}.')
            if left['data_readiness']['eligible'] != right['data_readiness']['eligible']:
                raise ValueError(f'Paired forecast eligibility differs for {district_id}.')
            forecasted += 1
            persistence = float(local.iloc[-1].gwl_current) if len(local) else np.nan
            for h, target, actual in available:
                previous_date = target - pd.DateOffset(years=1)
                previous = local.loc[local.date.eq(previous_date)]
                seasonal = (float(previous.iloc[0].gwl_current)
                            if previous_date <= _completed_feature_month(cutoff) and len(previous)
                            else np.nan)
                records.append(dict(district_id=district_id,
                    state_id=metadata.get('state_id', district_id.split('-', 1)[0]),
                    origin=cutoff.date().isoformat(), target_date=target.date().isoformat(), horizon=h,
                    actual=actual, frozen=float(left['forecast'][h - 1]['predicted_gwl']),
                    retrained=float(right['forecast'][h - 1]['predicted_gwl']), tier=left['evidence_tier'],
                    observation_count=len(local), age=left.get('data_age_months'),
                    persistence=persistence, seasonal=seasonal, newly_enriched=district_id in added,
                    frozen_method=left['forecast_method'], retrained_method=right['forecast_method'],
                    frozen_eligible=bool(left['data_readiness']['eligible']),
                    retrained_eligible=bool(right['data_readiness']['eligible'])))
        print(f'Paired replay {cutoff.date()}: {len(records)} cumulative observed cases.', flush=True)
    table = pd.DataFrame(records, columns=COLUMNS)
    potential = len(identifiers) * len(cutoffs) * 12
    table.attrs['evaluation_coverage'] = {
        'canonical_districts': len(identifiers), 'requested_origins': [c.date().isoformat() for c in sorted(cutoffs)],
        'potential_target_slots': potential, 'observed_paired_cases': len(table),
        'unavailable_target_slots': potential - len(table), 'forecasted_district_origins': forecasted,
        'enrichment_membership_supplied': added_districts is not None,
        'newly_enriched_districts_supplied': len(added)}
    return table


def _counts(rows):
    keys = rows[CASE_KEYS].sort_values(CASE_KEYS).to_dict('records')
    return {'cases': len(rows), 'districts': int(rows.district_id.nunique()),
            'states': int(rows.state_id.nunique()), 'origins': int(rows.origin.nunique()),
            'target_months': int(rows.target_date.nunique()),
            'origin_dates': sorted(rows.origin.unique().tolist()),
            'target_dates': sorted(rows.target_date.unique().tolist()),
            'case_keys_sha256': hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()}


def _metrics(actual, predicted):
    if not len(actual):
        return {'n': 0, 'mae_m': None, 'rmse_m': None}
    error = np.asarray(predicted, float) - np.asarray(actual, float)
    return {'n': len(error), 'mae_m': float(np.abs(error).mean()),
            'rmse_m': float(np.sqrt(np.mean(error ** 2)))}


def _paired(rows, baseline):
    baselines = ('persistence', 'seasonal') if baseline == 'seasonal' else ('persistence',)
    subset = rows.loc[rows[list(baselines)].notna().all(axis=1)]
    return {'status': 'evaluated' if len(subset) else 'unavailable', **_counts(subset),
            'excluded_cases': len(rows) - len(subset), 'paired_baselines': list(baselines),
            **{name: _metrics(subset.actual, subset[name])
               for name in ('frozen', 'retrained', *baselines)}}


def _panel(rows, *, district=False):
    result = {'status': 'evaluated' if len(rows) else 'unavailable', **_counts(rows),
              'baseline_availability': {name: {'available_cases': int(rows[name].notna().sum()),
                  'missing_cases': int(rows[name].isna().sum())} for name in ('persistence', 'seasonal')}}
    if district and len(rows) < 5:
        result.update(status='insufficient_cases', reason='Fewer than five cases; district errors are not interpreted.')
        return result
    result.update({name: _metrics(rows.actual, rows[name]) for name in ('frozen', 'retrained')})
    result['persistence_paired'] = _paired(rows, 'persistence')
    result['seasonal_paired'] = _paired(rows, 'seasonal')
    return result


def summarize(table):
    """Describe every paired population; no horizon or unavailable baseline vanishes."""
    if set(COLUMNS) - set(table):
        raise ValueError('Paired evaluation table is missing its required columns.')
    if table.duplicated(CASE_KEYS).any():
        raise ValueError('Duplicate paired evaluation case keys.')
    for name in ('actual', 'frozen', 'retrained'):
        if any(not _finite_number(value) or value < 0 for value in table[name]):
            raise ValueError(f'Paired {name} values must all be finite nonnegative depths.')
    for name in ('persistence', 'seasonal'):
        if any(not pd.isna(value) and (not _finite_number(value) or value < 0) for value in table[name]):
            raise ValueError(f'Invalid {name} baseline value.')
    if any(not isinstance(value, (bool, np.bool_)) for value in table.newly_enriched):
        raise ValueError('Enrichment membership must be explicit boolean values.')
    if any(h not in range(1, 13) or isinstance(h, bool) for h in table.horizon):
        raise ValueError('Invalid paired forecast horizon.')
    if any(t not in tiered.TIERS for t in table.tier):
        raise ValueError('Invalid paired evidence tier.')
    if (not table.frozen_method.equals(table.retrained_method)
            or not table.frozen_eligible.equals(table.retrained_eligible)):
        raise ValueError('Paired forecast methods or eligibility differ.')
    if len(table):
        origins = pd.to_datetime(table.origin, errors='raise')
        targets = pd.to_datetime(table.target_date, errors='raise')
        expected = [origin.to_period('M').to_timestamp() + pd.DateOffset(months=int(h))
                    for origin, h in zip(origins, table.horizon)]
        if origins.isna().any() or targets.isna().any() or (targets != expected).any():
            raise ValueError('Paired target dates must match exact calendar horizons.')
    age = pd.to_numeric(table.age, errors='raise')
    if (age.dropna() < 0).any() or np.isinf(age.to_numpy(dtype=float)).any():
        raise ValueError('Invalid observation age.')
    groups = pd.cut(age, [-1, 3, 12, 36, np.inf], labels=AGE_GROUPS[:-1]).astype('string').fillna(AGE_GROUPS[-1])
    return {'status': 'evaluated' if len(table) else 'unavailable', 'units': 'm_bgl',
        'new_blind_evaluation': False, 'model_or_interval_selection_performed': False,
        'database_written': False, 'production_model_replaced': False,
        'coverage': table.attrs.get('evaluation_coverage', {}), 'overall': _panel(table),
        'by_horizon': {str(h): _panel(table.loc[table.horizon.eq(h)]) for h in range(1, 13)},
        'by_tier': {tier: _panel(table.loc[table.tier.eq(tier)]) for tier in tiered.TIERS},
        'by_state': {str(state): _panel(rows) for state, rows in table.groupby('state_id', sort=True)},
        'by_district': {str(did): _panel(rows, district=True) for did, rows in table.groupby('district_id', sort=True)},
        'by_origin': {str(origin): _panel(rows) for origin, rows in table.groupby('origin', sort=True)},
        'by_age': {name: _panel(table.loc[groups.eq(name)]) for name in AGE_GROUPS},
        'by_newly_enriched': {'newly_enriched': _panel(table.loc[table.newly_enriched.eq(True)]),
                              'other': _panel(table.loc[table.newly_enriched.eq(False)])},
        'limitations': ['Retrospective observed-target comparison; inspected January 2026 labels are not a new blind test.',
            'Repeated districts, overlapping horizons and target dates are dependent cases.',
            'Observation dates do not establish historical provider publication availability or stable well panels.',
            'All comparisons use identical target keys; seasonal panels pair both models and both baselines on their common available cases.',
            'District errors require at least five cases; five dependent cases do not establish local skill.',
            'No model selection, uncertainty calibration or prospective accuracy claim is made.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', type=Path, required=True, help='Verified feature snapshot directory.')
    parser.add_argument('--frozen-checkpoint', type=Path, required=True)
    parser.add_argument('--candidate-checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing evidence is never replaced.')
    parser.add_argument('--origins', nargs='+', required=True, help='Explicit space-separated or comma-separated as-of dates.')
    parser.add_argument('--added-districts', type=Path, help='Optional JSON list of canonical districts gaining history.')
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError('Evaluation output must be a new directory.')
    frame = load_feature_matrix(args.features)
    generation = frame.attrs['feature_generation_id']
    bundles = [climate.load_bundle(path, expected_generation=generation)
               for path in (args.frozen_checkpoint, args.candidate_checkpoint)]
    origins = [value for entry in args.origins for value in entry.split(',') if value]
    added = None
    if args.added_districts:
        added = json.loads(args.added_districts.read_text(encoding='utf-8'))
        if not isinstance(added, list) or any(not isinstance(did, str) for did in added):
            raise ValueError('--added-districts must contain a JSON list of canonical district IDs.')
    table = evaluate(frame, *bundles, origins, added_districts=added)
    report = summarize(table)
    report.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
        inputs={'feature_generation_id': generation, 'feature_csv_sha256': frame.attrs['feature_manifest']['feature_csv_sha256'],
            'feature_dataframe_sha256': frame.attrs.get('data_sha256'),
            'frozen_model_sha256': bundles[0][1]['model_sha256'], 'candidate_model_sha256': bundles[1][1]['model_sha256'],
            'frozen_pointer_sha256': sha256_file(args.frozen_checkpoint),
            'candidate_pointer_sha256': sha256_file(args.candidate_checkpoint),
            'added_districts_sha256': sha256_file(args.added_districts) if args.added_districts else None,
            'evaluation_code_sha256': sha256_file(Path(__file__))})
    # Serialize strict JSON before reserving the destination; the directory's
    # exclusive creation prevents concurrent/repeated runs from overwriting it.
    encoded = json.dumps(report, indent=2, allow_nan=False)
    args.output.mkdir(parents=True, exist_ok=False)
    cases_path = args.output / 'cases.csv'
    table.to_csv(cases_path, index=False)
    report['cases_sha256'] = sha256_file(cases_path)
    encoded = json.dumps(report, indent=2, allow_nan=False)
    (args.output / 'summary.json').write_text(encoded + '\n', encoding='utf-8')
    print(json.dumps(report['overall'], indent=2, allow_nan=False))
    return report


if __name__ == '__main__':
    main()
