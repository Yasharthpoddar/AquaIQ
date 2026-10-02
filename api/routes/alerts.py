"""
GET /api/alerts
Returns all districts in Warning or Crisis tier.
"""

from flask import Blueprint, jsonify, request
from models.ensemble import compute_crisis_score, get_connection
from api.district_resolver import resolve_district_id, get_district_metadata

alerts_bp = Blueprint("alerts", __name__)


def _get_monitored_districts():
    """
    Get a representative set of districts to monitor for alerts.
    Picks districts with the most data across different states.
    """
    try:
        conn = get_connection()
        import pandas as pd
        df = pd.read_sql("""
            SELECT d.district_id, d.district_name, d.state,
                   COUNT(f.id) as data_points
            FROM districts d
            JOIN features f ON d.district_id = f.district_id
            WHERE f.gwl_current IS NOT NULL
            GROUP BY d.district_id, d.district_name, d.state
            ORDER BY data_points DESC
            LIMIT 20
        """, conn)
        conn.close()

        if len(df) > 0:
            return [
                {"id": row["district_id"], "name": row["district_name"], "state": row["state"]}
                for _, row in df.iterrows()
            ]
    except Exception:
        pass

    # Fallback to known districts
    return [
        {"id": "GJ-Mehsana", "name": "Mehsana", "state": "Gujarat"},
        {"id": "HR-Kurukshetra", "name": "Kurukshetra", "state": "Haryana"},
        {"id": "RJ-Jaipur", "name": "Jaipur", "state": "Rajasthan"},
        {"id": "PB-Ludhiana", "name": "Ludhiana", "state": "Punjab"},
    ]


@alerts_bp.route("/alerts", methods=["GET"])
def get_alerts():
    """
    Query params: ?tier=Crisis (optional filter)
    Response:
    {
      "count": 2,
      "alerts": [
        {
          "district_id": "102",
          "name": "Jaipur",
          "state": "Rajasthan",
          "score": 72,
          "tier": "Warning",
          "estimate_type": "district_level",
          "recommendation": "..."
        },
        ...
      ]
    }
    """
    tier_filter = request.args.get("tier")

    monitored_districts = _get_monitored_districts()
    alerts = []

    for d in monitored_districts:
        try:
            resolved_id = resolve_district_id(d["id"])
            score_data = compute_crisis_score(resolved_id)
            score = score_data["crisis_score"]
            tier = score_data["tier"]
            estimate_type = score_data.get("estimate_type", "district_level")

            if score is None:
                continue
        except Exception:
            continue

        # Generate policy recommendation
        if tier == "Crisis":
            rec = "Declare water-stressed zone -- emergency conservation and supply measures."
        elif tier == "Warning":
            rec = "Restrict new extraction permits and enforce conservation measures."
        else:
            rec = "Monitor conditions and promote rainwater harvesting."

        if tier in ["Warning", "Crisis"]:
            alerts.append({
                "district_id": d["id"],
                "name": d["name"],
                "state": d["state"],
                "score": score,
                "tier": tier,
                "estimate_type": estimate_type,
                "recommendation": rec,
            })

    if tier_filter:
        alerts = [a for a in alerts if a["tier"].lower() == tier_filter.lower()]

    # Sort by score descending
    alerts.sort(key=lambda x: x["score"], reverse=True)

    return jsonify({
        "count": len(alerts),
        "alerts": alerts,
    })
