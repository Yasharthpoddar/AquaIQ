"""
AquaIQ — Preprocessing Unit Tests (Week 6, Yash)
---------------------------------------------------
5 tests covering all preprocessing functions:
  1. test_interpolate_gaps — short gap filling
  2. test_sarima_fill — SARIMA fallback
  3. test_minmax_scaler — train-only normalization
  4. test_feature_engineering — all 10 features
  5. test_train_test_split — temporal split correctness

Run:
    pytest tests/test_preprocessing.py -v
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from preprocessing.pipeline import (
    interpolate_gaps,
    sarima_fill,
    TrainFitMinMaxScaler,
)
from preprocessing.features import (
    build_gwl_features,
    build_derived_features,
    build_train_test_split,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_series():
    """A time series with some gaps."""
    data = [1.0, 2.0, np.nan, 4.0, 5.0, np.nan, np.nan, np.nan, np.nan, 10.0]
    return pd.Series(data)


@pytest.fixture
def sample_df():
    """A minimal district-monthly DataFrame for feature testing."""
    dates = pd.date_range("2002-01-01", periods=36, freq="MS")
    np.random.seed(42)
    df = pd.DataFrame({
        "district_id": ["D001"] * 36,
        "date": dates,
        "gwl": np.random.uniform(5, 15, 36),
        "rainfall": np.random.uniform(0, 200, 36),
        "temperature": np.random.uniform(20, 40, 36),
        "evapotranspiration": np.random.uniform(2, 8, 36),
    })
    return df


@pytest.fixture
def train_test_df():
    """DataFrame spanning 2002-2024 for split testing."""
    dates = pd.date_range("2002-01-01", "2024-12-01", freq="MS")
    df = pd.DataFrame({
        "district_id": ["D001"] * len(dates),
        "date": dates,
        "GWL_current": np.random.uniform(5, 15, len(dates)),
    })
    return df


# ── Test 1: Linear Interpolation ─────────────────────────────────────────

class TestInterpolateGaps:
    def test_fills_short_gaps(self, sample_series):
        """Gaps <= 3 months should be filled by linear interpolation."""
        result = interpolate_gaps(sample_series, max_gap=3)
        # The single NaN at index 2 (gap of 1) should be filled
        assert not np.isnan(result.iloc[2]), "Single gap should be filled"

    def test_leaves_long_gaps(self, sample_series):
        """Gaps > 3 months should be left as NaN for SARIMA."""
        result = interpolate_gaps(sample_series, max_gap=3)
        # The 4 consecutive NaNs at indices 5-8 should remain
        long_gap_nans = result.iloc[5:9].isna().sum()
        assert long_gap_nans >= 1, "Long gaps should not be fully filled by interpolation"

    def test_no_gaps_returns_same(self):
        """Series without NaN should be returned unchanged."""
        clean = pd.Series([1.0, 2.0, 3.0, 4.0])
        result = interpolate_gaps(clean)
        assert result.isna().sum() == 0
        pd.testing.assert_series_equal(result, clean)

    def test_all_nan_returns_same(self):
        """All-NaN series should be returned as-is (nothing to interpolate from)."""
        nans = pd.Series([np.nan, np.nan, np.nan])
        result = interpolate_gaps(nans)
        assert result.isna().sum() == 3


# ── Test 2: SARIMA Fill ──────────────────────────────────────────────────

class TestSarimaFill:
    def test_fills_remaining_nans(self):
        """SARIMA should fill any remaining NaN values (or fall back to ffill)."""
        # Create a series long enough for seasonal model
        np.random.seed(42)
        data = np.sin(np.arange(48) * 2 * np.pi / 12) * 5 + 10  # 4 years seasonal
        series = pd.Series(data)
        # Add some gaps
        series.iloc[20:23] = np.nan

        result = sarima_fill(series, seasonal_period=12)
        assert result.isna().sum() == 0, "SARIMA should fill all remaining NaNs"

    def test_short_series_uses_ffill(self):
        """Series too short for SARIMA should fall back to forward-fill."""
        short = pd.Series([1, 2, np.nan, 4, 5])
        result = sarima_fill(short, seasonal_period=12)
        assert result.isna().sum() == 0, "Should fill via ffill fallback"


# ── Test 3: MinMaxScaler ─────────────────────────────────────────────────

class TestMinMaxScaler:
    def test_fit_on_train_only(self):
        """Scaler should use min/max from train period only."""
        df = pd.DataFrame({
            "date": pd.date_range("2015-01-01", periods=120, freq="MS"),
            "value": list(range(120)),
        })
        scaler = TrainFitMinMaxScaler()
        # Train period ends at 2019-12-31 (60 months in)
        scaled = scaler.fit_transform(df, ["value"])

        # Train period values should be in [0, 1]
        train_mask = pd.to_datetime(df["date"]) <= pd.Timestamp("2019-12-31")
        train_vals = scaled.loc[train_mask, "value"]
        assert train_vals.min() >= 0, "Train min should be >= 0"
        assert train_vals.max() <= 1, "Train max should be <= 1"

    def test_test_values_can_exceed_1(self):
        """Test-period values may exceed 1.0 if they're beyond train range (clipped to [0,1])."""
        df = pd.DataFrame({
            "date": pd.date_range("2015-01-01", periods=120, freq="MS"),
            "value": list(range(120)),
        })
        scaler = TrainFitMinMaxScaler()
        scaled = scaler.fit_transform(df, ["value"])

        # After clipping, all values should be in [0, 1]
        assert scaled["value"].min() >= 0
        assert scaled["value"].max() <= 1

    def test_zero_variance_column(self):
        """Column with constant values shouldn't cause division by zero."""
        df = pd.DataFrame({
            "date": pd.date_range("2015-01-01", periods=60, freq="MS"),
            "value": [5.0] * 60,
        })
        scaler = TrainFitMinMaxScaler()
        scaled = scaler.fit_transform(df, ["value"])
        assert not scaled["value"].isna().any(), "Constant column should not produce NaN"


# ── Test 4: Feature Engineering ──────────────────────────────────────────

class TestFeatureEngineering:
    def test_gwl_lags_created(self, sample_df):
        """GWL lag features should be created correctly."""
        result = build_gwl_features(sample_df)
        assert "GWL_current" in result.columns
        assert "GWL_lag_3mo" in result.columns
        assert "GWL_lag_6mo" in result.columns

    def test_lag_values_correct(self, sample_df):
        """Lag values should match shifted original values."""
        result = build_gwl_features(sample_df)
        # GWL_lag_3mo at index 3 should equal GWL_current at index 0
        expected = sample_df["gwl"].iloc[0]
        actual = result["GWL_lag_3mo"].iloc[3]
        assert actual == expected, f"Lag-3 mismatch: {actual} != {expected}"

    def test_derived_features(self, sample_df):
        """Water balance and crop season features should be created."""
        sample_df["rainfall_current"] = sample_df["rainfall"]
        result = build_derived_features(sample_df)
        assert "water_balance_proxy" in result.columns
        assert "crop_season_flag" in result.columns

    def test_crop_season_values(self, sample_df):
        """Crop season flag should only contain valid values."""
        sample_df["rainfall_current"] = sample_df["rainfall"]
        result = build_derived_features(sample_df)
        valid_seasons = {"Kharif", "Rabi", "Zaid"}
        actual_seasons = set(result["crop_season_flag"].unique())
        assert actual_seasons.issubset(valid_seasons), f"Invalid seasons: {actual_seasons - valid_seasons}"


# ── Test 5: Train-Test Split ─────────────────────────────────────────────

class TestTrainTestSplit:
    def test_no_overlap(self, train_test_df):
        """Train and test sets should not overlap."""
        train, test = build_train_test_split(train_test_df)
        if len(train) > 0 and len(test) > 0:
            assert train["date"].max() < test["date"].min(), "Train and test should not overlap"

    def test_train_ends_at_2019(self, train_test_df):
        """Train set should end at or before 2019-12-31."""
        train, _ = build_train_test_split(train_test_df)
        assert train["date"].max() <= pd.Timestamp("2019-12-31"), "Train should end by 2019"

    def test_test_starts_at_2023(self, train_test_df):
        """Test set should start at or after 2023-01-01."""
        _, test = build_train_test_split(train_test_df)
        if len(test) > 0:
            assert test["date"].min() >= pd.Timestamp("2023-01-01"), "Test should start at 2023"

    def test_split_ratio(self, train_test_df):
        """Train should have significantly more data than test (roughly 80/20)."""
        train, test = build_train_test_split(train_test_df)
        total = len(train) + len(test)
        if total > 0:
            train_pct = len(train) / total
            assert train_pct > 0.6, f"Train should be > 60% of data, got {train_pct:.0%}"
