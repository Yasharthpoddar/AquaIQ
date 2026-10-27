"""Reject bad targets and preserve accepted physical measurements before fitting."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import audit_retraining_data as audit

REGISTRY = ['AA-A', 'AA-B']


def fixture_frame(extra=None):
    observations = {'AA-A': {'2002-01-01': 1., '2002-05-01': 2., '2003-01-01': 3.},
                    'AA-B': {'2002-03-01': 5., '2002-09-01': 6.}}
    for district, values in (extra or {}).items():
        observations[district].update(values)
    parts = []
    for district in REGISTRY:
        dates = pd.date_range('2002-01-01', '2003-01-01', freq='MS')
        values = pd.Series([observations[district].get(str(day.date()), np.nan) for day in dates])
        observed = values.notna()
        carried = values.ffill(limit=3)
        age, last = [], None
        for index, value in enumerate(values):
            if pd.notna(value):
                last = index
            age.append(index - last if last is not None else np.nan)
        part = pd.DataFrame({'district_id': district, 'date': dates, 'gwl_current': carried,
            'gwl_lag_3mo': carried.shift(3), 'gwl_lag_6mo': carried.shift(6),
            'is_observed': observed, 'is_imputed': ~observed & carried.notna(),
            'months_since_observation': age, 'feature_generation': 'fixture-generation'})
        for upper, lower in [('GWL_current', 'gwl_current'), ('GWL_lag_3mo', 'gwl_lag_3mo'), ('GWL_lag_6mo', 'gwl_lag_6mo')]:
            part[upper] = part[lower]
        for column in ['rainfall_current', 'rainfall_3mo_avg', 'monsoon_deficit_pct', 'temperature', 'evapotranspiration', 'water_balance_proxy']:
            part[column] = 10.
        part['crop_season_flag'] = 'Rabi'
        parts.append(part)
    frame = pd.concat(parts, ignore_index=True)
    manifest = {'units': dict(audit.FEATURE_UNITS), 'causal_preprocessing': True,
        'feature_columns': list(audit.FEATURES_LIST), 'date_start': '2002-01-01', 'date_end': '2003-01-01',
        'generation_id': 'fixture-generation', 'sample_only': False}
    return frame, manifest


@pytest.fixture
def data():
    return fixture_frame()


def checked(data):
    return audit.validate_frame(*data, REGISTRY)


def test_valid_observations_imputations_and_missing_rows_stay_distinct(data):
    frame = checked(data)
    summary = audit.summarize_frame(frame)
    assert summary['rows'] == 26 and summary['observed_rows'] == 5
    assert summary['imputed_rows'] > 0 and summary['missing_groundwater_rows'] > 0
    assert summary['observed_by_month']['2002-02-01'] == 0
    assert frame is not data[0]
    pd.testing.assert_frame_equal(data[0], fixture_frame()[0])


def test_string_false_is_not_an_observed_training_target(data):
    frame, manifest = data
    frame['is_observed'] = frame.is_observed.astype(str)
    validated = audit.validate_frame(frame, manifest, REGISTRY)
    assert int(validated.is_observed.sum()) == 5


@pytest.mark.parametrize('column', ['is_observed', 'is_imputed'])
def test_unknown_flags_fail_closed(data, column):
    frame, manifest = data
    frame[column] = frame[column].astype(object)
    frame.loc[0, column] = 'unknown'
    with pytest.raises(ValueError, match='Unknown observation flag'):
        audit.validate_frame(frame, manifest, REGISTRY)


@pytest.mark.parametrize('depth', [np.nan, np.inf, -np.inf, -1.])
def test_nonfinite_or_negative_measured_target_rejected(data, depth):
    frame, manifest = data
    frame.loc[0, 'gwl_current'] = depth
    with pytest.raises(ValueError):
        audit.validate_frame(frame, manifest, REGISTRY)


def test_duplicate_month_rejected(data):
    frame, manifest = data
    with pytest.raises(ValueError, match='Duplicate'):
        audit.validate_frame(pd.concat([frame, frame.iloc[:1]]), manifest, REGISTRY)


def test_unknown_district_rejected(data):
    frame, manifest = data
    frame.loc[0, 'district_id'] = 'made-up'
    with pytest.raises(ValueError, match='identifiers'):
        audit.validate_frame(frame, manifest, REGISTRY)


def test_missing_canonical_district_rejected(data):
    frame, manifest = data
    with pytest.raises(ValueError, match='identifiers'):
        audit.validate_frame(frame.loc[frame.district_id.eq('AA-A')], manifest, REGISTRY)


def test_calendar_hole_rejected(data):
    frame, manifest = data
    with pytest.raises(ValueError, match='monthly grid'):
        audit.validate_frame(frame.drop(index=3), manifest, REGISTRY)


def test_non_month_start_rejected(data):
    frame, manifest = data
    frame.loc[0, 'date'] = pd.Timestamp('2002-01-15')
    with pytest.raises(ValueError, match='month-start'):
        audit.validate_frame(frame, manifest, REGISTRY)


@pytest.mark.parametrize('field,value', [('units', {'gwl': 'feet'}), ('causal_preprocessing', False),
    ('feature_columns', list(reversed(audit.FEATURES_LIST))), ('sample_only', True), ('generation_id', 'different')])
def test_invalid_units_order_and_generation_rejected(data, field, value):
    frame, manifest = data
    manifest[field] = value
    with pytest.raises(ValueError):
        audit.validate_frame(frame, manifest, REGISTRY)


def test_observed_imputed_overlap_rejected(data):
    frame, manifest = data
    frame.loc[0, 'is_imputed'] = True
    with pytest.raises(ValueError, match='overlap'):
        audit.validate_frame(frame, manifest, REGISTRY)


def test_untraced_finite_forecast_like_value_is_not_a_measurement(data):
    frame, manifest = data
    row = frame.index[frame.gwl_current.isna()][0]
    frame.loc[row, 'gwl_current'] = 3.
    with pytest.raises(ValueError, match='provenance'):
        audit.validate_frame(frame, manifest, REGISTRY)


def test_future_backfill_or_extended_carry_rejected(data):
    frame, manifest = data
    row = frame.index[frame.gwl_current.isna()][0]
    frame.loc[row, ['gwl_current', 'GWL_current', 'months_since_observation']] = [3., 3., 1.]
    frame.loc[row, 'is_imputed'] = True
    with pytest.raises(ValueError, match='LOCF'):
        audit.validate_frame(frame, manifest, REGISTRY)


def test_calendar_lag_corruption_rejected(data):
    frame, manifest = data
    frame.loc[6, ['gwl_lag_3mo', 'GWL_lag_3mo']] = 99.
    with pytest.raises(ValueError, match='calendar shift'):
        audit.validate_frame(frame, manifest, REGISTRY)


def test_observed_age_and_imputed_carry_limit_rejected(data):
    frame, manifest = data
    frame.loc[0, 'months_since_observation'] = 1
    with pytest.raises(ValueError, match='zero observation age'):
        audit.validate_frame(frame, manifest, REGISTRY)
    frame, manifest = fixture_frame()
    frame.loc[1, 'months_since_observation'] = 4
    with pytest.raises(ValueError, match='carry policy'):
        audit.validate_frame(frame, manifest, REGISTRY)


def test_suspicious_depth_is_reported_without_clipping():
    frame, manifest = fixture_frame({'AA-A': {'2002-01-01': 106.156}})
    validated = audit.validate_frame(frame, manifest, REGISTRY)
    summary = audit.summarize_frame(validated)
    assert summary['observed_depths_above_100m'] == [
        {'district_id': 'AA-A', 'date': '2002-01-01', 'gwl_current': 106.156}]
    assert validated.loc[0, 'gwl_current'] == 106.156


def test_added_measurements_count_but_existing_measurements_take_precedence():
    baseline = checked(fixture_frame())
    candidate = checked(fixture_frame({'AA-A': {'2002-08-01': 4.}}))
    delta = audit.compare_measured(baseline, candidate)
    assert delta['added_observed_rows'] == 1 and delta['added_by_month'] == {'2002-08-01': 1}
    candidate.loc[0, 'gwl_current'] = 9.
    with pytest.raises(ValueError, match='measured values were changed'):
        audit.compare_measured(baseline, candidate)


def test_existing_measured_flag_cannot_be_removed():
    baseline = checked(fixture_frame())
    candidate = baseline.copy()
    candidate.loc[0, 'is_observed'] = False
    with pytest.raises(ValueError, match='removed'):
        audit.compare_measured(baseline, candidate)


def test_pair_summary_only_joins_observed_endpoints_and_labels_its_limit():
    baseline = checked(fixture_frame())
    candidate = checked(fixture_frame({'AA-A': {'2002-08-01': 4.}}))
    summary = audit.calendar_pair_summary(candidate, baseline)
    assert 'not final XGBoost training counts' in summary['scope']
    assert summary['training_pairs_with_added_targets'] > 0
    assert summary['distinct_added_months_used_in_either_role'] == 1
    assert summary['january_2026_target_pair_counts_by_horizon'] == {}


def test_audit_api_is_read_only_and_proves_added_target_source_values(tmp_path, monkeypatch):
    import db.connection
    import preprocessing.official_enrichment as overlay

    baseline, baseline_manifest = fixture_frame()
    final, manifest = fixture_frame({'AA-A': {'2002-08-01': 4.}})
    candidate_dir = tmp_path / 'candidate'
    candidate_dir.mkdir()
    source = {'sources': [{'name': 'CGWB Manual Quarterly'}]}
    (candidate_dir / 'manifest.json').write_text(json.dumps(source))
    manifest['enrichment'] = {'candidate_manifest_sha256': audit.sha256_file(candidate_dir / 'manifest.json')}
    manifest['station_provenance_manifest'] = source
    assets = {}
    for name, frame, card in [('baseline', baseline, baseline_manifest), ('final', final, manifest)]:
        directory = tmp_path / name
        directory.mkdir()
        frame.to_csv(directory / 'features_matrix.csv', index=False)
        (directory / 'feature_manifest.json').write_text(json.dumps(card))
        frame.attrs = {'feature_manifest': card, 'data_sha256': 'fixture-physical-hash'}
        assets[directory] = frame
    monkeypatch.setattr(audit, 'load_feature_matrix', lambda directory: assets[Path(directory)])
    monkeypatch.setattr(audit, '_bundle_proof', lambda *args: {'model_sha256': 'fixture-original-model'})
    incoming = final.loc[final.is_observed, ['district_id', 'date', 'gwl_current']].rename(columns={'gwl_current': 'gwl_mean'})
    incoming['units'] = 'm_bgl'
    monkeypatch.setattr(overlay, 'read_candidate', lambda *args, **kwargs: (incoming, deepcopy(source)))

    def forbidden(*args, **kwargs):
        pytest.fail('Read-only data audit must not write files or access the database')

    monkeypatch.setattr(Path, 'write_text', forbidden)
    monkeypatch.setattr(Path, 'write_bytes', forbidden)
    monkeypatch.setattr(db.connection, 'get_connection', forbidden)
    report = audit.audit(tmp_path / 'final', tmp_path / 'baseline', registry_ids=REGISTRY,
                         candidate_directory=candidate_dir)
    assert report['references']['baseline']['final_comparison']['added_observed_rows'] == 1
    assert report['provenance']['observed_target_union_and_source_values_verified'] is True
    assert report['database_accessed'] is False and report['source_model_or_feature_files_written'] is False
    incoming.loc[incoming.date.eq('2002-08-01'), 'gwl_mean'] = 8.
    with pytest.raises(ValueError, match='accepted physical source aggregates'):
        audit.audit(tmp_path / 'final', tmp_path / 'baseline', registry_ids=REGISTRY, candidate_directory=candidate_dir)
