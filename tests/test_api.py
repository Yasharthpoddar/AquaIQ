"""Deterministic API contracts, including the failures found in the audit."""
import json
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
from api.app import create_app
from api.routes import predict,history,simulate,district,health

@pytest.fixture
def client():
    return create_app({'TESTING':True}).test_client()

def test_unvalidated_horizons_rejected(client):
    for query in ('?months=12','?months=abc','?target_year=2027','?as_of=oops'):
        assert client.get('/api/predict/RJ-Jaipur'+query).status_code==400

def test_missing_forecast_preserves_null(client,monkeypatch):
    monkeypatch.setattr(predict,'resolve_district_id',lambda value:value)
    monkeypatch.setattr(predict,'forecast_result',lambda *args:{'status':'insufficient_data','forecast':[],'crisis_score':None,'tier':None})
    data=client.get('/api/predict/PY-Mahe').json
    assert data['crisis_score'] is None and data['tier'] is None and not data['forecast']

def test_database_failure_does_not_become_score(client,monkeypatch):
    monkeypatch.setattr(simulate,'resolve_district_id',Mock(side_effect=RuntimeError('DB failed')))
    result=client.post('/api/simulate',json={'district_id':'RJ-Jaipur'})
    assert result.status_code==503 and 'baseline_score' not in result.json

@pytest.mark.parametrize('value',[None,False,0,34])
def test_simulation_zero_change_exact_parity(client,monkeypatch,value):
    if value is False:
        value=None
    monkeypatch.setattr(simulate,'resolve_district_id',lambda value:value)
    monkeypatch.setattr(simulate,'select_evidence',lambda *args:{})
    monkeypatch.setattr(simulate,'score_evidence',lambda *args:{'crisis_score':value,'tier':'Watch' if value is not None else None,
        'status':'success' if value is not None else 'insufficient_data','estimate_type':'district_level'})
    result=client.post('/api/simulate',json={'district_id':'RJ-Jaipur'}).json
    assert result['baseline_score']==result['simulated_score']==value
    assert result['delta']==(0 if value is not None else None)

@pytest.mark.parametrize('value',['NaN','Infinity',-101,101,None,'bad'])
def test_simulation_invalid_numbers(client,value):
    assert client.post('/api/simulate',json={'district_id':'RJ-Jaipur','rainfall_change_pct':value}).status_code==400

def test_history_strict_json_and_provenance(client,monkeypatch):
    monkeypatch.setattr(history,'resolve_district_id',lambda value:value)
    connection=Mock()
    monkeypatch.setattr(history,'get_connection',lambda:connection)
    monkeypatch.setattr(history,'feature_generation',lambda:'generation')
    monkeypatch.setattr(history,'read_frame',lambda *args:pd.DataFrame({'month':['2024-01'],'gwl':[np.nan],
        'rainfall':[float('inf')],'is_observed':[False],'is_imputed':[False]}))
    result=client.get('/api/history/RJ-Jaipur')
    decoded=json.loads(result.text,parse_constant=lambda value:(_ for _ in ()).throw(ValueError(value)))
    assert decoded['data'][0]['gwl'] is None and decoded['data'][0]['rainfall'] is None
    assert decoded['data'][0]['is_observed'] is False
    connection.close.assert_called_once()

@pytest.mark.parametrize('query',['?months=0','?months=no','?start=no','?start=2024-01&end=2023-01'])
def test_history_invalid_ranges(client,query):
    assert client.get('/api/history/RJ-Jaipur'+query).status_code==400

def test_unknown_district(client,monkeypatch):
    monkeypatch.setattr(predict,'resolve_district_id',Mock(side_effect=LookupError('Unknown ID')))
    assert client.get('/api/predict/not-known').status_code==404

def test_health_checks_model_contents(client,monkeypatch):
    connection=Mock()
    connection.cursor.return_value.__enter__=Mock(return_value=Mock())
    connection.cursor.return_value.__exit__=Mock(return_value=False)
    monkeypatch.setattr(health,'get_connection',lambda:connection)
    monkeypatch.setattr(health,'feature_generation',lambda:'generation')
    monkeypatch.setattr(health,'load_model_bundle',Mock(side_effect=ValueError('Corrupt bundle')))
    result=client.get('/api/health')
    assert result.status_code==503 and result.json['model_loaded'] is False
