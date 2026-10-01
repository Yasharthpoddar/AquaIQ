"""
AquaIQ — Regression test for district gaps.
Ensures that the districts table contains all ~640+ districts from the GeoJSON,
not just the ~567 districts that have recent CGWB borewell coverage.
"""

import pytest
import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


@pytest.fixture(scope="module")
def db_connection():
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
    yield conn
    conn.close()


def test_districts_table_has_all_districts(db_connection):
    """
    Test that the districts table contains more than the base ~567 CGWB districts.
    With the GeoJSON fallback fix, it should have >640 districts.
    """
    with db_connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM districts")
        count = cur.fetchone()[0]
        
    assert count >= 640, f"Expected >= 640 districts, but found {count}. Did the GeoJSON fallback run?"
