"""Select isolated score outputs while retaining read-only source-table access."""
import os
from pathlib import Path
import re
from psycopg2 import sql
from db.connection import get_connection as source_connection

TABLES = ('scoring_runs','crisis_scores','predictions')


def validate_test_schema(schema):
    if not re.fullmatch(r'aquaiq_test_[a-z0-9_]+',schema):
        raise ValueError('Scoring test schema must start aquaiq_test_ and use lowercase identifiers.')
    return schema


def _select_schema(connection,schema):
    validate_test_schema(schema)
    with connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_type='BASE TABLE' AND table_name=ANY(%s)",(schema,list(TABLES)))
        if cur.fetchone()[0] != len(TABLES):
            raise ValueError('Scoring test schema is not initialized; refusing to fall back to public output tables.')
        cur.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(schema)))
    connection.commit()
    return connection


def get_scoring_connection():
    connection=source_connection()
    try:
        schema=os.getenv('AQUAIQ_SCORING_SCHEMA')
        return _select_schema(connection,schema) if schema else connection
    except Exception as error:
        connection.close()
        raise RuntimeError('Configured scoring output storage is unavailable.') from error


def initialize_test_schema(schema):
    """Create only output tables in the requested namespace, with local sequences."""
    validate_test_schema(schema)
    connection=source_connection()
    try:
        with connection:
            with connection.cursor() as cur:
                cur.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema)))
                cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                cur.execute((Path(__file__).parent/'migrations/005_scoring_storage.sql').read_text(encoding='utf-8'))
        return _select_schema(connection,schema)
    except Exception:
        connection.close()
        raise
