"""
GET /api/alerts
Returns monitored districts with their crisis scores.
"""

from flask import Blueprint, jsonify, request
from models.ensemble import compute_crisis_score, get_connection
import pandas as pd

alerts_bp = Blueprint("alerts", __name__)


def _get_monitored_districts():
    """
    Get districts that have actual CGWB GWL data (numeric IDs).
    These are the districts with real groundwater readings.
    """
    try:
        conn = get_connection()
        df = pd.read_sql("""
            SELECT d.district_id, d.district_name, d.state, MAX(f.gwl_current) as peak_gwl
            FROM districts d
            JOIN features f ON d.district_id = f.district_id
            WHERE f.gwl_current IS NOT NULL AND f.gwl_current != 'NaN'
            GROUP BY d.district_id, d.district_name, d.state
            HAVING COUNT(f.gwl_current) >= 12
            ORDER BY peak_gwl DESC
            LIMIT 30
        """, conn)
        conn.close()

        if len(df) > 0:
            return [
                {"id": row["district_id"], "name": row["district_name"], "state": row["state"]}
                for _, row in df.iterrows()
            ]
    except Exception as e:
        print(f"Error fetching districts: {e}")

    return []


@alerts_bp.route("/alerts", methods=["GET"])
def get_alerts():
    tier_filter = request.args.get("tier")
    monitored = _get_monitored_districts()
    alerts = []

    for d in monitored:
        try:
            score_data = compute_crisis_score(d["id"])
            score = score_data.get("crisis_score")
            tier = score_data.get("tier")
            estimate_type = score_data.get("estimate_type", "district_level")

            if score is None:
                score = 50
                tier = "Watch"
        except Exception:
            score = 50
            tier = "Watch"
            estimate_type = "zone_fallback"

        if tier == "Crisis":
            rec = "Declare water-stressed zone -- emergency conservation and supply measures."
        elif tier == "Warning":
            rec = "Restrict new extraction permits and enforce conservation measures."
        elif tier == "Watch":
            rec = "Increase monitoring frequency and promote rainwater harvesting."
        else:
            rec = "Continue routine monitoring."

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

    alerts.sort(key=lambda x: x["score"], reverse=True)

    return jsonify({
        "count": len(alerts),
        "alerts": alerts,
    })
