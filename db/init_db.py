"""Initialize base tables and apply additive, idempotent schema migrations."""
from pathlib import Path
import argparse
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.connection import get_connection

def init_db(test_schema=None):
    if test_schema is not None and (not re.fullmatch(r'aquaiq_test_[a-z0-9_]+', test_schema)
                                    or len(test_schema) > 63):
        raise ValueError('Test schema must be aquaiq_test_* with lowercase identifiers, at most 63 characters.')
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                if test_schema is not None:
                    from psycopg2 import sql
                    cursor.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(test_schema)))
                    # Never resolve a missing source/output table into public.
                    # Explicit pg_temp last prevents temporary table shadows.
                    cursor.execute(sql.SQL('SET LOCAL search_path TO {}, pg_temp').format(sql.Identifier(test_schema)))
                cursor.execute((ROOT / 'db/schema.sql').read_text(encoding='utf-8'))
                cursor.execute((ROOT / 'db/migrations/003_pipeline_provenance.sql').read_text(encoding='utf-8'))
                cursor.execute((ROOT / 'db/migrations/004_xgboost_forecast_storage.sql').read_text(encoding='utf-8'))
                cursor.execute((ROOT / 'db/migrations/005_scoring_storage.sql').read_text(encoding='utf-8'))
        print('Database schema verified; pipeline provenance and forecast storage migrations applied.'
              + (f' Isolated namespace: {test_schema}.' if test_schema is not None else ''))
    finally:
        connection.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-schema', help='Initialize only a private aquaiq_test_* namespace; preserve public tables')
    args = parser.parse_args()
    init_db(args.test_schema)
