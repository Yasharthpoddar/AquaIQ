"""
AquaIQ — Flask Application Factory (Week 6, Yasharth)
-------------------------------------------------------
App factory pattern with blueprint registration for each API route group.
Registers primary twelve-month research and separate legacy API products.

Course mapping: CS301 — Web Development.

Run:
    flask --app api.app run --debug
    # or
    python -m api.app
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask
from flask_cors import CORS

ROOT = Path(__file__).parent.parent

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000", "http://localhost:5173",
    "http://127.0.0.1:3000", "http://127.0.0.1:5173",
)


def cors_origins(value):
    """Accept explicit web origins; an empty setting disables cross-origin access."""
    if value is None:
        return list(DEFAULT_CORS_ORIGINS)
    if isinstance(value, str):
        origins = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        origins = [item.strip() for item in value]
    else:
        raise ValueError("AQUAIQ_CORS_ORIGINS must be a comma-separated string or list of web origins")
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            _ = parsed.port  # Parse and range-check a supplied port.
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path
                    or parsed.query or parsed.fragment or origin.endswith(":")
                    or any(char.isspace() for char in origin) or "*" in origin or "\\" in origin):
                raise ValueError
        except ValueError:
            raise ValueError("CORS origins must be explicit http(s)://host[:port] origins without paths or wildcards") from None
    return list(dict.fromkeys(origins))


def create_app(config_override=None):
    """Application factory — creates and configures the Flask app."""
    app = Flask(__name__)

    # Load config
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "aquaiq-dev-key"),
        POSTGRES_HOST=os.getenv("POSTGRES_HOST", "localhost"),
        POSTGRES_PORT=int(os.getenv("POSTGRES_PORT", 5432)),
        POSTGRES_DB=os.getenv("POSTGRES_DB", "aquaiq"),
        POSTGRES_USER=os.getenv("POSTGRES_USER", "aquaiq_user"),
        POSTGRES_PASSWORD=os.getenv("POSTGRES_PASSWORD", ""),
        AQUAIQ_CORS_ORIGINS=os.getenv("AQUAIQ_CORS_ORIGINS"),
        RESEARCH_FORECAST_CONFIG_PATH=os.getenv("AQUAIQ_RESEARCH_CONFIG"),
    )

    if config_override:
        app.config.update(config_override)

    # A reverse-proxy deployment uses an empty setting and same-origin /api.
    origins = cors_origins(app.config["AQUAIQ_CORS_ORIGINS"])
    app.config["AQUAIQ_CORS_ORIGINS"] = origins
    CORS(app, resources={r"/api/*": {"origins": origins}})

    # Register blueprints
    from api.routes.predict import predict_bp
    from api.routes.district import district_bp
    from api.routes.history import history_bp
    from api.routes.alerts import alerts_bp
    from api.routes.simulate import simulate_bp
    from api.routes.health import health_bp
    from api.routes.scores import scores_bp
    from api.routes.research import research_bp

    app.register_blueprint(predict_bp, url_prefix="/api")
    app.register_blueprint(district_bp, url_prefix="/api")
    app.register_blueprint(history_bp, url_prefix="/api")
    app.register_blueprint(alerts_bp, url_prefix="/api")
    app.register_blueprint(simulate_bp, url_prefix="/api")
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(scores_bp, url_prefix="/api")
    app.register_blueprint(research_bp, url_prefix="/api")

    # Root route
    @app.route("/")
    def index():
        return {
            "name": "AquaIQ API",
            "version": "1.0.0",
            "primary_research_horizon_months": 12,
            "primary_research_product": "direct_12month_research",
            "prospective_skill_verified": False,
            "endpoints": [
                "/api/config",
                "/api/scores",
                "/api/predict/<district_id>",
                "/api/predict/climate-12m/<district_id>",
                "/api/research/forecast",
                "/api/research/forecast/<district_id>",
                "/api/research/graph/<district_id>",
                "/api/research/scenario/<district_id>",
                "/api/district/<district_id>",
                "/api/history/<district_id>",
                "/api/alerts",
                "/api/simulate",
                "/api/health",
            ],
        }

    return app


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    app = create_app()
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() in ("true", "1")
    port = int(os.getenv("FLASK_PORT", 5000))
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=debug_mode)
