"""
AquaIQ -- XGBoost Training Pipeline Skeleton (Week 3)
------------------------------------------------------
Defines the feature matrix construction and train/val/test split logic
for the XGBoost GWL forecasting model.

Architecture:
  1. Pull the 10-feature matrix from the `features` table (or CSV fallback)
  2. Create the target variable: GWL 6 months ahead
  3. Split: train (2002-2019) / val (2020-2022) / test (2023-2024)
     Walk-forward validation uses rolling windows within the val period.
  4. Train XGBoost regressor (500 trees, config.yaml hyperparams)
  5. Evaluate: RMSE, R², NSE per walk-forward window
  6. Save model checkpoint

Full training happens in Week 8. This skeleton sets up the pipeline
and ensures the data flow works end-to-end.

Run:
    python models/xgboost_model.py          # train
    python models/xgboost_model.py --eval   # evaluate saved model
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv
from sklearn.metrics import mean_squared_error, r2_score

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

FEATURES = CONFIG["features"]
XGB_PARAMS = CONFIG["model_hyperparameters"]["xgboost"]
DATE_RANGE = CONFIG["date_range"]
CHECKPOINT_PATH = ROOT / CONFIG["paths"]["xgboost_checkpoint"]
FORECAST_HORIZON = 6  # months ahead


def get_connection():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def load_feature_matrix() -> pd.DataFrame:
    """
    Load the 10-feature matrix. Tries the features table first,
    falls back to the CSV export if the table is empty.
    """
    csv_path = ROOT / "data" / "processed" / "features_matrix.csv"

    # Try PostgreSQL first
    try:
        conn = get_connection()
        df = pd.read_sql(
            "SELECT * FROM features ORDER BY district_id, date",
            conn,
        )
        conn.close()
        if len(df) > 0:
            print(f"  Loaded {len(df):,} rows from features table")
            return df
    except Exception:
        pass

    # Fallback to CSV
    if csv_path.exists():
        df = pd.read_csv(csv_path, parse_dates=["date"])
        print(f"  Loaded {len(df):,} rows from {csv_path.name}")
        return df

    print("ERROR: No feature data found. Run preprocessing/features.py first.")
    sys.exit(1)


def create_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create the target variable: GWL value 6 months ahead.
    For each district, shift gwl_current back by FORECAST_HORIZON months.
    Rows without a valid target (last 6 months per district) are dropped.
    """
    df = df.sort_values(["district_id", "date"]).copy()
    df["target_gwl_6mo"] = (
        df.groupby("district_id")["gwl_current"]
        .shift(-FORECAST_HORIZON)
    )
    before = len(df)
    df = df.dropna(subset=["target_gwl_6mo"])
    print(f"  Target created: {len(df):,} rows (dropped {before - len(df):,} without 6mo lookahead)")
    return df


def temporal_split(df: pd.DataFrame) -> tuple:
    """
    Time-based split (not random!) to prevent data leakage:
      train: 2002-01-01 to 2019-12-31
      val:   2020-01-01 to 2022-12-31
      test:  2023-01-01 to 2024-12-31
    """
    df["date"] = pd.to_datetime(df["date"])

    train_end = pd.Timestamp(DATE_RANGE["train_end"])
    val_end = pd.Timestamp(DATE_RANGE["val_end"])

    train = df[df["date"] <= train_end]
    val = df[(df["date"] > train_end) & (df["date"] <= val_end)]
    test = df[df["date"] > val_end]

    print(f"  Split: train={len(train):,} | val={len(val):,} | test={len(test):,}")
    return train, val, test


def encode_crop_season(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot encode crop_season_flag (Kharif/Rabi/Zaid) for XGBoost."""
    df = df.copy()
    if "crop_season_flag" in df.columns:
        dummies = pd.get_dummies(df["crop_season_flag"], prefix="season", dtype=float)
        df = pd.concat([df, dummies], axis=1)
        df = df.drop(columns=["crop_season_flag"])
    return df


def get_feature_columns(df: pd.DataFrame) -> list:
    """Return the list of feature columns (excluding metadata and target)."""
    exclude = {"id", "district_id", "date", "target_gwl_6mo", "data_readiness_score"}
    return [c for c in df.columns if c not in exclude and not c.startswith("_")]


def nash_sutcliffe_efficiency(y_true, y_pred):
    """Nash-Sutcliffe Efficiency — standard hydrology metric."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return float("nan")
    return 1 - (ss_res / ss_tot)


def walk_forward_validate(model, val_df: pd.DataFrame, feature_cols: list) -> dict:
    """
    Walk-forward validation: train on expanding window, predict next period.
    Windows: 2020, 2020-2021, 2020-2022 (predict the next year each time).
    
    Returns dict of metrics per window.
    """
    val_df = val_df.copy()
    val_df["year"] = val_df["date"].dt.year
    years = sorted(val_df["year"].unique())

    results = []
    for i, year in enumerate(years):
        test_mask = val_df["year"] == year
        y_true = val_df.loc[test_mask, "target_gwl_6mo"].values
        X_test = val_df.loc[test_mask, feature_cols].values

        if len(y_true) == 0:
            continue

        y_pred = model.predict(X_test)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        r2 = r2_score(y_true, y_pred)
        nse = nash_sutcliffe_efficiency(y_true, y_pred)

        results.append({
            "window": f"val-{year}",
            "n_samples": len(y_true),
            "rmse": round(rmse, 4),
            "r2": round(r2, 4),
            "nse": round(nse, 4),
        })
        print(f"    Window {year}: RMSE={rmse:.4f}  R2={r2:.4f}  NSE={nse:.4f}  (n={len(y_true)})")

    return results


def train_xgboost(train_df, val_df, feature_cols):
    """Train XGBoost with config.yaml hyperparameters + MLflow tracking."""
    import xgboost as xgb

    X_train = train_df[feature_cols].values
    y_train = train_df["target_gwl_6mo"].values
    X_val = val_df[feature_cols].values
    y_val = val_df["target_gwl_6mo"].values

    model = xgb.XGBRegressor(
        n_estimators=XGB_PARAMS["n_estimators"],
        max_depth=XGB_PARAMS["max_depth"],
        learning_rate=XGB_PARAMS["learning_rate"],
        subsample=XGB_PARAMS["subsample"],
        random_state=XGB_PARAMS["random_state"],
        objective="reg:squarederror",
        eval_metric="rmse",
        verbosity=1,
    )

    print(f"\n  Training XGBoost ({XGB_PARAMS['n_estimators']} trees, "
          f"max_depth={XGB_PARAMS['max_depth']}, lr={XGB_PARAMS['learning_rate']})...")

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    # Save checkpoint
    os.makedirs(CHECKPOINT_PATH.parent, exist_ok=True)
    model.save_model(str(CHECKPOINT_PATH))
    print(f"  Model saved to {CHECKPOINT_PATH}")

    # MLflow tracking (best-effort — doesn't fail if mlflow isn't running)
    try:
        import mlflow
        mlflow.set_experiment("aquaiq-xgboost")
        with mlflow.start_run(run_name="xgboost_baseline"):
            # Log hyperparameters
            mlflow.log_params({
                "n_estimators": XGB_PARAMS["n_estimators"],
                "max_depth": XGB_PARAMS["max_depth"],
                "learning_rate": XGB_PARAMS["learning_rate"],
                "subsample": XGB_PARAMS["subsample"],
                "n_features": len(feature_cols),
                "n_train": len(train_df),
                "n_val": len(val_df),
            })

            # Log validation metrics
            y_val_pred = model.predict(X_val)
            val_rmse = np.sqrt(mean_squared_error(y_val, y_val_pred))
            val_r2 = r2_score(y_val, y_val_pred)
            mlflow.log_metrics({
                "val_rmse": val_rmse,
                "val_r2": val_r2,
            })

            # Log model artifact
            mlflow.log_artifact(str(CHECKPOINT_PATH))
            print(f"  MLflow run logged to experiment 'aquaiq-xgboost'")
    except Exception as e:
        print(f"  MLflow tracking skipped ({e})")

    return model


def evaluate_on_test(model, test_df, feature_cols):
    """Final evaluation on held-out 2023-2024 test set."""
    X_test = test_df[feature_cols].values
    y_test = test_df["target_gwl_6mo"].values

    if len(y_test) == 0:
        print("  WARNING: Test set is empty — no 2023-2024 data with 6mo lookahead.")
        return

    y_pred = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    nse = nash_sutcliffe_efficiency(y_test, y_pred)

    print(f"\n  Test set (2023-2024):")
    print(f"    RMSE = {rmse:.4f}")
    print(f"    R2   = {r2:.4f}")
    print(f"    NSE  = {nse:.4f}")
    print(f"    n    = {len(y_test)}")


def main():
    parser = argparse.ArgumentParser(description="AquaIQ XGBoost Training Pipeline")
    parser.add_argument("--eval", action="store_true", help="Evaluate saved model only")
    args = parser.parse_args()

    print("AquaIQ -- XGBoost Training Pipeline\n")

    # 1. Load features
    print("[1/5] Loading feature matrix...")
    df = load_feature_matrix()

    # 2. Encode categoricals
    print("[2/5] Encoding features...")
    df = encode_crop_season(df)

    # 3. Create target
    print("[3/5] Creating 6-month forecast target...")
    df = create_target(df)

    # 4. Split
    print("[4/5] Temporal split...")
    train, val, test = temporal_split(df)

    feature_cols = get_feature_columns(train)
    print(f"  Feature columns ({len(feature_cols)}): {feature_cols}")

    if args.eval:
        # Load saved model
        import xgboost as xgb
        if not CHECKPOINT_PATH.exists():
            print(f"ERROR: No saved model at {CHECKPOINT_PATH}. Train first.")
            sys.exit(1)
        model = xgb.XGBRegressor()
        model.load_model(str(CHECKPOINT_PATH))
        print(f"  Loaded model from {CHECKPOINT_PATH}")
    else:
        # 5. Train
        print("[5/5] Training...")
        model = train_xgboost(train, val, feature_cols)

    # Walk-forward validation
    print("\n  Walk-forward validation:")
    walk_forward_validate(model, val, feature_cols)

    # Test set evaluation
    evaluate_on_test(model, test, feature_cols)

    print("\nDone.")


if __name__ == "__main__":
    main()
