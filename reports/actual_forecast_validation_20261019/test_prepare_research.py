"""Synthetic unit fixtures for the offline adapter, never shadow records."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MODULE = Path(__file__).with_name('prepare_research.py')
spec = importlib.util.spec_from_file_location('aquaiq_actual_research_prepare', MODULE)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def raw_row(well='1001', date='01-01-2024', depth='4', **changes):
    row = {'Well ID': well, 'State Name (as per LGD)': 'Telangana',
        'District Name (as per LGD)': 'ADILABAD', 'Block Name (as per LGD)': 'Block',
        'Village (as per LGD, if available)': 'Village', 'Site Name': 'Site',
        'Latitude': '19.66', 'Longitude': '78.52', 'Well Type': 'Peizometer',
        'Well Depth, m': '30', 'Aquifer Tapped (Unconfined, Semi-Confined, Confined)': 'Unconfined',
        'Agency': 'SGWD-Telangana', 'Date': date, 'Water Level in mbgl': depth}
    row.update(changes)
    return row


def test_conflicting_month_not_averaged_and_exact_duplicate_explicit():
    raw = pd.DataFrame([raw_row(depth='4'), raw_row(depth='5'),
        raw_row('1002', depth='7'), raw_row('1002', depth='7')])
    audited, _ = adapter.audit_rows(raw)
    assert audited.loc[:1, 'exclusion_reason'].str.contains('conflicting_well_month_depths').all()
    accepted = audited.loc[audited.exclusion_reason.eq('')]
    assert accepted.provider_well_id.tolist() == ['1002']
    assert audited.loc[3, 'exclusion_reason'] == 'exact_duplicate_well_month'


@pytest.mark.parametrize('missing', ['', 'Dry', '?', '-', None, np.nan])
def test_nonnumeric_depths_are_rejected_after_nullable_string_coercion(missing):
    audited, _ = adapter.audit_rows(pd.DataFrame([raw_row(depth=missing)]))
    assert audited.gwl_m_bgl.dtype == np.dtype('float64')
    assert np.isnan(audited.gwl_m_bgl.iloc[0])
    assert 'nonfinite_depth' in audited.exclusion_reason.iloc[0]
    assert not audited.exclusion_reason.eq('').any()


@pytest.mark.parametrize('coordinates', [
    {'Latitude': ''}, {'Latitude': np.nan}, {'Longitude': None},
    {'Longitude': '?'}, {'Latitude': '-', 'Longitude': 'Dry'},
])
def test_missing_coordinates_are_rejected_instead_of_nullable_unknown(coordinates):
    audited, _ = adapter.audit_rows(pd.DataFrame([raw_row(**coordinates)]))
    assert audited.latitude.dtype == np.dtype('float64')
    assert audited.longitude.dtype == np.dtype('float64')
    assert 'invalid_india_coordinates' in audited.exclusion_reason.iloc[0]
    assert not audited.exclusion_reason.eq('').any()


def test_metadata_changes_do_not_remove_past_rows_but_conflicted_month_rejected():
    raw = pd.DataFrame([raw_row(), raw_row(date='01-02-2024', Latitude='19.67'),
        raw_row('1002', Latitude='19.66'), raw_row('1002', Latitude='19.67')])
    audited, diagnostics = adapter.audit_rows(raw)
    assert audited.loc[:1, 'exclusion_reason'].eq('').all()
    assert diagnostics['provider_ids_with_cross_time_metadata_variation'] == 2
    assert audited.loc[2:, 'exclusion_reason'].str.contains('conflicting_well_month_metadata').all()


def test_explicit_day_first_dates_unknown_availability_and_all_aquifers():
    audited, _ = adapter.audit_rows(pd.DataFrame([raw_row(date='02-03-2024', **{
        'Aquifer Tapped (Unconfined, Semi-Confined, Confined)': 'Semi-Confined/Confined'})]))
    assert audited.loc[0, 'reported_observation_date'] == pd.Timestamp('2024-03-02')
    assert audited.loc[0, 'date'] == pd.Timestamp('2024-03-01')
    assert audited.exclusion_reason.eq('').all()
    assert audited[['actual_acquisition_at', 'first_publication_at', 'first_received_at', 'available_at']].isna().all().all()
    with pytest.raises(ValueError, match='Explicit mbgl'):
        adapter.audit_rows(pd.DataFrame([raw_row()]).drop(columns='Water Level in mbgl'))


def test_monthly_equal_weights_panels_order_invariant_and_no_conflicts():
    audited, _ = adapter.audit_rows(pd.DataFrame([raw_row('1001', depth='4'), raw_row('1002', depth='8')]))
    audited['district_id'] = 'TS-SYNTHETIC_TEST'
    monthly, panel = adapter.aggregate_monthly(audited)
    reordered, _ = adapter.aggregate_monthly(audited.iloc[::-1])
    assert monthly.gwl.tolist() == [6.0]
    assert panel.weight.tolist() == [0.5, 0.5]
    assert panel.provider_well_id.tolist() == ['1001', '1002']
    assert monthly.panel_sha256.tolist() == reordered.panel_sha256.tolist()
    with pytest.raises(ValueError, match='duplicate well-months'):
        adapter.aggregate_monthly(pd.concat([audited, audited.iloc[:1]]))


def monthly_fixture():
    return pd.DataFrame({'district_id': ['TS-SYNTHETIC_TEST'] * 3,
        'date': pd.to_datetime(['2024-01-01', '2024-06-01', '2024-07-01']), 'gwl': [4., 8., 12.],
        'well_count': [1, 1, 1], 'panel_sha256': ['p', 'p', 'p']})


def weather_fixture():
    dates = pd.date_range('2024-01-01', '2024-08-01', freq='MS')
    weather = pd.DataFrame({'district_id': 'TS-SYNTHETIC_TEST', 'date': dates})
    for number, name in enumerate(adapter.WEATHER):
        weather[name] = float(number)
    return weather


def test_future_perturbation_cannot_change_past_fills_lags_or_weather():
    monthly = monthly_fixture()
    weather = weather_fixture()
    before = adapter.build_research_features(monthly, weather, end='2024-08-01')
    monthly.loc[monthly.date >= '2024-06-01', 'gwl'] = [1000., 9000.]
    weather.loc[weather.date >= '2024-06-01', adapter.WEATHER] = 1234.
    after = adapter.build_research_features(monthly, weather, end='2024-08-01')
    prefix = before.date < '2024-06-01'
    pd.testing.assert_frame_equal(before.loc[prefix], after.loc[prefix])
    assert before.loc[before.date.eq('2024-04-01'), 'gwl_current'].item() == 4.
    assert np.isnan(before.loc[before.date.eq('2024-05-01'), 'gwl_current'].item())
    assert before.loc[before.date.eq('2024-04-01'), 'gwl_lag_3mo'].item() == 4.
    assert before.loc[before.date.eq('2024-07-01'), 'gwl_lag_6mo'].item() == 4.


def test_weather_missingness_copied_and_calendar_target_is_exact():
    monthly = monthly_fixture()
    weather = weather_fixture()
    weather.loc[weather.date.eq('2024-01-01'), 'temperature'] = np.nan
    features = adapter.build_research_features(monthly, weather, end='2024-08-01')
    assert np.isnan(features.loc[features.date.eq('2024-01-01'), 'temperature'].item())
    target = adapter.forecast.create_target(features)
    jan = target.loc[target.date.eq('2024-01-01')].iloc[0]
    assert jan.target_date == pd.Timestamp('2024-07-01')
    assert jan.target_gwl_6mo == 12.
    assert jan.target_is_observed
    # A finite carried-forward target must never become an observed label.
    feb = target.loc[target.date.eq('2024-02-01')].iloc[0]
    assert feb.target_date == pd.Timestamp('2024-08-01')
    assert not feb.target_is_observed


def test_spatial_ambiguity_not_snapped_and_wrong_state_rejected():
    import geopandas as gpd
    from shapely.geometry import Polygon
    boundaries = gpd.GeoDataFrame({'district': ['One', 'Two'], 'st_nm': ['Telangana', 'Maharashtra']},
        geometry=[Polygon([(78, 19), (79, 19), (79, 20), (78, 20)]),
                  Polygon([(79, 19), (80, 19), (80, 20), (79, 20)])], crs='EPSG:4326')
    crosswalk = pd.DataFrame({'legacy_district_id': ['1', '2'],
        'canonical_district_id': ['TS-One', 'MH-Two'], 'canonical_name': ['One', 'Two'],
        'canonical_state': ['Telangana', 'Maharashtra']})
    raw = pd.DataFrame([raw_row(Longitude='79', Latitude='19.5'),
        raw_row('1002', Longitude='79.5', Latitude='19.5')])
    audited, _ = adapter.audit_rows(raw)
    mapped = adapter.map_districts(audited, crosswalk, boundaries)
    assert mapped.loc[0, 'mapping_basis'] == 'ambiguous_boundary'
    assert 'unresolved_or_ambiguous' in mapped.loc[0, 'exclusion_reason']
    assert 'source_state_disagrees' in mapped.loc[1, 'exclusion_reason']


def test_existing_output_rejected_before_any_read_or_write():
    # A real existing run directory must be rejected before opening the input.
    with pytest.raises(ValueError, match='new, absent'):
        adapter.prepare(adapter.RUN / 'missing.csv', adapter.RUN)
