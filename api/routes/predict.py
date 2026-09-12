"""
GET /api/predict/<district_id>
Returns 6-month GWL forecast + crisis score for a district.
"""

from flask import Blueprint, jsonify, request

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
    # Stub — replaced with real model inference in Week 9
    return jsonify({
        "district_id": district_id,
        "crisis_score": 72,
        "tier": "Warning",
        "forecast": [
            {"month": "2027-01", "predicted_gwl": 8.5},
            {"month": "2027-02", "predicted_gwl": 8.9},
            {"month": "2027-03", "predicted_gwl": 9.4},
            {"month": "2027-04", "predicted_gwl": 10.1},
            {"month": "2027-05", "predicted_gwl": 10.8},
            {"month": "2027-06", "predicted_gwl": 11.2},
        ],
        "ensemble_weights": {
            "linear_regression_trend": 0.25,
            "xgboost_risk": 0.50,
            "drought_frequency": 0.25,
        },
        "recommendation": "Restrict new extraction permits and enforce conservation measures.",
    })
