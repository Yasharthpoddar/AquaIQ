"""
Shared pytest configuration.

Tests marked ``requires_db`` need the PostgreSQL instance created by setup.sh.
On a machine without it (for example a fresh clone) they are reported as
skipped instead of failing, so ``pytest`` gives a clean, honest result.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def _database_reachable() -> bool:
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "aquaiq"),
            user=os.getenv("POSTGRES_USER", "aquaiq_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    db_tests = [item for item in items if "requires_db" in item.keywords]
    if not db_tests or _database_reachable():
        return
    skip = pytest.mark.skip(reason="PostgreSQL not reachable - run setup.sh and start the database")
    for item in db_tests:
        item.add_marker(skip)
