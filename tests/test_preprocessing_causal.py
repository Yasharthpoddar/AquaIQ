"""
AquaIQ — D4 & D3 Causal Preprocessing Regression Test.
Verifies:
1. Zero look-ahead leakage: future observations are never linearly interpolated backwards.
2. LOCF bounded at <= 3 months; gaps > 3 months remain NaN.
3. months_since_observation tracks distance to last true measurement.
4. Physical units are preserved (GWL in metres bgl, not [0, 1] scaled).
5. Output timeline is continuous monthly grid (MS) from 2002-01-01 to 2024-12-01.
"""

import pandas as pd
import numpy as np
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
from preprocessing.pipeline import apply_causal_gwl_imputation, reindex_district_monthly


def test_no_backward_leakage_and_bounded_locf():
    """
    Given observations at month 0 (depth 5.0m) and month 5 (depth 10.0m):
    - Month 0: 5.0, months_since=0, is_imputed=False
    - Month 1: 5.0 (LOCF), months_since=1, is_imputed=True
    - Month 2: 5.0 (LOCF), months_since=2, is_imputed=True
    - Month 3: 5.0 (LOCF), months_since=3, is_imputed=True
    - Month 4: NaN (gap > 3), months_since=4, is_imputed=False
    - Month 5: 10.0, months_since=0, is_imputed=False
    
    CRITICAL: Month 1 must NOT be (5.0 + (10.0-5.0)*1/5 = 6.0) - that would leak future 10.0m!
    """
    dates = pd.date_range("2020-01-01", periods=6, freq="MS")
    df = pd.DataFrame({
        "date": dates,
        "gwl": [5.0, np.nan, np.nan, np.nan, np.nan, 10.0]
    })

    result = apply_causal_gwl_imputation(df, max_locf_gap=3)

    # Check values
    assert result.loc[0, "gwl"] == 5.0
    assert result.loc[0, "months_since_observation"] == 0
    assert not result.loc[0, "is_imputed"]

    # Month 1, 2, 3 must be LOCF (5.0), NEVER interpolated towards 10.0!
    assert result.loc[1, "gwl"] == 5.0
    assert result.loc[1, "months_since_observation"] == 1
    assert result.loc[1, "is_imputed"]

    assert result.loc[2, "gwl"] == 5.0
    assert result.loc[2, "months_since_observation"] == 2
    assert result.loc[2, "is_imputed"]

    assert result.loc[3, "gwl"] == 5.0
    assert result.loc[3, "months_since_observation"] == 3
    assert result.loc[3, "is_imputed"]

    # Month 4 exceeds 3-month gap: must be NaN
    assert np.isnan(result.loc[4, "gwl"])
    assert result.loc[4, "months_since_observation"] == 4

    # Month 5 is fresh observation
    assert result.loc[5, "gwl"] == 10.0
    assert result.loc[5, "months_since_observation"] == 0
    assert not result.loc[5, "is_imputed"]


def test_reindex_district_monthly():
    """Verify district timeline is reindexed to complete 276-month grid."""
    df = pd.DataFrame({
        "district_id": ["MH-Pune", "MH-Pune"],
        "date": [pd.Timestamp("2002-03-01"), pd.Timestamp("2002-06-01")],
        "gwl": [4.2, 5.1],
        "rainfall": [12.0, 45.0],
        "temperature": [28.0, 31.0],
        "evapotranspiration": [90.0, 110.0]
    })

    reindexed = reindex_district_monthly(
        df,
        start_date="2002-01-01",
        end_date="2024-12-01"
    )

    assert len(reindexed) == 276
    assert reindexed["date"].min() == pd.Timestamp("2002-01-01")
    assert reindexed["date"].max() == pd.Timestamp("2024-12-01")
    assert (reindexed["district_id"] == "MH-Pune").all()
