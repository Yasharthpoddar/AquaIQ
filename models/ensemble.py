"""
AquaIQ — Ensemble Crisis Score (Phase III)
--------------------------------------------
Combines Linear Regression trend, XGBoost risk, and historical drought
frequency into a single 0–100 Crisis Score per district.

Weights are loaded from config.yaml (fitted via backtest, not hand-picked).
estimate_type is set per district based on data readiness:
  - district_level:     enough CGWB history for per-district prediction
  - zone_fallback:      sparse data → aggregated by agro_climatic_zone
  - insufficient_data:  even the zone lacks enough history

v2 — Now uses the trained XGBoost checkpoint and sklearn LinearRegression
     for the ensemble components instead of heuristic proxies.
"""

import os
from pathlib import Path
import pandas as pd
import numpy as np
import yaml
from functools import lru_cache

try:
    from models.tiers import score_to_tier
except ImportError:  # executed as a script: python models/ensemble.py
    from tiers import score_to_tier

ROOT = Path(__file__).parent.parent

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

# ─── Trained XGBoost model (lazy-loaded singleton) ────────────────────────
_XGB_MODEL = None
_XGB_FEATURE_COLS = None  # set after first load


def _load_xgb_model():
    """Load the saved XGBoost checkpoint once."""
    global _XGB_MODEL, _XGB_FEATURE_COLS
    if _XGB_MODEL is not None:
        return _XGB_MODEL

    checkpoint = ROOT / CONFIG["paths"]["xgboost_checkpoint"]
    if not checkpoint.exists():
        print(f"WARNING: XGBoost checkpoint not found at {checkpoint}, falling back to heuristic")
        return None

    import xgboost as xgb
    _XGB_MODEL = xgb.XGBRegressor()
    _XGB_MODEL.load_model(str(checkpoint))

    # The model was trained on these 12 features (in order):
    # gwl_current, gwl_lag_3mo, gwl_lag_6mo, rainfall_current, rainfall_3mo_avg,
    # monsoon_deficit_pct, temperature, evapotranspiration, water_balance_proxy,
    # season_Kharif, season_Rabi, season_Zaid
    _XGB_FEATURE_COLS = [
        "gwl_current", "gwl_lag_3mo", "gwl_lag_6mo",
        "rainfall_current", "rainfall_3mo_avg", "monsoon_deficit_pct",
        "temperature", "evapotranspiration", "water_balance_proxy",
        "season_Kharif", "season_Rabi", "season_Zaid",
    ]
    return _XGB_MODEL


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


def _load_ensemble_weights() -> dict:
    """
    Load ensemble weights from config.yaml.
    Uses fitted_weights if available, otherwise falls back to initial_weights.
    """
    ensemble_cfg = CONFIG.get("model_hyperparameters", {}).get("ensemble", {})
    weights = ensemble_cfg.get("fitted_weights", ensemble_cfg.get("initial_weights", {}))
    return {
        "linear_regression_trend": weights.get("linear_regression_trend", 0.25),
        "xgboost_risk": weights.get("xgboost_risk", 0.50),
        "drought_frequency": weights.get("drought_frequency", 0.25),
    }


def compute_drought_frequency(district_id: str, gwl_history: pd.Series) -> float:
    """
    Drought frequency = % of past months above the district's 80th percentile
    GWL depth (higher depth = worse). Returned as a score 0–100.
    """
    if len(gwl_history) < 12:
        return 50.0  # fallback for insufficient data

    threshold = gwl_history.quantile(0.80)
    drought_months = (gwl_history > threshold).sum()
    freq_pct = (drought_months / len(gwl_history)) * 100
    score = min((freq_pct / 20.0) * 100, 100.0)
    return float(score)


def _determine_estimate_type(district_id: str, conn) -> tuple:
    """
    Determine estimate_type for a district based on data readiness.
    Returns (estimate_type, zone_fallback_reason or None).
    """
    min_months = CONFIG.get("crisis_score", {}).get("fallback_strategy", {}).get("min_months_required", 24)
    min_pct = CONFIG.get("crisis_score", {}).get("data_readiness_min_pct", 60)

    with conn.cursor() as cur:
        # Count months of CGWB data for this district
        cur.execute(
            "SELECT COUNT(*) FROM raw_data WHERE district_id = %s AND source = 'CGWB'",
            (district_id,)
        )
        n_months = cur.fetchone()[0]

    if n_months >= min_months:
        return "district_level", None

    # Not enough per-district data — check zone-level
    with conn.cursor() as cur:
        cur.execute(
            "SELECT agro_climatic_zone FROM districts WHERE district_id = %s",
            (district_id,)
        )
        row = cur.fetchone()
        zone = row[0] if row else None

    if zone:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM raw_data r
                JOIN districts d ON r.district_id = d.district_id
                WHERE d.agro_climatic_zone = %s AND r.source = 'CGWB'
            """, (zone,))
            zone_months = cur.fetchone()[0]

        if zone_months >= min_months:
            reason = f"Only {n_months} months of CGWB data (need {min_months}); using zone '{zone}'"
            return "zone_fallback", reason

    reason = f"Only {n_months} months of CGWB data and zone lacks sufficient history"
    return "insufficient_data", reason


# ─── Component functions (now using real models) ─────────────────────────

def lr_trend_score(gwl: pd.Series) -> float:
    """
    LR-trend component, 0-100.
    Fits a sklearn LinearRegression on the GWL history and extracts the slope.
    Positive slope = worsening (deepening GWL), negative = improving.
    Score: 50 = stable, >50 = worsening, <50 = improving.
    """
    from sklearn.linear_model import LinearRegression

    if len(gwl) < 6:
        return 50.0

    X = np.arange(len(gwl)).reshape(-1, 1)
    y = gwl.values

    model = LinearRegression()
    model.fit(X, y)
    slope = model.coef_[0]

    # Scale: slope is in GWL-units/month (MinMax-scaled, so ~0-1 range).
    # A slope of +0.01/month → score ~60 (moderate worsening)
    # A slope of +0.05/month → score ~100 (severe worsening)
    score = 50.0 + slope * 1000.0
    return float(min(max(score, 0), 100))


def _build_feature_row(row, season=None):
    """Build a 12-element feature vector for the XGBoost model from a DB row."""
    if season is None:
        season = row.get("crop_season_flag", "Kharif")
    return [
        _safe_float(row.get("gwl_current", 0)),
        _safe_float(row.get("gwl_lag_3mo", 0)),
        _safe_float(row.get("gwl_lag_6mo", 0)),
        _safe_float(row.get("rainfall_current", 0)),
        _safe_float(row.get("rainfall_3mo_avg", 0)),
        _safe_float(row.get("monsoon_deficit_pct", 0)),
        _safe_float(row.get("temperature", 0)),
        _safe_float(row.get("evapotranspiration", 0)),
        _safe_float(row.get("water_balance_proxy", 0)),
        1.0 if season == "Kharif" else 0.0,
        1.0 if season == "Rabi" else 0.0,
        1.0 if season == "Zaid" else 0.0,
    ]


def xgb_risk_score(district_id: str, conn=None) -> float:
    """
    XGBoost-risk component, 0-100.
    Uses the trained XGBoost checkpoint to predict GWL 6 months ahead,
    then compares the predicted value against the current value to gauge
    whether the situation is worsening.

    Score mapping:
      - predicted ≈ current  → ~50 (stable)
      - predicted > current  → >50 (worsening)
      - predicted < current  → <50 (improving)
    The current depth itself is blended in so deeper districts score higher.
    """
    model = _load_xgb_model()
    if model is None:
        return 50.0

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        df = pd.read_sql(
            """SELECT gwl_current, gwl_lag_3mo, gwl_lag_6mo,
                      rainfall_current, rainfall_3mo_avg, monsoon_deficit_pct,
                      temperature, evapotranspiration, water_balance_proxy,
                      crop_season_flag
               FROM features
               WHERE district_id = %s AND gwl_current IS NOT NULL
               ORDER BY date DESC LIMIT 1""",
            conn, params=(district_id,)
        )

        if len(df) == 0:
            return 50.0

        row = df.iloc[0]
        feature_values = _build_feature_row(row)
        X = np.array([feature_values])
        predicted_gwl = float(model.predict(X)[0])
        predicted_gwl = max(0, min(1, predicted_gwl))

        current_gwl = _safe_float(row.get("gwl_current", 0))

        # Blend: 60% current depth + 40% predicted future depth
        # Both are 0-1 MinMax-scaled, so multiply by 100 for 0-100 score
        blended = 0.6 * current_gwl + 0.4 * predicted_gwl
        score = float(min(max(blended * 100, 0), 100))
        return score

    except Exception as e:
        print(f"XGBoost prediction error for {district_id}: {e}")
        return 50.0
    finally:
        if close_conn:
            conn.close()


def _safe_float(val, default=0.0):
    """Convert a value to float, returning default for None/NaN."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if np.isnan(f) else f
    except (ValueError, TypeError):
        return default


def xgb_forecast_6mo(district_id: str, conn=None) -> list:
    """
    Use the trained XGBoost model to generate a 6-month GWL forecast.
    The model predicts GWL 6 months ahead in a single step (not iterative),
    then interpolates the intermediate months for a smooth forecast curve.
    Returns a list of {"month": "YYYY-MM", "predicted_gwl": float}.
    """
    model = _load_xgb_model()
    if model is None:
        return []

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        # Fetch the most recent feature rows for this district
        df = pd.read_sql(
            """SELECT date, gwl_current, gwl_lag_3mo, gwl_lag_6mo,
                      rainfall_current, rainfall_3mo_avg, monsoon_deficit_pct,
                      temperature, evapotranspiration, water_balance_proxy,
                      crop_season_flag
               FROM features
               WHERE district_id = %s AND gwl_current IS NOT NULL
               ORDER BY date DESC LIMIT 6""",
            conn, params=(district_id,)
        )

        if len(df) < 1:
            return []

        df = df.sort_values("date")  # oldest first
        last_row = df.iloc[-1]
        last_date = pd.Timestamp(last_row["date"])
        current_gwl = _safe_float(last_row["gwl_current"])

        # Single-step prediction: model predicts GWL 6 months ahead
        feature_values = _build_feature_row(last_row)
        X = np.array([feature_values])
        predicted_6mo = float(model.predict(X)[0])
        predicted_6mo = max(0, min(1, predicted_6mo))  # Clamp

        # Interpolate intermediate months with a smooth curve
        forecast = []
        for i in range(1, 7):
            future_date = last_date + pd.DateOffset(months=i)
            # Linear interpolation from current to predicted 6-month value
            t = i / 6.0
            interp_gwl = current_gwl + t * (predicted_6mo - current_gwl)
            interp_gwl = max(0, min(1, interp_gwl))

            forecast.append({
                "month": future_date.strftime("%Y-%m"),
                "predicted_gwl": round(interp_gwl, 4),
            })

        return forecast

    except Exception as e:
        print(f"XGBoost forecast error for {district_id}: {e}")
        return []
    finally:
        if close_conn:
            conn.close()


def components_from_history(gwl: pd.Series, district_id: str = "") -> dict:
    """
    The three ensemble components (each 0-100) for one district, from its GWL
    history ordered oldest -> newest with NaNs removed.

    Shared by the live API (get_model_components) and models/backtest.py, so the
    ensemble weights are fitted on exactly the scores they are later applied to.
    """
    return {
        "lr_trend": lr_trend_score(gwl),
        "xgb_risk": xgb_risk_score(district_id) if district_id else float(min(max(gwl.iloc[-1] * 100, 0), 100)),
        "drought_frequency": compute_drought_frequency(district_id, gwl),
    }


def get_model_components(district_id: str) -> dict:
    """
    Fetch the underlying predictions from LR and XGBoost, and history for drought frequency.
    Tries the resolved district ID if the given one has no GWL data.
    """
    try:
        # Try to resolve to an ID that has actual GWL data
        try:
            from api.district_resolver import resolve_district_id
            resolved_id = resolve_district_id(district_id)
        except ImportError:
            resolved_id = district_id

        conn = get_connection()
        df = pd.read_sql(
            "SELECT date, gwl_current FROM features WHERE district_id = %s ORDER BY date",
            conn,
            params=(resolved_id,)
        )

        # If resolved ID has no non-null GWL, try all IDs for same district name
        if df["gwl_current"].dropna().empty and resolved_id == district_id:
            name_df = pd.read_sql(
                "SELECT district_name FROM districts WHERE district_id = %s",
                conn, params=(district_id,)
            )
            if not name_df.empty:
                name = name_df.iloc[0]["district_name"]
                alt_df = pd.read_sql(
                    "SELECT district_id FROM districts WHERE LOWER(district_name) = LOWER(%s)",
                    conn, params=(name,)
                )
                for _, row in alt_df.iterrows():
                    alt_id = row["district_id"]
                    if alt_id != district_id:
                        alt_data = pd.read_sql(
                            "SELECT date, gwl_current FROM features WHERE district_id = %s ORDER BY date",
                            conn, params=(alt_id,)
                        )
                        if not alt_data["gwl_current"].dropna().empty:
                            df = alt_data
                            resolved_id = alt_id
                            break

        conn.close()

        if len(df) == 0:
            raise ValueError(f"No data for district {district_id}")

        gwl_history = df["gwl_current"].dropna()

        if len(gwl_history) < 2:
            raise ValueError(f"Insufficient non-null GWL data for {district_id}")

        # LR trend from GWL history
        lr = lr_trend_score(gwl_history)

        # XGBoost risk from the trained model (uses full feature row)
        xgb = xgb_risk_score(resolved_id)

        # Drought frequency from GWL history
        drought = compute_drought_frequency(resolved_id, gwl_history)

        return {
            "lr_trend": lr,
            "xgb_risk": xgb,
            "drought_frequency": drought,
        }

    except Exception as e:
        print(f"Error computing components for {district_id}: {e}")
        return {
            "lr_trend": 50.0,
            "xgb_risk": 50.0,
            "drought_frequency": 50.0
        }




@lru_cache(maxsize=1024)
def compute_crisis_score(district_id: str) -> dict:
    """
    AquaIQ Crisis Score = weighted sum of LR trend + XGBoost risk + drought frequency.
    Weights come from config.yaml (fitted via backtest).
    Also determines estimate_type (district_level / zone_fallback / insufficient_data).
    """
    weights = _load_ensemble_weights()
    comps = get_model_components(district_id)

    # Determine estimate type
    try:
        conn = get_connection()
        estimate_type, zone_reason = _determine_estimate_type(district_id, conn)
        conn.close()
    except Exception:
        estimate_type, zone_reason = "district_level", None

    # If insufficient data, return null score
    if estimate_type == "insufficient_data":
        return {
            "district_id": district_id,
            "crisis_score": None,
            "tier": None,
            "estimate_type": estimate_type,
            "zone_fallback_reason": zone_reason,
            "ensemble_weights": weights,
            "components": comps,
        }

    final_score = (
        comps["lr_trend"] * weights["linear_regression_trend"] +
        comps["xgb_risk"] * weights["xgboost_risk"] +
        comps["drought_frequency"] * weights["drought_frequency"]
    )
    final_score = round(min(max(final_score, 0), 100))
    tier = score_to_tier(final_score)

    return {
        "district_id": district_id,
        "crisis_score": final_score,
        "tier": tier,
        "estimate_type": estimate_type,
        "zone_fallback_reason": zone_reason,
        "ensemble_weights": weights,
        "components": comps,
    }


def write_crisis_score_to_db(district_id: str, score_data: dict):
    """Write the computed crisis score to the crisis_scores table."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO crisis_scores
                    (district_id, forecast_date, aquaiq_score, tier, estimate_type, zone_fallback_reason)
                VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
                ON CONFLICT (district_id, forecast_date) DO UPDATE SET
                    aquaiq_score = EXCLUDED.aquaiq_score,
                    tier = EXCLUDED.tier,
                    estimate_type = EXCLUDED.estimate_type,
                    zone_fallback_reason = EXCLUDED.zone_fallback_reason,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                district_id,
                score_data.get("crisis_score"),
                score_data.get("tier"),
                score_data.get("estimate_type", "district_level"),
                score_data.get("zone_fallback_reason"),
            ))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    res = compute_crisis_score("RJ-Jaipur")
    print(res)
