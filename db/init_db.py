"""
AquaIQ database initializer — PostgreSQL.

Run once during setup (setup.sh calls this automatically):
    python3 db/init_db.py

Reads PostgreSQL credentials from .env (via python-dotenv).
Creates all 6 tables from schema.sql if they don't already exist.
Safe to re-run — every CREATE TABLE uses IF NOT EXISTS.

Prerequisites:
    1. PostgreSQL 14+ installed and running
    2. Database 'aquaiq' created:
           psql -U postgres -c "CREATE DATABASE aquaiq;"
           psql -U postgres -c "CREATE USER aquaiq_user WITH PASSWORD 'your_password_here';"
           psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE aquaiq TO aquaiq_user;"
    3. .env file present (copy from .env.example and fill in your values)
"""
import os
import psycopg2
import yaml
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent

# Load credentials from .env
load_dotenv(ROOT / ".env")


def get_connection():
    """Return a psycopg2 connection using credentials from .env."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def init_db():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('districts', 'raw_data', 'features', 'predictions', 'shap_values', 'crisis_scores');
            """)
            count = cur.fetchone()[0]
            
            if count >= 6:
                print("Database already initialized. Skipping schema creation.")
            else:
                schema_path = Path(__file__).parent / "schema.sql"
                with open(schema_path) as f:
                    schema_sql = f.read()
                cur.execute(schema_sql)
                conn.commit()
                print("AquaIQ PostgreSQL database initialized successfully.")
                print("Tables: districts, raw_data, features, predictions, shap_values, crisis_scores")
        
        print(f"  Host : {os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}")
        print(f"  DB   : {os.getenv('POSTGRES_DB')}")
        print(f"  User : {os.getenv('POSTGRES_USER')}")
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Database verification/initialization failed: {e}") from e
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
