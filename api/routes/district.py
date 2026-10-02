"""
GET /api/district/<district_id>
Returns district metadata + crisis score + data readiness.
"""

from flask import Blueprint, jsonify, request
from models.ensemble import compute_crisis_score
from models.data_readiness import get_data_readiness
from api.district_resolver import resolve_district_id, get_district_metadata

district_bp = Blueprint("district", __name__)

@district_bp.route("/district/<district_id>", methods=["GET"])
def get_district(district_id):
    """Returns district metadata + crisis score + data readiness."""
    try:
        # Resolve to the ID that has actual data
        resolved_id = resolve_district_id(district_id)
        meta = get_district_metadata(district_id)

        crisis_data = compute_crisis_score(resolved_id)
        readiness = get_data_readiness(resolved_id)

        return jsonify({
            "district_id": district_id,
            "resolved_id": resolved_id,
            "metadata": meta,
            "crisis_score": crisis_data["crisis_score"],
            "tier": crisis_data["tier"],
            "estimate_type": crisis_data.get("estimate_type", "district_level"),
            "data_readiness": readiness,
            "ensemble_components": crisis_data["components"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
