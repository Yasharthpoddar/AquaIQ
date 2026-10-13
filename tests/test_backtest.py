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
    """Physical-unit monthly fixtures with explicit observed-target provenance."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_districts):
        gwl = np.cumsum(rng.normal(0.002, 0.03, periods)) + 8.0
        for date, value in zip(pd.date_range(start, periods=periods, freq="MS"), gwl):
            rows.append({"district_id": f"D-{d}", "date": date, "gwl_current": value,
                         "monsoon_deficit_pct": 0.0, "is_observed": True, "is_imputed": False,
                         "predicted_gwl_6mo": value + .5,
                         "prediction_train_target_cutoff": (date.to_period("M") - 7).to_timestamp()})
    return pd.DataFrame(rows)


def test_backtest_components_are_the_live_components():
    df = _toy_features()
    row = backtest._compute_component_scores(df).iloc[40]
    history = (
        df[(df.district_id == row.district_id) & (df.date <= row.date)]
        .sort_values("date")
    )
    predicted = df[(df.district_id == row.district_id) & (df.date == row.date)].iloc[0].predicted_gwl_6mo
    live = components_from_history(history, predicted_depth=predicted)
    assert row.lr_score == pytest.approx(live["lr_trend"])
    assert row.xgb_score == pytest.approx(live["xgb_risk"])
    assert row.drought_score == pytest.approx(live["drought_frequency"])
    assert row.fuzzy_score == pytest.approx(live["fuzzy_logic"])


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


def test_as_of_safety_no_future_leakage():
    df = _toy_features()
    as_of = "2015-12-31"
    comp = backtest._compute_component_scores(df, as_of=as_of)
    assert len(comp) > 0
    # Strict causal cutoff: no observation date past as_of can be included
    assert (comp["date"] <= pd.Timestamp(as_of)).all()
    assert (comp["target_date"] <= pd.Timestamp(as_of)).all()


def test_fitted_weights_are_non_negative_and_sum_to_one():
    weights = backtest.fit_ensemble_weights(_toy_features())
    values = np.array(list(weights.values()))
    assert set(weights) == {"linear_regression_trend", "xgboost_risk", "drought_frequency", "fuzzy_logic"}
    assert (values >= 0).all()
    assert values.sum() == pytest.approx(1.0, abs=1e-3)


def test_synthetic_data_needs_explicit_flag(monkeypatch, tmp_path):
    def no_database():
        raise RuntimeError("no database")

    monkeypatch.setattr(backtest.forecast, "get_connection", no_database)
    monkeypatch.setattr(backtest.forecast, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="manifest missing"):
        backtest.load_feature_matrix()

    df = backtest.load_feature_matrix(allow_synthetic=True)
    assert df.attrs["data_source"] == "synthetic"
    assert backtest.should_write_config(df.attrs["data_source"]) is False
    assert df["gwl_current"].between(0, 50).all()
    assert (df["gwl_current"] > 1).any()
