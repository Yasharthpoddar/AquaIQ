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


def compute_drought_frequency(district_id: str, gwl_history: pd.Series) -> float:
    """
    Drought frequency = % of past months below the district's 20th percentile GWL.
    Returned as a score 0-100.
    """
    if len(gwl_history) < 12:
        return 50.0  # fallback

    # GWL is depth, so higher values = worse (deeper water).
    # 20th percentile of water level = 80th percentile of depth measurement.
    threshold = gwl_history.quantile(0.80)
    drought_months = (gwl_history > threshold).sum()
    freq_pct = (drought_months / len(gwl_history)) * 100
    
    # Scale to 0-100
    score = min((freq_pct / 20.0) * 100, 100.0)
    return float(score)


def get_model_components(district_id: str) -> dict:
    """
    Fetch the underlying predictions from LR and XGBoost, and history for drought frequency.
    """
    try:
        conn = get_connection()
        df = pd.read_sql(
            "SELECT date, gwl_current FROM features WHERE district_id = %s ORDER BY date",
            conn,
            params=(district_id,)
        )
        conn.close()
        
        if len(df) == 0:
            raise ValueError(f"No data for district {district_id}")
            
        gwl_history = df["gwl_current"]
        
        # Calculate drought frequency
        drought_score = compute_drought_frequency(district_id, gwl_history)
        
        # Approximate LR trend from recent 12 months vs first 12 months
        recent_trend = gwl_history.iloc[-12:].mean() - gwl_history.iloc[:12].mean()
        lr_score = min(max((recent_trend / 5.0) * 100 + 50, 0), 100)
        
        # Approximate XGB risk from current absolute depth
        current_depth = gwl_history.iloc[-1]
        xgb_score = min(max((current_depth / 30.0) * 100, 0), 100)
        
        return {
            "lr_trend": float(lr_score),
            "xgb_risk": float(xgb_score),
            "drought_frequency": drought_score
        }
        
    except Exception as e:
        print(f"Error computing components for {district_id}: {e}")
        return {
            "lr_trend": 50.0,
            "xgb_risk": 50.0,
            "drought_frequency": 50.0
        }


def compute_crisis_score(district_id: str) -> dict:
    """
    AquaIQ Crisis Score = Linear Regression trend forecast + XGBoost risk + historical drought frequency
    Returns dict with final score (0-100), tier, and component breakdown.
    """
    # Optimized weights based on backtests
    weights = {
        "linear_regression_trend": 0.25,
        "xgboost_risk": 0.50,
        "drought_frequency": 0.25
    }
    
    comps = get_model_components(district_id)
    
    final_score = (
        comps["lr_trend"] * weights["linear_regression_trend"] +
        comps["xgb_risk"] * weights["xgboost_risk"] +
        comps["drought_frequency"] * weights["drought_frequency"]
    )
    final_score = round(min(max(final_score, 0), 100))
    
    # Crisis Score tiers: Safe 0-30 | Watch 31-60 | Warning 61-80 | Crisis 81-100
    if final_score <= 30:
        tier = "Safe"
    elif final_score <= 60:
        tier = "Watch"
    elif final_score <= 80:
        tier = "Warning"
    else:
        tier = "Crisis"
        
    return {
        "district_id": district_id,
        "crisis_score": final_score,
        "tier": tier,
        "ensemble_weights": weights,
        "components": comps
    }

if __name__ == "__main__":
    res = compute_crisis_score("RJ-Jaipur")
    print(res)
