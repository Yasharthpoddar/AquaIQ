"""
GET /api/predict/<district_id>
Returns 6-month GWL forecast + crisis score for a district.
"""

from flask import Blueprint, jsonify, request
from models.ensemble import compute_crisis_score

predict_bp = Blueprint("predict", __name__)


@predict_bp.route("/predict/<district_id>", methods=["GET"])
def get_prediction(district_id):
    """
    Response:
    {
      "district_id": "RJ-Jaipur",
      "crisis_score": 72,
      "tier": "Warning",
      "forecast": [
        {"month": "2027-01", "predicted_gwl": 8.5},
        ...
      ],
      "ensemble_weights": {
        "linear_regression_trend": 0.25,
        "xgboost_risk": 0.50,
        "drought_frequency": 0.25
      },
      "recommendation": "Restrict new extraction permits..."
    }
    """
    try:
        crisis_data = compute_crisis_score(district_id)
        
        # Stub the forecast array for now until XGBoost pipeline is fully run
        forecast = []
        base_gwl = 8.5
        for i in range(1, 7):
            forecast.append({
                "month": f"2027-0{i}",
                "predicted_gwl": round(base_gwl + (i * 0.4), 1)
            })
            
        return jsonify({
            "district_id": district_id,
            "crisis_score": crisis_data["crisis_score"],
            "tier": crisis_data["tier"],
            "forecast": forecast,
            "ensemble_weights": crisis_data["ensemble_weights"],
            "recommendation": "Restrict new extraction permits and enforce conservation measures.",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
