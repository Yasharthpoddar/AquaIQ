"""
AquaIQ — XGBoost Hyperparameter Grid Search (Week 6, Yash)
-------------------------------------------------------------
Grid search over max_depth, learning_rate, subsample using
CPU-only XGBoost. Results logged to MLflow and CSV.

Run:
    python models/xgboost_gridsearch.py
    python models/xgboost_gridsearch.py --quick   # reduced grid for testing
"""

import argparse
import os
import sys
import itertools
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

PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]
DATE_RANGE = CONFIG["date_range"]

# Grid search parameters
FULL_GRID = {
    "max_depth": [3, 5, 7, 9],
    "learning_rate": [0.01, 0.05, 0.1, 0.2],
    "subsample": [0.6, 0.8, 1.0],
}

QUICK_GRID = {
    "max_depth": [3, 7],
    "learning_rate": [0.05, 0.1],
    "subsample": [0.8],
}


def load_data():
    """Load feature matrix and create target."""
    path = PROCESSED_DIR / "features_matrix.csv"
    if not path.exists():
        print("ERROR: features_matrix.csv not found. Run preprocessing/features.py first.")
        sys.exit(1)
    df = pd.read_csv(path, parse_dates=["date"])
    return df


def prepare_data(df):
    """Build target and split."""
    df = df.sort_values(["district_id", "date"]).copy()
    df["target_gwl_6mo"] = df.groupby("district_id")["GWL_current"].shift(-6)
    df = df.dropna(subset=["target_gwl_6mo"])

    feature_cols = [c for c in CONFIG["features"]
                    if c in df.columns and c != "crop_season_flag"]

    # One-hot encode crop_season_flag if present
    if "crop_season_flag" in df.columns:
        dummies = pd.get_dummies(df["crop_season_flag"], prefix="season", dtype=float)
        df = pd.concat([df, dummies], axis=1)
        feature_cols.extend(dummies.columns.tolist())

    train_end = pd.Timestamp(DATE_RANGE["train_end"])
    val_end = pd.Timestamp(DATE_RANGE["val_end"])

    train = df[df["date"] <= train_end]
    val = df[(df["date"] > train_end) & (df["date"] <= val_end)]

    return train, val, feature_cols


def run_grid_search(train, val, feature_cols, grid):
    """Run exhaustive grid search over hyperparameters."""
    import xgboost as xgb

    X_train = train[feature_cols].fillna(0).values
    y_train = train["target_gwl_6mo"].values
    X_val = val[feature_cols].fillna(0).values
    y_val = val["target_gwl_6mo"].values

    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))

    print(f"  Grid: {len(combos)} combinations")
    print(f"  Train: {len(X_train):,} | Val: {len(X_val):,} | Features: {len(feature_cols)}\n")

    results = []
    for i, values in enumerate(combos):
        params = dict(zip(keys, values))

        model = xgb.XGBRegressor(
            n_estimators=500,
            max_depth=params["max_depth"],
            learning_rate=params["learning_rate"],
            subsample=params["subsample"],
            random_state=42,
            objective="reg:squarederror",
            verbosity=0,
        )

        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        y_pred = model.predict(X_val)

        rmse = np.sqrt(mean_squared_error(y_val, y_pred))
        r2 = r2_score(y_val, y_pred)

        results.append({**params, "rmse": round(rmse, 4), "r2": round(r2, 4)})

        print(f"  [{i+1}/{len(combos)}] depth={params['max_depth']} "
              f"lr={params['learning_rate']} sub={params['subsample']} "
              f"-> RMSE={rmse:.4f} R2={r2:.4f}")

        # MLflow logging (best-effort)
        try:
            import mlflow
            mlflow.set_experiment("aquaiq-xgboost-gridsearch")
            with mlflow.start_run(run_name=f"gs_{i}"):
                mlflow.log_params(params)
                mlflow.log_metrics({"val_rmse": rmse, "val_r2": r2})
        except Exception:
            pass

    return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description="XGBoost Grid Search")
    parser.add_argument("--quick", action="store_true", help="Use reduced grid")
    args = parser.parse_args()

    print("AquaIQ -- XGBoost Hyperparameter Grid Search\n")

    print("[1/3] Loading data...")
    df = load_data()

    print("[2/3] Preparing train/val split...")
    train, val, feature_cols = prepare_data(df)

    print(f"\n[3/3] Running grid search ({'quick' if args.quick else 'full'})...")
    grid = QUICK_GRID if args.quick else FULL_GRID
    results = run_grid_search(train, val, feature_cols, grid)

    # Save results
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out_path = PROCESSED_DIR / "xgboost_gridsearch_results.csv"
    results.to_csv(out_path, index=False)
    print(f"\n  Results saved to {out_path}")

    # Best config
    best = results.loc[results["rmse"].idxmin()]
    print(f"\n  Best configuration:")
    print(f"    max_depth      = {best['max_depth']}")
    print(f"    learning_rate  = {best['learning_rate']}")
    print(f"    subsample      = {best['subsample']}")
    print(f"    RMSE           = {best['rmse']}")
    print(f"    R2             = {best['r2']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
