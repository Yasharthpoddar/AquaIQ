"""
AquaIQ — Flask Application Factory (Week 6, Yasharth)
-------------------------------------------------------
App factory pattern with blueprint registration for each API route group.
Matches the 5 endpoints defined in api_spec.md.

Course mapping: CS301 — Web Development.

Run:
    flask --app api.app run --debug
    # or
    python -m api.app
"""

import os
from pathlib import Path

from flask import Flask
from flask_cors import CORS

ROOT = Path(__file__).parent.parent


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
    )

    if config_override:
        app.config.update(config_override)

    # CORS for React dashboard
    CORS(app, origins=["http://localhost:3000", "http://localhost:5173"])

    # Register blueprints
    from api.routes.predict import predict_bp
    from api.routes.history import history_bp
    from api.routes.alerts import alerts_bp
    from api.routes.simulate import simulate_bp
    from api.routes.health import health_bp

    app.register_blueprint(predict_bp, url_prefix="/api")
    app.register_blueprint(history_bp, url_prefix="/api")
    app.register_blueprint(alerts_bp, url_prefix="/api")
    app.register_blueprint(simulate_bp, url_prefix="/api")
    app.register_blueprint(health_bp, url_prefix="/api")

    # Root route
    @app.route("/")
    def index():
        return {
            "name": "AquaIQ API",
            "version": "1.0.0",
            "endpoints": [
                "/api/predict/<district_id>",
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
    app.run(host="0.0.0.0", port=5000, debug=True)
