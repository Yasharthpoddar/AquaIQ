"""Candidate labels are genuine and features equal the causal serving encoding."""
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from models import enriched_training_data as training
from models.climate_forecast import feature_rows, origin_inputs
from models.climate_forecast_12m import FEATURES
from models.climate_inputs import forecast_weather
from models.monthly_projection import _design, fit_projection


def physical_frame():
    dates = pd.date_range('2012-01-01', '2019-12-01', freq='MS')
    sequence = np.arange(len(dates), dtype=float)
    frame = pd.DataFrame({'district_id': 'AA-One', 'date': dates,
        'gwl_current': 10. + sequence * .03 + np.sin(sequence),
        'rainfall_current': 100. + sequence * .1,
        'temperature': 18. + sequence * .017,
        'evapotranspiration': 30. + sequence * .13,
        'is_observed': True, 'is_imputed': False})
    frame['gwl_lag_3mo'] = frame.gwl_current.shift(3)
    frame['gwl_lag_6mo'] = frame.gwl_current.shift(6)
    frame.attrs.update(data_source='observed_schema_fixture',
        feature_generation_id='fixture-enriched-physical-generation')
    return frame


def serving_rows(frame, origin):
    """Reference the existing production lag-fallback and feature functions."""
    origin = pd.Timestamp(origin)
    cutoff = origin + pd.offsets.MonthEnd(0)
    prefix = frame.loc[frame.date.le(cutoff)].copy()
    known = prefix.loc[prefix.is_observed & ~prefix.is_imputed]
    fit = fit_projection(known, cutoff)
    lags = {}
    for lag in (3, 6):
        date = origin - pd.DateOffset(months=lag)
        values = prefix.loc[prefix.date.eq(date), 'gwl_current']
        value = float(values.iloc[0]) if len(values) else np.nan
        if not np.isfinite(value) and fit is not None:
            value = float(max(0., (_design([date], fit['origin'], fit['seasonal'])
                @ fit['coefficients'] + fit['level_offset'])[0]))
        lags[lag] = value
    depth = float(known.loc[known.date.eq(origin), 'gwl_current'].iloc[0])
    inputs, _ = origin_inputs(frame, origin, cutoff, depth, lags)
    weather = forecast_weather(frame, cutoff, months=12)
    assert weather['status'] == 'available'
    return feature_rows(origin, weather['path'], inputs)


def features_at(pairs, origin):
    rows = pairs.loc[pairs.origin_date.eq(pd.Timestamp(origin)), FEATURES].sort_values('horizon_months').reset_index(drop=True)
    rows.attrs = {}
    return rows


def test_features_exactly_equal_serving_month_end_encoding_at_multiple_origins():
    frame = physical_frame()
    # Current July must enter the same-calendar-month M+12 climatology.
    frame.loc[frame.date.eq('2017-07-01'), 'rainfall_current'] = 1000.
    # Missing origin temperature exercises origin_inputs' causal fallback.
    frame.loc[frame.date.eq('2016-04-01'), 'temperature'] = np.nan
    pairs = training.prepare_pairs(frame)
    for origin in ('2015-01-01', '2016-04-01', '2017-07-01'):
        expected = serving_rows(frame, origin).reset_index(drop=True)
        expected.attrs = {}
        pd.testing.assert_frame_equal(features_at(pairs, origin), expected, check_exact=True)
    assert set(pairs.horizon_months) == set(range(1, 13))
    assert list(pairs.columns) == training.PAIR_COLUMNS
    assert (pairs.target_delta == pairs.actual_gwl - pairs.origin_gwl).all()
    months = (pairs.target_date.dt.year - pairs.origin_date.dt.year) * 12 + pairs.target_date.dt.month - pairs.origin_date.dt.month
    assert months.eq(pairs.horizon_months).all()


def test_calendar_lags_override_stale_columns_and_match_production_projection_fallback():
    frame = physical_frame()
    frame[['gwl_lag_3mo', 'gwl_lag_6mo']] = 99999.
    for date in ('2015-10-01', '2016-01-01'):
        frame.loc[frame.date.eq(date), ['gwl_current', 'is_observed']] = [np.nan, False]
    pairs = training.prepare_pairs(frame)
    expected = serving_rows(frame, '2016-04-01').reset_index(drop=True)
    expected.attrs = {}
    actual = features_at(pairs, '2016-04-01')
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    assert np.isfinite(actual[['origin_gwl_lag_3mo', 'origin_gwl_lag_6mo']]).all().all()
    assert pairs.attrs['pair_audit']['origins_with_projection_lag_fallback'] > 0


def test_future_measurements_weather_and_output_columns_cannot_change_prior_features():
    original = physical_frame()
    changed = original.copy()
    future = changed.date.gt('2016-06-01')
    changed.loc[future, 'gwl_current'] += 50.
    changed.loc[future, 'rainfall_current'] = 9999.
    changed.loc[future, 'temperature'] = 55.
    changed.loc[future, 'evapotranspiration'] = 777.
    changed['predicted_gwl'] = 999999.
    changed['target_gwl_6mo'] = -12345.
    before = training.prepare_pairs(original)
    after = training.prepare_pairs(changed)
    pd.testing.assert_frame_equal(features_at(before, '2016-06-01'),
                                  features_at(after, '2016-06-01'), check_exact=True)
    # Rebuilding from a historical prefix gives the same earlier feature rows.
    prefix = original.loc[original.date.le('2016-06-01')].copy()
    prefix_pairs = training.prepare_pairs(prefix)
    pd.testing.assert_frame_equal(features_at(before, '2015-06-01'),
                                  features_at(prefix_pairs, '2015-06-01'), check_exact=True)


def test_imputed_and_nonobserved_depths_never_become_origins_or_targets():
    frame = physical_frame()
    missing = frame.date.eq('2017-01-01')
    frame.loc[missing, ['gwl_current', 'is_observed', 'is_imputed']] = [2000., False, True]
    pairs = training.prepare_pairs(frame)
    assert not pairs.origin_date.eq('2017-01-01').any()
    assert not pairs.target_date.eq('2017-01-01').any()
    assert not pairs.actual_gwl.eq(2000.).any()


def test_sparse_observed_origins_keep_native_nan_lags_without_fabricated_fit():
    frame = physical_frame()
    frame['is_observed'] = frame.date.isin(pd.to_datetime(['2016-01-01', '2017-01-01']))
    frame.loc[~frame.is_observed, 'gwl_current'] = np.nan
    pairs = training.prepare_pairs(frame)
    assert len(pairs) == 1 and pairs.iloc[0].horizon_months == 12
    assert pairs[['origin_gwl_lag_3mo', 'origin_gwl_lag_6mo']].isna().all().all()
    assert pairs.attrs['pair_audit']['origins_without_fit_retaining_native_nan_lags'] == 1


def test_builder_does_not_mutate_input_and_preserves_identity_and_audit():
    frame = physical_frame()
    before = frame.copy(deep=True)
    identity = deepcopy(frame.attrs)
    pairs = training.prepare_pairs(frame)
    pd.testing.assert_frame_equal(frame, before, check_exact=True)
    assert frame.attrs == identity
    assert pairs.attrs['feature_generation_id'] == identity['feature_generation_id']
    assert pairs.attrs['data_source'] == identity['data_source']
    audit = pairs.attrs['pair_audit']
    assert audit['pair_rows'] == len(pairs)
    assert sum(audit['pairs_by_horizon'].values()) == len(pairs)
    assert audit['observed_rows'] == len(frame)


@pytest.mark.parametrize('name,value', [('is_observed', 'maybe'), ('is_imputed', None)])
def test_unknown_observation_flags_fail_closed(name, value):
    frame = physical_frame()
    frame[name] = frame[name].astype(object)
    frame.loc[0, name] = value
    with pytest.raises(ValueError, match='Unknown observation provenance'):
        training.prepare_pairs(frame)


@pytest.mark.parametrize('value', [np.nan, np.inf, -1.])
def test_invalid_observed_depths_fail_closed(value):
    frame = physical_frame()
    frame.loc[0, 'gwl_current'] = value
    with pytest.raises(ValueError, match='finite nonnegative'):
        training.prepare_pairs(frame)


def test_duplicate_keys_and_conflicting_flags_fail_closed():
    frame = physical_frame()
    repeated = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    repeated.attrs = frame.attrs.copy()
    with pytest.raises(ValueError, match='Duplicate'):
        training.prepare_pairs(repeated)
    frame.loc[0, 'is_imputed'] = True
    with pytest.raises(ValueError, match='both observed and imputed'):
        training.prepare_pairs(frame)


@pytest.mark.parametrize('source', ['unknown', 'synthetic', 'forecast_model_output'])
def test_unidentified_or_synthetic_data_source_is_rejected(source):
    frame = physical_frame()
    frame.attrs['data_source'] = source
    with pytest.raises(ValueError, match='identified real'):
        training.prepare_pairs(frame)


def test_explicit_synthetic_source_cannot_be_marked_observed():
    frame = physical_frame()
    frame['source_type'] = 'official_manual'
    frame.loc[0, 'source_type'] = 'synthetic_forecast'
    with pytest.raises(ValueError, match='Synthetic or predicted'):
        training.prepare_pairs(frame)


def test_districts_never_share_labels_or_calendar_lags():
    first = physical_frame()
    second = first.copy()
    second['district_id'] = 'BB-Two'
    second['gwl_current'] += 50.
    together = pd.concat([second, first], ignore_index=True)
    together.attrs = first.attrs.copy()
    pairs = training.prepare_pairs(together)
    a = pairs.loc[pairs.district_id.eq('AA-One')].reset_index(drop=True)
    b = pairs.loc[pairs.district_id.eq('BB-Two')].reset_index(drop=True)
    np.testing.assert_allclose(b.actual_gwl - a.actual_gwl, 50.)
    np.testing.assert_allclose(b.origin_gwl - a.origin_gwl, 50.)
    np.testing.assert_allclose(b.origin_gwl_lag_3mo - a.origin_gwl_lag_3mo, 50.)


def test_no_available_observed_pair_returns_empty_inventory_with_audit():
    frame = physical_frame()
    frame['is_observed'] = False
    frame.loc[0, 'is_observed'] = True
    pairs = training.prepare_pairs(frame)
    assert pairs.empty and list(pairs) == training.PAIR_COLUMNS
    assert pairs.attrs['pair_audit']['pair_rows'] == 0
