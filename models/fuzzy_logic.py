"""
AquaIQ -- Fuzzy Inference System Design (Week 3, Ayush)
---------------------------------------------------------
Mamdani Fuzzy Inference System for crisis scoring using scikit-fuzzy.

Inputs:
  1. rainfall_deficit (0-100%):  how far current rainfall is below the
     climatological normal. 0% = normal, 100% = zero rainfall.
  2. depletion_rate (0-10+ cm/yr): rate of groundwater level decline
     over the past 12 months. 0 = stable, 10+ = severe.

Output:
  crisis_score (0-100): mapped to tiers:
    Safe (0-30) | Watch (31-60) | Warning (61-80) | Crisis (81-100)

9 rules (3 rainfall bins x 3 depletion bins) as defined in config.yaml.

Course mapping: CS303 — AI & Soft Computing (Fuzzy Logic module).

Run:
    python models/fuzzy_logic.py                    # run on all districts
    python models/fuzzy_logic.py --demo             # demo with sample values
    python models/fuzzy_logic.py --plot             # plot membership functions
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).parent.parent
with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

FUZZY_PARAMS = CONFIG["model_hyperparameters"]["fuzzy_logic"]
CRISIS_TIERS = CONFIG["crisis_score"]["tiers"]


def build_fuzzy_system():
    """
    Build the Mamdani FIS with membership functions and rules.
    Returns the control system simulation object.
    """
    import skfuzzy as fuzz
    from skfuzzy import control as ctrl

    # ── Input 1: Rainfall Deficit (0-100%) ────────────────────
    rainfall_deficit = ctrl.Antecedent(np.arange(0, 101, 1), "rainfall_deficit")

    # Membership functions — triangular, overlapping at boundaries
    # Low:    0-20% deficit (near-normal rainfall)
    # Medium: 15-50% deficit (moderate shortfall)
    # High:   40-100% deficit (severe shortfall / drought)
    rainfall_deficit["low"] = fuzz.trimf(rainfall_deficit.universe, [0, 0, 25])
    rainfall_deficit["medium"] = fuzz.trimf(rainfall_deficit.universe, [15, 35, 55])
    rainfall_deficit["high"] = fuzz.trimf(rainfall_deficit.universe, [40, 100, 100])

    # ── Input 2: Depletion Rate (0-10 cm/yr) ──────────────────
    depletion_rate = ctrl.Antecedent(np.arange(0, 15.1, 0.1), "depletion_rate")

    # Stable:   0-2 cm/yr  (healthy, no significant decline)
    # Moderate: 1.5-5 cm/yr (notable decline)
    # Severe:   4-15 cm/yr  (rapid decline, crisis territory)
    depletion_rate["stable"] = fuzz.trimf(depletion_rate.universe, [0, 0, 2.5])
    depletion_rate["moderate"] = fuzz.trimf(depletion_rate.universe, [1.5, 3.5, 5.5])
    depletion_rate["severe"] = fuzz.trimf(depletion_rate.universe, [4, 15, 15])

    # ── Output: Crisis Score (0-100) ──────────────────────────
    crisis_score = ctrl.Consequent(np.arange(0, 101, 1), "crisis_score")

    # Safe:    0-30  (green)
    # Watch:   25-65 (yellow)
    # Warning: 55-85 (orange)
    # Crisis:  75-100 (red)
    crisis_score["safe"] = fuzz.trimf(crisis_score.universe, [0, 10, 35])
    crisis_score["watch"] = fuzz.trimf(crisis_score.universe, [25, 45, 65])
    crisis_score["warning"] = fuzz.trimf(crisis_score.universe, [55, 70, 85])
    crisis_score["crisis"] = fuzz.trimf(crisis_score.universe, [75, 100, 100])

    # ── 9 Fuzzy Rules ─────────────────────────────────────────
    # rainfall_deficit x depletion_rate → crisis_score
    #
    # Matrix:
    #              stable     moderate    severe
    # low deficit: safe       watch       warning
    # med deficit: watch      warning     crisis
    # high deficit:warning    crisis      crisis

    rules = [
        ctrl.Rule(rainfall_deficit["low"] & depletion_rate["stable"], crisis_score["safe"]),
        ctrl.Rule(rainfall_deficit["low"] & depletion_rate["moderate"], crisis_score["watch"]),
        ctrl.Rule(rainfall_deficit["low"] & depletion_rate["severe"], crisis_score["warning"]),

        ctrl.Rule(rainfall_deficit["medium"] & depletion_rate["stable"], crisis_score["watch"]),
        ctrl.Rule(rainfall_deficit["medium"] & depletion_rate["moderate"], crisis_score["warning"]),
        ctrl.Rule(rainfall_deficit["medium"] & depletion_rate["severe"], crisis_score["crisis"]),

        ctrl.Rule(rainfall_deficit["high"] & depletion_rate["stable"], crisis_score["warning"]),
        ctrl.Rule(rainfall_deficit["high"] & depletion_rate["moderate"], crisis_score["crisis"]),
        ctrl.Rule(rainfall_deficit["high"] & depletion_rate["severe"], crisis_score["crisis"]),
    ]

    system = ctrl.ControlSystem(rules)
    sim = ctrl.ControlSystemSimulation(system)

    return sim, rainfall_deficit, depletion_rate, crisis_score


def score_to_tier(score: float) -> str:
    """Map a 0-100 crisis score to its tier label."""
    for tier, (low, high) in CRISIS_TIERS.items():
        if low <= score <= high:
            return tier.capitalize()
    return "Crisis" if score > 80 else "Safe"


def compute_crisis_score(sim, rainfall_deficit_val: float, depletion_rate_val: float) -> tuple:
    """
    Run the FIS for a single district's inputs.
    Returns (crisis_score, tier).
    """
    # Clamp inputs to valid ranges
    rainfall_deficit_val = np.clip(rainfall_deficit_val, 0, 100)
    depletion_rate_val = np.clip(depletion_rate_val, 0, 15)

    sim.input["rainfall_deficit"] = rainfall_deficit_val
    sim.input["depletion_rate"] = depletion_rate_val

    try:
        sim.compute()
        score = float(sim.output["crisis_score"])
    except Exception:
        # If FIS can't resolve (e.g., both inputs at exact boundary), default
        score = 50.0

    score = np.clip(score, 0, 100)
    tier = score_to_tier(score)
    return round(score, 2), tier


def demo():
    """Run FIS with sample input values to verify it works."""
    sim, *_ = build_fuzzy_system()

    test_cases = [
        (5, 0.5, "Low deficit, stable — expect Safe"),
        (30, 3.0, "Medium deficit, moderate — expect Warning"),
        (60, 7.0, "High deficit, severe — expect Crisis"),
        (10, 4.5, "Low deficit, severe — expect Warning"),
        (50, 1.0, "High deficit, stable — expect Watch/Warning"),
        (80, 8.0, "Very high deficit, severe — expect Crisis"),
        (0, 0, "Zero deficit, zero depletion — expect Safe"),
        (100, 15, "Max deficit, max depletion — expect Crisis"),
    ]

    print("\nAquaIQ Fuzzy Logic Demo")
    print("=" * 70)
    print(f"  {'Rainfall Deficit':>18}  {'Depletion Rate':>15}  {'Score':>6}  {'Tier':>8}  Note")
    print("-" * 70)

    for rd, dr, note in test_cases:
        score, tier = compute_crisis_score(sim, rd, dr)
        print(f"  {rd:>17.0f}%  {dr:>14.1f} cm/yr  {score:>5.1f}  {tier:>8}  {note}")


def plot_membership_functions():
    """Save membership function plots to data/processed/."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _, rainfall_deficit, depletion_rate, crisis_score = build_fuzzy_system()

    fig, axes = plt.subplots(3, 1, figsize=(10, 10))

    for var, ax, title in [
        (rainfall_deficit, axes[0], "Input: Rainfall Deficit (%)"),
        (depletion_rate, axes[1], "Input: Depletion Rate (cm/yr)"),
        (crisis_score, axes[2], "Output: Crisis Score (0-100)"),
    ]:
        var.view(ax=ax)
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path = ROOT / "data" / "processed" / "fuzzy_membership_functions.png"
    os.makedirs(out_path.parent, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Membership function plot saved to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="AquaIQ Fuzzy Inference System")
    parser.add_argument("--demo", action="store_true", help="Run demo with sample values")
    parser.add_argument("--plot", action="store_true", help="Plot membership functions")
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.plot:
        plot_membership_functions()
    else:
        # Default: show demo + plot
        demo()
        print()
        plot_membership_functions()


if __name__ == "__main__":
    main()
