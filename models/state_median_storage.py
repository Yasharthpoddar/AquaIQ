"""Immutable experimental state snapshots in the existing PostgreSQL store.

The candidate has independent tables and vintage selection. Reading it never
starts training/inference or depends on current district model assets.
"""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import uuid5, NAMESPACE_URL

import pandas as pd
from psycopg2 import sql
from psycopg2.extras import Json, execute_values

from db.connection import finite_json, get_connection
from models.forecast_storage import storage_connection
from models.ensemble import _completed_feature_month
from models.state_mapping import resolve_state_id, STATES_REGISTRY

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = '1.0-state-median-xgboost'
MODEL_NAME = 'state_median_xgboost'
PRODUCT_NAME = 'state_median_groundwater_12m_forecast'
TIERED_MODEL_VERSION = '2.0-state-median-tiered'
TIERED_MODEL_NAME = 'state_median_tiered'
POLICY_VERSION = '1.0-state-median-coverage'


def _calendar_date(value):
    if isinstance(value, date):
        return date.fromisoformat(value.isoformat()[:10])
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Candidate as_of must be YYYY-MM-DD.')
    return date.fromisoformat(value)


def _depth(value, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Candidate depths must be finite nonnegative metres below ground level.')


def _coverage(row):
    count = row.get('contributing_districts_count')
    total = row.get('total_districts_in_state')
    percent = row.get('district_coverage_pct')
    if (isinstance(count, bool) or not isinstance(count, int)
            or isinstance(total, bool) or not isinstance(total, int)
            or not 0 <= count <= total or isinstance(percent, bool)
            or not isinstance(percent, (float, int)) or not math.isfinite(percent)
            or not 0 <= percent <= 100):
        raise ValueError('Candidate district coverage counts are invalid.')
    expected = 100 * count / total if total else 0.
    if abs(percent-expected) > .11:
        raise ValueError('Candidate district coverage counts and percentage are inconsistent.')
    return count, total


def validate_generation(payloads):
    """Reject incomplete snapshots and malformed historical/forecast calendars."""
    if not isinstance(payloads, dict) or set(payloads) != set(STATES_REGISTRY):
        raise ValueError('Candidate generation must contain exactly the 36 registered states/UTs.')
    versions = {payload.get('model_version') for payload in payloads.values()}
    tiered = versions == {TIERED_MODEL_VERSION}
    if versions not in ({MODEL_VERSION}, {TIERED_MODEL_VERSION}):
        raise ValueError('Generation model metadata must use one supported state model version.')
    cutoffs = set()
    for code, payload in payloads.items():
        if (payload.get('state_id') != code or payload.get('product') != PRODUCT_NAME
                or payload.get('model_version') != (TIERED_MODEL_VERSION if tiered else MODEL_VERSION)
                or payload.get('model_name') != (TIERED_MODEL_NAME if tiered else MODEL_NAME)
                or payload.get('units') != 'm_bgl' or payload.get('horizon_months') != 12
                or payload.get('promotion_status') != 'experimental'):
            raise ValueError('Candidate state, model or units metadata is invalid.')
        cutoff = _calendar_date(payload.get('as_of'))
        cutoffs.add(cutoff)
        if cutoff > date.today():
            raise ValueError('Candidate as_of cannot be in the future.')
        origin = pd.Timestamp(cutoff).to_period('M').to_timestamp()
        completed = _completed_feature_month(pd.Timestamp(cutoff)).date()
        if payload.get('forecast_origin') != origin.date().isoformat():
            raise ValueError('Candidate forecast origin must match the as_of calendar month.')
        try:
            generated_at = datetime.fromisoformat(payload.get('computed_at', ''))
            if generated_at.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError('Candidate computation timestamp must include a timezone.') from None
        _coverage(payload)
        min_coverage = payload.get('min_coverage', .5)
        if (isinstance(min_coverage, bool) or not isinstance(min_coverage, (float, int))
                or not math.isfinite(min_coverage) or not 0 <= min_coverage <= 1):
            raise ValueError('Candidate minimum coverage must be a proportion between zero and one.')
        status = payload.get('status')
        method = payload.get('forecast_method') if tiered else MODEL_NAME
        if tiered and (payload.get('policy_version') != POLICY_VERSION or
                method not in (MODEL_NAME,'persistence_fallback','no_observations') or
                not re.fullmatch(r'[a-f0-9]{64}',str(payload.get('policy_sha256','')))):
            raise ValueError('Tiered forecast policy identity or method is invalid.')
        if status not in ('forecast', 'insufficient_data', 'model_unavailable'):
            raise ValueError('Candidate status is invalid.')
        forecasts = payload.get('forecast')
        if not isinstance(forecasts, list) or len(forecasts) != (12 if status == 'forecast' else 0):
            raise ValueError('Candidate must contain twelve forecast months or an explicit unavailable status.')
        for horizon, row in enumerate(forecasts, 1):
            expected = (origin + pd.DateOffset(months=horizon)).date().isoformat()
            if row.get('target_date', row.get('date')) != expected or row.get('horizon') != horizon:
                raise ValueError('Candidate forecast calendar is invalid.')
            _depth(row.get('predicted_gwl'))
            if row.get('is_observed') is not False or row.get('is_forecast') is not True:
                raise ValueError('Candidate forecast provenance flags are invalid.')
        training_cutoff = payload.get('training_cutoff')
        if training_cutoff is not None and _calendar_date(training_cutoff) > cutoff:
            raise ValueError('Candidate training cutoff exceeds its as_of date.')
        if status == 'forecast' and method == MODEL_NAME:
            if training_cutoff is None or not re.fullmatch(r'[a-f0-9]{64}', str(payload.get('model_sha256', ''))):
                raise ValueError('Candidate forecasts require a training cutoff and model SHA-256.')
            if _calendar_date(training_cutoff) > completed:
                raise ValueError('Candidate training labels exceed the latest completed input month.')
        elif status != 'forecast' and (not isinstance(payload.get('message'), str) or not payload['message'].strip()):
            raise ValueError('Unavailable candidate requires an explanatory message.')
        history = payload.get('history')
        if not isinstance(history, list):
            raise ValueError('Candidate history must be a list, including explicit missing months.')
        previous = None
        for row in history:
            stamp = _calendar_date(row.get('date', row.get('month')))
            if stamp.day != 1 or stamp > completed or (previous is not None and stamp <= previous):
                raise ValueError('Candidate history dates must be ordered unique completed month starts.')
            if previous is not None and stamp != (pd.Timestamp(previous)+pd.DateOffset(months=1)).date():
                raise ValueError('Candidate historical gaps require explicit missing monthly rows.')
            previous = stamp
            value = row.get('gwl_m_bgl', row.get('historical_median_depth'))
            _depth(value, nullable=True)
            if row.get('is_forecast') is True:
                raise ValueError('Candidate history cannot contain forecast values.')
            count, total = _coverage(row)
            if total != payload['total_districts_in_state']:
                raise ValueError('Historical and forecast registered district totals differ.')
            coverage = row.get('coverage_ratio')
            if (isinstance(coverage, bool) or not isinstance(coverage, (int, float))
                    or not 0 <= coverage <= 1 or abs(coverage*100-row['district_coverage_pct']) > .11):
                raise ValueError('Candidate historical coverage must match its district counts.')
            observations = row.get('observation_count')
            if (isinstance(observations, bool) or not isinstance(observations, int)
                    or observations < count or (count == 0 and observations != 0)):
                raise ValueError('Candidate observation count must include every contributing district.')
            if (count == 0) != (value is None):
                raise ValueError('Candidate historical median and observation counts are inconsistent.')
            eligible = row.get('training_eligible')
            if not isinstance(eligible, bool) or eligible != (value is not None and coverage >= min_coverage and count >= min(2, total)):
                raise ValueError('Candidate historical target eligibility conflicts with coverage quality rules.')
            quality = 'coverage_qualified' if eligible else 'low_coverage' if count else 'missing'
            if 'observation_quality' in row and row['observation_quality'] != quality:
                raise ValueError('Candidate observation quality conflicts with its target eligibility.')
        evaluation = payload.get('evaluation')
        if not isinstance(evaluation, dict) or not isinstance(evaluation.get('status'), str):
            raise ValueError('Candidate requires held-out evaluation metadata or an explicit unavailable evaluation.')
        n = evaluation.get('n')
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError('Candidate evaluation count is invalid.')
        if n:
            _depth(evaluation.get('mae_m'))
            _depth(evaluation.get('rmse_m'))
            start, end = (_calendar_date(evaluation.get(name)) for name in ('period_start', 'period_end'))
            if start > end or end > cutoff:
                raise ValueError('Candidate held-out evaluation period is invalid.')
        elif evaluation.get('mae_m') is not None or evaluation.get('rmse_m') is not None:
            raise ValueError('Candidate error metrics require held-out observations.')
        if tiered:
            _validate_tiered_state(payload,origin,completed,n)
    if len(cutoffs) != 1:
        raise ValueError('Candidate generation must use one as_of date.')
    # A strict JSON encoding also rejects non-finite values in any metadata.
    json.dumps(payloads, allow_nan=False)
    return {'states_total': len(payloads), 'as_of': next(iter(cutoffs)).isoformat()}


def _validate_tiered_state(payload, origin, completed, evaluation_n):
    method,status = payload['forecast_method'],payload['status']
    months,observations = payload.get('genuine_observed_months'),payload.get('genuine_observation_count')
    if (isinstance(months,bool) or not isinstance(months,int) or months < 0
            or isinstance(observations,bool) or not isinstance(observations,int)
            or observations < months or ((months==0) != (observations==0))):
        raise ValueError('Genuine observation counts are invalid.')
    observed_history = [row for row in payload['history'] if row['gwl_m_bgl'] is not None]
    if any(row.get('is_observed') is not True or row.get('is_forecast') is not False for row in observed_history):
        raise ValueError('Genuine historical medians must retain explicit observation provenance.')
    if len(observed_history) > months or sum(row['observation_count'] for row in observed_history) > observations:
        raise ValueError('Historical observations exceed the declared genuine observation inventory.')
    if method != MODEL_NAME and (payload.get('model_sha256') is not None or payload.get('training_cutoff') is not None):
        raise ValueError('Fallback/no-data methods cannot claim fitted state model weights or a training cutoff.')
    if method == 'no_observations':
        if (status != 'insufficient_data' or months or observations or observed_history
                or payload.get('reference_observation') is not None
                or payload.get('last_observed_gwl_m_bgl') is not None
                or payload.get('historical_reference_date') is not None
                or payload.get('latest_observation_date') is not None
                or payload.get('observation_age_months') is not None
                or payload.get('reference_age_months') is not None
                or payload.get('features') != [] or evaluation_n):
            raise ValueError('No-observations status requires genuinely empty history and no forecast/model evidence.')
        return
    if not months or not observations:
        raise ValueError('A state forecast requires at least one genuine observation.')
    if status not in ('forecast','model_unavailable'):
        raise ValueError('States with genuine observations cannot be labelled insufficient_data.')
    reference = payload.get('reference_observation')
    if not isinstance(reference,dict) or reference.get('is_observed') is not True or reference.get('is_forecast') is not False:
        raise ValueError('Tiered method requires a genuine reference observation.')
    stamp = _calendar_date(reference.get('date'))
    _depth(reference.get('gwl_m_bgl'))
    if stamp > completed or stamp.day != 1:
        raise ValueError('Reference observation must be a completed historical month.')
    matching = [row for row in payload['history'] if row['date']==stamp.isoformat()]
    for field in ('gwl_m_bgl','contributing_districts_count','total_districts_in_state','district_coverage_pct',
                  'coverage_ratio','observation_count','observation_quality','training_eligible'):
        if not matching or reference.get(field) != matching[0].get(field):
            raise ValueError('Reference observation differs from genuine source history.')
    age = (origin.year-stamp.year)*12+origin.month-stamp.month
    reference_age = payload.get('reference_age_months')
    if (payload.get('historical_reference_date') != stamp.isoformat()
            or payload.get('last_observed_gwl_m_bgl') != reference['gwl_m_bgl']
            or isinstance(reference_age,bool) or not isinstance(reference_age,int) or reference_age != age
            or payload.get('reference_training_eligible') is not reference['training_eligible']
            or payload['contributing_districts_count'] != reference['contributing_districts_count']
            or abs(payload['district_coverage_pct']-reference['district_coverage_pct']) > .000001):
        raise ValueError('Reference depth, date, age or coverage metadata is inconsistent.')
    latest_date = _calendar_date(payload.get('latest_observation_date'))
    latest_age = (origin.year-latest_date.year)*12+origin.month-latest_date.month
    observation_age = payload.get('observation_age_months')
    if (latest_date > completed or latest_date < stamp or isinstance(observation_age,bool)
            or not isinstance(observation_age,int) or observation_age != latest_age):
        raise ValueError('Latest genuine observation age or date is inconsistent.')
    if not observed_history or latest_date != max(_calendar_date(row['date']) for row in observed_history):
        raise ValueError('Latest observation metadata hides newer genuine observations.')
    if 'normal_reporting_interval_months' in payload or 'reference_is_stale' in payload:
        interval = payload.get('normal_reporting_interval_months')
        if (isinstance(interval,bool) or not isinstance(interval,int) or interval <= 0
                or payload.get('reference_is_stale') is not (age > interval)):
            raise ValueError('Historical reference staleness must match its age and reporting interval.')
    if method == MODEL_NAME:
        if not reference['training_eligible'] or stamp >= origin.date() or age > 12:
            raise ValueError('XGBoost reference must retain its qualified, recent, pre-origin safeguards.')
        if not payload.get('features'):
            raise ValueError('XGBoost feature schema is missing.')
    else:
        if (payload.get('features') != ['latest_genuine_state_median'] or not isinstance(payload.get('fallback_reason'),str)
                or not payload['fallback_reason'].strip() or latest_date != stamp
                or any(row['predicted_gwl'] != reference['gwl_m_bgl'] for row in payload['forecast'])
                or evaluation_n or payload['evaluation'].get('status') != 'not_evaluated_for_fallback'):
            raise ValueError('Persistence fallback must repeat its latest genuine median with explicit limitations and no XGBoost metrics.')
        if observed_history and stamp != max(_calendar_date(row['date']) for row in observed_history):
            raise ValueError('Persistence fallback must use the latest genuine historical median.')


def save_generation(payloads, test_schema=None):
    """Persist one complete candidate atomically; only private schemas auto-migrate.

    Identical input payloads reuse their immutable generation. A changed payload
    creates a separate candidate vintage; no production publication is changed.
    """
    payloads = finite_json(deepcopy(payloads))
    metadata = validate_generation(payloads)
    version = next(iter(payloads.values()))['model_version']
    canonical = json.dumps(payloads, sort_keys=True, separators=(',', ':'), allow_nan=False)
    signature = hashlib.sha256(canonical.encode()).hexdigest()
    generation_id = str(uuid5(NAMESPACE_URL, 'aquaiq:state_median:' + signature))
    if test_schema is not None and (not re.fullmatch(r'aquaiq_test_[a-z0-9_]+', test_schema) or len(test_schema) > 63):
        raise ValueError('Candidate test schema must be aquaiq_test_* with lowercase identifiers, at most 63 characters.')
    connection = get_connection() if test_schema is not None else storage_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                if test_schema is not None:
                    cursor.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(test_schema)))
                    cursor.execute(sql.SQL('SET LOCAL search_path TO {}, pg_temp').format(sql.Identifier(test_schema)))
                    cursor.execute((ROOT/'db/migrations/006_state_median_forecasts.sql').read_text(encoding='utf-8'))
                cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('aquaiq:state_median:' + metadata['as_of'],))
                cursor.execute('''INSERT INTO state_median_generations
                    (generation_id, generation_signature, as_of, model_version, status, states_total)
                    VALUES (%s,%s,%s,%s,'experimental',%s) ON CONFLICT DO NOTHING''',
                    (generation_id, signature, metadata['as_of'], version, metadata['states_total']))
                inserted = cursor.rowcount > 0
                if inserted:
                    rows = [(generation_id, code, metadata['as_of'], version, payload['status'],
                             payload.get('training_cutoff'), payload.get('model_sha256'), Json(payload))
                            for code, payload in sorted(payloads.items())]
                    execute_values(cursor, '''INSERT INTO state_median_forecast_records
                        (generation_id,state_id,as_of,model_version,status,training_cutoff,model_sha256,payload_json)
                        VALUES %s''', rows)
                cursor.execute('SELECT state_id,payload_json FROM state_median_forecast_records WHERE generation_id=%s', (generation_id,))
                stored = dict(cursor.fetchall())
                validate_generation(stored)
                if stored != payloads:
                    raise ValueError('Immutable candidate generation differs from its payload signature.')
        return {'generation_id': generation_id, 'status': 'persisted_experimental',
                'states_total': metadata['states_total'], 'as_of': metadata['as_of'], 'reused': not inserted}
    finally:
        connection.close()


def get_state_forecast(state_id, as_of=None):
    """Read exact explicit vintage or latest candidate vintage no later than today."""
    code = resolve_state_id(state_id)
    cutoff = _calendar_date(as_of) if as_of is not None else date.today()
    if cutoff > date.today():
        raise ValueError('Candidate as_of cannot be in the future.')
    connection = storage_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('state_median_generations')")
            if cursor.fetchone()[0] is None:
                return None
            operator = '=' if as_of is not None else '<='
            cursor.execute('''SELECT r.payload_json,g.generation_id FROM state_median_generations g
                JOIN state_median_forecast_records r ON r.generation_id=g.generation_id
                WHERE g.status='experimental' AND g.model_version=%s AND r.state_id=%s AND g.as_of ''' + operator + ''' %s
                ORDER BY g.as_of DESC,g.created_at DESC,g.generation_id DESC LIMIT 1''',
                (MODEL_VERSION, code, cutoff))
            row = cursor.fetchone()
            if row is None:
                return None
            result = deepcopy(row[0])
            result['generation_id'] = str(row[1])
            result['persistence_status'] = 'experimental'
            return result
    finally:
        connection.close()
