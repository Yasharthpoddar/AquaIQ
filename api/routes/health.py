"""
GET /api/health
Health check endpoint — returns API status and DB connectivity.
"""

import os
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """
    Response:
    {
      "status": "healthy",
      "database": "connected" | "disconnected",
      "model_loaded": true | false,
      "version": "1.0.0"
    }
    """
    db_status = "disconnected"
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "aquaiq"),
            user=os.getenv("POSTGRES_USER", "aquaiq_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
        )
        conn.close()
        db_status = "connected"
    except Exception:
        pass

    # Check if XGBoost model checkpoint exists
    from pathlib import Path
    checkpoint = Path(__file__).parent.parent.parent / "models" / "checkpoints" / "xgboost_v1.json"
    model_loaded = checkpoint.exists()

    return jsonify({
        "status": "healthy",
        "database": db_status,
        "model_loaded": model_loaded,
        "version": "1.0.0",
    })
