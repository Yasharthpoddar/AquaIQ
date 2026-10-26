"""Official-data overlays preserve causal semantics and frozen training inputs."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from preprocessing import official_enrichment as enrichment
from preprocessing.features import build_gwl_features
from preprocessing.pipeline import apply_causal_gwl_imputation
from models.xgboost_model import load_feature_matrix
from scripts.precompute_forecasts import run_precomputation


def baseline():
    frame = pd.DataFrame({'district_id': 'AA-Test', 'date': pd.date_range('2019-01-01', '2021-12-01', freq='MS')})
    frame['gwl'] = np.nan
    frame.loc[frame.date.dt.month.eq(1), 'gwl'] = [3., 4., 5.]
    frame = build_gwl_features(apply_causal_gwl_imputation(frame))
    for upper, lower in zip(enrichment.GWL_COLUMNS[:3], enrichment.GWL_COLUMNS[3:]):
        frame[lower] = frame[upper]
    frame = frame.drop(columns='gwl')
    frame['feature_generation'] = 'baseline'
    for col in ('rainfall_current', 'rainfall_3mo_avg', 'temperature', 'evapotranspiration', 'water_balance_proxy', 'monsoon_deficit_pct'):
        frame[col] = 2.
    frame['crop_season_flag'] = 'Rabi'
    frame['data_readiness_score'] = frame[[c for c in enrichment.FEATURES_LIST if c != 'crop_season_flag']].notna().mean(axis=1) * 100
    return frame


def months(date='2021-05-01', value=7.):
    return pd.DataFrame([dict(district_id='AA-Test', date=date, gwl_mean=value,
        station_count=2, reading_count=2, first_observation_date=date,
        last_observation_date=date, source='CGWB', metric='GWL', units='m_bgl', is_observed=True)])


def overlay(base=None, incoming=None):
    return enrichment.enrich_frame(base if base is not None else baseline(), incoming if incoming is not None else months(),
        generation='candidate', as_of='2022-01-20', registry_ids=['AA-Test'])


def test_overlay_uses_existing_causal_rules_and_preserves_training_values():
    original = baseline()
    candidate, added, overlap = overlay(original)
    assert len(added) == 1 and overlap.empty
    selected = candidate.set_index('date')
    assert selected.loc['2021-05-01', 'is_observed']
    assert not selected.loc['2021-05-01', 'is_imputed']
    assert selected.loc['2021-08-01', 'gwl_current'] == 7
    assert selected.loc['2021-08-01', 'gwl_lag_3mo'] == 7
    assert np.isnan(selected.loc['2021-09-01', 'gwl_current'])
    proof = enrichment.prove_frozen_compatibility(original, candidate, '2019-12-31')
    assert proof['training_rows_checked'] == 12
    assert proof['identical_training_values']
    pd.testing.assert_frame_equal(original, baseline())


def test_existing_measured_month_retained_and_conflict_reported():
    candidate, added, overlap = overlay(incoming=months('2021-01-01', 200))
    assert added.empty and len(overlap) == 1
    assert overlap.iloc[0].candidate_difference_m == 195
    assert candidate.set_index('date').loc['2021-01-01', 'gwl_current'] == 5


def test_future_observation_cannot_change_past_features():
    a, _, _ = overlay(incoming=months('2021-05-01', 7))
    b, _, _ = overlay(incoming=months('2021-05-01', 30))
    pd.testing.assert_frame_equal(a[a.date < '2021-05-01'], b[b.date < '2021-05-01'])


@pytest.mark.parametrize('column,value', [('units', 'm_msl'), ('gwl_mean', -1), ('gwl_mean', np.inf),
    ('district_id', 'Unknown'), ('is_observed', False), ('station_count', 1.5), ('reading_count', 1),
    ('date', '2021-05-03'), ('last_observation_date', '2021-06-01'), ('date', '2022-01-01')])
def test_invalid_candidate_fails_closed(column, value):
    incoming = months()
    incoming[column] = value
    with pytest.raises(ValueError):
        overlay(incoming=incoming)


def test_duplicate_and_incomplete_calendar_grids_rejected():
    incoming = pd.concat([months(), months()], ignore_index=True)
    with pytest.raises(ValueError, match='invalid canonical'):
        overlay(incoming=incoming)
    with pytest.raises(ValueError, match='complete common monthly grid'):
        overlay(base=baseline().drop(index=4))


@pytest.mark.parametrize('column', ['rainfall_current', 'gwl_current', 'crop_season_flag'])
def test_frozen_artifact_cannot_be_rebound_to_changed_training_or_weather(column):
    base = baseline()
    candidate, _, _ = overlay()
    candidate.loc[0, column] = 'Zaid' if column == 'crop_season_flag' else 100
    with pytest.raises(ValueError, match='identical training inputs'):
        enrichment.prove_frozen_compatibility(base, candidate, '2019-12-31')


def test_explicit_snapshot_never_falls_back_to_public_database(tmp_path, monkeypatch):
    (tmp_path / 'feature_manifest.json').write_text('{}')
    monkeypatch.setattr('models.xgboost_model.get_connection', lambda: pytest.fail('must not access database'))
    with pytest.raises(FileNotFoundError, match='database fallback is forbidden'):
        load_feature_matrix(tmp_path)


def test_explicit_candidate_inputs_require_complete_set_and_isolated_connection():
    with pytest.raises(ValueError, match='explicit features'):
        run_precomputation(as_of='2026-10-26', feature_directory='candidate')
    with pytest.raises(ValueError, match='isolated test connection'):
        run_precomputation(as_of='2026-10-26', feature_directory='candidate', checkpoint='candidate', calibration_path='candidate')


def test_candidate_evidence_hash_tampering_detected(tmp_path):
    (tmp_path / 'manifest.json').write_text(json.dumps({'artifact_version': 'nwdp-cgwb-manual-v1', 'output_sha256': {
        'canonical_district_month_candidates.csv': '0' * 64, 'station_audit.csv': '0' * 64}, 'geojson_sha256': 'x'}))
    (tmp_path / 'canonical_district_month_candidates.csv').write_text('altered')
    with pytest.raises(ValueError, match='checksum/path'):
        enrichment.read_candidate(tmp_path, as_of='2026-10-26', registry_ids=['AA-Test'])
