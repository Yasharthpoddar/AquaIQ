"""Synthetic unit fixtures only; real-source smoke check never fits active ML."""
from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from api.app import create_app
from models import experimental_scenario as scenario
from models import research_forecast as direct

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def forbid_active_models_and_database(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Scenario must not access a DB or fit/load active ML")
    import psycopg2
    import xgboost
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge
    from models import research_horizon
    monkeypatch.setattr(psycopg2, "connect", forbidden)
    monkeypatch.setattr(xgboost.XGBRegressor, "fit", forbidden)
    monkeypatch.setattr(xgboost.XGBRegressor, "load_model", forbidden)
    monkeypatch.setattr(research_horizon, "load_research_model", forbidden)
    for model in (HistGradientBoostingRegressor, RandomForestRegressor, LinearRegression, Ridge):
        monkeypatch.setattr(model, "fit", forbidden)


@pytest.fixture
def synthetic(monkeypatch):
    dates = pd.date_range("2010-01-01", "2027-02-01", freq="MS")
    frame = pd.DataFrame({"date": dates, "district_id": "TS-Adilabad",
                          "gwl_current": 10 + .01*np.arange(len(dates)) + np.sin(dates.month*2*np.pi/12),
                          "is_observed": True, "is_imputed": False, "_observed": True,
                          "first_reported_date": "SYNTHETIC FIXTURE ONLY",
                          "last_reported_date": "SYNTHETIC FIXTURE ONLY", "well_count": 3,
                          "panel_sha256": "SYNTHETIC FIXTURE ONLY"})
    bundle = {"frame": frame, "manifest": {"snapshot_sha256": "a"*64},
              "contract": {"feature_generation_id": "SYNTHETIC FIXTURE ONLY"}, "config_sha256": "b"*64}
    monkeypatch.setattr(direct, "_load_bundle", lambda *_: bundle)
    return bundle


def test_twelve_full_calendar_months_and_unvalidated_contract(synthetic):
    value = scenario.scenario("TS-Adilabad", now=NOW)
    assert value["status"] == "scenario"
    assert value["as_of"] == "2026-10-21"
    assert [r["month"] for r in value["forecast"]] == ["2026-11", "2026-12"] + [f"2027-{m:02d}" for m in range(1,11)]
    assert [r["horizon_months"] for r in value["forecast"]] == list(range(1,13))
    assert all(np.isfinite(r["projected_gwl"]) and r["projected_gwl"] >= 0 for r in value["forecast"])
    assert value["forecast_issued_at"] is None
    assert value["validation"] == {"status": "unvalidated_scenario", "prospective_skill_verified": False, "sufficient_for_operational_use": False}
    assert value["source"]["availability_verified"] is False
    assert value["method"]["parameters_saved"] is False


def test_future_and_current_months_cannot_influence_fit_even_on_month_end(synthetic):
    before = scenario.scenario("TS-Adilabad", "2026-10-21", now=NOW)
    frame = synthetic["frame"]
    frame.loc[frame.date.ge("2026-10-01"), "gwl_current"] = 999999
    after = scenario.scenario("TS-Adilabad", "2026-10-21", now=NOW)
    assert before["forecast"] == after["forecast"]
    assert before["method"]["history_sha256"] == after["method"]["history_sha256"]
    end = scenario.scenario("TS-Adilabad", "2026-10-31", now=datetime(2026,11,1,tzinfo=timezone.utc))
    assert end["source"]["last_observed_month"] == "2026-09"


def test_imputed_and_unknown_observation_rows_do_not_change_projection(synthetic):
    frame = synthetic["frame"]
    mask = frame.date.dt.month.eq(2)
    frame.loc[mask, ["_observed", "is_observed"]] = False
    frame.loc[mask, "is_imputed"] = True
    before = scenario.scenario("TS-Adilabad", now=NOW)
    frame.loc[mask, "gwl_current"] = 999999
    after = scenario.scenario("TS-Adilabad", now=NOW)
    assert before["forecast"] == after["forecast"]
    assert 2 not in after["method"]["observed_calendar_months"]
    assert 2 in after["method"]["unobserved_calendar_months"]


def test_history_is_not_modified_and_fit_is_deterministic(synthetic):
    original = deepcopy(synthetic["frame"])
    one = scenario.scenario("TS-Adilabad", now=NOW)
    two = scenario.scenario("TS-Adilabad", now=NOW)
    assert one == two
    pd.testing.assert_frame_equal(original, synthetic["frame"])


def test_unknown_district_never_loads_adilabad_or_substitutes_source(monkeypatch):
    monkeypatch.setattr(direct, "_load_bundle", lambda *_: pytest.fail("Unsupported scope read assets"))
    result = scenario.scenario("XX-Unknown", now=NOW)
    assert result["status"] == "unavailable" and result["forecast"] == []
    assert result["estimated_current_gwl"] is None


def test_insufficient_observed_history_abstains(synthetic):
    synthetic["frame"] = synthetic["frame"].tail(10)
    result = scenario.scenario("TS-Adilabad", now=NOW)
    assert result["status"] == "unavailable" and result["forecast"] == []


@pytest.mark.parametrize("date", ["2026-02-30", "2026-13-01", "2026-11-01", "2026-1-01", "today", "2026-10-21T00:00:00Z"])
def test_bad_or_future_dates_rejected_before_source_access(monkeypatch, date):
    monkeypatch.setattr(direct, "_load_bundle", lambda *_: pytest.fail("Invalid request read assets"))
    with pytest.raises(ValueError):
        scenario.scenario("TS-Adilabad", date, now=NOW)


def test_timezone_uses_india_calendar_at_utc_date_boundary():
    assert scenario.parse_as_of(now=datetime(2026,10,20,20,tzinfo=timezone.utc)).isoformat() == "2026-10-21"
    with pytest.raises(ValueError):
        scenario.parse_as_of(now=datetime(2026,10,21))


def test_year_boundary_and_leap_day_are_calendar_based(synthetic):
    december = scenario.scenario("TS-Adilabad", "2025-12-31", now=NOW)
    assert [r["month"] for r in december["forecast"]] == [f"2026-{m:02d}" for m in range(1,13)]
    leap = scenario.scenario("TS-Adilabad", "2024-02-29", now=NOW)
    assert leap["forecast"][0]["month"] == "2024-03" and leap["forecast"][-1]["month"] == "2025-02"


def test_route_dispatch_is_isolated_and_has_no_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(scenario, "scenario", lambda *args: calls.append(args) or scenario.unavailable(args[0], args[1], "SYNTHETIC FIXTURE ONLY"))
    client = create_app({"TESTING": True}).test_client()
    result = client.get("/api/research/scenario/TS-Adilabad?months=12&as_of=2024-01-01")
    assert result.status_code == 200 and result.json["product"] == scenario.PRODUCT
    assert calls == [("TS-Adilabad", "2024-01-01", None)]
    for query in ("months=6", "months=12&months=12", "origin_month=2024-01", "as_of=2024-01-01&as_of=2024-01-01"):
        assert client.get("/api/research/scenario/TS-Adilabad?"+query).status_code == 400
    assert len(calls) == 1


def test_source_integrity_failure_blocks_scenario_with_safe_error(monkeypatch):
    def bad(*args):
        raise direct.ResearchContractError("Research artifact checksum mismatch; estimates are blocked.")
    monkeypatch.setattr(direct, "_load_bundle", bad)
    client = create_app({"TESTING": True}).test_client()
    result = client.get("/api/research/scenario/TS-Adilabad?months=12")
    assert result.status_code == 503 and result.json["forecast"] == []
    assert "checksum" in result.json["unavailable_reasons"][0]


def test_real_local_snapshot_smoke_without_active_ml_or_database():
    # This reads the existing frozen source and calculates only the approved
    # seasonal scenario. It neither creates labels nor evaluates accuracy.
    result = scenario.scenario("TS-Adilabad", now=NOW)
    assert result["status"] == "scenario"
    assert result["source"]["last_observed_month"] == "2026-05"
    assert result["source"]["data_age_months"] == 5
    assert result["method"]["observed_calendar_months"] == list(range(1,13))
    assert len(result["forecast"]) == 12
