"""
AquaIQ -- Rainfall vs GWL Correlation + Heatmap (Yash, Week 2, Task 2)
---------------------------------------------------------------------------
Merges district-monthly rainfall (from imd_district_climatology.py) with
CGWB groundwater levels, computes a Pearson correlation per district, and
plots it as a choropleth ("heatmap") of India using Ayush's district
GeoJSON.

CGWB's 'currentlevel' is depth-to-water-table (metres below ground) --
lower number = water closer to surface = healthier. So the physically
expected correlation with rainfall is NEGATIVE (more rain -> shallower
depth -> lower currentlevel). Positive correlations are a real EDA
finding worth flagging in your report, not a bug.
"""

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from pathlib import Path
import sys
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from data_ingestion.ingest_imd_era5 import norm_state, norm_str

CGWB_PATH = ROOT / "data/raw/cgwb_combined.csv"
CGWB_DISTRICT_COL = "district_name"
CGWB_STATE_COL = "state_name"
CGWB_DATE_COL = "date"
CGWB_GWL_COL = "currentlevel"

IMD_DISTRICT_MONTHLY = ROOT / "data/processed/imd_rainfall_district_monthly.csv"
GEOJSON_PATH = ROOT / "data/raw/india_districts.geojson"
GEO_DISTRICT_COL = "district"

OUT_CORRELATION_CSV = ROOT / "reports/candidates/correlation/district_rainfall_gwl_correlation.csv"
OUT_HEATMAP_PNG = ROOT / "reports/candidates/correlation/rainfall_gwl_correlation_heatmap.png"

MIN_MONTHS_REQUIRED = 4  # CGWB is only ~2 readings/year, so lower bar than a true monthly series


def load_cgwb():
    df = pd.read_csv(CGWB_PATH)
    df = df.rename(columns={
        CGWB_DISTRICT_COL: "district",
        CGWB_STATE_COL: "state",
        CGWB_GWL_COL: "gwl",
    })
    df["date"] = pd.to_datetime(df[CGWB_DATE_COL], errors="coerce")
    df["gwl"] = pd.to_numeric(df["gwl"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["date", "gwl", "district", "state"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["district"] = df["district"].map(norm_str)
    df["state"] = df["state"].map(norm_state)
    # collapse multiple borewell stations in the same district/month to one mean reading
    district_monthly = (
        df.groupby(["state", "district", "year", "month"])["gwl"].mean().reset_index()
    )
    return district_monthly


def load_imd():
    df = pd.read_csv(IMD_DISTRICT_MONTHLY)
    df["district"] = df["district"].map(norm_str)
    df["state"] = df["st_nm"].map(norm_state)
    keys = ["state", "district", "year", "month"]
    if df.duplicated(keys).any():
        raise ValueError("Duplicate state-qualified rainfall months")
    return df[[*keys, "rainfall_mm"]]


def compute_district_correlations(merged: pd.DataFrame) -> pd.DataFrame:
    results = []
    for (state, district), group in merged.groupby(["state", "district"]):
        group = group.dropna(subset=["rainfall_mm", "gwl"])
        if (len(group) < MIN_MONTHS_REQUIRED or group["rainfall_mm"].nunique() < 2
                or group["gwl"].nunique() < 2):
            continue
        r, p_value = pearsonr(group["rainfall_mm"], group["gwl"])
        results.append({"state": state, "district": district, "correlation": r, "p_value": p_value, "n_months": len(group)})
    return pd.DataFrame(results, columns=["state", "district", "correlation", "p_value", "n_months"])


if __name__ == "__main__":
    print("Loading CGWB (this file is large, may take a little while)...")
    cgwb = load_cgwb()
    print(f"  {len(cgwb):,} district-month rows, {cgwb['district'].nunique()} districts")

    print("Loading IMD district-monthly rainfall...")
    imd = load_imd()
    print(f"  {len(imd):,} rows, {imd['district'].nunique()} districts")

    print("Merging on (state, district, year, month)...")
    merged = pd.merge(cgwb, imd, on=["state", "district", "year", "month"], how="inner", validate="one_to_one")
    matched_districts = merged["district"].nunique()
    print(f"  {len(merged):,} matched rows across {matched_districts} districts")
    if matched_districts < 50:
        print("  WARNING: very few districts matched -- likely a district-name mismatch")
        print("  between CGWB and IMD/GeoJSON. Ask Ayush for his cleaned name-lookup table.")

    print("\nComputing per-district Pearson correlation (rainfall vs GWL)...")
    corr_df = compute_district_correlations(merged)
    OUT_CORRELATION_CSV.parent.mkdir(parents=True, exist_ok=True)
    corr_df.to_csv(OUT_CORRELATION_CSV, index=False)
    print(f"  saved {len(corr_df)} district correlations to {OUT_CORRELATION_CSV}")
    print(f"  mean correlation across districts: {corr_df['correlation'].mean():.3f}")
    print(f"  ({(corr_df['correlation'] < 0).sum()} negative / {(corr_df['correlation'] > 0).sum()} positive)")

    print("\nBuilding choropleth heatmap...")
    districts_geo = gpd.read_file(GEOJSON_PATH)
    districts_geo["district"] = districts_geo[GEO_DISTRICT_COL].map(norm_str)
    districts_geo["state"] = districts_geo["st_nm"].map(norm_state)
    geo_merged = districts_geo.merge(corr_df, on=["state", "district"], how="left", validate="many_to_one")

    fig, ax = plt.subplots(1, 1, figsize=(12, 14))
    geo_merged.plot(
        column="correlation",
        cmap="RdYlGn_r",  # reversed: red=positive(unexpected), green=negative(expected/healthy)
        linewidth=0.2,
        edgecolor="grey",
        legend=True,
        vmin=-1,
        vmax=1,
        missing_kwds={"color": "lightgrey", "label": "No data"},
        ax=ax,
    )
    ax.set_title("Rainfall vs Groundwater Depth Correlation by District", fontsize=16, fontweight="bold")
    ax.axis("off")
    plt.tight_layout()

    import os
    os.makedirs(os.path.dirname(OUT_HEATMAP_PNG), exist_ok=True)
    plt.savefig(OUT_HEATMAP_PNG, dpi=200, bbox_inches="tight")
    print(f"  saved heatmap to {OUT_HEATMAP_PNG}")
    print("\nDone. Green = expected physical pattern (more rain -> shallower water table).")
    print("Red = inverse/unexpected pattern -- worth a sentence in your EDA findings.")
