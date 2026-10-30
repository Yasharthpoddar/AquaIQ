"""Verification for database role separation and read-only serving safety."""
from pathlib import Path
import os
import pytest
import psycopg2

ROOT = Path(__file__).resolve().parents[1]


def test_provisioning_script_structure_and_safety():
    """Verify scripts/provision_readonly_serving_role.sql satisfies security rules."""
    script_path = ROOT / 'scripts' / 'provision_readonly_serving_role.sql'
    assert script_path.is_file(), 'provision_readonly_serving_role.sql must exist'
    content = script_path.read_text(encoding='utf-8')

    # All 5 state median release tables must be explicitly covered
    required_tables = [
        'state_median_generations',
        'state_median_forecast_records',
        'state_median_releases',
        'state_median_publications',
        'state_median_active_release',
    ]
    for table in required_tables:
        assert table in content, f'Script must reference table {table}'

    # Core legacy read tables must also be covered for API serving
    for table in ['districts', 'raw_data', 'features', 'forecast_generations', 'forecast_records', 'score_publications']:
        assert table in content, f'Script must reference legacy table {table}'

    # Verify least-privilege constraints
    assert 'NOCREATEDB' in content
    assert 'NOCREATEROLE' in content
    assert 'NOSUPERUSER' in content
    assert 'GRANT CONNECT ON DATABASE' in content
    assert 'GRANT USAGE ON SCHEMA' in content
    assert 'GRANT SELECT ON TABLE' in content

    # Verify that write privileges are revoked, never granted to the serving role
    assert 'GRANT INSERT' not in content
    assert 'GRANT UPDATE' not in content
    assert 'GRANT DELETE' not in content
    assert 'GRANT TRUNCATE' not in content

    # Verify no hardcoded credentials exist
    assert 'password123' not in content.lower()
    assert "password 'admin'" not in content.lower()
    assert "password 'password'" not in content.lower()


def test_read_paths_succeed_in_readonly_transaction():
    """Verify serving reads succeed when the database session enforces read-only mode."""
    from db.connection import get_connection
    from models import state_median_release_storage as s

    # Use the existing primary test schema where r1 was published
    test_schema = 'aquaiq_test_state_median_primary_20261029'
    connection = s._connect(test_schema=test_schema)
    connection.set_session(readonly=True)
    try:
        with connection.cursor() as cursor:
            # 1. Active release lookup
            cursor.execute('''SELECT a.release_id, r.as_of, r.manifest_json, a.publication_id
                              FROM state_median_active_release a
                              JOIN state_median_releases r ON r.release_id = a.release_id
                              WHERE a.product = %s''', ('state_median_groundwater_12m_forecast',))
            row = cursor.fetchone()
            assert row is not None, 'Active release row must be readable in read-only mode'
            release_id = str(row[0])

            # 2. Summary lookup
            cursor.execute('SELECT summary_json FROM state_median_releases WHERE release_id = %s', (release_id,))
            summary_row = cursor.fetchone()
            assert summary_row is not None, 'Summary must be readable in read-only mode'
            assert summary_row[0]['total_states'] == 36

            # 3. Pinned state detail lookup
            cursor.execute('''SELECT payload_json FROM state_median_forecast_records
                              WHERE generation_id = (SELECT generation_id FROM state_median_releases WHERE release_id = %s)
                              AND state_id = %s''', (release_id, 'AP'))
            state_row = cursor.fetchone()
            assert state_row is not None, 'State record must be readable in read-only mode'
            assert state_row[0]['horizon_months'] == 12
    finally:
        connection.close()


def test_write_paths_fail_in_readonly_mode():
    """Verify write operations fail when read-only transaction mode is active."""
    test_schema = 'aquaiq_test_state_median_primary_20261029'
    from models import state_median_release_storage as s
    connection = s._connect(test_schema=test_schema)
    connection.set_session(readonly=True)
    try:
        with connection.cursor() as cursor:
            # Attempting an INSERT must fail with ReadOnlySqlTransaction
            with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
                cursor.execute('''INSERT INTO state_median_publications (release_id, previous_release_id, action, reason)
                                  VALUES ('eaabeba7-a554-59a6-9110-726221e63cb2', NULL, 'publish', 'should_fail')''')
    finally:
        connection.close()
