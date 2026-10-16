"""Explicit environment origins and factory overrides retain API behavior."""
import pytest

from api.app import create_app, cors_origins, DEFAULT_CORS_ORIGINS


def test_local_defaults_and_deduplication():
    assert cors_origins(None) == list(DEFAULT_CORS_ORIGINS)
    assert cors_origins("https://example.org, https://example.org") == ["https://example.org"]
    assert cors_origins("") == []


@pytest.mark.parametrize("value", ["*", "null", "file://example.org", "https://example.org/",
    "https://user:pass@example.org", "https://example.org?q=1", "https://example.org#x",
    "https://example.org:99999", "https://exa mple.org", "https://*.example.org", 123,
    ["https://example.org", None]])
def test_invalid_origins_rejected(value):
    with pytest.raises(ValueError):
        cors_origins(value)


def test_environment_allowlist(monkeypatch):
    monkeypatch.setenv("AQUAIQ_CORS_ORIGINS", "https://aquaiq.example.org")
    client = create_app({"TESTING": True}).test_client()
    allowed = client.get("/api/config", headers={"Origin": "https://aquaiq.example.org"})
    denied = client.get("/api/config", headers={"Origin": "https://other.example.org"})
    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "https://aquaiq.example.org"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_factory_override_wins_and_empty_disables_cors(monkeypatch):
    monkeypatch.setenv("AQUAIQ_CORS_ORIGINS", "https://environment.example.org")
    app = create_app({"TESTING": True, "AQUAIQ_CORS_ORIGINS": ""})
    result = app.test_client().get("/api/config", headers={"Origin": "https://environment.example.org"})
    assert result.status_code == 200
    assert "Access-Control-Allow-Origin" not in result.headers


def test_invalid_environment_fails_at_startup(monkeypatch):
    monkeypatch.setenv("AQUAIQ_CORS_ORIGINS", "*")
    with pytest.raises(ValueError):
        create_app()
