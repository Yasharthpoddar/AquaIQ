"""Measure actual Flask state routes without network, database access or training.

Each invocation is a fresh-process application-cache-cold run; OS disk caches
are not flushed. --profile adds cProfile overhead and is not a latency sample.
The output directory must be new. Existing model/data/report files are read only.
"""
import argparse
from contextlib import ExitStack
import cProfile
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import pstats
import time
from unittest.mock import patch


def canonical(value):
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items() if k != 'computed_at'}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state', default=None, help='Omit to measure nationwide summary.')
    parser.add_argument('--as-of', default='2026-10-25')
    parser.add_argument('--warm', default=3, type=int)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from api.app import create_app
    from models import state_forecast as state, climate_inputs, climate_forecast_12m as climate
    from models import climate_forecast as climate6
    import db.connection
    import numpy as np
    import pandas as pd
    import xgboost
    stats = {}

    def watch(owner, name, label):
        original = getattr(owner, name)
        def wrapped(*a, **kw):
            started = time.perf_counter()
            try:
                return original(*a, **kw)
            finally:
                result = stats.setdefault(label, {'calls': 0, 'seconds': 0.})
                result['calls'] += 1
                result['seconds'] += time.perf_counter() - started
        return patch.object(owner, name, wrapped)

    client = create_app({'TESTING': True}).test_client()
    endpoint = '/api/states/summary' if args.state is None else '/api/predict/state/' + args.state
    endpoint += '?horizon=12&as_of=' + args.as_of
    timings, counters, payloads = [], [], []
    profiler = cProfile.Profile() if args.profile else None
    with ExitStack() as stack:
        stack.enter_context(patch.object(db.connection, 'get_connection', side_effect=AssertionError('Benchmark must not query the DB')))
        for owner, name, label in [(state,'load_feature_matrix','feature_load_validate'),
                (state,'_state_frame','state_frame'), (state,'get_state_districts','registry_reads'),
                (state,'aggregate_state_observations','history_aggregation'),
                (state,'_readiness','readiness'), (climate,'load_bundle','bundle_lookup'),
                (climate,'forecast_from_evidence','district_forecast'),
                (climate,'forecast_weather','future_weather'), (climate,'origin_inputs','origin_inputs'),
                (climate,'fit_projection','anchor_fit'),
                (xgboost.XGBRegressor,'predict','xgb_predict')]:
            stack.enter_context(watch(owner,name,label))
        for i in range(args.warm + 1):
            stats.clear()
            if profiler and i == 0:
                profiler.enable()
            start = time.perf_counter()
            response = client.get(endpoint)
            seconds = time.perf_counter() - start
            if profiler:
                profiler.disable()
            payload = response.get_json()
            timings.append({'kind': 'cold' if i == 0 else 'warm', 'seconds': seconds, 'http_status': response.status_code})
            counters.append(json.loads(json.dumps(stats)))
            payloads.append(payload)
            print(json.dumps(timings[-1]), flush=True)
            if response.status_code != 200:
                raise RuntimeError(f'Unexpected route failure: {response.status_code} {payload}')
        for payload in payloads[1:]:
            assert canonical(payload) == canonical(payloads[0]), 'Warm result differs from cold result.'
        snapshots = {'response': payloads[0]}
        if args.state is None:
            snapshots['states'] = {row['state_id']: client.get('/api/predict/state/' + row['state_id'] + '?horizon=12&as_of=' + args.as_of).get_json()
                                   for row in payloads[0]['states']}
    with (args.output/'payloads.json').open('x',encoding='utf-8') as stream:
        json.dump(snapshots,stream,indent=2,allow_nan=False)
    comparison = None
    if args.compare:
        before = json.loads((args.compare/'payloads.json').read_text(encoding='utf-8'))
        comparison = canonical(before) == canonical(snapshots)
        if not comparison:
            raise AssertionError('Optimized result differs from preserved baseline (ignoring only computed_at).')
    result = dict(endpoint=endpoint, profile_overhead=args.profile, timings=timings, counters=counters,
        canonical_baseline_equal=comparison, conditions=dict(application_cache='fresh process for first request',
        disk_cache='not flushed', execution='Flask test client, route/serialization included, app import excluded',
        concurrency='one request at a time',python=platform.python_version(),platform=platform.platform(),
        cpu_count=os.cpu_count(),numpy=np.__version__,pandas=pd.__version__,xgboost=xgboost.__version__,
        OMP_NUM_THREADS=os.environ.get('OMP_NUM_THREADS'),OPENBLAS_NUM_THREADS=os.environ.get('OPENBLAS_NUM_THREADS')),
        source_sha256={str(Path(module.__file__).relative_to(Path.cwd())): hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (state,climate,climate_inputs,climate6)})
    with (args.output/'timings.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2)
    if profiler:
        profiler.dump_stats(str(args.output/'cold.pstats'))
        report = io.StringIO()
        pstats.Stats(profiler,stream=report).sort_stats('cumulative').print_stats(60)
        (args.output/'profile.txt').write_text(report.getvalue(),encoding='utf-8')


if __name__ == '__main__':
    main()
