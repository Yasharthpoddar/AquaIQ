"""
Backtest guards: components match the live API, the fitted weights are a valid
distribution, and synthetic data can only be used when explicitly requested.
"""

import numpy as np
import pandas as pd
import pytest

from models import backtest
from models.ensemble import components_from_history


def _toy_features(n_districts=4, start="2012-01-01", periods=96, seed=0):
    """Monthly scaled-GWL random walks, 2012-2019 by default (covers the backtest years)."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_districts):
        gwl = np.clip(np.cumsum(rng.normal(0.002, 0.03, periods)) + 0.4, 0, 1)
        for date, value in zip(pd.date_range(start, periods=periods, freq="MS"), gwl):
            rows.append({"district_id": f"D-{d}", "date": date, "gwl_current": value})
    return pd.DataFrame(rows)


def test_backtest_components_are_the_live_components():
    df = _toy_features()
    row = backtest._compute_component_scores(df).iloc[40]
    history = (
        df[(df.district_id == row.district_id) & (df.date <= row.date)]
        .sort_values("date")["gwl_current"]
    )
    live = components_from_history(history)
    assert row.lr_score == pytest.approx(live["lr_trend"])
    assert row.xgb_score == pytest.approx(live["xgb_risk"])
    assert row.drought_score == pytest.approx(live["drought_frequency"])


def test_target_is_gwl_six_months_ahead():
    df = _toy_features(n_districts=1)
    series = df.set_index("date")["gwl_current"]
    for _, r in backtest._compute_component_scores(df).head(10).iterrows():
        later = r.date + pd.DateOffset(months=backtest.HORIZON_MONTHS)
        assert r.gwl_future == pytest.approx(series[later])


def test_years_filter_limits_rows():
    comp = backtest._compute_component_scores(_toy_features(), years=[2015])
    assert len(comp) > 0
    assert set(comp["date"].dt.year) == {2015}


def test_fitted_weights_are_non_negative_and_sum_to_one():
    weights = backtest.fit_ensemble_weights(_toy_features())
    values = np.array(list(weights.values()))
    assert set(weights) == {"linear_regression_trend", "xgboost_risk", "drought_frequency"}
    assert (values >= 0).all()
    assert values.sum() == pytest.approx(1.0, abs=1e-3)


def test_synthetic_data_needs_explicit_flag(monkeypatch, tmp_path):
    def no_database():
        raise RuntimeError("no database")

    monkeypatch.setattr(backtest, "get_connection", no_database)
    monkeypatch.setattr(backtest, "ROOT", tmp_path)  # no features_matrix.csv here

    with pytest.raises(SystemExit):
        backtest.load_feature_matrix()

    df = backtest.load_feature_matrix(allow_synthetic=True)
    assert df.attrs["data_source"] == "synthetic"
    assert backtest.should_write_config(df.attrs["data_source"]) is False
    assert df["gwl_current"].between(0, 1).all()
