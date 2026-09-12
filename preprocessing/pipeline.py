"""
AquaIQ — Preprocessing Pipeline (Week 4, Yasharth)
-----------------------------------------------------
Three-stage pipeline that cleans and normalizes raw data before
feature engineering:

  1. Linear interpolation — fills gaps <= 3 months
  2. SARIMA gap-fill — fills longer gaps using seasonal ARIMA
  3. MinMaxScaler — normalizes to [0, 1], fitted on train period only

Each function is independently callable and unit-testable.

Course mapping: AS202 (Python for Data Science), CS205 (Statistical Methods).

Run:
    python preprocessing/pipeline.py              # process all districts
    python preprocessing/pipeline.py --sample 10  # process 10 districts only
"""

import argparse
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]
TRAIN_END = pd.Timestamp(CONFIG["date_range"]["train_end"])

# Maximum gap (months) to fill with linear interpolation.
# Longer gaps use SARIMA instead.
MAX_LINEAR_GAP = 3


# ── Stage 1: Linear Interpolation ─────────────────────────────────────────

def interpolate_gaps(series: pd.Series, max_gap: int = MAX_LINEAR_GAP) -> pd.Series:
    """
    Fill short gaps (<= max_gap consecutive NaNs) with linear interpolation.
    Longer gaps are left as NaN for SARIMA to handle.
    """
    if series.isna().sum() == 0:
        return series

    # All NaN — nothing to interpolate from
    if series.notna().sum() == 0:
        return series

    result = series.copy()
    # Identify gap runs
    is_null = series.isna()
    gap_groups = (~is_null).cumsum()

    # For each gap, check if it's short enough for linear interp
    for _, group in series[is_null].groupby(gap_groups[is_null]):
        if len(group) <= max_gap:
            start_idx = max(0, group.index[0] - 1)
            end_idx = min(len(series) - 1, group.index[-1] + 1)
            segment = series.iloc[start_idx:end_idx + 1]
            interpolated = segment.interpolate(method="linear")
            result.iloc[group.index[0]:group.index[-1] + 1] = \
                interpolated.iloc[1:-1] if len(interpolated) > 2 else interpolated

    return result


# ── Stage 2: SARIMA Gap-Fill ──────────────────────────────────────────────

def sarima_fill(series: pd.Series, seasonal_period: int = 12) -> pd.Series:
    """
    Fill remaining NaN gaps using SARIMA(1,1,1)(1,1,1,12).
    Falls back to forward-fill if SARIMA fails to converge.
    
    Only attempts SARIMA if the series has enough non-NaN values
    to fit a seasonal model (>= 2 * seasonal_period).
    """
    if series.isna().sum() == 0:
        return series

    result = series.copy()
    non_null_count = series.notna().sum()

    # Need enough data for seasonal model
    if non_null_count < 2 * seasonal_period:
        # Not enough data — fall back to forward-fill then back-fill
        result = result.ffill().bfill()
        return result

    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        # Fit on the non-NaN portion
        train_series = series.dropna()
        model = SARIMAX(
            train_series,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, seasonal_period),
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = model.fit(disp=False, maxiter=50)

        # Predict for the full index
        predicted = fit.predict(start=0, end=len(series) - 1)

        # Only fill where original is NaN
        null_mask = series.isna()
        if len(predicted) == len(result):
            result[null_mask] = predicted[null_mask]
        else:
            # Index mismatch — fall back
            result = result.ffill().bfill()

    except Exception:
        # SARIMA failed — fall back to forward/back fill
        result = result.ffill().bfill()

    return result


# ── Stage 3: MinMaxScaler ─────────────────────────────────────────────────

class TrainFitMinMaxScaler:
    """
    MinMaxScaler fitted ONLY on the training period (pre-2020) to prevent
    data leakage. The same min/max values are then applied to val/test.
    """

    def __init__(self):
        self.mins = {}
        self.maxs = {}
        self.columns = []

    def fit(self, df: pd.DataFrame, columns: list, date_col: str = "date"):
        """Fit on training data only (date <= TRAIN_END)."""
        train_mask = pd.to_datetime(df[date_col]) <= TRAIN_END
        train_df = df[train_mask]

        self.columns = columns
        for col in columns:
            self.mins[col] = train_df[col].min()
            self.maxs[col] = train_df[col].max()
            # Avoid division by zero
            if self.mins[col] == self.maxs[col]:
                self.maxs[col] = self.mins[col] + 1

        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply min-max scaling using training-period statistics."""
        result = df.copy()
        for col in self.columns:
            if col in result.columns:
                result[col] = (result[col] - self.mins[col]) / (self.maxs[col] - self.mins[col])
                result[col] = result[col].clip(0, 1)
        return result

    def fit_transform(self, df: pd.DataFrame, columns: list, date_col: str = "date") -> pd.DataFrame:
        self.fit(df, columns, date_col)
        return self.transform(df)


# ── Full Pipeline ─────────────────────────────────────────────────────────

def load_raw_data() -> pd.DataFrame:
    """Load raw_data from PostgreSQL or CSV fallback."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "aquaiq"),
            user=os.getenv("POSTGRES_USER", "aquaiq_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
        )
        df = pd.read_sql(
            "SELECT district_id, date, source, metric, value FROM raw_data ORDER BY district_id, date",
            conn,
        )
        conn.close()
        if len(df) > 0:
            print(f"  Loaded {len(df):,} rows from PostgreSQL raw_data")
            return df
    except Exception as e:
        print(f"  PostgreSQL unavailable ({e}), trying CSV fallback...")

    # CSV fallback — load CGWB directly
    cgwb_path = ROOT / CONFIG["paths"]["data_raw"] / "cgwb_combined.csv"
    if cgwb_path.exists():
        print(f"  Loading from {cgwb_path.name} (CSV fallback)...")
        raw = pd.read_csv(cgwb_path, dtype=str, low_memory=False)
        raw["currentlevel"] = pd.to_numeric(raw["currentlevel"], errors="coerce")
        raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
        raw = raw.dropna(subset=["currentlevel", "date", "district_code"])
        raw["month_date"] = raw["date"].dt.to_period("M").dt.to_timestamp()

        # Aggregate to district-monthly
        agg = raw.groupby(["district_code", "month_date"])["currentlevel"].mean().reset_index()
        agg.columns = ["district_id", "date", "value"]
        agg["source"] = "CGWB"
        agg["metric"] = "GWL"
        print(f"  Built {len(agg):,} district-month rows from CSV")
        return agg

    print("ERROR: No data source available.")
    sys.exit(1)


def pivot_raw_to_wide(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot raw_data (long format) to wide format:
    One row per (district_id, date) with columns for GWL, rainfall, temp, ET.
    """
    raw_df["date"] = pd.to_datetime(raw_df["date"])

    # Create a source_metric key
    raw_df["key"] = raw_df["source"] + "_" + raw_df["metric"]

    pivoted = raw_df.pivot_table(
        index=["district_id", "date"],
        columns="key",
        values="value",
        aggfunc="mean",
    ).reset_index()

    # Flatten column names
    pivoted.columns = [c if isinstance(c, str) else c for c in pivoted.columns]

    # Rename to standard names
    rename_map = {
        "CGWB_GWL": "gwl",
        "IMD_rainfall": "rainfall",
        "ERA5_temperature": "temperature",
        "ERA5_evapotranspiration": "evapotranspiration",
    }
    pivoted = pivoted.rename(columns=rename_map)

    return pivoted


def run_pipeline(df: pd.DataFrame, sample_districts: int = None) -> pd.DataFrame:
    """
    Run the full 3-stage pipeline on the wide-format data.
    Returns a cleaned, gap-filled, normalized DataFrame.
    """
    districts = df["district_id"].unique()
    if sample_districts:
        districts = districts[:sample_districts]
        df = df[df["district_id"].isin(districts)]

    print(f"\n  Processing {len(districts)} districts...")

    numeric_cols = [c for c in ["gwl", "rainfall", "temperature", "evapotranspiration"]
                    if c in df.columns]

    # Stage 1 & 2: Per-district gap filling
    filled_frames = []
    for i, district_id in enumerate(districts):
        district_df = df[df["district_id"] == district_id].copy()
        district_df = district_df.sort_values("date")

        for col in numeric_cols:
            if col in district_df.columns:
                # Stage 1: linear interpolation for short gaps
                district_df[col] = interpolate_gaps(district_df[col].reset_index(drop=True))
                # Stage 2: SARIMA for remaining gaps
                district_df[col] = sarima_fill(district_df[col].reset_index(drop=True))

        filled_frames.append(district_df)

        if (i + 1) % 50 == 0 or i == len(districts) - 1:
            print(f"    Gap-filled {i + 1}/{len(districts)} districts", end="\r")

    print()
    result = pd.concat(filled_frames, ignore_index=True)

    # Stage 3: MinMaxScaler (fit on train period only)
    scaler = TrainFitMinMaxScaler()
    scale_cols = [c for c in numeric_cols if c in result.columns]
    if scale_cols:
        result = scaler.fit_transform(result, scale_cols)
        print(f"  MinMaxScaler fitted on train period (<= {TRAIN_END.date()})")

    return result


def main():
    parser = argparse.ArgumentParser(description="AquaIQ Preprocessing Pipeline")
    parser.add_argument("--sample", type=int, default=None,
                        help="Process only N districts (for testing)")
    args = parser.parse_args()

    print("AquaIQ -- Preprocessing Pipeline\n")

    # Load
    print("[1/3] Loading raw data...")
    raw = load_raw_data()

    # Pivot
    print("[2/3] Pivoting to wide format...")
    wide = pivot_raw_to_wide(raw)
    print(f"  Wide format: {len(wide):,} rows, columns: {list(wide.columns)}")

    # Pipeline
    print("[3/3] Running pipeline (interpolation + SARIMA + MinMaxScaler)...")
    processed = run_pipeline(wide, sample_districts=args.sample)

    # Save
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out_path = PROCESSED_DIR / "preprocessed_wide.csv"
    processed.to_csv(out_path, index=False)
    print(f"\n  Saved {len(processed):,} rows to {out_path}")

    # Summary stats
    print("\n  Summary:")
    for col in ["gwl", "rainfall", "temperature", "evapotranspiration"]:
        if col in processed.columns:
            null_pct = processed[col].isna().mean() * 100
            print(f"    {col:25s}: {null_pct:.1f}% missing after gap-fill")

    print("\nDone.")


if __name__ == "__main__":
    main()
