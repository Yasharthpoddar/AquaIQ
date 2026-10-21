"""Synthetic graph responses; verify the demo guard without opening a socket/DB."""
import pytest

from models import research_graph
from reports.candidates.twelve_month_graph_only_20261021.demo_server import guarded_app


def test_demo_allows_only_file_backed_graph_and_preserves_legacy_403(monkeypatch):
    calls = []

    def synthetic_graph(*args):
        calls.append(args)
        return research_graph.unavailable_graph("SYNTHETIC FIXTURE ONLY", "TS-Adilabad", "2024-12")

    monkeypatch.setattr(research_graph, "research_graph", synthetic_graph)
    with guarded_app() as app:
        client = app.test_client()
        graph = client.get("/api/research/graph/TS-Adilabad?months=12")
        assert graph.status_code == 200 and len(graph.json["forecast"]) == 12
        assert graph.json["forecast"][0]["month"] == "2025-01"
        assert graph.json["forecast"][-1]["month"] == "2025-12"
        assert len(calls) == 1
        scores = client.get("/api/scores", headers={"Origin": "http://127.0.0.1:5181"})
        assert scores.status_code == 403
        assert scores.json["error"] == "Legacy routes are excluded from this read-only demonstration."
        assert scores.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5181"
        assert len(calls) == 1


@pytest.mark.parametrize("method,path", [("get", "/api/district/TS-Adilabad"),
                                       ("get", "/api/predict/TS-Adilabad"),
                                       ("post", "/api/research/graph/TS-Adilabad"),
                                       ("post", "/api/simulate")])
def test_demo_does_not_enable_legacy_or_mutating_routes(method, path):
    with guarded_app() as app:
        response = getattr(app.test_client(), method)(path)
        assert response.status_code == 403
