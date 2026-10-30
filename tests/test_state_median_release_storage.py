"""Synthetic release fixtures exercise publication without touching live outputs."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from psycopg2 import sql
import pytest

from db.connection import get_connection
from models import state_median_release_storage as releases
from tests.test_state_median_storage import snapshots, add_forecast


def release_fixture(artifact='test-release-v1', as_of='2025-01-31'):
    payloads = add_forecast(snapshots(as_of))
    for payload in payloads.values():
        payload.update(training_cutoff='2024-12-01',feature_generation='synthetic-test-source',
                       source_data_sha256='a'*64,registry_sha256='c'*64,features=['lag_1','horizon'],
                       artifact_release=artifact,model_card_sha256='d'*64)
    payloads['TN'].update(last_observed_gwl_m_bgl=3.,historical_reference_date='2024-12-01',
                          contributing_districts_count=6,district_coverage_pct=60.)
    manifest = dict(artifact_release=artifact,model_card_sha256='d'*64,model_version=releases.MODEL_VERSION,
        training_cutoff='2024-12-01',feature_generation_id='synthetic-test-source',data_sha256='a'*64,
        registry_sha256='c'*64,features=['lag_1','horizon'],package_versions={'python':'synthetic-fixture'},
        evaluation_report_sha256=None,models={'TN':'b'*64})
    return payloads,manifest


def test_release_requires_exact_artifact_and_source_identity():
    payloads, manifest = release_fixture()
    assert releases.validate_release(payloads,manifest)['states_total'] == 36
    manifest['models']['TN'] = 'f'*64
    with pytest.raises(ValueError,match='identities'):
        releases.validate_release(payloads,manifest)


@pytest.mark.parametrize('field', ['feature_generation_id','data_sha256','registry_sha256','training_cutoff','features',
                                 'artifact_release','model_card_sha256'])
def test_mismatched_manifest_cannot_be_staged(field):
    payloads, manifest = release_fixture()
    payloads['TN'][{'feature_generation_id':'feature_generation','data_sha256':'source_data_sha256'}.get(field,field)] = None
    with pytest.raises(ValueError):
        releases.validate_release(payloads,manifest)


def test_release_evaluation_requires_matching_report_identity():
    payloads,manifest = release_fixture()
    payloads['TN']['evaluation'] = dict(status='retrospective_experimental',n=1,mae_m=1.,rmse_m=1.,
        period_start='2024-01-01',period_end='2024-01-01',report_sha256='e'*64)
    with pytest.raises(ValueError,match='evaluation report'):
        releases.validate_release(payloads,manifest)
    manifest['evaluation_report_sha256'] = 'e'*64
    releases.validate_release(payloads,manifest)


def test_invalid_namespace_and_uuid_fail_before_connecting(monkeypatch):
    monkeypatch.setattr(releases.dbc,'get_connection',lambda:pytest.fail('must not connect'))
    with pytest.raises(ValueError,match='test schema'):
        releases._connect('public')
    with pytest.raises(ValueError,match='UUID'):
        releases.get_published_summary(generation_id='not-a-uuid')


@pytest.fixture
def private_release_store(monkeypatch):
    connection = get_connection()
    schema = 'aquaiq_test_median_release_' + uuid4().hex[:12]
    monkeypatch.setenv('AQUAIQ_STATE_MEDIAN_SCHEMA',schema)
    # The independent release store must not consult the district namespace.
    monkeypatch.setenv('AQUAIQ_FORECAST_SCHEMA','aquaiq_test_nonexistent_legacy_namespace')
    monkeypatch.delenv('AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE',raising=False)
    with connection.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM public.forecast_generations')
        original_count = cursor.fetchone()[0]
    yield schema,connection
    with connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM public.forecast_generations')
            assert cursor.fetchone()[0] == original_count
            cursor.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
    connection.close()


@pytest.mark.requires_db
def test_stage_publish_pin_and_rollback_are_independent_atomic_and_immutable(private_release_store):
    schema,connection = private_release_store
    payloads,manifest = release_fixture()
    first = releases.stage_release(payloads,manifest,test_schema=schema)
    assert releases.stage_release(payloads,manifest,test_schema=schema) == first
    assert releases.get_published_summary() is None
    assert releases.get_published_state_forecast('TN',generation_id=first['release_id']) is None
    assert releases.get_active_release() is None
    published = releases.publish_release(first['release_id'],test_schema=schema)
    assert published['status'] == 'published'
    assert releases.publish_release(first['release_id'],test_schema=schema)['status'] == 'already_active'
    summary = releases.get_published_summary()
    assert summary['generation_id'] == first['release_id'] and len(summary['states']) == 36
    assert summary['available_states_count'] == 1
    assert next(row for row in summary['states'] if row['state_id']=='TN')['status'] == 'available'
    assert next(row for row in summary['states'] if row['state_id']=='TN')['forecast_12m_gwl_m_bgl'] is not None
    assert 'current_gwl_m_bgl' not in summary['states'][0]
    if shutil.which('node'):
        contract = Path(__file__).resolve().parents[1]/'dashboard/src/components/stateMedianForecastContract.js'
        script = (f"import {{ validateMedianStatesSummary }} from {json.dumps(contract.as_uri())};"
                  "let body='';for await(const chunk of process.stdin)body+=chunk;"
                  "validateMedianStatesSummary(JSON.parse(body));")
        node_result = subprocess.run([shutil.which('node'),'--input-type=module','-e',script],
                                     input=json.dumps(summary),text=True,capture_output=True)
        assert node_result.returncode == 0,node_result.stderr
    detail = releases.get_published_state_forecast('Tamil Nadu')
    assert detail['artifact_release'] == 'test-release-v1'
    assert detail['forecast'] == payloads['TN']['forecast']
    assert releases.get_published_summary(as_of='2025-01-30') is None
    detail['forecast'][0]['predicted_gwl'] = -1
    assert releases.get_published_state_forecast('TN')['forecast'][0]['predicted_gwl'] >= 0

    second_payloads,second_manifest = release_fixture('test-release-v2','2025-02-28')
    second = releases.stage_release(second_payloads,second_manifest,test_schema=schema)
    with pytest.raises(ValueError,match='expected_active'):
        releases.publish_release(second['release_id'],test_schema=schema)
    assert releases.get_active_release()['release_id'] == first['release_id']
    releases.publish_release(second['release_id'],expected_active=first['release_id'],test_schema=schema)
    assert releases.get_published_summary()['as_of'] == '2025-02-28'
    assert releases.get_published_state_forecast('TN',generation_id=first['release_id'])['as_of'] == '2025-01-31'
    assert releases.get_published_summary(as_of='2025-01-31',generation_id=second['release_id']) is None
    releases.rollback_release(first['release_id'],expected_active=second['release_id'],test_schema=schema,reason='Synthetic rollback test')
    assert releases.get_active_release()['release_id'] == first['release_id']
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL('SELECT action FROM {}.state_median_publications ORDER BY publication_id').format(sql.Identifier(schema)))
        assert [row[0] for row in cursor.fetchall()] == ['publish','publish','rollback']


@pytest.mark.requires_db
def test_corrupt_generation_never_replaces_current_publication(private_release_store):
    schema,connection = private_release_store
    first = releases.stage_release(*release_fixture(),test_schema=schema)
    releases.publish_release(first['release_id'],test_schema=schema)
    second = releases.stage_release(*release_fixture('test-release-v2','2025-02-28'),test_schema=schema)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("UPDATE {}.state_median_forecast_records SET payload_json=jsonb_set(payload_json,'{{model_sha256}}','\"wrong\"') WHERE generation_id=%s AND state_id='TN'").format(sql.Identifier(schema)),
                           (second['candidate_generation_id'],))
    with pytest.raises(ValueError):
        releases.publish_release(second['release_id'],expected_active=first['release_id'],test_schema=schema)
    assert releases.get_active_release()['release_id'] == first['release_id']
    assert releases.get_published_state_forecast('TN')['status'] == 'forecast'


@pytest.mark.requires_db
def test_database_failure_inside_publication_rolls_back_pointer_and_event(private_release_store):
    schema,connection = private_release_store
    first = releases.stage_release(*release_fixture(),test_schema=schema)
    releases.publish_release(first['release_id'],test_schema=schema)
    second = releases.stage_release(*release_fixture('test-release-v2','2025-02-28'),test_schema=schema)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('''CREATE FUNCTION {}.reject_pointer_update() RETURNS trigger LANGUAGE plpgsql AS
                $$ BEGIN RAISE EXCEPTION 'Synthetic publication failure'; END $$''').format(sql.Identifier(schema)))
            cursor.execute(sql.SQL('''CREATE TRIGGER reject_pointer_update BEFORE UPDATE ON {}.state_median_active_release
                FOR EACH ROW EXECUTE FUNCTION {}.reject_pointer_update()''').format(sql.Identifier(schema),sql.Identifier(schema)))
    with pytest.raises(Exception,match='Synthetic publication failure'):
        releases.publish_release(second['release_id'],expected_active=first['release_id'],test_schema=schema)
    assert releases.get_active_release()['release_id'] == first['release_id']
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL('SELECT count(*) FROM {}.state_median_publications').format(sql.Identifier(schema)))
        assert cursor.fetchone()[0] == 1


@pytest.mark.requires_db
def test_expected_default_artifact_identity_and_explicit_older_pins(private_release_store,monkeypatch):
    schema,_ = private_release_store
    first = releases.stage_release(*release_fixture(),test_schema=schema)
    releases.publish_release(first['release_id'],test_schema=schema)
    monkeypatch.setenv('AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE','different-release')
    with pytest.raises(ValueError,match='EXPECTED_RELEASE'):
        releases.get_published_summary()
    assert releases.get_published_summary(generation_id=first['release_id'])['artifact_release'] == 'test-release-v1'
    assert releases.get_published_state_forecast('TN',as_of='2025-01-31')['artifact_release'] == 'test-release-v1'


@pytest.mark.requires_db
def test_rollback_rejects_never_published_target(private_release_store):
    schema,_ = private_release_store
    first = releases.stage_release(*release_fixture(),test_schema=schema)
    releases.publish_release(first['release_id'],test_schema=schema)
    never = releases.stage_release(*release_fixture('test-release-v2','2025-02-28'),test_schema=schema)
    with pytest.raises(ValueError,match='previously'):
        releases.rollback_release(never['release_id'],expected_active=first['release_id'],test_schema=schema,reason='Invalid target test')
    assert releases.get_active_release()['release_id'] == first['release_id']


@pytest.mark.requires_db
def test_explicit_release_migration_is_idempotent_and_private(private_release_store):
    schema,connection = private_release_store
    first = releases.migrate_release_storage(test_schema=schema)
    assert releases.migrate_release_storage(test_schema=schema) == first
    assert first['schema'] == schema
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL('SELECT version FROM {}.schema_migrations ORDER BY version').format(sql.Identifier(schema)))
        assert [row[0] for row in cursor.fetchall()] == ['006_state_median_forecasts','007_state_median_publication']
