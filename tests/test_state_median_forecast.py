"""Synthetic fixtures test mathematics and leakage, never represent real evidence."""
import numpy as np
import pandas as pd
import pytest

from models import state_median_forecast as median


REGISTRY = [dict(district_id=f'TN-{name}', state_id='TN') for name in ('A', 'B', 'C', 'D')]


def source(rows):
    return pd.DataFrame([dict(district_id=d, date=date, gwl_current=v, is_observed=obs, is_imputed=False)
                         for d, date, v, obs in rows])


def test_median_balances_districts_deduplicates_and_keeps_missing_calendar():
    frame = source([('TN-A','2010-01-01',2,True), ('TN-A','2010-01-01',2,True),
        ('TN-A','2010-01-15',6,True), ('TN-B','2010-01-01',10,True),
        ('TN-C','2010-01-01',100,True), ('TN-D','2010-03-01',np.nan,True),
        ('TN-D','2010-03-01',5,False)])
    h = median.build_state_history(frame, REGISTRY)
    jan, feb, mar = h.iloc[0], h.iloc[1], h.iloc[2]
    assert jan.gwl_m_bgl == 10  # median([mean(2,6),10,100]), not mean/readings median
    assert jan.contributing_districts_count == 3 and jan.observation_count == 4
    assert jan.coverage_ratio == .75 and jan.training_eligible
    assert pd.isna(feb.gwl_m_bgl) and not feb.training_eligible and feb.observation_quality == 'missing'
    assert pd.isna(mar.gwl_m_bgl)


def test_low_coverage_is_retained_but_not_a_target_and_flags_fail_closed():
    f = source([('TN-A','2010-01-01',4,True), ('TN-B','2010-02-01',0,True),
                ('TN-C','2010-02-01',8,True), ('TN-D','2010-02-01',100,True)])
    f.loc[3, 'is_imputed'] = True
    h = median.build_state_history(f, REGISTRY)
    assert h.iloc[0].gwl_m_bgl == 4 and not h.iloc[0].training_eligible
    assert h.iloc[1].gwl_m_bgl == 4 and h.iloc[1].training_eligible  # zero is a valid measurement
    assert h.iloc[1].observation_count == 2
    with pytest.raises(ValueError, match='min_coverage'):
        median.build_state_history(f, REGISTRY, 0)
    with pytest.raises(ValueError, match='unregistered'):
        median.build_state_history(f.assign(district_id='UP-Unknown'), REGISTRY)
    with pytest.raises(ValueError, match='disagrees'):
        median.build_state_history(f.assign(state_id='UP'), REGISTRY)


@pytest.fixture
def history():
    dates = pd.date_range('2010-01-01', '2021-12-01', freq='MS')
    f = source([(d['district_id'], date, 8+np.sin(date.month*np.pi/6)+(date.year-2010)*.08+i, True)
        for i, d in enumerate(REGISTRY) for date in dates])
    f['rainfall_current'] = f.date.dt.month * 10.
    f.attrs.update(feature_generation_id='test-only', data_sha256='fixture')
    return median.build_state_history(f, REGISTRY)


def test_lags_rolling_and_climate_cannot_see_future_or_other_state(history):
    origin = pd.Timestamp('2015-06-01')
    before = median.state_features(history, origin, 12)
    changed = history.copy()
    changed.loc[changed.date.ge(origin), ['gwl_m_bgl','rainfall_current']] = 999999
    after = median.state_features(changed, origin, 12)
    np.testing.assert_allclose(list(before.values()), list(after.values()), equal_nan=True)
    assert before['lag_1'] == history.loc[history.date.eq('2015-05-01'), 'gwl_m_bgl'].iloc[0]
    assert before['rainfall_current_lag1'] == 50
    window = history.loc[history.date.between('2015-03-01','2015-05-01'), 'gwl_m_bgl']
    assert before['rolling_median_3'] == window.median()
    with pytest.raises(ValueError, match='one unique state'):
        median.state_features(pd.concat([history, history.assign(state_id='UP')]), origin, 1)


def test_training_targets_respect_cutoff_and_features_are_origin_limited(history):
    examples = median.training_examples(history, '2019-12-31')
    assert examples.target_date.max() == pd.Timestamp('2019-12-01')
    assert (examples.origin < examples.target_date).all()
    mutated = history.copy()
    mutated.loc[mutated.date.gt('2019-12-01'), 'gwl_m_bgl'] = 100000
    pd.testing.assert_frame_equal(examples, median.training_examples(mutated, '2019-12-31'))


def test_train_reload_twelve_month_forecast_and_metadata(history, tmp_path):
    models, card = median.train_state_models(history, tmp_path/'models', '2019-12-31')
    assert set(models) == {'TN'}
    assert card['states']['TN']['validation']['role'] == 'development_diagnostic_only_not_test_accuracy'
    assert card['initial_fit_target_cutoff'] == '2016-12-01'
    assert card['states']['TN']['last_training_target'] <= card['training_cutoff']
    result = median.forecast_state('Tamil Nadu', history, models, card, '2021-10-29')
    assert result['status'] == 'forecast' and result['promotion_status'] == 'experimental'
    assert result['forecast'][0]['target_date'] == '2021-11-01'
    assert result['forecast'][-1]['target_date'] == '2022-10-01'
    assert len(result['forecast']) == 12 and result['history'][-1]['date'] == '2021-09-01'
    assert result['model_version'] == median.MODEL_VERSION and result['evaluation']['mae_m'] is None
    assert all(r['predicted_gwl'] >= 0 for r in result['forecast'])
    bad = dict(card, data_sha256='wrong')
    assert median.forecast_state('TN', history, models, bad, '2021-10-29')['status'] == 'model_unavailable'
    stale = median.forecast_state('TN', history, models, card, '2026-10-29')
    assert stale['status'] == 'insufficient_data' and not stale['forecast']
    assert 'last 12 months' in stale['message']
    model_path = tmp_path/'models'/'TN.json'
    model_path.write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        median.load_models(tmp_path/'models')


def test_insufficient_history_has_no_fabricated_forecast(history, tmp_path):
    short = history.iloc[:12].copy()
    models, card = median.train_state_models(short, tmp_path/'short', '2019-12-31', '2010-06-01')
    assert not models
    result = median.forecast_state('TN', short, models, card, '2021-10-29')
    assert result['status'] == 'insufficient_data' and not result['forecast']


def test_partial_month_excludes_future_readings_and_extends_missing_calendar():
    f = source([('TN-A','2021-01-01',4,True),('TN-B','2021-01-01',8,True),
                ('TN-A','2021-03-20',100,True)])
    h = median.build_state_history(f, REGISTRY, as_of='2021-03-10')
    assert list(h.date) == [pd.Timestamp('2021-01-01'),pd.Timestamp('2021-02-01')]
    assert pd.isna(h.iloc[-1].gwl_m_bgl)


def test_even_median_validity_flags_and_district_month_mean():
    f = source([('TN-A', '2010-01-01', 2, True), ('TN-A', '2010-01-15', 6, True),
                ('TN-B', '2010-01-01', 10, True), ('TN-C', '2010-01-01', -4, True),
                ('TN-D', '2010-01-01', np.inf, True)])
    assert median.build_state_history(f, REGISTRY).iloc[0].gwl_m_bgl == 7
    f['is_observed'] = 'unknown'
    assert not median.build_state_history(f, REGISTRY).training_eligible.any()
    f = f.drop(columns=['is_observed', 'is_imputed'])
    assert median.build_state_history(f, REGISTRY).gwl_m_bgl.isna().all()


def test_short_dense_series_fails_span_requirement(history, tmp_path):
    short = history.iloc[:36].copy()
    models, card = median.train_state_models(short, tmp_path/'dense', '2019-12-31', '2011-06-01')
    assert not models
    assert card['states']['TN']['observed_months'] == 36
    assert card['states']['TN']['span_months'] == 36


def test_training_and_serving_features_match_for_partial_month_origin(history):
    origin = pd.Timestamp('2016-09-01')
    examples = median.training_examples(history, '2017-12-31')
    trained = examples.loc[examples.origin.eq(origin) & examples.horizon.eq(1), median.FEATURES].iloc[0]
    available = history.loc[history.date.lt(origin)]
    serving = pd.Series(median.state_features(available, origin, 1))[median.FEATURES]
    np.testing.assert_allclose(trained.to_numpy(float), serving.to_numpy(float), equal_nan=True)
