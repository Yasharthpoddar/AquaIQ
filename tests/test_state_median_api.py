"""Additive state candidate API contracts; production and district paths stay separate."""
from datetime import date
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from api.app import create_app
from api.routes import state as routes
from models import state_median_storage as storage


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(routes.forecast_storage, 'latest_published_as_of', lambda *a: pytest.fail('candidate must select its own vintage'))
    monkeypatch.setattr(routes, 'forecast_state_twelve_months', lambda *a, **k: pytest.fail('candidate must not launch inference'))
    return create_app({'TESTING':True}).test_client()


def test_candidate_selects_own_latest_vintage_and_preserves_identity(client, monkeypatch):
    calls = []
    payload = {'state_id':'TN', 'status':'insufficient_data', 'history':[], 'forecast':[], 'as_of':'2025-01-31'}
    def read(code, cutoff):
        calls.append((code,cutoff))
        return payload
    monkeypatch.setattr(storage, 'get_state_forecast', read)
    result = client.get('/api/predict/state/Tamil%20Nadu?model=median_xgboost')
    assert result.status_code == 200
    assert calls == [('TN', None)]
    assert result.json['requested_state_id'] == 'Tamil Nadu'
    assert result.json['resolved_state_id'] == 'TN'
    assert 'requested_state_id' not in payload


def test_explicit_candidate_vintage_is_exact(client, monkeypatch):
    calls = []
    monkeypatch.setattr(storage, 'get_state_forecast', lambda code, cutoff: calls.append((code,cutoff)))
    result = client.get('/api/predict/state/TN?model=median_xgboost&as_of=2025-01-31')
    assert result.status_code == 503
    assert result.json['status'] == 'model_unavailable'
    assert result.json['model_version'] == storage.MODEL_VERSION
    assert result.json['as_of'] == '2025-01-31'
    assert calls == [('TN', date(2025,1,31))]


@pytest.mark.parametrize('query', [
    'model=unknown', 'model=median_xgboost&horizon=6', 'model=median_xgboost&horizon=nan',
    'model=median_xgboost&as_of=2025-02-30', 'model=median_xgboost&as_of=today',
    'model=median_xgboost&as_of=2999-01-01', 'model=median_xgboost&as_of=2025-1-1',
])
def test_invalid_mode_horizon_or_candidate_date_rejected_without_database(client, monkeypatch, query):
    monkeypatch.setattr(storage, 'get_state_forecast', lambda *a, **k: pytest.fail('invalid request must not read database'))
    result = client.get('/api/predict/state/TN?' + query)
    assert result.status_code == 400


def test_missing_candidate_and_database_failure_are_explicit_without_fake_graph(client, monkeypatch):
    def unavailable(*args):
        raise RuntimeError('test database unavailable')
    monkeypatch.setattr(storage, 'get_state_forecast', unavailable)
    result = client.get('/api/predict/state/TN?model=median_xgboost')
    assert result.status_code == 503
    assert result.json['status'] == 'model_unavailable'
    assert result.json['forecast'] == [] and result.json['history'] == []
    assert result.json['unavailable_reason'] == 'candidate_storage_unavailable'
    assert result.json['promotion_status'] == 'experimental'
    assert result.json['training_cutoff'] is None
    assert result.json['contributing_districts_count'] == 0
    assert result.json['total_districts_in_state'] > 0
    assert result.json['district_coverage_pct'] == 0.
    assert result.json['evaluation']['n'] == 0
    assert result.json['evaluation']['mae_m'] is None


def test_real_missing_candidate_envelope_passes_dashboard_javascript_contract(client, monkeypatch):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node runtime required to execute dashboard contract.')
    monkeypatch.setattr(storage, 'get_state_forecast', lambda *a: None)
    result = client.get('/api/predict/state/TN?model=median_xgboost')
    contract = Path(__file__).resolve().parents[1]/'dashboard/src/components/stateMedianForecastContract.js'
    script = (f"import {{ validateStateMedianForecast }} from {json.dumps(contract.as_uri())};"
              "let body=''; for await (const chunk of process.stdin) body+=chunk;"
              "validateStateMedianForecast(JSON.parse(body),'TN');")
    completed = subprocess.run([node, '--input-type=module', '-e', script],
                               input=json.dumps(result.json), text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr


def test_default_state_api_uses_existing_production_storage(client, monkeypatch):
    monkeypatch.setattr(storage, 'get_state_forecast', lambda *a: pytest.fail('production must not read candidate'))
    payload = {'state_id':'TN', 'status':'forecast', 'model_name':'district_tiered_equal_weight', 'forecast':[{'predicted_gwl':8.}]}
    monkeypatch.setattr(routes.forecast_storage, 'get_state_forecast', lambda code, cutoff: deepcopy(payload))
    result = client.get('/api/predict/state/TN?as_of=2025-01-31')
    assert result.status_code == 200
    assert result.json['model_name'] == payload['model_name']
    assert result.json['forecast'] == payload['forecast']


def test_unknown_state_remains_not_found(client):
    assert client.get('/api/predict/state/Atlantis?model=median_xgboost').status_code == 404
