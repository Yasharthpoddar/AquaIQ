"""Stage, publish, pin and roll back independent median States releases.

Release snapshots and publication events are immutable. One atomic pointer
selects the active version; historical reads require an actual publication.
Normal reads do not inspect model files or start inference.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import UUID, uuid5, NAMESPACE_URL

from psycopg2 import sql
from psycopg2.extras import Json, execute_values

from db import connection as dbc
from models.state_mapping import resolve_state_id, STATES_REGISTRY
from models.state_median_storage import (validate_generation, _calendar_date,
    _depth, MODEL_VERSION, MODEL_NAME, PRODUCT_NAME,
    TIERED_MODEL_VERSION, TIERED_MODEL_NAME, POLICY_VERSION)

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PRODUCT = 'state_median_groundwater_summary'


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('generation_id must be a valid release UUID.') from None


def _schema(test_schema=None):
    value = test_schema if test_schema is not None else os.getenv('AQUAIQ_STATE_MEDIAN_SCHEMA', 'public')
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', value):
        raise ValueError('Median release schema must be a lowercase PostgreSQL identifier, at most 63 characters.')
    if test_schema is not None and not value.startswith('aquaiq_test_'):
        raise ValueError('Explicit test schema must start aquaiq_test_.')
    return value


def _connect(test_schema=None, create=False):
    _schema(test_schema)  # Reject invalid explicit names before opening a connection.
    connection = dbc.get_connection()
    try:
        # get_connection loads the project's .env on the first request.
        schema = _schema(test_schema)
        with connection:
            with connection.cursor() as cursor:
                if create and test_schema is not None:
                    cursor.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema)))
                cursor.execute('SELECT to_regnamespace(%s)', (schema,))
                if cursor.fetchone()[0] is None:
                    raise ValueError('Configured median release schema does not exist.')
                cursor.execute(sql.SQL('SET search_path TO {}, pg_temp').format(sql.Identifier(schema)))
                if create and test_schema is not None:
                    for migration in ('006_state_median_forecasts.sql', '007_state_median_publication.sql'):
                        cursor.execute((ROOT/'db/migrations'/migration).read_text(encoding='utf-8'))
        return connection
    except Exception:
        connection.close()
        raise


def migrate_release_storage(test_schema=None):
    """Explicit additive migration entry point; callers guard production writes.

    Stage/publish never auto-migrate public or another production namespace.
    This function changes only the selected median namespace's output tables.
    """
    connection = _connect(test_schema,create=True)
    try:
        with connection:
            with connection.cursor() as cursor:
                for name in ('006_state_median_forecasts.sql','007_state_median_publication.sql'):
                    cursor.execute((ROOT/'db/migrations'/name).read_text(encoding='utf-8'))
                cursor.execute('SELECT current_schema()')
                schema = cursor.fetchone()[0]
        return dict(status='migrated',schema=schema,
                    migrations=['006_state_median_forecasts','007_state_median_publication'])
    finally:
        connection.close()


def validate_release(payloads, manifest):
    """Require one verified artifact/source identity across every state response."""
    metadata = validate_generation(payloads)
    required = {'artifact_release', 'model_card_sha256', 'model_version', 'training_cutoff',
                'feature_generation_id', 'data_sha256', 'registry_sha256', 'features',
                'package_versions', 'evaluation_report_sha256', 'models'}
    if not isinstance(manifest, dict) or required-set(manifest):
        raise ValueError('Release manifest is incomplete.')
    tiered = manifest.get('format_version') == 2
    if manifest.get('format_version') not in (None,1,2):
        raise ValueError('Unsupported state release manifest format.')
    expected_version = TIERED_MODEL_VERSION if tiered else MODEL_VERSION
    if (not isinstance(manifest['artifact_release'], str) or not manifest['artifact_release'].strip()
            or manifest['model_version'] != expected_version or not isinstance(manifest['features'], list)
            or not manifest['features'] or len(set(manifest['features'])) != len(manifest['features'])
            or not isinstance(manifest['package_versions'], dict) or not manifest['package_versions']
            or not isinstance(manifest['models'], dict)):
        raise ValueError('Release artifact version, schema or package metadata is invalid.')
    if tiered and (manifest.get('model_name') != TIERED_MODEL_NAME
            or manifest.get('policy_version') != POLICY_VERSION
            or not re.fullmatch(r'[a-f0-9]{64}',str(manifest.get('policy_sha256','')))
            or not re.fullmatch(r'[a-f0-9]{64}',str(manifest.get('xgboost_model_card_sha256','')))
            or not isinstance(manifest.get('policy_details'),dict) or not manifest['policy_details']
            or not isinstance(manifest.get('state_methods'),dict)
            or set(manifest['state_methods']) != set(STATES_REGISTRY)):
        raise ValueError('Tiered release requires a complete immutable method policy and base model-card identity.')
    for field in ('model_card_sha256', 'data_sha256', 'registry_sha256'):
        if not re.fullmatch(r'[a-f0-9]{64}', str(manifest[field])):
            raise ValueError('Release manifest requires SHA-256 artifact and source identities.')
    evaluation_sha = manifest['evaluation_report_sha256']
    if evaluation_sha is not None and not re.fullmatch(r'[a-f0-9]{64}', str(evaluation_sha)):
        raise ValueError('Evaluation report identity is invalid.')
    if not isinstance(manifest['feature_generation_id'], str) or not manifest['feature_generation_id']:
        raise ValueError('Release feature generation identity is missing.')
    _calendar_date(manifest['training_cutoff'])
    if set(manifest['models'])-set(STATES_REGISTRY):
        raise ValueError('Release manifest has an unknown state model.')
    for code, digest in manifest['models'].items():
        if not re.fullmatch(r'[a-f0-9]{64}', str(digest)):
            raise ValueError('Release state model SHA-256 is invalid.')
    for code, payload in payloads.items():
        method = payload.get('forecast_method') if tiered else MODEL_NAME
        if (payload.get('feature_generation') != manifest['feature_generation_id']
                or payload.get('artifact_release') != manifest['artifact_release']
                or payload.get('model_card_sha256') != manifest['model_card_sha256']
                or payload.get('source_data_sha256') != manifest['data_sha256']
                or payload.get('registry_sha256') != manifest['registry_sha256']):
            raise ValueError('Release payload and model/source/feature identities differ.')
        if method == MODEL_NAME and (payload.get('training_cutoff') != manifest['training_cutoff']
                or payload.get('features') != manifest['features']
                or payload.get('model_sha256') != manifest['models'].get(code)):
            raise ValueError('Release payload and trained XGBoost model/source/feature identities differ.')
        if tiered and (payload.get('policy_version') != manifest['policy_version']
                or payload.get('policy_sha256') != manifest['policy_sha256']
                or method != manifest['state_methods'][code]
                or ('xgboost_model_card_sha256' in payload and
                    payload['xgboost_model_card_sha256'] != manifest['xgboost_model_card_sha256'])):
            raise ValueError('Tiered payload differs from its released forecast method or policy.')
        if payload['status'] == 'forecast' and method == MODEL_NAME and code not in manifest['models']:
            raise ValueError('A forecast requires a released state model.')
        reference_date = payload.get('historical_reference_date')
        reference_depth = payload.get('last_observed_gwl_m_bgl')
        if reference_date is not None:
            reference = _calendar_date(reference_date)
            _depth(reference_depth)
            if reference.day != 1 or ((not tiered or method == MODEL_NAME) and reference >= _calendar_date(payload['forecast_origin'])):
                raise ValueError('Historical reference must be an observed month before the forecast origin.')
        elif reference_depth is not None or payload['status'] == 'forecast':
            raise ValueError('A median forecast needs an explicit historical depth reference.')
        if payload['status'] == 'forecast' and method == MODEL_NAME:
            matching = [row for row in payload['history'] if row['date'] == reference_date and row['training_eligible']]
            if not matching or (matching[0]['gwl_m_bgl'] != reference_depth
                    or matching[0]['contributing_districts_count'] != payload['contributing_districts_count']
                    or matching[0]['district_coverage_pct'] != payload['district_coverage_pct']):
                raise ValueError('Forecast historical reference and coverage differ from the observed history.')
        evaluation = payload['evaluation']
        if evaluation.get('n', 0) and (evaluation_sha is None or evaluation.get('report_sha256') != evaluation_sha):
            raise ValueError('Held-out metrics do not match the released evaluation report.')
    _canonical(manifest)
    return metadata


def _summary(payloads, manifest, release_id):
    rows = []
    for code, payload in sorted(payloads.items(), key=lambda pair: STATES_REGISTRY[pair[0]]['name']):
        forecasts = payload['forecast']
        end = forecasts[-1]['predicted_gwl'] if forecasts else None
        last = payload.get('last_observed_gwl_m_bgl')
        rows.append(dict(state_id=code, state_name=STATES_REGISTRY[code]['name'],
            state_type=STATES_REGISTRY[code]['type'], st_code=STATES_REGISTRY[code]['st_code'],
            status='available' if payload['status']=='forecast' else payload['status'], model_name=MODEL_NAME, model_version=MODEL_VERSION,
            contributing_districts_count=payload['contributing_districts_count'],
            total_districts_in_state=payload['total_districts_in_state'],
            district_coverage_pct=payload['district_coverage_pct'],
            last_observed_gwl_m_bgl=last, historical_reference_date=payload.get('historical_reference_date'),
            forecast_12m_gwl_m_bgl=end, projected_change_12m_m=end-last if end is not None and last is not None else None,
            unavailable_reason=payload.get('message'), evaluation=payload['evaluation']))
    first = next(iter(payloads.values()))
    available = sum(row['status'] == 'available' for row in rows)
    summary = dict(product=SUMMARY_PRODUCT, model_name=MODEL_NAME, model_version=MODEL_VERSION,
        artifact_release=manifest['artifact_release'], promotion_status='experimental',
        generation_id=release_id, release_id=release_id, as_of=first['as_of'],
        forecast_origin=first['forecast_origin'], computed_at=max(row['computed_at'] for row in payloads.values()),
        training_cutoff=manifest['training_cutoff'], horizon_months=12, units='m_bgl',
        total_states=len(rows), available_states_count=available,
        insufficient_data_states_count=len(rows)-available,
        data_insufficient_states_count=sum(row['status']=='insufficient_data' for row in rows),
        model_unavailable_states_count=sum(row['status']=='model_unavailable' for row in rows),
        states=rows, aggregation_method='median_of_observed_district_month_means',
        evaluation_summary=manifest.get('evaluation_summary', {
            'status':'not_evaluated', 'n':0, 'mae_m':None, 'rmse_m':None,
            'description':'No release-specific held-out summary attached.'}),
        limitations=first.get('limitations', []))
    if manifest.get('format_version') == 2:
        methods = ('state_median_xgboost','persistence_fallback','no_observations')
        summary.update(model_name=TIERED_MODEL_NAME,model_version=TIERED_MODEL_VERSION,
            policy_version=manifest['policy_version'],policy_sha256=manifest['policy_sha256'],
            counts_by_forecast_method={method:sum(p['forecast_method']==method for p in payloads.values()) for method in methods})
        for row in rows:
            payload = payloads[row['state_id']]
            row.update(model_name=TIERED_MODEL_NAME,model_version=TIERED_MODEL_VERSION,
                **{field:payload.get(field) for field in ('forecast_method','policy_version',
                    'genuine_observed_months','genuine_observation_count','latest_observation_date',
                    'observation_age_months','reference_age_months','reference_training_eligible',
                    'reference_is_stale','normal_reporting_interval_months','fallback_reason')})
    return summary


def stage_release(payloads, manifest, test_schema=None):
    """Stage a complete immutable release. This never changes the active pointer."""
    payloads, manifest = deepcopy(payloads), deepcopy(manifest)
    metadata = validate_release(payloads, manifest)
    version = manifest['model_version']
    candidate_signature = _hash(payloads)
    candidate_id = str(uuid5(NAMESPACE_URL, 'aquaiq:state_median:' + candidate_signature))
    signature = _hash({'candidate_signature':candidate_signature, 'manifest':manifest})
    release_id = str(uuid5(NAMESPACE_URL, 'aquaiq:state_median_release:' + signature))
    summary = _summary(payloads, manifest, release_id)
    connection = _connect(test_schema, create=True)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('aquaiq:state_median_release',))
                cursor.execute('''INSERT INTO state_median_generations
                    (generation_id,generation_signature,as_of,model_version,status,states_total)
                    VALUES (%s,%s,%s,%s,'experimental',36) ON CONFLICT DO NOTHING''',
                    (candidate_id,candidate_signature,metadata['as_of'],version))
                if cursor.rowcount:
                    execute_values(cursor, '''INSERT INTO state_median_forecast_records
                        (generation_id,state_id,as_of,model_version,status,training_cutoff,model_sha256,payload_json)
                        VALUES %s''', [(candidate_id,code,metadata['as_of'],version,payload['status'],
                            payload.get('training_cutoff'),payload.get('model_sha256'),Json(payload)) for code,payload in sorted(payloads.items())])
                cursor.execute('''INSERT INTO state_median_releases
                    (release_id,generation_id,release_signature,as_of,model_version,manifest_sha256,manifest_json,summary_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                    (release_id,candidate_id,signature,metadata['as_of'],version,_hash(manifest),Json(manifest),Json(summary)))
                _verified_release(cursor, release_id)
        return dict(release_id=release_id,generation_id=release_id,candidate_generation_id=candidate_id,
                    status='staged',as_of=metadata['as_of'],artifact_release=manifest['artifact_release'])
    finally:
        connection.close()


def _verified_release(cursor, release_id):
    cursor.execute('''SELECT generation_id,release_signature,as_of,model_version,manifest_sha256,manifest_json,summary_json
                      FROM state_median_releases WHERE release_id=%s''', (release_id,))
    row = cursor.fetchone()
    if row is None:
        raise LookupError('Median release was not staged.')
    candidate_id, signature, as_of, version, manifest_sha, manifest, summary = row
    cursor.execute('SELECT state_id,payload_json FROM state_median_forecast_records WHERE generation_id=%s', (candidate_id,))
    payloads = dict(cursor.fetchall())
    metadata = validate_release(payloads, manifest)
    candidate_signature = _hash(payloads)
    expected_candidate_id = str(uuid5(NAMESPACE_URL, 'aquaiq:state_median:' + candidate_signature))
    cursor.execute('''SELECT generation_signature,as_of,model_version,status,states_total
                      FROM state_median_generations WHERE generation_id=%s''', (candidate_id,))
    candidate_header = cursor.fetchone()
    expected_signature = _hash({'candidate_signature':candidate_signature, 'manifest':manifest})
    expected_id = str(uuid5(NAMESPACE_URL, 'aquaiq:state_median_release:' + expected_signature))
    if (candidate_header != (candidate_signature,as_of,manifest['model_version'],'experimental',36)
            or str(candidate_id) != expected_candidate_id
            or signature != expected_signature or str(release_id) != expected_id or manifest_sha != _hash(manifest)
            or metadata['as_of'] != as_of.isoformat() or version != manifest['model_version']
            or summary != _summary(payloads, manifest, str(release_id))):
        raise ValueError('Stored median release content or artifact identity is corrupt.')
    return payloads, manifest, summary


def get_active_release(test_schema=None):
    connection = _connect(test_schema)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('state_median_active_release')")
            if cursor.fetchone()[0] is None:
                return None
            cursor.execute('''SELECT a.release_id,r.as_of,r.manifest_json,a.publication_id
                FROM state_median_active_release a JOIN state_median_releases r ON r.release_id=a.release_id
                WHERE a.product=%s''', (PRODUCT_NAME,))
            row = cursor.fetchone()
            return None if row is None else dict(release_id=str(row[0]),generation_id=str(row[0]),
                as_of=row[1].isoformat(),artifact_release=row[2]['artifact_release'],publication_id=row[3])
    finally:
        connection.close()


def _activate(release_id, expected_active, test_schema, reason, action):
    release_id = _uuid(release_id)
    expected_active = _uuid(expected_active) if expected_active is not None else None
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Publication/rollback requires a reason.')
    connection = _connect(test_schema)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('aquaiq:state_median_release',))
                _, manifest, summary = _verified_release(cursor, release_id)
                cursor.execute('SELECT release_id FROM state_median_active_release WHERE product=%s FOR UPDATE', (PRODUCT_NAME,))
                active = cursor.fetchone()
                previous = str(active[0]) if active else None
                if previous == release_id:
                    return dict(status='already_active',release_id=release_id,generation_id=release_id,
                                as_of=summary['as_of'],artifact_release=manifest['artifact_release'])
                if previous != expected_active:
                    raise ValueError('Active median release changed; inspect it and supply the exact expected_active UUID.')
                if action == 'rollback':
                    cursor.execute('SELECT 1 FROM state_median_publications WHERE release_id=%s LIMIT 1', (release_id,))
                    if cursor.fetchone() is None:
                        raise ValueError('Rollback target must have been published previously.')
                cursor.execute('''INSERT INTO state_median_publications
                    (release_id,previous_release_id,action,reason) VALUES (%s,%s,%s,%s) RETURNING publication_id''',
                    (release_id,previous,action,reason.strip()))
                publication_id = cursor.fetchone()[0]
                cursor.execute('''INSERT INTO state_median_active_release(product,release_id,publication_id)
                    VALUES (%s,%s,%s) ON CONFLICT(product) DO UPDATE
                    SET release_id=EXCLUDED.release_id,publication_id=EXCLUDED.publication_id''',
                    (PRODUCT_NAME,release_id,publication_id))
        return dict(status='rolled_back' if action=='rollback' else 'published',
                    release_id=release_id,generation_id=release_id,previous_release_id=previous,
                    publication_id=publication_id,as_of=summary['as_of'],artifact_release=manifest['artifact_release'])
    finally:
        connection.close()


def publish_release(release_id, *, expected_active=None, test_schema=None, reason='Validated median States release'):
    return _activate(release_id,expected_active,test_schema,reason,'publish')


def rollback_release(release_id, *, expected_active, test_schema=None, reason):
    return _activate(release_id,expected_active,test_schema,reason,'rollback')


def _read_release(as_of=None, generation_id=None):
    cutoff = _calendar_date(as_of) if as_of is not None else None
    if cutoff is not None and cutoff > date.today():
        raise ValueError('as_of cannot be in the future.')
    release_id = _uuid(generation_id) if generation_id is not None else None
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('state_median_releases')")
            if cursor.fetchone()[0] is None:
                return None
            if release_id is not None:
                cursor.execute('''SELECT release_id FROM state_median_releases r WHERE release_id=%s
                    AND EXISTS (SELECT 1 FROM state_median_publications p WHERE p.release_id=r.release_id)''', (release_id,))
            elif cutoff is not None:
                cursor.execute('''SELECT r.release_id FROM state_median_releases r
                    JOIN state_median_publications p ON p.release_id=r.release_id
                    WHERE r.as_of=%s ORDER BY p.publication_id DESC LIMIT 1''', (cutoff,))
            else:
                cursor.execute('SELECT release_id FROM state_median_active_release WHERE product=%s', (PRODUCT_NAME,))
            selected = cursor.fetchone()
            if selected is None:
                return None
            selected_id = str(selected[0])
            payloads, manifest, summary = _verified_release(cursor, selected_id)
            if cutoff is not None and summary['as_of'] != cutoff.isoformat():
                return None
            expected_artifact = os.getenv('AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE')
            if cutoff is None and release_id is None and expected_artifact and manifest['artifact_release'] != expected_artifact:
                raise ValueError('Active median publication differs from AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE.')
            return payloads, manifest, deepcopy(summary)
    finally:
        connection.close()


def get_published_summary(as_of=None, generation_id=None):
    release = _read_release(as_of,generation_id)
    return None if release is None else release[2]


def get_published_summary_statistics(as_of=None, generation_id=None):
    """Add display counts from actual verified records without rewriting a release.

    The immutable saved summary remains part of its original release signature.
    These additive fields are a response projection of the same one-read snapshot.
    """
    release = _read_release(as_of,generation_id)
    if release is None:
        return None
    payloads,manifest,stored_summary = release
    summary = deepcopy(stored_summary)
    complete = {code:payload for code,payload in payloads.items()
                if payload['status']=='forecast' and len(payload['forecast'])==12}
    methods = {'state_median_xgboost':0,'persistence_fallback':0,'no_observations':0}
    for code,payload in payloads.items():
        method = payload.get('forecast_method')
        if method is None and code in complete and payload.get('model_name')==MODEL_NAME:
            method = MODEL_NAME
        if code in complete and method in ('state_median_xgboost','persistence_fallback'):
            methods[method] += 1
        elif payload.get('forecast_method')=='no_observations':
            methods['no_observations'] += 1
    for row in summary['states']:
        row['forecast_month_count'] = len(payloads[row['state_id']]['forecast'])
    summary.update(available_states_count=len(complete),
        forecast_month_count=sum(len(payload['forecast']) for payload in payloads.values()),
        unavailable_states_count=len(payloads)-len(complete),counts_by_forecast_method=methods,
        forecast_coverage_basis='validated_persisted_forecast_records')
    return summary


def get_published_manifest(as_of=None, generation_id=None):
    """Release readiness can compare persisted identities with local assets."""
    release = _read_release(as_of,generation_id)
    return None if release is None else deepcopy(release[1])


def get_published_state_forecast(state_id, as_of=None, generation_id=None):
    context = get_published_state_context(state_id,as_of,generation_id)
    return None if context is None else context['forecast']


def get_published_state_context(state_id, as_of=None, generation_id=None):
    """Return one pinned published forecast and its verified source manifest."""
    code = resolve_state_id(state_id)
    release = _read_release(as_of,generation_id)
    if release is None:
        return None
    payloads, manifest, summary = release
    result = deepcopy(payloads[code])
    result.update(generation_id=summary['generation_id'],release_id=summary['release_id'],
                  artifact_release=manifest['artifact_release'],publication_status='published')
    return {'forecast':result,'manifest':deepcopy(manifest)}
