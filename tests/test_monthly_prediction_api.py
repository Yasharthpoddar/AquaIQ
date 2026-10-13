"""New prediction windows dispatch honestly without changing the legacy endpoint."""
from datetime import date
from unittest.mock import Mock

import pytest

from api import contracts
from api.app import create_app
from api.routes import predict


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 13)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(contracts, 'date', FixedDate)
    return create_app({'TESTING': True}).test_client()


@pytest.mark.parametrize('query', ['', '?window=observed_endpoint'])
def test_existing_endpoint_stays_default(client, monkeypatch, query):
    resolve = Mock(return_value='GJ-Gandhinagar')
    historical = Mock(return_value={
        'status': 'historical_forecast',
        'district_id': 'GJ-Gandhinagar',
        'forecast': [{'month': '2023-09', 'predicted_gwl': 8.2}],
        'projection_method': 'direct_xgboost_6_month_endpoint',
    })
    future = Mock(side_effect=AssertionError('The default must retain the historical endpoint.'))
    monkeypatch.setattr(predict, 'resolve_district_id', resolve)
    monkeypatch.setattr(predict, 'forecast_result', historical)
    monkeypatch.setattr(predict, 'forecast_next_six_months', future)

    result = client.get('/api/predict/legacy-gandhinagar' + query)

    assert result.status_code == 200
    assert result.json['forecast'] == [{'month': '2023-09', 'predicted_gwl': 8.2}]
    assert result.json['requested_id'] == 'legacy-gandhinagar'
    assert result.json['resolved_id'] == 'GJ-Gandhinagar'
    historical.assert_called_once_with('GJ-Gandhinagar', FixedDate.today())
    future.assert_not_called()


@pytest.mark.parametrize('as_of', ['', '&as_of=today', '&as_of=2026-10-13'])
def test_today_window_uses_monthly_projection_and_preserves_provenance(client, monkeypatch, as_of):
    monkeypatch.setattr(predict, 'resolve_district_id', lambda value: 'GJ-Gandhinagar')
    historical = Mock(side_effect=AssertionError('A future window must use the monthly projection.'))
    future = Mock(return_value={
        'district_id': 'GJ-Gandhinagar',
        'status': 'projection',
        'projection_method': 'damped_seasonal_trend',
        'last_observed_date': '2023-03-01',
        'forecast_origin': '2026-10-13',
        'data_age_months': 43,
        'estimated_current_gwl': 8.1,
        'validation': {'status': 'unvalidated_current_projection', 'sufficient_for_operational_use': False},
        'forecast': [
            {'month': month, 'predicted_gwl': float(index + 8)}
            for index, month in enumerate(('2026-11', '2026-12', '2027-01', '2027-02', '2027-03', '2027-04'))
        ],
        'limitations': ['Current groundwater depth is estimated from historical observations.'],
    })
    monkeypatch.setattr(predict, 'forecast_result', historical)
    monkeypatch.setattr(predict, 'forecast_next_six_months', future)

    result = client.get('/api/predict/legacy-id?window=next_six_months&months=6' + as_of)

    assert result.status_code == 200
    assert result.json['status'] == 'projection'
    assert [item['month'] for item in result.json['forecast']] == [
        '2026-11', '2026-12', '2027-01', '2027-02', '2027-03', '2027-04',
    ]
    assert result.json['last_observed_date'] == '2023-03-01'
    assert result.json['estimated_current_gwl'] == 8.1
    assert result.json['validation']['sufficient_for_operational_use'] is False
    assert result.json['limitations']
    assert result.json['requested_id'] == 'legacy-id'
    assert result.json['resolved_id'] == 'GJ-Gandhinagar'
    future.assert_called_once_with('GJ-Gandhinagar', FixedDate.today())
    historical.assert_not_called()


def test_retrospective_window_passes_requested_cutoff(client, monkeypatch):
    monkeypatch.setattr(predict, 'resolve_district_id', lambda value: value)
    future = Mock(return_value={'status': 'projection', 'forecast': []})
    monkeypatch.setattr(predict, 'forecast_next_six_months', future)

    assert client.get('/api/predict/RJ-Jaipur?window=next_six_months&as_of=2021-01-15').status_code == 200
    future.assert_called_once_with('RJ-Jaipur', date(2021, 1, 15))


@pytest.mark.parametrize('query', [
    'window=unknown',
    'window=',
    'window=next_six_months&months=12',
    'window=next_six_months&months=abc',
    'window=next_six_months&months=0',
    'window=next_six_months&as_of=2026-10-14',
    'window=next_six_months&as_of=2026-02-30',
    'window=next_six_months&as_of=invalid',
    'window=next_six_months&target_year=2027',
    'window=next_six_months&year=2027',
    'window=next_six_months&start=2026-11',
    'window=next_six_months&start_month=2026-11',
])
def test_invalid_future_requests_rejected_before_data_access(client, monkeypatch, query):
    resolve = Mock(side_effect=AssertionError('Invalid inputs must not access district data.'))
    monkeypatch.setattr(predict, 'resolve_district_id', resolve)

    result = client.get('/api/predict/RJ-Jaipur?' + query)

    assert result.status_code == 400
    assert result.json['status'] == 'invalid_request'
    resolve.assert_not_called()


@pytest.mark.parametrize('window', ['observed_endpoint', 'next_six_months'])
def test_unknown_identity_remains_404_for_both_windows(client, monkeypatch, window):
    monkeypatch.setattr(predict, 'resolve_district_id', Mock(side_effect=LookupError('Unknown ID')))
    future = Mock()
    monkeypatch.setattr(predict, 'forecast_next_six_months', future)

    result = client.get('/api/predict/unknown?window=' + window)

    assert result.status_code == 404
    assert result.json['status'] == 'not_found'
    future.assert_not_called()


def test_projection_failure_stays_503(client, monkeypatch):
    monkeypatch.setattr(predict, 'resolve_district_id', lambda value: value)
    monkeypatch.setattr(predict, 'forecast_next_six_months', Mock(side_effect=RuntimeError('Database failure')))

    result = client.get('/api/predict/RJ-Jaipur?window=next_six_months')

    assert result.status_code == 503
    assert result.json['status'] == 'unavailable'
    assert 'forecast' not in result.json


def test_projection_missing_evidence_remains_explicit(client, monkeypatch):
    monkeypatch.setattr(predict, 'resolve_district_id', lambda value: value)
    monkeypatch.setattr(predict, 'forecast_next_six_months', lambda *args: {
        'status': 'insufficient_data', 'forecast': [], 'estimated_current_gwl': None,
        'last_observed_date': None, 'message': 'No usable observations for this district or zone.',
    })

    result = client.get('/api/predict/PY-Mahe?window=next_six_months')

    assert result.status_code == 200
    assert result.json['status'] == 'insufficient_data'
    assert result.json['estimated_current_gwl'] is None
    assert result.json['forecast'] == []
