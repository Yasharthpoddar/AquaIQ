"""
Tier boundaries must come from config.yaml and be identical everywhere
(ensemble, /simulate, fuzzy logic).
"""

from pathlib import Path

import pytest
import yaml

from models.tiers import score_to_tier

CONFIG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())


@pytest.mark.parametrize("score, tier", [
    (0, "Safe"), (30, "Safe"),
    (31, "Watch"), (60, "Watch"),
    (61, "Warning"), (80, "Warning"),
    (81, "Crisis"), (100, "Crisis"),
])
def test_integer_boundaries(score, tier):
    assert score_to_tier(score) == tier


@pytest.mark.parametrize("score, tier", [
    (30.4, "Safe"), (30.6, "Watch"),
    (60.4, "Watch"), (60.6, "Warning"),
    (80.4, "Warning"), (80.6, "Crisis"),
])
def test_fractional_scores_do_not_fall_between_ranges(score, tier):
    assert score_to_tier(score) == tier


def test_out_of_range_scores_use_the_end_tiers():
    assert score_to_tier(-5) == "Safe"
    assert score_to_tier(130) == "Crisis"


def test_every_integer_score_matches_config_yaml():
    for score in range(0, 101):
        expected = next(
            name.capitalize()
            for name, (low, high) in CONFIG["crisis_score"]["tiers"].items()
            if low <= score <= high
        )
        assert score_to_tier(score) == expected, score


def test_all_modules_share_one_tier_function():
    from api.routes import simulate
    from models import ensemble, fuzzy_logic

    assert ensemble.score_to_tier is score_to_tier
    assert simulate.score_to_tier is score_to_tier
    assert fuzzy_logic.score_to_tier is score_to_tier
