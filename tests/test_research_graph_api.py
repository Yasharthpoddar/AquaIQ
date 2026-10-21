"""Graph-contract tests use synthetic endpoints and prohibit runtime model/DB IO."""
from copy import deepcopy

import pytest

from api.app import create_app
from models import research_forecast as direct
from models import research_graph as graph


@pytest.fixture(autouse=True)
def no_runtime_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Graph tests must not access a DB, fit, or load an actual model")
    import db.connection
    import xgboost
    from api import district_resolver
    from models import research_horizon, xgboost_model
    monkeypatch.setattr(db.connection, "get_connection", forbidden)
    monkeypatch.setattr(district_resolver, "get_connection", forbidden)
    monkeypatch.setattr(xgboost_model, "get_connection", forbidden)
    monkeypatch.setattr(xgboost.XGBRegressor, "fit", forbidden)
    monkeypatch.setattr(research_horizon, "load_research_model", forbidden)


@pytest.fixture
def synthetic_endpoint():
    value = direct.unavailable_response("SYNTHETIC TEST ONLY", "TS-Adilabad", "2023-12")
    value.update(status="available", output_kind="historical_research", ml_estimate_m=5.5,
                 annual_baseline_m=6.0, observed_target_m=4.75, unavailable_reasons=[],
                 model={"family": "xgboost", "model_sha256": "a" * 64})
    value["source"].update(origin_is_observed=True, origin_is_imputed=False,
                           latest_observed_month="2026-05", input_flags=[])
    return value


@pytest.fixture
def client():
    return create_app({"TESTING": True}).test_client()


def test_exact_twelve_slots_cross_december_and_retain_only_valid_endpoint(synthetic_endpoint):
    value = graph.graph_from_endpoint(synthetic_endpoint)
    assert value["product"] == graph.PRODUCT and value["horizon_months"] == 12
    assert len(value["forecast"]) == 12
    assert [row["month"] for row in value["forecast"]] == [f"2024-{number:02d}" for number in range(1, 13)]
    assert [row["horizon_months"] for row in value["forecast"]] == list(range(1, 13))
    assert all(row["predicted_gwl"] is None and row["annual_baseline_m"] is None for row in value["forecast"][:11])
    assert all(row["unavailable_reasons"] for row in value["forecast"][:11])
    assert value["forecast"][11]["predicted_gwl"] == 5.5
    assert value["forecast"][11]["annual_baseline_m"] == 6.0
    assert value["origin_observed_gwl"] == 6.0
    assert value["target_month"] == "2024-12"
    assert value["forecast_issued_at"] is None
    assert value["source"] == synthetic_endpoint["source"]
    assert value["model"] == synthetic_endpoint["model"]


def test_annual_baseline_does_not_fill_unsupported_months(synthetic_endpoint):
    synthetic_endpoint.update(status="unavailable", ml_estimate_m=None,
                              unavailable_reasons=["Synthetic missing weather"])
    value = graph.graph_from_endpoint(synthetic_endpoint)
    assert all(row["predicted_gwl"] is None for row in value["forecast"])
    assert [row["annual_baseline_m"] for row in value["forecast"]] == [None] * 11 + [6.0]
    assert value["forecast"][-1]["unavailable_reasons"] == ["Synthetic missing weather"]


def test_unknown_origin_never_becomes_today_or_another_district():
    endpoint = direct.unavailable_response("Unsupported district", "GJ-Gandhinagar")
    value = graph.graph_from_endpoint(endpoint)
    assert value["origin_month"] is None and value["target_month"] is None
    assert len(value["forecast"]) == 12
    assert all(row["month"] is None and row["predicted_gwl"] is None and row["annual_baseline_m"] is None
               for row in value["forecast"])


def test_explicit_unsupported_origin_has_calendar_labels_but_no_values():
    value = graph.unavailable_graph("Unsupported district", "GJ-Gandhinagar", "2024-11")
    assert [row["month"] for row in value["forecast"]][:2] == ["2024-12", "2025-01"]
    assert value["forecast"][-1]["month"] == "2025-11"
    assert all(row["predicted_gwl"] is None and row["annual_baseline_m"] is None for row in value["forecast"])


def test_adapter_calls_only_validated_twelve_month_endpoint_once(monkeypatch, synthetic_endpoint):
    calls = []
    monkeypatch.setattr(direct, "research_forecast", lambda *args: calls.append(args) or synthetic_endpoint)
    value = graph.research_graph("TS-Adilabad", "2023-12", "synthetic-descriptor.json")
    assert calls == [("TS-Adilabad", "2023-12", "synthetic-descriptor.json")]
    assert value["forecast"][-1]["predicted_gwl"] == 5.5


def test_new_route_resolves_explicit_twelve_month_product(client, monkeypatch, synthetic_endpoint):
    monkeypatch.setattr(direct, "research_forecast", lambda *args: synthetic_endpoint)
    result = client.get("/api/research/graph/TS-Adilabad?months=12&origin_month=2023-12")
    assert result.status_code == 200
    assert result.json["product"] == graph.PRODUCT
    assert len(result.json["forecast"]) == 12
    assert result.json["forecast"][-1]["month"] == "2024-12"


def test_default_preserves_latest_observed_origin_without_complete_row_fallback(client, monkeypatch):
    calls = []
    endpoint = direct.unavailable_response("Missing current inputs", "TS-Adilabad", "2026-05")
    endpoint.update(annual_baseline_m=6.5)
    endpoint["source"].update(origin_is_observed=True, origin_is_imputed=False, latest_observed_month="2026-05")
    monkeypatch.setattr(direct, "research_forecast", lambda *args: calls.append(args) or endpoint)
    result = client.get("/api/research/graph/TS-Adilabad?months=12")
    assert calls == [("TS-Adilabad", None, None)]
    assert result.json["origin_month"] == "2026-05" and result.json["target_month"] == "2027-05"
    assert result.json["forecast"][0]["month"] == "2026-06"
    assert all(row["predicted_gwl"] is None for row in result.json["forecast"])


@pytest.mark.parametrize("query", ["months=6", "months=1", "months=12.0", "months=12&months=12",
                                  "origin_month=2023-13", "origin_month=2023-12-01", "window=next_six_months",
                                  "origin_month=2023-12&origin_month=2023-12", "as_of=today"])
def test_invalid_graph_requests_fail_before_artifact_access(client, monkeypatch, query):
    monkeypatch.setattr(direct, "research_forecast", lambda *args: pytest.fail("Invalid request accessed artifacts"))
    assert client.get("/api/research/graph/TS-Adilabad?" + query).status_code == 400


@pytest.mark.parametrize("field,value", [("horizon_months", 6), ("horizon_months", True), ("units", "feet"),
                                       ("product", "climate_conditioned_xgboost_monthly"), ("target_month", "2024-06"),
                                       ("ml_estimate_m", float("nan")), ("annual_baseline_m", float("inf"))])
def test_incompatible_or_six_month_result_cannot_satisfy_graph(synthetic_endpoint, field, value):
    synthetic_endpoint[field] = value
    with pytest.raises(direct.ResearchContractError):
        graph.graph_from_endpoint(synthetic_endpoint)


def test_artifact_failure_returns_public_safe_twelve_slot_unavailable(client, monkeypatch):
    def incompatible(*args):
        raise direct.ResearchContractError("Research artifact checksum mismatch; estimates are blocked.")
    monkeypatch.setattr(direct, "research_forecast", incompatible)
    result = client.get("/api/research/graph/TS-Adilabad?months=12&origin_month=2023-12")
    assert result.status_code == 503
    assert len(result.json["forecast"]) == 12
    assert all(row["predicted_gwl"] is None for row in result.json["forecast"])
    assert result.json["forecast"][-1]["month"] == "2024-12"


def test_graph_does_not_modify_existing_endpoint_response(synthetic_endpoint):
    before = deepcopy(synthetic_endpoint)
    graph.graph_from_endpoint(synthetic_endpoint)
    assert synthetic_endpoint == before
