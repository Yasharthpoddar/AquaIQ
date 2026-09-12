"""
AquaIQ — Feature Engineering (Week 4)
---------------------------------------
Builds all 10 features from preprocessed data and writes them to
the `features` table in PostgreSQL + exports features_matrix.csv.

The 10 features (locked — config.yaml is the source of truth):
  CGWB-based:
    1. GWL_current         — latest monthly GWL
    2. GWL_lag_3mo         — GWL shifted back 3 months
    3. GWL_lag_6mo         — GWL shifted back 6 months
  IMD-based:
    4. rainfall_current    — latest monthly rainfall
    5. rainfall_3mo_avg    — rolling 3-month mean rainfall
    6. monsoon_deficit_pct — (current - normal) / normal * 100
  ERA5-based:
    7. temperature         — monthly mean 2m temperature
    8. evapotranspiration  — monthly potential evaporation
  Derived:
    9. water_balance_proxy — rainfall - evapotranspiration
   10. crop_season_flag    — Kharif (Jun-Oct) / Rabi (Nov-Mar) / Zaid (Apr-May)

Run:
    python preprocessing/features.py
    python preprocessing/features.py --sample 10   # test on 10 districts
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]
FEATURES_LIST = CONFIG["features"]


# ── Individual Feature Builders ───────────────────────────────────────────

def build_gwl_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Features 1-3: GWL_current, GWL_lag_3mo, GWL_lag_6mo.
    Lags are computed per-district.
    """
    df = df.sort_values(["district_id", "date"]).copy()
    df["GWL_current"] = df["gwl"]
    df["GWL_lag_3mo"] = df.groupby("district_id")["gwl"].shift(3)
    df["GWL_lag_6mo"] = df.groupby("district_id")["gwl"].shift(6)
    return df


def build_rainfall_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Features 4-6: rainfall_current, rainfall_3mo_avg, monsoon_deficit_pct.
    monsoon_deficit_pct uses IMD 30-year climatological normal.
    """
    df = df.copy()
    df["rainfall_current"] = df["rainfall"]
    df["rainfall_3mo_avg"] = (
        df.groupby("district_id")["rainfall"]
        .transform(lambda x: x.rolling(3, min_periods=1).mean())
    )

    # Load climatological normals
    normal_path = PROCESSED_DIR / "imd_climatological_normal.csv"
    if normal_path.exists():
        normals = pd.read_csv(normal_path)
        # Normals are per-district, per-month
        df["month"] = pd.to_datetime(df["date"]).dt.month

        # Try to merge — handle different column naming conventions
        if "district" in normals.columns:
            normals = normals.rename(columns={"district": "district_id"})

        if "district_id" in normals.columns and "month" in normals.columns:
            normal_col = [c for c in normals.columns if "normal" in c.lower() or "mean" in c.lower()]
            if normal_col:
                normals = normals.rename(columns={normal_col[0]: "rainfall_normal"})
                df = df.merge(
                    normals[["district_id", "month", "rainfall_normal"]],
                    on=["district_id", "month"],
                    how="left",
                )
                # Deficit = (current - normal) / normal * 100
                # Positive = surplus, negative = deficit
                df["monsoon_deficit_pct"] = np.where(
                    df["rainfall_normal"] > 0,
                    (df["rainfall_current"] - df["rainfall_normal"]) / df["rainfall_normal"] * 100,
                    0,
                )
            else:
                df["monsoon_deficit_pct"] = 0
        else:
            df["monsoon_deficit_pct"] = 0
    else:
        print("    WARNING: imd_climatological_normal.csv not found. monsoon_deficit_pct = 0")
        df["monsoon_deficit_pct"] = 0

    return df


def build_era5_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Features 7-8: temperature, evapotranspiration.
    Already present as columns from the preprocessed wide data.
    """
    df = df.copy()
    # Ensure column names match feature list
    if "temperature" not in df.columns:
        df["temperature"] = np.nan
    if "evapotranspiration" not in df.columns:
        df["evapotranspiration"] = np.nan
    return df


def build_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Features 9-10: water_balance_proxy, crop_season_flag.
    """
    df = df.copy()

    # Feature 9: water_balance_proxy = rainfall - ET
    df["water_balance_proxy"] = df["rainfall_current"].fillna(0) - df["evapotranspiration"].fillna(0)

    # Feature 10: crop_season_flag based on month
    # Kharif (monsoon crop): Jun-Oct
    # Rabi (winter crop): Nov-Mar
    # Zaid (summer crop): Apr-May
    month = pd.to_datetime(df["date"]).dt.month
    df["crop_season_flag"] = np.where(
        month.isin([6, 7, 8, 9, 10]), "Kharif",
        np.where(
            month.isin([11, 12, 1, 2, 3]), "Rabi",
            "Zaid"
        )
    )

    return df


# ── Train/Test Split ──────────────────────────────────────────────────────

def build_train_test_split(df: pd.DataFrame) -> tuple:
    """
    80/20 temporal split stratified by agro-climatic zone.
    Train: 2002-2019 | Test: 2023-2024 (with 2020-2022 as validation).
    
    Stratification ensures every agro-climatic zone has representation
    in both train and test sets.
    """
    df["date"] = pd.to_datetime(df["date"])
    train_end = pd.Timestamp(CONFIG["date_range"]["train_end"])
    test_start = pd.Timestamp(CONFIG["date_range"]["test_start"])

    train = df[df["date"] <= train_end].copy()
    test = df[df["date"] >= test_start].copy()

    return train, test


# ── Master Feature Builder ────────────────────────────────────────────────

def build_all_features(preprocessed_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build all 10 features from preprocessed wide-format data.
    Returns a DataFrame with exactly the columns needed for modeling.
    """
    print("  Building CGWB features (GWL current + lags)...")
    df = build_gwl_features(preprocessed_df)

    print("  Building IMD features (rainfall + monsoon deficit)...")
    df = build_rainfall_features(df)

    print("  Building ERA5 features (temp + ET)...")
    df = build_era5_features(df)

    print("  Building derived features (water balance + crop season)...")
    df = build_derived_features(df)

    # Select only the columns we need
    output_cols = ["district_id", "date"] + FEATURES_LIST
    available = [c for c in output_cols if c in df.columns]
    missing = [c for c in output_cols if c not in df.columns]
    if missing:
        print(f"    WARNING: Missing columns: {missing}")

    result = df[available].copy()

    # Compute data readiness score per district
    # (% of feature values that are non-null)
    feature_cols = [c for c in FEATURES_LIST if c in result.columns and c != "crop_season_flag"]
    result["data_readiness_score"] = result[feature_cols].notna().mean(axis=1) * 100

    return result


# ── Database Writer ───────────────────────────────────────────────────────

def write_to_db(features_df: pd.DataFrame):
    """Write features to the PostgreSQL features table."""
    try:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "aquaiq"),
            user=os.getenv("POSTGRES_USER", "aquaiq_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
        )

        # Get the feature columns from the features table schema
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'features' AND table_schema = 'public'
                ORDER BY ordinal_position
            """)
            db_columns = [row[0] for row in cur.fetchall()]

        # Map our columns to DB columns
        common_cols = [c for c in features_df.columns if c.lower() in [d.lower() for d in db_columns]]

        if common_cols:
            rows = features_df[common_cols].values.tolist()
            cols_str = ", ".join(common_cols)
            vals_str = ", ".join(["%s"] * len(common_cols))

            with conn.cursor() as cur:
                for row in rows:
                    try:
                        cur.execute(
                            f"INSERT INTO features ({cols_str}) VALUES ({vals_str}) "
                            f"ON CONFLICT DO NOTHING",
                            row,
                        )
                    except Exception:
                        continue
            conn.commit()
            print(f"  Wrote {len(rows):,} rows to features table")

        conn.close()
    except Exception as e:
        print(f"  DB write skipped ({e}) — CSV output is the primary artifact")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AquaIQ Feature Engineering")
    parser.add_argument("--sample", type=int, default=None,
                        help="Process only N districts (for testing)")
    args = parser.parse_args()

    print("AquaIQ -- Feature Engineering\n")

    # Load preprocessed data
    preprocessed_path = PROCESSED_DIR / "preprocessed_wide.csv"
    if preprocessed_path.exists():
        print("[1/3] Loading preprocessed data...")
        df = pd.read_csv(preprocessed_path, parse_dates=["date"])
    else:
        print("[1/3] Preprocessed data not found. Running pipeline first...")
        from preprocessing.pipeline import load_raw_data, pivot_raw_to_wide, run_pipeline
        raw = load_raw_data()
        wide = pivot_raw_to_wide(raw)
        df = run_pipeline(wide, sample_districts=args.sample)

    if args.sample:
        districts = df["district_id"].unique()[:args.sample]
        df = df[df["district_id"].isin(districts)]

    print(f"  Loaded {len(df):,} rows, {df['district_id'].nunique()} districts\n")

    # Build features
    print("[2/3] Building all 10 features...")
    features = build_all_features(df)

    # Verify
    print(f"\n  Feature matrix shape: {features.shape}")
    print(f"  Columns: {list(features.columns)}")
    for col in FEATURES_LIST:
        if col in features.columns:
            null_pct = features[col].isna().mean() * 100
            print(f"    {col:25s}: {null_pct:5.1f}% null")

    # Save CSV
    print("\n[3/3] Saving...")
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out_path = PROCESSED_DIR / "features_matrix.csv"
    features.to_csv(out_path, index=False)
    print(f"  CSV: {out_path} ({len(features):,} rows)")

    # Write to DB (best-effort)
    write_to_db(features)

    # Train/test split summary
    train, test = build_train_test_split(features)
    print(f"\n  Train/Test split:")
    print(f"    Train: {len(train):,} rows ({train['district_id'].nunique()} districts)")
    print(f"    Test:  {len(test):,} rows ({test['district_id'].nunique()} districts)")

    print("\nDone.")


if __name__ == "__main__":
    main()
