"""
AquaIQ — Ensemble Weight Backtest & XGBoost Walk-Forward Validation
---------------------------------------------------------------------
(a) Fits ensemble weights w1–w4 by minimising MAE against known drought
    windows (2015-16, 2018-19) — not hand-set.
(b) Runs XGBoost walk-forward validation: rolling folds 2020→2021→2022→2023
    plus a 2023–2024 held-out test, reporting RMSE/R²/NSE per fold.

Saves fitted weights to config.yaml under model_hyperparameters.ensemble.fitted_weights.
Reports all metrics and saves backtest results.

Run:
    python models/backtest.py
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import minimize
from sklearn.metrics import mean_squared_error, r2_score
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

CONFIG_PATH = ROOT / "config.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

try:
    from models.ensemble import components_from_history
except ImportError:  # executed as a script: python models/backtest.py
    sys.path.insert(0, str(ROOT))
    from models.ensemble import components_from_history

HORIZON_MONTHS = 6  # the Crisis Score anticipates groundwater depth six months ahead


def get_connection():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def nash_sutcliffe_efficiency(y_true, y_pred):
    """Nash-Sutcliffe Efficiency — standard hydrology metric."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return float("nan")
    return 1 - (ss_res / ss_tot)


def load_feature_matrix(allow_synthetic: bool = False) -> pd.DataFrame:
    """
    Load the feature matrix from the DB, falling back to the processed CSV.
    Where the data came from is recorded in df.attrs["data_source"].

    Synthetic data is generated ONLY when allow_synthetic=True (--synthetic).
    Such results are a smoke test of this script and must never be reported as
    model performance on real districts.
    """
    csv_path = ROOT / "data" / "processed" / "features_matrix.csv"
    try:
        conn = get_connection()
        df = pd.read_sql("SELECT * FROM features ORDER BY district_id, date", conn)
        conn.close()
        if len(df) > 0:
            print(f"  Loaded {len(df):,} rows from features table")
            df.attrs["data_source"] = "features table (PostgreSQL)"
            return df
    except Exception:
        pass

    if csv_path.exists():
        df = pd.read_csv(csv_path, parse_dates=["date"])
        print(f"  Loaded {len(df):,} rows from {csv_path.name}")
        df.attrs["data_source"] = csv_path.name
        return df

    if not allow_synthetic:
        raise SystemExit(
            "ERROR: no feature data found (features table empty or unreachable, and "
            f"{csv_path.relative_to(ROOT)} is missing).\\n"
            "Run the ingestion + preprocessing pipeline first, or pass --synthetic for a "
            "smoke test whose results must not be reported."
        )

    print("  --synthetic: generating SYNTHETIC data (smoke test only).")
    df = _generate_synthetic_features()
    df.attrs["data_source"] = "synthetic"
    return df


def _generate_synthetic_features():
    """
    Generate realistic synthetic feature data for backtesting.
    Used when DB/CSV aren't populated yet.
    """
    np.random.seed(42)
    districts = [f"D-{i:03d}" for i in range(50)]
    dates = pd.date_range("2002-01-01", "2024-12-01", freq="MS")
    rows = []
    for d in districts:
        base_gwl = np.random.uniform(3, 20)
        trend = np.random.uniform(0.001, 0.02)  # slow depletion
        for i, date in enumerate(dates):
            month = date.month
            seasonal = 2 * np.sin(2 * np.pi * month / 12)
            noise = np.random.normal(0, 0.5)
            gwl = base_gwl + trend * i + seasonal + noise
            rainfall = max(0, 80 + 60 * np.sin(2 * np.pi * (month - 7) / 12) + np.random.normal(0, 20))
            temp = 25 + 10 * np.sin(2 * np.pi * (month - 5) / 12) + np.random.normal(0, 2)
            et = max(0, 3 + 2 * np.sin(2 * np.pi * (month - 5) / 12) + np.random.normal(0, 0.5))
            rows.append({
                "district_id": d, "date": date,
                "gwl_current": gwl,
                "gwl_lag_3mo": gwl - 0.3 + np.random.normal(0, 0.2),
                "gwl_lag_6mo": gwl - 0.6 + np.random.normal(0, 0.3),
                "rainfall_current": rainfall,
                "rainfall_3mo_avg": rainfall + np.random.normal(0, 10),
                "monsoon_deficit_pct": np.random.uniform(-30, 30),
                "temperature": temp,
                "evapotranspiration": et,
                "water_balance_proxy": rainfall - et,
                "crop_season_flag": ["Kharif", "Kharif", "Kharif", "Kharif", "Kharif",
                                      "Rabi", "Rabi", "Rabi", "Rabi",
                                      "Zaid", "Zaid", "Zaid"][month - 1],
            })
    df = pd.DataFrame(rows)
    # The real features table stores MinMax-scaled GWL ([0, 1]); mimic that so the
    # ensemble components behave as they do in the live API.
    gwl_cols = ["gwl_current", "gwl_lag_3mo", "gwl_lag_6mo"]
    lo, hi = df[gwl_cols].min().min(), df[gwl_cols].max().max()
    df[gwl_cols] = (df[gwl_cols] - lo) / (hi - lo)
    return df


# ─── Part (a): Ensemble Weight Fitting ──────────────────────────────────────

def _compute_component_scores(df, years=None):
    """
    For each district-month t, compute the three ensemble components from the GWL
    history up to t -- with models.ensemble.components_from_history, the same
    function the live API uses -- plus the target: that district's GWL
    HORIZON_MONTHS later. Months without an observed GWL at t or at t+HORIZON are
    skipped; ``years`` optionally restricts t to those calendar years.
    Assumes one row per month per district (the features table is gap-filled).
    """
    columns = ["district_id", "date", "gwl_actual", "gwl_future",
               "lr_score", "xgb_score", "drought_score"]
    results = []
    for did, group in df.groupby("district_id"):
        group = group.sort_values("date")
        dates = pd.to_datetime(group["date"]).reset_index(drop=True)
        gwl = group["gwl_current"].reset_index(drop=True)
        if len(gwl) < 24:
            continue

        for idx in range(12, len(gwl) - HORIZON_MONTHS):
            if years is not None and dates.iloc[idx].year not in years:
                continue
            gap = dates.iloc[idx + HORIZON_MONTHS].to_period("M") - dates.iloc[idx].to_period("M")
            current, future = gwl.iloc[idx], gwl.iloc[idx + HORIZON_MONTHS]
            if gap.n != HORIZON_MONTHS or pd.isna(current) or pd.isna(future):
                continue

            comps = components_from_history(gwl.iloc[: idx + 1].dropna(), str(did))
            results.append({
                "district_id": did,
                "date": dates.iloc[idx],
                "gwl_actual": current,
                "gwl_future": future,
                "lr_score": comps["lr_trend"],
                "xgb_score": comps["xgb_risk"],
                "drought_score": comps["drought_frequency"],
            })

    return pd.DataFrame(results, columns=columns)


def fit_ensemble_weights(df):
    """
    Fit weights w1, w2, w3 by minimising MAE on the drought backtesting windows
    (testing.backtest_years in config.yaml).

    Components are computed exactly as in the live API (models/ensemble.py); the
    target is each district's GWL six months later, rescaled to 0-100 (deeper =
    worse). Weights are constrained to be non-negative and to sum to 1 (softmax
    parametrisation), so every component can only add to the Crisis Score.
    """
    print("\\n== Part (a): Ensemble Weight Fitting ==")

    backtest_years = CONFIG.get("testing", {}).get("backtest_years", [2015, 2016, 2018, 2019])
    bt = _compute_component_scores(df, years=backtest_years)

    if len(bt) == 0:
        print("  WARNING: No data in drought windows --- using initial weights.")
        return CONFIG["model_hyperparameters"]["ensemble"]["initial_weights"]

    print(f"  Backtest samples: {len(bt):,} (years {backtest_years}, "
          f"target = GWL {HORIZON_MONTHS} months ahead)")

    lo, hi = bt["gwl_future"].min(), bt["gwl_future"].max()
    if hi == lo:
        hi = lo + 1
    y = ((bt["gwl_future"] - lo) / (hi - lo) * 100).values
    X = bt[["lr_score", "xgb_score", "drought_score"]].values

    def to_weights(z):
        e = np.exp(z - np.max(z))
        return e / e.sum()

    def objective(z):
        return np.mean(np.abs(y - X @ to_weights(z)))

    initial = CONFIG["model_hyperparameters"]["ensemble"]["initial_weights"]
    x0 = np.log(np.clip([
        initial.get("linear_regression_trend", 0.45),
        initial.get("xgboost_risk", 0.35),
        initial.get("drought_frequency", 0.20),
    ], 1e-6, None))

    result = minimize(
        objective, x0,
        method="Nelder-Mead",
        options={"maxiter": 5000, "xatol": 1e-6, "fatol": 1e-9},
    )

    fitted = to_weights(result.x)
    fitted_weights = {
        "linear_regression_trend": round(float(fitted[0]), 4),
        "xgboost_risk": round(float(fitted[1]), 4),
        "drought_frequency": round(float(fitted[2]), 4),
    }

    print("  Fitted weights:")
    for k, v in fitted_weights.items():
        print(f"    {k}: {v}")
    print(f"  MAE (backtest): {result.fun:.4f}")

    return fitted_weights


# ─── Part (b): XGBoost Walk-Forward Validation ─────────────────────────────

def run_walkforward_validation(df):
    """
    Walk-forward validation: rolling folds 2020→2021→2022→2023
    plus a 2023–2024 held-out test.
    """
    import xgboost as xgb

    print("\n== Part (b): XGBoost Walk-Forward Validation ==")

    XGB_PARAMS = CONFIG["model_hyperparameters"]["xgboost"]
    FORECAST_HORIZON = 6

    # Prepare data
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # One-hot encode crop_season_flag
    if "crop_season_flag" in df.columns:
        dummies = pd.get_dummies(df["crop_season_flag"], prefix="season", dtype=float)
        df = pd.concat([df, dummies], axis=1)
        df = df.drop(columns=["crop_season_flag"])

    # Create target
    df = df.sort_values(["district_id", "date"])
    df["target_gwl_6mo"] = df.groupby("district_id")["gwl_current"].shift(-FORECAST_HORIZON)
    df = df.dropna(subset=["target_gwl_6mo"])

    exclude = {"id", "district_id", "date", "target_gwl_6mo", "data_readiness_score"}
    feature_cols = [c for c in df.columns if c not in exclude and not c.startswith("_")]

    # Walk-forward folds
    folds = [
        {"train_end": "2019-12-31", "test_year": 2020},
        {"train_end": "2020-12-31", "test_year": 2021},
        {"train_end": "2021-12-31", "test_year": 2022},
        {"train_end": "2022-12-31", "test_year": 2023},
    ]

    results = []
    print(f"  Features: {len(feature_cols)}")
    print()

    for fold in folds:
        train_mask = df["date"] <= fold["train_end"]
        test_mask = df["date"].dt.year == fold["test_year"]

        train = df[train_mask]
        test = df[test_mask]

        if len(test) == 0 or len(train) == 0:
            print(f"  Fold {fold['test_year']}: SKIP (empty)")
            continue

        X_train = train[feature_cols].values
        y_train = train["target_gwl_6mo"].values
        X_test = test[feature_cols].values
        y_test = test["target_gwl_6mo"].values

        model = xgb.XGBRegressor(
            n_estimators=XGB_PARAMS["n_estimators"],
            max_depth=XGB_PARAMS["max_depth"],
            learning_rate=XGB_PARAMS["learning_rate"],
            subsample=XGB_PARAMS["subsample"],
            random_state=XGB_PARAMS["random_state"],
            objective="reg:squarederror",
            verbosity=0,
        )
        model.fit(X_train, y_train, verbose=False)

        y_pred = model.predict(X_test)
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        r2 = float(r2_score(y_test, y_pred))
        nse = float(nash_sutcliffe_efficiency(y_test, y_pred))

        results.append({
            "fold": f"train->{fold['test_year']}",
            "n_train": len(train),
            "n_test": len(test),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
            "nse": round(nse, 4),
        })

        print(f"  Fold train->{fold['test_year']}: "
              f"RMSE={rmse:.4f}  R^2={r2:.4f}  NSE={nse:.4f}  "
              f"(train={len(train):,} test={len(test):,})")

    # Held-out test: 2023-2024
    print("\n  -- Held-out test (2023-2024) --")
    train_mask = df["date"] <= "2022-12-31"
    test_mask = df["date"].dt.year.isin([2023, 2024])
    train = df[train_mask]
    test = df[test_mask]

    if len(test) > 0 and len(train) > 0:
        X_train = train[feature_cols].values
        y_train = train["target_gwl_6mo"].values
        X_test = test[feature_cols].values
        y_test = test["target_gwl_6mo"].values

        model = xgb.XGBRegressor(
            n_estimators=XGB_PARAMS["n_estimators"],
            max_depth=XGB_PARAMS["max_depth"],
            learning_rate=XGB_PARAMS["learning_rate"],
            subsample=XGB_PARAMS["subsample"],
            random_state=XGB_PARAMS["random_state"],
            objective="reg:squarederror",
            verbosity=0,
        )
        model.fit(X_train, y_train, verbose=False)

        y_pred = model.predict(X_test)
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        r2 = float(r2_score(y_test, y_pred))
        nse = float(nash_sutcliffe_efficiency(y_test, y_pred))

        results.append({
            "fold": "held-out 2023-2024",
            "n_train": len(train),
            "n_test": len(test),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
            "nse": round(nse, 4),
        })

        print(f"  RMSE={rmse:.4f}  R^2={r2:.4f}  NSE={nse:.4f}  (n={len(test):,})")

        # Save model checkpoint
        os.makedirs(ROOT / CONFIG["paths"]["model_checkpoints"], exist_ok=True)
        checkpoint = ROOT / CONFIG["paths"]["xgboost_checkpoint"]
        model.save_model(str(checkpoint))
        print(f"  Model saved to {checkpoint}")
    else:
        print("  SKIP: No test data for 2023-2024.")

    return results


# ─── Save to config.yaml ────────────────────────────────────────────────────

def save_to_config(fitted_weights, walkforward_results, data_source):
    """Save fitted weights and backtest metrics (with their data source) to config.yaml."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    # Save fitted weights
    config["model_hyperparameters"]["ensemble"]["fitted_weights"] = fitted_weights

    # Save backtest metrics
    config["backtest_results"] = {
        "data_source": data_source,
        "ensemble_weights": fitted_weights,
        "walkforward_validation": walkforward_results,
    }

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\\n  Saved fitted weights and metrics to {CONFIG_PATH}")


def should_write_config(data_source: str) -> bool:
    """Results from synthetic smoke-test data are never written to config.yaml."""
    return data_source != "synthetic"


# ─── Main ────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="AquaIQ ensemble backtest & walk-forward validation")
    parser.add_argument("--synthetic", action="store_true",
                        help="run on generated data as a smoke test (results are NOT saved to config.yaml)")
    args = parser.parse_args(argv)

    print("AquaIQ — Ensemble Backtest & Walk-Forward Validation\\n")

    # Load data
    print("[1/3] Loading feature matrix...")
    df = load_feature_matrix(allow_synthetic=args.synthetic)
    data_source = df.attrs.get("data_source", "unknown")
    print(f"  Data source: {data_source} ({df['district_id'].nunique()} districts)")

    # Part (a): Fit ensemble weights
    print("[2/3] Fitting ensemble weights on drought backtests...")
    fitted_weights = fit_ensemble_weights(df)

    # Part (b): Walk-forward validation
    print("[3/3] Running XGBoost walk-forward validation...")
    wf_results = run_walkforward_validation(df)

    if should_write_config(data_source):
        save_to_config(fitted_weights, wf_results, data_source)
    else:
        print("\\n  Synthetic smoke test: config.yaml was NOT updated.")

    print("\\n=== Done ===")


if __name__ == "__main__":
    main()
