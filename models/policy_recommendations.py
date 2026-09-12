"""
AquaIQ — Policy Recommendation Lookup Table (Week 3, Ayush)
--------------------------------------------------------------
One suggested action per risk tier (Safe/Watch/Warning/Crisis).
Used by the alert system and the /simulate endpoint's response.

This is a static lookup — the recommendations don't change based on
district-specific data. A future version could incorporate district-level
factors (crop type, irrigation infrastructure) but that's out of scope.
"""

# Each tier maps to:
#   - severity: human-readable label
#   - color: hex for dashboard display
#   - action: short policy recommendation
#   - detail: expanded explanation for the alert/report
#   - urgency: days within which action is recommended

POLICY_RECOMMENDATIONS = {
    "Safe": {
        "severity": "Normal",
        "color": "#22c55e",
        "action": "Continue monitoring — no intervention needed.",
        "detail": (
            "Groundwater levels are within normal range for this district. "
            "Continue routine monitoring of well readings. Maintain existing "
            "water conservation practices and seasonal crop planning."
        ),
        "urgency_days": None,
    },
    "Watch": {
        "severity": "Elevated",
        "color": "#f59e0b",
        "action": "Increase monitoring frequency and review extraction permits.",
        "detail": (
            "Groundwater levels show early signs of stress. Recommend: "
            "(1) Increase CGWB monitoring from quarterly to monthly for this district. "
            "(2) Review and audit active groundwater extraction permits. "
            "(3) Issue advisory to farmers on water-efficient irrigation practices. "
            "(4) Begin planning rainwater harvesting infrastructure for next monsoon."
        ),
        "urgency_days": 90,
    },
    "Warning": {
        "severity": "High",
        "color": "#ef4444",
        "action": "Restrict new extraction permits and enforce conservation measures.",
        "detail": (
            "Groundwater depletion rate exceeds sustainable thresholds. Recommend: "
            "(1) Freeze new groundwater extraction permits in this district. "
            "(2) Mandate micro-irrigation (drip/sprinkler) for existing permit holders. "
            "(3) Deploy tanker water supply planning for worst-affected blocks. "
            "(4) Initiate district-level water budgeting exercise with Gram Panchayats. "
            "(5) Fast-track pending check dam and percolation tank projects."
        ),
        "urgency_days": 30,
    },
    "Crisis": {
        "severity": "Critical",
        "color": "#dc2626",
        "action": "Declare water-stressed zone — emergency conservation and supply measures.",
        "detail": (
            "Groundwater is critically depleted. Immediate action required: "
            "(1) Declare district as water-stressed zone under CGWB guidelines. "
            "(2) Enforce mandatory reduction in agricultural groundwater extraction. "
            "(3) Activate emergency tanker supply and rationing protocols. "
            "(4) Prioritize drinking water supply over irrigation allocation. "
            "(5) Coordinate with NDRF/state disaster management for contingency planning. "
            "(6) Accelerate artificial recharge projects (recharge wells, farm ponds)."
        ),
        "urgency_days": 7,
    },
}


def get_recommendation(tier: str) -> dict:
    """Get the policy recommendation for a given risk tier."""
    tier = tier.strip().capitalize()
    if tier not in POLICY_RECOMMENDATIONS:
        raise ValueError(f"Unknown tier '{tier}'. Must be one of: {list(POLICY_RECOMMENDATIONS.keys())}")
    return POLICY_RECOMMENDATIONS[tier]


def format_alert_message(district_name: str, score: float, tier: str) -> str:
    """Format a human-readable alert message for a district."""
    rec = get_recommendation(tier)
    return (
        f"[{rec['severity'].upper()}] {district_name} — "
        f"AquaIQ Crisis Score: {score:.0f}/100 ({tier})\n"
        f"Recommended action: {rec['action']}"
    )


if __name__ == "__main__":
    print("AquaIQ — Policy Recommendation Lookup Table\n")
    print(f"{'Tier':<10} {'Severity':<10} {'Urgency':<12} Action")
    print("-" * 80)
    for tier, rec in POLICY_RECOMMENDATIONS.items():
        urgency = f"{rec['urgency_days']}d" if rec["urgency_days"] else "—"
        print(f"{tier:<10} {rec['severity']:<10} {urgency:<12} {rec['action']}")

    print("\n\nSample alerts:")
    print("-" * 80)
    for district, score, tier in [
        ("Jaipur", 15, "Safe"),
        ("Mehsana", 48, "Watch"),
        ("Mahbubnagar", 72, "Warning"),
        ("Kurukshetra", 91, "Crisis"),
    ]:
        print(format_alert_message(district, score, tier))
        print()
