"""Initialize base tables and apply additive, idempotent schema migrations."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db.connection import get_connection

def init_db():
    connection = get_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute((ROOT / 'db/schema.sql').read_text(encoding='utf-8'))
                cursor.execute((ROOT / 'db/migrations/003_pipeline_provenance.sql').read_text(encoding='utf-8'))
        print('Database schema verified; pipeline provenance migration applied.')
    finally:
        connection.close()

if __name__ == '__main__':
    init_db()
