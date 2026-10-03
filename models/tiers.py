"""
AquaIQ — Crisis-score tiers (single source of truth)
-----------------------------------------------------
Tier boundaries live in config.yaml under crisis_score.tiers
(Safe 0-30, Watch 31-60, Warning 61-80, Crisis 81-100).

The ensemble, the /simulate endpoint and the fuzzy-logic module all call
score_to_tier(), so one score can never receive two different labels.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent

with open(ROOT / "config.yaml") as _f:
    TIERS = yaml.safe_load(_f)["crisis_score"]["tiers"]

# (label, inclusive upper bound), lowest tier first
_BOUNDS = sorted(
    ((name.capitalize(), high) for name, (_, high) in TIERS.items()),
    key=lambda item: item[1],
)


def score_to_tier(score) -> str:
    """
    Map a 0-100 crisis score to its tier label.

    The score is rounded to an integer first (the API reports integer scores),
    so the label always matches the number shown and fractional scores such as
    60.4 cannot fall between the integer ranges defined in config.yaml.
    Scores outside 0-100 are clamped to the lowest / highest tier.
    """
    value = round(float(score))
    for label, high in _BOUNDS:
        if value <= high:
            return label
    return _BOUNDS[-1][0]
