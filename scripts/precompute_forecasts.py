"""Precompute and persist complete AquaIQ twelve-month district/state outputs.

Generates forecasts ahead of time, validates completeness and contracts,
and atomically publishes the generation in PostgreSQL for indexed API reads.

Usage:
    python -m scripts.precompute_forecasts --horizon 12
    python -m scripts.precompute_forecasts --horizon 12 --as-of 2026-10-25
    python -m scripts.precompute_forecasts --dry-run
    python -m scripts.precompute_forecasts --validate-only
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import re
from psycopg2 import sql

import numpy as np
import pandas as pd

from db.connection import get_connection, finite_json
from models.district_registry import get_registry, reconcile_features
from models.tiered_forecast import (RegionalReference, forecast_district, load_calibration, validate_complete_generation, VERSION)
from models import climate_forecast_12m as climate
from models.ensemble import _as_of, _completed_feature_month, _readiness
from models.state_forecast import (
    get_feature_matrix, state_observed_mask, get_state_districts,
    aggregate_state_observations, _validate_district_forecast,
    MIN_COVERAGE, MODEL_VERSION as STATE_MODEL_VERSION, PRODUCT_NAME as STATE_PRODUCT_NAME,
    MODEL_NAME as STATE_MODEL_NAME, EVALUATION_METRICS, STATE_LIMITATIONS
)
from models.state_mapping import STATES_REGISTRY, get_state_metadata
from models.forecast_storage import (
    compute_input_identity, get_active_generation, get_generation_diagnostics,
    save_generation_atomic, is_storage_available, validate_stored_generation
)

ROOT = Path(__file__).resolve().parents[1]
STATE_MODEL_VERSION = '3.0-state-tiered'
STATE_MODEL_NAME = 'district_tiered_equal_weight'
STATE_LIMITATIONS = [
    'Equal weights across every registered district; not area, well or groundwater-volume weights.',
    'The state mean mixes XGBoost forecasts, local persistence and zero-history regional/global references; inspect the evidence counts.',
    'Regional references share donors and errors may be correlated; averaging does not establish reliability.',
    'Observed history uses the districts reporting each month; its composition can differ from the complete forecast panel.',
    'Current depth and future estimates are unverified for operational use. Source month labels do not certify publication time or stable wells.',
]
FORECAST_OUTPUT_TABLES = (
    'forecast_generations', 'district_forecast_records',
    'district_forecast_horizons', 'state_forecast_records',
    'state_forecast_horizons', 'nationwide_summary_records',
)


def isolate_candidate_connection(connection):
    """Fail closed before candidate reads/writes can resolve public outputs.

    A matching current schema alone is insufficient: a caller's search path
    may fall through to public for missing tables. Require the actual six
    private base tables, then remove public from relation resolution. Explicit
    pg_temp last also prevents temporary relations from shadowing the outputs.
    """
    with connection.cursor() as cur:
        cur.execute('SELECT pg_catalog.current_schema()')
        schema = cur.fetchone()[0]
        if not re.fullmatch(r'aquaiq_test_[a-z0-9_]+', str(schema)):
            raise ValueError('Candidate publication is restricted to an aquaiq_test_* schema.')
        cur.execute('''SELECT c.relname, c.relkind, n.nspname
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relname = ANY(%s)''',
            (schema, list(FORECAST_OUTPUT_TABLES)))
        expected = {(name, 'r', schema) for name in FORECAST_OUTPUT_TABLES}
        if set(cur.fetchall()) != expected:
            raise ValueError('Candidate publication requires all six private base output tables; public fallback, views and foreign tables are forbidden.')
        cur.execute(sql.SQL('SET search_path TO {}, pg_temp').format(sql.Identifier(schema)))
    return schema


def run_precomputation(as_of=None, horizon=12, batch_size=50, dry_run=False,
                       validate_only=False, force=False, connection=None, notes=None, export_dir=None,
                       feature_directory=None, checkpoint=None, calibration_path=None):
    """Core reproducible precomputation pipeline for district and state XGBoost forecasts."""
    started_time = time.perf_counter()
    cutoff = _as_of(as_of).date()
    cutoff_ts = pd.Timestamp(cutoff)
    origin_ts = cutoff_ts.to_period('M').to_timestamp()

    print(f"AquaIQ Precomputation Pipeline — As-Of: {cutoff.isoformat()}, Horizon: {horizon}m")

    # 1. Establish and verify input identities
    explicit = any(value is not None for value in (feature_directory, checkpoint, calibration_path))
    if explicit and not all(value is not None for value in (feature_directory, checkpoint, calibration_path)):
        raise ValueError('Candidate generation requires explicit features, checkpoint and calibration paths.')
    if explicit and not dry_run:
        if connection is None:
            raise ValueError('Candidate publication requires an explicitly isolated test connection.')
        isolate_candidate_connection(connection)
    identity = (compute_input_identity(cutoff, horizon, feature_directory=feature_directory,
                checkpoint=checkpoint, calibration_path=calibration_path) if explicit
                else compute_input_identity(cutoff, horizon))
    print(f"Verified Model: {identity['model_version']} (SHA-256: {identity['model_sha256'][:16]}...)")
    print(f"Verified Feature Data: {identity['feature_generation_id']}")
    print(f"Generation Signature: {identity['generation_signature'][:16]}...")
    print(f"Generation ID: {identity['generation_id']}")

    # 2. Check for validate-only
    if validate_only:
        active = get_active_generation(cutoff, connection=connection, identity=identity)
        if active:
            validation = validate_stored_generation(identity, connection)
            print(f"SUCCESS: Generation {active['generation_id']} is published and active.")
            print(f"  Districts: {active['districts_forecast']} forecast, {active['districts_insufficient']} insufficient")
            print(f"  States: {active['states_available']} available, {active['states_insufficient']} insufficient")
            return {'status': 'validated', 'generation': active, 'validation': validation}
        diag = get_generation_diagnostics(cutoff, connection=connection)
        print(f"FAIL: No active generation matching current inputs ({diag.get('message')})")
        raise RuntimeError(f"Validation failed: {diag.get('message')}")

    # 3. Idempotency check
    if not dry_run:
        active = get_active_generation(cutoff, connection=connection, identity=identity)
        if active:
            validate_stored_generation(identity, connection)
            print(f"IDEMPOTENT SKIP: Active generation {active['generation_id']} is already published for these exact inputs.")
            return {'status': 'already_published', 'generation': active}

    # 4. Load verified snapshot once
    if explicit:
        from models.xgboost_model import load_feature_matrix
        frame = load_feature_matrix(feature_directory)
    else:
        frame = get_feature_matrix()
    if (frame.attrs.get('feature_generation_id') != identity['feature_generation_id']
            or frame.attrs['feature_manifest']['feature_csv_sha256'] != identity['feature_data_sha256']):
        raise RuntimeError('Feature snapshot changed after generation identity verification.')
    bundle = identity['bundle']
    card = bundle[1]
    districts = identity['districts']

    available = frame.loc[frame.date.le(_completed_feature_month(cutoff_ts))]
    district_groups = {d_id: group for d_id, group in available.groupby('district_id', sort=False)}

    print(f"Generating forecasts for {len(districts)} canonical districts in batches of {batch_size}...")

    # 5. One tiered district path around the unchanged verified XGBoost model.
    registry = get_registry()
    reconcile_features(frame, registry)
    meta_by_id = {r['district_id']: r for r in registry}
    reference = RegionalReference(available, cutoff_ts)
    calibration = (load_calibration(cutoff_ts, path=calibration_path,
        generation=identity['feature_generation_id'], bundle=bundle) if explicit else load_calibration(cutoff_ts))
    district_results = {}
    for idx, district_id in enumerate(districts, 1):
        district = district_groups.get(district_id, available.iloc[:0]).copy()
        val = forecast_district(district_id, district, cutoff_ts,
            identity['feature_generation_id'], bundle, reference, calibration=calibration)
        val.update(meta_by_id[district_id], generation_id=identity['generation_id'])
        val['provenance'] = {k: identity[k] for k in ('generation_signature', 'feature_generation_id',
            'feature_data_sha256', 'district_registry_hash', 'district_crosswalk_hash')}
        district_results[district_id] = val
        if idx % batch_size == 0 or idx == len(districts):
            print(f"  Processed {idx}/{len(districts)} districts", flush=True)

    # 6. State aggregation using exact eligible panel
    print("Aggregating complete state/UT forecasts with evidence counts...")
    state_results = {}
    summary_states_list = []

    for code, meta in sorted(STATES_REGISTRY.items(), key=lambda item: item[1]['name']):
        state_districts = get_state_districts(code)
        state_frame = frame.loc[frame.district_id.str.startswith(code + '-')].copy()
        history = aggregate_state_observations(code, cutoff_ts, _frame=state_frame, _districts=state_districts)

        panel = [district_results[d_id] for d_id in state_districts if district_results.get(d_id, {}).get('status') == 'forecast']
        ids = [p['district_id'] for p in panel]
        coverage = len(panel) / len(state_districts) if state_districts else 0.0
        coverage_pct = round(coverage * 100, 1)

        state_res = {
            'product': STATE_PRODUCT_NAME,
            'model_version': STATE_MODEL_VERSION,
            'model_name': STATE_MODEL_NAME,
            'state_id': code,
            'state_name': meta['name'],
            'state_type': meta['type'],
            'st_code': meta['st_code'],
            'units': 'm_bgl',
            'horizon_months': 12,
            'forecast_origin': origin_ts.date().isoformat(),
            'as_of': cutoff.isoformat(),
            'computed_at': datetime.now(timezone.utc).isoformat(),
            'districts': state_districts,
            'total_districts_in_state': len(state_districts),
            'contributing_districts_count': len(ids),
            'contributing_district_ids': ids,
            'excluded_districts': [
                {'district_id': d_id, 'reason': district_results.get(d_id, {}).get('message', 'District XGBoost inputs unavailable.')}
                for d_id in state_districts if d_id not in ids
            ],
            'district_coverage_pct': coverage_pct,
            'current_depth_basis': 'estimated_district_inputs',
            'aggregation_method': 'equal_weight_all_registered_districts',
            'generation_id': identity['generation_id'],
            'evidence_tier_counts': dict(Counter(p['evidence_tier'] for p in panel)),
            'evidence_tier_proportions': {t: sum(p['evidence_tier']==t for p in panel)/len(state_districts) for t in ('A','B','C','D')},
            'district_evidence': {p['district_id']: {'tier': p['evidence_tier'], 'method': p['forecast_method']} for p in panel},
            'evaluation_status': 'experimental_state_outlook',
            'evaluation': EVALUATION_METRICS,
            'limitations': STATE_LIMITATIONS,
            'history': [
                {
                    'date': r.date.date().isoformat(),
                    'gwl_m_bgl': float(r.gwl_m_bgl),
                    'contributing_districts_count': int(r.contributing_districts_count),
                    'total_districts_in_state': len(state_districts),
                    'district_coverage_pct': float(r.district_coverage_pct),
                    'is_observed': True,
                    'is_forecast': False
                }
                for r in history.tail(24).itertuples()
            ],
            'last_observed_date': history.iloc[-1].date.date().isoformat() if len(history) else None,
            'last_observed_gwl_m_bgl': float(history.iloc[-1].gwl_m_bgl) if len(history) else None,
        }

        if not state_districts or coverage < MIN_COVERAGE or len(panel) < min(2, len(state_districts)):
            state_res.update(
                status='insufficient_data',
                forecast=[],
                estimated_current_gwl_m_bgl=None,
                message='Insufficient district XGBoost coverage: at least 50% and two districts are required (one for a single-district state).'
            )
        else:
            anchor = float(np.mean([p['estimated_current_gwl'] for p in panel]))
            depths = np.mean([[row['predicted_gwl'] for row in p['forecast']] for p in panel], axis=0)
            state_res.update(
                status='forecast',
                estimated_current_gwl_m_bgl=round(anchor, 4),
                panel_id=hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest(),
                forecast=[
                    {
                        'horizon': h,
                        'target_date': (origin_ts + pd.DateOffset(months=h)).date().isoformat(),
                        'predicted_gwl': round(float(depth), 4),
                        'delta_from_current_m': round(float(depth - anchor), 4),
                        'units': 'm_bgl',
                        'is_observed': False,
                        'is_forecast': True
                    }
                    for h, depth in enumerate(depths, 1)
                ]
            )

        state_results[code] = state_res

        # Format summary state row
        end = state_res['forecast'][-1] if state_res['status'] == 'forecast' else None
        summary_states_list.append({
            'state_id': code,
            'state_name': meta['name'],
            'state_type': meta['type'],
            'st_code': meta['st_code'],
            'status': 'available' if end else state_res['status'],
            'total_districts': state_res['total_districts_in_state'],
            'contributing_districts': state_res['contributing_districts_count'],
            'district_coverage_pct': state_res['district_coverage_pct'],
            'last_observed_date': state_res.get('last_observed_date'),
            'current_gwl_m_bgl': state_res['estimated_current_gwl_m_bgl'],
            'estimated_current_gwl_m_bgl': state_res['estimated_current_gwl_m_bgl'],
            'forecast_12m_gwl_m_bgl': end['predicted_gwl'] if end else None,
            'projected_change_12m_m': end['delta_from_current_m'] if end else None,
            'unavailable_reason': state_res.get('message'),
            'evidence_tier_counts': state_res['evidence_tier_counts'],
            'evidence_tier_proportions': state_res['evidence_tier_proportions'],
            'aggregation_method': state_res['aggregation_method'],
        })

    # 7. Compile nationwide summary
    avail_count = sum(s['status'] == 'available' for s in summary_states_list)
    nationwide_summary = {
        'product': 'state_groundwater_summary',
        'generation_id': identity['generation_id'],
        'districts_total': len(districts),
        'districts_forecast': len(district_results),
        'evidence_tier_counts': dict(Counter(r['evidence_tier'] for r in district_results.values())),
        'aggregation_method': 'equal_weight_all_registered_districts',
        'model_version': STATE_MODEL_VERSION,
        'horizon_months': 12,
        'as_of': cutoff.isoformat(),
        'computed_at': datetime.now(timezone.utc).isoformat(),
        'total_states': len(summary_states_list),
        'available_states_count': avail_count,
        'insufficient_data_states_count': len(summary_states_list) - avail_count,
        'states': summary_states_list,
        'evaluation_summary': EVALUATION_METRICS,
        'limitations': STATE_LIMITATIONS,
    }

    # 8. Reject any omitted district, incomplete horizon or inconsistent state mean.
    validation = validate_complete_generation(identity, district_results, state_results, nationwide_summary)
    print(f"Validation successful: {validation}")
    if export_dir:
        export_dir = Path(export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        for name, value in [('districts', district_results), ('states', state_results), ('summary', nationwide_summary)]:
            (export_dir / (name+'.json')).write_text(json.dumps(finite_json(value), indent=2, allow_nan=False), encoding='utf-8')

    # 9. Persistence (if not dry run)
    if dry_run:
        print("DRY-RUN MODE: Skipping database persistence.")
        published_res = {
            'generation_id': identity['generation_id'],
            'status': 'dry_run_validated',
            'districts_total': len(district_results),
            'districts_forecast': sum(r.get('status') == 'forecast' for r in district_results.values()),
            'districts_insufficient': sum(r.get('status') == 'insufficient_data' for r in district_results.values()),
            'districts_unavailable': sum(r.get('status') not in ('forecast', 'insufficient_data') for r in district_results.values()),
            'states_total': len(state_results),
            'states_available': avail_count,
            'states_insufficient': len(state_results) - avail_count,
        }
    else:
        print(f"Persisting and atomically publishing generation {identity['generation_id']}...")
        published_res = save_generation_atomic(
            identity, district_results, state_results, nationwide_summary,
            connection=connection, notes=notes or 'CLI precompute_forecasts execution'
        )
        print("Generation successfully published!")

    total_seconds = time.perf_counter() - started_time
    published_res['validation'] = validation
    published_res['duration_seconds'] = round(total_seconds, 2)
    published_res['as_of'] = cutoff.isoformat()
    published_res['completed_at'] = datetime.now(timezone.utc).isoformat()

    print(f"\nPrecomputation Summary (completed in {total_seconds:.2f}s):")
    print(f"  Districts Total: {published_res['districts_total']}")
    print(f"  Districts Forecast: {published_res['districts_forecast']}")
    print(f"  Districts Insufficient: {published_res['districts_insufficient']}")
    print(f"  States Total: {published_res['states_total']}")
    print(f"  States Available: {published_res['states_available']}")
    print(f"  States Insufficient: {published_res['states_insufficient']}")

    return published_res


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--horizon', type=int, default=12, help='Forecast horizon in months (default: 12)')
    parser.add_argument('--as-of', default=None, help='Forecast as-of cutoff date (default: today / latest completed)')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size for district processing (default: 50)')
    parser.add_argument('--dry-run', action='store_true', help='Compute and validate without writing to database')
    parser.add_argument('--validate-only', action='store_true', help='Validate existing active generation without recomputing')
    parser.add_argument('--force', action='store_true', help='Recompute even if an identical active generation exists')
    parser.add_argument('--output', type=Path, default=None, help='Path to write summary execution JSON report')
    parser.add_argument('--export-dir', type=Path, help='Save complete district/state JSON outputs locally')
    parser.add_argument('--test-schema', help='Create/use an isolated aquaiq_test_* forecast schema; never changes public source tables')
    parser.add_argument('--feature-directory', type=Path, help='Verified candidate features; requires explicit checkpoint/calibration and dry-run or test schema')
    parser.add_argument('--checkpoint', type=Path, help='Candidate model pointer; the deployed artifact remains unchanged')
    parser.add_argument('--calibration-path', type=Path, help='Candidate calibration JSON, or an explicit absent path for unavailable ranges')
    args = parser.parse_args(argv)
    explicit = (args.feature_directory, args.checkpoint, args.calibration_path)
    if any(value is not None for value in explicit):
        if not all(value is not None for value in explicit) or not (args.dry_run or args.test_schema):
            parser.error('Explicit candidate inputs require all three paths and --dry-run or --test-schema.')

    connection = None
    if args.test_schema:
        if not re.fullmatch(r'aquaiq_test_[a-z0-9_]+', args.test_schema):
            parser.error('--test-schema must be aquaiq_test_* with lowercase letters, digits and underscores')
        connection = get_connection()
        with connection:
            with connection.cursor() as cur:
                cur.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(args.test_schema)))
                cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(args.test_schema)))
                cur.execute((ROOT/'db/migrations/004_xgboost_forecast_storage.sql').read_text(encoding='utf-8'))

    try:
        summary = run_precomputation(
            as_of=args.as_of,
            horizon=args.horizon,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            validate_only=args.validate_only,
            force=args.force, export_dir=args.export_dir, connection=connection,
            feature_directory=args.feature_directory, checkpoint=args.checkpoint,
            calibration_path=args.calibration_path
        )
    finally:
        if connection is not None: connection.close()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(finite_json(summary), indent=2), encoding='utf-8')
        print(f"Saved execution report to {args.output}")

    return summary


if __name__ == '__main__':
    main()
