"""Comprehensive automated tests for state-level forecasting eligibility audit and production release candidates."""
import json
from pathlib import Path
import pytest

from models.state_mapping import STATES_REGISTRY
from models import state_median_release as release
from models import state_median_policy as policy
from models import state_median_forecast as core

R3_DIR = Path('models/artifacts/state_median_releases/20261030-r3')
RC1_DIR = Path('models/artifacts/state_median_releases/20261030-production-rc1')


@pytest.mark.parametrize("release_dir,expected_release", [
    (R3_DIR, '2026.10.30-r3'),
    (RC1_DIR, '2026.10.30-production-rc1'),
])
def test_release_manifest_integrity(release_dir, expected_release):
    """Verify release manifests exist, have valid checksums, format_version=2 and 17 trained states."""
    models, card, manifest, signature = release.verify_release(release_dir, expected_release=expected_release)
    assert manifest['format_version'] == 2
    assert manifest['model_version'] == policy.MODEL_VERSION
    assert manifest['policy_version'] == policy.POLICY_VERSION
    assert len(models) == 17
    assert manifest['training_cutoff'] == '2026-09-01'
    assert manifest['as_of'] == '2026-10-29'


@pytest.mark.parametrize("release_dir", [R3_DIR, RC1_DIR])
def test_all_36_states_represented_in_candidate_releases(release_dir):
    """Verify all 36 states in STATES_REGISTRY are present in the candidate releases."""
    manifest = json.loads((release_dir / 'release_manifest.json').read_text(encoding='utf-8'))
    methods = manifest['state_methods']
    assert set(methods.keys()) == set(STATES_REGISTRY.keys())
    assert len(methods) == 36


@pytest.mark.parametrize("release_dir", [R3_DIR, RC1_DIR])
def test_exact_state_method_distribution(release_dir):
    """Verify the exact distribution: 17 XGBoost, 17 persistence fallback, 2 unavailable."""
    manifest = json.loads((release_dir / 'release_manifest.json').read_text(encoding='utf-8'))
    methods = manifest['state_methods']
    
    xgb_states = [s for s, m in methods.items() if m == 'state_median_xgboost']
    fallback_states = [s for s, m in methods.items() if m == 'persistence_fallback']
    unavail_states = [s for s, m in methods.items() if m == 'no_observations']
    
    assert len(xgb_states) == 17, f"Expected 17 XGBoost states, got {len(xgb_states)}: {xgb_states}"
    assert len(fallback_states) == 17, f"Expected 17 fallback states, got {len(fallback_states)}: {fallback_states}"
    assert len(unavail_states) == 2, f"Expected 2 unavailable states, got {len(unavail_states)}: {unavail_states}"
    
    # Exact known set of XGBoost qualifying states
    expected_xgb = {'AP', 'BR', 'CG', 'GJ', 'HP', 'HR', 'JH', 'KA', 'KL', 'MH', 'MP', 'OD', 'PB', 'RJ', 'TN', 'TR', 'UP'}
    assert set(xgb_states) == expected_xgb
    
    # Exact unavailable states (zero observations)
    assert set(unavail_states) == {'LA', 'LD'}


@pytest.mark.parametrize("release_dir", [R3_DIR, RC1_DIR])
def test_zero_observation_states_marked_unavailable(release_dir):
    """Ladakh and Lakshadweep have zero observations and must never fabricate forecasts."""
    card = json.loads((release_dir / 'release_model_card.json').read_text(encoding='utf-8'))
    for code in ('LA', 'LD'):
        state_meta = card['states'][code]
        assert state_meta['status'] == 'insufficient_data'
        assert state_meta['forecast_method'] == 'no_observations'
        assert state_meta['genuine_observed_months'] == 0
        assert state_meta['latest_observation_date'] is None


@pytest.mark.parametrize("release_dir", [R3_DIR, RC1_DIR])
def test_single_observation_state_persistence_fallback(release_dir):
    """Sikkim has genuine observations and must receive a 12-month persistence fallback."""
    card = json.loads((release_dir / 'release_model_card.json').read_text(encoding='utf-8'))
    sk = card['states']['SK']
    assert sk['status'] == 'forecast'
    assert sk['forecast_method'] == 'persistence_fallback'
    assert sk['genuine_observed_months'] == 1
    assert sk['reference_is_stale'] is True
    assert sk['historical_reference_date'] == '2025-01-01'


@pytest.mark.parametrize("payloads_path", [
    Path('scratch/state_median_r3_payloads.json'),
    Path('scratch/production_rc1_payloads.json'),
])
def test_payloads_have_exactly_34_forecastable_states_and_408_predictions(payloads_path):
    """Payloads must contain exactly 34 forecastable states, each with 12 monthly predictions."""
    if not payloads_path.exists():
        pytest.skip(f"Run release generate for {payloads_path} first")
    
    payloads = json.loads(payloads_path.read_text(encoding='utf-8'))
    assert len(payloads) == 36
    
    forecastable = [p for p in payloads.values() if p['status'] == 'forecast']
    assert len(forecastable) == 34
    
    total_predictions = sum(len(p['forecast']) for p in forecastable)
    assert total_predictions == 408
    
    for p in forecastable:
        assert len(p['forecast']) == 12
        dates = [r['target_date'] for r in p['forecast']]
        assert dates[0] == '2026-11-01'
        assert dates[-1] == '2027-10-01'
        assert all(isinstance(r['predicted_gwl'], (int, float)) and r['predicted_gwl'] >= 0 for r in p['forecast'])


def test_immutable_releases_r1_and_r2_preserved():
    """Verify r1 and r2 release manifests remain untouched and valid."""
    r1_dir = Path('models/artifacts/state_median_releases/20261029-r1')
    r2_dir = Path('models/artifacts/state_median_releases/20261029-r2')
    assert (r1_dir / 'release_manifest.json').exists()
    assert (r2_dir / 'release_manifest.json').exists()
    
    r1_manifest = json.loads((r1_dir / 'release_manifest.json').read_text(encoding='utf-8'))
    r2_manifest = json.loads((r2_dir / 'release_manifest.json').read_text(encoding='utf-8'))
    
    assert r1_manifest['artifact_release'] == '2026.10.29-r1'
    assert r2_manifest['artifact_release'] == '2026.10.29-r2'
    assert r1_manifest['format_version'] == 1
    assert r2_manifest['format_version'] == 2


def test_district_model_remains_unchanged():
    """Verify production district model hash remains untouched."""
    p = Path('models/artifacts/climate_12m_bundles/20261024T152950484968Z-6369f3e3ec/model.json')
    assert p.exists()
    import hashlib
    with open(p, 'rb') as f:
        h = hashlib.sha256(f.read()).hexdigest()
    assert h == '4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03'
