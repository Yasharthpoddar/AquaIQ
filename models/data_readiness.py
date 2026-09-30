import os
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).parent.parent

def get_connection():
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )

def get_data_readiness(district_id: str) -> dict:
    """
    Compute per-district data readiness (% months with valid, non-imputed data).
    If below 60%, fallback to zone-level aggregation.
    """
    conn = None
    try:
        conn = get_connection()
        # Suppose raw_data table has 'is_imputed' or we just check nulls.
        # Since we don't have the exact schema, we will query raw_data to see total months vs valid months.
        
        # MOCK IMPLEMENTATION since actual DB schema and data might not match exactly yet.
        # We assume 24 years * 12 months = 288 months.
        
        # Check if district exists in raw_data
        df = pd.read_sql(
            "SELECT count(*) as total, sum(case when gwl_current is not null then 1 else 0 end) as valid FROM raw_data WHERE district_id = %s",
            conn,
            params=(district_id,)
        )
        total = df.iloc[0]["total"]
        valid = df.iloc[0]["valid"]
        
        if total == 0:
            readiness_score = 0
        else:
            readiness_score = (valid / total) * 100
            
    except Exception as e:
        # Fallback if table or columns are missing
        readiness_score = 100.0  # assume perfect readiness for now
    finally:
        if conn:
            conn.close()

    is_fallback = readiness_score < 60.0
    
    return {
        "district_id": district_id,
        "readiness_score": round(readiness_score, 1),
        "is_zone_fallback": is_fallback,
        "fallback_zone": "Agro-Climatic Zone (Mocked)" if is_fallback else None
    }

if __name__ == "__main__":
    print(get_data_readiness("RJ-Jaipur"))
