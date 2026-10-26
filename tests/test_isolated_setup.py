"""Clean setup can initialize source/output tables without public fallthrough."""
import uuid
from unittest.mock import MagicMock

import pytest
from psycopg2 import sql

from db import init_db as initializer
from db.connection import get_connection


@pytest.mark.parametrize('name', ['public', '', 'aquaiq_test_', 'aquaiq_test_bad;public', 'aquaiq_test_'+'a'*60])
def test_invalid_setup_schema_rejected_before_connecting(name, monkeypatch):
    monkeypatch.setattr(initializer,'get_connection',lambda: pytest.fail('must validate before database access'))
    with pytest.raises(ValueError,match='Test schema'):
        initializer.init_db(name)


def test_explicit_setup_removes_public_fallback(monkeypatch):
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(initializer,'get_connection',lambda:connection)
    initializer.init_db('aquaiq_test_setup')
    command=cursor.execute.call_args_list[1].args[0]
    assert isinstance(command,sql.Composed)
    assert command.seq[1].strings==('aquaiq_test_setup',)
    assert 'pg_temp' in command.seq[-1].string
    connection.close.assert_called_once()


@pytest.mark.requires_db
def test_clean_migrations_are_idempotent_and_all_relations_private():
    schema='aquaiq_test_setup_'+uuid.uuid4().hex
    connection=get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT md5(string_agg(version,',' ORDER BY version)) FROM public.schema_migrations")
            before=cursor.fetchone()[0]
        initializer.init_db(schema);initializer.init_db(schema)
        with connection.cursor() as cursor:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s",(schema,))
            tables={row[0] for row in cursor.fetchall()}
            assert {'districts','raw_data','features','scoring_runs','forecast_generations','district_forecast_records'} <= tables
            for name in ('districts','raw_data','features'):
                cursor.execute(sql.SQL('SELECT COUNT(*) FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(name)))
                assert cursor.fetchone()[0]==0
            cursor.execute("SELECT n.nspname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=pg_get_serial_sequence(%s,'id')::regclass",(schema+'.raw_data',))
            assert cursor.fetchone()[0]==schema
            cursor.execute("SELECT md5(string_agg(version,',' ORDER BY version)) FROM public.schema_migrations")
            assert cursor.fetchone()[0]==before
    finally:
        connection.rollback()
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
        connection.close()
