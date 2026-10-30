"""Tiered coverage contracts; all forecast data in these tests are synthetic."""
from copy import deepcopy

import pytest
import pandas as pd

from api.app import create_app
from models import state_median_release_storage as releases
from models.state_median_storage import (validate_generation,TIERED_MODEL_NAME,TIERED_MODEL_VERSION,POLICY_VERSION)
from tests.test_state_median_release_storage import release_fixture,private_release_store


def tiered_fixture():
    payloads,manifest = release_fixture('synthetic-tiered-r2')
    for code,payload in payloads.items():
        payload.update(model_name=TIERED_MODEL_NAME,model_version=TIERED_MODEL_VERSION,
            policy_version=POLICY_VERSION,policy_sha256='e'*64,model_card_sha256='f'*64,
            forecast_method='no_observations',training_cutoff=None,model_sha256=None,features=[],
            genuine_observed_months=0,genuine_observation_count=0,reference_observation=None,
            reference_training_eligible=None,reference_age_months=None,latest_observation_date=None,
            observation_age_months=None,reference_is_stale=None,normal_reporting_interval_months=3,
            last_observed_gwl_m_bgl=None,historical_reference_date=None,fallback_reason=None)
    trained = payloads['TN']
    trained.update(forecast_method='state_median_xgboost',training_cutoff=manifest['training_cutoff'],
        model_sha256=manifest['models']['TN'],features=manifest['features'],genuine_observed_months=1,
        genuine_observation_count=6,last_observed_gwl_m_bgl=3.,historical_reference_date='2024-12-01',
        reference_training_eligible=True,reference_age_months=1,latest_observation_date='2024-12-01',
        observation_age_months=1,reference_is_stale=False)
    trained['history'][0].update(observation_quality='coverage_qualified',is_observed=True,is_forecast=False)
    trained['reference_observation'] = deepcopy(trained['history'][0])
    limited = payloads['AN']
    reference = dict(date='2024-12-01',gwl_m_bgl=7.,contributing_districts_count=1,
        total_districts_in_state=10,district_coverage_pct=10.,coverage_ratio=.1,observation_count=1,
        training_eligible=False,observation_quality='low_coverage',is_observed=True,is_forecast=False)
    limited.update(status='forecast',forecast_method='persistence_fallback',features=['latest_genuine_state_median'],
        history=[reference],reference_observation=deepcopy(reference),reference_training_eligible=False,
        reference_age_months=1,latest_observation_date='2024-12-01',observation_age_months=1,
        reference_is_stale=False,genuine_observed_months=1,genuine_observation_count=1,
        last_observed_gwl_m_bgl=7.,historical_reference_date='2024-12-01',
        contributing_districts_count=1,district_coverage_pct=10.,fallback_reason='Only one genuine observation.',
        forecast=[dict(row,predicted_gwl=7.) for row in trained['forecast']])
    limited['evaluation']['status'] = 'not_evaluated_for_fallback'
    manifest.update(format_version=2,model_name=TIERED_MODEL_NAME,model_version=TIERED_MODEL_VERSION,
        model_card_sha256='f'*64,xgboost_model_card_sha256='d'*64,policy_version=POLICY_VERSION,
        policy_sha256='e'*64,policy_details={'limited_history_method':'persistence_fallback'},
        state_methods={code:payload['forecast_method'] for code,payload in payloads.items()})
    return payloads,manifest


def test_one_low_coverage_observation_is_a_valid_persistence_forecast():
    payloads,manifest = tiered_fixture()
    validate_generation(payloads)
    releases.validate_release(payloads,manifest)
    assert payloads['AN']['forecast_method'] == 'persistence_fallback'
    assert len(payloads['AN']['forecast']) == 12
    assert payloads['AN']['training_cutoff'] is None and payloads['AN']['model_sha256'] is None
    assert not payloads['AN']['reference_training_eligible']


@pytest.mark.parametrize('mutation', [
    lambda p,m:p['AN'].update(model_sha256='a'*64),
    lambda p,m:p['AN'].update(training_cutoff='2024-12-01'),
    lambda p,m:p['AN'].update(genuine_observed_months=0),
    lambda p,m:p['AN']['forecast'][0].update(predicted_gwl=7.1),
    lambda p,m:p['AN'].update(fallback_reason=''),
    lambda p,m:p['AN'].update(latest_observation_date='2024-11-01'),
    lambda p,m:p['AN'].update(observation_age_months=2),
    lambda p,m:p['AN'].update(reference_training_eligible=True),
    lambda p,m:p['AN']['reference_observation'].update(is_observed=False),
    lambda p,m:p['AN'].update(status='insufficient_data',forecast=[]),
    lambda p,m:p['AP'].update(genuine_observed_months=1,genuine_observation_count=1),
    lambda p,m:m['state_methods'].update(AN='state_median_xgboost'),
    lambda p,m:p['TN'].update(model_sha256=None),
    lambda p,m:p['TN'].update(reference_training_eligible=False),
    lambda p,m:p['AN'].update(policy_sha256='0'*64),
])
def test_policy_metadata_and_fallback_values_cannot_bypass_integrity(mutation):
    payloads,manifest = tiered_fixture()
    mutation(payloads,manifest)
    with pytest.raises(ValueError):
        releases.validate_release(payloads,manifest)


def test_fallback_cannot_borrow_xgboost_backtest_metrics():
    payloads,manifest = tiered_fixture()
    payloads['AN']['evaluation'].update(n=1,mae_m=1.,rmse_m=1.,period_start='2024-01-01',period_end='2024-01-01')
    with pytest.raises(ValueError,match='metrics'):
        releases.validate_release(payloads,manifest)


def test_month_end_fallback_can_use_completed_origin_month_without_changing_xgboost():
    payloads,manifest = tiered_fixture()
    limited = payloads['AN']
    limited['history'][0]['date'] = '2025-01-01'
    limited['reference_observation']['date'] = '2025-01-01'
    limited.update(historical_reference_date='2025-01-01',latest_observation_date='2025-01-01',
                   reference_age_months=0,observation_age_months=0)
    releases.validate_release(payloads,manifest)
    trained = payloads['TN']
    trained['history'][0]['date'] = '2025-01-01'
    trained['reference_observation']['date'] = '2025-01-01'
    trained.update(historical_reference_date='2025-01-01',latest_observation_date='2025-01-01',
                   reference_age_months=0,observation_age_months=0)
    with pytest.raises(ValueError,match='XGBoost reference'):
        releases.validate_release(payloads,manifest)


def test_stale_one_observation_reference_keeps_real_date_and_age_even_outside_history_window():
    payloads,manifest = tiered_fixture()
    limited = payloads['AN']
    reference = dict(limited['reference_observation'],date='2002-01-01')
    missing = [dict(reference,date=stamp.date().isoformat(),gwl_m_bgl=None,contributing_districts_count=0,
        district_coverage_pct=0.,coverage_ratio=0.,observation_count=0,observation_quality='missing',is_observed=False)
        for stamp in pd.date_range('2002-02-01','2024-12-01',freq='MS')]
    limited.update(history=[reference]+missing,reference_observation=deepcopy(reference),
        historical_reference_date='2002-01-01',latest_observation_date='2002-01-01',
        reference_age_months=276,observation_age_months=276,reference_is_stale=True)
    releases.validate_release(payloads,manifest)
    assert all(row['predicted_gwl']==7. for row in limited['forecast'])
    assert limited['latest_observation_date'] == '2002-01-01'


def test_few_observations_preserve_latest_real_median_and_genuine_inventory():
    payloads,manifest = tiered_fixture()
    limited = payloads['AN']
    older = dict(limited['history'][0],date='2024-11-01',gwl_m_bgl=9.)
    limited.update(history=[older]+limited['history'],genuine_observed_months=2,genuine_observation_count=2)
    releases.validate_release(payloads,manifest)
    assert all(row['predicted_gwl']==7. for row in limited['forecast'])


def test_tiered_summary_separates_method_counts_and_identity():
    payloads,manifest = tiered_fixture()
    summary = releases._summary(payloads,manifest,'synthetic-release-uuid')
    assert summary['model_name'] == TIERED_MODEL_NAME
    assert summary['counts_by_forecast_method'] == {'state_median_xgboost':1,'persistence_fallback':1,'no_observations':34}
    row = next(row for row in summary['states'] if row['state_id']=='AN')
    assert row['status'] == 'available' and row['forecast_method'] == 'persistence_fallback'
    assert row['forecast_12m_gwl_m_bgl'] == 7. and row['projected_change_12m_m'] == 0.


@pytest.mark.requires_db
def test_tiered_snapshot_stages_all36_without_publication_or_active_pointer(private_release_store):
    schema,connection = private_release_store
    payloads,manifest = tiered_fixture()
    staged = releases.stage_release(payloads,manifest,test_schema=schema)
    with connection.cursor() as cursor:
        from psycopg2 import sql
        cursor.execute(sql.SQL('SET search_path TO {},pg_temp').format(sql.Identifier(schema)))
        stored,stored_manifest,summary = releases._verified_release(cursor,staged['release_id'])
        cursor.execute('SELECT count(*) FROM state_median_publications')
        assert cursor.fetchone()[0] == 0
        cursor.execute('SELECT model_version FROM state_median_generations')
        assert cursor.fetchone()[0] == TIERED_MODEL_VERSION
    assert stored == payloads and stored_manifest == manifest
    assert summary['available_states_count'] == 2
    assert releases.get_active_release() is None
    assert releases.get_published_state_forecast('AN',generation_id=staged['release_id']) is None


def test_v2_serves_explicit_fallback_identity_without_changing_legacy_routes(monkeypatch):
    payloads,manifest = tiered_fixture()
    payload = dict(payloads['AN'],generation_id='synthetic-release-uuid')
    monkeypatch.setattr(releases,'get_published_state_forecast',lambda *args:deepcopy(payload))
    client = create_app({'TESTING':True}).test_client()
    result = client.get('/api/v2/predict/state/AN')
    assert result.status_code == 200
    assert result.json['model_name'] == TIERED_MODEL_NAME and result.json['forecast_method'] == 'persistence_fallback'
    assert result.json['training_cutoff'] is None and result.json['model_sha256'] is None
    assert client.get('/api/v2/predict/state/AN?model=median_xgboost').status_code == 400
    assert client.get('/api/v2/predict/state/AN?model=median_tiered').status_code == 200


def test_missing_release_never_falls_back_or_claims_no_observations(monkeypatch):
    monkeypatch.setattr(releases,'get_published_state_forecast',lambda *args:None)
    result = create_app({'TESTING':True}).test_client().get('/api/v2/predict/state/AN')
    assert result.status_code == 503 and result.json['forecast'] == []
    assert result.json['forecast_method'] is None and result.json['genuine_observation_count'] is None
