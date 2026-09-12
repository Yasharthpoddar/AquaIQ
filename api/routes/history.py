"""
GET /api/history/<district_id>
Returns historical GWL + rainfall data for a district.
"""

from flask import Blueprint, jsonify, request

history_bp = Blueprint("history", __name__)


@history_bp.route("/history/<district_id>", methods=["GET"])
def get_history(district_id):
    """
    Query params: ?start=2020-01&end=2024-12
    Response:
    {
      "district_id": "RJ-Jaipur",
      "data": [
        {"date": "2024-01", "gwl": 7.2, "rainfall": 12.5},
        ...
      ]
    }
    """
    start = request.args.get("start", "2020-01")
    end = request.args.get("end", "2024-12")

    # Stub — replaced with real DB query in Week 9
    return jsonify({
        "district_id": district_id,
        "start": start,
        "end": end,
        "data": [
            {"date": "2024-01", "gwl": 7.2, "rainfall": 12.5},
            {"date": "2024-02", "gwl": 7.5, "rainfall": 8.3},
            {"date": "2024-03", "gwl": 8.1, "rainfall": 4.1},
        ],
    })
