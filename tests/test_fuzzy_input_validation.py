"""Missing or infinite observations must not manufacture fuzzy risk scores."""
import numpy as np
import pytest

from models.fuzzy_logic import build_fuzzy_system, compute_crisis_score


class UntouchedSimulation:
    @property
    def input(self):
        pytest.fail('Invalid observations must be rejected before mutating the simulation')


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), np.float32('nan')])
@pytest.mark.parametrize('argument', ['rainfall', 'depletion'])
def test_nonfinite_observations_are_rejected_before_simulation_input(argument, value):
    rainfall, depletion = (value, 3.) if argument == 'rainfall' else (30., value)
    with pytest.raises(ValueError, match='finite observations'):
        compute_crisis_score(UntouchedSimulation(), rainfall, depletion)


def test_rejected_observation_does_not_poison_reused_simulation():
    simulation, *_ = build_fuzzy_system()
    assert compute_crisis_score(simulation, 0., 0.) == (15., 'Safe')
    for rainfall, depletion in ((float('nan'), 3.), (30., float('inf'))):
        with pytest.raises(ValueError, match='finite observations'):
            compute_crisis_score(simulation, rainfall, depletion)
    assert compute_crisis_score(simulation, 0., 0.) == (15., 'Safe')
    assert compute_crisis_score(simulation, 35., 3.5) == (70., 'Warning')


@pytest.mark.parametrize('rainfall, depletion', [(-20., -3.), (150., 40.), (np.float32(35), np.float64(3.5))])
def test_finite_numeric_inputs_keep_existing_clipping_and_scores(rainfall, depletion):
    simulation, *_ = build_fuzzy_system()
    expected = (15., 'Safe') if rainfall < 0 else (91.67, 'Crisis') if rainfall > 100 else (70., 'Warning')
    assert compute_crisis_score(simulation, rainfall, depletion) == expected
