"""Read-only source/release coverage audit; no prediction, training or database calls.

Observation counts are distinct genuine district-month aggregates, not wells.
An optional generated JSON snapshot is checked against the independent source
counts; this does not publish or change any release.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from db.connection import finite_json
from models import state_median_forecast as median
from models.district_registry import get_registry, registry_hash
from models.ensemble import _as_of, _completed_feature_month
from models.state_forecast import state_observed_mask
from models.state_mapping import STATES_REGISTRY
from models.xgboost_model import load_feature_matrix, sha256_file


def training_gates(state, card, entry):
    """Trace the actual early-return gates without fitting a model."""
    cutoff = pd.Timestamp(card['training_cutoff'])
    state = state.loc[state.date.le(cutoff)]
    eligible, count, span = median._eligibility(state)
    result = dict(coverage_qualified_training_months=count, qualified_span_months=span,
                  supervised_target_months=entry.get('training_target_months'),
                  pre_validation_fit_target_months=None, validation_target_months=None,
                  rejection_conditions=[])
    reasons = result['rejection_conditions']
    if count < median.MIN_HISTORY:
        reasons.append('qualified_months_below_36')
    if span < median.MIN_SPAN_MONTHS:
        reasons.append('qualified_span_below_60_months')
    # Trained entries already establish that these gates passed. Computing
    # examples is needed only to explain otherwise opaque rejected entries.
    if eligible and entry.get('status') != 'trained':
        examples = median.training_examples(state, cutoff)
        targets = int(examples.target_date.nunique()) if len(examples) else 0
        result['supervised_target_months'] = targets
        if targets < median.MIN_TRAINING_TARGETS:
            reasons.append('supervised_target_months_below_24')
        else:
            start = pd.Timestamp(card.get('validation_start', '2017-01-01'))
            fit = int(examples.loc[examples.target_date.lt(start)].target_date.nunique())
            val = int(examples.loc[examples.origin.ge(start) & examples.target_date.ge(start)].target_date.nunique())
            result.update(pre_validation_fit_target_months=fit, validation_target_months=val)
            if fit < median.MIN_TRAINING_TARGETS:
                reasons.append('pre_validation_development_targets_below_24')
            if val < 3:
                reasons.append('chronological_validation_targets_below_3')
    return result


def audit_coverage(frame, card, as_of, registry=None, generation=None):
    registry = get_registry() if registry is None else registry
    codes = sorted({row['state_id'] for row in registry})
    if set(card.get('states', {})) != set(codes):
        raise ValueError('The audited model card must account for the exact registered state inventory.')
    for key in ('feature_generation_id', 'data_sha256'):
        if card.get(key) is not None and card[key] != frame.attrs.get(key):
            raise ValueError('The audited model card and source snapshot identities differ.')
    cutoff = _as_of(as_of)
    completed = _completed_feature_month(cutoff)
    origin = cutoff.to_period('M').to_timestamp()
    available = frame.loc[pd.to_datetime(frame.date).le(completed)].copy()
    available.attrs.update(frame.attrs)
    history = median.build_state_history(available, registry=registry, min_coverage=card.get('min_coverage', .5))
    depth = pd.to_numeric(available.gwl_current, errors='coerce')
    valid = state_observed_mask(available) & np.isfinite(depth) & depth.ge(0)
    observations = available.loc[valid, ['district_id', 'date']].copy()
    observations['date'] = pd.to_datetime(observations.date).dt.to_period('M').dt.to_timestamp()
    observations = observations.drop_duplicates(['district_id', 'date'])
    mapping = {row['district_id']: row['state_id'] for row in registry}
    observations['state_id'] = observations.district_id.map(mapping)
    rows = []
    for code in codes:
        state = history.loc[history.state_id.eq(code)].sort_values('date')
        genuine = state.loc[state.gwl_m_bgl.notna()]
        qualified = state.loc[state.training_eligible]
        references = qualified.loc[qualified.date.lt(origin)]
        obs = observations.loc[observations.state_id.eq(code)]
        entry = card['states'][code]
        gates = training_gates(state, card, entry)
        latest = genuine.iloc[-1] if len(genuine) else None
        old_status, old_message = 'insufficient_data', entry.get('reason')
        if pd.Timestamp(card['training_cutoff']) > completed:
            old_status, old_message = 'model_unavailable', 'Artifact training cutoff exceeds available inputs.'
        elif entry.get('status') == 'trained':
            if references.empty or median._distance(origin, references.iloc[-1].date) > median.MAX_REFERENCE_AGE_MONTHS:
                old_message = 'No coverage-qualified state median within the last 12 months.'
                gates['rejection_conditions'].append('qualified_reference_missing_or_older_than_12_months')
            else:
                old_status, old_message = 'forecast', None
        if genuine.empty:
            gates['rejection_conditions'].insert(0, 'no_genuine_observations')
        expected = 'state_median_xgboost' if old_status == 'forecast' else 'persistence_fallback' if len(genuine) else 'no_observations'
        rows.append(dict(state_id=code, state_name=STATES_REGISTRY[code]['name'],
            genuine_district_month_observations=len(obs), districts_with_genuine_observations=int(obs.district_id.nunique()),
            observed_state_months=len(genuine), coverage_qualified_state_months=len(qualified),
            **gates, latest_genuine_observation_date=latest.date.date().isoformat() if latest is not None else None,
            latest_observed_state_median_m_bgl=float(latest.gwl_m_bgl) if latest is not None else None,
            latest_observation_age_months=median._distance(origin, latest.date) if latest is not None else None,
            latest_qualified_observation_date=references.iloc[-1].date.date().isoformat() if len(references) else None,
            latest_contributing_districts=int(latest.contributing_districts_count) if latest is not None else 0,
            registered_districts=int(state.total_districts_in_state.iloc[-1]),
            latest_coverage_pct=float(latest.district_coverage_pct) if latest is not None else 0.,
            old_model_card_status=entry.get('status'), old_status=old_status,
            old_horizon_rows=12 if old_status == 'forecast' else 0, old_message=old_message,
            expected_policy_method=expected))
    report = dict(as_of=cutoff.date().isoformat(), completed_input_month=completed.date().isoformat(),
        source_generation=frame.attrs.get('feature_generation_id'), source_data_sha256=frame.attrs.get('data_sha256'),
        observation_count_unit='distinct_genuine_district_month_aggregates_not_wells',
        minimum_xgboost_policy=dict(qualified_months=median.MIN_HISTORY, span_months=median.MIN_SPAN_MONTHS,
            supervised_target_months=median.MIN_TRAINING_TARGETS, development_fit_target_months=median.MIN_TRAINING_TARGETS,
            validation_target_months=3, validation_start=card.get('validation_start', '2017-01-01')),
        genuine_district_month_observations=len(observations), registered_states=len(rows),
        states_with_genuine_observations=sum(row['observed_state_months'] > 0 for row in rows),
        states_without_genuine_observations=[row['state_id'] for row in rows if row['observed_state_months'] == 0],
        old_status_counts=dict(Counter(row['old_status'] for row in rows)),
        expected_policy_method_counts=dict(Counter(row['expected_policy_method'] for row in rows)),
        status='source_audit_only_not_a_generated_forecast', after=None, states=rows)
    if generation is not None:
        report['after'] = compare_generation(report, generation)
    return finite_json(report)


def compare_generation(report, generation):
    """Independently check coverage and persistence against the actual source."""
    expected = {row['state_id'] for row in report['states']}
    if not isinstance(generation, dict) or set(generation) != expected:
        raise ValueError('Generated snapshot must contain the exact registered state inventory.')
    violations, methods, statuses, release_ids, signatures, generation_ids = [], Counter(), Counter(), set(), set(), set()
    origin = pd.Timestamp(report['as_of']).to_period('M').to_timestamp()
    for row in report['states']:
        code = row['state_id']
        value = generation[code]
        if (value.get('state_id') != code or value.get('as_of') != report['as_of']
                or value.get('feature_generation') != report['source_generation']
                or value.get('source_data_sha256') != report['source_data_sha256']):
            raise ValueError('Generated snapshot and audited state/vintage/source identities differ.')
        method, status, path = value.get('forecast_method'), value.get('status'), value.get('forecast', [])
        methods[method] += 1
        statuses[status] += 1
        release_ids.add(value.get('artifact_release'))
        signatures.add(value.get('release_manifest_sha256'))
        generation_ids.add(value.get('generation_id'))
        if method != row['expected_policy_method']:
            violations.append(f'{code}:unexpected_forecast_method')
        has_data = row['observed_state_months'] > 0
        if (value.get('genuine_observation_count') != row['genuine_district_month_observations']
                or value.get('genuine_observed_months') != row['observed_state_months']
                or value.get('latest_observation_date') != row['latest_genuine_observation_date']
                or value.get('observation_age_months') != row['latest_observation_age_months']):
            violations.append(f'{code}:generated_observation_metadata_differs_from_source')
        if has_data and (status != 'forecast' or len(path) != 12):
            violations.append(f'{code}:data_bearing_state_missing_twelve_month_forecast')
        elif not has_data and (status != 'insufficient_data' or path or method != 'no_observations'):
            violations.append(f'{code}:no_data_state_requires_explicit_unavailable_status')
        if not has_data and value.get('unavailable_reason') != 'no_genuine_observations':
            violations.append(f'{code}:missing_no_observations_reason')
        for h, point in enumerate(path, 1):
            depth = point.get('predicted_gwl')
            if (point.get('horizon') != h or point.get('target_date') != (origin+pd.DateOffset(months=h)).date().isoformat()
                    or isinstance(depth, bool) or not isinstance(depth, (int, float)) or not np.isfinite(depth) or depth < 0
                    or point.get('units') != 'm_bgl' or point.get('is_forecast') is not True or point.get('is_observed') is not False):
                violations.append(f'{code}:invalid_monthly_forecast_value_or_calendar')
                break
        if method == 'persistence_fallback' and has_data:
            if (value.get('historical_reference_date') != row['latest_genuine_observation_date']
                    or value.get('observation_age_months') != row['latest_observation_age_months']
                    or any(isinstance(point.get('predicted_gwl'), bool)
                        or not isinstance(point.get('predicted_gwl'), (int, float))
                        or not np.isfinite(point['predicted_gwl'])
                        or abs(point['predicted_gwl']-row['latest_observed_state_median_m_bgl']) > 1e-9 for point in path)):
                violations.append(f'{code}:persistence_does_not_repeat_the_actual_latest_genuine_median')
            metrics = value.get('evaluation', {})
            if metrics.get('n') != 0 or metrics.get('mae_m') is not None or metrics.get('rmse_m') is not None:
                violations.append(f'{code}:fallback_must_not_inherit_xgboost_accuracy_metrics')
        row.update(final_status=status, final_forecast_method=method, final_horizon_rows=len(path),
                   final_reference_date=value.get('historical_reference_date'))
    if len(release_ids) != 1 or None in release_ids or len(signatures) != 1 or None in signatures or len(generation_ids) != 1:
        violations.append('mixed_or_missing_release_provenance')
    return dict(status_counts=dict(statuses), method_counts=dict(methods), acceptance_met=not violations,
                violations=violations, artifact_release=next(iter(release_ids)) if len(release_ids) == 1 else None,
                release_manifest_sha256=next(iter(signatures)) if len(signatures) == 1 else None,
                generation_id=next(iter(generation_ids)) if len(generation_ids) == 1 else None,
                publication_status='not_checked_no_publication_performed')


def write_audit(directory, report):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory/'coverage.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    rows = [{**row, 'rejection_conditions': ';'.join(row['rejection_conditions'])} for row in report['states']]
    pd.DataFrame(rows).to_csv(directory/'coverage.csv', index=False)
    lines = ['# State median coverage audit', '',
        'Counts are genuine district-month aggregates, not wells. Missing, imputed, invalid and future values are excluded. Proposed methods are not claims that a new forecast has been generated.', '',
        '| State | Genuine district-months | Observed state months | Qualified months | Latest observed month | Old status | Method | Forecast months | Final status |',
        '|---|---:|---:|---:|---|---|---|---:|---|']
    for row in report['states']:
        lines.append(f'| {row["state_id"]} — {row["state_name"]} | {row["genuine_district_month_observations"]} | {row["observed_state_months"]} | {row["coverage_qualified_state_months"]} | {row["latest_genuine_observation_date"] or "none"} | {row["old_status"]} | {row.get("final_forecast_method", row["expected_policy_method"])} | {row.get("final_horizon_rows", "pending")} | {row.get("final_status", "not generated")} |')
    lines += ['', 'Exact XGBoost rejection conditions, development split counts, reference coverage and source identities are in coverage.json and coverage.csv.', '']
    (directory/'coverage.md').write_text('\n'.join(lines), encoding='utf-8')


def load_release_card(directory, frame):
    directory = Path(directory)
    manifest = json.loads((directory/'release_manifest.json').read_text(encoding='utf-8'))
    path = directory/'models/model_card.json'
    if sha256_file(path) != manifest.get('model_card_sha256'):
        raise ValueError('Audited release model-card checksum mismatch.')
    card = json.loads(path.read_text(encoding='utf-8'))
    if (manifest.get('source_csv_sha256') != frame.attrs['feature_manifest']['feature_csv_sha256']
            or manifest.get('registry_sha256') != registry_hash()
            or card.get('implementation_sha256') != sha256_file(median.__file__)):
        raise ValueError('Audited release source, registry or model implementation differs.')
    for code, signature in manifest['models'].items():
        model = (directory/'models'/card['states'][code]['file']).resolve()
        if model.parent != (directory/'models').resolve() or sha256_file(model) != signature:
            raise ValueError('Audited model inventory path or checksum mismatch.')
    return card, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--processed-dir', type=Path, required=True)
    parser.add_argument('--release-dir', type=Path, required=True, help='Existing r1 release whose XGBoost-only coverage is being audited.')
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--generation', type=Path, help='Optional actual r2 JSON snapshot to independently check after coverage.')
    parser.add_argument('--output', type=Path, required=True, help='New audit directory, never overwritten.')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('--output must be a new directory.')
    frame = load_feature_matrix(args.processed_dir)
    card, manifest = load_release_card(args.release_dir, frame)
    generation = json.loads(args.generation.read_text(encoding='utf-8')) if args.generation else None
    report = audit_coverage(frame, card, args.as_of, generation=generation)
    report.update(audited_artifact_release=manifest['artifact_release'],
                  audited_model_card_sha256=manifest['model_card_sha256'],
                  source_csv_sha256=frame.attrs['feature_manifest']['feature_csv_sha256'])
    write_audit(args.output, report)
    print(json.dumps({key: value for key, value in report.items() if key != 'states'}, indent=2))
    if report['after'] is not None and not report['after']['acceptance_met']:
        raise ValueError('Generated state coverage audit failed; inspect coverage.json for violations.')
    return report


if __name__ == '__main__':
    main()
