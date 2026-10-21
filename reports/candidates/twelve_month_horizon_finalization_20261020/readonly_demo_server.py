"""Temporary localhost demonstration: file-only routes, no DB access or fitting.

This is a development verification helper, not a production deployment server.
Use the Vite research page on port 5181 with VITE_API_URL=http://127.0.0.1:5051.
"""
from contextlib import ExitStack
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def forbidden(*args, **kwargs):
    raise RuntimeError("The research demonstration forbids database access and fitting")


if __name__ == "__main__":
    from api.app import create_app
    from flask import request
    with ExitStack() as guards:
        for name in ("psycopg2.connect", "db.connection.get_connection",
                     "api.district_resolver.get_connection", "models.xgboost_model.get_connection",
                     "xgboost.XGBRegressor.fit"):
            guards.enter_context(patch(name, forbidden))
        app = create_app({"AQUAIQ_CORS_ORIGINS": "http://127.0.0.1:5181"})

        @app.before_request
        def allow_research_only():
            if request.method not in {"GET", "OPTIONS"} or not (
                request.path in {"/", "/api/config", "/api/research/forecast"}
                or request.path.startswith("/api/research/forecast/")
            ):
                return {"status": "unavailable", "error": "Legacy routes are excluded from this read-only demonstration."}, 403

        app.run(host="127.0.0.1", port=5051, debug=False, use_reloader=False)
