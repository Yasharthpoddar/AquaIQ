"""Comprehensive regression tests for persistent XGBoost forecast storage and precomputation.

Uses isolated PostgreSQL test schemas (aquaiq_test_<uuid>) to ensure
the user's live public database is never modified.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from io import BytesIO
import json
from pathlib import Path
import sys
import uuid

import numpy as np
import pandas as pd
from psycopg2 import sql
import pytest

from db.connection import get_connection
import db.connection as dbc
from models import forecast_storage, state_forecast as sf, climate_forecast_12m as climate
from models.forecast_storage import (
    compute_input_identity, get_active_generation, get_generation_diagnostics,
    get_district_forecast, get_state_forecast, get_nationwide_summary,
    save_generation_atomic, clear_storage_l1_caches
)
from scripts.precompute_forecasts import run_precomputation
from api.app import create_app

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.requires_db


@pytest.fixture(scope='module')
def generated_outputs(tmp_path_factory):
    """Compute the real nationwide inference once; each test gets isolated storage."""
    directory = tmp_path_factory.mktemp('nationwide')
    run_precomputation(as_of='2026-10-25', dry_run=True, export_dir=directory)
    return json.loads((directory/'districts.json').read_text(encoding='utf-8'))


class IsolatedConnectionWrapper:
    """Connection wrapper that prevents premature connection closure during multi-query tests."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        # Intentional no-op: fixture teardown manages actual underlying connection lifecycle
        pass

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def isolated_db(generated_outputs, monkeypatch):
    """Create an isolated test schema in PostgreSQL and clean it up after test."""
    try:
        raw_conn = get_connection()
    except Exception as exc:
        pytest.skip(f"PostgreSQL connection unavailable for storage tests: {exc}")

    test_schema = f"aquaiq_storage_test_{uuid.uuid4().hex}"
    try:
        with raw_conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(test_schema)))
            cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(test_schema)))
            cur.execute((ROOT / "db/migrations/004_xgboost_forecast_storage.sql").read_text(encoding="utf-8"))
        raw_conn.commit()
    except Exception as exc:
        raw_conn.close()
        pytest.skip(f"Failed to initialize isolated test schema: {exc}")

    wrapper = IsolatedConnectionWrapper(raw_conn)
    import scripts.precompute_forecasts as precompute
    monkeypatch.setattr(precompute, 'forecast_district', lambda did,*a,**kw: deepcopy(generated_outputs[did]))
    clear_storage_l1_caches()
    yield wrapper, test_schema

    try:
        with raw_conn.cursor() as cur:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(test_schema)))
        raw_conn.commit()
    finally:
        raw_conn.close()
        clear_storage_l1_caches()


def test_migration_004_creates_all_tables_and_indexes(isolated_db):
    conn, schema = isolated_db
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = %s
        """, (schema,))
        tables = {row[0] for row in cur.fetchall()}
        required = {
            'forecast_generations',
            'district_forecast_records',
            'district_forecast_horizons',
            'state_forecast_records',
            'state_forecast_horizons',
            'nationwide_summary_records',
        }
        assert required.issubset(tables)

        cur.execute("SELECT version FROM schema_migrations WHERE version = '004_xgboost_forecast_storage'")
        assert cur.fetchone() is not None


def test_precomputation_and_atomic_publication(isolated_db):
    conn, _ = isolated_db
    as_of = '2026-10-25'

    # Run precomputation for a small batch in the test schema
    res = run_precomputation(as_of=as_of, horizon=12, batch_size=100, connection=conn)
    assert res['status'] == 'published'
    assert res['districts_total'] == len(compute_input_identity(as_of)['districts'])
    assert res['districts_forecast'] == res['districts_total']
    assert res['states_total'] == 36
    assert res['states_available'] == len(sf.STATES_REGISTRY)

    # Verify active generation lookup
    active = get_active_generation(as_of, connection=conn)
    assert active is not None
    assert active['status'] == 'published'
    assert active['generation_id'] == res['generation_id']

    # Verify state read
    hr_forecast = get_state_forecast('HR', as_of, connection=conn)
    assert hr_forecast is not None
    assert hr_forecast['state_id'] == 'HR'
    assert hr_forecast['status'] == 'forecast'
    assert len(hr_forecast['forecast']) == 12

    # Verify nationwide summary read
    summary = get_nationwide_summary(as_of, connection=conn)
    assert summary is not None
    assert summary['product'] == 'state_groundwater_summary'
    assert summary['available_states_count'] == len(sf.STATES_REGISTRY)
    assert len(summary['states']) == 36


def test_idempotent_repeated_precomputation(isolated_db):
    conn, _ = isolated_db
    as_of = '2026-10-25'

    first = run_precomputation(as_of=as_of, horizon=12, connection=conn)
    assert first['status'] == 'published'

    # Second run without force should detect existing published generation
    second = run_precomputation(as_of=as_of, horizon=12, connection=conn, force=False)
    assert second['status'] == 'already_published'
    assert second['generation']['generation_id'] == first['generation_id']


def test_unique_keys_and_duplicate_prevention(isolated_db):
    conn, _ = isolated_db
    as_of = '2026-10-25'
    run_precomputation(as_of=as_of, horizon=12, connection=conn)

    active = get_active_generation(as_of, connection=conn)
    gen_id = active['generation_id']

    with conn.cursor() as cur:
        # Duplicate district record under same generation should violate unique constraint
        with pytest.raises(Exception):
            cur.execute("""
                INSERT INTO district_forecast_records (
                    generation_id, district_id, as_of, forecast_origin, status, payload_json
                ) VALUES (%s, 'HR-Kaithal', %s, %s, 'forecast', '{}')
            """, (gen_id, as_of, '2026-10-01'))

    conn.rollback()


def test_exact_equivalence_computed_vs_persisted(isolated_db):
    conn, _ = isolated_db
    as_of = '2026-10-25'
    run_precomputation(as_of=as_of, horizon=12, connection=conn)

    # Every state value must exactly average the same persisted district panel.
    persisted_hr = get_state_forecast('HR', as_of, connection=conn)
    panel = [get_district_forecast(d, as_of, connection=conn) for d in persisted_hr['districts']]
    for h, row in enumerate(persisted_hr['forecast']):
        assert row['predicted_gwl'] == round(float(np.mean([p['forecast'][h]['predicted_gwl'] for p in panel])), 4)
    # The supported path retains the verified existing XGBoost numerical outputs.
    persisted_d = get_district_forecast('HR-Kaithal', as_of, connection=conn)
    computed_d = climate.forecast_next_twelve_months('HR-Kaithal', as_of, _allow_storage=False)
    assert persisted_d['evidence_tier'] == 'A'
    for p_h, c_h in zip(persisted_d['forecast'], computed_d['forecast']):
        assert p_h['predicted_gwl'] == c_h['predicted_gwl']


def test_invalidation_when_model_or_feature_signature_changes(isolated_db, monkeypatch):
    conn, _ = isolated_db
    as_of = '2026-10-25'
    run_precomputation(as_of=as_of, horizon=12, connection=conn)

    # Simulate an incompatible model version / hash
    orig_identity = compute_input_identity(as_of)
    tampered_identity = deepcopy(orig_identity)
    tampered_identity['generation_signature'] = '0' * 64

    # Active generation check should fail
    active = get_active_generation(as_of, connection=conn, identity=tampered_identity)
    assert active is None

    # Diagnostics should identify signature mismatch
    monkeypatch.setattr(forecast_storage, 'compute_input_identity', lambda *a, **kw: tampered_identity)
    diag = get_generation_diagnostics(as_of, connection=conn)
    assert diag['code'] == 'generation_stale'
    assert diag['status'] == 'model_unavailable'


def test_concurrent_reads_return_independent_defensive_copies(isolated_db):
    conn, _ = isolated_db
    as_of = '2026-10-25'
    run_precomputation(as_of=as_of, horizon=12, connection=conn)

    def read_and_mutate():
        val = get_state_forecast('HR', as_of, connection=conn)
        val['forecast'][0]['predicted_gwl'] = -999.0
        return val

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: read_and_mutate(), range(4)))

    fresh = get_state_forecast('HR', as_of, connection=conn)
    assert fresh['forecast'][0]['predicted_gwl'] > 0
    assert fresh['forecast'][0]['predicted_gwl'] != -999.0


def test_api_serves_persisted_forecasts_and_prevents_inference(isolated_db, monkeypatch):
    conn, _ = isolated_db
    as_of = '2026-10-25'
    run_precomputation(as_of=as_of, horizon=12, connection=conn)

    # Monkeypatch db.connection.get_connection so routes use isolated test schema
    monkeypatch.setattr(dbc, 'get_connection', lambda: conn)

    # Ensure model inference is NEVER called during normal API reads
    def forbidden_inference(*a, **kw):
        raise AssertionError("Inference must not be executed during persisted API read!")
    monkeypatch.setattr(climate, 'forecast_from_evidence', forbidden_inference)

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()

    # 1. Nationwide summary endpoint
    res_summary = client.get(f'/api/states/summary?horizon=12&as_of={as_of}')
    assert res_summary.status_code == 200
    data_summary = res_summary.get_json()
    assert data_summary['available_states_count'] == len(sf.STATES_REGISTRY)
    assert len(data_summary['states']) == 36

    # 2. State endpoint
    res_state = client.get(f'/api/predict/state/HR?horizon=12&as_of={as_of}')
    assert res_state.status_code == 200
    data_state = res_state.get_json()
    assert data_state['state_id'] == 'HR'
    assert data_state['status'] == 'forecast'
    assert len(data_state['forecast']) == 12

    # 3. District climate-12m endpoint
    res_district = client.get(f'/api/predict/climate-12m/HR-Kaithal?months=12&as_of={as_of}')
    assert res_district.status_code == 200
    data_district = res_district.get_json()
    assert data_district['district_id'] == 'HR-Kaithal'
    assert data_district['status'] == 'forecast'
    assert len(data_district['forecast']) == 12


def test_api_returns_503_when_generation_missing_and_sync_disabled(isolated_db, monkeypatch):
    conn, _ = isolated_db
    as_of = '2026-10-25'
    clear_storage_l1_caches()

    # Ensure no active generation is present
    monkeypatch.setattr(dbc, 'get_connection', lambda: conn)
    monkeypatch.setenv("AQUAIQ_ENABLE_SYNC_FORECAST_FALLBACK", "false")
    monkeypatch.setenv("AQUAIQ_REQUIRE_PERSISTED_FORECASTS", "true")

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()

    res = client.get(f'/api/predict/state/HR?horizon=12&as_of={as_of}')
    assert res.status_code == 503
    payload = res.get_json()
    assert payload['status'] == 'model_unavailable'
    assert 'precompute' in payload['message'].lower()


def test_six_month_district_api_preserved():
    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()

    res = client.get('/api/predict/HR-Kaithal?window=next_six_months&months=6&as_of=2026-10-25')
    assert res.status_code == 200
    data = res.get_json()
    assert data['requested_id'] == 'HR-Kaithal'
    assert 'forecast' in data


def test_incomplete_and_mid_transaction_failure_preserve_published_generation(isolated_db, generated_outputs, monkeypatch):
    """Both validation rejection and SQL failure leave the previous pointer/rows."""
    import models.forecast_storage as storage
    conn, _ = isolated_db
    as_of = '2026-10-25'
    result = run_precomputation(as_of=as_of, connection=conn)
    identity = compute_input_identity(as_of)
    states = {code:get_state_forecast(code, as_of, connection=conn) for code in sf.STATES_REGISTRY}
    summary = get_nationwide_summary(as_of, connection=conn)
    incomplete = deepcopy(generated_outputs)
    incomplete.pop(next(iter(incomplete)))
    with pytest.raises(ValueError,match='registry'):
        save_generation_atomic(identity,incomplete,states,summary,connection=conn)
    # New identity, valid complete outputs, then deliberately fail after headers.
    changed = deepcopy(identity);changed['generation_id']=str(uuid.uuid4());changed['generation_signature']='f'*64
    districts = deepcopy(generated_outputs);new_states=deepcopy(states);new_summary=deepcopy(summary)
    for value in [*districts.values(),*new_states.values(),new_summary]:value['generation_id']=changed['generation_id']
    original=storage.execute_values;calls=[]
    def fail_on_second(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise RuntimeError('Injected district-horizon write failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(storage,'execute_values',fail_on_second)
    with pytest.raises(RuntimeError,match='Injected'):
        save_generation_atomic(changed,districts,new_states,new_summary,connection=conn)
    assert get_active_generation(as_of,connection=conn)['generation_id']==result['generation_id']
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM forecast_generations WHERE generation_id=%s',(changed['generation_id'],))
        assert cur.fetchone()[0]==0


def test_published_reads_survive_missing_live_artifacts_and_cache_changes(isolated_db, monkeypatch):
    conn,_=isolated_db;as_of='2026-10-25'
    result=run_precomputation(as_of=as_of,connection=conn)
    clear_storage_l1_caches()
    monkeypatch.setattr(forecast_storage,'compute_input_identity',lambda *a,**kw:(_ for _ in ()).throw(FileNotFoundError('unavailable source')))
    assert get_active_generation(as_of,connection=conn)['generation_id']==result['generation_id']
    assert get_district_forecast('HR-Kaithal',as_of,connection=conn)['status']=='forecast'
    # Another worker supersedes a generation: no process-local pointer may serve it.
    with conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE forecast_generations SET status='superseded' WHERE generation_id=%s",(result['generation_id'],))
    assert get_active_generation(as_of,connection=conn) is None


def test_validate_only_detects_corrupt_normalized_storage(isolated_db):
    from models.forecast_storage import validate_stored_generation
    conn,_=isolated_db;as_of='2026-10-25'
    run_precomputation(as_of=as_of,connection=conn)
    identity=compute_input_identity(as_of)
    assert validate_stored_generation(identity,conn)['horizons']==12*len(identity['districts'])
    with conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM district_forecast_horizons WHERE generation_id=%s AND district_id=%s AND horizon=12',(identity['generation_id'],'HR-Kaithal'))
    with pytest.raises(ValueError,match='horizons missing'):
        validate_stored_generation(identity,conn)
