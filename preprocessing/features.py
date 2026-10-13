"""
AquaIQ — Feature Engineering (Week 4, Refactored for Physical Units & Canonical IDs)
-------------------------------------------------------------------------------------
Builds all 10 features from preprocessed physical-unit data and writes them to
the `features` table in PostgreSQL + exports features_matrix.csv.

The 10 features (locked — config.yaml is the source of truth):
  CGWB-based:
    1. GWL_current         — latest monthly GWL (m bgl)
    2. GWL_lag_3mo         — GWL shifted back 3 months (m bgl)
    3. GWL_lag_6mo         — GWL shifted back 6 months (m bgl)
  IMD-based:
    4. rainfall_current    — latest monthly rainfall (mm)
    5. rainfall_3mo_avg    — rolling 3-month mean rainfall (mm)
    6. monsoon_deficit_pct — (current_mm - normal_mm) / normal_mm * 100
  ERA5-based:
    7. temperature         — monthly mean 2m temperature (°C)
    8. evapotranspiration  — monthly potential evaporation (mm)
  Derived:
    9. water_balance_proxy — rainfall - evapotranspiration (mm)
   10. crop_season_flag    — Kharif (Jun-Oct) / Rabi (Nov-Mar) / Zaid (Apr-May)

Run:
    python preprocessing/features.py
    python preprocessing/features.py --sample 10   # test on 10 districts
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]
FEATURES_LIST = CONFIG["features"]


# ── Individual Feature Builders ───────────────────────────────────────────

def build_gwl_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Features 1-3: GWL_current, GWL_lag_3mo, GWL_lag_6mo.
    Lags are computed per canonical district on continuous monthly timeline.
    Preserves physical depth in metres below ground level.
    """
    df = df.sort_values(["district_id", "date"]).copy()
    df["GWL_current"] = df["gwl"]
    df["date"] = pd.to_datetime(df["date"])
    if df.duplicated(["district_id", "date"]).any():
        raise ValueError("Feature input contains duplicate district months")
    for lag in (3, 6):
        history = df[["district_id", "date", "gwl"]].copy()
        history["date"] = history["date"] + pd.DateOffset(months=lag)
        df = df.merge(history.rename(columns={"gwl": f"GWL_lag_{lag}mo"}),
                      on=["district_id", "date"], how="left", validate="one_to_one")
    return df


def _load_district_name_map() -> pd.DataFrame:
    """Load canonical district_id → (district_name, state) mapping from PostgreSQL."""
    try:
        from db.connection import get_connection, read_frame
        conn = get_connection()
        try:
            return read_frame("SELECT district_id, district_name, state FROM districts", conn)
        finally:
            conn.close()
    except Exception:
        crosswalk_path = ROOT / "data_ingestion" / "district_crosswalk.csv"
        if crosswalk_path.exists():
            cw = pd.read_csv(crosswalk_path)
            return cw[["canonical_district_id", "canonical_name", "canonical_state"]].rename(
                columns={
                    "canonical_district_id": "district_id",
                    "canonical_name": "district_name",
                    "canonical_state": "state",
                }
            ).drop_duplicates()
        return pd.DataFrame(columns=["district_id", "district_name", "state"])


def build_rainfall_features(df: pd.DataFrame, rainfall_history=None) -> pd.DataFrame:
    """
    Features 4-6: rainfall_current, rainfall_3mo_avg, monsoon_deficit_pct.
    monsoon_deficit_pct compares current physical mm against the mean of
    available prior years for the same calendar month (at least three years):
        monsoon_deficit_pct = (current_mm - normal_mm) / normal_mm * 100
    """
    df = df.sort_values(["district_id", "date"]).copy()
    df["rainfall_current"] = df["rainfall"]
    df["rainfall_3mo_avg"] = (
        df.groupby("district_id")["rainfall"]
        .transform(lambda x: x.rolling(3, min_periods=1).mean())
    )

    # An all-years climatology leaks future rainfall into historical forecast
    # origins. Each row uses this district's *previous years* for the same month.
    # No normal or a zero normal means unavailable anomaly, not a neutral zero.
    df["month"] = pd.to_datetime(df["date"]).dt.month
    normal_source = df[["district_id", "date", "rainfall"]].copy()
    if rainfall_history is not None and not rainfall_history.empty:
        earlier = rainfall_history.copy()
        earlier["date"] = pd.to_datetime(earlier["date"])
        earlier = earlier[earlier["date"] < df["date"].min()]
        normal_source = pd.concat([earlier[["district_id", "date", "rainfall"]], normal_source], ignore_index=True)
    normal_source = normal_source.sort_values(["district_id", "date"])
    if normal_source.duplicated(["district_id", "date"]).any():
        raise ValueError("Rainfall normal source contains duplicate district months")
    normal_source["month"] = normal_source["date"].dt.month
    grouping = normal_source.groupby(["district_id", "month"])["rainfall"]
    normal_source["rainfall_normal"] = grouping.transform(lambda s: s.shift(1).expanding(min_periods=3).mean())
    normal_source["rainfall_normal_n_years"] = grouping.transform(lambda s: s.shift(1).expanding().count()).astype("Int64")
    df = df.merge(normal_source[["district_id", "date", "rainfall_normal", "rainfall_normal_n_years"]],
                  on=["district_id", "date"], how="left", validate="one_to_one")
    df["monsoon_deficit_pct"] = (
        (df["rainfall_current"] - df["rainfall_normal"]) / df["rainfall_normal"].where(df["rainfall_normal"] > 0) * 100.0
    )

    return df


def build_era5_features(df: pd.DataFrame) -> pd.DataFrame:
    """Features 7-8: temperature (°C), evapotranspiration (mm/month)."""
    df = df.copy()
    if "temperature" not in df.columns:
        df["temperature"] = np.nan
    if "evapotranspiration" not in df.columns:
        df["evapotranspiration"] = np.nan
    return df


def build_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Features 9-10: water_balance_proxy (mm), crop_season_flag.
    """
    df = df.copy()

    # Feature 9: water_balance_proxy = rainfall - ET (physical mm)
    df["water_balance_proxy"] = df["rainfall_current"] - df["evapotranspiration"]

    # Feature 10: crop_season_flag based on month
    # Kharif: Jun-Oct | Rabi: Nov-Mar | Zaid: Apr-May
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
    Temporal split based on config.yaml boundaries.
    Train: 2002-2019 | Test: 2020-2021 (with meaningful observations).
    """
    df["date"] = pd.to_datetime(df["date"])
    train_end = pd.Timestamp(CONFIG["date_range"]["train_end"])
    test_start = pd.Timestamp(CONFIG["date_range"].get("test_start", "2020-01-01"))

    train = df[df["date"] <= train_end].copy()
    test = df[df["date"] >= test_start].copy()
    return train, test


# ── Column name mapping ───────────────────────────────────────────────────
DB_COLUMN_MAP = {
    "GWL_current": "gwl_current",
    "GWL_lag_3mo": "gwl_lag_3mo",
    "GWL_lag_6mo": "gwl_lag_6mo",
}


# ── Master Feature Builder ────────────────────────────────────────────────

def build_all_features(preprocessed_df: pd.DataFrame, rainfall_history=None) -> pd.DataFrame:
    """
    Build all 10 features from preprocessed wide-format data.
    """
    required = {"is_observed", "is_imputed", "months_since_observation", "feature_generation"}
    if not required.issubset(preprocessed_df.columns):
        raise ValueError("Unknown observation provenance; regenerate preprocessing before features")
    if preprocessed_df["feature_generation"].nunique() != 1:
        raise ValueError("Mixed feature generations are forbidden")
    for flag in ("is_observed", "is_imputed"):
        if not preprocessed_df[flag].isin([True, False]).all():
            raise ValueError(f"Missing/invalid {flag} observation provenance")
    if (preprocessed_df["is_observed"] & preprocessed_df["is_imputed"]).any():
        raise ValueError("An observation cannot also be an imputation")
    finite_gwl = np.isfinite(pd.to_numeric(preprocessed_df["gwl"], errors="coerce"))
    if (finite_gwl != (preprocessed_df["is_observed"] | preprocessed_df["is_imputed"])).any():
        raise ValueError("Finite groundwater has inconsistent observation/imputation provenance")
    print("  Building CGWB features (GWL current + lags in m bgl)...")
    df = build_gwl_features(preprocessed_df)

    print("  Building IMD features (rainfall + physical monsoon deficit in mm)...")
    df = build_rainfall_features(df, rainfall_history=rainfall_history)
    # Historical climate inputs participate in the generation fingerprint.
    if rainfall_history is not None and not rainfall_history.empty:
        fingerprint = str(df["feature_generation"].iloc[0]) + rainfall_history.sort_values(["district_id", "date"]).to_csv(index=False, float_format="%.12g")
        df["feature_generation"] = "physical-v3-causal-monthly-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12]

    print("  Building ERA5 features (temp + ET in mm)...")
    df = build_era5_features(df)

    print("  Building derived features (water balance + crop season)...")
    df = build_derived_features(df)

    # Add lowercase aliases for DB compatibility
    for config_name, db_name in DB_COLUMN_MAP.items():
        if config_name in df.columns:
            df[db_name] = df[config_name]

    # Select output columns
    output_cols = ["district_id", "date"] + FEATURES_LIST + sorted(required)
    available = [c for c in output_cols if c in df.columns]
    result = df[available].copy()
    numeric = result.select_dtypes(include="number").columns
    result[numeric] = result[numeric].replace([np.inf, -np.inf], np.nan)

    for config_name, db_name in DB_COLUMN_MAP.items():
        if config_name in result.columns:
            result[db_name] = result[config_name]

    # Compute data readiness score per district
    feature_cols = [c for c in FEATURES_LIST if c in result.columns and c != "crop_season_flag"]
    result["data_readiness_score"] = result[feature_cols].notna().mean(axis=1) * 100.0

    return result


def load_prior_rainfall_history():
    """Load verified pre-start IMD years for historically available normals."""
    path = PROCESSED_DIR / "imd_rainfall_district_monthly.csv"
    if not path.exists():
        return None
    from data_ingestion.ingest_imd_era5 import validate_weather_artifact, norm_str, norm_state
    validate_weather_artifact(path, {"rainfall_mm": "mm/month"})
    history = pd.read_csv(path)
    history["date"] = pd.to_datetime(dict(year=history["year"], month=history["month"], day=1))
    history = history[history["date"] < pd.Timestamp(CONFIG["date_range"]["start"])].copy()
    if history.empty:
        return None
    dmap = _load_district_name_map()
    history["d_clean"] = history["district"].map(norm_str)
    history["s_clean"] = history["st_nm"].map(norm_state)
    dmap["d_clean"] = dmap["district_name"].map(norm_str)
    dmap["s_clean"] = dmap["state"].map(norm_state)
    dmap = dmap[["district_id", "d_clean", "s_clean"]].drop_duplicates()
    if dmap.duplicated(["d_clean", "s_clean"]).any():
        raise ValueError("Ambiguous canonical rainfall history lookup")
    history = history.merge(dmap[["district_id", "d_clean", "s_clean"]], on=["d_clean", "s_clean"],
                            how="inner", validate="many_to_one")
    return history[["district_id", "date", "rainfall_mm"]].rename(columns={"rainfall_mm": "rainfall"})


# ── Database Writer (Zero Stored NaNs) ─────────────────────────────────────

def write_to_db(features_df: pd.DataFrame):
    """Atomically replace the derived generation; never leave stale unit mixtures.

    Call only for a full rebuild. The old rows survive any validation/insert
    failure through transaction rollback. Raw observations are never changed.
    """
    import psycopg2.extras
    from db.connection import get_connection
    cols = ["district_id", "date", "gwl_current", "gwl_lag_3mo", "gwl_lag_6mo",
            "rainfall_current", "rainfall_3mo_avg", "monsoon_deficit_pct", "temperature",
            "evapotranspiration", "water_balance_proxy", "crop_season_flag", "data_readiness_score",
            "is_observed", "is_imputed", "months_since_observation", "feature_generation"]
    if features_df.empty or features_df["feature_generation"].nunique() != 1:
        raise ValueError("A nonempty, single feature generation is required")
    if features_df.duplicated(["district_id", "date"]).any():
        raise ValueError("Duplicate feature keys")
    if features_df["date"].min() < pd.Timestamp(CONFIG["date_range"]["start"]):
        raise ValueError("Feature generation extends before the configured physical-unit range")
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT district_id FROM districts")
                valid_ids = {row[0] for row in cur.fetchall()}
                unknown = set(features_df["district_id"]) - valid_ids
                if unknown:
                    raise ValueError(f"Unknown canonical districts: {sorted(unknown)}")
                records = []
                for row in features_df[cols].itertuples(index=False, name=None):
                    records.append(tuple(None if pd.isna(value) or isinstance(value, (int, float, np.number)) and not np.isfinite(value)
                                         else value.item() if isinstance(value, np.generic) else value for value in row))
                cur.execute("DELETE FROM features")
                psycopg2.extras.execute_values(cur, f"INSERT INTO features ({', '.join(cols)}) VALUES %s", records, page_size=5000)
        print(f"  Atomically replaced features with {len(records):,} physical-unit rows")
    finally:
        conn.close()


# ── Main ──────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description="AquaIQ Feature Engineering")
    parser.add_argument("--sample", type=int, default=None, help="Process only N districts")
    parser.add_argument("--csv-only", action="store_true", help="Build isolated candidate artifacts without replacing the database")
    parser.add_argument("--input-dir", type=Path, default=None, help="Directory containing verified preprocessing artifacts (default: production processed directory)")
    args = parser.parse_args(argv)
    if args.sample is not None and args.sample < 1:
        parser.error("--sample must be a positive district count")

    print("AquaIQ — Feature Engineering (Physical Units & Zero-NaN Storage)\n")

    input_dir = args.input_dir or PROCESSED_DIR
    preprocessed_path = input_dir / "preprocessed_wide.csv"
    manifest_path = input_dir / "preprocessed_manifest.json"
    if not preprocessed_path.exists() or not manifest_path.exists():
        raise ValueError("Regenerate causal preprocessing and its manifest before building features")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("preprocessed_csv_sha256") != hashlib.sha256(preprocessed_path.read_bytes()).hexdigest():
        raise ValueError("Preprocessed CSV does not match its provenance manifest")
    if not manifest.get("causal_preprocessing") or manifest.get("units", {}).get("gwl") != "m_bgl":
        raise ValueError("Preprocessed generation must be causal and physical-unit data")
    print("[1/3] Loading verified preprocessed data...")
    df = pd.read_csv(preprocessed_path, parse_dates=["date"], dtype={"district_id": str})

    if args.sample:
        districts = df["district_id"].unique()[:args.sample]
        df = df[df["district_id"].isin(districts)]

    print(f"  Loaded {len(df):,} rows, {df['district_id'].nunique()} canonical districts\n")

    print("[2/3] Building all 10 features...")
    rainfall_history = load_prior_rainfall_history()
    features = build_all_features(df, rainfall_history=rainfall_history)

    print(f"\n  Feature matrix shape: {features.shape}")
    print(f"  Columns: {list(features.columns)}")

    print("\n[3/3] Saving...")
    sample_only = args.sample is not None or bool(manifest.get("sample_only", False))
    output_dir = ROOT / "reports" / "samples" if sample_only else ROOT / "reports" / "candidates" if args.csv_only else PROCESSED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "features_matrix.csv"
    features.to_csv(out_path, index=False)
    print(f"  CSV: {out_path} ({len(features):,} rows)")

    feature_manifest = {**manifest,
        "generation_id": features["feature_generation"].iloc[0],
        "feature_csv_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "rainfall_normals_method": "expanding_prior_year_same_month", "rainfall_normals_min_prior_years": 3,
        "feature_columns": FEATURES_LIST, "observation_column": "is_observed",
        "sample_only": sample_only,
        "data_readiness_score_meaning": "numeric feature completeness; not observation coverage",
        "rainfall_history_start": str(rainfall_history["date"].min().date()) if rainfall_history is not None else manifest["date_start"],
    }
    (output_dir / "feature_manifest.json").write_text(json.dumps(feature_manifest, indent=2), encoding="utf-8")
    if not args.csv_only and not feature_manifest["sample_only"]:
        write_to_db(features)
    else:
        print("  Sample/CSV-only generation: database unchanged")

    train, test = build_train_test_split(features)
    print(f"\n  Train/Test split:")
    print(f"    Train: {len(train):,} rows ({train['district_id'].nunique()} districts)")
    print(f"    Test:  {len(test):,} rows ({test['district_id'].nunique()} districts)")

    print("\nDone [OK]")


if __name__ == "__main__":
    main()
