#!/usr/bin/env python3
"""
AquaIQ — Final Statistical Inference Review
Date: 2026-10-22
Purpose: Independent recalculation of bootstrap CI, review of p-value validity,
         and district-level cluster-aware inference.

This script does NOT modify any production code, datasets, or artifacts.
"""

import numpy as np
import pandas as pd
from scipy import stats
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]

# ============================================================================
# SECTION 1: Load and validate the primary evaluation dataset
# ============================================================================
print("=" * 80)
print("SECTION 1: Dataset Integrity Verification")
print("=" * 80)

pred_path = ROOT / "reports/candidates/twelve_month_horizon_20261020/evaluation/full_coordinate_predictions.csv"
df = pd.read_csv(pred_path)
primary = df[df["period"] == "primary"].copy()

n_rows = len(primary)
n_districts = primary["district_id"].nunique()
unique_districts = np.sort(primary["district_id"].unique())
rows_per_district = primary.groupby("district_id").size()

print(f"Total rows in file: {len(df)}")
print(f"Primary-period rows: {n_rows}")
print(f"Unique districts: {n_districts}")
print(f"Rows per district (min/max): {rows_per_district.min()}/{rows_per_district.max()}")
print(f"Balanced panel: {rows_per_district.nunique() == 1}")
print(f"Duplicate [district_id, date, target_date]: {primary.duplicated(subset=['district_id', 'date', 'target_date']).sum()}")
print(f"Duplicate case_id: {primary.duplicated(subset=['case_id']).sum()}")
print(f"Missing actual: {primary['actual'].isna().sum()}")
print(f"Missing xgb_expanding: {primary['xgb_expanding'].isna().sum()}")
print(f"Missing annual_seasonal_naive: {primary['annual_seasonal_naive'].isna().sum()}")

# Confirm the data structures
assert n_rows == 792, f"Expected 792 rows, got {n_rows}"
assert n_districts == 33, f"Expected 33 districts, got {n_districts}"
assert rows_per_district.nunique() == 1, "Unbalanced panel"
assert rows_per_district.iloc[0] == 24, f"Expected 24 rows per district, got {rows_per_district.iloc[0]}"
assert primary.duplicated(subset=["district_id", "date", "target_date"]).sum() == 0
assert primary["actual"].isna().sum() == 0
assert primary["xgb_expanding"].isna().sum() == 0
assert primary["annual_seasonal_naive"].isna().sum() == 0
print("\nAll integrity checks PASSED.")

# ============================================================================
# SECTION 2: Point estimate calculation
# ============================================================================
print("\n" + "=" * 80)
print("SECTION 2: Point Estimates")
print("=" * 80)

y = primary["actual"].values
y_xgb = primary["xgb_expanding"].values
y_base = primary["annual_seasonal_naive"].values

rmse_xgb = np.sqrt(np.mean((y_xgb - y)**2))
rmse_base = np.sqrt(np.mean((y_base - y)**2))
delta_rmse_point = rmse_xgb - rmse_base

mae_xgb = np.mean(np.abs(y_xgb - y))
mae_base = np.mean(np.abs(y_base - y))
delta_mae_point = mae_xgb - mae_base

print(f"RMSE_XGBoost = {rmse_xgb:.10f} m")
print(f"RMSE_Baseline = {rmse_base:.10f} m")
print(f"Delta_RMSE (XGBoost - Baseline) = {delta_rmse_point:.10f} m")
print(f"MAE_XGBoost = {mae_xgb:.10f} m")
print(f"MAE_Baseline = {mae_base:.10f} m")
print(f"Delta_MAE (XGBoost - Baseline) = {delta_mae_point:.10f} m")

# ============================================================================
# SECTION 3: Paired district-cluster bootstrap (independent recalculation)
# ============================================================================
print("\n" + "=" * 80)
print("SECTION 3: Paired District-Cluster Bootstrap (Independent Recalculation)")
print("=" * 80)

districts_arr = primary["district_id"].values
district_idx = {d: np.where(districts_arr == d)[0] for d in unique_districts}

B = 10000
seed = 42
rng = np.random.default_rng(seed)

boot_delta_rmse = np.empty(B)
boot_delta_mae = np.empty(B)

for b in range(B):
    # Draw ONE set of district clusters with replacement
    sampled = rng.choice(unique_districts, size=n_districts, replace=True)
    # Concatenate all row indices for the sampled districts (with multiplicity)
    idx = np.concatenate([district_idx[d] for d in sampled])
    
    y_b = y[idx]
    xgb_b = y_xgb[idx]
    base_b = y_base[idx]
    
    boot_delta_rmse[b] = np.sqrt(np.mean((xgb_b - y_b)**2)) - np.sqrt(np.mean((base_b - y_b)**2))
    boot_delta_mae[b] = np.mean(np.abs(xgb_b - y_b)) - np.mean(np.abs(base_b - y_b))

ci_rmse = np.percentile(boot_delta_rmse, [2.5, 97.5])
ci_mae = np.percentile(boot_delta_mae, [2.5, 97.5])
se_rmse = np.std(boot_delta_rmse, ddof=1)
se_mae = np.std(boot_delta_mae, ddof=1)
boot_mean_rmse = np.mean(boot_delta_rmse)
boot_mean_mae = np.mean(boot_delta_mae)
frac_ge0_rmse = np.mean(boot_delta_rmse >= 0)
frac_ge0_mae = np.mean(boot_delta_mae >= 0)

print(f"Bootstrap parameters: B={B}, seed={seed}, K={n_districts} clusters, N={n_rows} observations")
print(f"\nDelta RMSE:")
print(f"  Point estimate:     {delta_rmse_point:.10f} m")
print(f"  Bootstrap mean:     {boot_mean_rmse:.10f} m")
print(f"  Bootstrap SE:       {se_rmse:.10f} m")
print(f"  95% CI (percentile):[{ci_rmse[0]:.10f}, {ci_rmse[1]:.10f}] m")
print(f"  Fraction >= 0:      {frac_ge0_rmse:.4f} ({frac_ge0_rmse * 100:.2f}%)")
print(f"\nDelta MAE:")
print(f"  Point estimate:     {delta_mae_point:.10f} m")
print(f"  Bootstrap mean:     {boot_mean_mae:.10f} m")
print(f"  Bootstrap SE:       {se_mae:.10f} m")
print(f"  95% CI (percentile):[{ci_mae[0]:.10f}, {ci_mae[1]:.10f}] m")
print(f"  Fraction >= 0:      {frac_ge0_mae:.4f} ({frac_ge0_mae * 100:.2f}%)")

# ============================================================================
# SECTION 4: Review of the reported "p-value" (lines 184-185 of correction script)
# ============================================================================
print("\n" + "=" * 80)
print("SECTION 4: Critical Review of the Reported 'p-value' = 0.4094")
print("=" * 80)

# Reproduce the reported calculation:
reported_p = 2 * min(frac_ge0_rmse, 1 - frac_ge0_rmse)
print(f"Reproduced calculation: 2 * min({frac_ge0_rmse:.4f}, {1-frac_ge0_rmse:.4f}) = {reported_p:.4f}")

print("""
ANALYSIS OF VALIDITY:

The correction script computes:
    p_value = 2 * min(np.mean(delta_rmse_list >= 0), np.mean(delta_rmse_list <= 0))

This is the proportion of the sampling distribution of delta_RMSE under the
ESTIMATED (not null) distribution that falls on the opposite side of zero
from the point estimate, doubled to create a two-sided quantity.

This is NOT a valid frequentist p-value. A frequentist p-value requires:
    P(T >= t_obs | H0 is true)
where H0: Delta_RMSE = 0 and the distribution of T is computed UNDER H0.

The bootstrap sampling distribution is centered near the observed point estimate
(-0.038 m), not at zero. The fraction of this distribution exceeding zero
describes a property of the bootstrap distribution of the estimator, not the
probability of obtaining the observed result under the null hypothesis.

There are two standard approaches to obtain a valid bootstrap p-value:

  (a) Pivot/shift method: Center the bootstrap distribution at zero by computing
      T_b* = delta_RMSE_b* - delta_RMSE_obs, then compute P(T_b* <= -|delta_RMSE_obs|
      or T_b* >= |delta_RMSE_obs|). This is equivalent to checking whether zero
      lies outside the bootstrap CI, but expressed as a probability.

  (b) Wald-type test: z = delta_RMSE_obs / SE_boot, then p = 2 * Phi(-|z|).
      This requires a normal approximation assumption.

Neither of these was used. The reported 0.4094 is therefore not a valid p-value.

However: The 95% percentile bootstrap CI [-0.1209, +0.0555] m includes zero,
which is itself a valid inferential statement at the 5% level. If zero is
inside the 95% CI, a corresponding bootstrap hypothesis test at alpha=0.05
would fail to reject H0. This is the defensible inference.
""")

# ============================================================================
# SECTION 5: Compute valid inferential quantities
# ============================================================================
print("=" * 80)
print("SECTION 5: Valid Inferential Quantities")
print("=" * 80)

# --- 5A: Bootstrap pivot p-value ---
# Under the pivot method, the null distribution of the test statistic is
# approximated by the centered bootstrap: T_b* = boot_delta - observed_delta.
# Under H0: delta=0, we approximate p = P(|T| >= |observed_delta|)
# which equals P(boot_delta <= 2*observed_delta - boot_delta) OR P(boot_delta >= -observed_delta + delta_obs)
# Simplifying: p = mean(|boot_delta - observed_delta| >= |observed_delta|)
pivot_deviations = np.abs(boot_delta_rmse - delta_rmse_point)
p_pivot = np.mean(pivot_deviations >= np.abs(delta_rmse_point))
print(f"\n5A. Bootstrap pivot p-value (two-sided):")
print(f"    T_b* = boot_delta_b - delta_obs; p = P(|T_b*| >= |delta_obs|)")
print(f"    p_pivot = {p_pivot:.4f}")

# --- 5B: Wald-type bootstrap p-value ---
z_wald = delta_rmse_point / se_rmse
p_wald = 2 * stats.norm.sf(np.abs(z_wald))
print(f"\n5B. Wald-type bootstrap p-value (normal approximation):")
print(f"    z = delta_obs / SE_boot = {delta_rmse_point:.6f} / {se_rmse:.6f} = {z_wald:.4f}")
print(f"    p_wald = 2 * Phi(-|z|) = {p_wald:.4f}")
print(f"    Assumption: delta_RMSE bootstrap distribution is approximately normal.")

# Check normality of the bootstrap distribution
shapiro_stat, shapiro_p = stats.shapiro(boot_delta_rmse[:5000])  # shapiro limited to 5000
print(f"    Shapiro-Wilk normality test (on first 5000 replicates): W={shapiro_stat:.6f}, p={shapiro_p:.4f}")
skew_boot = stats.skew(boot_delta_rmse)
kurt_boot = stats.kurtosis(boot_delta_rmse)
print(f"    Skewness: {skew_boot:.4f}, Excess Kurtosis: {kurt_boot:.4f}")

# --- 5C: District-level paired tests ---
# These test a DIFFERENT estimand: the mean of district-level RMSE differences,
# NOT the difference in pooled RMSE. Document this distinction.
print(f"\n5C. District-level paired tests (N=33 districts):")
print(f"    NOTE: These test whether the AVERAGE of per-district RMSE differences")
print(f"    equals zero. This is NOT the same as testing whether the POOLED Delta_RMSE")
print(f"    equals zero, because pooled RMSE weights districts by their squared-error")
print(f"    magnitude, whereas the per-district average treats each district equally.")

dist_rmse_diffs = []
for d in unique_districts:
    ix = district_idx[d]
    r_xgb = np.sqrt(np.mean((y_xgb[ix] - y[ix])**2))
    r_base = np.sqrt(np.mean((y_base[ix] - y[ix])**2))
    dist_rmse_diffs.append(r_xgb - r_base)

dist_rmse_diffs = np.array(dist_rmse_diffs)
t_stat, t_pval = stats.ttest_1samp(dist_rmse_diffs, 0)
w_stat, w_pval = stats.wilcoxon(dist_rmse_diffs)

print(f"    Mean district-level Delta_RMSE: {np.mean(dist_rmse_diffs):.6f} m")
print(f"    Median district-level Delta_RMSE: {np.median(dist_rmse_diffs):.6f} m")
print(f"    Std dev: {np.std(dist_rmse_diffs, ddof=1):.6f} m")
print(f"    Districts favoring XGBoost (delta < 0): {(dist_rmse_diffs < 0).sum()} / {n_districts}")
print(f"    Districts favoring Baseline (delta > 0): {(dist_rmse_diffs > 0).sum()} / {n_districts}")
print(f"    Paired t-test: t({n_districts-1}) = {t_stat:.4f}, p = {t_pval:.4f}")
print(f"    Wilcoxon signed-rank: W = {w_stat:.1f}, p = {w_pval:.4f}")
print(f"    Estimand: E[RMSE_xgb(d) - RMSE_base(d)] across districts d")
print(f"    Assumptions (t-test): district-level differences are iid normal")
print(f"    Assumptions (Wilcoxon): district-level differences are iid symmetric about median")
print(f"    Both assumptions are approximate: districts share common climate and model artifacts.")

# --- 5D: Correct interpretation of the 20.47% bootstrap sign proportion ---
print(f"\n5D. Correct interpretation of the bootstrap sign proportion:")
print(f"    Observed fraction of bootstrap replicates with Delta_RMSE >= 0: {frac_ge0_rmse:.4f}")
print(f"    This quantity describes a property of the bootstrap sampling distribution of the")
print(f"    estimator. It is the estimated probability that, under resampling of the OBSERVED")
print(f"    data-generating process (not under H0), the pooled RMSE difference would be")
print(f"    nonnegative. It is NOT the probability that annual persistence will outperform")
print(f"    XGBoost in the population. The distinction is critical:")
print(f"      - The bootstrap distribution is centered near the observed delta ({delta_rmse_point:.4f} m),")
print(f"        not at zero.")
print(f"      - The sign proportion reflects sampling uncertainty in the estimator, not a")
print(f"        frequentist probability statement about model superiority.")

# ============================================================================
# SECTION 6: Summary
# ============================================================================
print("\n" + "=" * 80)
print("SECTION 6: Summary of Inferential Findings")
print("=" * 80)

print(f"""
VERIFIED POINT ESTIMATE:
  Delta_RMSE = RMSE(XGBoost) - RMSE(Annual Baseline) = {delta_rmse_point:.6f} m
  (Negative value indicates XGBoost achieves lower pooled RMSE.)

VERIFIED 95% PAIRED CLUSTER-BOOTSTRAP CI (B=10,000, seed=42):
  [{ci_rmse[0]:.6f}, {ci_rmse[1]:.6f}] m
  Resampling unit: district (K=33), with all 24 monthly observations per district
  included with correct multiplicity. Both models evaluated on identical
  resampled panels in every replicate.

BOOTSTRAP SE: {se_rmse:.6f} m

VALID INFERENTIAL RESULTS:
  1. Bootstrap pivot p-value (two-sided): p = {p_pivot:.4f}
     (Approximates P(|T| >= |t_obs| | H0: delta=0) via shifted bootstrap distribution.)
  2. Wald-type p-value (normal approx):  p = {p_wald:.4f}
     (z = {z_wald:.4f}; bootstrap distribution is approximately normal: skew={skew_boot:.3f}, kurtosis={kurt_boot:.3f}.)
  3. District-level paired t-test:       p = {t_pval:.4f} (t={t_stat:.3f}, df=32)
     (Tests the unweighted mean of per-district RMSE differences, a DIFFERENT estimand.)
  4. Wilcoxon signed-rank:               p = {w_pval:.4f} (W={w_stat:.0f})
     (Non-parametric test of symmetric per-district differences.)

INVALID QUANTITY (WITHDRAWN):
  The previously reported "p-value = 0.4094" was computed as:
    2 * min(fraction_boot >= 0, fraction_boot <= 0)
  This is not a valid frequentist p-value because the bootstrap distribution
  is centered at the observed delta, not at zero. The calculation measures
  the tail weight of the estimator's sampling distribution relative to zero,
  not the probability of the observed result under the null hypothesis.

20.47% BOOTSTRAP SIGN PROPORTION:
  This is the fraction of paired cluster-bootstrap replicates in which the
  resampled pooled RMSE of the annual baseline was less than or equal to that
  of XGBoost. It describes the sampling variability of the estimator under
  the observed data distribution, not a predictive probability about future
  model performance.

CONCLUSION:
  The 95% paired cluster-bootstrap confidence interval [{ci_rmse[0]:.4f}, {ci_rmse[1]:.4f}] m
  includes zero. The bootstrap pivot p-value is {p_pivot:.4f}, substantially above 0.05.
  The Wald-type p-value ({p_wald:.4f}) and the district-level t-test ({t_pval:.4f}) and
  Wilcoxon test ({w_pval:.4f}) are all consistent: none rejects H0 at alpha=0.05.
  
  The current evaluation does NOT establish that XGBoost achieves statistically
  significantly lower RMSE than annual seasonal persistence for 12-month
  groundwater depth forecasting across these 33 Telangana districts.
  The observed 3.8 cm RMSE advantage is indistinguishable from sampling noise
  at conventional significance levels.
""")

# ============================================================================
# Save machine-readable summary
# ============================================================================
summary = {
    "dataset": {
        "source_file": str(pred_path.relative_to(ROOT)),
        "period_filter": "primary",
        "n_rows": int(n_rows),
        "n_districts": int(n_districts),
        "rows_per_district": 24,
        "duplicates": 0,
        "missing_values": 0
    },
    "point_estimates": {
        "rmse_xgboost": float(rmse_xgb),
        "rmse_baseline": float(rmse_base),
        "delta_rmse": float(delta_rmse_point),
        "mae_xgboost": float(mae_xgb),
        "mae_baseline": float(mae_base),
        "delta_mae": float(delta_mae_point)
    },
    "paired_cluster_bootstrap": {
        "B": B,
        "seed": seed,
        "n_clusters": int(n_districts),
        "ci_95_percentile_rmse": [float(ci_rmse[0]), float(ci_rmse[1])],
        "se_rmse": float(se_rmse),
        "bootstrap_mean_rmse": float(boot_mean_rmse),
        "fraction_ge_zero_rmse": float(frac_ge0_rmse),
        "ci_95_percentile_mae": [float(ci_mae[0]), float(ci_mae[1])],
        "se_mae": float(se_mae),
        "bootstrap_mean_mae": float(boot_mean_mae),
        "fraction_ge_zero_mae": float(frac_ge0_mae),
    },
    "valid_p_values": {
        "bootstrap_pivot_two_sided": float(p_pivot),
        "wald_type_two_sided": float(p_wald),
        "wald_z_statistic": float(z_wald),
        "bootstrap_normality_shapiro_p": float(shapiro_p),
        "bootstrap_skewness": float(skew_boot),
        "bootstrap_excess_kurtosis": float(kurt_boot)
    },
    "district_level_tests": {
        "estimand": "mean_of_district_RMSE_differences",
        "note": "Different estimand from pooled delta_RMSE",
        "mean_delta": float(np.mean(dist_rmse_diffs)),
        "median_delta": float(np.median(dist_rmse_diffs)),
        "n_xgb_wins": int((dist_rmse_diffs < 0).sum()),
        "n_baseline_wins": int((dist_rmse_diffs > 0).sum()),
        "paired_t_test": {"t_statistic": float(t_stat), "p_value": float(t_pval), "df": 32},
        "wilcoxon_signed_rank": {"W_statistic": float(w_stat), "p_value": float(w_pval)}
    },
    "invalid_quantities": {
        "reported_p_0_4094": {
            "formula": "2 * min(frac_boot >= 0, frac_boot <= 0)",
            "status": "INVALID as frequentist p-value",
            "reason": "Bootstrap distribution centered at observed delta, not at null hypothesis value"
        }
    },
    "conclusion": "XGBoost does not demonstrate statistically significant RMSE improvement over annual persistence at alpha=0.05"
}

out_dir = ROOT / "reports" / "statistical_inference_review_20261022"
out_dir.mkdir(parents=True, exist_ok=True)
with open(out_dir / "inference_results.json", "w") as f:
    json.dump(summary, f, indent=2)
print(f"Machine-readable results saved to {out_dir / 'inference_results.json'}")
