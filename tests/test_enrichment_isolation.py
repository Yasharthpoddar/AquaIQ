"""Explicit candidate snapshots cannot fall through to public forecast tables."""
from pathlib import Path
from unittest.mock import MagicMock
import uuid

import pytest
from psycopg2 import sql

from db.connection import get_connection
from scripts import precompute_forecasts as precompute


def mocked_connection(schema='aquaiq_test_isolation'):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (schema,)
    cursor.fetchall.return_value = [(name, 'r', schema) for name in precompute.FORECAST_OUTPUT_TABLES]
    return connection, cursor


def test_complete_private_tables_force_private_search_path():
    connection, cursor = mocked_connection()
    assert precompute.isolate_candidate_connection(connection) == 'aquaiq_test_isolation'
    assert cursor.execute.call_count == 3
    query = cursor.execute.call_args_list[-1].args[0]
    assert isinstance(query, sql.Composed)
    assert query.seq[1].strings == ('aquaiq_test_isolation',)
    assert 'pg_temp' in query.seq[-1].string
    assert 'public' not in str(query)
    connection.commit.assert_not_called()


@pytest.mark.parametrize('kind', ['missing', 'view', 'foreign', 'wrong_namespace'])
def test_missing_or_nonbase_private_outputs_rejected_before_inference(kind, monkeypatch):
    connection, cursor = mocked_connection()
    rows = cursor.fetchall.return_value
    if kind == 'missing': rows.pop()
    elif kind == 'view': rows[0] = (rows[0][0], 'v', rows[0][2])
    elif kind == 'foreign': rows[0] = (rows[0][0], 'f', rows[0][2])
    else: rows[0] = (rows[0][0], 'r', 'public')
    monkeypatch.setattr(precompute, 'compute_input_identity', lambda *a, **kw: pytest.fail('must fail before inputs/inference'))
    with pytest.raises(ValueError, match='six private base output tables'):
        precompute.run_precomputation(as_of='2026-10-26', connection=connection,
            feature_directory='candidate', checkpoint='candidate', calibration_path='candidate')
    assert cursor.execute.call_count == 2
    connection.commit.assert_not_called()


@pytest.mark.parametrize('schema', ['public', 'aquaiq_test_', None, 'aquaiq_test_bad;public'])
def test_other_schemas_rejected_without_table_queries(schema):
    connection, cursor = mocked_connection(schema)
    with pytest.raises(ValueError, match='restricted'):
        precompute.isolate_candidate_connection(connection)
    assert cursor.execute.call_count == 1


@pytest.fixture
def private_connection():
    connection = get_connection()
    schema = 'aquaiq_test_candidate_isolation_' + uuid.uuid4().hex
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            cursor.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(schema)))
    try:
        yield connection, schema
    finally:
        connection.rollback()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        connection.close()


@pytest.mark.requires_db
def test_empty_test_namespace_with_public_fallback_fails_before_inference(private_connection, monkeypatch):
    connection, schema = private_connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_schema(), to_regclass(\'forecast_generations\')::oid')
        current, resolved = cursor.fetchone()
        assert current == schema
        # This demonstrates the previously dangerous public fallthrough.
        cursor.execute("SELECT to_regclass('public.forecast_generations')::oid")
        assert resolved == cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM public.forecast_generations')
        before = cursor.fetchone()[0]
    monkeypatch.setattr(precompute, 'compute_input_identity', lambda *a, **kw: pytest.fail('must not start inference'))
    with pytest.raises(ValueError, match='six private base output tables'):
        precompute.run_precomputation(as_of='2026-10-26', connection=connection,
            feature_directory='candidate', checkpoint='candidate', calibration_path='candidate')
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM public.forecast_generations')
        assert cursor.fetchone()[0] == before


@pytest.mark.requires_db
@pytest.mark.parametrize('view', [False, True])
def test_initialized_private_relations_are_base_tables_and_resolve_privately(private_connection, view):
    connection, schema = private_connection
    with connection:
        with connection.cursor() as cursor:
            # Isolated structural fixtures; no public source or output mutations.
            for name in precompute.FORECAST_OUTPUT_TABLES:
                statement = 'CREATE VIEW {}.{} AS SELECT 1 AS fixture' if view and name == precompute.FORECAST_OUTPUT_TABLES[0] else 'CREATE TABLE {}.{} (fixture integer)'
                cursor.execute(sql.SQL(statement).format(sql.Identifier(schema), sql.Identifier(name)))
    if view:
        with pytest.raises(ValueError, match='six private base output tables'):
            precompute.isolate_candidate_connection(connection)
        return
    assert precompute.isolate_candidate_connection(connection) == schema
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_schema(), current_schemas(false)')
        current, search = cursor.fetchone()
        assert current == schema and 'public' not in search
        for name in precompute.FORECAST_OUTPUT_TABLES:
            cursor.execute('''SELECT n.nspname FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace
                WHERE c.oid=pg_catalog.to_regclass(%s)''', (name,))
            assert cursor.fetchone()[0] == schema
