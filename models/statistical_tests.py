"""
AquaIQ — Statistical Tests (Week 5, Yash)
--------------------------------------------
Two-sample t-test: Is the 2020-2024 GWL depletion rate statistically
significantly greater than the 2002-2010 baseline?

Hypothesis:
  H0: mean(depletion_2020_2024) <= mean(depletion_2002_2010)
  H1: mean(depletion_2020_2024) > mean(depletion_2002_2010)

One-sided Welch's t-test, alpha = 0.05.

Course mapping: CS205 — Statistical Methods for AI.

Run:
    python models/statistical_tests.py
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv
from scipy import stats

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]


def load_gwl_data() -> pd.DataFrame:
    """Load GWL data from features matrix or raw CGWB."""
    path = PROCESSED_DIR / "features_matrix.csv"
    if path.exists():
        df = pd.read_csv(path, parse_dates=["date"])
        if "GWL_current" in df.columns:
            return df[["district_id", "date", "GWL_current"]].copy()

    # Fallback: raw CGWB
    cgwb_path = ROOT / CONFIG["paths"]["data_raw"] / "cgwb_combined.csv"
    if not cgwb_path.exists():
        print("ERROR: No GWL data found.")
        sys.exit(1)

    raw = pd.read_csv(cgwb_path, dtype=str, low_memory=False)
    raw["GWL_current"] = pd.to_numeric(raw["currentlevel"], errors="coerce")
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw = raw.dropna(subset=["GWL_current", "date", "district_code"])
    raw["date"] = raw["date"].dt.to_period("M").dt.to_timestamp()

    df = raw.groupby(["district_code", "date"])["GWL_current"].mean().reset_index()
    df = df.rename(columns={"district_code": "district_id"})
    return df


def compute_depletion_rate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute annual depletion rate (cm/year) per district.
    Depletion rate = slope of GWL over time (positive = deepening wells = bad).
    """
    df = df.sort_values(["district_id", "date"]).copy()
    df["year"] = df["date"].dt.year

    # Annual mean GWL per district
    annual = df.groupby(["district_id", "year"])["GWL_current"].mean().reset_index()
    annual = annual.rename(columns={"GWL_current": "mean_gwl"})

    # Compute year-over-year change
    annual = annual.sort_values(["district_id", "year"])
    annual["gwl_change"] = annual.groupby("district_id")["mean_gwl"].diff()

    return annual


def run_ttest(annual: pd.DataFrame):
    """
    Perform two-sample t-test comparing depletion rates:
      Baseline period: 2002-2010
      Recent period:   2020-2024
    """
    baseline = annual[(annual["year"] >= 2002) & (annual["year"] <= 2010)]
    recent = annual[(annual["year"] >= 2020) & (annual["year"] <= 2024)]

    # Drop NaN changes (first year per district has no diff)
    baseline_rates = baseline["gwl_change"].dropna()
    recent_rates = recent["gwl_change"].dropna()

    print(f"  Baseline period (2002-2010): {len(baseline_rates):,} observations")
    print(f"  Recent period   (2020-2024): {len(recent_rates):,} observations")
    print()
    print(f"  Baseline mean depletion: {baseline_rates.mean():.4f} m/year")
    print(f"  Recent mean depletion:   {recent_rates.mean():.4f} m/year")
    print(f"  Baseline std:            {baseline_rates.std():.4f}")
    print(f"  Recent std:              {recent_rates.std():.4f}")
    print()

    # Welch's t-test (one-sided: recent > baseline)
    t_stat, p_two_sided = stats.ttest_ind(
        recent_rates, baseline_rates,
        equal_var=False,  # Welch's
        alternative="greater",
    )

    print(f"  Welch's t-test (one-sided, H1: recent > baseline):")
    print(f"    t-statistic = {t_stat:.4f}")
    print(f"    p-value     = {p_two_sided:.6f}")
    print()

    alpha = 0.05
    if p_two_sided < alpha:
        print(f"  RESULT: REJECT H0 (p={p_two_sided:.6f} < alpha={alpha})")
        print("  The 2020-2024 depletion rate is statistically significantly")
        print("  greater than the 2002-2010 baseline.")
    else:
        print(f"  RESULT: FAIL TO REJECT H0 (p={p_two_sided:.6f} >= alpha={alpha})")
        print("  No statistically significant difference found.")

    # Effect size (Cohen's d)
    pooled_std = np.sqrt(
        (baseline_rates.std() ** 2 + recent_rates.std() ** 2) / 2
    )
    if pooled_std > 0:
        cohens_d = (recent_rates.mean() - baseline_rates.mean()) / pooled_std
        print(f"\n  Cohen's d (effect size) = {cohens_d:.4f}")
        if abs(cohens_d) < 0.2:
            print("  Interpretation: Negligible effect")
        elif abs(cohens_d) < 0.5:
            print("  Interpretation: Small effect")
        elif abs(cohens_d) < 0.8:
            print("  Interpretation: Medium effect")
        else:
            print("  Interpretation: Large effect")

    return {
        "t_statistic": round(t_stat, 4),
        "p_value": round(p_two_sided, 6),
        "baseline_mean": round(baseline_rates.mean(), 4),
        "recent_mean": round(recent_rates.mean(), 4),
        "significant": p_two_sided < alpha,
    }


def save_results(results: dict):
    """Save t-test results to CSV."""
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out_path = PROCESSED_DIR / "ttest_results.csv"
    pd.DataFrame([results]).to_csv(out_path, index=False)
    print(f"\n  Results saved to {out_path}")


def main():
    print("AquaIQ -- Statistical Tests\n")

    print("[1/3] Loading GWL data...")
    gwl = load_gwl_data()
    print(f"  {len(gwl):,} rows, {gwl['district_id'].nunique()} districts")

    print("\n[2/3] Computing annual depletion rates...")
    annual = compute_depletion_rate(gwl)

    print("\n[3/3] Running two-sample t-test...")
    print("=" * 60)
    results = run_ttest(annual)
    print("=" * 60)

    save_results(results)
    print("\nDone.")


if __name__ == "__main__":
    main()
