"""Production serving rejects empty databases and mismatched publications."""
from unittest.mock import Mock

import pytest

from deploy.serve import validate_release, validate_environment


def setup_release(monkeypatch, *, health_status=200, rows=(725, (1000, 725), 1000), total=725):
    health = Mock(status_code=health_status, json={"status": "healthy"})
    scores = Mock(status_code=200, json={"status": "success", "total": total,
                                       "districts": [{}] * total})
    app = Mock()
    app.test_client.return_value.get.side_effect = [health, scores]
    connection, cursor = Mock(), Mock()
    connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
    connection.cursor.return_value.__exit__ = Mock(return_value=False)
    cursor.fetchone.side_effect = [(rows[0],), rows[1], (rows[2],)]
    monkeypatch.setattr("db.connection.get_connection", lambda: connection)
    monkeypatch.setattr("models.ensemble.feature_generation", lambda: "generation")
    return app, connection


def test_complete_matching_release(monkeypatch):
    app, connection = setup_release(monkeypatch)
    assert validate_release(app)["districts"] == 725
    connection.close.assert_called_once()


def test_missing_models_reject_startup(monkeypatch):
    app, _ = setup_release(monkeypatch, health_status=503)
    with pytest.raises(RuntimeError, match="all three matching model"):
        validate_release(app)


@pytest.mark.parametrize("rows", [(0, (0, 0), 0), (725, (0, 0), 100), (725, (1000, 724), 100), (725, (1000, 725), 0)])
def test_empty_or_incomplete_database_rejected(monkeypatch, rows):
    app, connection = setup_release(monkeypatch, rows=rows)
    with pytest.raises(RuntimeError, match="Restore"):
        validate_release(app)
    connection.close.assert_called_once()


def test_incomplete_score_publication_rejected(monkeypatch):
    app, _ = setup_release(monkeypatch, total=724)
    with pytest.raises(RuntimeError, match="complete scoring run"):
        validate_release(app)


@pytest.mark.parametrize("secret,password", [
    ("replace_with_private_random_value", "private-db-value"),
    ("e14d7c3f9a662b80f0ae49d1794b7e12", "replace_locally"),
    (" " * 40, "private-db-value"),
    ("e14d7c3f9a662b80f0ae49d1794b7e12", "   "),
    (" e14d7c3f9a662b80f0ae49d1794b7e12", "private-db-value"),
    ("e14d7c3f9a662b80f0ae49d1794b7e12", "password"),
])
def test_example_and_whitespace_credentials_rejected(secret, password):
    with pytest.raises(ValueError, match="non-placeholder"):
        validate_environment({"SECRET_KEY": secret, "POSTGRES_PASSWORD": password})


def test_private_credentials_accepted():
    validate_environment({"SECRET_KEY": "e14d7c3f9a662b80f0ae49d1794b7e12", "POSTGRES_PASSWORD": "private-db-value"})
