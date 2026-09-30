from flask import Blueprint, jsonify, request
from models.ensemble import compute_crisis_score
from models.data_readiness import get_data_readiness

district_bp = Blueprint("district", __name__)

@district_bp.route("/district/<district_id>", methods=["GET"])
def get_district(district_id):
    """
    Returns district metadata + crisis score + data readiness.
    """
    try:
        crisis_data = compute_crisis_score(district_id)
        readiness = get_data_readiness(district_id)
        
        return jsonify({
            "district_id": district_id,
            "metadata": {
                "name": district_id.split("-")[-1],  # mock for now
                "state": district_id.split("-")[0]
            },
            "crisis_score": crisis_data["crisis_score"],
            "tier": crisis_data["tier"],
            "data_readiness": readiness,
            "ensemble_components": crisis_data["components"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
