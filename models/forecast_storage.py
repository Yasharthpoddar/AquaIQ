"""Persistent, versioned serving for complete district and state forecasts.

Maintains generation lifecycle, input identity verification, and multi-worker safety
using PostgreSQL backing and bounded process-local L1 caching.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
from io import BytesIO
import json
import os
import re
from pathlib import Path
from threading import RLock
from uuid import uuid5, NAMESPACE_URL

import numpy as np
import pandas as pd
from psycopg2.extras import execute_batch, execute_values, Json
from psycopg2 import sql

from db import connection as dbc
from db.connection import finite_json
from models import climate_forecast_12m as climate
from models.ensemble import _as_of, CONFIG
from models.state_mapping import resolve_state_id, STATES_REGISTRY
from models.forecast_cache import ForecastCache
from models.district_registry import get_registry
from models.tiered_forecast import VERSION as PIPELINE_VERSION, CALIBRATION_PATH, validate_complete_generation

ROOT = Path(__file__).resolve().parents[1]

_STORAGE_LOCK = RLock()
_DISTRICT_L1_CACHE = ForecastCache(1500)
_STATE_L1_CACHE = ForecastCache(80)
_SUMMARY_L1_CACHE = {}
_ACTIVE_GENERATION_CACHE = {}


def storage_connection():
    """Optional isolated forecast namespace; source tables are never rewritten."""
    conn = dbc.get_connection()
    schema = os.getenv('AQUAIQ_FORECAST_SCHEMA')
    if schema:
        if not re.fullmatch(r'aquaiq_test_[a-z0-9_]+', schema):
            conn.close()
            raise ValueError('Forecast test schema must start aquaiq_test_ and contain lowercase identifiers.')
        with conn.cursor() as cur:
            cur.execute('SELECT to_regnamespace(%s)', (schema,))
            if cur.fetchone()[0] is None:
                conn.close()
                raise ValueError('Isolated forecast schema does not exist.')
            cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        conn.commit()
    return conn


def _file_signature(paths):
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.exists())


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)


def compute_input_identity(as_of=None, horizon=12, *, feature_directory=None, checkpoint=None, calibration_path=None):
    """Compute verified hash identities for all inputs to the 12-month XGBoost forecast."""
    if horizon != 12:
        raise ValueError("Only horizon=12 is currently supported for XGBoost precomputation.")
    cutoff = _as_of(as_of).date()
    origin = cutoff.replace(day=1)

    # 1. Feature matrix and manifest
    directory = Path(feature_directory) if feature_directory is not None else ROOT / 'data/processed'
    manifest_path = directory / 'feature_manifest.json'
    matrix_path = directory / 'features_matrix.csv'
    if not manifest_path.exists() or not matrix_path.exists():
        raise FileNotFoundError("Processed feature matrix or manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    feature_generation_id = manifest.get('generation_id') or manifest.get('feature_generation_id', '')
    feature_data_sha256 = manifest.get('feature_csv_sha256') or manifest.get('data_sha256', '')

    # 2. Model bundle and card
    bundle = climate.load_bundle(checkpoint, expected_generation=feature_generation_id) if checkpoint is not None else climate.load_bundle(expected_generation=feature_generation_id)
    card = bundle[1]
    model_sha256 = card.get('model_sha256', '')
    model_card_sha256 = _sha256_bytes(json.dumps(card, sort_keys=True).encode('utf-8'))

    # 3. Crosswalk and state registry
    crosswalk_path = ROOT / 'data_ingestion/district_crosswalk.csv'
    crosswalk_raw = crosswalk_path.read_bytes() if crosswalk_path.exists() else b''
    crosswalk_hash = _sha256_bytes(crosswalk_raw)

    district_crosswalk_df = pd.read_csv(BytesIO(crosswalk_raw), usecols=['canonical_district_id'])
    districts = sorted(district_crosswalk_df.canonical_district_id.unique().tolist())
    registry = get_registry()
    district_registry_hash = _sha256_bytes(_canonical_json(registry).encode('utf-8'))
    state_registry_hash = _sha256_bytes(_canonical_json(STATES_REGISTRY).encode('utf-8'))
    config_hash = _sha256_bytes(_canonical_json(CONFIG).encode('utf-8'))

    calibration_file = Path(calibration_path) if calibration_path is not None else CALIBRATION_PATH
    signature_basis = {
        'pipeline_version': PIPELINE_VERSION,
        'implementation_sha256': _sha256_bytes(b''.join((ROOT / p).read_bytes() for p in (
            'models/tiered_forecast.py', 'models/district_registry.py', 'scripts/precompute_forecasts.py',
            'models/climate_forecast_12m.py', 'models/climate_inputs.py', 'models/monthly_projection.py'))),
        'calibration_sha256': _sha256_bytes(calibration_file.read_bytes()) if calibration_file.exists() else None,
        'as_of': cutoff.isoformat(),
        'horizon_months': 12,
        'model_id': 'tiered_district_12m_forecast',
        'model_version': PIPELINE_VERSION,
        'model_sha256': model_sha256,
        'model_card_sha256': model_card_sha256,
        'feature_generation_id': feature_generation_id,
        'feature_data_sha256': feature_data_sha256,
        'district_registry_hash': district_registry_hash,
        'district_crosswalk_hash': crosswalk_hash,
        'state_registry_hash': state_registry_hash,
        'config_hash': config_hash,
    }
    generation_signature = _sha256_bytes(_canonical_json(signature_basis).encode('utf-8'))
    generation_id = str(uuid5(NAMESPACE_URL, 'aquaiq:forecast_generation:' + generation_signature))

    return {
        'generation_id': generation_id,
        'generation_signature': generation_signature,
        'as_of': cutoff,
        'forecast_origin': origin,
        'horizon_months': 12,
        'model_id': 'tiered_district_12m_forecast',
        'model_version': PIPELINE_VERSION,
        'model_sha256': model_sha256,
        'model_card_sha256': model_card_sha256,
        'feature_generation_id': feature_generation_id,
        'feature_data_sha256': feature_data_sha256,
        'district_registry_hash': district_registry_hash,
        'district_crosswalk_hash': crosswalk_hash,
        'state_registry_hash': state_registry_hash,
        'config_hash': config_hash,
        'bundle': bundle,
        'districts': districts,
    }


def is_storage_available(connection=None):
    """Check if the database connection and forecast storage tables are accessible."""
    conn = connection
    close_after = False
    try:
        if conn is None:
            conn = storage_connection()
            close_after = True
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('forecast_generations')")
            return cur.fetchone()[0] is not None
    except Exception:
        return False
    finally:
        if close_after and conn is not None:
            conn.close()


def latest_published_as_of(cutoff=None):
    """Default pages pin one explicit published vintage, even after midnight."""
    conn = None
    try:
        conn = storage_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(as_of) FROM forecast_generations WHERE status='published' AND as_of<=%s", (_as_of(cutoff).date(),))
            return cur.fetchone()[0]
    except Exception:
        return None
    finally:
        if conn is not None: conn.close()


def get_active_generation(as_of=None, connection=None, identity=None):
    """Read the published snapshot; failed rebuilds/input changes never hide it.

    Builders pass identity explicitly for idempotency. Readers do not require
    live training assets. Never cache this pointer across transactions/workers.
    """
    cutoff = _as_of(as_of).date()

    conn = connection
    close_after = False
    try:
        if conn is None:
            conn = storage_connection()
            close_after = True
        with conn.cursor() as cur:
            condition = ' AND generation_signature = %s' if identity else ''
            cur.execute("""
                SELECT generation_id, status, as_of, forecast_origin, horizon_months,
                       model_id, model_version, model_sha256, feature_generation_id,
                       generation_signature, districts_total, districts_forecast,
                       districts_insufficient, states_total, states_available,
                       states_insufficient, published_at
                FROM forecast_generations
                WHERE status = 'published' AND as_of = %s
            """ + condition + ' ORDER BY published_at DESC LIMIT 1',
                (cutoff, identity['generation_signature']) if identity else (cutoff,))
            row = cur.fetchone()
            if not row:
                return None
            result = {
                'generation_id': str(row[0]),
                'status': row[1],
                'as_of': row[2].isoformat() if hasattr(row[2], 'isoformat') else str(row[2]),
                'forecast_origin': row[3].isoformat() if hasattr(row[3], 'isoformat') else str(row[3]),
                'horizon_months': row[4],
                'model_id': row[5],
                'model_version': row[6],
                'model_sha256': row[7],
                'feature_generation_id': row[8],
                'generation_signature': row[9],
                'districts_total': row[10],
                'districts_forecast': row[11],
                'districts_insufficient': row[12],
                'states_total': row[13],
                'states_available': row[14],
                'states_insufficient': row[15],
                'published_at': row[16].isoformat() if hasattr(row[16], 'isoformat') else str(row[16]),
            }
            return result
    except Exception:
        return None
    finally:
        if close_after and conn is not None:
            conn.close()


def get_generation_diagnostics(as_of=None, connection=None):
    """Explain why a persisted generation is missing or unavailable."""
    cutoff = _as_of(as_of).date()
    try:
        ident = compute_input_identity(cutoff)
    except Exception as exc:
        return {
            'code': 'model_data_unavailable',
            'status': 'model_unavailable',
            'message': f'Model artifacts or feature data could not be verified: {exc}',
            'reason': type(exc).__name__,
        }

    conn = connection
    close_after = False
    try:
        if conn is None:
            conn = storage_connection()
            close_after = True
        with conn.cursor() as cur:
            # Check if any generation exists for this as_of
            cur.execute("""
                SELECT generation_id, status, generation_signature, published_at, started_at
                FROM forecast_generations
                WHERE as_of = %s
                ORDER BY started_at DESC LIMIT 1
            """, (cutoff,))
            row = cur.fetchone()
            if not row:
                return {
                    'code': 'no_forecast_generation',
                    'status': 'model_unavailable',
                    'message': f"No forecast generation exists for as_of={cutoff.isoformat()}. Run 'python -m scripts.precompute_forecasts --horizon 12' to generate.",
                    'reason': 'forecast_generation_missing',
                }
            gen_id, status, sig, pub_at, started = row
            if status == 'published' and sig != ident['generation_signature']:
                return {
                    'code': 'generation_stale',
                    'status': 'model_unavailable',
                    'message': f"Stored generation ({gen_id}) was computed against a different model artifact or feature export. Recomputation required.",
                    'reason': 'generation_signature_mismatch',
                    'stored_signature': sig,
                    'current_signature': ident['generation_signature'],
                }
            if status == 'building':
                return {
                    'code': 'generation_building',
                    'status': 'model_unavailable',
                    'message': f"A forecast generation ({gen_id}) is currently building (started at {started}).",
                    'reason': 'generation_in_progress',
                }
            if status in ('failed', 'superseded'):
                return {
                    'code': f'generation_{status}',
                    'status': 'model_unavailable',
                    'message': f"The previous forecast generation ({gen_id}) is marked {status}. Run 'python -m scripts.precompute_forecasts' to publish a new generation.",
                    'reason': f'generation_{status}',
                }
            return {'code': 'available', 'status': 'available', 'generation_id': str(gen_id)}
    except Exception as exc:
        return {
            'code': 'storage_unavailable',
            'status': 'model_unavailable',
            'message': 'Forecast storage is unavailable; inspect server-side diagnostics.',
            'reason': type(exc).__name__,
        }
    finally:
        if close_after and conn is not None:
            conn.close()


def get_district_forecast(district_id, as_of=None, connection=None):
    """Retrieve precomputed district forecast from persistent storage."""
    cutoff = _as_of(as_of).date()
    active = get_active_generation(cutoff, connection=connection)
    if not active:
        return None

    gen_id = active['generation_id']
    cache_key = (gen_id, district_id)
    with _STORAGE_LOCK:
        cached = _DISTRICT_L1_CACHE.get(cache_key)
        if cached is not None:
            return deepcopy(cached)

    conn = connection
    close_after = False
    try:
        if conn is None:
            conn = storage_connection()
            close_after = True
        with conn.cursor() as cur:
            cur.execute("""
                SELECT payload_json FROM district_forecast_records
                WHERE generation_id = %s AND district_id = %s
            """, (gen_id, district_id))
            row = cur.fetchone()
            if not row:
                return None
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            with _STORAGE_LOCK:
                _DISTRICT_L1_CACHE.set(cache_key, payload)
            return deepcopy(payload)
    except Exception:
        return None
    finally:
        if close_after and conn is not None:
            conn.close()


def get_state_forecast(state_id, as_of=None, connection=None):
    """Retrieve precomputed state forecast from persistent storage."""
    code = resolve_state_id(state_id)
    cutoff = _as_of(as_of).date()
    active = get_active_generation(cutoff, connection=connection)
    if not active:
        return None

    gen_id = active['generation_id']
    cache_key = (gen_id, code)
    with _STORAGE_LOCK:
        cached = _STATE_L1_CACHE.get(cache_key)
        if cached is not None:
            return deepcopy(cached)

    conn = connection
    close_after = False
    try:
        if conn is None:
            conn = storage_connection()
            close_after = True
        with conn.cursor() as cur:
            cur.execute("""
                SELECT payload_json FROM state_forecast_records
                WHERE generation_id = %s AND state_id = %s
            """, (gen_id, code))
            row = cur.fetchone()
            if not row:
                return None
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            with _STORAGE_LOCK:
                _STATE_L1_CACHE.set(cache_key, payload)
            return deepcopy(payload)
    except Exception:
        return None
    finally:
        if close_after and conn is not None:
            conn.close()


def get_nationwide_summary(as_of=None, connection=None):
    """Retrieve precomputed nationwide state summary from persistent storage."""
    cutoff = _as_of(as_of).date()
    active = get_active_generation(cutoff, connection=connection)
    if not active:
        return None

    gen_id = active['generation_id']
    cache_key = (gen_id, cutoff.isoformat())
    with _STORAGE_LOCK:
        if cache_key in _SUMMARY_L1_CACHE:
            return deepcopy(_SUMMARY_L1_CACHE[cache_key])

    conn = connection
    close_after = False
    try:
        if conn is None:
            conn = storage_connection()
            close_after = True
        with conn.cursor() as cur:
            cur.execute("""
                SELECT payload_json FROM nationwide_summary_records
                WHERE generation_id = %s
            """, (gen_id,))
            row = cur.fetchone()
            if not row:
                return None
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            with _STORAGE_LOCK:
                _SUMMARY_L1_CACHE[cache_key] = payload
            return deepcopy(payload)
    except Exception:
        return None
    finally:
        if close_after and conn is not None:
            conn.close()


def save_generation_atomic(identity, district_results, state_results, nationwide_summary,
                           connection=None, notes=None):
    """Atomically persist a complete forecast generation and publish it in one transaction."""
    validate_complete_generation(identity, district_results, state_results, nationwide_summary)
    gen_id = identity['generation_id']
    as_of = identity['as_of']
    origin = identity['forecast_origin']

    district_records = []
    district_horizons = []
    d_forecast = 0
    d_insufficient = 0
    d_unavailable = 0

    for d_id, res in district_results.items():
        st = res.get('status', 'model_unavailable')
        if st == 'forecast':
            d_forecast += 1
        elif st == 'insufficient_data':
            d_insufficient += 1
        else:
            d_unavailable += 1

        payload_finite = finite_json(res)
        district_records.append((
            gen_id, d_id, as_of, origin, st,
            res.get('estimate_type'), res.get('source_zone'), res.get('zone_fallback_reason'),
            res.get('last_observed_date'), res.get('last_observed_gwl'), res.get('data_age_months'),
            res.get('estimated_current_gwl'), res.get('current_depth_basis'), res.get('message'),
            Json(res.get('weather_basis')) if res.get('weather_basis') else None,
            Json(payload_finite)
        ))

        if st == 'forecast':
            for h in res.get('forecast', []):
                w = h.get('weather', {})
                b = h.get('baselines', {})
                district_horizons.append((
                    gen_id, d_id, h['horizon'], h['date'], h['month'],
                    h['predicted_gwl'], h['delta_from_current_m'],
                    w.get('rainfall_mm'), w.get('temperature_c'), w.get('evapotranspiration_mm'),
                    b.get('persistence'), b.get('seasonal'), b.get('seasonal_reference_date')
                ))

    state_records = []
    state_horizons = []
    s_available = 0
    s_insufficient = 0

    for s_id, s_res in state_results.items():
        st = s_res.get('status', 'model_unavailable')
        if st == 'forecast' or st == 'available':
            s_available += 1
        else:
            s_insufficient += 1

        end = s_res['forecast'][-1] if s_res.get('status') == 'forecast' and s_res.get('forecast') else None
        p12_depth = end['predicted_gwl'] if end else None
        p12_delta = end['delta_from_current_m'] if end else None

        payload_finite = finite_json(s_res)
        state_records.append((
            gen_id, s_id, as_of, origin, st, s_res.get('panel_id'),
            s_res.get('total_districts_in_state', 0), s_res.get('contributing_districts_count', 0),
            s_res.get('district_coverage_pct', 0.0),
            Json(s_res.get('contributing_district_ids', [])),
            Json(s_res.get('excluded_districts', [])),
            s_res.get('estimated_current_gwl_m_bgl'),
            s_res.get('last_observed_date'), s_res.get('last_observed_gwl_m_bgl'),
            p12_depth, p12_delta, s_res.get('message'),
            Json(payload_finite)
        ))

        if s_res.get('status') == 'forecast':
            for h in s_res.get('forecast', []):
                t_date = h.get('target_date', '')
                state_horizons.append((
                    gen_id, s_id, h['horizon'], t_date, t_date[:7],
                    h['predicted_gwl'], h['delta_from_current_m']
                ))

    summary_finite = finite_json(nationwide_summary)

    conn = connection
    close_after = False
    try:
        if conn is None:
            conn = storage_connection()
            close_after = True

        with conn:
            with conn.cursor() as cur:
                # Serialize publishers for one origin, including separate workers.
                cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('aquaiq:forecast:'+str(as_of),))
                cur.execute('SELECT status FROM forecast_generations WHERE generation_id=%s', (gen_id,))
                existing = cur.fetchone()
                if existing:
                    raise ValueError('Generation identities are immutable; reuse an existing generation or change inputs.')
                # 1. Register building generation
                cur.execute("""
                    INSERT INTO forecast_generations (
                        generation_id, status, as_of, forecast_origin, horizon_months,
                        model_id, model_version, model_sha256, model_card_sha256,
                        feature_generation_id, feature_data_sha256, district_registry_hash,
                        district_crosswalk_hash, state_registry_hash, config_hash,
                        generation_signature, districts_total, districts_forecast,
                        districts_insufficient, districts_unavailable, states_total,
                        states_available, states_insufficient, notes
                    ) VALUES (
                        %s, 'building', %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s
                    )
                """, (
                    gen_id, as_of, origin, identity['horizon_months'],
                    identity['model_id'], identity['model_version'], identity['model_sha256'],
                    identity['model_card_sha256'], identity['feature_generation_id'],
                    identity['feature_data_sha256'], identity['district_registry_hash'],
                    identity['district_crosswalk_hash'], identity['state_registry_hash'],
                    identity['config_hash'], identity['generation_signature'],
                    len(district_records), d_forecast, d_insufficient, d_unavailable,
                    len(state_records), s_available, s_insufficient, notes
                ))

                # 2. Batch insert district records
                execute_values(cur, """
                    INSERT INTO district_forecast_records (
                        generation_id, district_id, as_of, forecast_origin, status,
                        estimate_type, source_zone, zone_fallback_reason,
                        last_observed_date, last_observed_gwl, data_age_months,
                        estimated_current_gwl, current_depth_basis, message,
                        weather_basis_json, payload_json
                    ) VALUES %s
                    ON CONFLICT (generation_id, district_id) DO UPDATE SET
                        status = EXCLUDED.status, payload_json = EXCLUDED.payload_json
                """, district_records)

                # 3. Batch insert district horizons
                if district_horizons:
                    execute_values(cur, """
                        INSERT INTO district_forecast_horizons (
                            generation_id, district_id, horizon, target_date, target_month,
                            predicted_gwl, delta_from_current_m, rainfall_mm, temperature_c,
                            evapotranspiration_mm, persistence_gwl, seasonal_gwl, seasonal_reference_date
                        ) VALUES %s
                        ON CONFLICT (generation_id, district_id, horizon) DO UPDATE SET
                            predicted_gwl = EXCLUDED.predicted_gwl, delta_from_current_m = EXCLUDED.delta_from_current_m
                    """, district_horizons)

                # 4. Batch insert state records
                execute_values(cur, """
                    INSERT INTO state_forecast_records (
                        generation_id, state_id, as_of, forecast_origin, status, panel_id,
                        total_districts, contributing_districts, district_coverage_pct,
                        contributing_district_ids, excluded_districts,
                        estimated_current_gwl_m_bgl, last_observed_date, last_observed_gwl_m_bgl,
                        forecast_12m_gwl_m_bgl, projected_change_12m_m, message, payload_json
                    ) VALUES %s
                    ON CONFLICT (generation_id, state_id) DO UPDATE SET
                        status = EXCLUDED.status, payload_json = EXCLUDED.payload_json
                """, state_records)

                # 5. Batch insert state horizons
                if state_horizons:
                    execute_values(cur, """
                        INSERT INTO state_forecast_horizons (
                            generation_id, state_id, horizon, target_date, target_month,
                            predicted_gwl, delta_from_current_m
                        ) VALUES %s
                        ON CONFLICT (generation_id, state_id, horizon) DO UPDATE SET
                            predicted_gwl = EXCLUDED.predicted_gwl, delta_from_current_m = EXCLUDED.delta_from_current_m
                    """, state_horizons)

                # 6. Insert nationwide summary record
                cur.execute("""
                    INSERT INTO nationwide_summary_records (
                        generation_id, as_of, total_states, available_states_count,
                        insufficient_data_states_count, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (generation_id) DO UPDATE SET payload_json = EXCLUDED.payload_json
                """, (
                    gen_id, as_of, len(state_records), s_available, s_insufficient, Json(summary_finite)
                ))

                # 7. Atomic publication: supersede any previous active generation for this as_of
                cur.execute('SELECT COUNT(*) FROM district_forecast_horizons WHERE generation_id=%s', (gen_id,))
                if cur.fetchone()[0] != 12*len(identity['districts']):
                    raise ValueError('Persisted district horizons are incomplete.')
                cur.execute('SELECT COUNT(*) FROM state_forecast_horizons WHERE generation_id=%s', (gen_id,))
                if cur.fetchone()[0] != 12*len(state_results):
                    raise ValueError('Persisted state horizons are incomplete.')
                cur.execute("""
                    UPDATE forecast_generations
                    SET status = 'superseded', superseded_at = CURRENT_TIMESTAMP
                    WHERE as_of = %s AND status = 'published' AND generation_id != %s
                """, (as_of, gen_id))

                # 8. Set this generation to published
                cur.execute("""
                    UPDATE forecast_generations
                    SET status = 'published', completed_at = CURRENT_TIMESTAMP, published_at = CURRENT_TIMESTAMP
                    WHERE generation_id = %s
                """, (gen_id,))

        # Update process L1 caches
        with _STORAGE_LOCK:
            _ACTIVE_GENERATION_CACHE[(as_of.isoformat(), identity['generation_signature'])] = {
                'generation_id': gen_id,
                'status': 'published',
                'as_of': as_of.isoformat(),
                'forecast_origin': origin.isoformat(),
                'horizon_months': 12,
                'model_id': identity['model_id'],
                'model_version': identity['model_version'],
                'model_sha256': identity['model_sha256'],
                'feature_generation_id': identity['feature_generation_id'],
                'generation_signature': identity['generation_signature'],
                'districts_total': len(district_records),
                'districts_forecast': d_forecast,
                'districts_insufficient': d_insufficient,
                'states_total': len(state_records),
                'states_available': s_available,
                'states_insufficient': s_insufficient,
                'published_at': datetime.now(timezone.utc).isoformat(),
            }
            _SUMMARY_L1_CACHE[(gen_id, as_of.isoformat())] = summary_finite

        return {
            'generation_id': gen_id,
            'status': 'published',
            'districts_total': len(district_records),
            'districts_forecast': d_forecast,
            'districts_insufficient': d_insufficient,
            'districts_unavailable': d_unavailable,
            'states_total': len(state_records),
            'states_available': s_available,
            'states_insufficient': s_insufficient,
        }
    finally:
        if close_after and conn is not None:
            conn.close()


def clear_storage_l1_caches():
    """Clear process-local L1 storage caches."""
    with _STORAGE_LOCK:
        _DISTRICT_L1_CACHE.clear()
        _STATE_L1_CACHE.clear()
        _SUMMARY_L1_CACHE.clear()
        _ACTIVE_GENERATION_CACHE.clear()


def validate_stored_generation(identity, connection=None):
    """Read and validate JSON plus normalized rows, rather than trusting a status."""
    own = connection is None
    conn = connection or storage_connection()
    try:
        gen_id = identity['generation_id']
        with conn.cursor() as cur:
            cur.execute('SELECT district_id,payload_json FROM district_forecast_records WHERE generation_id=%s', (gen_id,))
            districts = dict(cur.fetchall())
            cur.execute('SELECT state_id,payload_json FROM state_forecast_records WHERE generation_id=%s', (gen_id,))
            states = dict(cur.fetchall())
            cur.execute('SELECT payload_json FROM nationwide_summary_records WHERE generation_id=%s', (gen_id,))
            row = cur.fetchone()
            if not row: raise ValueError('Nationwide summary missing from storage.')
            report = validate_complete_generation(identity, districts, states, row[0])
            cur.execute('SELECT district_id,horizon,target_date,predicted_gwl FROM district_forecast_horizons WHERE generation_id=%s', (gen_id,))
            rows = cur.fetchall()
            if len(rows) != 12*len(districts): raise ValueError('Normalized district horizons missing.')
            for did,h,target,value in rows:
                item = districts[did]['forecast'][h-1]
                if target.isoformat()!=item['date'] or abs(value-item['predicted_gwl'])>max(.0001,abs(value)*1e-6):
                    raise ValueError('Normalized district horizon differs from payload.')
            cur.execute('SELECT state_id,horizon,target_date,predicted_gwl FROM state_forecast_horizons WHERE generation_id=%s', (gen_id,))
            rows = cur.fetchall()
            if len(rows)!=12*len(states): raise ValueError('Normalized state horizons missing.')
            for sid,h,target,value in rows:
                item=states[sid]['forecast'][h-1]
                if target.isoformat()!=item['target_date'] or abs(value-item['predicted_gwl'])>max(.0001,abs(value)*1e-6):
                    raise ValueError('Normalized state horizon differs from payload.')
            return report
    finally:
        if own: conn.close()
