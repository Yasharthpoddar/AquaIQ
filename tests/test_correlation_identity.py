"""EDA must not merge identically named districts in different states."""
import pandas as pd
import pytest
from preprocessing.correlation_analysis import compute_district_correlations, load_cgwb


def test_same_district_name_retains_state_in_correlation():
    frame = pd.DataFrame({"state": ["bihar"] * 4 + ["maharashtra"] * 4,
                          "district": ["aurangabad"] * 8,
                          "rainfall_mm": [1, 2, 3, 4] * 2,
                          "gwl": [4, 3, 2, 1, 1, 2, 3, 4]})
    result = compute_district_correlations(frame).set_index("state")
    assert len(result) == 2
    assert result.loc["bihar", "correlation"] == pytest.approx(-1)
    assert result.loc["maharashtra", "correlation"] == pytest.approx(1)


def test_eda_loader_uses_actual_path_and_state_qualified_aggregation(tmp_path, monkeypatch):
    path = tmp_path / "cgwb.csv"
    pd.DataFrame({"state_name": ["Bihar", "Maharashtra", "Bihar"],
                  "district_name": ["Aurangabad"] * 3,
                  "date": ["2020-01-01", "2020-01-01", "invalid"],
                  "currentlevel": [4, 12, 99]}).to_csv(path, index=False)
    monkeypatch.setattr("preprocessing.correlation_analysis.CGWB_PATH", path)
    frame = load_cgwb()
    assert len(frame) == 2
    assert set(frame.gwl) == {4, 12}
