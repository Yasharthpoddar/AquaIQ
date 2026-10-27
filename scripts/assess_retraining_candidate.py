"""Assess locked retraining evidence; never fit, select or deploy a model.

Only earlier validation case files named by the sealed selection are read.
Inspected January 2026 diagnostic metrics have no role in this assessment.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

KEYS = ['district_id', 'origin_date', 'target_date', 'horizon']
MODELS = ('frozen', 'retrained', 'persistence')
HISTORY_GROUPS = ('gained_accepted_history', 'newly_local_history', 'substantial_original_history')
DIAGNOSTIC_TARGET_START = pd.Timestamp('2026-01-01')


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _no_larger(value, limit):
    # Permit floating arithmetic at the declared boundary, never round metrics.
    return bool(value <= limit or np.isclose(value, limit, rtol=1e-12, atol=0.))


def _metric(rows, name):
    if rows.empty:
        return {'n': 0, 'districts': 0, 'mae_m': None, 'district_macro_mae_m': None}
    absolute = (rows[name] - rows.actual).abs()
    return {'n': len(rows), 'districts': int(rows.district_id.nunique()),
            'mae_m': float(absolute.mean()),
            'district_macro_mae_m': float(absolute.groupby(rows.district_id).mean().mean())}


def _load_cases(directory, record, fold, final_cutoff):
    filename = record['validation_cases_file']
    if (not isinstance(filename, str) or Path(filename).name != filename
            or any(char in filename for char in ('/', '\\', ':'))
            or Path(filename).suffix.lower() != '.csv'):
        raise ValueError('Validation case files must be simple CSV names inside selection.parent.')
    path = (directory / filename).resolve()
    if path.parent != directory:
        raise ValueError('Validation evidence escapes selection.parent.')
    if _sha(path) != record['validation_cases_sha256']:
        raise ValueError(f'Validation case checksum changed: {filename}.')
    rows = pd.read_csv(path, float_precision='round_trip')
    required = set(KEYS + ['actual', *MODELS, 'seasonal', *HISTORY_GROUPS])
    if required - set(rows) or rows.empty or rows.district_id.isna().any():
        raise ValueError('Validation cases must be nonempty with complete paired fields.')
    if rows.duplicated(KEYS).any():
        raise ValueError('Duplicate validation target keys.')
    for name in ('origin_date', 'target_date'):
        rows[name] = pd.to_datetime(rows[name], errors='raise')
        if (rows[name].isna().any() or rows[name].dt.tz is not None
                or not rows[name].dt.is_month_start.all()):
            raise ValueError('Validation cases require exact calendar month starts.')
    horizon = pd.to_numeric(rows.horizon, errors='raise')
    if not (horizon.between(1, 12) & horizon.eq(horizon.astype(int))).all():
        raise ValueError('Validation horizon must be an integer from one to twelve.')
    rows['horizon'] = horizon.astype(int)
    expected = [origin + pd.DateOffset(months=int(h)) for origin, h in zip(rows.origin_date, horizon)]
    cutoff = pd.Timestamp(fold['train_target_cutoff'])
    first = pd.Timestamp(fold['validation_origin_start'])
    if (first < (cutoff.to_period('M') + 13).to_timestamp()
            or not rows.origin_date.between(first, pd.Timestamp(fold['validation_origin_end'])).all()
            or not rows.target_date.le(pd.Timestamp(fold['validation_target_end'])).all()
            or not rows.target_date.le(final_cutoff).all()
            or rows.target_date.ge(DIAGNOSTIC_TARGET_START).any()
            or (rows.target_date != expected).any()
            or pd.Timestamp(record['max_train_target']) > cutoff):
        raise ValueError('Validation evidence violates the locked chronological boundaries.')
    for name in ('actual', *MODELS):
        rows[name] = pd.to_numeric(rows[name], errors='raise')
        if not np.isfinite(rows[name]).all() or rows[name].lt(0).any():
            raise ValueError('All validation models must cover the same finite depth targets.')
    rows['seasonal'] = pd.to_numeric(rows.seasonal, errors='raise')
    available = rows.seasonal.notna()
    if (not np.isfinite(rows.loc[available, 'seasonal']).all()
            or rows.loc[available, 'seasonal'].lt(0).any()):
        raise ValueError('Seasonal baseline must be finite or explicitly unavailable.')
    for name in HISTORY_GROUPS:
        parsed = rows[name].astype('string').str.strip().str.lower().map({'true': True, 'false': False})
        if parsed.isna().any():
            raise ValueError('History group membership must contain explicit boolean values.')
        rows[name] = parsed.astype(bool)
    return rows.sort_values(KEYS).reset_index(drop=True), path


def _gain(candidate, baseline, required):
    # A perfect baseline cannot demonstrate a strictly positive percentage gain.
    return {'candidate_mean_fold_macro_mae_m': candidate, 'baseline_mean_fold_macro_mae_m': baseline,
            'required_relative_gain': required,
            'observed_relative_gain': (baseline - candidate) / baseline if baseline > 0 else None,
            'maximum_candidate_mae_m': baseline * (1 - required),
            'passed': bool(baseline > 0 and _no_larger(candidate, baseline * (1 - required))),
            'zero_baseline': baseline == 0}


def _subgroup(rows, fold_name, kind, name, requirements):
    counts = {'cases': len(rows), 'districts': int(rows.district_id.nunique())}
    result = {'fold': fold_name, 'kind': kind, 'name': name, **counts}
    if (counts['cases'] < requirements['supported_panel_minimum_cases']
            or counts['districts'] < requirements['supported_panel_minimum_districts']):
        return {**result, 'status': 'insufficient_support'}
    metrics = {model: _metric(rows, model) for model in MODELS}
    candidate = metrics['retrained']['mae_m']
    tolerance = requirements['supported_horizon_or_new_history_group_maximum_mae_regression']
    comparisons = {name: {'baseline_mae_m': metrics[name]['mae_m'],
        'maximum_candidate_mae_m': (1 + tolerance) * metrics[name]['mae_m'],
        'passed': _no_larger(candidate, (1 + tolerance) * metrics[name]['mae_m'])}
        for name in ('frozen', 'persistence')}
    return {**result, 'status': 'passed' if all(c['passed'] for c in comparisons.values()) else 'failed',
            'metrics': metrics, 'relative_regression_limit': tolerance, 'comparisons': comparisons}


def assess(protocol, selection, contracts_passed=False, untouched_test_available=False):
    """Assess protocol/selection JSON paths without changing the locked winner.

    Contracts and genuinely untouched test evidence are external prerequisites.
    The defaults fail closed; this report itself performs no promotion action.
    """
    if not isinstance(contracts_passed, bool) or not isinstance(untouched_test_available, bool):
        raise ValueError('Contract and untouched-test assertions must be explicit booleans.')
    protocol_path, selection_path = Path(protocol).resolve(), Path(selection).resolve()
    rules = json.loads(protocol_path.read_text(encoding='utf-8'))
    locked = json.loads(selection_path.read_text(encoding='utf-8'))
    if (locked.get('phase') != 'locked_before_retrospective_final_diagnostic'
            or locked.get('selection_uses_january2026_labels') is not False):
        raise ValueError('Only an earlier-validation selection locked before final diagnostics is accepted.')
    if locked.get('protocol_sha256') != _sha(protocol_path):
        raise ValueError('Protocol changed after the selection was locked.')
    requirements = rules['promotion_requirements']
    gain = requirements['rolling_validation_mae_gain_vs_frozen_and_persistence_at_least']
    regression = requirements['supported_horizon_or_new_history_group_maximum_mae_regression']
    if (not isinstance(gain, (int, float)) or isinstance(gain, bool) or not np.isfinite(gain)
            or not 0 < gain < 1 or not isinstance(regression, (int, float))
            or isinstance(regression, bool) or not np.isfinite(regression) or regression < 0):
        raise ValueError('Acceptance thresholds must be finite relative fractions.')
    for name in ('supported_panel_minimum_cases', 'supported_panel_minimum_districts'):
        if isinstance(requirements[name], bool) or not isinstance(requirements[name], int) or requirements[name] < 1:
            raise ValueError('Subgroup support thresholds must be positive integer counts.')
    candidates = [item['name'] for item in rules['selection']['candidates']]
    folds = {fold['name']: fold for fold in rules['folds']}
    chosen = locked['selected']
    if (chosen not in candidates or len(set(candidates)) != len(candidates)
            or len(folds) != len(rules['folds']) or not folds):
        raise ValueError('Locked candidate or fold inventory is invalid.')
    final_cutoff = pd.Timestamp(rules['final_fit_target_cutoff'])
    if (pd.isna(final_cutoff) or final_cutoff >= DIAGNOSTIC_TARGET_START
            or locked.get('final_target_cutoff') != final_cutoff.date().isoformat()):
        raise ValueError('Final fit cutoff differs from the locked protocol.')
    seen, paths, canonical, selected_rows = set(), set(), {}, {}
    evidence = []
    for record in locked['fold_results']:
        if record.get('phase') != 'earlier_validation':
            raise ValueError('Final/unknown phases cannot enter acceptance or selection evidence.')
        candidate, fold = record['candidate'], record['fold']
        key = (candidate, fold['name'])
        if (candidate not in candidates or fold['name'] not in folds or folds[fold['name']] != fold or key in seen):
            raise ValueError('Duplicate or inconsistent candidate/fold validation inventory.')
        rows, path = _load_cases(selection_path.parent, record, fold, final_cutoff)
        if path in paths:
            raise ValueError('Each candidate/fold must retain its own sealed validation file.')
        seen.add(key)
        paths.add(path)
        comparison_columns = KEYS + ['actual', 'frozen', 'persistence', 'seasonal', *HISTORY_GROUPS]
        comparable = rows[comparison_columns]
        if fold['name'] in canonical:
            try:
                pd.testing.assert_frame_equal(canonical[fold['name']], comparable, check_exact=True, check_dtype=False)
            except AssertionError as error:
                raise ValueError('Candidates were evaluated on different target/baseline/group cases.') from error
        else:
            canonical[fold['name']] = comparable
        evidence.append({'candidate': candidate, 'fold': fold['name'], 'file': path.name,
                         'sha256': record['validation_cases_sha256'], 'cases': len(rows)})
        if candidate == chosen:
            selected_rows[fold['name']] = rows
    if seen != {(candidate, fold) for candidate in candidates for fold in folds}:
        raise ValueError('All candidates must share every prespecified validation fold.')
    fold_metrics = {name: {model: _metric(rows, model) for model in MODELS}
                    for name, rows in selected_rows.items()}
    means = {model: float(np.mean([metrics[model]['district_macro_mae_m'] for metrics in fold_metrics.values()]))
             for model in MODELS}
    gains = {name: _gain(means['retrained'], means[name], gain) for name in ('frozen', 'persistence')}
    seasonal_folds = {name: {model: _metric(rows.loc[rows.seasonal.notna()], model)
                            for model in (*MODELS, 'seasonal')} for name, rows in selected_rows.items()}
    seasonal_complete = all(metrics['seasonal']['n'] > 0 for metrics in seasonal_folds.values())
    seasonal_means = ({model: float(np.mean([metrics[model]['district_macro_mae_m']
                       for metrics in seasonal_folds.values()])) for model in (*MODELS, 'seasonal')}
                      if seasonal_complete else None)
    seasonal_passed = bool(seasonal_complete and _no_larger(seasonal_means['retrained'], seasonal_means['seasonal']))
    panels = []
    for fold_name, rows in selected_rows.items():
        panels += [_subgroup(rows.loc[rows.horizon.eq(h)], fold_name, 'horizon', str(h), requirements)
                   for h in range(1, 13)]
        panels += [_subgroup(rows.loc[rows[name]], fold_name, 'history_group', name, requirements)
                   for name in HISTORY_GROUPS]
    supported = [panel for panel in panels if panel['status'] != 'insufficient_support']
    subgroups_passed = bool(supported and all(panel['status'] == 'passed' for panel in supported))
    checks = {
        'relative_mean_fold_macro_gain_vs_frozen': gains['frozen']['passed'],
        'relative_mean_fold_macro_gain_vs_persistence': gains['persistence']['passed'],
        'seasonal_paired_mean_fold_macro_no_worse': seasonal_passed,
        'supported_subgroups_no_excess_regression': subgroups_passed,
        'complete_contracts_and_rollback_verified': contracts_passed,
        'untouched_post_refit_test_available': untouched_test_available}
    reasons = [name for name, passed in checks.items() if not passed]
    explanations = {
        'relative_mean_fold_macro_gain_vs_frozen': 'The locked candidate does not establish the required relative gain over the frozen model.',
        'relative_mean_fold_macro_gain_vs_persistence': 'The locked candidate does not establish the required relative gain over persistence.',
        'seasonal_paired_mean_fold_macro_no_worse': ('At least one fold lacks seasonal comparison cases.' if not seasonal_complete
            else 'The mean fold macro MAE exceeds seasonal naive on identically paired cases.'),
        'supported_subgroups_no_excess_regression': ('No subgroup meets the prespecified support counts.' if not supported
            else 'A supported horizon or history subgroup exceeds the prespecified regression limit.'),
        'complete_contracts_and_rollback_verified': 'Complete candidate API/contract and rollback evidence has not been verified.',
        'untouched_post_refit_test_available': 'No genuinely untouched post-refit test evidence is available.'}
    return {'schema_version': 'aquaiq-locked-retraining-assessment-v1', 'selected': chosen,
        'locked_parameters': deepcopy(locked['parameters']), 'locked_scores': deepcopy(locked.get('scores', {})),
        'selection_recomputed': False, 'diagnostic_metrics_used': False, 'promoted': False,
        'promotion_eligible': all(checks.values()),
        'decision': 'eligible_for_separate_promotion' if all(checks.values()) else 'keep_frozen_production',
        'checks': checks, 'blocking_reasons': reasons,
        'blocking_reason_details': {name: explanations[name] for name in reasons},
        'requirements': deepcopy(requirements),
        'threshold_units': 'Relative fractions: 0.02 means a 2% reduction; 0.10 means a 10% increase, not metres.',
        'validation': {'fold_metrics': fold_metrics, 'mean_fold_district_macro_mae_m': means,
            'relative_gain_checks': gains, 'seasonal_paired_fold_metrics': seasonal_folds,
            'seasonal_paired_mean_fold_macro_mae_m': seasonal_means,
            'seasonal_gate_status': ('insufficient_support' if not seasonal_complete else 'passed' if seasonal_passed else 'failed'),
            'subgroup_gate_status': ('insufficient_support' if not supported else 'passed' if subgroups_passed else 'failed'),
            'subgroup_checks': panels,
            'supported_panels': len(supported),
            'insufficient_support_panels': [panel for panel in panels if panel['status'] == 'insufficient_support']},
        'inputs': {'protocol_sha256': _sha(protocol_path), 'selection_sha256': _sha(selection_path),
                   'validation_evidence': evidence},
        'limitations': ['Previously inspected January 2026 results are excluded from acceptance calculations.',
            'No untouched post-refit test currently exists; external availability defaults to false.',
            'Unsupported subgroups are reported without a pass claim; zero-error baselines cannot show positive relative gain.',
            'This utility does not select another candidate or change serving models or database publications.']}


def _contracts(report_path, selection_path):
    """Validate supplied API-count and immutable rollback evidence, without DB I/O."""
    report = json.loads(Path(report_path).read_text(encoding='utf-8'))
    training = json.loads((Path(selection_path).resolve().parent / 'training_summary.json').read_text(encoding='utf-8'))
    locked = json.loads(Path(selection_path).read_text(encoding='utf-8'))
    validation = report.get('validation', {})
    valid = (validation.get('districts') == 725 and validation.get('horizons') == 8700
        and report.get('registry_database_reconciled') == 725
        and report.get('district_and_state_api_reads') == 761
        and report.get('inference_calls_during_forecast_reads') == 0
        and re.fullmatch(r'aquaiq_test_[a-z0-9_]+', str(report.get('schema')))
        and all(report.get(name) == 'passed' for name in ('six_month_endpoints',
            'default_vintage_and_missing_assets', 'missing_generation_and_invalid_requests'))
        and all(training.get(name) is True for name in ('rollback_verified', 'reloaded_predictions_exact',
            'frozen_assets_unchanged', 'model_bytes_reproducible'))
        and training.get('selected') == locked.get('selected')
        and training.get('parameters') == locked.get('parameters')
        and training.get('training_code_sha256') == locked.get('training_code_sha256')
        and re.fullmatch(r'[0-9a-f]{64}', str(training.get('candidate_model_sha256')))
        and report.get('candidate_model_sha256') == training.get('candidate_model_sha256'))
    if not valid:
        raise ValueError('Supplied contract/rollback reports do not verify the complete candidate release.')
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('protocol', 'selection', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--contracts', type=Path, help='Optional verified nationwide API report; rollback summary must accompany selection.')
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError('Assessment output must be a new JSON file.')
    if args.output.suffix.lower() != '.json':
        raise ValueError('Assessment output requires a .json extension.')
    contracts = _contracts(args.contracts, args.selection) if args.contracts else False
    report = assess(args.protocol, args.selection, contracts_passed=contracts)
    report['created_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['assessment_code_sha256'] = _sha(Path(__file__))
    if args.contracts:
        report['inputs']['contract_report_sha256'] = _sha(args.contracts)
        report['inputs']['training_summary_sha256'] = _sha(args.selection.parent / 'training_summary.json')
    encoded = json.dumps(report, indent=2, allow_nan=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(encoded + '\n')
    print(json.dumps({'selected': report['selected'], 'promoted': False,
                      'checks': report['checks'], 'blocking_reasons': report['blocking_reasons']}, indent=2))
    return report


if __name__ == '__main__':
    main()
