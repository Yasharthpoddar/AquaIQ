"""Shared evaluation proves production math before reusing any model inputs."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
import pytest

from models import tiered_forecast as tiered
from scripts import evaluate_retrained_shared as shared


class Predictor:
    def __init__(self, scale, dtype=float):
        self.scale, self.dtype, self.inputs = scale, dtype, []

    def predict(self, rows):
        self.inputs.append(rows.copy(deep=True))
        return np.asarray(rows.horizon_months * self.scale - .3456789, dtype=self.dtype)

    def fit(self, *args, **kwargs):
        pytest.fail('Shared evaluation cannot train a model.')


@pytest.fixture
def bundles():
    base = {'feature_generation_id': 'fixture-generation', 'train_target_cutoff': '2019-12-31'}
    return ((Predictor(-2.23456789, np.float32), {**base, 'model_sha256': 'old-weights',
                'validation_assessment': {'status': 'old-assessment'}}),
            (Predictor(.123456789), {**base, 'model_sha256': 'new-weights',
                'train_target_cutoff': '2025-01-31', 'validation_assessment': {'status': 'experimental'}}))


@pytest.fixture
def source_frame():
    dates = pd.date_range('2010-01-01', '2025-01-01', freq='MS')
    return pd.DataFrame({'district_id': 'HR-One', 'date': dates,
        'gwl_current': 10.123456789 + np.sin(dates.month * np.pi / 6),
        'is_observed': True, 'is_imputed': False, 'rainfall_current': 60.,
        'temperature': 25., 'evapotranspiration': 30.})


def normalized(value):
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items() if key != 'computed_at'}
    if isinstance(value, list):
        return [normalized(item) for item in value]
    return value


def test_shared_path_matches_both_complete_real_production_results(source_frame, bundles):
    cutoff, reference = pd.Timestamp('2025-01-31'), object()
    args = ('HR-One', source_frame, cutoff, 'fixture-generation')
    complete = [tiered.forecast_district(*args, bundle, reference, calibration=None) for bundle in bundles]
    assert all(result['evidence_tier'] == 'A' for result in complete)
    assert complete[0]['estimated_current_gwl'] != float(bundles[0][0].inputs[0].origin_gwl.iloc[0])
    engine = shared.SharedForecast(*bundles)
    results = [engine(*args, bundle, reference, calibration=None) for bundle in bundles]
    assert [normalized(result) for result in results] == [normalized(result) for result in complete]
    assert engine.metadata()['exact_frozen_path_proofs'] == 1
    assert engine.metadata()['exact_frozen_points_proved'] == 12
    pd.testing.assert_frame_equal(bundles[1][0].inputs[0], bundles[1][0].inputs[1], check_exact=True)
    assert all('lower_gwl' not in row and 'upper_gwl' not in row for row in results[1]['forecast'])


def synthetic_source(tier='A', wrong_proof=False):
    """Small recorded input/output fixture, including native NaN lag values."""
    def forecast(did, frame, cutoff, generation, bundle, reference, *, calibration=None):
        current = 10.123456789
        months = pd.date_range(pd.Timestamp(cutoff).to_period('M').to_timestamp() + pd.offsets.MonthBegin(1), periods=12, freq='MS')
        if tier == 'A':
            rows = pd.DataFrame(np.ones((12, len(shared.climate.FEATURES))), columns=shared.climate.FEATURES)
            rows['origin_gwl'] = current
            rows['horizon_months'] = np.arange(1, 13, dtype=float)
            rows[['origin_gwl_lag_3mo', 'origin_gwl_lag_6mo']] = np.nan
            raw = np.asarray(bundle[0].predict(rows), dtype=float)
            points = shared._points(current, raw)
        else:
            points = [(current, 0.)] * 12
        result = dict(district_id=did, status='forecast', evidence_tier=tier, units='m_bgl',
            estimated_current_gwl=round(current, 4), computed_at=datetime.now(timezone.utc).isoformat(),
            forecast=[dict(horizon=h, date=month.date().isoformat(), predicted_gwl=depth,
                delta_from_current_m=delta, interval_status='unavailable', weather={'rainfall_mm': 60.})
                for h, (month, (depth, delta)) in enumerate(zip(months, points), 1)],
            uncertainty={'status': 'unavailable'})
        if tier == 'A':
            result.update(model_sha256=bundle[1]['model_sha256'], model_train_target_cutoff=bundle[1]['train_target_cutoff'],
                          model_validation=deepcopy(bundle[1].get('validation_assessment', {})))
        if wrong_proof:
            result['forecast'][0]['delta_from_current_m'] += .0001
        return result
    return forecast


def call(engine, source_frame, bundle, reference, **overrides):
    args = dict(district_id='HR-One', frame=source_frame, cutoff=pd.Timestamp('2025-01-31'),
                generation='fixture-generation', bundle=bundle, reference=reference, calibration=None)
    args.update(overrides)
    return engine(**args)


def test_native_nan_lags_are_captured_and_candidate_outputs_match_full_fixture(source_frame, bundles):
    source = synthetic_source()
    engine, reference = shared.SharedForecast(*bundles, real_forecast=source), object()
    old = call(engine, source_frame, bundles[0], reference)
    new = call(engine, source_frame, bundles[1], reference)
    full = source('HR-One', source_frame, pd.Timestamp('2025-01-31'), 'fixture-generation', bundles[1], reference)
    assert normalized(new) == normalized(full)
    assert bundles[1][0].inputs[0].origin_gwl_lag_3mo.isna().all()
    assert bundles[1][0].inputs[0].origin_gwl_lag_6mo.isna().all()
    assert old['model_sha256'] != new['model_sha256']
    # Returned objects do not share the nested cached forecast path.
    old['forecast'][0]['predicted_gwl'] = 9999
    assert new['forecast'][0]['predicted_gwl'] != 9999
    engine.finish()


def test_mismatched_frozen_math_fails_before_candidate_prediction(source_frame, bundles):
    engine = shared.SharedForecast(*bundles, real_forecast=synthetic_source(wrong_proof=True))
    with pytest.raises(ValueError, match='exactly reproduce'):
        call(engine, source_frame, bundles[0], object())
    assert not bundles[1][0].inputs


@pytest.mark.parametrize('bad', [np.ones(1), np.ones((12, 1)), np.full(12, np.inf), np.full(12, -np.inf), np.full(12, np.nan)])
def test_candidate_wrong_shape_and_nonfinite_predictions_fail_closed(source_frame, bundles, bad):
    bundles[1][0].predict = lambda rows: bad
    engine, reference = shared.SharedForecast(*bundles, real_forecast=synthetic_source()), object()
    call(engine, source_frame, bundles[0], reference)
    with pytest.raises(ValueError, match='twelve finite'):
        call(engine, source_frame, bundles[1], reference)


def test_candidate_prediction_failure_propagates(source_frame, bundles):
    def unavailable(rows):
        raise RuntimeError('candidate prediction unavailable')
    bundles[1][0].predict = unavailable
    engine, reference = shared.SharedForecast(*bundles, real_forecast=synthetic_source()), object()
    call(engine, source_frame, bundles[0], reference)
    with pytest.raises(RuntimeError, match='candidate prediction unavailable'):
        call(engine, source_frame, bundles[1], reference)


@pytest.mark.parametrize('tier', ['B', 'C', 'D'])
def test_model_independent_fallbacks_never_predict_either_model(source_frame, bundles, tier):
    def forbidden(rows):
        pytest.fail('Fallback results must not invoke a candidate or frozen model.')
    for model, card in bundles:
        model.predict = forbidden
    source = synthetic_source(tier=tier)
    engine, reference = shared.SharedForecast(*bundles, real_forecast=source), object()
    results = [call(engine, source_frame, bundle, reference) for bundle in bundles]
    assert normalized(results[0]) == normalized(results[1])
    stats = engine.metadata()
    assert stats['model_independent_pairs'] == 1 and stats['candidate_predict_calls'] == 0
    assert stats['exact_frozen_path_proofs'] == 0


@pytest.mark.parametrize('problem', ['double_frozen', 'other_frame', 'mutated_frame', 'other_reference',
    'other_district', 'other_cutoff', 'unknown_bundle', 'changed_frozen_card', 'changed_candidate_card'])
def test_strict_sequence_and_immutable_evidence_keys_prevent_cache_reuse(source_frame, bundles, problem):
    engine, reference = shared.SharedForecast(*bundles, real_forecast=synthetic_source()), object()
    call(engine, source_frame, bundles[0], reference)
    overrides = {}
    if problem == 'double_frozen': overrides['bundle'] = bundles[0]
    elif problem == 'other_frame': overrides['frame'] = source_frame.copy()
    elif problem == 'mutated_frame': source_frame.loc[0, 'gwl_current'] += 1
    elif problem == 'other_reference': overrides['reference'] = object()
    elif problem == 'other_district': overrides['district_id'] = 'TN-Other'
    elif problem == 'other_cutoff': overrides['cutoff'] = pd.Timestamp('2025-02-28')
    elif problem == 'unknown_bundle': overrides['bundle'] = (bundles[1][0], bundles[1][1])
    elif problem == 'changed_frozen_card': bundles[0][1]['model_sha256'] = 'changed'
    else: bundles[1][1]['model_sha256'] = 'changed'
    args = dict(bundle=bundles[1], reference=reference, **{})
    args.update(overrides)
    with pytest.raises(ValueError):
        call(engine, source_frame, **args)


def test_candidate_first_calibration_or_incomplete_pair_is_rejected(source_frame, bundles):
    engine, reference = shared.SharedForecast(*bundles, real_forecast=synthetic_source()), object()
    with pytest.raises(ValueError, match='begin'):
        call(engine, source_frame, bundles[1], reference)
    with pytest.raises(ValueError, match='bounds'):
        call(engine, source_frame, bundles[0], reference, calibration={})
    call(engine, source_frame, bundles[0], reference)
    with pytest.raises(ValueError, match='incomplete'):
        engine.finish()


def test_shared_cli_forwards_original_and_restores_process_local_patches(tmp_path, monkeypatch, source_frame, bundles):
    source, reference = synthetic_source(), object()
    monkeypatch.setattr(tiered, 'forecast_district', source)
    output = tmp_path / 'new_evaluation'
    arguments = ['--features', 'verified', '--output', str(output)]
    original_evaluate = shared.original.evaluate

    def evaluate_once(frame, frozen, candidate, origins, added_districts=None):
        for bundle in (frozen, candidate):
            call(tiered.forecast_district, frame, bundle, reference)
        return pd.DataFrame()

    def original_cli(argv):
        assert argv is arguments
        shared.original.evaluate(source_frame, *bundles, ['2025-01-31'])
        output.mkdir()
        report = {'original_report': True}
        (output / 'summary.json').write_text(json.dumps(report))
        return report

    monkeypatch.setattr(shared, '_EVALUATE', evaluate_once)
    monkeypatch.setattr(shared.original, 'main', original_cli)
    report = shared.main(arguments)
    assert report['shared_execution']['exact_frozen_points_proved'] == 12
    assert report['shared_execution']['model_fit_performed'] is False
    assert json.loads((output / 'summary.json').read_text()) == report
    assert tiered.forecast_district is source
    assert shared.original.evaluate is original_evaluate


def test_patch_is_restored_when_original_evaluation_fails(monkeypatch, source_frame, bundles):
    source = synthetic_source()
    monkeypatch.setattr(tiered, 'forecast_district', source)
    def failure(*args, **kwargs):
        raise RuntimeError('explicit original evaluator failure')
    monkeypatch.setattr(shared, '_EVALUATE', failure)
    with pytest.raises(RuntimeError, match='original evaluator failure'):
        shared.evaluate(source_frame, *bundles, ['2025-01-31'])
    assert tiered.forecast_district is source
