"""Candidate validation and PostgreSQL isolation; fixtures are synthetic test data."""
from copy import deepcopy
from uuid import uuid4

import pandas as pd
from psycopg2 import sql
import pytest

from db.connection import get_connection
from models import state_median_storage as storage
from models.state_mapping import STATES_REGISTRY


def snapshots(as_of='2025-01-31'):
    return {code: {
        'product': storage.PRODUCT_NAME, 'model_name': storage.MODEL_NAME,
        'model_version': storage.MODEL_VERSION, 'state_id': code,
        'state_name': meta['name'], 'as_of': as_of,
        'units': 'm_bgl', 'horizon_months': 12,
        'status': 'insufficient_data', 'evaluation_status': 'experimental',
        'promotion_status': 'experimental', 'forecast_origin': as_of[:7]+'-01',
        'computed_at': '2026-10-29T01:00:00+00:00',
        'contributing_districts_count':0, 'total_districts_in_state':10, 'district_coverage_pct':0.,
        'evaluation': {'status':'not_evaluated','n':0,'mae_m':None,'rmse_m':None,
                       'period_start':None,'period_end':None},
        'message': 'Synthetic fixture has insufficient history.',
        'training_cutoff': None, 'model_sha256': None,
        'feature_generation': 'synthetic-fixture', 'source_sha256': 'a'*64,
        'config': {'minimum_coverage': .5}, 'history': [], 'forecast': [],
    } for code, meta in STATES_REGISTRY.items()}


def add_forecast(values, code='TN'):
    payload = values[code]
    origin = pd.Timestamp(payload['as_of']).to_period('M').to_timestamp()
    payload.update(status='forecast', training_cutoff='2024-12-01', model_sha256='b'*64,
                   history=[{'date': '2024-12-01', 'gwl_m_bgl': 3., 'coverage_ratio': .6,
                             'contributing_districts_count': 6, 'total_districts_in_state': 10,
                             'district_coverage_pct':60., 'observation_count':6, 'training_eligible':True}],
                   forecast=[{'horizon': h, 'target_date': (origin+pd.DateOffset(months=h)).date().isoformat(),
                              'predicted_gwl': 3.+h/10, 'is_forecast': True, 'is_observed': False}
                             for h in range(1,13)])
    return values


def test_complete_snapshot_validation_and_model_identity():
    values = add_forecast(snapshots())
    assert storage.validate_generation(values) == {'states_total': 36, 'as_of': '2025-01-31'}
    values['TN']['model_version'] = 'district-version'
    with pytest.raises(ValueError, match='metadata'):
        storage.validate_generation(values)


@pytest.mark.parametrize('mutation', [
    lambda rows: rows.pop('TN'),
    lambda rows: rows['TN'].update(as_of='2025-02-28'),
    lambda rows: rows['TN']['forecast'].pop(),
    lambda rows: rows['TN']['forecast'][0].update(predicted_gwl=-1),
    lambda rows: rows['TN']['forecast'][0].update(predicted_gwl=float('nan')),
    lambda rows: rows['TN']['forecast'][0].update(target_date='2025-03-01'),
    lambda rows: rows['TN']['forecast'][0].update(is_observed=True),
    lambda rows: rows['TN'].update(training_cutoff='2025-02-01'),
    lambda rows: rows['TN'].update(model_sha256=None),
    lambda rows: rows['TN']['history'].append(deepcopy(rows['TN']['history'][0])),
    lambda rows: rows['TN']['history'][0].update(coverage_ratio=1.1),
    lambda rows: rows['TN']['history'][0].update(contributing_districts_count=11),
    lambda rows: rows['TN']['history'][0].update(date='2025-02-01'),
    lambda rows: rows['TN']['history'][0].update(training_eligible=False),
    lambda rows: rows['TN']['history'][0].update(district_coverage_pct=20.),
    lambda rows: rows['TN'].update(promotion_status='validated'),
    lambda rows: rows['TN'].update(computed_at='2025-01-31T10:00:00'),
    lambda rows: rows['TN'].update(evaluation={'status':'evaluated','n':0,'mae_m':1.}),
])
def test_malformed_or_incomplete_candidate_is_rejected(mutation):
    values = add_forecast(snapshots())
    mutation(values)
    with pytest.raises(ValueError):
        storage.validate_generation(values)


def test_explicit_missing_historical_months_remain_null():
    values = snapshots()
    values['TN']['history'] = [{'date':'2024-12-01', 'gwl_m_bgl':None,
                               'coverage_ratio':0., 'contributing_districts_count':0, 'total_districts_in_state':10,
                               'district_coverage_pct':0., 'observation_count':0, 'training_eligible':False}]
    storage.validate_generation(values)
    assert values['TN']['history'][0]['gwl_m_bgl'] is None


def test_incomplete_current_month_is_rejected_even_when_month_stamp_is_past():
    values = snapshots('2025-01-15')
    values['TN']['history'] = [{'date':'2025-01-01', 'gwl_m_bgl':None,
                               'coverage_ratio':0., 'contributing_districts_count':0, 'total_districts_in_state':10,
                               'district_coverage_pct':0., 'observation_count':0, 'training_eligible':False}]
    with pytest.raises(ValueError, match='completed'):
        storage.validate_generation(values)


def test_invalid_private_namespace_rejected_before_database_access(monkeypatch):
    monkeypatch.setattr(storage, 'get_connection', lambda: pytest.fail('must not connect'))
    with pytest.raises(ValueError, match='schema'):
        storage.save_generation(snapshots(), test_schema='public')


@pytest.fixture
def private_storage(monkeypatch):
    connection = get_connection()
    schema = 'aquaiq_test_state_median_' + uuid4().hex[:12]
    monkeypatch.setenv('AQUAIQ_FORECAST_SCHEMA', schema)
    with connection.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM public.forecast_generations')
        production_count = cursor.fetchone()[0]
    yield schema, connection
    with connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM public.forecast_generations')
            assert cursor.fetchone()[0] == production_count
            cursor.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
    connection.close()


@pytest.mark.requires_db
def test_private_postgres_roundtrip_immutability_and_independent_vintages(private_storage):
    schema, connection = private_storage
    original = add_forecast(snapshots())
    result = storage.save_generation(original, test_schema=schema)
    assert result['states_total'] == 36 and result['reused'] is False
    assert storage.save_generation(original, test_schema=schema)['reused'] is True
    stored = storage.get_state_forecast('Tamil Nadu')
    assert stored['generation_id'] == result['generation_id']
    assert stored['history'] == original['TN']['history']
    assert stored['forecast'] == original['TN']['forecast']
    assert stored['persistence_status'] == 'experimental'
    assert storage.get_state_forecast('TN', '2024-12-31') is None
    newer = snapshots('2025-02-28')
    second = storage.save_generation(newer, test_schema=schema)
    assert second['generation_id'] != result['generation_id']
    assert storage.get_state_forecast('TN')['as_of'] == '2025-02-28'
    assert storage.get_state_forecast('TN', '2025-01-31')['forecast'] == original['TN']['forecast']
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL('SELECT count(*) FROM {}.state_median_forecast_records').format(sql.Identifier(schema)))
        assert cursor.fetchone()[0] == 72


@pytest.mark.requires_db
def test_absent_candidate_tables_return_none_without_touching_production(private_storage):
    schema, connection = private_storage
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    assert storage.get_state_forecast('TN') is None
