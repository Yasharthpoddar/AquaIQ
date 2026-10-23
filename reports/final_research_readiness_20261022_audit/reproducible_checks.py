#!/usr/bin/env python3
"""
AquaIQ — Final Research Readiness, Statistical Robustness, and Validation Checks
Directory: reports/final_research_readiness_20261022_audit/
Author: Senior ML Researcher, Applied Statistician & Groundwater Reviewer
Date: 2026-10-22

This script performs independent, reproducible verification of:
1. Research dataset integrity (Study A: 792 expanding cases, Study B: 24 fixed cases).
2. Headline metric reproduction (MAE, RMSE, Bias, R2).
3. Annual seasonal-persistence baseline audit.
4. Corrected paired cluster bootstrap (10,000 replicates across multiple seeds).
5. Comprehensive spatial and temporal dependence diagnostics (autocorrelations, cross-district correlations, annual regime reversal, temporal block bootstrap, time-cluster bootstrap).
6. Statistical inference review (centered pivot test, Wald test, district-level paired t-test, Wilcoxon test).
7. Machine-readable export to results.json.

Preservation: Does NOT modify any existing dataset, artifact, report, or configuration.
"""

import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent

def run_checks():
    print("=" * 80)
    print("AquaIQ — Comprehensive Statistical Robustness and Publication-Readiness Audit")
    print("=" * 80)
    print(f"Project root: {ROOT}")
    print(f"Output directory: {OUT_DIR}")
    
    results = {}

    # =========================================================================
    # 1. DATASET INTEGRITY CHECKS (Study A: Primary Evaluation Panel)
    # =========================================================================
    print("\n" + "=" * 80)
    print("1. DATASET INTEGRITY CHECKS (Study A)")
    print("=" * 80)
    
    pred_path = ROOT / "reports/candidates/twelve_month_horizon_20261020/evaluation/full_coordinate_predictions.csv"
    if not pred_path.exists():
        raise FileNotFoundError(f"Missing evaluation dataset: {pred_path}")
    
    df_all = pd.read_csv(pred_path)
    primary = df_all[df_all["period"] == "primary"].copy()
    secondary = df_all[df_all["period"] == "secondary"].copy()
    
    n_total = len(df_all)
    n_primary = len(primary)
    n_secondary = len(secondary)
    n_districts = primary["district_id"].nunique()
    unique_districts = np.sort(primary["district_id"].unique())
    rows_per_district = primary.groupby("district_id").size()
    
    origin_min = primary["date"].min()
    origin_max = primary["date"].max()
    target_min = primary["target_date"].min()
    target_max = primary["target_date"].max()
    
    unique_case_ids = primary["case_id"].nunique()
    dup_cases = primary.duplicated(subset=["case_id"]).sum()
    dup_keys = primary.duplicated(subset=["district_id", "date", "target_date"]).sum()
    
    horizons = primary["horizon_months"].unique().tolist()
    
    missing_actual = int(primary["actual"].isna().sum())
    missing_xgb = int(primary["xgb_expanding"].isna().sum())
    missing_base = int(primary["annual_seasonal_naive"].isna().sum())
    missing_lin = int(primary["linear_expanding"].isna().sum())
    missing_hgb = int(primary["hgb_12month_fixed"].isna().sum())
    
    # Check baseline equivalence
    baseline_exact_match = bool(np.allclose(primary["persistence"], primary["annual_seasonal_naive"]))
    
    # Check model hashes
    xgb_models = primary.groupby(primary["target_date"].str[:4])["xgb_expanding_model_sha256"].unique().to_dict()
    xgb_models = {k: v.tolist() for k, v in xgb_models.items()}
    
    print(f"Total rows in predictions file: {n_total} (Primary: {n_primary}, Secondary: {n_secondary})")
    print(f"Districts in primary: {n_districts}")
    print(f"Panel balance: {rows_per_district.nunique() == 1} (Exactly {rows_per_district.iloc[0]} rows/district)")
    print(f"Origin range: {origin_min} to {origin_max} (24 calendar months)")
    print(f"Target range: {target_min} to {target_max} (24 calendar months)")
    print(f"Forecast horizon: {horizons} months")
    print(f"Unique case_ids: {unique_case_ids} (Duplicates: {dup_cases})")
    print(f"Duplicate [district, date, target_date]: {dup_keys}")
    print(f"Missing actuals / predictions: {missing_actual} / {missing_xgb} / {missing_base}")
    print(f"Persistence == Annual Seasonal Naive: {baseline_exact_match}")
    print(f"Expanding XGBoost models per target year: {xgb_models}")
    
    results["dataset_integrity"] = {
        "source_file": str(pred_path.relative_to(ROOT)),
        "n_total": n_total,
        "n_primary": n_primary,
        "n_secondary": n_secondary,
        "n_districts": n_districts,
        "balanced_panel": bool(rows_per_district.nunique() == 1),
        "rows_per_district": int(rows_per_district.iloc[0]),
        "origin_range": [origin_min, origin_max],
        "target_range": [target_min, target_max],
        "horizon_months": horizons,
        "duplicate_cases": int(dup_cases),
        "duplicate_keys": int(dup_keys),
        "missing_values": {
            "actual": missing_actual,
            "xgb_expanding": missing_xgb,
            "annual_seasonal_naive": missing_base,
            "linear_expanding": missing_lin,
            "hgb_12month_fixed": missing_hgb
        },
        "persistence_equals_seasonal_naive": baseline_exact_match,
        "xgb_expanding_models_by_target_year": xgb_models
    }

    # =========================================================================
    # 2. HEADLINE METRICS REPRODUCTION (Study A & Study B)
    # =========================================================================
    print("\n" + "=" * 80)
    print("2. HEADLINE METRICS REPRODUCTION")
    print("=" * 80)
    
    # Study A: 792 Primary rows
    y = primary["actual"].values
    y_base = primary["annual_seasonal_naive"].values
    y_xgb = primary["xgb_expanding"].values
    y_lin = primary["linear_expanding"].values
    y_hgb = primary["hgb_12month_fixed"].values
    
    def calc_metrics(actual, pred):
        err = pred - actual
        rmse = float(np.sqrt(np.mean(err**2)))
        mae = float(np.mean(np.abs(err)))
        bias = float(np.mean(err))
        r2 = float(1.0 - np.sum(err**2) / np.sum((actual - np.mean(actual))**2))
        return {"rmse": rmse, "mae": mae, "bias": bias, "r2": r2}
    
    metrics_base_A = calc_metrics(y, y_base)
    metrics_xgb_A = calc_metrics(y, y_xgb)
    metrics_lin_A = calc_metrics(y, y_lin)
    metrics_hgb_A = calc_metrics(y, y_hgb)
    
    delta_rmse_A = metrics_xgb_A["rmse"] - metrics_base_A["rmse"]
    delta_mae_A = metrics_xgb_A["mae"] - metrics_base_A["mae"]
    rel_rmse_change_A = (delta_rmse_A / metrics_base_A["rmse"]) * 100.0
    
    print("Study A (792-Case Primary Evaluation):")
    print(f"  Annual Baseline : RMSE = {metrics_base_A['rmse']:.6f} m, MAE = {metrics_base_A['mae']:.6f} m, Bias = {metrics_base_A['bias']:.6f} m, R2 = {metrics_base_A['r2']:.6f}")
    print(f"  Expanding XGB   : RMSE = {metrics_xgb_A['rmse']:.6f} m, MAE = {metrics_xgb_A['mae']:.6f} m, Bias = {metrics_xgb_A['bias']:.6f} m, R2 = {metrics_xgb_A['r2']:.6f}")
    print(f"  Expanding Linear: RMSE = {metrics_lin_A['rmse']:.6f} m, MAE = {metrics_lin_A['mae']:.6f} m, Bias = {metrics_lin_A['bias']:.6f} m, R2 = {metrics_lin_A['r2']:.6f}")
    print(f"  Fixed 12m HGB   : RMSE = {metrics_hgb_A['rmse']:.6f} m, MAE = {metrics_hgb_A['mae']:.6f} m, Bias = {metrics_hgb_A['bias']:.6f} m, R2 = {metrics_hgb_A['r2']:.6f}")
    print(f"  Delta RMSE (XGB - Base): {delta_rmse_A:+.6f} m ({rel_rmse_change_A:+.2f}%)")
    print(f"  Delta MAE  (XGB - Base): {delta_mae_A:+.6f} m")
    
    # Study B: 24-Case TS-Adilabad Fixed Artifact
    hist_path = ROOT / "reports/candidates/twelve_month_horizon_finalization_20261020/artifact/historical_checks.csv"
    if not hist_path.exists():
        raise FileNotFoundError(f"Missing historical checks dataset: {hist_path}")
    df_b = pd.read_csv(hist_path)
    
    y_B = df_b["target_value"].values
    base_B = df_b["annual_baseline"].values
    xgb_B = df_b["fixed_xgb_2021"].values
    
    metrics_base_B = calc_metrics(y_B, base_B)
    metrics_xgb_B = calc_metrics(y_B, xgb_B)
    delta_rmse_B = metrics_xgb_B["rmse"] - metrics_base_B["rmse"]
    delta_mae_B = metrics_xgb_B["mae"] - metrics_base_B["mae"]
    
    print("\nStudy B (24-Case Fixed TS-Adilabad Artifact):")
    print(f"  Annual Baseline : RMSE = {metrics_base_B['rmse']:.6f} m, MAE = {metrics_base_B['mae']:.6f} m, Bias = {metrics_base_B['bias']:.6f} m, R2 = {metrics_base_B['r2']:.6f}")
    print(f"  Fixed 2021 XGB  : RMSE = {metrics_xgb_B['rmse']:.6f} m, MAE = {metrics_xgb_B['mae']:.6f} m, Bias = {metrics_xgb_B['bias']:.6f} m, R2 = {metrics_xgb_B['r2']:.6f}")
    print(f"  Delta RMSE (XGB - Base): {delta_rmse_B:+.6f} m (XGBoost is {metrics_xgb_B['rmse']/metrics_base_B['rmse']*100:.1f}% of baseline RMSE)")
    print(f"  Delta MAE  (XGB - Base): {delta_mae_B:+.6f} m")
    
    results["study_a_headline_metrics"] = {
        "n_cases": len(primary),
        "annual_baseline": metrics_base_A,
        "xgb_expanding": metrics_xgb_A,
        "linear_expanding": metrics_lin_A,
        "hgb_12month_fixed": metrics_hgb_A,
        "delta_rmse": delta_rmse_A,
        "delta_mae": delta_mae_A,
        "relative_rmse_pct": rel_rmse_change_A
    }
    results["study_b_headline_metrics"] = {
        "n_cases": len(df_b),
        "district": "TS-Adilabad",
        "annual_baseline": metrics_base_B,
        "fixed_xgb_2021": metrics_xgb_B,
        "delta_rmse": delta_rmse_B,
        "delta_mae": delta_mae_B
    }

    # =========================================================================
    # 3. PAIRED CLUSTER BOOTSTRAP VALIDATION & SEED SENSITIVITY
    # =========================================================================
    print("\n" + "=" * 80)
    print("3. PAIRED DISTRICT-CLUSTER BOOTSTRAP VALIDATION")
    print("=" * 80)
    
    districts_arr = primary["district_id"].values
    district_idx = {d: np.where(districts_arr == d)[0] for d in unique_districts}
    
    def run_cluster_bootstrap(B=10000, seed=42):
        rng = np.random.default_rng(seed)
        boot_diff_rmse = np.empty(B)
        boot_diff_mae = np.empty(B)
        for b in range(B):
            sampled_d = rng.choice(unique_districts, size=n_districts, replace=True)
            idx = np.concatenate([district_idx[d] for d in sampled_d])
            y_b = y[idx]
            xgb_b = y_xgb[idx]
            base_b = y_base[idx]
            boot_diff_rmse[b] = np.sqrt(np.mean((xgb_b - y_b)**2)) - np.sqrt(np.mean((base_b - y_b)**2))
            boot_diff_mae[b] = np.mean(np.abs(xgb_b - y_b)) - np.mean(np.abs(base_b - y_b))
        return boot_diff_rmse, boot_diff_mae
    
    seeds = [42, 2026, 12345, 99999]
    bootstrap_results = {}
    
    for s in seeds:
        b_rmse, b_mae = run_cluster_bootstrap(B=10000, seed=s)
        ci_r = np.percentile(b_rmse, [2.5, 97.5])
        ci_m = np.percentile(b_mae, [2.5, 97.5])
        se_r = float(np.std(b_rmse, ddof=1))
        se_m = float(np.std(b_mae, ddof=1))
        mean_r = float(np.mean(b_rmse))
        mean_m = float(np.mean(b_mae))
        frac_ge0_r = float(np.mean(b_rmse >= 0))
        frac_ge0_m = float(np.mean(b_mae >= 0))
        
        bootstrap_results[f"seed_{s}"] = {
            "rmse_ci_95": [float(ci_r[0]), float(ci_r[1])],
            "rmse_se": se_r,
            "rmse_mean": mean_r,
            "rmse_frac_ge0": frac_ge0_r,
            "mae_ci_95": [float(ci_m[0]), float(ci_m[1])],
            "mae_se": se_m,
            "mae_mean": mean_m,
            "mae_frac_ge0": frac_ge0_m
        }
        print(f"Seed {s:5d}: 95% CI RMSE = [{ci_r[0]:+.6f}, {ci_r[1]:+.6f}] m, Mean = {mean_r:+.6f} m, SE = {se_r:.6f} m, Frac >= 0 = {frac_ge0_r:.4f}")
    
    results["paired_cluster_bootstrap"] = bootstrap_results

    # =========================================================================
    # 4. SPATIAL & TEMPORAL DEPENDENCE DIAGNOSTICS & SENSITIVITY
    # =========================================================================
    print("\n" + "=" * 80)
    print("4. SPATIAL AND TEMPORAL DEPENDENCE ANALYSIS (PRIORITY)")
    print("=" * 80)
    
    primary["err_xgb"] = primary["xgb_expanding"] - primary["actual"]
    primary["err_base"] = primary["annual_seasonal_naive"] - primary["actual"]
    primary["sq_err_xgb"] = primary["err_xgb"]**2
    primary["sq_err_base"] = primary["err_base"]**2
    primary["diff_sq"] = primary["sq_err_xgb"] - primary["sq_err_base"]
    
    # 4.1 Contemporaneous Cross-District Correlation across 24 months
    piv_xgb = primary.pivot(index="date", columns="district_id", values="err_xgb")
    piv_base = primary.pivot(index="date", columns="district_id", values="err_base")
    piv_diff = primary.pivot(index="date", columns="district_id", values="diff_sq")
    
    c_xgb = piv_xgb.corr().to_numpy().copy()
    c_base = piv_base.corr().to_numpy().copy()
    c_diff = piv_diff.corr().to_numpy().copy()
    np.fill_diagonal(c_xgb, np.nan)
    np.fill_diagonal(c_base, np.nan)
    np.fill_diagonal(c_diff, np.nan)
    
    mean_cross_corr_xgb = float(np.nanmean(c_xgb))
    mean_cross_corr_base = float(np.nanmean(c_base))
    mean_cross_corr_diff = float(np.nanmean(c_diff))
    
    print(f"Mean pairwise cross-district error correlation (XGBoost) : {mean_cross_corr_xgb:.4f}")
    print(f"Mean pairwise cross-district error correlation (Baseline): {mean_cross_corr_base:.4f}")
    print(f"Mean pairwise cross-district correlation of Delta(SE)    : {mean_cross_corr_diff:.4f}")
    
    # 4.2 Serial Autocorrelation within District across 24 consecutive months
    acfs_xgb = []
    acfs_base = []
    acfs_diff = []
    for d, sub in primary.groupby("district_id"):
        sub_sort = sub.sort_values("date")
        e_x = sub_sort["err_xgb"].values
        e_b = sub_sort["err_base"].values
        e_d = sub_sort["diff_sq"].values
        if np.std(e_x) > 0:
            acfs_xgb.append(np.corrcoef(e_x[:-1], e_x[1:])[0, 1])
        if np.std(e_b) > 0:
            acfs_base.append(np.corrcoef(e_b[:-1], e_b[1:])[0, 1])
        if np.std(e_d) > 0:
            acfs_diff.append(np.corrcoef(e_d[:-1], e_d[1:])[0, 1])
            
    mean_acf_xgb = float(np.mean(acfs_xgb))
    mean_acf_base = float(np.mean(acfs_base))
    mean_acf_diff = float(np.mean(acfs_diff))
    
    print(f"Mean lag-1 serial autocorrelation within district (XGBoost) : {mean_acf_xgb:.4f}")
    print(f"Mean lag-1 serial autocorrelation within district (Baseline): {mean_acf_base:.4f}")
    print(f"Mean lag-1 serial autocorrelation of Delta(SE)              : {mean_acf_diff:.4f}")
    
    # 4.3 Annual Regime Reversal
    primary["target_year"] = primary["target_date"].str[:4]
    annual_breakdown = {}
    for yr, sub in primary.groupby("target_year"):
        m_b = calc_metrics(sub["actual"].values, sub["annual_seasonal_naive"].values)
        m_x = calc_metrics(sub["actual"].values, sub["xgb_expanding"].values)
        d_r = m_x["rmse"] - m_b["rmse"]
        annual_breakdown[yr] = {
            "n_cases": len(sub),
            "baseline_rmse": m_b["rmse"],
            "xgb_rmse": m_x["rmse"],
            "delta_rmse": d_r,
            "baseline_bias": m_b["bias"],
            "xgb_bias": m_x["bias"]
        }
        print(f"Target Year {yr} (N={len(sub)}): Baseline RMSE={m_b['rmse']:.4f} m, XGB RMSE={m_x['rmse']:.4f} m, Delta={d_r:+.4f} m")
    
    # 4.4 Dependence-Aware Resampling Sensitivity Analyses
    dates_arr = primary["date"].values
    unique_dates = np.sort(np.unique(dates_arr))
    date_idx = {t: np.where(dates_arr == t)[0] for t in unique_dates}
    T = len(unique_dates)
    B_sens = 10000
    rng_s = np.random.default_rng(42)
    
    # A: Time-cluster bootstrap (resampling entire 33-district cross-sections by origin month, T=24)
    boot_time = np.empty(B_sens)
    for b in range(B_sens):
        s_t = rng_s.choice(unique_dates, size=T, replace=True)
        idx = np.concatenate([date_idx[t] for t in s_t])
        boot_time[b] = np.sqrt(np.mean((y_xgb[idx] - y[idx])**2)) - np.sqrt(np.mean((y_base[idx] - y[idx])**2))
    
    ci_time = np.percentile(boot_time, [2.5, 97.5])
    se_time = float(np.std(boot_time, ddof=1))
    
    # B: Temporal contiguous block bootstrap (L=6 months, preserving cross-district correlation)
    L6 = 6
    boot_block6 = np.empty(B_sens)
    n_b6 = int(np.ceil(T / L6))
    for b in range(B_sens):
        st_idx = rng_s.choice(T, size=n_b6, replace=True)
        sampled_dates = []
        for st in st_idx:
            for off in range(L6):
                sampled_dates.append(unique_dates[(st + off) % T])
        sampled_dates = sampled_dates[:T]
        idx = np.concatenate([date_idx[t] for t in sampled_dates])
        boot_block6[b] = np.sqrt(np.mean((y_xgb[idx] - y[idx])**2)) - np.sqrt(np.mean((y_base[idx] - y[idx])**2))
    
    ci_b6 = np.percentile(boot_block6, [2.5, 97.5])
    se_b6 = float(np.std(boot_block6, ddof=1))
    
    # C: Temporal contiguous block bootstrap (L=12 months)
    L12 = 12
    boot_block12 = np.empty(B_sens)
    n_b12 = int(np.ceil(T / L12))
    for b in range(B_sens):
        st_idx = rng_s.choice(T, size=n_b12, replace=True)
        sampled_dates = []
        for st in st_idx:
            for off in range(L12):
                sampled_dates.append(unique_dates[(st + off) % T])
        sampled_dates = sampled_dates[:T]
        idx = np.concatenate([date_idx[t] for t in sampled_dates])
        boot_block12[b] = np.sqrt(np.mean((y_xgb[idx] - y[idx])**2)) - np.sqrt(np.mean((y_base[idx] - y[idx])**2))
    
    ci_b12 = np.percentile(boot_block12, [2.5, 97.5])
    se_b12 = float(np.std(boot_block12, ddof=1))
    
    print("\nResampling Scheme Comparison for Delta_RMSE:")
    print(f"  1. District-only cluster (K=33)      : SE = {bootstrap_results['seed_42']['rmse_se']:.6f} m, 95% CI = [{bootstrap_results['seed_42']['rmse_ci_95'][0]:+.6f}, {bootstrap_results['seed_42']['rmse_ci_95'][1]:+.6f}] m")
    print(f"  2. Time-only cluster (T=24)          : SE = {se_time:.6f} m, 95% CI = [{ci_time[0]:+.6f}, {ci_time[1]:+.6f}] m")
    print(f"  3. Temporal block bootstrap (L=6 mo) : SE = {se_b6:.6f} m, 95% CI = [{ci_b6[0]:+.6f}, {ci_b6[1]:+.6f}] m")
    print(f"  4. Temporal block bootstrap (L=12 mo): SE = {se_b12:.6f} m, 95% CI = [{ci_b12[0]:+.6f}, {ci_b12[1]:+.6f}] m")
    
    results["dependence_diagnostics"] = {
        "cross_district_correlation": {
            "xgb_errors": mean_cross_corr_xgb,
            "baseline_errors": mean_cross_corr_base,
            "diff_squared_errors": mean_cross_corr_diff
        },
        "serial_autocorrelation_lag1": {
            "xgb_errors": mean_acf_xgb,
            "baseline_errors": mean_acf_base,
            "diff_squared_errors": mean_acf_diff
        },
        "annual_regime_reversal": annual_breakdown,
        "resampling_sensitivity": {
            "district_cluster_k33": {
                "se": bootstrap_results["seed_42"]["rmse_se"],
                "ci_95": bootstrap_results["seed_42"]["rmse_ci_95"]
            },
            "time_cluster_t24": {
                "se": se_time,
                "ci_95": [float(ci_time[0]), float(ci_time[1])]
            },
            "temporal_block_l6": {
                "se": se_b6,
                "ci_95": [float(ci_b6[0]), float(ci_b6[1])]
            },
            "temporal_block_l12": {
                "se": se_b12,
                "ci_95": [float(ci_b12[0]), float(ci_b12[1])]
            }
        }
    }

    # =========================================================================
    # 5. STATISTICAL INFERENCE REVIEW
    # =========================================================================
    print("\n" + "=" * 80)
    print("5. STATISTICAL INFERENCE PROCEDURES REVIEW")
    print("=" * 80)
    
    # Baseline boot from seed 42
    b_rmse_42 = run_cluster_bootstrap(B=10000, seed=42)[0]
    se_r_42 = np.std(b_rmse_42, ddof=1)
    
    # 5.1 Centered Bootstrap Pivot Test
    pivot_deviations = np.abs(b_rmse_42 - delta_rmse_A)
    p_pivot = float(np.mean(pivot_deviations >= np.abs(delta_rmse_A)))
    
    # 5.2 Cluster-Robust Wald Test
    z_wald = float(delta_rmse_A / se_r_42)
    p_wald = float(2 * stats.norm.sf(np.abs(z_wald)))
    
    # Normality diagnostics of bootstrap distribution
    skew_b = float(stats.skew(b_rmse_42))
    kurt_b = float(stats.kurtosis(b_rmse_42))
    shapiro_p = float(stats.shapiro(b_rmse_42[:5000])[1])
    
    # 5.3 District-Level Paired Tests
    dist_rmse_diffs = []
    dist_mae_diffs = []
    for d in unique_districts:
        ix = district_idx[d]
        r_x = np.sqrt(np.mean((y_xgb[ix] - y[ix])**2))
        r_b = np.sqrt(np.mean((y_base[ix] - y[ix])**2))
        dist_rmse_diffs.append(r_x - r_b)
        dist_mae_diffs.append(np.mean(np.abs(y_xgb[ix] - y[ix])) - np.mean(np.abs(y_base[ix] - y[ix])))
    
    dist_rmse_diffs = np.array(dist_rmse_diffs)
    dist_mae_diffs = np.array(dist_mae_diffs)
    
    t_stat, t_pval = stats.ttest_1samp(dist_rmse_diffs, 0)
    w_stat, w_pval = stats.wilcoxon(dist_rmse_diffs)
    
    n_xgb_wins = int((dist_rmse_diffs < 0).sum())
    n_base_wins = int((dist_rmse_diffs > 0).sum())
    
    print(f"5.1 Centered Bootstrap Pivot Test : p = {p_pivot:.4f}")
    print(f"5.2 Cluster-Robust Wald Test      : z = {z_wald:.4f}, p = {p_wald:.4f} (Skewness={skew_b:.3f}, Kurtosis={kurt_b:.3f})")
    print(f"5.3 District-Level Paired t-test  : t(32) = {t_stat:.4f}, p = {t_pval:.4f}")
    print(f"5.4 District-Level Wilcoxon Test  : W = {w_stat:.1f}, p = {w_pval:.4f}")
    print(f"    Districts favoring XGBoost: {n_xgb_wins} / {n_districts} ({n_xgb_wins/n_districts*100:.1f}%)")
    print(f"    Districts favoring Base   : {n_base_wins} / {n_districts} ({n_base_wins/n_districts*100:.1f}%)")
    print(f"    Mean district Delta_RMSE  : {np.mean(dist_rmse_diffs):+.6f} m")
    print(f"    Median district Delta_RMSE: {np.median(dist_rmse_diffs):+.6f} m")
    
    results["inferential_procedures"] = {
        "centered_bootstrap_pivot": {
            "estimand": "pooled_delta_rmse",
            "p_value": p_pivot,
            "h0": "pooled_delta_rmse == 0"
        },
        "wald_test": {
            "estimand": "pooled_delta_rmse",
            "z_statistic": z_wald,
            "p_value": p_wald,
            "bootstrap_skewness": skew_b,
            "bootstrap_kurtosis": kurt_b,
            "shapiro_p": shapiro_p
        },
        "district_level_paired_t_test": {
            "estimand": "unweighted_mean_of_district_delta_rmse",
            "t_statistic": float(t_stat),
            "df": n_districts - 1,
            "p_value": float(t_pval),
            "mean_district_delta": float(np.mean(dist_rmse_diffs))
        },
        "district_level_wilcoxon": {
            "estimand": "median_of_district_delta_rmse",
            "w_statistic": float(w_stat),
            "p_value": float(w_pval),
            "median_district_delta": float(np.median(dist_rmse_diffs))
        },
        "district_win_counts": {
            "xgb_wins": n_xgb_wins,
            "baseline_wins": n_base_wins,
            "total_districts": n_districts
        }
    }

    # Save results to JSON
    out_file = OUT_DIR / "results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nAll checks completed successfully. Machine-readable results saved to: {out_file}")

if __name__ == "__main__":
    run_checks()
