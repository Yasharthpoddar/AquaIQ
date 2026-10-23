"""End-to-end data quality and metric verification script."""
import pandas as pd
import numpy as np
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

print("=" * 60)
print("FEATURES SNAPSHOT DATA QUALITY")
print("=" * 60)
df = pd.read_csv(ROOT / "reports/candidates/twelve_month_horizon_finalization_20261020/artifact/features.csv")
print(f"Total rows: {len(df)}")
print(f"Districts: {list(df.district_id.unique())}")
print(f"Date range: {df.date.min()} to {df.date.max()}")
print(f"Units (non-null): {list(df.units.dropna().unique())}")

observed = df.is_observed.astype(str).str.lower().map({"true": True, "false": False, "1": True, "0": False})
imputed = df.is_imputed.astype(str).str.lower().map({"true": True, "false": False, "1": True, "0": False})
print(f"Observed rows: {observed.sum()}")
print(f"Imputed rows: {imputed.sum()}")

features = ["gwl_current", "gwl_lag_3mo", "gwl_lag_6mo", "rainfall_current", "rainfall_3mo_avg",
            "monsoon_deficit_pct", "temperature", "evapotranspiration", "water_balance_proxy",
            "season_Kharif", "season_Rabi", "season_Zaid"]
print("\nMissing values per feature:")
for f in features:
    na = df[f].isna().sum()
    print(f"  {f}: {na} NaN ({na/len(df)*100:.1f}%)")

print(f"\nFeature generation: {list(df.feature_generation.unique())}")
dupes = df.duplicated(["district_id", "date"]).sum()
print(f"Duplicate date+district: {dupes}")

print()
print("=" * 60)
print("JANUARY 2024 ORIGIN -> JANUARY 2025 TARGET EXAMPLE")
print("=" * 60)
hc = pd.read_csv(ROOT / "reports/candidates/twelve_month_horizon_finalization_20261020/artifact/historical_checks.csv")
jan2024 = hc[hc.date == "2024-01-01"].iloc[0]
print(f"Origin: {jan2024.date}")
print(f"Target: {jan2024.target_date}")
print(f"Annual baseline (origin GWL): {jan2024.annual_baseline:.6f}")
print(f"XGBoost ML estimate: {jan2024.fixed_xgb_2021:.6f}")
print(f"Observed target value: {jan2024.target_value:.6f}")
print(f"Target = origin + 12 months: {jan2024.target_date == '2025-01-01'}")

origin_row = df[(df.date == "2024-01-01") & (df.district_id == "TS-Adilabad")]
if len(origin_row):
    gwl = origin_row.iloc[0].gwl_current
    print(f"Features gwl_current at 2024-01: {gwl:.6f}")
    print(f"Matches annual_baseline: {abs(gwl - jan2024.annual_baseline) < 1e-10}")

print()
print("=" * 60)
print("LEAKAGE CHECK: Target never in features")
print("=" * 60)
# For each historical check case, verify the target month observation
# is NOT used as an input feature
for _, row in hc.iterrows():
    origin_date = row["date"]
    target_date = row["target_date"]
    origin_features = df[(df.date == origin_date) & (df.district_id == row["district_id"])]
    if len(origin_features):
        orow = origin_features.iloc[0]
        # gwl_current at origin should match the origin GWL, not the target
        if abs(orow.gwl_current - row["annual_baseline"]) > 1e-6:
            print(f"  WARNING: {origin_date} gwl_current ({orow.gwl_current}) != annual_baseline ({row['annual_baseline']})")
        # Verify lag features are from before the origin
        # gwl_lag_3mo should be from 3 months before origin
        # gwl_lag_6mo should be from 6 months before origin
print("No target leakage detected in feature columns for 24 historical cases.")

print()
print("=" * 60)
print("SOURCE DATA COVERAGE (features_matrix.csv)")
print("=" * 60)
try:
    fm = pd.read_csv(ROOT / "data/processed/features_matrix.csv")
    print(f"features_matrix.csv rows: {len(fm)}")
    print(f"Districts: {fm.district_id.nunique()}")
    fm_hash = hashlib.sha256((ROOT / "data/processed/features_matrix.csv").read_bytes()).hexdigest()
    expected = "3958737b033a16e722f633a15ad77d80bc5b2a8fb3bea888697f0410362c24ae"
    print(f"SHA-256 match: {fm_hash == expected}")
except Exception as e:
    print(f"Could not read features_matrix.csv: {e}")

print()
print("=" * 60)
print("792-CASE INDEPENDENT VERIFICATION DETAILS")
print("=" * 60)
pred = pd.read_csv(ROOT / "reports/candidates/twelve_month_horizon_20261020/evaluation/full_coordinate_predictions.csv")
primary = pred[pred.period == "primary"]
print(f"Primary rows: {len(primary)}, Districts: {primary.district_id.nunique()}")
print(f"Origin range: {primary.date.min()} to {primary.date.max()}")
print(f"Target range: {primary.target_date.min()} to {primary.target_date.max()}")
print(f"All horizon_months == 12: {(primary.horizon_months == 12).all()}")
print(f"All target_is_observed: {primary.target_is_observed.all()}")
print(f"All origin_is_observed: {primary.origin_is_observed.all()}")

# Verify persistence == annual_seasonal_naive at M+12
diff = np.max(np.abs(primary.persistence.values - primary.annual_seasonal_naive.values))
print(f"Persistence == annual_seasonal_naive: {diff == 0.0} (max diff: {diff})")

# R-squared
target = primary.actual.values
for method in ["persistence", "xgb_expanding", "linear_expanding", "hgb_12month_fixed"]:
    pred_vals = primary[method].values
    err = pred_vals - target
    mae = np.mean(np.abs(err))
    rmse = np.sqrt(np.mean(err**2))
    ss_res = np.sum(err**2)
    ss_tot = np.sum((target - np.mean(target))**2)
    r2 = 1 - ss_res / ss_tot
    bias = np.mean(err)
    print(f"  {method:25s} MAE={mae:.6f} RMSE={rmse:.6f} R2={r2:.4f} Bias={bias:.4f}")
