"""AquaIQ — Comprehensive Unit & Integration Tests for State-Wise Groundwater Forecasting.

Tests:
1. Authoritative State Registry, Aliases, and District-to-State Mapping.
2. Canonical Crosswalk 100% State Coverage (725 districts).
3. State Observation Aggregation, Weighting, and Missing-Data Safety (never treated as 0).
4. Zero-Observation and Insufficient-Coverage States (no fabricated data).
5. Exact 12-Month Chronological Response Contract and Baselines.
6. Leakage-Free Chronological Evaluation Protocol.
7. Verified State GeoJSON Feature ID Mapping (36 states).
8. State API Route Validation, Parameters, and Error Handling (400, 404).
9. Full Preservation of Existing District APIs, 6-Month and 12-Month Forecasting.
"""

from datetime import date
import json
from pathlib import Path
import math
import numpy as np
import pandas as pd
import pytest

from models.state_mapping import (
    STATES_REGISTRY,
    STATE_ALIASES,
    resolve_state_id,
    get_state_metadata,
    list_states,
    normalize_state_name,
)
from models.state_forecast import (
    aggregate_state_observations,
    forecast_state_twelve_months,
    get_all_states_summary,
    get_state_districts,
    EVALUATION_METRICS,
    PRODUCT_NAME,
    MODEL_VERSION,
)
from api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


# ── 1. Authoritative State Registry & Aliases ──────────────────────────────

def test_state_registry_contains_all_36_states_and_uts():
    states = list_states()
    assert len(states) == 36
    assert len(STATES_REGISTRY) == 36

    types = {s["type"] for s in states}
    assert types == {"State", "UT"}

    # Verify key states and UTs
    for code in ("UP", "TN", "MH", "RJ", "KA", "DL", "JK", "LA", "LD", "CH", "DD", "AN"):
        assert code in STATES_REGISTRY
        meta = get_state_metadata(code)
        assert meta["state_id"] == code
        assert isinstance(meta["name"], str) and meta["name"]
        assert isinstance(meta["st_code"], str) and len(meta["st_code"]) == 2


def test_resolve_state_id_handles_codes_names_aliases_and_district_ids():
    # Direct code
    assert resolve_state_id("UP") == "UP"
    assert resolve_state_id("up") == "UP"
    assert resolve_state_id("TN") == "TN"

    # Full name
    assert resolve_state_id("Uttar Pradesh") == "UP"
    assert resolve_state_id("tamil nadu") == "TN"
    assert resolve_state_id("Maharashtra") == "MH"

    # Historical and colloquial aliases
    assert resolve_state_id("Orissa") == "OD"
    assert resolve_state_id("Odisha") == "OD"
    assert resolve_state_id("Uttaranchal") == "UK"
    assert resolve_state_id("Uttarakhand") == "UK"
    assert resolve_state_id("Pondicherry") == "PY"
    assert resolve_state_id("Puducherry") == "PY"
    assert resolve_state_id("The Dadra and Nagar Haveli and Daman and Diu") == "DD"
    assert resolve_state_id("Dadra and Nagar Haveli") == "DD"
    assert resolve_state_id("Daman and Diu") == "DD"
    assert resolve_state_id("Jammu & Kashmir") == "JK"

    # District ID resolution
    assert resolve_state_id("UP-Deoria") == "UP"
    assert resolve_state_id("TN-Cuddalore") == "TN"
    assert resolve_state_id("RJ-Jaipur") == "RJ"

    # Invalid / ambiguous identifiers raise LookupError
    with pytest.raises(LookupError):
        resolve_state_id("Atlantis")
    with pytest.raises(LookupError):
        resolve_state_id("")
    with pytest.raises(LookupError):
        resolve_state_id(None)


# ── 2. Canonical Crosswalk 100% State Coverage ─────────────────────────────

def test_all_725_canonical_districts_map_to_registered_states():
    cw_path = ROOT / "data_ingestion/district_crosswalk.csv"
    assert cw_path.exists()
    cw = pd.read_csv(cw_path)
    canonical = cw[cw["source"] == "GeoJSON"]
    assert len(canonical) == 724 or len(canonical) == 725

    unique_districts = cw["canonical_district_id"].unique()
    assert len(unique_districts) >= 724

    for dist_id in unique_districts:
        state_code = dist_id.split("-")[0]
        assert state_code in STATES_REGISTRY, f"District {dist_id} has unregistered state prefix {state_code}"
        assert resolve_state_id(dist_id) == state_code


# ── 3. State Observation Aggregation & Missing Data Safety ─────────────────

def test_state_aggregation_excludes_imputed_and_missing_values():
    # Test on Tamil Nadu (dense observations)
    hist = aggregate_state_observations("TN")
    assert not hist.empty
    assert "date" in hist.columns
    assert "gwl_m_bgl" in hist.columns
    assert "contributing_districts_count" in hist.columns
    assert "total_districts_in_state" in hist.columns
    assert "district_coverage_pct" in hist.columns

    # Verify no NaN or negative depths
    assert hist["gwl_m_bgl"].notna().all()
    assert (hist["gwl_m_bgl"] >= 0.0).all()
    assert (hist["contributing_districts_count"] >= 1).all()
    assert (hist["total_districts_in_state"] == 37).all()
    assert (hist["district_coverage_pct"] > 0).all()


def test_missing_districts_are_never_treated_as_zero():
    # If a district did not report in month M, its value is not assumed to be 0 m bgl.
    # The average is strictly over reporting districts.
    hist = aggregate_state_observations("UP")
    for row in hist.itertuples():
        # Depth in UP averages 5-15m; if missing districts were treated as 0,
        # months with few districts would collapse to near 0.
        assert row.gwl_m_bgl > 1.0, f"Suspicious zero-collapsed average {row.gwl_m_bgl} on {row.date}"


# ── 4. Zero-Observation and Insufficient-Coverage States ────────────────────

@pytest.mark.parametrize("state_id", ["LA", "LD", "SK"])
def test_zero_observation_states_return_insufficient_data(state_id):
    fc = forecast_state_twelve_months(state_id)
    assert fc["status"] == "insufficient_data"
    assert fc["forecast"] == []
    assert len(fc["forecast"]) == 0
    assert "insufficient" in fc["message"].lower() or "unavailable" in fc["message"].lower()
    assert fc["contributing_districts_count"] == 0


def test_sparse_observation_state_mizoram():
    # Mizoram has only 1 historical observation date
    fc = forecast_state_twelve_months("MZ")
    assert fc["status"] == "insufficient_data"
    assert fc["forecast"] == []
    assert "minimum 3 required" in fc["message"]


# ── 5. Exact 12-Month Chronological Response Contract ──────────────────────

def test_forecast_response_contract_for_reporting_state():
    fc = forecast_state_twelve_months("RJ")
    assert fc["status"] == "forecast"
    assert fc["product"] == PRODUCT_NAME
    assert fc["model_version"] == MODEL_VERSION
    assert fc["state_id"] == "RJ"
    assert fc["state_name"] == "Rajasthan"
    assert fc["units"] == "m_bgl"
    assert fc["horizon_months"] == 12
    assert "forecast_origin" in fc
    assert "as_of" in fc
    assert "last_observed_date" in fc
    assert "last_observed_gwl_m_bgl" in fc

    forecast = fc["forecast"]
    assert len(forecast) == 12

    origin_dt = pd.Timestamp(fc["forecast_origin"])

    for idx, pt in enumerate(forecast, start=1):
        assert pt["horizon"] == idx
        expected_target = (origin_dt + pd.DateOffset(months=idx)).strftime("%Y-%m-%d")
        assert pt["target_date"] == expected_target
        assert isinstance(pt["predicted_gwl"], (int, float))
        assert math.isfinite(pt["predicted_gwl"])
        assert pt["predicted_gwl"] >= 0.0
        assert isinstance(pt["delta_from_current_m"], (int, float))
        assert math.isfinite(pt["delta_from_current_m"])

        # Baselines
        baselines = pt["baselines"]
        assert "persistence" in baselines
        assert "seasonal_naive" in baselines
        assert math.isfinite(baselines["persistence"])
        assert math.isfinite(baselines["seasonal_naive"])


# ── 6. Leakage-Free Chronological Evaluation Protocol ──────────────────────

def test_as_of_cutoff_strictly_excludes_future_data():
    cutoff = "2019-12-31"
    hist_pre_2020 = aggregate_state_observations("TN", as_of=cutoff)
    assert not hist_pre_2020.empty
    assert (hist_pre_2020["date"] <= pd.Timestamp(cutoff)).all()

    # Forecast with historical cutoff
    fc_pre = forecast_state_twelve_months("TN", as_of=cutoff)
    assert fc_pre["status"] == "forecast"
    assert fc_pre["as_of"] == "2019-12-31"
    # Target horizons must be in 2020
    assert fc_pre["forecast"][0]["target_date"] == "2020-01-01"
    assert fc_pre["forecast"][11]["target_date"] == "2020-12-01"


def test_evaluation_metrics_disclose_positive_skill_over_baselines():
    metrics = EVALUATION_METRICS["models"]
    proj_mae = metrics["direct_state_projection"]["mae_m"]
    persist_mae = metrics["persistence_baseline"]["mae_m"]
    seasonal_mae = metrics["seasonal_naive_baseline"]["mae_m"]
    district_agg_mae = metrics["district_aggregation_approach_b"]["mae_m"]

    assert proj_mae < persist_mae, "Direct state projection must outperform persistence baseline"
    assert proj_mae < seasonal_mae, "Direct state projection must outperform seasonal naive baseline"
    assert proj_mae < district_agg_mae, "Direct state projection must outperform district aggregation"
    assert metrics["direct_state_projection"]["skill_vs_persistence_r2_delta"] > 0.0


# ── 7. Verified State GeoJSON Feature ID Mapping ───────────────────────────

def test_india_states_geojson_has_36_features_and_matches_registry():
    geojson_path = ROOT / "dashboard/public/india_states.geojson"
    assert geojson_path.exists(), "dashboard/public/india_states.geojson must exist"

    with open(geojson_path, "r", encoding="utf-8") as f:
        gj = json.load(f)

    assert gj["type"] == "FeatureCollection"
    assert len(gj["features"]) == 36

    found_states = set()
    for feat in gj["features"]:
        props = feat["properties"]
        sid = props.get("state_id")
        assert sid in STATES_REGISTRY, f"Unexpected state_id {sid} in GeoJSON"
        found_states.add(sid)
        assert props.get("state_name") == STATES_REGISTRY[sid]["name"]
        assert props.get("st_code") == STATES_REGISTRY[sid]["st_code"]
        assert feat.get("geometry") is not None

    assert found_states == set(STATES_REGISTRY.keys())


# ── 8. State API Route Validation & Error Handling ─────────────────────────

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_api_states_list(client):
    res = client.get("/api/states")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total"] == 36
    assert len(data["states"]) == 36
    sample = data["states"][0]
    assert "state_id" in sample
    assert "state_name" in sample
    assert "total_districts" in sample
    assert "districts" in sample


def test_api_states_summary_and_validation(client):
    # Valid call
    res = client.get("/api/states/summary?horizon=12")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total_states"] == 36
    assert data["available_states_count"] >= 25
    assert len(data["states"]) == 36

    # Invalid horizon
    res_bad = client.get("/api/states/summary?horizon=6")
    assert res_bad.status_code == 400
    assert res_bad.get_json()["status"] == "invalid_request"

    res_non_int = client.get("/api/states/summary?horizon=invalid")
    assert res_non_int.status_code == 400


def test_api_predict_state_validation(client):
    # Valid state
    res = client.get("/api/predict/state/UP?horizon=12")
    assert res.status_code == 200
    data = res.get_json()
    assert data["state_id"] == "UP"
    assert len(data["forecast"]) == 12

    # Case insensitivity & full name support
    res_name = client.get("/api/predict/state/karnataka?horizon=12")
    assert res_name.status_code == 200
    assert res_name.get_json()["state_id"] == "KA"

    # Sparse state returns 200 with structured insufficient_data status
    res_sparse = client.get("/api/predict/state/LA?horizon=12")
    assert res_sparse.status_code == 200
    assert res_sparse.get_json()["status"] == "insufficient_data"

    # Unknown state returns 404
    res_unknown = client.get("/api/predict/state/INVALID_STATE?horizon=12")
    assert res_unknown.status_code == 404

    # Invalid horizon returns 400
    res_bad_h = client.get("/api/predict/state/UP?horizon=24")
    assert res_bad_h.status_code == 400


# ── 9. Non-Regression: Existing District APIs & Models Intact ──────────────

def test_existing_district_endpoints_are_fully_preserved(client):
    # District crisis score
    res_dist = client.get("/api/district/TN-Cuddalore")
    assert res_dist.status_code == 200
    dist_data = res_dist.get_json()
    assert "crisis_score" in dist_data

    # Six-month prediction
    res_6m = client.get("/api/predict/TN-Cuddalore")
    assert res_6m.status_code == 200

    # Next six months window
    res_next6m = client.get("/api/predict/TN-Cuddalore?window=next_six_months")
    assert res_next6m.status_code == 200

    # Experimental 12-month climate prediction
    res_12m = client.get("/api/predict/climate-12m/TN-Cuddalore")
    assert res_12m.status_code == 200
    data_12m = res_12m.get_json()
    assert data_12m["product"] == "climate_informed_12m_forecast"
    assert len(data_12m["forecast"]) == 12

    # Batch scores
    res_scores = client.get("/api/scores")
    assert res_scores.status_code == 200
    assert "districts" in res_scores.get_json()
