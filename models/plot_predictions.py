"""
AquaIQ — Predicted vs Actual GWL Plots (Week 5, Ayush)
---------------------------------------------------------
Plots predicted vs actual GWL for 5 representative districts:
  Punjab, Rajasthan, Maharashtra, Tamil Nadu, Uttar Pradesh

Uses the Linear Regression model output. Saves plots to data/processed/.

Run:
    python models/plot_predictions.py
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv

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

# Target states — pick the largest district per state
TARGET_STATES = ["Punjab", "Rajasthan", "Maharashtra", "Tamil Nadu", "Uttar Pradesh"]


def load_data():
    """Plot explicitly observed depths from the verified physical generation."""
    frame = forecast.load_feature_matrix()
    values = pd.to_numeric(frame.gwl_current, errors='coerce')
    frame = frame.loc[forecast.observed_mask(frame) & np.isfinite(values) & (values >= 0)].copy()
    frame['GWL_current'] = frame.gwl_current
    return frame


def pick_representative_districts(df: pd.DataFrame) -> dict:
    """Pick one district per target state with the most data."""
    state_col = None
    for col in ["state", "state_name"]:
        if col in df.columns:
            state_col = col
            break

    if state_col is None:
        # Try to infer state from district_id
        print("  No state column — using first 5 districts with most data")
        counts = df.groupby("district_id").size().nlargest(5)
        return {did: did for did in counts.index}

    selected = {}
    for state in TARGET_STATES:
        state_df = df[df[state_col].str.contains(state, case=False, na=False)]
        if len(state_df) == 0:
            continue
        # Pick district with most observations
        counts = state_df.groupby("district_id").size()
        best = counts.idxmax()
        selected[state] = best

    if not selected:
        # Fallback: just pick top-5 by data volume
        counts = df.groupby("district_id").size().nlargest(5)
        selected = {f"District_{i}": did for i, did in enumerate(counts.index)}

    return selected


def plot_district(df: pd.DataFrame, district_id: str, state_name: str, ax):
    """Plot actual vs predicted for one district."""
    from sklearn.linear_model import LinearRegression

    ddf = df[df["district_id"] == district_id].sort_values("date").copy()

    if "GWL_current" not in ddf.columns:
        return

    # Simple time-based regression
    month_number = ddf.date.dt.year * 12 + ddf.date.dt.month
    ddf["time_idx"] = month_number - month_number.min()
    ddf = ddf.dropna(subset=["GWL_current"])

    train = ddf[ddf["date"] <= TRAIN_END]
    all_data = ddf

    if len(train) < 6:
        ax.text(0.5, 0.5, f"Insufficient data\n({len(train)} points)",
                transform=ax.transAxes, ha="center", va="center")
        ax.set_title(f"{state_name}: {district_id}")
        return

    model = LinearRegression()
    model.fit(train[["time_idx"]], train["GWL_current"])
    all_data["predicted"] = model.predict(all_data[["time_idx"]])

    # Plot
    ax.plot(all_data["date"], all_data["GWL_current"], "b-", label="Actual", linewidth=1.5)
    ax.plot(all_data["date"], all_data["predicted"], "r--", label="Predicted", linewidth=1.5)

    # Mark train/test boundary
    ax.axvline(x=TRAIN_END, color="gray", linestyle=":", alpha=0.7, label="Train/Test split")

    ax.set_title(f"{state_name}", fontsize=11, fontweight="bold")
    ax.set_ylabel("GWL (m bgl)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print("AquaIQ -- Predicted vs Actual GWL Plots\n")

    print("[1/3] Loading data...")
    df = load_data()
    print(f"  {len(df):,} rows, {df['district_id'].nunique()} districts")

    print("\n[2/3] Selecting representative districts...")
    selected = pick_representative_districts(df)
    for state, did in selected.items():
        n = len(df[df["district_id"] == did])
        print(f"  {state}: {did} ({n} months)")

    print("\n[3/3] Plotting...")
    n_plots = len(selected)
    fig, axes = plt.subplots(n_plots, 1, figsize=(12, 4 * n_plots))
    if n_plots == 1:
        axes = [axes]

    for ax, (state, did) in zip(axes, selected.items()):
        plot_district(df, did, state, ax)

    plt.tight_layout()
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out_path = PROCESSED_DIR / "predicted_vs_actual_gwl.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  Saved plot to {out_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
