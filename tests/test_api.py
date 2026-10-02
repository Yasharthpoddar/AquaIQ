"""
AquaIQ API test suite.
Tests all 5 endpoints + health check against the live database.
"""

import pytest
from api.app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"


def test_district_endpoint_success(client):
    response = client.get("/api/district/RJ-Jaipur")
    assert response.status_code == 200
    data = response.json
    assert "district_id" in data
    assert data["district_id"] == "RJ-Jaipur"
    assert "crisis_score" in data
    assert "data_readiness" in data
    assert "estimate_type" in data


def test_predict_endpoint_success(client):
    response = client.get("/api/predict/RJ-Jaipur")
    assert response.status_code == 200
    data = response.json
    assert "forecast" in data
    assert len(data["forecast"]) == 6
    assert "crisis_score" in data
    assert "estimate_type" in data


def test_history_endpoint_success(client):
    response = client.get("/api/history/RJ-Jaipur?start=2020-01&end=2024-12")
    assert response.status_code == 200
    data = response.json
    assert data["district_id"] == "RJ-Jaipur"
    assert "data" in data
    assert isinstance(data["data"], list)


def test_alerts_endpoint_success(client):
    response = client.get("/api/alerts")
    assert response.status_code == 200
    data = response.json
    assert "alerts" in data
    assert "count" in data


def test_alerts_endpoint_with_filter(client):
    response = client.get("/api/alerts?tier=Crisis")
    assert response.status_code == 200
    data = response.json
    for alert in data["alerts"]:
        assert alert["tier"] == "Crisis"


def test_simulate_endpoint_success(client):
    payload = {
        "district_id": "RJ-Jaipur",
        "rainfall_change_pct": -20,
        "extraction_change_pct": 10
    }
    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 200
    data = response.json
    assert data["district_id"] == "RJ-Jaipur"
    assert "simulated_score" in data
    assert "delta" in data


def test_404_error(client):
    response = client.get("/api/nonexistent")
    assert response.status_code == 404


def test_predict_has_ensemble_weights(client):
    """Ensemble weights should come from config.yaml, not be hardcoded."""
    response = client.get("/api/predict/RJ-Jaipur")
    assert response.status_code == 200
    data = response.json
    assert "ensemble_weights" in data
    weights = data["ensemble_weights"]
    assert "linear_regression_trend" in weights
    assert "xgboost_risk" in weights
    assert "drought_frequency" in weights


def test_district_has_estimate_type(client):
    """estimate_type should be present in district response (P3 requirement)."""
    response = client.get("/api/district/RJ-Jaipur")
    assert response.status_code == 200
    data = response.json
    assert data["estimate_type"] in ["district_level", "zone_fallback", "insufficient_data"]
