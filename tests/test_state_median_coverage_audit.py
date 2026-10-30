"""Coverage auditing counts genuine data independently of model readiness."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts import audit_state_median_coverage as audit


@pytest.fixture
def source():
    registry = [dict(district_id=code+'-'+district, state_id=code)
                for code, districts in [('TN', ['A', 'B']), ('AS', ['A', 'B']), ('LA', ['A'])]
                for district in districts]
    rows = [dict(district_id=district, date=pd.Timestamp(date), gwl_current=value,
                 is_observed=observed, is_imputed=imputed)
            for district, date, value, observed, imputed in [
                ('TN-A', '2025-01-01', 2., True, False),
                ('TN-B', '2025-01-01', 6., True, False),
                ('TN-A', '2026-01-01', 8., True, False),  # Latest genuine median has low coverage.
                ('AS-A', '2025-01-01', 4., True, False),  # One genuine observation, stale.
                ('AS-B', '2026-01-01', 100., True, True),  # Conflicting provenance.
                ('AS-B', '2026-02-01', 50., False, False),
                ('LA-A', '2026-01-01', np.nan, True, False),
                ('LA-A', '2026-02-01', np.inf, True, False),
                ('LA-A', '2026-03-01', -1., True, False),
                ('AS-A', '2026-11-01', 1000., True, False),  # Future at the audited vintage.
            ]]
    frame = pd.DataFrame(rows)
    frame.attrs.update(feature_generation_id='fixture-only', data_sha256='fixture-hash')
    card = dict(training_cutoff='2026-09-01', validation_start='2017-01-01', min_coverage=.5,
        feature_generation_id='fixture-only', data_sha256='fixture-hash',
        states={code: dict(status='insufficient_data', reason='Insufficient XGBoost history.') for code in ['TN', 'AS', 'LA']})
    return frame, card, registry


def test_counts_genuine_observations_separately_from_training_quality(source, monkeypatch):
    frame, card, registry = source
    monkeypatch.setattr(audit.median, 'forecast_state', lambda *a, **k: pytest.fail('Audit must never infer.'))
    report = audit.audit_coverage(frame, card, '2026-10-29', registry)
    rows = {row['state_id']: row for row in report['states']}
    assert report['genuine_district_month_observations'] == 4
    assert report['states_with_genuine_observations'] == 2
    assert report['states_without_genuine_observations'] == ['LA']
    assert rows['TN']['genuine_district_month_observations'] == 3
    assert rows['TN']['observed_state_months'] == 2
    assert rows['TN']['coverage_qualified_state_months'] == 1
    assert rows['TN']['latest_observed_state_median_m_bgl'] == 8.
    assert rows['TN']['expected_policy_method'] == 'persistence_fallback'
    assert rows['AS']['genuine_district_month_observations'] == 1
    assert rows['AS']['coverage_qualified_state_months'] == 0
    assert rows['AS']['latest_genuine_observation_date'] == '2025-01-01'
    assert rows['AS']['latest_observation_age_months'] == 21
    assert rows['AS']['supervised_target_months'] is None  # Gate never attempted, not a fabricated zero.
    assert rows['LA']['expected_policy_method'] == 'no_observations'


def test_zero_depth_is_valid_only_when_genuine_and_duplicate_months_count_once(source):
    frame, card, registry = source
    genuine_zero = frame.loc[frame.district_id.eq('AS-A')].iloc[:1].copy()
    genuine_zero['gwl_current'] = 0.
    frame = pd.concat([frame.loc[~frame.district_id.eq('AS-A')], genuine_zero, genuine_zero], ignore_index=True)
    frame.attrs.update(feature_generation_id='fixture-only', data_sha256='fixture-hash')
    report = audit.audit_coverage(frame, card, '2026-10-29', registry)
    row = next(row for row in report['states'] if row['state_id'] == 'AS')
    assert row['genuine_district_month_observations'] == 1
    assert row['latest_observed_state_median_m_bgl'] == 0.
    assert row['expected_policy_method'] == 'persistence_fallback'


def test_exact_development_gate_explains_rejection_despite_long_history():
    dates = pd.date_range('2013-01-01', '2024-10-01', freq='3MS')
    registry = [dict(district_id='CH-A', state_id='CH')]
    frame = pd.DataFrame(dict(district_id='CH-A', date=dates, gwl_current=5., is_observed=True, is_imputed=False))
    card = dict(training_cutoff='2026-09-01', validation_start='2017-01-01', min_coverage=.5,
                states={'CH': dict(status='insufficient_data', reason='Chronological development evidence insufficient.')})
    report = audit.audit_coverage(frame, card, '2026-10-29', registry)
    row = report['states'][0]
    assert row['coverage_qualified_state_months'] >= 36
    assert row['qualified_span_months'] >= 60
    assert row['supervised_target_months'] >= 24
    assert row['pre_validation_fit_target_months'] < 24
    assert row['rejection_conditions'] == ['pre_validation_development_targets_below_24']


def test_trained_supported_state_is_reported_as_xgboost_without_loading_models():
    dates = pd.date_range('2010-01-01', '2026-01-01', freq='MS')
    registry = [dict(district_id='CH-A', state_id='CH')]
    frame = pd.DataFrame(dict(district_id='CH-A', date=dates, gwl_current=5., is_observed=True, is_imputed=False))
    card = dict(training_cutoff='2026-09-01', states={'CH': dict(status='trained', training_target_months=180)})
    report = audit.audit_coverage(frame, card, '2026-10-29', registry)
    assert report['old_status_counts'] == {'forecast': 1}
    assert report['states'][0]['expected_policy_method'] == 'state_median_xgboost'
    assert report['states'][0]['rejection_conditions'] == []


def generated_snapshot(report):
    output = {}
    origin = pd.Timestamp(report['as_of']).to_period('M').to_timestamp()
    for row in report['states']:
        has_data = row['observed_state_months'] > 0
        output[row['state_id']] = dict(state_id=row['state_id'], as_of=report['as_of'],
            feature_generation=report['source_generation'], source_data_sha256=report['source_data_sha256'],
            artifact_release='fixture-r2', release_manifest_sha256='a'*64,
            status='forecast' if has_data else 'insufficient_data', forecast_method=row['expected_policy_method'],
            historical_reference_date=row['latest_genuine_observation_date'], observation_age_months=row['latest_observation_age_months'],
            latest_observation_date=row['latest_genuine_observation_date'],
            genuine_observation_count=row['genuine_district_month_observations'], genuine_observed_months=row['observed_state_months'],
            unavailable_reason=None if has_data else 'no_genuine_observations',
            forecast=[dict(horizon=h, target_date=(origin+pd.DateOffset(months=h)).date().isoformat(),
                predicted_gwl=row['latest_observed_state_median_m_bgl'], units='m_bgl', is_forecast=True, is_observed=False)
                for h in range(1, 13)] if has_data else [],
            evaluation=dict(status='not_evaluated_for_fallback', n=0, mae_m=None, rmse_m=None))
    return output


def test_actual_generation_compares_all_states_methods_and_reference_dates(source):
    frame, card, registry = source
    before = audit.audit_coverage(frame, card, '2026-10-29', registry)
    generation = generated_snapshot(before)
    after = audit.audit_coverage(frame, card, '2026-10-29', registry, generation)
    assert after['after']['acceptance_met'] is True
    assert after['after']['method_counts'] == {'persistence_fallback': 2, 'no_observations': 1}
    assert after['after']['status_counts'] == {'forecast': 2, 'insufficient_data': 1}
    assert after['after']['publication_status'] == 'not_checked_no_publication_performed'
    assert all('final_horizon_rows' in row for row in after['states'])


def test_missing_fallback_false_metrics_and_mixed_provenance_are_detected(source):
    frame, card, registry = source
    report = audit.audit_coverage(frame, card, '2026-10-29', registry)
    generation = generated_snapshot(report)
    generation['AS'].update(status='insufficient_data', forecast=[])
    generation['TN']['evaluation']['mae_m'] = 1.
    generation['TN']['artifact_release'] = 'different-release'
    result = audit.compare_generation(report, generation)
    assert result['acceptance_met'] is False
    assert 'AS:data_bearing_state_missing_twelve_month_forecast' in result['violations']
    assert 'TN:fallback_must_not_inherit_xgboost_accuracy_metrics' in result['violations']
    assert 'mixed_or_missing_release_provenance' in result['violations']


def test_generation_source_mismatch_and_missing_states_fail_explicitly(source):
    frame, card, registry = source
    report = audit.audit_coverage(frame, card, '2026-10-29', registry)
    generation = generated_snapshot(report)
    generation['TN']['feature_generation'] = 'other'
    with pytest.raises(ValueError, match='identities'):
        audit.compare_generation(report, generation)
    with pytest.raises(ValueError, match='inventory'):
        audit.compare_generation(report, {})


def test_nonfinite_forecast_and_false_observation_counts_fail_audit(source):
    frame, card, registry = source
    report = audit.audit_coverage(frame, card, '2026-10-29', registry)
    generation = generated_snapshot(report)
    generation['AS']['forecast'][0]['predicted_gwl'] = float('nan')
    generation['TN']['genuine_observation_count'] = 99
    result = audit.compare_generation(report, generation)
    assert result['acceptance_met'] is False
    assert 'AS:invalid_monthly_forecast_value_or_calendar' in result['violations']
    assert 'TN:generated_observation_metadata_differs_from_source' in result['violations']


def test_audit_exports_all_rows_and_never_overwrites_evidence(tmp_path, source):
    frame, card, registry = source
    report = audit.audit_coverage(frame, card, '2026-10-29', registry)
    output = tmp_path/'coverage'
    audit.write_audit(output, report)
    assert json.loads((output/'coverage.json').read_text()) == report
    assert len(pd.read_csv(output/'coverage.csv')) == 3
    assert 'AS' in (output/'coverage.md').read_text()
    with pytest.raises(FileExistsError):
        audit.write_audit(output, report)
