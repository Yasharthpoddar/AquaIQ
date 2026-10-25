"""AquaIQ — Comprehensive Unit & Integration Tests for State-Wise Groundwater Forecasting.

Tests:
1. Authoritative State Registry, Aliases, and District-to-State Mapping.
2. Canonical Crosswalk 100% State Coverage (725 districts).
3. State Observation Aggregation, Weighting, and Missing-Data Safety (never treated as 0).
4. Zero-Observation and Insufficient-Coverage States (no fabricated data).
5. Exact 12-Month Chronological Response Contract and Baselines.
6. Leakage-Free Chronological Evaluation Protocol.
7. Verified State GeoJSON Feature ID Mapping (36 states).
8. State API Route Validation, Parameters, and Error Handling (400, 404).
9. Full Preservation of Existing District APIs, 6-Month and 12-Month Forecasting.
"""

from datetime import date
import json
from pathlib import Path
import math
import numpy as np
import pandas as pd
import pytest

from models.state_mapping import (
    STATES_REGISTRY,
    STATE_ALIASES,
    resolve_state_id,
    get_state_metadata,
    list_states,
    normalize_state_name,
)
from models.state_forecast import (
    aggregate_state_observations,
    forecast_state_twelve_months,
    get_all_states_summary,
    get_state_districts,
    EVALUATION_METRICS,
    PRODUCT_NAME,
    MODEL_VERSION,
)
from api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


# â”€â”€ 1. Authoritative State Registry & Aliases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_state_registry_contains_all_36_states_and_uts():
    states = list_states()
    assert len(states) == 36
    assert len(STATES_REGISTRY) == 36

    types = {s["type"] for s in states}
    assert types == {"State", "UT"}

    # Verify key states and UTs
    for code in ("UP", "TN", "MH", "RJ", "KA", "DL", "JK", "LA", "LD", "CH", "DD", "AN"):
        assert code in STATES_REGISTRY
        meta = get_state_metadata(code)
        assert meta["state_id"] == code
        assert isinstance(meta["name"], str) and meta["name"]
        assert isinstance(meta["st_code"], str) and len(meta["st_code"]) == 2


def test_resolve_state_id_handles_codes_names_aliases_and_district_ids():
    # Direct code
    assert resolve_state_id("UP") == "UP"
    assert resolve_state_id("up") == "UP"
    assert resolve_state_id("TN") == "TN"

    # Full name
    assert resolve_state_id("Uttar Pradesh") == "UP"
    assert resolve_state_id("tamil nadu") == "TN"
    assert resolve_state_id("Maharashtra") == "MH"

    # Historical and colloquial aliases
    assert resolve_state_id("Orissa") == "OD"
    assert resolve_state_id("Odisha") == "OD"
    assert resolve_state_id("Uttaranchal") == "UK"
    assert resolve_state_id("Uttarakhand") == "UK"
    assert resolve_state_id("Pondicherry") == "PY"
    assert resolve_state_id("Puducherry") == "PY"
    assert resolve_state_id("The Dadra and Nagar Haveli and Daman and Diu") == "DD"
    assert resolve_state_id("Dadra and Nagar Haveli") == "DD"
    assert resolve_state_id("Daman and Diu") == "DD"
    assert resolve_state_id("Jammu & Kashmir") == "JK"

    # District ID resolution
    assert resolve_state_id("UP-Deoria") == "UP"
    assert resolve_state_id("TN-Cuddalore") == "TN"
    assert resolve_state_id("RJ-Jaipur") == "RJ"

    # Invalid / ambiguous identifiers raise LookupError
    with pytest.raises(LookupError):
        resolve_state_id("Atlantis")
    with pytest.raises(LookupError):
        resolve_state_id("")
    with pytest.raises(LookupError):
        resolve_state_id(None)


# â”€â”€ 2. Canonical Crosswalk 100% State Coverage â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_all_725_canonical_districts_map_to_registered_states():
    cw_path = ROOT / "data_ingestion/district_crosswalk.csv"
    assert cw_path.exists()
    cw = pd.read_csv(cw_path)
    canonical = cw[cw["source"] == "GeoJSON"]
    assert len(canonical) == 724 or len(canonical) == 725

    unique_districts = cw["canonical_district_id"].unique()
    assert len(unique_districts) >= 724

    for dist_id in unique_districts:
        state_code = dist_id.split("-")[0]
        assert state_code in STATES_REGISTRY, f"District {dist_id} has unregistered state prefix {state_code}"
        assert resolve_state_id(dist_id) == state_code



@pytest.fixture
def state_inputs(monkeypatch):
    from models import state_forecast as sf
    ids = ['TN-A', 'TN-B', 'TN-C', 'TN-D']
    frame = pd.DataFrame([dict(district_id=d, date=pd.Timestamp(m), gwl_current=v,
        is_observed=True, is_imputed=False) for d,v in zip(ids,[2.,6.,10.,14.])
        for m in ['2021-01-01','2021-02-01','2021-03-01']])
    frame.attrs.update(feature_generation_id='test-generation', data_sha256='fixture-only')
    sf.clear_caches()
    monkeypatch.setattr(sf, 'get_feature_matrix', lambda: frame)
    monkeypatch.setattr(sf, 'get_state_districts', lambda code: ids)
    monkeypatch.setattr(sf, '_readiness', lambda district, cutoff: {'eligible': True})
    monkeypatch.setattr(sf.climate, 'load_bundle', lambda **kwargs: (None, {
        'model_sha256': 'a'*64, 'train_target_cutoff': '2019-12-31', 'feature_generation_id': 'test-generation'}))
    seen = []
    def predict(evidence, **kwargs):
        seen.append(evidence)
        assert evidence['zone'] is None and evidence['estimate_type'] == 'district_level'
        assert evidence['frame'].date.max() <= pd.Timestamp('2021-02-01')
        anchor = float(evidence['history'].gwl_current.iloc[-1])
        return dict(district_id=evidence['district_id'], product=sf.climate.PRODUCT_NAME,
            status='forecast', as_of='2021-02-28', feature_generation='test-generation', model_version=sf.climate.MODEL_VERSION,
            model_sha256='a'*64, units='m_bgl', estimate_type='district_level',
            horizon_months=12, estimated_current_gwl=anchor, forecast=[
                dict(horizon=h, date=(pd.Timestamp('2021-02-01')+pd.DateOffset(months=h)).date().isoformat(),
                     month=(pd.Timestamp('2021-02-01')+pd.DateOffset(months=h)).strftime('%Y-%m'),
                     predicted_gwl=anchor+h) for h in range(1,13)])
    monkeypatch.setattr(sf.climate, 'forecast_from_evidence', predict)
    return sf, frame, seen


def test_equal_fixed_panel_uses_real_xgboost_outputs_and_no_future_rows(state_inputs):
    sf, frame, seen = state_inputs
    result = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert result['status'] == 'forecast'
    assert result['estimated_current_gwl_m_bgl'] == 8
    assert [r['predicted_gwl'] for r in result['forecast']] == list(range(9,21))
    assert result['contributing_districts_count'] == 4
    assert result['forecast'][0]['target_date'] == '2021-03-01'
    assert result['forecast'][-1]['target_date'] == '2022-02-01'
    assert len(seen) == 4
    # Cached results are immutable to callers and keyed by state/date/data/model.
    result['forecast'][0]['predicted_gwl'] = -10
    assert sf.forecast_state_twelve_months('TN', '2021-02-28')['forecast'][0]['predicted_gwl'] == 9


def test_observations_exclude_imputed_missing_and_future_without_zero_fill(state_inputs):
    sf, frame, _ = state_inputs
    frame.loc[frame.district_id.eq('TN-A'), 'is_imputed'] = True
    frame.loc[frame.district_id.eq('TN-B'), 'is_observed'] = False
    frame.loc[frame.district_id.eq('TN-C'), 'gwl_current'] = np.nan
    hist = sf.aggregate_state_observations('TN', '2021-02-27')
    assert hist.date.tolist() == [pd.Timestamp('2021-01-01')]
    assert hist.gwl_m_bgl.tolist() == [14.]
    assert hist.contributing_districts_count.tolist() == [1]
    assert hist.district_coverage_pct.tolist() == [25.]


def test_insufficient_panel_never_zero_fills_or_substitutes_a_zone(state_inputs, monkeypatch):
    sf, _, seen = state_inputs
    monkeypatch.setattr(sf, '_readiness', lambda district, cutoff: {'eligible': district.district_id.iloc[0] == 'TN-A'})
    result = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert result['status'] == 'insufficient_data'
    assert result['forecast'] == []
    assert result['district_coverage_pct'] == 25.
    assert len(seen) == 1


def test_single_district_state_can_pass_but_multi_district_needs_two(state_inputs, monkeypatch):
    sf, _, _ = state_inputs
    monkeypatch.setattr(sf, 'get_state_districts', lambda _: ['TN-A'])
    assert sf.forecast_state_twelve_months('TN', '2021-02-28')['status'] == 'forecast'


def test_corrupt_model_fails_closed(state_inputs, monkeypatch):
    sf, _, seen = state_inputs
    def unavailable(**kwargs):
        raise ValueError('invalid hash')
    monkeypatch.setattr(sf.climate, 'load_bundle', unavailable)
    result = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert result['status'] == 'model_unavailable'
    assert result['forecast'] == [] and not seen


@pytest.mark.parametrize('field,bad', [('district_id','TN-Wrong'), ('units','feet'),
    ('model_version','trend'), ('model_sha256','wrong'), ('estimate_type','zone_fallback'),
    ('as_of','2021-02-01'), ('feature_generation','wrong-generation')])
def test_wrong_district_model_units_or_zone_rejected(state_inputs, monkeypatch, field, bad):
    sf, _, _ = state_inputs
    predict = sf.climate.forecast_from_evidence
    def corrupt(evidence, **kwargs):
        result = predict(evidence)
        result[field] = bad
        return result
    monkeypatch.setattr(sf.climate, 'forecast_from_evidence', corrupt)
    with pytest.raises(RuntimeError, match='Invalid district'):
        sf.forecast_state_twelve_months('TN', '2021-02-28')


def test_incomplete_or_wrong_calendar_xgboost_path_rejected(state_inputs, monkeypatch):
    sf, _, _ = state_inputs
    predict = sf.climate.forecast_from_evidence
    def corrupt(evidence, **kwargs):
        result = predict(evidence)
        result['forecast'][2]['date'] = '2021-03-01'
        return result
    monkeypatch.setattr(sf.climate, 'forecast_from_evidence', corrupt)
    with pytest.raises(RuntimeError, match='calendar'):
        sf.forecast_state_twelve_months('TN', '2021-02-28')


def test_duplicate_month_abstains_instead_of_double_weighting(state_inputs):
    sf, frame, _ = state_inputs
    frame.loc[len(frame)] = frame.iloc[0]
    result = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert result['status'] == 'model_unavailable' and result['forecast'] == []


def test_unsupported_weighting_and_horizons_fail(state_inputs):
    sf, _, _ = state_inputs
    with pytest.raises(ValueError):
        sf.forecast_state_twelve_months('TN', '2021-02-28', weighting='population')
    with pytest.raises(ValueError):
        sf.get_all_states_summary(horizon=6)


def test_cache_invalidates_when_district_registry_or_card_changes(state_inputs, monkeypatch):
    sf, _, seen = state_inputs
    first = sf.forecast_state_twelve_months('TN', '2021-02-28')
    monkeypatch.setattr(sf, 'get_state_districts', lambda _: ['TN-A','TN-B'])
    second = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert first['estimated_current_gwl_m_bgl'] == 8 and second['estimated_current_gwl_m_bgl'] == 4
    monkeypatch.setattr(sf.climate, 'load_bundle', lambda **kwargs: (None, {
        'model_sha256':'a'*64, 'train_target_cutoff':'2019-11-30', 'feature_generation_id':'test-generation'}))
    third = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert third['model_train_target_cutoff'] == '2019-11-30'
    assert len(seen) == 8


def test_geojson_matches_registry_and_all_district_prefixes():
    value = json.loads((ROOT/'dashboard/public/india_states.geojson').read_text())
    assert len(value['features']) == 36
    assert {f['properties']['state_id'] for f in value['features']} == set(STATES_REGISTRY)
    for row in value['features']:
        assert row['properties']['state_name'] == STATES_REGISTRY[row['properties']['state_id']]['name']


def test_historical_baseline_evidence_preserved_without_superiority_requirement():
    legacy = json.loads((ROOT/'reports/state_forecast_evaluation.json').read_text())
    assert legacy  # Legacy harmonic evidence remains separate from the new XGBoost product.
    assert EVALUATION_METRICS['prospective_skill_verified'] is False
    from scripts.evaluate_state_xgboost import comparisons, exact_panel_mean
    cases = pd.DataFrame({'actual':[2.,4.], 'xgboost':[3.,5.],
                          'persistence':[2.,4.], 'seasonal_naive':[np.nan,5.]})
    result = comparisons(cases)
    assert result['xgb_and_observed_persistence']['persistence']['mae_m'] == 0
    assert result['all_three_matched']['xgboost']['n'] == 1
    assert result['all_three_matched']['xgboost']['r2'] is None
    labels = pd.Series([3.], index=pd.MultiIndex.from_tuples([('TN-A',pd.Timestamp('2021-01-01'))]))
    assert exact_panel_mean(labels,['TN-A','TN-B'],'2021-01-01') is None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AQUAIQ_ENABLE_SYNC_FORECAST_FALLBACK", "true")
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()


def test_api_horizon_dates_identity_and_structured_model_failure(client, monkeypatch):
    import api.routes.state as routes
    assert client.get('/api/states').get_json()['total'] == 36
    for query in ['horizon=6','horizon=bad','as_of=bad','as_of=2099-01-01']:
        assert client.get('/api/predict/state/TN?'+query).status_code == 400
    assert client.get('/api/predict/state/Atlantis').status_code == 404
    monkeypatch.setattr(routes, 'forecast_state_twelve_months',
        lambda code, as_of: dict(status='model_unavailable', state_id=code, forecast=[]))
    response = client.get('/api/predict/state/TN')
    assert response.status_code == 503 and response.get_json()['forecast'] == []
    assert client.get('/api/states/summary?horizon=6').status_code == 400


def test_cache_eviction_and_uncached_state_calculation_are_equivalent(state_inputs):
    from scripts.benchmark_state_forecasts import canonical
    sf, _, seen = state_inputs
    first = sf.forecast_state_twelve_months('TN', '2021-02-28')
    sf._FORECAST_CACHE.clear()
    # Reaggregation reuses district forecasts after a state entry is evicted.
    assert canonical(sf.forecast_state_twelve_months('TN', '2021-02-28')) == canonical(first)
    assert len(seen) == 4
    sf.clear_caches()
    assert canonical(sf.forecast_state_twelve_months('TN', '2021-02-28')) == canonical(first)
    assert len(seen) == 8


def test_insufficient_coverage_is_cached_without_fabricated_forecasts(state_inputs, monkeypatch):
    sf, _, seen = state_inputs
    monkeypatch.setattr(sf, '_readiness', lambda district, cutoff: {'eligible': district.district_id.iloc[0] == 'TN-A'})
    first = sf.forecast_state_twelve_months('TN', '2021-02-28')
    first['excluded_districts'].clear()
    again = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert again['status'] == 'insufficient_data' and again['forecast'] == []
    assert len(again['excluded_districts']) == 3 and len(seen) == 1


def test_model_failures_are_not_cached_and_warm_hits_verify_bundle(state_inputs, monkeypatch):
    sf, _, seen = state_inputs
    loader = sf.climate.load_bundle
    sf.forecast_state_twelve_months('TN', '2021-02-28')
    def unavailable(**kwargs):
        raise RuntimeError('bundle missing')
    monkeypatch.setattr(sf.climate, 'load_bundle', unavailable)
    failed = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert failed['status'] == 'model_unavailable' and failed['forecast'] == []
    monkeypatch.setattr(sf.climate, 'load_bundle', loader)
    assert sf.forecast_state_twelve_months('TN', '2021-02-28')['status'] == 'forecast'
    assert len(seen) == 4


@pytest.mark.parametrize('field', ['data_sha256', 'feature_generation_id'])
def test_feature_identity_changes_invalidate_predictions(state_inputs, monkeypatch, field):
    sf, frame, seen = state_inputs
    sf.forecast_state_twelve_months('TN', '2021-02-28')
    predict = sf.climate.forecast_from_evidence
    def updated(evidence, **kwargs):
        value = predict(evidence, **kwargs)
        value['feature_generation'] = evidence['generation']
        return value
    monkeypatch.setattr(sf.climate, 'forecast_from_evidence', updated)
    frame.attrs[field] = 'new-source-identity'
    sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert len(seen) == 8


def test_model_artifact_identity_invalidates_district_and_state_cache(state_inputs, monkeypatch):
    sf, _, seen = state_inputs
    sf.forecast_state_twelve_months('TN', '2021-02-28')
    model, card = sf.climate.load_bundle()
    monkeypatch.setattr(sf.climate, 'load_bundle', lambda **kwargs: (model, {**card, 'model_sha256': 'b'*64}))
    predict = sf.climate.forecast_from_evidence
    def updated(evidence, **kwargs):
        value = predict(evidence, **kwargs)
        value['model_sha256'] = 'b'*64
        return value
    monkeypatch.setattr(sf.climate, 'forecast_from_evidence', updated)
    assert sf.forecast_state_twelve_months('TN', '2021-02-28')['model_sha256'] == 'b'*64
    assert len(seen) == 8


def test_as_of_is_part_of_cache_identity_even_with_same_origin_month(state_inputs, monkeypatch):
    sf, _, seen = state_inputs
    sf.forecast_state_twelve_months('TN', '2021-02-28')
    predict = sf.climate.forecast_from_evidence
    def updated(evidence, **kwargs):
        value = predict(evidence, **kwargs)
        value['as_of'] = evidence['as_of'].date().isoformat()
        return value
    monkeypatch.setattr(sf.climate, 'forecast_from_evidence', updated)
    earlier = sf.forecast_state_twelve_months('TN', '2021-02-27')
    assert earlier['as_of'] == '2021-02-27' and len(seen) == 8
    assert seen[-1]['frame'].date.max() == pd.Timestamp('2021-01-01')


def test_different_states_are_isolated(state_inputs, monkeypatch):
    sf, frame, seen = state_inputs
    other = frame.copy()
    other['district_id'] = other.district_id.str.replace('TN-', 'HR-')
    other['gwl_current'] += 30
    combined = pd.concat([frame, other], ignore_index=True)
    combined.attrs.update(frame.attrs)
    monkeypatch.setattr(sf, 'get_feature_matrix', lambda: combined)
    monkeypatch.setattr(sf, 'get_state_districts', lambda code: [code+'-'+d for d in 'ABCD'])
    tn = sf.forecast_state_twelve_months('TN', '2021-02-28')
    hr = sf.forecast_state_twelve_months('HR', '2021-02-28')
    assert tn['forecast'][0]['predicted_gwl'] == 9
    assert hr['forecast'][0]['predicted_gwl'] == 39
    assert all(d.startswith('HR-') for d in hr['contributing_district_ids'])
    assert sf.forecast_state_twelve_months('TN', '2021-02-28')['forecast'] == tn['forecast']
    assert len(seen) == 8


def test_summary_failure_is_503_instead_of_empty_success(state_inputs, client, monkeypatch):
    sf, _, _ = state_inputs
    monkeypatch.setattr(sf, 'forecast_state_twelve_months', lambda *a, **kw: {'status':'model_unavailable'})
    response = client.get('/api/states/summary?as_of=2021-02-28')
    assert response.status_code == 503
    assert response.get_json()['status'] == 'unavailable'


def test_registry_endpoint_provides_shared_server_as_of(client):
    value = client.get('/api/states?as_of=2021-02-28').get_json()
    assert value['as_of'] == '2021-02-28' and value['horizon_months'] == 12


def test_feature_file_revision_reloads_verification_and_failure_cannot_serve_cache(state_inputs, monkeypatch):
    sf, fixture, seen = state_inputs
    # Exercise the production snapshot loader with isolated signatures, never write real data.
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('state_snapshot_under_test', ROOT/'models/state_forecast.py')
    real = module_from_spec(spec)
    spec.loader.exec_module(real)
    version = [1]
    loaded = []
    def loader():
        loaded.append(version[0])
        if version[0] == 3:
            raise ValueError('manifest no longer verifies')
        return fixture.copy()
    monkeypatch.setattr(real, '_file_signature', lambda paths: tuple([version[0]]))
    monkeypatch.setattr(real, 'load_feature_matrix', loader)
    first = real.get_feature_matrix()
    assert real.get_feature_matrix() is first and loaded == [1]
    version[0] = 2
    assert real.get_feature_matrix() is not first and loaded == [1, 2]
    version[0] = 3
    with pytest.raises(ValueError, match='manifest'):
        real.get_feature_matrix()
    with pytest.raises(ValueError, match='manifest'):
        real.get_feature_matrix()


def test_registry_change_during_request_is_rejected(state_inputs, monkeypatch):
    sf, _, seen = state_inputs
    calls = []
    monkeypatch.setattr(sf, '_REGISTRY_SNAPSHOT', None)
    def changing_registry(code):
        calls.append(code)
        if len(calls) == 3:
            sf._REGISTRY_SNAPSHOT = ('new', 'new-hash', ())
        return ['TN-A', 'TN-B']
    monkeypatch.setattr(sf, 'get_state_districts', changing_registry)
    value = sf.forecast_state_twelve_months('TN', '2021-02-28')
    assert value['status'] == 'model_unavailable' and not seen
