"""
GET /api/alerts
Returns all districts in Warning or Crisis tier.
"""

from flask import Blueprint, jsonify, request

alerts_bp = Blueprint("alerts", __name__)


@alerts_bp.route("/alerts", methods=["GET"])
def get_alerts():
    """
    Query params: ?tier=Crisis (optional filter)
    Response:
    {
      "count": 2,
      "alerts": [
        {
          "district_id": "GJ-Mehsana",
          "name": "Mehsana",
          "state": "Gujarat",
          "score": 88,
          "tier": "Crisis",
          "recommendation": "..."
        },
        ...
      ]
    }
    """
    tier_filter = request.args.get("tier")

    # Stub — replaced with real DB query in Week 9
    alerts = [
        {
            "district_id": "GJ-Mehsana",
            "name": "Mehsana",
            "state": "Gujarat",
            "score": 88,
            "tier": "Crisis",
            "recommendation": "Declare water-stressed zone.",
        },
        {
            "district_id": "HR-Kurukshetra",
            "name": "Kurukshetra",
            "state": "Haryana",
            "score": 91,
            "tier": "Crisis",
            "recommendation": "Declare water-stressed zone.",
        },
        {
            "district_id": "RJ-Jaipur",
            "name": "Jaipur",
            "state": "Rajasthan",
            "score": 72,
            "tier": "Warning",
            "recommendation": "Restrict new extraction permits.",
        },
    ]

    if tier_filter:
        alerts = [a for a in alerts if a["tier"].lower() == tier_filter.lower()]

    return jsonify({
        "count": len(alerts),
        "alerts": alerts,
    })
