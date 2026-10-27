"""Acceptance gates consume sealed validation evidence without selecting or fitting."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from scripts import assess_retraining_candidate as assessment


def rows_for(year):
    records = []
    for district in range(10):
        for month in (1, 2, 3):
            for horizon in (1, 2):
                origin = pd.Timestamp(year=year, month=month, day=1)
                records.append(dict(district_id=f'TN-{district:02}', origin_date=origin.date().isoformat(),
                    target_date=(origin + pd.DateOffset(months=horizon)).date().isoformat(), horizon=horizon,
                    actual=10., frozen=11., retrained=10.98, persistence=11., seasonal=11.,
                    gained_accepted_history=True, newly_local_history=False, substantial_original_history=True))
    return pd.DataFrame(records)


@pytest.fixture
def evidence(tmp_path):
    protocol = {'selection': {'candidates': [{'name': 'locked'}]},
        'folds': [{'name': 'rolling_2023', 'train_target_cutoff': '2021-12-31',
            'validation_origin_start': '2023-01-01', 'validation_origin_end': '2023-12-01', 'validation_target_end': '2024-01-01'},
            {'name': 'rolling_2024', 'train_target_cutoff': '2022-12-31',
            'validation_origin_start': '2024-01-01', 'validation_origin_end': '2024-12-01', 'validation_target_end': '2025-01-01'}],
        'final_fit_target_cutoff': '2025-01-31',
        'promotion_requirements': {'untouched_post_refit_test_required': True,
            'rolling_validation_mae_gain_vs_frozen_and_persistence_at_least': .02,
            'rolling_validation_seasonal_paired_mae_no_worse': True,
            'supported_horizon_or_new_history_group_maximum_mae_regression': .10,
            'supported_panel_minimum_cases': 30, 'supported_panel_minimum_districts': 10,
            'complete_725_by_12_outputs_and_36_states': True, 'all_contract_and_rollback_checks_pass': True}}
    selection = {'phase': 'locked_before_retrospective_final_diagnostic', 'selected': 'locked',
        'parameters': {'n_estimators': 8}, 'scores': {'locked': {'do_not_reselect': True}},
        'training_code_sha256': 'frozen-training-code', 'final_target_cutoff': '2025-01-31',
        'selection_uses_january2026_labels': False, 'fold_results': []}
    for fold in protocol['folds']:
        filename = f"validation_{fold['name']}_locked.csv"
        rows_for(int(fold['name'][-4:])).to_csv(tmp_path / filename, index=False)
        selection['fold_results'].append({'phase': 'earlier_validation', 'candidate': 'locked',
            'fold': fold, 'max_train_target': fold['train_target_cutoff'],
            'validation_cases_file': filename, 'validation_cases_sha256': assessment._sha(tmp_path / filename)})
    protocol_path, selection_path = tmp_path / 'protocol.json', tmp_path / 'selection.json'

    def save():
        protocol_path.write_text(json.dumps(protocol), encoding='utf-8')
        selection['protocol_sha256'] = assessment._sha(protocol_path)
        selection_path.write_text(json.dumps(selection), encoding='utf-8')

    def change_cases(transform):
        for index, record in enumerate(selection['fold_results']):
            path = tmp_path / record['validation_cases_file']
            rows = pd.read_csv(path, float_precision='round_trip')
            rows = transform(rows, index)
            rows.to_csv(path, index=False)
            record['validation_cases_sha256'] = assessment._sha(path)
        save()

    save()
    return protocol_path, selection_path, protocol, selection, save, change_cases


def test_exact_relative_boundary_passes_but_missing_untouched_test_blocks_promotion(evidence):
    protocol_path, selection_path, _, selection, _, _ = evidence
    report = assessment.assess(protocol_path, selection_path, contracts_passed=True)
    assert report['checks']['relative_mean_fold_macro_gain_vs_frozen']
    assert report['checks']['relative_mean_fold_macro_gain_vs_persistence']
    assert report['checks']['seasonal_paired_mean_fold_macro_no_worse']
    assert report['checks']['supported_subgroups_no_excess_regression']
    assert report['blocking_reasons'] == ['untouched_post_refit_test_available']
    assert report['promoted'] is False and report['promotion_eligible'] is False
    assert report['selected'] == selection['selected']
    assert report['locked_scores'] == selection['scores']
    assert report['selection_recomputed'] is False and report['diagnostic_metrics_used'] is False
    assert len(report['validation']['insufficient_support_panels']) > 0
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('contracts,untouched', [(False, False), (False, True), (True, False)])
def test_no_candidate_is_eligible_without_both_external_prerequisites(evidence, contracts, untouched):
    report = assessment.assess(*evidence[:2], contracts_passed=contracts, untouched_test_available=untouched)
    assert report['promotion_eligible'] is False and report['promoted'] is False


def test_all_gates_only_authorize_a_separate_future_promotion_action(evidence):
    report = assessment.assess(*evidence[:2], contracts_passed=True, untouched_test_available=True)
    assert report['promotion_eligible'] is True
    assert report['decision'] == 'eligible_for_separate_promotion'
    assert report['promoted'] is False


def test_two_percent_is_relative_not_point_zero_two_metres(evidence):
    def transform(rows, index):
        return rows.assign(frozen=20., persistence=20., seasonal=20., retrained=19.85)
    evidence[5](transform)
    report = assessment.assess(*evidence[:2])
    check = report['validation']['relative_gain_checks']['frozen']
    assert check['observed_relative_gain'] == pytest.approx(.015)
    assert check['maximum_candidate_mae_m'] == pytest.approx(9.8)
    assert check['passed'] is False


def test_mean_fold_macro_gate_does_not_pool_unequal_fold_counts(evidence):
    def transform(rows, index):
        if index == 0:
            rows = rows.iloc[::2].copy()
        return rows.assign(retrained=10.97 if index == 0 else 10.99)
    evidence[5](transform)
    report = assessment.assess(*evidence[:2])
    assert report['validation']['mean_fold_district_macro_mae_m']['retrained'] == pytest.approx(.98)
    assert report['checks']['relative_mean_fold_macro_gain_vs_frozen'] is True


def test_perfect_baseline_cannot_establish_a_positive_relative_gain(evidence):
    evidence[5](lambda rows, index: rows.assign(frozen=10., retrained=10.))
    check = assessment.assess(*evidence[:2])['validation']['relative_gain_checks']['frozen']
    assert check['zero_baseline'] and check['observed_relative_gain'] is None
    assert check['passed'] is False


def test_supported_horizon_regression_cannot_hide_in_good_overall_error(evidence):
    def transform(rows, index):
        rows['retrained'] = np.where(rows.horizon.eq(1), 11.11, 10.1)
        rows['newly_local_history'] = rows.horizon.eq(1)
        return rows
    evidence[5](transform)
    report = assessment.assess(*evidence[:2])
    assert report['checks']['relative_mean_fold_macro_gain_vs_frozen'] is True
    assert report['checks']['supported_subgroups_no_excess_regression'] is False
    failed = [panel for panel in report['validation']['subgroup_checks'] if panel['status'] == 'failed']
    assert {panel['kind'] for panel in failed} == {'horizon', 'history_group'}
    assert all(panel['cases'] == 30 and panel['districts'] == 10 for panel in failed)


def test_supported_zero_baseline_requires_exact_zero_candidate_error(evidence):
    evidence[5](lambda rows, index: rows.assign(frozen=10., persistence=10., retrained=10.000001))
    report = assessment.assess(*evidence[:2])
    assert report['checks']['supported_subgroups_no_excess_regression'] is False


def test_missing_seasonal_fold_support_is_explicit_not_a_pass(evidence):
    evidence[5](lambda rows, index: rows.assign(seasonal=np.nan) if index == 0 else rows)
    report = assessment.assess(*evidence[:2])
    assert report['checks']['seasonal_paired_mean_fold_macro_no_worse'] is False
    assert report['validation']['seasonal_paired_mean_fold_macro_mae_m'] is None


@pytest.mark.parametrize('problem', ['final_phase', 'unknown_phase', 'selection_phase', 'duplicate_fold', 'missing_fold', 'escape'])
def test_only_complete_locked_earlier_validation_evidence_is_accepted(evidence, problem):
    _, _, _, selection, save, _ = evidence
    if problem == 'final_phase': selection['fold_results'][0]['phase'] = 'final_diagnostic'
    elif problem == 'unknown_phase': selection['fold_results'][0]['phase'] = 'unlabelled'
    elif problem == 'selection_phase': selection['phase'] = 'final_diagnostic'
    elif problem == 'duplicate_fold': selection['fold_results'].append(deepcopy(selection['fold_results'][0]))
    elif problem == 'missing_fold': selection['fold_results'].pop()
    else: selection['fold_results'][0]['validation_cases_file'] = '../outside.csv'
    save()
    with pytest.raises(ValueError):
        assessment.assess(*evidence[:2])


def test_case_and_protocol_hashes_cannot_change_after_sealing(evidence):
    protocol_path, selection_path, _, selection, _, _ = evidence
    case_path = selection_path.parent / selection['fold_results'][0]['validation_cases_file']
    case_path.write_bytes(case_path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='checksum'):
        assessment.assess(protocol_path, selection_path)
    protocol_path.write_bytes(protocol_path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='Protocol changed'):
        assessment.assess(protocol_path, selection_path)


def test_all_candidates_must_share_identical_targets_not_merely_equal_counts(evidence):
    _, selection_path, protocol, selection, save, _ = evidence
    protocol['selection']['candidates'].append({'name': 'other'})
    for record in list(selection['fold_results']):
        copied = deepcopy(record)
        copied['candidate'] = 'other'
        copied['validation_cases_file'] = record['validation_cases_file'].replace('locked', 'other')
        rows = pd.read_csv(selection_path.parent / record['validation_cases_file'])
        rows.loc[0, 'actual'] += .1
        rows.to_csv(selection_path.parent / copied['validation_cases_file'], index=False)
        copied['validation_cases_sha256'] = assessment._sha(selection_path.parent / copied['validation_cases_file'])
        selection['fold_results'].append(copied)
    save()
    with pytest.raises(ValueError, match='different target'):
        assessment.assess(*evidence[:2])


def test_inspected_2026_targets_cannot_enter_validation(evidence):
    def transform(rows, index):
        rows.loc[0, 'target_date'] = '2026-01-01'
        return rows
    evidence[5](transform)
    with pytest.raises(ValueError, match='chronological'):
        assessment.assess(*evidence[:2])


def test_even_a_relabelled_protocol_cannot_consume_reserved_2026_targets(evidence):
    _, _, protocol, selection, save, _ = evidence
    protocol['final_fit_target_cutoff'] = '2026-01-31'
    selection['final_target_cutoff'] = '2026-01-31'
    save()
    with pytest.raises(ValueError, match='cutoff'):
        assessment.assess(*evidence[:2])


def test_cli_checks_candidate_specific_contract_receipt_and_preserves_outputs(evidence, tmp_path):
    _, selection_path, _, selection, _, _ = evidence
    training = {'selected': selection['selected'], 'parameters': selection['parameters'],
        'training_code_sha256': selection['training_code_sha256'], 'candidate_model_sha256': 'a' * 64,
        'rollback_verified': True, 'reloaded_predictions_exact': True,
        'frozen_assets_unchanged': True, 'model_bytes_reproducible': True}
    (selection_path.parent / 'training_summary.json').write_text(json.dumps(training))
    contracts = {'validation': {'districts': 725, 'horizons': 8700}, 'schema': 'aquaiq_test_candidate',
        'candidate_model_sha256': 'a' * 64, 'registry_database_reconciled': 725,
        'district_and_state_api_reads': 761, 'inference_calls_during_forecast_reads': 0,
        'six_month_endpoints': 'passed', 'default_vintage_and_missing_assets': 'passed',
        'missing_generation_and_invalid_requests': 'passed'}
    contract_path, output = tmp_path / 'contracts.json', tmp_path / 'assessment.json'
    contract_path.write_text(json.dumps(contracts))
    arguments = ['--protocol', str(evidence[0]), '--selection', str(selection_path),
                 '--output', str(output), '--contracts', str(contract_path)]
    report = assessment.main(arguments)
    assert report['checks']['complete_contracts_and_rollback_verified'] is True
    assert report['checks']['untouched_post_refit_test_available'] is False
    assert json.loads(output.read_text()) == report
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        assessment.main(arguments)
    assert output.read_bytes() == before
    contracts['candidate_model_sha256'] = 'b' * 64
    contract_path.write_text(json.dumps(contracts))
    with pytest.raises(ValueError, match='complete candidate'):
        assessment._contracts(contract_path, selection_path)
