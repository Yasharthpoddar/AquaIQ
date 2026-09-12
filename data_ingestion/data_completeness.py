"""
AquaIQ — Data Completeness Report (Week 6, Ayush)
----------------------------------------------------
Computes the % of districts with full CGWB + IMD + ERA5 coverage
across the 2002-2024 study period. Outputs a summary CSV and
console report.

Run:
    python data_ingestion/data_completeness.py
"""

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

DATA_RAW = ROOT / CONFIG["paths"]["data_raw"]
PROCESSED_DIR = ROOT / CONFIG["paths"]["data_processed"]

# Full study period: 2002-2024, monthly
EXPECTED_MONTHS = (2024 - 2002 + 1) * 12  # 276 months


def check_cgwb() -> pd.DataFrame:
    """Count months per district in CGWB data."""
    cgwb_path = DATA_RAW / "cgwb_combined.csv"
    if not cgwb_path.exists():
        print("  CGWB: NOT FOUND")
        return pd.DataFrame()

    raw = pd.read_csv(cgwb_path, dtype=str, low_memory=False)
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw["currentlevel"] = pd.to_numeric(raw["currentlevel"], errors="coerce")
    raw = raw.dropna(subset=["date", "currentlevel"])

    # Get district identifier
    dist_col = "district_code" if "district_code" in raw.columns else "district_name"
    if dist_col not in raw.columns:
        dist_col = raw.columns[0]

    raw["month"] = raw["date"].dt.to_period("M")
    coverage = raw.groupby(dist_col)["month"].nunique().reset_index()
    coverage.columns = ["district_id", "cgwb_months"]
    print(f"  CGWB: {len(coverage)} districts, median {coverage['cgwb_months'].median():.0f} months")
    return coverage


def check_imd() -> pd.DataFrame:
    """Count months per district in IMD data."""
    imd_path = PROCESSED_DIR / "imd_rainfall_district_monthly.csv"
    if not imd_path.exists():
        print("  IMD: NOT FOUND")
        return pd.DataFrame()

    raw = pd.read_csv(imd_path)
    dist_col = "district" if "district" in raw.columns else raw.columns[0]

    if "year" in raw.columns and "month" in raw.columns:
        coverage = raw.groupby(dist_col).size().reset_index()
        coverage.columns = ["district_id", "imd_months"]
    else:
        coverage = raw.groupby(dist_col).size().reset_index()
        coverage.columns = ["district_id", "imd_months"]

    print(f"  IMD: {len(coverage)} districts, median {coverage['imd_months'].median():.0f} months")
    return coverage


def check_era5() -> pd.DataFrame:
    """Count months per district in ERA5 data."""
    era5_path = PROCESSED_DIR / "era5_district_monthly.csv"
    if not era5_path.exists():
        print("  ERA5: NOT FOUND")
        return pd.DataFrame()

    raw = pd.read_csv(era5_path)
    dist_col = "district" if "district" in raw.columns else raw.columns[0]

    coverage = raw.groupby(dist_col).size().reset_index()
    coverage.columns = ["district_id", "era5_months"]
    print(f"  ERA5: {len(coverage)} districts, median {coverage['era5_months'].median():.0f} months")
    return coverage


def compute_report():
    """Merge all three sources and compute completeness."""
    print("[1/2] Checking individual source coverage...\n")

    cgwb = check_cgwb()
    imd = check_imd()
    era5 = check_era5()

    print(f"\n[2/2] Computing combined completeness...\n")

    if len(cgwb) == 0:
        print("ERROR: CGWB data missing. Cannot compute completeness.")
        return None

    # Start with CGWB as base
    report = cgwb.copy()

    # Merge IMD if available
    if len(imd) > 0:
        report = report.merge(imd, on="district_id", how="left")
        report["imd_months"] = report["imd_months"].fillna(0).astype(int)
    else:
        report["imd_months"] = 0

    # Merge ERA5 if available
    if len(era5) > 0:
        report = report.merge(era5, on="district_id", how="left")
        report["era5_months"] = report["era5_months"].fillna(0).astype(int)
    else:
        report["era5_months"] = 0

    # Completeness scores
    report["cgwb_pct"] = (report["cgwb_months"] / EXPECTED_MONTHS * 100).round(1)
    report["imd_pct"] = (report["imd_months"] / EXPECTED_MONTHS * 100).round(1)
    report["era5_pct"] = (report["era5_months"] / EXPECTED_MONTHS * 100).round(1)

    # Overall: minimum coverage across all 3 sources
    report["overall_pct"] = report[["cgwb_pct", "imd_pct", "era5_pct"]].min(axis=1)

    # Coverage tiers
    report["coverage_tier"] = pd.cut(
        report["overall_pct"],
        bins=[-1, 25, 50, 75, 100],
        labels=["Poor (<25%)", "Fair (25-50%)", "Good (50-75%)", "Excellent (>75%)"],
    )

    return report


def print_summary(report: pd.DataFrame):
    """Print a human-readable summary."""
    total = len(report)
    print(f"  Total districts: {total}")
    print(f"  Expected months per district: {EXPECTED_MONTHS} (2002-2024)\n")

    # Source coverage
    print(f"  Per-source coverage:")
    for src in ["cgwb", "imd", "era5"]:
        col = f"{src}_pct"
        if col in report.columns:
            mean = report[col].mean()
            above50 = (report[col] >= 50).sum()
            print(f"    {src.upper():5s}: mean={mean:.1f}%  |  {above50}/{total} districts >= 50%")

    # Overall tier distribution
    print(f"\n  Overall coverage distribution:")
    for tier in report["coverage_tier"].cat.categories:
        count = (report["coverage_tier"] == tier).sum()
        pct = count / total * 100
        print(f"    {tier:20s}: {count:4d} ({pct:.1f}%)")

    # Full coverage (all 3 sources >= 75%)
    full = (report["overall_pct"] >= 75).sum()
    print(f"\n  Districts with full coverage (>= 75% all sources): {full}/{total} ({full/total*100:.1f}%)")


def main():
    print("AquaIQ -- Data Completeness Report\n")

    report = compute_report()
    if report is None:
        return

    print_summary(report)

    # Save
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out_path = PROCESSED_DIR / "data_completeness_report.csv"
    report.to_csv(out_path, index=False)
    print(f"\n  Full report saved to {out_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
