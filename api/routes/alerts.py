"""
GET /api/alerts
Returns monitored districts with their crisis scores.
"""

from flask import Blueprint, jsonify, request
from models.ensemble import compute_crisis_score, get_connection
import pandas as pd
from functools import lru_cache

alerts_bp = Blueprint("alerts", __name__)


@lru_cache(maxsize=1)
def _get_monitored_districts():
    """
    Get a diverse pool of districts that have actual CGWB GWL data.
    We pull from three groups to maximise score diversity:
      - top by peak GWL (historically deep)
      - top by most-recent GWL (currently deep)
      - a random spread for variety
    """
    try:
        conn = get_connection()
        df = pd.read_sql("""
            WITH base AS (
                SELECT d.district_id, d.district_name, d.state,
                       MAX(f.gwl_current) AS peak_gwl,
                       (ARRAY_AGG(f.gwl_current ORDER BY f.date DESC))[1] AS latest_gwl
                FROM districts d
                JOIN features f ON d.district_id = f.district_id
                WHERE f.gwl_current IS NOT NULL AND CAST(f.gwl_current AS TEXT) != 'NaN'
                GROUP BY d.district_id, d.district_name, d.state
                HAVING COUNT(f.gwl_current) >= 12
            ),
            by_peak AS   (SELECT * FROM base ORDER BY peak_gwl   DESC LIMIT 50),
            by_latest AS (SELECT * FROM base ORDER BY latest_gwl DESC LIMIT 50),
            by_rand AS   (SELECT * FROM base ORDER BY RANDOM()        LIMIT 50)
            SELECT DISTINCT ON (district_id) * FROM (
                SELECT * FROM by_peak
                UNION SELECT * FROM by_latest
                UNION SELECT * FROM by_rand
            ) combined
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
    
    tier_limits = {"Safe": 5, "Watch": 5, "Warning": 2, "Crisis": 2}
    buckets = {t: [] for t in tier_limits}
    filtered_alerts = []

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

        alert_obj = {
            "district_id": d["id"],
            "name": d["name"],
            "state": d["state"],
            "score": score,
            "tier": tier,
            "estimate_type": estimate_type,
            "recommendation": rec,
        }

        # Early exit logic to drastically speed up loading
        if tier_filter:
            if tier.lower() == tier_filter.lower():
                filtered_alerts.append(alert_obj)
                if len(filtered_alerts) >= 15:  # Cap at 15 for a specific tier filter
                    break
        else:
            if tier in buckets and len(buckets[tier]) < tier_limits[tier]:
                buckets[tier].append(alert_obj)
            
            # Stop if we have fulfilled all our quotas (5, 5, 2, 2)
            if all(len(b) >= tier_limits[t] for t, b in buckets.items()):
                break

    if not tier_filter:
        balanced = []
        for t, limit in tier_limits.items():
            balanced.extend(sorted(buckets[t], key=lambda x: x["score"], reverse=True))
        alerts = sorted(balanced, key=lambda x: x["score"], reverse=True)
    else:
        alerts = sorted(filtered_alerts, key=lambda x: x["score"], reverse=True)

    return jsonify({
        "count": len(alerts),
        "alerts": alerts,
    })
