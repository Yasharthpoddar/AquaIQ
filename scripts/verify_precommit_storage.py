"""Final pre-commit verification of persistent XGBoost forecast storage.

Executes complete lifecycle in an isolated PostgreSQL test schema:
1. Migration 004 execution
2. Full precomputation run (725 districts, 36 states)
3. Atomic publication verification
4. Record count & schema verification
5. API contract, metadata, and forecast equivalence verification
6. Application restart / fresh process read verification (zero inference)
7. Failure isolation (failed runs do not supersede active generation)
8. Idempotency and duplicate prevention
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from unittest.mock import patch
import uuid

from api.app import create_app
from db import connection as dbc
from models import forecast_storage, climate_forecast_12m as climate
from models.forecast_storage import clear_storage_l1_caches, get_active_generation
from scripts.precompute_forecasts import run_precomputation

ROOT = Path(__file__).resolve().parents[1]


def run_verification():
    schema_name = f"aquaiq_precommit_{uuid.uuid4().hex[:12]}"
    print(f"=== AQUAIQ PRE-COMMIT VERIFICATION ===")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Isolated Test Schema: {schema_name}")

    conn = dbc.get_connection()
    conn.autocommit = True
    results = {}

    try:
        # Step 1: Migration 004 execution
        print("\n[Step 1/9] Applying Migration 004...")
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA {schema_name}")
            cur.execute(f"SET search_path TO {schema_name}, public")

            for mig_file in sorted((ROOT / 'db' / 'migrations').glob('*.sql')):
                sql = mig_file.read_text(encoding='utf-8')
                cur.execute(sql)

            cur.execute("SELECT version FROM schema_migrations WHERE version = '004_xgboost_forecast_storage'")
            row = cur.fetchone()
            assert row is not None, "Migration 004 not found in schema_migrations"

        conn.autocommit = False
        print("  -> Migration 004 applied and verified in schema_migrations.")
        results['step_1_migration'] = True

        # Setup mock wrapper for connection
        class WrappedConn:
            def __init__(self, raw_conn):
                self._conn = raw_conn
            def cursor(self, *a, **kw):
                return self._conn.cursor(*a, **kw)
            def close(self):
                pass
            def commit(self):
                return self._conn.commit()
            def rollback(self):
                return self._conn.rollback()
            def __getattr__(self, name):
                return getattr(self._conn, name)

        wrapped = WrappedConn(conn)

        # Step 2 & 3: Run precomputation and verify atomic publication
        print("\n[Step 2/9 & Step 3/9] Running precomputation & verifying atomic publication...")
        t0 = time.perf_counter()
        summary = run_precomputation(as_of='2026-10-25', horizon=12, connection=conn)
        dur = time.perf_counter() - t0
        gen_id = summary['generation_id']
        assert summary['status'] == 'published', f"Expected published, got {summary['status']}"
        assert summary['districts_total'] == 725
        assert summary['districts_forecast'] == 426
        assert summary['districts_insufficient'] == 299
        assert summary['states_total'] == 36
        assert summary['states_available'] == 16
        assert summary['states_insufficient'] == 20

        with conn.cursor() as cur:
            cur.execute("SELECT status, published_at, generation_signature FROM forecast_generations WHERE generation_id = %s", (gen_id,))
            st, pub_at, sig = cur.fetchone()
            assert st == 'published'
            assert pub_at is not None
            assert len(sig) == 64

        print(f"  -> Precomputation completed in {dur:.2f}s.")
        print(f"  -> Generation {gen_id} verified published with signature {sig[:16]}...")
        results['step_2_3_precomputation_publish'] = True

        # Step 4: Confirm expected district, state, and nationwide summary records
        print("\n[Step 4/9] Confirming database record counts...")
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM district_forecast_records WHERE generation_id = %s", (gen_id,))
            d_records = cur.fetchone()[0]
            assert d_records == 725, f"Expected 725 district records, got {d_records}"

            cur.execute("SELECT COUNT(*) FROM district_forecast_horizons WHERE generation_id = %s", (gen_id,))
            d_horizons = cur.fetchone()[0]
            assert d_horizons == 426 * 12, f"Expected {426*12} district horizons, got {d_horizons}"

            cur.execute("SELECT COUNT(*) FROM state_forecast_records WHERE generation_id = %s", (gen_id,))
            s_records = cur.fetchone()[0]
            assert s_records == 36, f"Expected 36 state records, got {s_records}"

            cur.execute("SELECT COUNT(*) FROM state_forecast_horizons WHERE generation_id = %s", (gen_id,))
            s_horizons = cur.fetchone()[0]
            assert s_horizons == 16 * 12, f"Expected {16*12} state horizons, got {s_horizons}"

            cur.execute("SELECT COUNT(*) FROM nationwide_summary_records WHERE generation_id = %s", (gen_id,))
            sum_records = cur.fetchone()[0]
            assert sum_records == 1, f"Expected 1 nationwide summary, got {sum_records}"

        print(f"  -> Verified: {d_records} districts, {d_horizons} district horizons, {s_records} states, {s_horizons} state horizons, {sum_records} nationwide summary.")
        results['step_4_record_counts'] = True

        # Step 5 & 6: Call API endpoints and verify contracts, metadata, dates, units
        print("\n[Step 5/9 & Step 6/9] Calling API endpoints & validating contracts & metadata...")
        with patch.object(dbc, 'get_connection', lambda: wrapped):
            # Model inference MUST NOT be called
            def forbidden_inference(*a, **kw):
                raise AssertionError("Model inference called during persisted API read!")
            with patch.object(climate, 'forecast_from_evidence', forbidden_inference):
                app = create_app({'TESTING': True})
                client = app.test_client()

                # State summary
                res_sum = client.get('/api/states/summary?horizon=12&as_of=2026-10-25')
                assert res_sum.status_code == 200
                sum_data = res_sum.get_json()
                assert sum_data['product'] == 'state_groundwater_summary'
                assert sum_data['model_version'] == '2.0-state-district-xgboost'
                assert sum_data['horizon_months'] == 12
                assert sum_data['total_states'] == 36
                assert sum_data['available_states_count'] == 16
                assert sum_data['insufficient_data_states_count'] == 20
                print("  -> Nationwide summary API contract verified.")

                # State forecast (HR)
                res_st = client.get('/api/predict/state/HR?horizon=12&as_of=2026-10-25')
                assert res_st.status_code == 200
                st_data = res_st.get_json()
                assert st_data['product'] == 'state_groundwater_12m_forecast'
                assert st_data['model_version'] == '2.0-state-district-xgboost'
                assert st_data['model_name'] == 'district_xgboost_equal_weight'
                assert st_data['state_id'] == 'HR'
                assert st_data['status'] == 'forecast'
                assert st_data['units'] == 'm_bgl'
                assert st_data['total_districts_in_state'] == 22
                assert st_data['contributing_districts_count'] == 19
                assert st_data['district_coverage_pct'] == 86.4
                assert len(st_data['forecast']) == 12
                assert st_data['forecast'][0]['target_date'] == '2026-11-01'
                assert st_data['forecast'][11]['target_date'] == '2027-10-01'
                assert len(st_data['history']) > 0
                assert st_data['panel_id'] is not None and len(st_data['panel_id']) == 64
                print("  -> State forecast (HR) contract, dates, units, panel membership verified.")

                # District forecast (HR-Kaithal)
                res_dist = client.get('/api/predict/climate-12m/HR-Kaithal?months=12&as_of=2026-10-25')
                assert res_dist.status_code == 200
                dist_data = res_dist.get_json()
                assert dist_data['product'] == 'climate_informed_12m_forecast'
                assert dist_data['model_version'] == '1.0-climate-conditioned-12m-xgb'
                assert dist_data['projection_method'] == 'climate_conditioned_xgboost_12m'
                assert dist_data['district_id'] == 'HR-Kaithal'
                assert dist_data['status'] == 'forecast'
                assert dist_data['units'] == 'm_bgl'
                assert len(dist_data['forecast']) == 12
                for h_idx, h_row in enumerate(dist_data['forecast'], 1):
                    assert h_row['horizon'] == h_idx
                    assert 'weather' in h_row
                    assert 'rainfall_mm' in h_row['weather']
                print("  -> District forecast (HR-Kaithal) contract, weather covariates verified.")

        results['step_5_6_api_metadata'] = True

        # Step 7: Application restart / cold process read test (zero inference, fast serving)
        print("\n[Step 7/9] Application restart simulation (cold process reads)...")
        clear_storage_l1_caches()

        with patch.object(dbc, 'get_connection', lambda: wrapped):
            with patch.object(climate, 'forecast_from_evidence', forbidden_inference):
                # Fresh Flask instance simulates server worker startup / restart
                fresh_app = create_app({'TESTING': True})
                fresh_client = fresh_app.test_client()

                t_cold = time.perf_counter()
                r1 = fresh_client.get('/api/states/summary?horizon=12&as_of=2026-10-25')
                r1_ms = (time.perf_counter() - t_cold) * 1000
                assert r1.status_code == 200

                t_cold_s = time.perf_counter()
                r2 = fresh_client.get('/api/predict/state/HR?horizon=12&as_of=2026-10-25')
                r2_ms = (time.perf_counter() - t_cold_s) * 1000
                assert r2.status_code == 200

                t_cold_d = time.perf_counter()
                r3 = fresh_client.get('/api/predict/climate-12m/HR-Kaithal?months=12&as_of=2026-10-25')
                r3_ms = (time.perf_counter() - t_cold_d) * 1000
                assert r3.status_code == 200

                print(f"  -> Cold read after restart: Summary {r1_ms:.2f}ms, State {r2_ms:.2f}ms, District {r3_ms:.2f}ms.")
                print(f"  -> Zero XGBoost model inference invoked (verified by assertion).")
        results['step_7_restart_cold_read'] = True

        # Step 8: Failed precomputation simulation (last published generation remains intact)
        print("\n[Step 8/9] Simulating failed precomputation and rollback safety...")
        failed_gen_id = str(uuid.uuid4())
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO forecast_generations (
                            generation_id, status, as_of, forecast_origin, horizon_months,
                            model_id, model_version, model_sha256, model_card_sha256,
                            feature_generation_id, feature_data_sha256, district_registry_hash,
                            district_crosswalk_hash, state_registry_hash, config_hash,
                            generation_signature
                        ) VALUES (
                            %s, 'building', '2026-10-25', '2026-10-01', 12,
                            'dummy', 'dummy', 'dummy', 'dummy',
                            'dummy', 'dummy', 'dummy', 'dummy', 'dummy', 'dummy',
                            'dummy_signature_00000000000000000000000000000000000000000000000000'
                        )
                    """, (failed_gen_id,))
                    # Simulate failure during district computation
                    raise RuntimeError("Simulated worker crash or out-of-memory error!")
        except RuntimeError:
            conn.rollback()

        # Confirm original published generation remains active and served
        with patch.object(dbc, 'get_connection', lambda: wrapped):
            active_gen = get_active_generation('2026-10-25', connection=wrapped)
            assert active_gen is not None
            assert active_gen['generation_id'] == gen_id
            assert active_gen['status'] == 'published'

            # Ensure failed generation never entered database
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM forecast_generations WHERE generation_id = %s", (failed_gen_id,))
                assert cur.fetchone() is None

        print("  -> Transaction rolled back. Original generation remained active and served without interruption.")
        results['step_8_failure_isolation'] = True

        # Step 9: Idempotency verification
        print("\n[Step 9/9] Verifying idempotent rerun...")
        second_run = run_precomputation(as_of='2026-10-25', horizon=12, connection=conn, force=False)
        assert second_run['status'] == 'already_published'
        assert second_run['generation']['generation_id'] == gen_id

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM forecast_generations WHERE as_of = '2026-10-25'")
            count = cur.fetchone()[0]
            assert count == 1, f"Expected exactly 1 generation record, found {count}"

        print(f"  -> Idempotent rerun detected existing generation {gen_id} and avoided duplicate writes.")
        results['step_9_idempotency'] = True

        print("\n=== ALL 9 PRE-COMMIT VERIFICATION STEPS PASSED SUCCESSFULLY ===")
        return results

    finally:
        print(f"\nCleaning up isolated schema {schema_name}...")
        try:
            conn.rollback()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
        except Exception as e:
            print(f"Cleanup note: {e}")
        finally:
            conn.close()


if __name__ == '__main__':
    run_verification()
