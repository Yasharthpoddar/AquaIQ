"""F6 reporting regressions: fixed arrays only, never estimator fitting."""
import numpy as np
import pandas as pd
import pytest

from models import linear_regression as linear
from models import xgboost_model as forecast


@pytest.fixture(autouse=True)
def forbid_training_and_production_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Reporting tests must not fit, forecast, load datasets or access a database.')
    for owner, name in [(linear.LinearRegression, 'fit'), (linear.LinearRegression, 'predict'),
                        (linear, 'train_per_district'), (linear, 'load_features'),
                        (linear, 'get_connection'), (forecast, 'new_model'),
                        (forecast, 'load_feature_matrix'), (forecast, 'get_connection')]:
        monkeypatch.setattr(owner, name, forbidden)


@pytest.mark.parametrize('truth,prediction,error', [
    ([2., 2., 2.], [1., 1., 1.], 1.),
    ([2., 2., 2.], [2., 2., 2.], 0.),
    ([5.55], [6.], .45),
    ([5.55, np.nextafter(5.55, np.inf), np.nextafter(5.55, -np.inf)],
     [5.8, 5.8, 5.8], .25),
])
def test_unresolved_targets_keep_null_r2_and_finite_errors(truth, prediction, error):
    result = linear.report_metrics(truth, prediction)
    assert result == {'r2': None, 'rmse': error, 'mae': error}
    assert forecast.metrics(truth, prediction)['r2'] is None


@pytest.mark.parametrize('truth,prediction,expected', [
    ([0., 1., 2.], [.5, 1.5, 2.5], {'r2': .625, 'rmse': .5, 'mae': .5}),
    ([10., 12., 14.], [10., 12., 14.], {'r2': 1., 'rmse': 0., 'mae': 0.}),
    ([0., 2.], [1., 1.], {'r2': 0., 'rmse': 1., 'mae': 1.}),
    ([0., 1., 2.], [5., 5., 5.], {'r2': -24., 'rmse': 4.0825, 'mae': 4.}),
])
def test_variable_targets_preserve_existing_values_and_rounding(truth, prediction, expected):
    assert linear.report_metrics(truth, prediction) == expected


def test_small_but_resolvable_variance_is_not_physical_precision_threshold():
    truth = 5.55 + np.array([0., 1e-8, 2e-8, 3e-8])
    prediction = truth + .5e-8
    measured = forecast.metrics(truth, prediction)
    assert measured['r2'] is not None
    assert linear.report_metrics(truth, prediction)['r2'] == round(measured['r2'], 4)


@pytest.mark.parametrize('truth,prediction', [([], []), ([np.nan], [0.]), ([0.], [np.inf])])
def test_invalid_metric_arrays_follow_shared_rejection(truth, prediction):
    with pytest.raises(ValueError):
        linear.report_metrics(truth, prediction)


def test_summary_counts_unavailable_without_converting_it_to_zero():
    frame = pd.DataFrame({'r2': [None, np.nan, 0., 1., -.5],
                          'rmse': [1., 1., 1., 0., 2.], 'mae': [1., 1., 1., 0., 2.]})
    original = frame.copy(deep=True)
    summary = linear.summarize_metrics(frame)
    assert summary['r2'] == {'available': 3, 'unavailable': 2,
                              'mean': pytest.approx(1/6), 'median': 0.}
    assert summary['rmse']['mean'] == 1.
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize('rows', [[], [None, None], [pd.NA, pd.NA]])
def test_all_unavailable_and_empty_summaries_remain_null(rows):
    frame = pd.DataFrame({name: pd.Series(rows, dtype='Float64') for name in ['r2','rmse','mae']})
    summary = linear.summarize_metrics(frame)
    assert all(value == {'available': 0, 'unavailable': len(rows), 'mean': None, 'median': None}
               for value in summary.values())


def test_save_all_undefined_r2_retains_blank_csv_and_no_ranking(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(linear, 'PROCESSED_DIR', tmp_path)
    frame = pd.DataFrame({'district_id':['SYNTHETIC-A','SYNTHETIC-B'], 'r2':[None,None],
                          'rmse':[1.,2.], 'mae':[1.,2.]})
    linear.save_results(frame)
    output = capsys.readouterr().out
    assert 'Mean R2   = unavailable' in output
    assert 'R2 available = 0; unavailable = 2' in output
    assert 'R2 unavailable: 2 (100%)' in output
    assert 'ranking unavailable' in output
    assert 'Top 5 districts' not in output
    saved = pd.read_csv(tmp_path/'linear_regression_results.csv')
    assert saved.r2.isna().all()
    assert saved.rmse.tolist() == [1.,2.]


def test_save_mixed_r2_ranks_real_zero_and_counts_null_separately(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(linear, 'PROCESSED_DIR', tmp_path)
    frame = pd.DataFrame({'district_id':['SYNTHETIC-UNDEFINED','SYNTHETIC-ZERO'],
                          'r2':[None,0.], 'rmse':[1.,2.], 'mae':[1.,2.]})
    linear.save_results(frame)
    output = capsys.readouterr().out
    assert 'Mean R2   = 0.0000' in output
    assert 'R2 < 0.50 (poor): 1 (50%)' in output
    assert 'R2 unavailable: 1 (50%)' in output
    ranking = output.split('Top 5 districts by R2:')[1]
    assert 'SYNTHETIC-ZERO' in ranking
    assert 'SYNTHETIC-UNDEFINED' not in ranking
    assert pd.isna(frame.r2.iloc[0])


def test_save_empty_results_has_no_metric_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(linear, 'PROCESSED_DIR', tmp_path)
    linear.save_results(pd.DataFrame(columns=['district_id','r2','rmse','mae']))
    assert 'No districts have sufficient observed' in capsys.readouterr().out
