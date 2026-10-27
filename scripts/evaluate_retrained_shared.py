"""Candidate-only shared feature replay around the unchanged paired evaluator.

The frozen call runs the complete production path. Its captured feature matrix
must reproduce every frozen point/delta exactly before a candidate can reuse
those inputs. Patches and the single pending-pair cache live in this process
only; no model, training protocol, publication or original evaluator is changed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from models import climate_forecast_12m as climate
from models import tiered_forecast as tiered
from models.xgboost_model import _write_json, sha256_file
from scripts import evaluate_retrained_model as original

_EVALUATE = original.evaluate


def _card_hash(card):
    return hashlib.sha256(json.dumps(card, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _frame_hash(frame):
    digest = hashlib.sha256()
    digest.update(repr([(str(c), str(t)) for c, t in zip(frame.columns, frame.dtypes)]).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return digest.hexdigest()


def _predictions(model, rows):
    values = np.asarray(model.predict(rows), dtype=float)
    if values.shape != (12,) or not np.isfinite(values).all():
        raise ValueError('Shared replay requires exactly twelve finite raw model predictions.')
    return values


def _points(current, deltas):
    depths = np.maximum(0., current + deltas)
    return [(round(float(depth), 4), round(float(depth - current), 4)) for depth in depths]


class CaptureModel:
    """Transparent prediction recorder; all fitting is forbidden."""
    def __init__(self, model):
        self.model = model
        self.rows = None
        self.raw = None

    def predict(self, rows, *args, **kwargs):
        if self.rows is not None:
            raise ValueError('The complete frozen path predicted more than once for one district.')
        if not isinstance(rows, pd.DataFrame) or list(rows.columns) != climate.FEATURES or rows.shape != (12, len(climate.FEATURES)):
            raise ValueError('Captured model inputs differ from the production seventeen-feature schema.')
        self.rows = rows.copy(deep=True)
        self.rows.attrs = {}
        raw = self.model.predict(rows, *args, **kwargs)
        pd.testing.assert_frame_equal(rows, self.rows, check_exact=True)
        self.raw = np.asarray(raw, dtype=float).copy()
        if self.raw.shape != (12,) or not np.isfinite(self.raw).all():
            raise ValueError('The frozen model returned an invalid complete raw prediction path.')
        return raw

    def fit(self, *args, **kwargs):
        raise RuntimeError('Shared evaluation must never fit a model.')


class SharedForecast:
    """Strict frozen/candidate call pairs around one real production function."""
    def __init__(self, frozen_bundle, candidate_bundle, *, real_forecast=None):
        if frozen_bundle is candidate_bundle or frozen_bundle[0] is candidate_bundle[0]:
            raise ValueError('Shared replay requires distinct frozen and candidate model identities.')
        self.bundles = (frozen_bundle, candidate_bundle)
        self.identities = [(id(bundle[0]), bundle[1]['model_sha256'], _card_hash(bundle[1])) for bundle in self.bundles]
        if any(not isinstance(identity[1], str) or not identity[1] for identity in self.identities):
            raise ValueError('Verified model weight identities are required.')
        self.real_forecast = real_forecast or tiered.forecast_district
        if isinstance(self.real_forecast, SharedForecast):
            raise ValueError('Nested shared forecast patches are forbidden.')
        self.pending = None
        self.stats = {'full_frozen_calls': 0, 'shared_candidate_calls': 0,
            'exact_frozen_path_proofs': 0, 'exact_frozen_points_proved': 0,
            'candidate_predict_calls': 0, 'model_independent_pairs': 0}

    def _identity(self, bundle):
        for position, expected in enumerate(self.bundles):
            identity = (id(expected[0]), expected[1]['model_sha256'], _card_hash(expected[1]))
            if identity != self.identities[position]:
                raise ValueError('Model identity or verified card changed during shared replay.')
        for position, expected in enumerate(self.bundles):
            if bundle is expected:
                return position
        raise ValueError('Unexpected bundle object in a shared forecast pair.')

    def __call__(self, district_id, frame, cutoff, generation, bundle, reference, *, calibration=None):
        if calibration is not None:
            raise ValueError('Shared retraining evaluation cannot reuse calibrated bounds.')
        position = self._identity(bundle)
        for expected in self.bundles:
            if (expected[1].get('feature_generation_id') != generation
                    or pd.Timestamp(cutoff) < pd.Timestamp(expected[1]['train_target_cutoff'])):
                raise ValueError('Shared model generation/cutoff differs from the requested evidence.')
        key = (district_id, pd.Timestamp(cutoff).isoformat(), generation, id(frame), id(reference))
        signature = _frame_hash(frame)
        if self.pending is None:
            if position != 0:
                raise ValueError('Each shared pair must begin with the verified frozen model.')
            capture = CaptureModel(bundle[0])
            result = self.real_forecast(district_id, frame, cutoff, generation,
                (capture, bundle[1]), reference, calibration=None)
            if _frame_hash(frame) != signature:
                raise ValueError('The full frozen path mutated shared source evidence.')
            if result.get('status') != 'forecast' or len(result.get('forecast', [])) != 12:
                raise ValueError('The complete frozen production forecast failed.')
            if any('lower_gwl' in row or 'upper_gwl' in row for row in result['forecast']):
                raise ValueError('Shared candidate replay requires unavailable numerical bounds.')
            tier = result.get('evidence_tier')
            if tier == 'A':
                if capture.rows is None:
                    raise ValueError('The frozen XGBoost path did not expose its actual prediction inputs.')
                inputs = capture.rows.to_numpy(dtype=float)
                if np.isinf(inputs).any():
                    raise ValueError('Captured feature inputs contain infinity.')
                for name in climate.FEATURES:
                    if name not in ('origin_gwl_lag_3mo', 'origin_gwl_lag_6mo') and not np.isfinite(capture.rows[name]).all():
                        raise ValueError('Only native missing groundwater lags may be unavailable in captured inputs.')
                current = float(capture.rows.origin_gwl.iloc[0])
                if (current < 0 or not np.array_equal(capture.rows.origin_gwl.to_numpy(), np.full(12, current))
                        or not np.array_equal(capture.rows.horizon_months.to_numpy(), np.arange(1, 13))
                        or result.get('estimated_current_gwl') != round(current, 4)):
                    raise ValueError('Captured origin anchor/horizons differ from full production output.')
                actual = [(row['predicted_gwl'], row['delta_from_current_m']) for row in result['forecast']]
                if _points(current, capture.raw) != actual:
                    raise ValueError('Captured raw predictions do not exactly reproduce the full frozen path.')
                self.stats['exact_frozen_path_proofs'] += 1
                self.stats['exact_frozen_points_proved'] += 12
            elif tier in ('B', 'C', 'D'):
                if capture.rows is not None or any(name in result for name in ('model_sha256', 'model_train_target_cutoff', 'model_validation')):
                    raise ValueError('Fallback output unexpectedly depends on a model bundle.')
            else:
                raise ValueError('Unknown production evidence tier in shared evaluation.')
            self.pending = {'key': key, 'signature': signature, 'result': deepcopy(result),
                            'rows': capture.rows, 'raw': capture.raw}
            self.stats['full_frozen_calls'] += 1
            return result
        if position != 1 or key != self.pending['key'] or signature != self.pending['signature']:
            raise ValueError('Shared forecasts must alternate matching immutable frozen/candidate evidence.')
        result = deepcopy(self.pending['result'])
        if result['evidence_tier'] == 'A':
            rows = self.pending['rows'].copy(deep=True)
            before = _frame_hash(rows)
            deltas = _predictions(bundle[0], rows)
            if _frame_hash(rows) != before:
                raise ValueError('Candidate prediction mutated the verified captured features.')
            current = float(rows.origin_gwl.iloc[0])
            for row, (depth, delta) in zip(result['forecast'], _points(current, deltas)):
                row.update(predicted_gwl=depth, delta_from_current_m=delta)
            card = bundle[1]
            result.update(model_sha256=card['model_sha256'], model_train_target_cutoff=card['train_target_cutoff'],
                          model_validation=deepcopy(card.get('validation_assessment', {})))
            self.stats['candidate_predict_calls'] += 1
        else:
            self.stats['model_independent_pairs'] += 1
        self.stats['shared_candidate_calls'] += 1
        self.pending = None
        return result

    def finish(self):
        if self.pending is not None or self.stats['full_frozen_calls'] != self.stats['shared_candidate_calls']:
            raise ValueError('Shared evaluation ended with an incomplete frozen/candidate pair.')

    def metadata(self):
        self.finish()
        return {**self.stats, 'mode': 'exact_verified_shared_feature_replay',
            'process_local_temporary_patch': True, 'persistent_cache': False,
            'calibration_used': False, 'model_fit_performed': False,
            'wrapper_sha256': sha256_file(Path(__file__)),
            'original_evaluator_sha256': sha256_file(Path(original.__file__)),
            'tiered_forecast_sha256': sha256_file(Path(tiered.__file__)),
            'climate_forecast_sha256': sha256_file(Path(climate.__file__))}


@contextmanager
def shared_path(frozen_bundle, candidate_bundle):
    engine = SharedForecast(frozen_bundle, candidate_bundle)
    with patch.object(tiered, 'forecast_district', engine):
        yield engine
        engine.finish()


def evaluate(frame, frozen_bundle, candidate_bundle, origins, added_districts=None):
    """Call the unchanged evaluator with a temporary verified sharing wrapper."""
    with shared_path(frozen_bundle, candidate_bundle) as engine:
        table = _EVALUATE(frame, frozen_bundle, candidate_bundle, origins, added_districts=added_districts)
    table.attrs['shared_execution'] = engine.metadata()
    return table


def main(argv=None):
    metadata = []

    def shared_evaluate(*args, **kwargs):
        table = evaluate(*args, **kwargs)
        metadata.append(table.attrs['shared_execution'])
        return table

    # The original CLI alone parses inputs, verifies both bundles, protects the
    # new output directory and saves paired cases. Its source remains unchanged.
    with patch.object(original, 'evaluate', shared_evaluate):
        report = original.main(argv)
    if len(metadata) != 1:
        raise ValueError('Shared CLI must execute exactly one complete paired evaluator.')
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--output', type=Path, required=True)
    args, _ = parser.parse_known_args(argv)
    report['shared_execution'] = metadata[0]
    _write_json(args.output / 'summary.json', report)
    return report


if __name__ == '__main__':
    main()
