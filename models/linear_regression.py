"""
AquaIQ — Linear Regression Baseline (Week 5, Yash)
-----------------------------------------------------
Trains a per-district Linear Regression model (2002-2019) and evaluates
on the 2023-2024 test set. This provides the baseline trend component
for the Crisis Score ensemble.

Course mapping: AS202 (Python for Data Science), CS205 (Statistical Methods).

Metrics: R², RMSE, MAE per district + aggregate.

Run:
    python models/linear_regression.py
    python models/linear_regression.py --top 20   # only top-20 data-rich districts
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from models import xgboost_model as forecast
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]
TRAIN_END = pd.Timestamp(CONFIG["date_range"]["train_end"])
TEST_START = pd.Timestamp(CONFIG["date_range"]["test_start"])


def get_connection():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def load_features() -> pd.DataFrame:
    """Use the same verified physical-unit generation as the forecaster."""
    return forecast.load_feature_matrix()


def train_per_district(df: pd.DataFrame, top_n: int = None) -> pd.DataFrame:
    """
    Train one Linear Regression per district.
    Returns a DataFrame of per-district metrics.
    """
    df = forecast.create_target(forecast.encode_crop_season(df))
    usable_features = forecast.get_feature_columns(df)

    print(f"  Features: {usable_features}")

    df["date"] = pd.to_datetime(df["date"])
    districts = df["district_id"].unique()

    # Filter to districts with enough data
    district_counts = df.groupby("district_id").size()
    valid_districts = district_counts[district_counts >= 24].index  # At least 2 years
    districts = [d for d in districts if d in valid_districts]

    if top_n:
        # Pick the top-N most data-rich districts
        top = district_counts.loc[valid_districts].nlargest(top_n).index
        districts = list(top)

    print(f"  Training on {len(districts)} districts (>= 24 months of data)\n")

    results = []
    models = {}

    for district_id in districts:
        ddf = df[df["district_id"] == district_id].copy()
        ddf = ddf.dropna(subset=usable_features + ["target_gwl_6mo"])
        train, test = forecast.temporal_split(ddf, TRAIN_END, forecast.heldout_origin_start(TRAIN_END), CONFIG["date_range"]["end"])

        if len(train) < 12 or len(test) < 3:
            continue

        X_train = train[usable_features].values
        y_train = train["target_gwl_6mo"].values
        X_test = test[usable_features].values
        y_test = test["target_gwl_6mo"].values

        model = LinearRegression()
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        r2 = r2_score(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        mae = mean_absolute_error(y_test, y_pred)

        results.append({
            "district_id": district_id,
            "n_train": len(train),
            "n_test": len(test),
            "r2": round(r2, 4),
            "rmse": round(rmse, 4),
            "mae": round(mae, 4),
            "units": "m_bgl", "horizon_months": forecast.FORECAST_HORIZON,
        })
        models[district_id] = model

    results_df = pd.DataFrame(results)
    return results_df, models


def save_results(results_df: pd.DataFrame):
    """Save per-district results to CSV and print summary."""
    out_path = PROCESSED_DIR / "linear_regression_results.csv"
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    results_df.to_csv(out_path, index=False)
    print(f"  Results saved to {out_path}")
    if results_df.empty:
        print("No districts have sufficient observed training/held-out samples.")
        return

    # Aggregate stats
    print(f"\n  Aggregate Metrics ({len(results_df)} districts):")
    print(f"    Mean R2   = {results_df['r2'].mean():.4f}")
    print(f"    Median R2 = {results_df['r2'].median():.4f}")
    print(f"    Mean RMSE = {results_df['rmse'].mean():.4f}")
    print(f"    Mean MAE  = {results_df['mae'].mean():.4f}")

    # Distribution
    r2_bins = [
        ("R2 > 0.75 (good)", (results_df["r2"] > 0.75).sum()),
        ("R2 0.50-0.75 (moderate)", ((results_df["r2"] >= 0.50) & (results_df["r2"] <= 0.75)).sum()),
        ("R2 < 0.50 (poor)", (results_df["r2"] < 0.50).sum()),
    ]
    print(f"\n  R2 Distribution:")
    for label, count in r2_bins:
        pct = count / len(results_df) * 100
        print(f"    {label}: {count} ({pct:.0f}%)")

    # Top 5
    print(f"\n  Top 5 districts by R2:")
    for _, row in results_df.nlargest(5, "r2").iterrows():
        print(f"    {row['district_id']:>15s}: R2={row['r2']:.4f}  RMSE={row['rmse']:.4f}")

    # Bottom 5
    print(f"\n  Bottom 5 districts by R2:")
    for _, row in results_df.nsmallest(5, "r2").iterrows():
        print(f"    {row['district_id']:>15s}: R2={row['r2']:.4f}  RMSE={row['rmse']:.4f}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="AquaIQ Linear Regression")
    parser.add_argument("--top", type=int, default=None,
                        help="Only train on top-N most data-rich districts")
    args = parser.parse_args(argv)

    print("AquaIQ -- Linear Regression Baseline\n")

    print("[1/3] Loading features...")
    df = load_features()
    print(f"  Loaded {len(df):,} rows, {df['district_id'].nunique()} districts")

    print("\n[2/3] Training per-district models...")
    results_df, models = train_per_district(df, top_n=args.top)

    print("\n[3/3] Saving results...")
    save_results(results_df)

    print("\nDone.")


if __name__ == "__main__":
    main()
