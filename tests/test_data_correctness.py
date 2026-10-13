"""Regressions for physical units, source provenance and forecast causality."""
import json
import hashlib
import numpy as np
import pandas as pd
import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon

from preprocessing.pipeline import apply_causal_gwl_imputation, run_pipeline
from preprocessing.features import build_gwl_features, build_rainfall_features, build_all_features
from data_ingestion.era5_to_district import evaporation_monthly, assign_districts_with_fallback
from data_ingestion.imd_district_climatology import assign_district, grid_to_long_monthly
from data_ingestion.ingest_imd_era5 import find_target_ids, validate_weather_artifact


def test_future_weather_does_not_change_past_features():
    dates = pd.date_range("2002-01-01", "2008-12-01", freq="MS")
    original = pd.DataFrame({"district_id": "RJ-Jaipur", "date": dates,
                             "gwl": 8.0, "rainfall": 100.0, "temperature": 25.0,
                             "evapotranspiration": 90.0})
    original.loc[13:15, "rainfall"] = np.nan
    future = original.copy()
    future.loc[future.date >= "2007-01-01", ["rainfall", "temperature", "evapotranspiration", "gwl"]] = 10000.0
    before = build_rainfall_features(run_pipeline(original))
    after = build_rainfall_features(run_pipeline(future))
    cols = ["gwl", "rainfall", "temperature", "evapotranspiration", "monsoon_deficit_pct"]
    pd.testing.assert_frame_equal(before.loc[before.date < "2007-01-01", cols],
                                  after.loc[after.date < "2007-01-01", cols])
    # Climate gaps use two-month bounded forward fill, never future interpolation.
    assert before.loc[13, "rainfall"] == 100.0
    assert before.loc[14, "rainfall"] == 100.0
    assert pd.isna(before.loc[15, "rainfall"])


def test_normals_use_prior_years_including_pre_start_history():
    current = pd.DataFrame({"district_id": ["D"] * 2, "date": pd.to_datetime(["2002-01-01", "2003-01-01"]),
                            "rainfall": [200.0, 10000.0]})
    past = pd.DataFrame({"district_id": ["D"] * 3, "date": pd.to_datetime(["1999-01-01", "2000-01-01", "2001-01-01"]),
                         "rainfall": [90.0, 100.0, 110.0]})
    result = build_rainfall_features(current, rainfall_history=past)
    assert result.loc[0, "rainfall_normal"] == 100.0
    assert result.loc[0, "monsoon_deficit_pct"] == 100.0
    assert result.loc[1, "rainfall_normal"] == 125.0


def test_unknown_normal_is_missing_not_zero_risk():
    df = pd.DataFrame({"district_id": "D", "date": pd.date_range("2002-01-01", periods=12, freq="MS"), "rainfall": 100.0})
    assert build_rainfall_features(df).monsoon_deficit_pct.isna().all()


def test_calendar_lag_does_not_skip_missing_month():
    df = pd.DataFrame({"district_id": ["D"] * 4,
                       "date": pd.to_datetime(["2002-01-01", "2002-02-01", "2002-04-01", "2002-05-01"]),
                       "gwl": [10.0, 11.0, 13.0, 14.0]})
    result = build_gwl_features(df)
    assert result.loc[2, "GWL_lag_3mo"] == 10.0
    assert result.loc[3, "GWL_lag_3mo"] == 11.0


def test_groundwater_has_explicit_observation_provenance():
    df = pd.DataFrame({"date": pd.date_range("2002-01-01", periods=8, freq="MS"),
                       "gwl": [np.nan, np.inf, 151.046, np.nan, np.nan, np.nan, np.nan, 9.0]})
    result = apply_causal_gwl_imputation(df)
    assert pd.isna(result.loc[0, "months_since_observation"])
    assert pd.isna(result.loc[1, "gwl"])
    assert not result.loc[1, "is_observed"]
    assert result.loc[2, "is_observed"]
    assert result.loc[3, "is_imputed"]
    assert result.loc[3, "gwl"] == 151.046
    assert pd.isna(result.loc[6, "gwl"])
    assert not result.loc[6, "is_imputed"]


def test_features_refuse_unknown_observation_origin():
    with pytest.raises(ValueError, match="Unknown observation provenance"):
        build_all_features(pd.DataFrame({"district_id": ["D"], "date": [pd.Timestamp("2002-01-01")], "gwl": [5.0]}))


def test_evaporation_daily_and_monthly_metadata_prevent_double_conversion():
    dates = pd.to_datetime(["2020-01-01", "2020-02-01", "2021-02-01"])
    shape = (3, 1, 1)
    monthly = evaporation_monthly(np.full(shape, -0.002), {"units": "m", "GRIB_stepType": "avgad"}, dates)
    np.testing.assert_allclose(monthly.ravel(), [62.0, 58.0, 56.0])
    np.testing.assert_allclose(evaporation_monthly(monthly, {"units": "mm/month"}, dates), monthly)
    with pytest.raises(ValueError, match="Unknown ERA5 evaporation"):
        evaporation_monthly(np.full(shape, 2.0), {"units": "mm"}, dates)


@pytest.mark.parametrize("imd", [False, True])
def test_small_district_uses_exactly_one_nearest_source_cell(imd):
    pts = pd.DataFrame({"longitude": [0.0, 1.0], "latitude": [0.0, 1.0], "lat_idx": [7, 8], "lon_idx": [3, 4]})
    districts = gpd.GeoDataFrame({"district": ["A", "Small"], "st_nm": ["S", "S"]},
                 geometry=[Polygon([(-.2,-.2),(.2,-.2),(.2,.2),(-.2,.2)]),
                           Polygon([(.38,.38),(.42,.38),(.42,.42),(.38,.42)])], crs="EPSG:4326")
    if imd:
        pts["year"], pts["month"], pts["rainfall_mm"] = 2020, 1, [10.0, 1000.0]
        result = assign_district(pts, districts)
    else:
        points = gpd.GeoDataFrame(pts, geometry=[Point(0,0), Point(1,1)], crs="EPSG:4326")
        result = assign_districts_with_fallback(points, districts)
    selected = result[result.district == "Small"]
    assert len(selected) == 1
    assert selected.lat_idx.iloc[0] == 7
    assert selected.lon_idx.iloc[0] == 3
    assert selected.geometry.iloc[0].equals(Point(0, 0))


def test_wrong_state_cannot_borrow_a_shared_district_name():
    lookup = {"state_aware": {("bilaspur", "chhattisgarh"): {"CG-Bilaspur"},
                               ("bilaspur", "himachal pradesh"): {"HP-Bilaspur"}},
              "name_only": {"bilaspur": {"CG-Bilaspur", "HP-Bilaspur"}}}
    assert find_target_ids("Bilaspur", "Chhattisgarh", lookup) == {"CG-Bilaspur"}
    assert find_target_ids("Bilaspur", "wrong state", lookup) == set()


def test_weather_ingestion_refuses_legacy_or_edited_artifact(tmp_path):
    path = tmp_path / "weather.csv"
    path.write_text("evapotranspiration\n2.94\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Regenerate verified"):
        validate_weather_artifact(path, {"evapotranspiration": "mm/month"})
    metadata = {"artifact_version": "weather-v3", "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "units": {"evapotranspiration": "mm/month"}}
    path.with_suffix(".manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
    validate_weather_artifact(path, {"evapotranspiration": "mm/month"})
    path.write_text("evapotranspiration\n91.00\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        validate_weather_artifact(path, {"evapotranspiration": "mm/month"})


def test_imd_sum_requires_all_daily_measurements(monkeypatch):
    import data_ingestion.imd_district_climatology as imd
    monkeypatch.setattr(imd, "NX", 2)
    monkeypatch.setattr(imd, "NY", 1)
    data = np.ones((365, 1, 2))
    data[0, 0, 1] = np.nan
    result = grid_to_long_monthly(data, 2021)
    january = result[result.month == 1]
    assert len(january) == 1
    assert january.rainfall_mm.iloc[0] == 31.0
    assert len(result[result.month == 2]) == 2
