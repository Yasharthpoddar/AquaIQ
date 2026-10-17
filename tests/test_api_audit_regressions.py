"""Input validation and complete alert visibility found in the October audit."""
from datetime import date
from unittest.mock import Mock

import pytest

from api.app import create_app
from api.routes import alerts, district, simulate


@pytest.fixture
def client():
    return create_app({'TESTING': True}).test_client()


@pytest.mark.parametrize('value', [True, False, '10', [], {}, 10**400])
@pytest.mark.parametrize('field', ['rainfall_change_pct', 'extraction_change_pct'])
def test_scenario_rejects_non_numeric_percentages_before_database(client, monkeypatch, field, value):
    resolver = Mock(side_effect=AssertionError('Invalid input must not query the database.'))
    monkeypatch.setattr(simulate, 'resolve_district_id', resolver)
    result = client.post('/api/simulate', json={'district_id': 'RJ-Jaipur', field: value})
    assert result.status_code == 400
    assert result.json['status'] == 'invalid_request'
    resolver.assert_not_called()


@pytest.mark.parametrize('value', [True, False, 2021, [], {}, '20260101', '2026-W01-1', '2026-02-30', '2999-01-01'])
def test_scenario_dates_cannot_be_interpreted_as_epoch_or_non_calendar_values(client, monkeypatch, value):
    resolver = Mock(side_effect=AssertionError('Invalid date must not query the database.'))
    monkeypatch.setattr(simulate, 'resolve_district_id', resolver)
    result = client.post('/api/simulate', json={'district_id': 'RJ-Jaipur', 'as_of': value})
    assert result.status_code == 400
    resolver.assert_not_called()


def test_scenario_explicit_cutoff_is_validated_and_passed_as_calendar_date(client, monkeypatch):
    monkeypatch.setattr(simulate, 'resolve_district_id', lambda value: value)
    selection = Mock(return_value={})
    monkeypatch.setattr(simulate, 'select_evidence', selection)
    monkeypatch.setattr(simulate, 'score_evidence', lambda evidence: {
        'crisis_score': None, 'tier': None, 'status': 'insufficient_data', 'estimate_type': 'insufficient_data',
    })
    assert client.post('/api/simulate', json={'district_id': 'RJ-Jaipur', 'as_of': '2021-01-31'}).status_code == 200
    selection.assert_called_once_with('RJ-Jaipur', date(2021, 1, 31))


@pytest.mark.parametrize('value', ['20260101', '2026-W01-1', '2026-02-30', '2999-01-01'])
def test_district_validates_cutoff_before_database_access(client, monkeypatch, value):
    resolver = Mock(side_effect=AssertionError('Invalid date must not query the database.'))
    monkeypatch.setattr(district, 'resolve_district_id', resolver)
    assert client.get('/api/district/RJ-Jaipur', query_string={'as_of': value}).status_code == 400
    resolver.assert_not_called()


def test_alert_limit_discloses_omitted_districts_and_allows_full_master(client, monkeypatch):
    connection = Mock()
    monkeypatch.setattr(alerts, 'get_connection', lambda: connection)
    monkeypatch.setattr(alerts, 'latest_scores', lambda conn: None)
    records = [{'district_id': f'D-{index}', 'score': index % 100, 'tier': 'Watch'} for index in range(724)]
    records.append({'district_id': 'D-unavailable', 'score': None, 'tier': None})
    monkeypatch.setattr(alerts, 'score_records', lambda frame: [dict(row) for row in records])

    limited = client.get('/api/alerts').json
    assert (limited['count'], limited['total'], limited['has_more']) == (100, 725, True)
    complete = client.get('/api/alerts?limit=1000').json
    assert (complete['count'], complete['total'], complete['has_more']) == (725, 725, False)
    assert complete['alerts'][-1]['district_id'] == 'D-unavailable'
    assert complete['alerts'][-1]['crisis_score'] is None
    filtered = client.get('/api/alerts?tier=watch&limit=1000').json
    assert (filtered['count'], filtered['total'], filtered['has_more']) == (724, 724, False)
    assert connection.close.call_count == 3
