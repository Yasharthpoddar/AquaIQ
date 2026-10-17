"""Regressions for the audit's model contracts and comparable evaluation."""
import json

import numpy as np
import pandas as pd
import pytest

from models import audit_evaluation as audit
from models import climate_forecast as climate
from models import data_readiness
from models import plot_predictions
from models import statistical_tests
from models import xgboost_model as forecast


def physical_frame():
    dates = pd.date_range('2010-01-01', '2024-12-01', freq='MS')
    depth = 10. + np.arange(len(dates)) * .1
    frame = pd.DataFrame({'district_id': 'fixture', 'date': dates, 'gwl_current': depth,
        'gwl_lag_3mo': pd.Series(depth).shift(3), 'gwl_lag_6mo': pd.Series(depth).shift(6),
        'rainfall_current': 100., 'rainfall_3mo_avg': 100., 'monsoon_deficit_pct': 0.,
        'temperature': 25., 'evapotranspiration': 90., 'water_balance_proxy': 10.,
        'crop_season_flag': 'Rabi', 'is_observed': True, 'is_imputed': False})
    frame.attrs.update(feature_generation_id='physical-fixture', data_source='real-schema-fixture')
    return frame


@pytest.mark.parametrize('field,value', [
    ('max_train_target_date', '2020-01-01'),
    ('max_train_target_date', None), ('max_train_origin', None),
    ('max_train_origin', '2019-12-01'), ('train_target_cutoff', 'NaT'),
])
def test_rehashed_direct_card_cannot_hide_training_date_violation(tmp_path, field, value):
    frame = forecast.create_target(forecast.encode_crop_season(physical_frame()))
    model = forecast.new_model({'n_estimators': 2, 'max_depth': 1, 'n_jobs': 1})
    training = frame.loc[frame.target_date <= '2019-12-31']
    model.fit(training[forecast.CANONICAL_FEATURE_COLS], training.target_gwl_6mo)
    card = {'features': forecast.CANONICAL_FEATURE_COLS,
        'feature_schema_sha256': forecast._json_hash(forecast.CANONICAL_FEATURE_COLS),
        'units': forecast.FEATURE_UNITS, 'horizon_months': 6,
        'feature_generation_id': 'physical-fixture', 'data_source': 'real-schema-fixture',
        'train_target_cutoff': '2019-12-31', 'max_train_target_date': '2019-12-01',
        'max_train_origin': '2019-06-01'}
    checkpoint = tmp_path / 'model.json'
    forecast.publish_model_bundle(model, card, checkpoint)
    pointer = json.loads(checkpoint.read_text())
    path = checkpoint.parent / pointer['card_path']
    stored = json.loads(path.read_text())
    stored[field] = value
    path.write_text(json.dumps(stored), encoding='utf-8')
    pointer['card_sha256'] = forecast.sha256_file(path)
    checkpoint.write_text(json.dumps(pointer), encoding='utf-8')
    with pytest.raises(ValueError, match='training dates'):
        forecast.load_model_bundle(checkpoint)


def test_monthly_baseline_uses_latest_known_season_even_if_input_is_unsorted():
    frame = physical_frame()
    labels = climate.prepare_pairs(frame)
    labels = labels.loc[labels.origin_date == pd.Timestamp('2022-01-01')]
    class Predictor:
        def predict(self, values):
            return np.zeros(len(values))
    expected = climate.evaluate_assumed_weather(Predictor(), frame, labels)
    actual = climate.evaluate_assumed_weather(Predictor(), frame.iloc[::-1], labels)
    assert expected == actual
    assert actual['by_district']['fixture']['n'] == 6
    assert actual['origin_start'] == '2022-01-01'


def test_readiness_compatibility_reuses_serving_observed_rounds(monkeypatch):
    captured = []
    def select(district, as_of):
        captured.append((district, as_of))
        return {'readiness': {'observed_months': 60, 'expected_monitoring_rounds': 99,
                             'readiness_score': 60.6, 'eligible': True},
                'estimate_type': 'district_level', 'zone': None,
                'frame': pd.DataFrame()}
    monkeypatch.setattr(data_readiness, 'select_evidence', select)
    result = data_readiness.get_data_readiness('fixture', '2026-09-30')
    assert captured == [('fixture', '2026-09-30')]
    assert result['readiness_score'] == 60.6
    assert result['cgwb_months'] == result['observed_months'] == 60
    assert result['is_zone_fallback'] is False


def test_readiness_query_failure_is_not_misreported_as_zero(monkeypatch):
    def unavailable(*args):
        raise RuntimeError('Database unavailable')
    monkeypatch.setattr(data_readiness, 'select_evidence', unavailable)
    with pytest.raises(RuntimeError, match='Database unavailable'):
        data_readiness.get_data_readiness('fixture')


def test_candidate_imputer_fit_and_selection_cannot_use_validation_or_test():
    frame = physical_frame()
    class Candidate:
        def fit(self, values, target):
            self.maximum_training_depth = values.gwl_current.max()
            self.training_targets = np.asarray(target)
        def predict(self, values):
            return values.gwl_current.to_numpy()
    candidate, saved = Candidate(), Candidate()
    card = {'train_target_cutoff': '2019-12-31', 'bundle_id': 'fixture', 'model_sha256': 'fixture'}
    report, cases = audit.compare_direct(frame, saved, card, {'candidate': candidate})
    prepared = forecast.create_target(forecast.encode_crop_season(frame))
    train, validation, test = audit.comparison_splits(prepared, '2019-12-31')
    assert train.target_date.max() <= pd.Timestamp('2019-12-31')
    assert validation.date.min() >= pd.Timestamp('2020-07-01')
    assert validation.target_date.max() < pd.Timestamp('2023-01-01')
    assert test.target_date.min() >= pd.Timestamp('2023-01-01')
    assert candidate.maximum_training_depth == train.gwl_current.max()
    np.testing.assert_array_equal(candidate.training_targets, train.target_gwl_6mo)
    assert set(cases.split) == {'validation', 'test'}
    # This deliberately makes the validation winner the test loser.
    validation_cases = pd.DataFrame({'actual': [10., 10.], 'good': [10., 10.], 'bad': [20., 20.]})
    test_cases = pd.DataFrame({'actual': [10., 10.], 'good': [20., 20.], 'bad': [10., 10.]})
    assert audit.select_on_validation(validation_cases, ['good', 'bad']) == 'good'
    assert audit.select_on_validation(test_cases, ['good', 'bad']) == 'bad'
    assert report['selected_by_validation'] in {'saved_xgboost', 'persistence', 'candidate'}


def test_auxiliary_statistics_and_plot_loaders_exclude_imputed_depths(monkeypatch):
    frame = physical_frame()
    frame.loc[0, ['is_observed', 'is_imputed', 'gwl_current']] = [False, True, 900.]
    monkeypatch.setattr(forecast, 'load_feature_matrix', lambda: frame)
    stats = statistical_tests.load_gwl_data()
    plot = plot_predictions.load_data()
    assert len(stats) == len(plot) == len(frame) - 1
    assert 900. not in stats.GWL_current.to_numpy()
    assert 900. not in plot.GWL_current.to_numpy()
    assert 'GWL_current' in plot  # Physical lowercase schema previously produced blank plots.


def test_annual_rates_require_adjacent_years_and_matching_observed_months():
    frame = pd.DataFrame({'district_id': ['fixture'] * 5,
        'date': pd.to_datetime(['2018-01-01', '2018-05-01', '2019-01-01', '2021-01-01', '2021-08-01']),
        'GWL_current': [10., 30., 11., 15., 50.]})
    annual = statistical_tests.compute_depletion_rate(frame).set_index('year')
    assert annual.loc[2019, 'gwl_change'] == 1.  # May cannot shift January's annual comparison.
    assert annual.loc[2019, 'compared_months'] == 1
    assert pd.isna(annual.loc[2021, 'gwl_change'])  # A two-year gap cannot be a one-year rate.


def test_statistical_test_counts_districts_instead_of_repeated_years(monkeypatch):
    observed = {}
    def paired(recent, baseline, **kwargs):
        observed['n'] = len(recent)
        return 1., .25
    monkeypatch.setattr(statistical_tests.stats, 'ttest_rel', paired)
    annual = pd.DataFrame({'district_id': ['a'] * 4 + ['b'] * 4,
        'year': [2008, 2009, 2021, 2022] * 2, 'gwl_change': [0., .2, .4, .6, .1, .3, .5, .7]})
    result = statistical_tests.run_ttest(annual)
    assert observed['n'] == result['paired_districts'] == 2
    assert result['units'] == 'm/year'


def test_auxiliary_ann_does_not_create_random_validation_holdout(monkeypatch):
    from models import ann_classifier as ann
    captured = {}
    class Imitation:
        n_iter_ = 1
        def __init__(self, **settings):
            captured.update(settings)
        def fit(self, values, labels):
            self.label = labels[0]
        def predict(self, values):
            return np.repeat(self.label, len(values))
    monkeypatch.setattr(ann, 'MLPClassifier', Imitation)
    monkeypatch.setattr(ann, 'generate_fuzzy_labels', lambda frame: pd.Series('Safe', index=frame.index))
    ann.train_ann(physical_frame(), max_iter=2)
    assert captured['early_stopping'] is False
    assert 'validation_fraction' not in captured
