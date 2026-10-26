"""Measure the registry-then-concurrent States-page API sequence, without a DB.

This uses real Flask routes in one fresh process with two request threads. It is
not a browser paint or remote deployment measurement. Output must be new.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import platform
from threading import Lock
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--state', default='HR')
    parser.add_argument('--as-of', default='2026-10-25')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from api.app import create_app
    from models import climate_forecast_12m as climate
    import db.connection
    app = create_app({'TESTING': True})
    calls, lock = {}, Lock()
    predict = climate.forecast_from_evidence
    def counted(evidence, **kwargs):
        with lock:
            district = evidence['district_id']
            calls[district] = calls.get(district, 0) + 1
        return predict(evidence, **kwargs)
    started = time.perf_counter()
    def request(path):
        with app.test_client() as client:
            response = client.get(path)
        return {'seconds_since_navigation': time.perf_counter()-started,
                'http_status': response.status_code, 'payload': response.get_json()}
    with patch.object(db.connection, 'get_connection', side_effect=AssertionError('No database access')):
        with patch.object(climate, 'forecast_from_evidence', counted):
            registry = request('/api/states?as_of='+args.as_of)
            assert registry['http_status'] == 200
            as_of = registry['payload']['as_of']
            paths = {'selected_state':f'/api/predict/state/{args.state}?horizon=12&as_of={as_of}',
                     'nationwide_summary':f'/api/states/summary?horizon=12&as_of={as_of}'}
            result = {'registry':registry}
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = {pool.submit(request,path): name for name,path in paths.items()}
                for future in as_completed(pending):
                    name = pending[future]
                    result[name] = future.result()
                    print(json.dumps({'stage':name, 'seconds':result[name]['seconds_since_navigation'],
                                      'http_status':result[name]['http_status']}), flush=True)
    assert all(row['http_status'] == 200 for row in result.values())
    assert max(calls.values(), default=0) <= 1, 'Concurrent requests duplicated district forecasts.'
    result['conditions'] = {'execution':'fresh-process Flask routes; two request threads; imports excluded; disk cache not flushed',
        'python':platform.python_version(), 'platform':platform.platform(), 'cpu_count':os.cpu_count(),
        'OMP_NUM_THREADS':os.environ.get('OMP_NUM_THREADS'), 'OPENBLAS_NUM_THREADS':os.environ.get('OPENBLAS_NUM_THREADS')}
    result['district_forecast_calls'] = calls
    with (args.output/'timings.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)


if __name__ == '__main__':
    main()
