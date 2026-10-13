"""
AquaIQ — Preprocessing Pipeline (Causal, Leakage-Free & Physical Units)
-----------------------------------------------------------------------
Three-stage pipeline that cleans and regularizes raw district data:

  1. Reindex every district to continuous calendar monthly grid (2002-01-01 to 2024-12-01).
  2. Causal GWL Imputation (No Look-Ahead):
     - At observation month: observed depth in m bgl, is_imputed=False, months_since=0
     - Between quarterly monitoring rounds (<= 3 months): Last Observation Carried Forward (LOCF),
       is_imputed=True, months_since=k
     - Beyond 3 months: remains NaN (honest missingness, handled natively by XGBoost)
  3. Climate variables: physical units preserved (mm for rainfall & ET, °C for temperature).
     Physical units are preserved in preprocessed_wide.csv and database.
     MinMaxScaler is decoupled from DB and fitted strictly in modeling steps.

Run:
    python preprocessing/pipeline.py              # process all districts
    python preprocessing/pipeline.py --sample 10  # process 10 districts only
"""

import argparse
import hashlib
import json
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
START_DATE = str(pd.Timestamp(CONFIG["date_range"]["start"]).to_period("M").to_timestamp().date())
END_DATE = str(pd.Timestamp(CONFIG["date_range"]["end"]).to_period("M").to_timestamp().date())
FEATURE_ALGORITHM_VERSION = "physical-v3-causal-monthly"
# Maximum groundwater carry-forward age in calendar months.
MAX_LOCF_GAP = 3


def interpolate_gaps(series: pd.Series, max_gap: int = MAX_LOCF_GAP) -> pd.Series:
    """Fill short gaps from past values only; never use a future endpoint."""
    if series.isna().sum() == 0 or series.notna().sum() == 0:
        return series
    return series.replace([np.inf, -np.inf], np.nan).ffill(limit=max_gap)


def sarima_fill(series: pd.Series, seasonal_period: int = 12) -> pd.Series:
    """Legacy EDA helper: forward fill only, with leading gaps preserved."""
    if series.isna().sum() == 0:
        return series
    return series.ffill()


# ── Stage 1: Continuous Monthly Timeline ──────────────────────────────────────

def reindex_district_monthly(
    df: pd.DataFrame,
    start_date: str = START_DATE,
    end_date: str = END_DATE
) -> pd.DataFrame:
    """
    Reindex a single district's observations onto a complete monthly timeline.
    Ensures exactly one row per month from start_date to end_date.
    """
    if df.empty:
        return df

    district_id = df["district_id"].iloc[0]
    full_dates = pd.date_range(start_date, end_date, freq="MS")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    
    # Drop duplicates if any on (district_id, date)
    if df["date"].duplicated().any():
        raise ValueError("Duplicate district months must be aggregated before reindexing")
    df = df.sort_values("date")

    reindexed = (
        df.set_index("date")
        .reindex(full_dates)
        .rename_axis("date")
        .reset_index()
    )
    reindexed["district_id"] = district_id
    return reindexed


# ── Stage 2: Causal GWL Imputation (No Backward Leakage) ──────────────────────

def apply_causal_gwl_imputation(df: pd.DataFrame, max_locf_gap: int = MAX_LOCF_GAP) -> pd.DataFrame:
    """
    Apply strictly forward-looking (causal) imputation for groundwater levels.
    - Zero future look-ahead: future observations are never interpolated backward.
    - Raw observation: is_imputed = False, months_since_observation = 0.
    - For 1 to max_locf_gap months after observation: LOCF, is_imputed = True, months_since_observation = k.
    - Beyond max_locf_gap months: NaN, is_imputed = False, months_since_observation = k.
    """
    df = df.copy().sort_values("date").reset_index(drop=True)

    gwl_out = []
    is_imputed = []
    months_since = []

    last_observed_val = None
    gap_count = None
    observed = []

    for val in df["gwl"]:
        if pd.notna(val) and np.isfinite(float(val)):
            # Fresh observation
            last_observed_val = float(val)
            gap_count = 0
            gwl_out.append(last_observed_val)
            is_imputed.append(False)
            months_since.append(0)
            observed.append(True)
        else:
            gap_count = None if gap_count is None else gap_count + 1
            observed.append(False)
            if last_observed_val is not None and gap_count <= max_locf_gap:
                # Bounded LOCF between seasonal rounds
                gwl_out.append(last_observed_val)
                is_imputed.append(True)
                months_since.append(gap_count)
            else:
                # Gap exceeded threshold: honest missingness (NaN)
                gwl_out.append(np.nan)
                is_imputed.append(False)
                months_since.append(gap_count)

    df["gwl"] = gwl_out
    df["is_imputed"] = is_imputed
    df["is_observed"] = observed
    df["months_since_observation"] = pd.array(months_since, dtype="Int64")
    return df


# ── Stage 3: MinMaxScaler for Modeling (Decoupled from Storage) ───────────────

class TrainFitMinMaxScaler:
    """
    MinMaxScaler fitted ONLY on training period data (date <= train_end)
    to prevent temporal leakage during model training.
    Saves and loads scaling parameters from JSON.
    """

    def __init__(self):
        self.mins = {}
        self.maxs = {}
        self.columns = []

    def fit(self, df: pd.DataFrame, columns: list, train_end: str = "2019-12-31", date_col: str = "date"):
        """Fit scaler strictly on training window."""
        train_mask = pd.to_datetime(df[date_col]) <= pd.Timestamp(train_end)
        train_df = df[train_mask]

        self.columns = columns
        for col in columns:
            valid_vals = train_df[col].dropna()
            self.mins[col] = float(valid_vals.min()) if not valid_vals.empty else 0.0
            self.maxs[col] = float(valid_vals.max()) if not valid_vals.empty else 1.0
            if self.mins[col] == self.maxs[col]:
                self.maxs[col] = self.mins[col] + 1.0
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply min-max scaling [0, 1]."""
        result = df.copy()
        for col in self.columns:
            if col in result.columns:
                denom = self.maxs[col] - self.mins[col]
                result[col] = (result[col] - self.mins[col]) / denom
                result[col] = result[col].clip(0, 1)
        return result

    def fit_transform(self, df: pd.DataFrame, columns: list, train_end: str = "2019-12-31", date_col: str = "date") -> pd.DataFrame:
        self.fit(df, columns, train_end, date_col)
        return self.transform(df)

    def inverse_transform_value(self, column: str, value: float) -> float:
        """Inverse-transform a scaled value back to physical units."""
        if column not in self.mins:
            return value
        lo = self.mins[column]
        hi = self.maxs[column]
        return float(lo + value * (hi - lo))

    def save(self, path):
        import json
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({
                "columns": self.columns,
                "mins": self.mins,
                "maxs": self.maxs,
            }, f, indent=2)

    @classmethod
    def load(cls, path):
        import json
        scaler = cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        scaler.columns = data.get("columns", [])
        scaler.mins = data.get("mins", {})
        scaler.maxs = data.get("maxs", {})
        return scaler


# ── Full Pipeline Execution ───────────────────────────────────────────────────

def load_raw_data() -> pd.DataFrame:
    """Load raw_data from PostgreSQL."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""), connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT district_id, date, source, metric, value FROM raw_data ORDER BY district_id, date")
            df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    finally:
        conn.close()
    print(f"  Loaded {len(df):,} rows from PostgreSQL raw_data")
    return df


def pivot_raw_to_wide(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot raw_data (long format) to wide format:
    One row per (district_id, date) with columns for gwl, rainfall, temperature, evapotranspiration.
    """
    raw_df = raw_df.copy()
    raw_df["date"] = pd.to_datetime(raw_df["date"]).dt.to_period("M").dt.to_timestamp()
    raw_df["value"] = pd.to_numeric(raw_df["value"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    raw_df["key"] = raw_df["source"] + "_" + raw_df["metric"]

    pivoted = raw_df.pivot_table(
        index=["district_id", "date"],
        columns="key",
        values="value",
        aggfunc="mean",
    ).reset_index()

    pivoted.columns = [c if isinstance(c, str) else c for c in pivoted.columns]

    rename_map = {
        "CGWB_GWL": "gwl",
        "IMD_rainfall": "rainfall",
        "ERA5_temperature": "temperature",
        "ERA5_evapotranspiration": "evapotranspiration",
    }
    pivoted = pivoted.rename(columns=rename_map)
    for col in ["gwl", "rainfall", "temperature", "evapotranspiration"]:
        if col not in pivoted:
            pivoted[col] = np.nan
    return pivoted


def run_pipeline(df: pd.DataFrame, sample_districts: int = None, as_of=None) -> pd.DataFrame:
    """
    Run causal reindexing and bounded LOCF imputation.
    Preserves physical units across all metrics.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    end_date = min(pd.Timestamp(END_DATE), pd.Timestamp(as_of).to_period("M").to_timestamp()) if as_of else pd.Timestamp(END_DATE)
    df = df[df["date"].between(pd.Timestamp(START_DATE), end_date)]
    for col in ["gwl", "rainfall", "temperature", "evapotranspiration"]:
        if col not in df:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    districts = sorted(df["district_id"].unique())
    if sample_districts:
        districts = districts[:sample_districts]
        df = df[df["district_id"].isin(districts)]

    source_text = df.sort_values(["district_id", "date"]).to_csv(index=False, float_format="%.12g")
    generation = FEATURE_ALGORITHM_VERSION + "-" + hashlib.sha256(
        (source_text + START_DATE + str(end_date.date()) + str(MAX_LOCF_GAP)).encode()).hexdigest()[:12]
    print(f"\n  Processing {len(districts)} districts through {end_date.date()}...")

    filled_frames = []
    for i, district_id in enumerate(districts):
        district_df = df[df["district_id"] == district_id].copy()

        # 1. Reindex to complete monthly grid
        reindexed = reindex_district_monthly(district_df, START_DATE, str(end_date.date()))

        # 2. Causal bounded carry-forward for minor climate gaps
        for c in ["rainfall", "temperature", "evapotranspiration"]:
            if c in reindexed.columns:
                reindexed[c] = interpolate_gaps(reindexed[c], max_gap=2)

        # 3. Strictly causal bounded LOCF for groundwater depth
        imputed = apply_causal_gwl_imputation(reindexed, max_locf_gap=MAX_LOCF_GAP)
        filled_frames.append(imputed)

        if (i + 1) % 50 == 0 or i == len(districts) - 1:
            print(f"    Processed {i + 1}/{len(districts)} districts", end="\r")

    print()
    if not filled_frames:
        raise ValueError("No raw records in the configured preprocessing date range")
    result = pd.concat(filled_frames, ignore_index=True)
    result["feature_generation"] = generation

    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="AquaIQ Causal Preprocessing Pipeline")
    parser.add_argument("--sample", type=int, default=None, help="Process only N districts")
    parser.add_argument("--as-of", help="Only use records available through this calendar month")
    args = parser.parse_args(argv)
    if args.sample is not None and args.sample < 1:
        parser.error("--sample must be a positive district count")

    print("AquaIQ — Preprocessing Pipeline (Causal, Leakage-Free)")
    t0 = pd.Timestamp.now()

    print("[1/3] Loading raw data...")
    raw = load_raw_data()

    print("[2/3] Pivoting to wide format...")
    wide = pivot_raw_to_wide(raw)
    print(f"  Wide format: {len(wide):,} rows")

    print("[3/3] Running causal timeline regularization...")
    processed = run_pipeline(wide, sample_districts=args.sample, as_of=args.as_of)

    output_dir = ROOT / "reports" / "samples" if args.sample is not None else PROCESSED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "preprocessed_wide.csv"
    processed.to_csv(out_path, index=False)
    manifest = {
        "generation_id": processed["feature_generation"].iloc[0],
        "algorithm_version": FEATURE_ALGORITHM_VERSION,
        "units": {"gwl": "m_bgl", "rainfall": "mm/month", "temperature": "degC", "evapotranspiration": "mm/month"},
        "date_start": str(processed["date"].min().date()), "date_end": str(processed["date"].max().date()),
        "preprocessed_csv_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "causal_preprocessing": True, "gwl_locf_limit_months": MAX_LOCF_GAP,
        "climate_locf_limit_months": 2, "sample_only": args.sample is not None,
    }
    (output_dir / "preprocessed_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n  Saved {len(processed):,} physical-unit rows to {out_path}")

    # Summary
    print("\n  Physical Units Summary:")
    for col in ["gwl", "rainfall", "temperature", "evapotranspiration"]:
        if col in processed.columns:
            valid = processed[col].dropna()
            print(f"    {col:<20}: min={valid.min():.2f}, max={valid.max():.2f}, mean={valid.mean():.2f}, null={processed[col].isna().mean()*100:.1f}%")

    print("\nDone [OK]")


if __name__ == "__main__":
    main()
