"""Supplemental history and count projections preserve immutable release data."""
from copy import deepcopy
from datetime import date
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.app import create_app
from models import state_median_release_storage as releases
from tests.test_state_median_release_storage import release_fixture
from tests.test_state_median_policy_storage import tiered_fixture


def test_summary_counts_actual_xgboost_and_persistence_monthly_records(monkeypatch):
    payloads,manifest = tiered_fixture()
    stored = releases._summary(payloads,manifest,str(uuid4()))
    before = deepcopy(stored)
    calls = []
    def read(as_of,generation):
        calls.append((as_of,generation))
        return payloads,manifest,stored
    monkeypatch.setattr(releases,'_read_release',read)
    result = releases.get_published_summary_statistics('2025-01-31',stored['generation_id'])
    assert calls == [('2025-01-31',stored['generation_id'])]
    assert result['available_states_count'] == 2
    assert result['forecast_month_count'] == 24
    assert result['unavailable_states_count'] == 34
    assert result['counts_by_forecast_method'] == {'state_median_xgboost':1,'persistence_fallback':1,'no_observations':34}
    assert result['forecast_coverage_basis'] == 'validated_persisted_forecast_records'
    assert next(row for row in result['states'] if row['state_id']=='AN')['forecast_month_count'] == 12
    assert next(row for row in result['states'] if row['state_id']=='LA')['forecast_month_count'] == 0
    assert stored == before
    assert 'forecast_month_count' not in stored


def test_r1_unavailable_states_are_not_relabelled_no_observations(monkeypatch):
    payloads,manifest = release_fixture()
    stored = releases._summary(payloads,manifest,str(uuid4()))
    monkeypatch.setattr(releases,'_read_release',lambda *args:(payloads,manifest,stored))
    result = releases.get_published_summary_statistics()
    assert result['available_states_count'] == 1 and result['forecast_month_count'] == 12
    assert result['unavailable_states_count'] == 35
    assert result['counts_by_forecast_method'] == {'state_median_xgboost':1,'persistence_fallback':0,'no_observations':0}
    assert all(row['forecast_month_count'] in (0,12) for row in result['states'])


def test_published_state_context_keeps_manifest_and_forecast_on_one_generation(monkeypatch):
    payloads,manifest = release_fixture()
    summary = releases._summary(payloads,manifest,str(uuid4()))
    calls = []
    def read(as_of,generation):
        calls.append((as_of,generation))
        return payloads,manifest,summary
    monkeypatch.setattr(releases,'_read_release',read)
    context = releases.get_published_state_context('Tamil Nadu','2025-01-31',summary['generation_id'])
    assert len(calls)==1
    assert context['forecast']['generation_id']==summary['generation_id']
    assert context['manifest']==manifest
    context['manifest']['data_sha256']='changed'
    context['forecast']['history'].clear()
    assert manifest['data_sha256']!='changed' and payloads['TN']['history']


@pytest.fixture
def client():
    return create_app({'TESTING':True}).test_client()


def test_history_endpoint_passes_exact_published_context_to_read_only_helper(client,monkeypatch):
    payloads,manifest = release_fixture()
    generation = str(uuid4())
    forecast = dict(payloads['TN'],generation_id=generation)
    reads,history_calls = [],[]
    def context(code,as_of,selected):
        reads.append((code,as_of,selected))
        return {'forecast':deepcopy(forecast),'manifest':manifest}
    def history(code,selected_forecast,selected_manifest):
        history_calls.append((code,selected_forecast,selected_manifest))
        return dict(product='state_median_groundwater_history',state_id=code,state_name='Tamil Nadu',
            units='m_bgl',as_of=selected_forecast['as_of'],generation_id=selected_forecast['generation_id'],
            model_version=selected_forecast['model_version'],feature_generation=selected_forecast['feature_generation'],
            source_data_sha256=selected_forecast['source_data_sha256'],history=deepcopy(selected_forecast['history']))
    monkeypatch.setattr(releases,'get_published_state_context',context)
    monkeypatch.setitem(sys.modules,'models.state_median_history',SimpleNamespace(get_full_state_history=history))
    result = client.get(f'/api/v2/history/state/Tamil%20Nadu?generation_id={generation}&as_of=2025-01-31')
    assert result.status_code==200
    assert reads==[('TN',date(2025,1,31),generation)]
    assert len(history_calls)==1 and history_calls[0][2] is manifest
    assert result.json['generation_id']==generation
    assert result.json['requested_state_id']=='Tamil Nadu' and result.json['resolved_state_id']=='TN'


def test_staged_or_missing_generation_never_reads_source_or_generates_forecast(client,monkeypatch):
    monkeypatch.setattr(releases,'get_published_state_context',lambda *args:None)
    monkeypatch.setitem(sys.modules,'models.state_median_history',SimpleNamespace(
        get_full_state_history=lambda *args:pytest.fail('unpublished generation cannot read supplemental source')))
    result=client.get(f'/api/v2/history/state/TN?generation_id={uuid4()}')
    assert result.status_code==503
    assert result.json['history']==[] and result.json['unavailable_reason']=='median_publication_missing'


def test_missing_or_mismatched_history_source_is_explicit_and_keeps_saved_forecast(client,monkeypatch):
    payloads,manifest=release_fixture()
    forecast=dict(payloads['TN'],generation_id=str(uuid4()))
    original=deepcopy(forecast)
    monkeypatch.setattr(releases,'get_published_state_context',lambda *args:{'forecast':forecast,'manifest':manifest})
    def unavailable(*args):
        raise ValueError('source identity mismatch')
    monkeypatch.setitem(sys.modules,'models.state_median_history',SimpleNamespace(get_full_state_history=unavailable))
    result=client.get('/api/v2/history/state/TN')
    assert result.status_code==503 and result.json['unavailable_reason']=='historical_source_unavailable'
    assert result.json['generation_id']==forecast['generation_id']
    assert forecast==original


@pytest.mark.parametrize('query',['as_of=today','as_of=2025-02-30','generation_id=wrong','horizon=6','unknown=1'])
def test_history_rejects_invalid_queries_before_snapshot_read(client,monkeypatch,query):
    monkeypatch.setattr(releases,'get_published_state_context',lambda *args:pytest.fail('invalid query'))
    assert client.get('/api/v2/history/state/TN?'+query).status_code==400


def test_history_unknown_state_retains_404(client):
    assert client.get('/api/v2/history/state/Atlantis').status_code==404


def test_summary_endpoint_uses_actual_record_projection(client,monkeypatch):
    payloads,manifest=tiered_fixture()
    summary=releases._summary(payloads,manifest,str(uuid4()))
    monkeypatch.setattr(releases,'_read_release',lambda *args:(payloads,manifest,summary))
    result=client.get('/api/v2/states/summary')
    assert result.status_code==200 and result.json['forecast_month_count']==24
    assert result.json['available_states_count']==2 and result.json['unavailable_states_count']==34
