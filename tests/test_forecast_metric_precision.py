"""Forecast skill cannot be divided by decimal-constant rounding artifacts."""
import numpy as np
import pytest
from sklearn.metrics import r2_score

from models import xgboost_model as forecast


@pytest.mark.parametrize("truth", [
    np.repeat(5.55, 10),
    np.array([5.55, np.nextafter(5.55, np.inf), np.nextafter(5.55, -np.inf)] * 4),
    np.repeat(0., 10),
    np.array([5.55]),
])
@pytest.mark.parametrize("bias", [0., .25])
def test_constant_at_float_precision_has_no_defined_r2_or_nse(truth, bias):
    predictions = truth + bias
    measured = forecast.metrics(truth, predictions)
    assert measured["n"] == len(truth)
    assert measured["r2"] is None
    assert measured["nse"] is None
    assert forecast.nash_sutcliffe_efficiency(truth, predictions) is None
    assert measured["mae_m"] == pytest.approx(abs(bias))
    assert measured["rmse_m"] == pytest.approx(abs(bias))


@pytest.mark.parametrize("truth,predictions", [
    (np.array([0., 1., 2.]), np.array([.5, 1.5, 2.5])),
    (5.55 + np.array([0., 1e-8, 2e-8, 3e-8]),
     5.55 + np.array([.5e-8, 1.5e-8, 2.5e-8, 3.5e-8])),
    (np.array([10., 12., 14., 16.]), np.array([10., 12., 14., 16.])),
])
def test_resolvable_target_variation_retains_r2_and_nse(truth, predictions):
    expected = float(r2_score(truth, predictions))
    measured = forecast.metrics(truth, predictions)
    assert measured["r2"] == pytest.approx(expected)
    assert measured["nse"] == pytest.approx(expected)
    assert forecast.nash_sutcliffe_efficiency(truth, predictions) == pytest.approx(expected)
