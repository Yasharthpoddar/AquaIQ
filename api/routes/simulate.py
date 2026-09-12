"""
POST /api/simulate
What-if policy simulator: adjusts inputs and returns new crisis score.
"""

from flask import Blueprint, jsonify, request

simulate_bp = Blueprint("simulate", __name__)


@simulate_bp.route("/simulate", methods=["POST"])
def simulate():
    """
    Request body:
    {
      "district_id": "RJ-Jaipur",
      "rainfall_change_pct": -20,
      "extraction_change_pct": 10
    }

    Response:
    {
      "district_id": "RJ-Jaipur",
      "baseline_score": 72,
      "simulated_score": 81,
      "baseline_tier": "Warning",
      "simulated_tier": "Crisis",
      "delta": +9
    }
    """
    data = request.get_json() or {}
    district_id = data.get("district_id", "unknown")
    rainfall_change = data.get("rainfall_change_pct", 0)
    extraction_change = data.get("extraction_change_pct", 0)

    # Stub — replaced with real FIS re-computation in Week 9
    baseline = 72
    delta = (rainfall_change * -0.3) + (extraction_change * 0.5)
    simulated = max(0, min(100, baseline + delta))

    def score_to_tier(s):
        if s >= 81: return "Crisis"
        if s >= 61: return "Warning"
        if s >= 31: return "Watch"
        return "Safe"

    return jsonify({
        "district_id": district_id,
        "baseline_score": baseline,
        "simulated_score": round(simulated),
        "baseline_tier": score_to_tier(baseline),
        "simulated_tier": score_to_tier(simulated),
        "delta": round(simulated - baseline),
    })
