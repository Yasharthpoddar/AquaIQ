"""Versioned API contract and independent generation selection."""
from copy import deepcopy
from datetime import date
from uuid import uuid4

import pytest

from api.app import create_app
from api.routes import state_median as routes
from models import state_median_release_storage as releases
from tests.test_state_median_release_storage import release_fixture


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr('models.forecast_storage.latest_published_as_of',lambda *a:pytest.fail('v2 must not read legacy vintage'))
    return create_app({'TESTING':True}).test_client()


def test_versioned_registry_remains_complete_before_publication(client,monkeypatch):
    monkeypatch.setattr(releases,'get_published_summary',lambda *a:None)
    result = client.get('/api/v2/states')
    assert result.status_code == 200
    assert result.json['total'] == 36 and len(result.json['states']) == 36
    assert result.json['as_of'] is None and result.json['generation_id'] is None
    assert all(row['districts'] and row['total_districts'] for row in result.json['states'])


def test_versioned_default_detail_is_median_and_pins_exact_generation(client,monkeypatch):
    payloads,_ = release_fixture()
    release_id = str(uuid4())
    payload = dict(payloads['TN'],generation_id=release_id,artifact_release='test-release')
    calls = []
    def read(code,as_of,generation):
        calls.append((code,as_of,generation))
        return deepcopy(payload)
    monkeypatch.setattr(releases,'get_published_state_forecast',read)
    result = client.get(f'/api/v2/predict/state/TN?generation_id={release_id}&as_of=2025-01-31')
    assert result.status_code == 200
    assert result.json['model_name'] == 'state_median_xgboost'
    assert calls == [('TN',date(2025,1,31),release_id)]
    assert 'resolved_state_id' not in payload


def test_missing_publication_and_corrupt_identity_produce_explicit_503(client,monkeypatch):
    def corrupt(*a):
        raise ValueError('Stored artifact mismatch')
    monkeypatch.setattr(releases,'get_published_state_forecast',corrupt)
    result = client.get('/api/v2/predict/state/TN')
    assert result.status_code == 503 and result.json['status'] == 'model_unavailable'
    assert result.json['forecast'] == []
    assert result.json['unavailable_reason'] == 'median_release_storage_unavailable'
    monkeypatch.setattr(releases,'get_published_summary_statistics',lambda *a:None)
    assert client.get('/api/v2/states/summary').status_code == 503


@pytest.mark.parametrize('query', [
    'as_of=today','as_of=2025-02-30','as_of=2999-01-01','generation_id=invalid',
    'horizon=6','horizon=NaN','model=current','unknown=1','horizon=12&horizon=6',
])
def test_invalid_requests_fail_without_storage_access(client,monkeypatch,query):
    monkeypatch.setattr(releases,'get_published_summary',lambda *a:pytest.fail('invalid request'))
    monkeypatch.setattr(releases,'get_published_summary_statistics',lambda *a:pytest.fail('invalid request'))
    monkeypatch.setattr(releases,'get_published_state_forecast',lambda *a:pytest.fail('invalid request'))
    assert client.get('/api/v2/states/summary?'+query).status_code == 400
    assert client.get('/api/v2/predict/state/TN?'+query).status_code == 400


def test_unknown_state_and_insufficient_data_follow_existing_status_conventions(client,monkeypatch):
    assert client.get('/api/v2/predict/state/Atlantis').status_code == 404
    payloads,_ = release_fixture()
    monkeypatch.setattr(releases,'get_published_state_forecast',lambda *a:deepcopy(payloads['AN']))
    result = client.get('/api/v2/predict/state/AN')
    assert result.status_code == 200 and result.json['status'] == 'insufficient_data'
    assert result.json['forecast'] == []
