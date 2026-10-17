"""
AquaIQ — Statistical Tests (Week 5, Yash)
--------------------------------------------
Exploratory paired district test: Is the 2020-2024 GWL depletion rate
significantly greater than the 2002-2010 baseline?

Hypothesis:
  H0: mean(depletion_2020_2024) <= mean(depletion_2002_2010)
  H1: mean(depletion_2020_2024) > mean(depletion_2002_2010)

One-sided paired test of district period means, alpha = 0.05. Repeated
district-years are not treated as independent samples. Spatial dependence,
monitoring-well changes and uneven observed coverage remain limitations.

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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from models import xgboost_model as forecast
load_dotenv(ROOT / ".env")

with open(ROOT / "config.yaml") as f:
    CONFIG = yaml.safe_load(f)

PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]


def get_connection():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "aquaiq"),
        user=os.getenv("POSTGRES_USER", "aquaiq_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def load_gwl_data() -> pd.DataFrame:
    """Use verified physical features and explicitly observed depths only."""
    frame = forecast.load_feature_matrix()
    observed = forecast.observed_mask(frame)
    values = pd.to_numeric(frame.gwl_current, errors='coerce')
    result = frame.loc[observed & np.isfinite(values) & (values >= 0), ['district_id', 'date']].copy()
    result['GWL_current'] = values.loc[result.index]
    if result.empty:
        raise ValueError('No explicitly observed physical groundwater data for statistical comparison.')
    return result


def compute_depletion_rate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compare the same observed calendar months in adjacent years (m/year).
    Missing years and changes in sampled seasons must not create annual rates.
    """
    df = df.sort_values(["district_id", "date"]).copy()
    df['date'] = pd.to_datetime(df.date)
    df['month'] = df.date.dt.month
    df["year"] = df["date"].dt.year
    if df.duplicated(['district_id', 'year', 'month']).any():
        raise ValueError('Duplicate district-month observations cannot form annual comparisons.')

    # Annual mean GWL per district
    annual = df.groupby(["district_id", "year"])["GWL_current"].mean().reset_index()
    annual = annual.rename(columns={"GWL_current": "mean_gwl"})

    prior = df[['district_id', 'year', 'month', 'GWL_current']].copy()
    prior['year'] += 1
    prior = prior.rename(columns={'GWL_current': 'prior_year_gwl'})
    paired = df.merge(prior, on=['district_id', 'year', 'month'], how='inner', validate='one_to_one')
    paired['gwl_change'] = paired.GWL_current - paired.prior_year_gwl
    changes = paired.groupby(['district_id', 'year']).agg(gwl_change=('gwl_change', 'mean'),
                                                         compared_months=('month', 'size')).reset_index()
    annual = annual.merge(changes, on=['district_id', 'year'], how='left', validate='one_to_one')

    return annual


def run_ttest(annual: pd.DataFrame):
    """
    Perform two-sample t-test comparing depletion rates:
      Baseline period: 2002-2010
      Recent period:   2020-2024
    """
    baseline = annual[(annual["year"] >= 2002) & (annual["year"] <= 2010)]
    recent = annual[(annual["year"] >= 2020) & (annual["year"] <= 2024)]

    # One mean per district per period, paired across the same districts.
    compared = pd.concat([baseline.groupby('district_id').gwl_change.mean().rename('baseline'),
                          recent.groupby('district_id').gwl_change.mean().rename('recent')], axis=1).dropna()
    baseline_rates, recent_rates = compared.baseline, compared.recent
    if len(compared) < 2:
        raise ValueError('At least two districts with comparable observed rates in both periods are required.')

    print(f"  Paired districts with observed rates in both periods: {len(compared):,}")
    print()
    print(f"  Baseline mean depletion: {baseline_rates.mean():.4f} m/year")
    print(f"  Recent mean depletion:   {recent_rates.mean():.4f} m/year")
    print(f"  Baseline std:            {baseline_rates.std():.4f}")
    print(f"  Recent std:              {recent_rates.std():.4f}")
    print()

    # Paired district period means; repeated years do not inflate sample size.
    t_stat, p_two_sided = stats.ttest_rel(
        recent_rates, baseline_rates,
        alternative="greater",
    )

    print(f"  Exploratory paired district test (one-sided, H1: recent > baseline):")
    print(f"    t-statistic = {t_stat:.4f}")
    print(f"    p-value     = {p_two_sided:.6f}")
    print()

    alpha = 0.05
    print('  Limitations: spatial dependence, changing well coverage and source publication dates are not resolved.')
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
        "paired_districts": len(compared),
        "test": "exploratory paired district period means",
        "units": "m/year",
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
