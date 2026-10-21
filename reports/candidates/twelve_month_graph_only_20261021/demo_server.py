"""Local file-only graph demo; keep legacy routes, DB and fitting blocked.

This new helper preserves the previous demonstration helper unchanged. It adds
only the validated file-backed research graph route to the demo allowlist.
It is not an authentication change or production deployment configuration.
"""
from contextlib import ExitStack, contextmanager
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def forbidden(*args, **kwargs):
    raise RuntimeError("The file-only demo forbids database access and fitting")


@contextmanager
def guarded_app():
    from api.app import create_app
    from flask import request
    with ExitStack() as guards:
        for name in ("psycopg2.connect", "db.connection.get_connection",
                     "api.district_resolver.get_connection", "models.xgboost_model.get_connection",
                     "xgboost.XGBRegressor.fit"):
            guards.enter_context(patch(name, forbidden))
        app = create_app({"AQUAIQ_CORS_ORIGINS": "http://127.0.0.1:5181"})

        @app.before_request
        def allow_file_only_research():
            eligible = (request.path in {"/", "/api/config", "/api/research/forecast"}
                        or request.path.startswith("/api/research/forecast/")
                        or request.path.startswith("/api/research/graph/"))
            if request.method not in {"GET", "OPTIONS"} or not eligible:
                return {"status": "unavailable", "error": "Legacy routes are excluded from this read-only demonstration."}, 403

        yield app


if __name__ == "__main__":
    with guarded_app() as app:
        app.run(host="127.0.0.1", port=5051, debug=False, use_reloader=False)
