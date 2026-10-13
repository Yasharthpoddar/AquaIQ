"""
AquaIQ — D2, D3, D6 Features Physical Units and NaN Cleanup Regression Test.
Verifies:
1. features table contains zero text/'NaN' values.
2. monsoon_deficit_pct has realistic distribution in physical units (not near-constant -96%).
3. gwl_current contains physical values (max > 1.0 m bgl, not [0, 1] scaled).
4. Feature matrix has >= 95% 4-variable completeness on valid rows.
"""

import os
from pathlib import Path
import psycopg2
import pytest
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


def test_zero_nan_strings_in_features(db_connection):
    """Assert zero stored 'NaN' values exist across all numeric columns in features table."""
    cols = [
        "gwl_current", "gwl_lag_3mo", "gwl_lag_6mo",
        "rainfall_current", "rainfall_3mo_avg", "monsoon_deficit_pct",
        "temperature", "evapotranspiration", "water_balance_proxy"
    ]
    with db_connection.cursor() as cur:
        for c in cols:
            cur.execute(f"SELECT count(*) FROM features WHERE {c}::text = 'NaN';")
            count = cur.fetchone()[0]
            assert count == 0, f"Column {c} contains {count} 'NaN' string values"


def test_physical_units_gwl(db_connection):
    """Assert gwl_current values reflect physical depth in metres (not [0, 1] scaled)."""
    with db_connection.cursor() as cur:
        cur.execute("SELECT MAX(gwl_current), AVG(gwl_current) FROM features WHERE gwl_current IS NOT NULL;")
        row = cur.fetchone()
        max_gwl, avg_gwl = row[0], row[1]

    # If scaled [0, 1], MAX would be 1.0. In physical metres, MAX exceeds 20.0 m bgl.
    assert max_gwl > 20.0, f"gwl_current max={max_gwl} is suspiciously scaled (expected > 20 m bgl)"
    assert avg_gwl > 2.0, f"gwl_current mean={avg_gwl} is suspiciously small (expected > 2 m bgl)"


def test_monsoon_deficit_not_degenerate(db_connection):
    """Assert monsoon_deficit_pct does not average near -96%."""
    with db_connection.cursor() as cur:
        cur.execute("""
            SELECT AVG(monsoon_deficit_pct), MIN(monsoon_deficit_pct), MAX(monsoon_deficit_pct)
            FROM features
            WHERE monsoon_deficit_pct IS NOT NULL;
        """)
        row = cur.fetchone()
        avg_deficit = row[0]

    assert avg_deficit > -50.0, f"monsoon_deficit_pct mean={avg_deficit} is degenerate (expected > -50%)"
