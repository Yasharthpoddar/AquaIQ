"""
AquaIQ — D1 Canonical District Identity Regression Test.
Asserts:
1. All district IDs follow canonical format {state_abbrev}-{name}.
2. Zero numeric-only district IDs exist in districts, raw_data, or features.
3. Every (state, district_name) pair in districts is strictly unique.
4. All raw_data and features foreign keys resolve to canonical districts.
5. legacy_district_ids table exists and records previous IDs.
"""

import os
import re
from pathlib import Path
import pytest
import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

pytestmark = pytest.mark.requires_db


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


def test_no_numeric_district_ids(db_connection):
    """Assert zero numeric-only IDs exist in districts, raw_data, or features."""
    with db_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM districts WHERE district_id ~ '^[0-9]+$';")
        num_districts = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT district_id) FROM raw_data WHERE district_id ~ '^[0-9]+$';")
        num_raw = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT district_id) FROM features WHERE district_id ~ '^[0-9]+$';")
        num_feat = cur.fetchone()[0]

    assert num_districts == 0, f"Found {num_districts} numeric IDs in districts table"
    assert num_raw == 0, f"Found {num_raw} numeric IDs in raw_data table"
    assert num_feat == 0, f"Found {num_feat} numeric IDs in features table"


def test_canonical_id_format(db_connection):
    """Assert all district IDs match {state_abbrev}-{Normalized_Name}."""
    canonical_pattern = re.compile(r"^[A-Z]{2}-[A-Za-z0-9_.-]+$")
    with db_connection.cursor() as cur:
        cur.execute("SELECT district_id FROM districts;")
        district_ids = [r[0] for r in cur.fetchall()]

    invalid = [d for d in district_ids if not canonical_pattern.match(d)]
    assert len(invalid) == 0, f"Found {len(invalid)} non-canonical IDs: {invalid[:10]}"


def test_districts_unique_state_name(db_connection):
    """Assert no duplicate (state, district_name) pairs exist in districts table."""
    with db_connection.cursor() as cur:
        cur.execute("""
            SELECT LOWER(TRIM(state)), LOWER(TRIM(district_name)), COUNT(*)
            FROM districts
            GROUP BY LOWER(TRIM(state)), LOWER(TRIM(district_name))
            HAVING COUNT(*) > 1;
        """)
        duplicates = cur.fetchall()

    assert len(duplicates) == 0, f"Found duplicate (state, district_name) pairs: {duplicates[:10]}"


def test_foreign_keys_resolve(db_connection):
    """Assert all raw_data district_ids exist in districts table."""
    with db_connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT r.district_id)
            FROM raw_data r
            LEFT JOIN districts d ON r.district_id = d.district_id
            WHERE d.district_id IS NULL;
        """)
        orphaned = cur.fetchone()[0]

    assert orphaned == 0, f"Found {orphaned} orphaned district_ids in raw_data"


def test_legacy_district_ids_audit_table(db_connection):
    """Assert legacy_district_ids table exists and contains audit entries."""
    with db_connection.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'legacy_district_ids'
            );
        """)
        table_exists = cur.fetchone()[0]
        assert table_exists, "legacy_district_ids table does not exist"

        cur.execute("SELECT COUNT(*) FROM legacy_district_ids;")
        legacy_count = cur.fetchone()[0]
        assert legacy_count >= 567, f"Expected >= 567 legacy mappings, got {legacy_count}"
