"""Coverage and inventory regressions: measured months, identities and duplicates."""
from pathlib import Path
import pandas as pd
import pytest
from data_ingestion import data_completeness as coverage
from scripts.audit_data_quality import audit_csv, district_series


@pytest.fixture
def mapping():
    return coverage.canonical_mapping(pd.DataFrame({
        'legacy_district_id': ['7', '8', '9'],
        'canonical_district_id': ['BR-Aurangabad', 'MH-Aurangabad', 'RJ-Jaipur'],
        'canonical_name': ['Aurangabad', 'Aurangabad', 'Jaipur'],
        'canonical_state': ['Bihar', 'Maharashtra', 'Rajasthan']}))


def test_study_months_uses_inclusive_configured_boundaries():
    assert len(coverage.study_months({'date_range': {'start': '2020-12-01', 'end': '2021-02-28'}})) == 3
    assert coverage.EXPECTED_MONTHS == 297


def test_source_coverage_counts_only_distinct_finite_months_in_window(tmp_path, mapping):
    path = tmp_path / 'cgwb.csv'
    pd.DataFrame({'district_code': ['7'] * 6 + ['unknown'],
                  'date': ['2020-01-01', '2020-01-20', '2020-02-01', '2020-03-01', 'bad', '1999-01-01', '2020-01-01'],
                  'currentlevel': ['8', '9', 'inf', '', '9', '8', '7']}).to_csv(path, index=False)
    report = coverage._coverage(path, 'cgwb', mapping,
                               {'date_range': {'start': '2020-01-01', 'end': '2020-03-31'}})
    assert report.to_dict('records') == [{'district_id': 'BR-Aurangabad', 'cgwb_months': 1}]
    diagnostics = report.attrs['diagnostics']
    assert diagnostics['invalid_date_rows'] == 1
    assert diagnostics['nonfinite_or_missing_rows'] == 2
    assert diagnostics['unmapped_rows'] == 1
    assert diagnostics['outside_study_rows'] == 1


def test_weather_names_do_not_join_different_states(tmp_path, mapping):
    path = tmp_path / 'rainfall.csv'
    pd.DataFrame({'district': ['Aurangabad'] * 4, 'st_nm': ['Bihar', 'Bihar', 'Maharashtra', 'Rajasthan'],
                  'year': [2020] * 4, 'month': [1, 1, 2, 1], 'rainfall_mm': [5, 5, 6, 7]}).to_csv(path, index=False)
    report = coverage._coverage(path, 'imd', mapping,
                               {'date_range': {'start': '2020-01-01', 'end': '2020-02-29'}})
    assert dict(zip(report.district_id, report.imd_months)) == {'BR-Aurangabad': 1, 'MH-Aurangabad': 1}
    assert report.attrs['diagnostics']['unmapped_rows'] == 1


def test_missing_sources_still_retain_every_canonical_district(tmp_path, mapping, monkeypatch):
    monkeypatch.setattr(coverage, 'DATA_RAW', tmp_path)
    monkeypatch.setattr(coverage, 'PROCESSED_DIR', tmp_path)
    result = coverage.compute_report(mapping[0])
    assert len(result) == 3
    assert result[['cgwb_months', 'imd_months', 'era5_months']].eq(0).all().all()
    assert not result.attrs['source_diagnostics']['cgwb']['available']


def test_csv_audit_finds_duplicates_across_chunks_and_nonfinite_values(tmp_path, mapping):
    path = tmp_path / 'features.csv'
    pd.DataFrame({'district_id': ['BR-Aurangabad'] * 4,
                  'date': ['2020-01-01', '2020-02-01', '2020-01-01', 'bad'],
                  'gwl_current': ['8', 'inf', '8', 'invalid'],
                  'is_observed': [True, False, True, False],
                  'is_imputed': [False] * 4}).to_csv(path, index=False)
    before = path.read_bytes()
    result = audit_csv(path, mapping, root=tmp_path, as_of='2026-10-17', chunksize=2)
    assert result['rows'] == 4 and result['duplicate_rows'] == 1
    assert result['monthly_key_duplicate_rows'] == 1
    assert result['invalid_date_rows'] == 1
    assert result['numeric']['gwl_current']['nonfinite'] == 1
    assert result['numeric']['gwl_current']['invalid_numeric'] == 1
    assert result['missing_pct']['gwl_current'] == 0
    assert path.read_bytes() == before


@pytest.mark.parametrize('name,state', [('District','State'),('district_name','state_name'),('district','state')])
def test_station_export_identity_schemas_retain_state(name, state, mapping):
    frame = pd.DataFrame({name: ['Aurangabad','Aurangabad'], state: ['Bihar','Maharashtra']})
    ids, _ = district_series(frame, mapping)
    assert ids.tolist() == ['BR-Aurangabad','MH-Aurangabad']
