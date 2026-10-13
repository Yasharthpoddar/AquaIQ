"""Shared PostgreSQL access with bounded connection time and safe reads."""
import os
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]

def get_connection():
    import psycopg2
    load_dotenv(ROOT / '.env')
    return psycopg2.connect(host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')), dbname=os.getenv('POSTGRES_DB', 'aquaiq'),
        user=os.getenv('POSTGRES_USER', 'aquaiq_user'), password=os.getenv('POSTGRES_PASSWORD', ''),
        connect_timeout=10, options='-c statement_timeout=120000')

def read_frame(query, connection, params=None):
    """Read a parameterized DBAPI query without pandas' unsupported adapter."""
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return pd.DataFrame(cursor.fetchall(), columns=[column[0] for column in cursor.description])

def finite_json(value):
    """Convert nested numpy/pandas scalars and non-finite numbers to strict JSON."""
    import math
    from datetime import date, datetime
    import numpy as np
    if isinstance(value, dict):
        return {str(key): finite_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(item) for item in value]
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    return None if isinstance(value, float) and not math.isfinite(value) else value
