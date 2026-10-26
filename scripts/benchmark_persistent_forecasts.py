"""Benchmark persistent XGBoost forecast storage and precomputation.

Measures precomputation duration, database queries, and cold/warm endpoint
latencies under an isolated PostgreSQL test schema without modifying production data.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import time
from unittest.mock import patch
import uuid

from api.app import create_app
from db import connection as dbc
from models import forecast_storage
from models.forecast_storage import clear_storage_l1_caches
from scripts.precompute_forecasts import run_precomputation

ROOT = Path(__file__).resolve().parents[1]


def setup_benchmark_schema(as_of='2026-10-25'):
    schema_name = f"aquaiq_bench_{uuid.uuid4().hex[:12]}"
    conn = dbc.get_connection()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema_name}")
        cur.execute(f"SET search_path TO {schema_name}, public")

        for mig in sorted((ROOT / 'db' / 'migrations').glob('*.sql')):
            sql = mig.read_text(encoding='utf-8')
            cur.execute(sql)

    conn.autocommit = False
    return schema_name, conn


def cleanup_benchmark_schema(schema_name, conn):
    try:
        conn.rollback()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
    except Exception as exc:
        print(f"Schema cleanup warning: {exc}")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports' / 'state_performance_20261025' / 'persistent_benchmark.json')
    parser.add_argument('--as-of', default='2026-10-25')
    parser.add_argument('--state', default='HR')
    parser.add_argument('--district', default='HR-Kaithal')
    args = parser.parse_args()

    as_of = args.as_of
    state_id = args.state
    district_id = args.district

    print(f"Setting up isolated PostgreSQL benchmark schema...")
    schema_name, conn = setup_benchmark_schema(as_of)

    results = {
        'benchmark_timestamp': datetime.now(timezone.utc).isoformat(),
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'cpu_count': os.cpu_count(),
        'as_of': as_of,
        'isolated_schema': schema_name,
    }

    try:
        # 1. Precomputation benchmark
        print(f"\n--- 1. Precomputation Benchmark ---")
        precompute_start = time.perf_counter()
        precompute_summary = run_precomputation(as_of=as_of, horizon=12, connection=conn)
        precompute_duration = time.perf_counter() - precompute_start

        results['precomputation'] = {
            'duration_seconds': round(precompute_duration, 3),
            'generation_id': precompute_summary['generation_id'],
            'districts_total': precompute_summary['districts_total'],
            'districts_forecast': precompute_summary['districts_forecast'],
            'districts_insufficient': precompute_summary['districts_insufficient'],
            'states_total': precompute_summary['states_total'],
            'states_available': precompute_summary['states_available'],
            'states_insufficient': precompute_summary['states_insufficient'],
        }
        print(f"Precomputation completed in {precompute_duration:.2f}s")
        print(f"Districts: {precompute_summary['districts_total']} total, {precompute_summary['districts_forecast']} forecast")
        print(f"States: {precompute_summary['states_total']} total, {precompute_summary['states_available']} available")

        # 2. Setup Flask client with patched connection pointing to benchmark schema
        class ConnectionWrapper:
            def __init__(self, raw_conn):
                self._conn = raw_conn
                self.query_count = 0
                self.query_duration = 0.0

            def cursor(self, *a, **kw):
                base_cur = self._conn.cursor(*a, **kw)
                wrapper = self
                class CursorWrapper:
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        return base_cur.__exit__(*args)
                    def execute(self, query, vars=None):
                        t0 = time.perf_counter()
                        try:
                            return base_cur.execute(query, vars)
                        finally:
                            wrapper.query_count += 1
                            wrapper.query_duration += time.perf_counter() - t0
                    def __getattr__(self, name):
                        return getattr(base_cur, name)
                return CursorWrapper()

            def close(self):
                pass  # Keep open

            def commit(self):
                return self._conn.commit()

            def rollback(self):
                return self._conn.rollback()

            def __getattr__(self, name):
                return getattr(self._conn, name)

        wrapped_conn = ConnectionWrapper(conn)

        with patch.object(dbc, 'get_connection', lambda: wrapped_conn):
            app = create_app({'TESTING': True})
            client = app.test_client()

            # Ensure model inference is NOT called during normal API reads
            from models import climate_forecast_12m as climate
            def forbidden_inference(*a, **kw):
                raise AssertionError("Inference must NOT be executed during persisted API read!")
            with patch.object(climate, 'forecast_from_evidence', forbidden_inference):

                # 3. District Latencies
                print(f"\n--- 2. District Endpoint Latency (/api/predict/climate-12m/{district_id}) ---")
                clear_storage_l1_caches()
                wrapped_conn.query_count = 0
                wrapped_conn.query_duration = 0.0

                t0 = time.perf_counter()
                res_cold_d = client.get(f'/api/predict/climate-12m/{district_id}?months=12&as_of={as_of}')
                cold_d_sec = time.perf_counter() - t0
                assert res_cold_d.status_code == 200, f"District cold returned {res_cold_d.status_code}"
                cold_d_queries = wrapped_conn.query_count
                cold_d_db_time = wrapped_conn.query_duration

                warm_d_timings = []
                for _ in range(5):
                    t0 = time.perf_counter()
                    res_warm_d = client.get(f'/api/predict/climate-12m/{district_id}?months=12&as_of={as_of}')
                    warm_d_timings.append(time.perf_counter() - t0)
                    assert res_warm_d.status_code == 200

                results['district_endpoint'] = {
                    'cold_ms': round(cold_d_sec * 1000, 2),
                    'cold_queries': cold_d_queries,
                    'cold_db_ms': round(cold_d_db_time * 1000, 2),
                    'warm_ms_avg': round(sum(warm_d_timings) / len(warm_d_timings) * 1000, 2),
                    'warm_ms_min': round(min(warm_d_timings) * 1000, 2),
                }
                print(f"District Cold: {cold_d_sec * 1000:.2f}ms (DB: {cold_d_db_time * 1000:.2f}ms across {cold_d_queries} queries)")
                print(f"District Warm: {min(warm_d_timings) * 1000:.2f}ms")

                # 4. State Latencies
                print(f"\n--- 3. State Endpoint Latency (/api/predict/state/{state_id}) ---")
                clear_storage_l1_caches()
                wrapped_conn.query_count = 0
                wrapped_conn.query_duration = 0.0

                t0 = time.perf_counter()
                res_cold_s = client.get(f'/api/predict/state/{state_id}?horizon=12&as_of={as_of}')
                cold_s_sec = time.perf_counter() - t0
                assert res_cold_s.status_code == 200, f"State cold returned {res_cold_s.status_code}"
                cold_s_queries = wrapped_conn.query_count
                cold_s_db_time = wrapped_conn.query_duration

                warm_s_timings = []
                for _ in range(5):
                    t0 = time.perf_counter()
                    res_warm_s = client.get(f'/api/predict/state/{state_id}?horizon=12&as_of={as_of}')
                    warm_s_timings.append(time.perf_counter() - t0)
                    assert res_warm_s.status_code == 200

                results['state_endpoint'] = {
                    'cold_ms': round(cold_s_sec * 1000, 2),
                    'cold_queries': cold_s_queries,
                    'cold_db_ms': round(cold_s_db_time * 1000, 2),
                    'warm_ms_avg': round(sum(warm_s_timings) / len(warm_s_timings) * 1000, 2),
                    'warm_ms_min': round(min(warm_s_timings) * 1000, 2),
                }
                print(f"State Cold: {cold_s_sec * 1000:.2f}ms (DB: {cold_s_db_time * 1000:.2f}ms across {cold_s_queries} queries)")
                print(f"State Warm: {min(warm_s_timings) * 1000:.2f}ms")

                # 5. Nationwide Summary Latencies
                print(f"\n--- 4. Nationwide State Summary Latency (/api/states/summary) ---")
                clear_storage_l1_caches()
                wrapped_conn.query_count = 0
                wrapped_conn.query_duration = 0.0

                t0 = time.perf_counter()
                res_cold_sum = client.get(f'/api/states/summary?horizon=12&as_of={as_of}')
                cold_sum_sec = time.perf_counter() - t0
                assert res_cold_sum.status_code == 200, f"Summary cold returned {res_cold_sum.status_code}"
                cold_sum_queries = wrapped_conn.query_count
                cold_sum_db_time = wrapped_conn.query_duration

                warm_sum_timings = []
                for _ in range(5):
                    t0 = time.perf_counter()
                    res_warm_sum = client.get(f'/api/states/summary?horizon=12&as_of={as_of}')
                    warm_sum_timings.append(time.perf_counter() - t0)
                    assert res_warm_sum.status_code == 200

                results['nationwide_summary'] = {
                    'cold_ms': round(cold_sum_sec * 1000, 2),
                    'cold_queries': cold_sum_queries,
                    'cold_db_ms': round(cold_sum_db_time * 1000, 2),
                    'warm_ms_avg': round(sum(warm_sum_timings) / len(warm_sum_timings) * 1000, 2),
                    'warm_ms_min': round(min(warm_sum_timings) * 1000, 2),
                }
                print(f"Summary Cold: {cold_sum_sec * 1000:.2f}ms (DB: {cold_sum_db_time * 1000:.2f}ms across {cold_sum_queries} queries)")
                print(f"Summary Warm: {min(warm_sum_timings) * 1000:.2f}ms")

                # 6. Initial States Page Sequence
                print(f"\n--- 5. States Page Sequence (Registry -> Concurrent State + Summary) ---")
                clear_storage_l1_caches()

                page_start = time.perf_counter()
                reg_res = client.get(f'/api/states?as_of={as_of}')
                reg_time = time.perf_counter() - page_start
                assert reg_res.status_code == 200

                def fetch_path(p):
                    t_start = time.perf_counter()
                    with app.test_client() as c:
                        r = c.get(p)
                    return {'path': p, 'status': r.status_code, 'duration_ms': (time.perf_counter() - t_start) * 1000}

                concurrent_paths = [
                    f'/api/predict/state/{state_id}?horizon=12&as_of={as_of}',
                    f'/api/states/summary?horizon=12&as_of={as_of}'
                ]
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(fetch_path, p) for p in concurrent_paths]
                    concurrent_results = [f.result() for f in futures]

                total_page_time = time.perf_counter() - page_start
                results['states_page_sequence'] = {
                    'total_sequence_ms': round(total_page_time * 1000, 2),
                    'registry_ms': round(reg_time * 1000, 2),
                    'concurrent_requests': concurrent_results,
                }
                print(f"States Page Sequence Total: {total_page_time * 1000:.2f}ms")
                for c_res in concurrent_results:
                    print(f"  {c_res['path']}: {c_res['duration_ms']:.2f}ms (HTTP {c_res['status']})")

        # 7. Comparison Table vs Previous Baseline
        # Previous cold nationwide summary was 39.42s; previous page sequence was ~40.82s
        comparison = {
            'metric': [
                'Precomputation Duration',
                'Cold District Endpoint (/api/predict/climate-12m)',
                'Warm District Endpoint',
                'Cold State Endpoint (/api/predict/state)',
                'Warm State Endpoint',
                'Cold Nationwide Summary (/api/states/summary)',
                'Warm Nationwide Summary',
                'States Page Concurrent API Sequence',
            ],
            'before_dynamic_inference': [
                'N/A (Computed on request)',
                '~150 ms (inferred)',
                '~25 ms',
                '~5.93 s (inferred 19 districts)',
                '~10 ms',
                '39.42 s (inferred 426 districts)',
                '41.7 ms',
                '40.82 s',
            ],
            'after_persistent_storage': [
                f"{results['precomputation']['duration_seconds']} s (background ahead-of-time)",
                f"{results['district_endpoint']['cold_ms']} ms",
                f"{results['district_endpoint']['warm_ms_min']} ms",
                f"{results['state_endpoint']['cold_ms']} ms",
                f"{results['state_endpoint']['warm_ms_min']} ms",
                f"{results['nationwide_summary']['cold_ms']} ms",
                f"{results['nationwide_summary']['warm_ms_min']} ms",
                f"{results['states_page_sequence']['total_sequence_ms']} ms",
            ],
            'speedup_or_reduction': [
                'Decoupled from user requests',
                'Normal read avoids model inference',
                'Cached in memory',
                f"{round(5930 / max(results['state_endpoint']['cold_ms'], 1), 1)}x faster cold read",
                'Cached in memory',
                f"{round(39420 / max(results['nationwide_summary']['cold_ms'], 1), 1)}x faster cold read",
                'Cached in memory',
                f"{round(40820 / max(results['states_page_sequence']['total_sequence_ms'], 1), 1)}x faster page load",
            ]
        }
        results['comparison'] = comparison

        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nBenchmark results saved to {args.output}")

    finally:
        print(f"Cleaning up isolated benchmark schema {schema_name}...")
        cleanup_benchmark_schema(schema_name, conn)


if __name__ == '__main__':
    main()
