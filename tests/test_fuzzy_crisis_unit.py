"""
AquaIQ - Unit tests for the Fuzzy Crisis-Score module
Module under test : models/fuzzy_logic.py  (build_fuzzy_system, compute_crisis_score)
                    models/tiers.py        (score_to_tier)
Run               : pytest tests/test_fuzzy_crisis_unit.py -v
No database or network is needed.
"""
import math

import pytest
import yaml
from pathlib import Path

from models.fuzzy_logic import build_fuzzy_system, compute_crisis_score
from models.tiers import score_to_tier

CONFIG = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())


@pytest.fixture(scope="module")
def fis():
    sim, rainfall, depletion, crisis = build_fuzzy_system()
    return sim, rainfall, depletion, crisis


@pytest.fixture()
def sim(fis):
    return fis[0]


# ---------------------------------------------------------------- FR-1 : FIS construction
def test_TC01_membership_terms_defined(fis):
    _, rainfall, depletion, crisis = fis
    assert set(rainfall.terms) == {"low", "medium", "high"}
    assert set(depletion.terms) == {"stable", "moderate", "severe"}
    assert set(crisis.terms) == {"safe", "watch", "warning", "crisis"}


def test_TC02_rule_base_has_nine_rules(sim):
    rule_count = len(list(sim.ctrl.rules))
    assert rule_count == 9
    assert rule_count == CONFIG["model_hyperparameters"]["fuzzy_logic"]["rule_count"]


# ---------------------------------------------------------------- FR-2 : rule matrix (one case per rule cell)
RULE_CELLS = [
    # id,    rainfall_deficit %, depletion cm/yr, expected tier
    ("TC03", 0, 0, "Safe"),       # low    x stable
    ("TC04", 0, 3.5, "Watch"),    # low    x moderate
    ("TC05", 0, 15, "Warning"),   # low    x severe
    ("TC06", 35, 0, "Watch"),     # medium x stable
    ("TC07", 35, 3.5, "Warning"),  # medium x moderate
    ("TC08", 35, 15, "Crisis"),   # medium x severe
    ("TC09", 100, 0, "Warning"),  # high   x stable
    ("TC10", 100, 3.5, "Crisis"),  # high   x moderate
    ("TC11", 100, 15, "Crisis"),  # high   x severe
]


@pytest.mark.parametrize("tc, rd, dr, tier", RULE_CELLS, ids=[c[0] for c in RULE_CELLS])
def test_rule_cell_returns_expected_tier(sim, tc, rd, dr, tier):
    score, label = compute_crisis_score(sim, rd, dr)
    assert label == tier
    assert 0 <= score <= 100


# ---------------------------------------------------------------- FR-3 : output contract
def test_TC12_output_type_and_rounding(sim):
    score, label = compute_crisis_score(sim, 30, 3)
    assert isinstance(float(score), float)
    assert isinstance(label, str)
    assert round(float(score), 2) == float(score)          # at most 2 decimals


def test_TC13_score_always_within_0_100(sim):
    for rd in range(0, 101, 20):
        for dr in (0, 1, 2.5, 5, 10, 15):
            score, _ = compute_crisis_score(sim, rd, dr)
            assert 0 <= score <= 100


def test_TC14_known_value_regression(sim):
    assert compute_crisis_score(sim, 0, 0) == (15.0, "Safe")
    assert float(compute_crisis_score(sim, 30, 3)[0]) == pytest.approx(70.0, abs=0.5)


def test_TC15_deterministic(sim):
    assert compute_crisis_score(sim, 42, 6.1) == compute_crisis_score(sim, 42, 6.1)


def test_TC16_worse_conditions_give_higher_score(sim):
    best = float(compute_crisis_score(sim, 0, 0)[0])
    mid = float(compute_crisis_score(sim, 35, 3.5)[0])
    worst = float(compute_crisis_score(sim, 100, 15)[0])
    assert best < mid < worst


# ---------------------------------------------------------------- FR-4 : input clamping
def test_TC17_negative_inputs_clamped_to_zero(sim):
    assert compute_crisis_score(sim, -20, -3) == compute_crisis_score(sim, 0, 0)


def test_TC18_inputs_above_range_clamped_to_max(sim):
    assert compute_crisis_score(sim, 150, 40) == compute_crisis_score(sim, 100, 15)


# ---------------------------------------------------------------- FR-5 : tier mapping
@pytest.mark.parametrize("score, tier", [
    (0, "Safe"), (30, "Safe"), (31, "Watch"), (60, "Watch"),
    (61, "Warning"), (80, "Warning"), (81, "Crisis"), (100, "Crisis"),
], ids=lambda v: str(v))
def test_TC19_tier_integer_boundaries(score, tier):
    assert score_to_tier(score) == tier


@pytest.mark.parametrize("score, tier", [
    (30.4, "Safe"), (30.6, "Watch"), (60.4, "Watch"),
    (60.6, "Warning"), (80.4, "Warning"), (80.6, "Crisis"),
], ids=lambda v: str(v))
def test_TC20_tier_fractional_scores(score, tier):
    assert score_to_tier(score) == tier


def test_TC21_tier_out_of_range_uses_end_tiers():
    assert score_to_tier(-5) == "Safe"
    assert score_to_tier(130) == "Crisis"


def test_TC22_config_tiers_cover_0_to_100_without_gaps():
    covered = []
    for low, high in CONFIG["crisis_score"]["tiers"].values():
        covered.extend(range(low, high + 1))
    assert sorted(covered) == list(range(0, 101))


# ---------------------------------------------------------------- FR-6 : invalid input handling
def test_TC23_non_numeric_input_is_rejected(sim):
    with pytest.raises(TypeError):
        compute_crisis_score(sim, "abc", 3)


@pytest.mark.xfail(strict=True, reason="DEFECT D-01: NaN passes np.clip and returns a made-up score "
                                       "(64.79 / Warning) instead of being rejected")
def test_TC24_nan_input_is_rejected(sim):
    with pytest.raises((ValueError, RuntimeError)):
        compute_crisis_score(sim, float("nan"), 3)