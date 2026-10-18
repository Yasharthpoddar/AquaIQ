"""
AquaIQ — Linear Regression Baseline (Week 5, Yash)
-----------------------------------------------------
Trains per-district Linear Regression using the configured training-label cutoff.
Held-out origins run from heldout_origin_start(cutoff) through date_range.end;
the shared splitter enforces the six-month embargo and observed targets.
This reporting script is separate from the serving ensemble's trend calculation.

Course mapping: AS202 (Python for Data Science), CS205 (Statistical Methods).

Metrics: R², RMSE, MAE per district + descriptive district summaries.
R² is unavailable for singleton, constant or numerically unresolved targets;
MAE/RMSE remain defined for finite nonempty prediction arrays.

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


def report_metrics(y_true, y_pred) -> dict:
    """Map shared evaluation semantics onto the existing four-decimal columns.

    Undefined R² stays None; no zero is substituted. The shared float64 guard
    measures numerical resolution, not instrument precision or physical variance.
    """
    measured = forecast.metrics(y_true, y_pred)
    return {"r2": None if measured["r2"] is None else round(measured["r2"], 4),
            "rmse": round(measured["rmse_m"], 4),
            "mae": round(measured["mae_m"], 4)}


def summarize_metrics(results_df: pd.DataFrame) -> dict:
    """Descriptive summaries over available district metrics, not pooled skill."""
    summary = {}
    for column in ("r2", "rmse", "mae"):
        values = pd.to_numeric(results_df[column], errors="raise")
        available = values.loc[values.notna() & np.isfinite(values)]
        summary[column] = {
            "available": len(available), "unavailable": len(values) - len(available),
            "mean": float(available.mean()) if len(available) else None,
            "median": float(available.median()) if len(available) else None,
        }
    return summary


def _display_metric(value):
    return "unavailable" if value is None else f"{value:.4f}"


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

        results.append({
            "district_id": district_id,
            "n_train": len(train),
            "n_test": len(test),
            **report_metrics(y_test, y_pred),
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

    summary = summarize_metrics(results_df)
    print(f"\n  District summaries ({len(results_df)} districts; available values only):")
    print(f"    Mean R2   = {_display_metric(summary['r2']['mean'])}")
    print(f"    Median R2 = {_display_metric(summary['r2']['median'])}")
    print(f"    R2 available = {summary['r2']['available']}; unavailable = {summary['r2']['unavailable']}")
    print(f"    Mean RMSE = {_display_metric(summary['rmse']['mean'])}")
    print(f"    Mean MAE  = {_display_metric(summary['mae']['mean'])}")

    # Unavailable R² values are neither ranked nor counted as meaningful zeros.
    r2_values = pd.to_numeric(results_df["r2"], errors="raise")
    defined = results_df.loc[r2_values.notna() & np.isfinite(r2_values)].copy()
    defined["r2"] = r2_values.loc[defined.index].astype(float)

    # Distribution
    r2_bins = [
        ("R2 > 0.75 (good)", (defined["r2"] > 0.75).sum()),
        ("R2 0.50-0.75 (moderate)", ((defined["r2"] >= 0.50) & (defined["r2"] <= 0.75)).sum()),
        ("R2 < 0.50 (poor)", (defined["r2"] < 0.50).sum()),
        ("R2 unavailable", summary["r2"]["unavailable"]),
    ]
    print(f"\n  R2 Distribution:")
    for label, count in r2_bins:
        pct = count / len(results_df) * 100
        print(f"    {label}: {count} ({pct:.0f}%)")

    if defined.empty:
        print("\n  No districts have a defined R2; ranking unavailable.")
        return

    # Top 5
    print(f"\n  Top 5 districts by R2:")
    for _, row in defined.nlargest(5, "r2").iterrows():
        print(f"    {row['district_id']:>15s}: R2={row['r2']:.4f}  RMSE={row['rmse']:.4f}")

    # Bottom 5
    print(f"\n  Bottom 5 districts by R2:")
    for _, row in defined.nsmallest(5, "r2").iterrows():
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
