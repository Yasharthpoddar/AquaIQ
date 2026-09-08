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
from scipy.stats import pearsonr

CGWB_PATH = "data/raw/cgwb/cgwb_combined.csv"
CGWB_DISTRICT_COL = "district_name"
CGWB_STATE_COL = "state_name"
CGWB_DATE_COL = "date"
CGWB_GWL_COL = "currentlevel"

IMD_DISTRICT_MONTHLY = "data/processed/imd_rainfall_district_monthly.csv"
GEOJSON_PATH = "data/raw/india_districts.geojson"
GEO_DISTRICT_COL = "district"

OUT_CORRELATION_CSV = "data/processed/district_rainfall_gwl_correlation.csv"
OUT_HEATMAP_PNG = "outputs/rainfall_gwl_correlation_heatmap.png"

MIN_MONTHS_REQUIRED = 4  # CGWB is only ~2 readings/year, so lower bar than a true monthly series


def load_cgwb():
    df = pd.read_csv(CGWB_PATH)
    df = df.rename(columns={
        CGWB_DISTRICT_COL: "district",
        CGWB_STATE_COL: "state",
        CGWB_GWL_COL: "gwl",
    })
    df["date"] = pd.to_datetime(df[CGWB_DATE_COL])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["district"] = df["district"].str.strip().str.title()
    # collapse multiple borewell stations in the same district/month to one mean reading
    district_monthly = (
        df.groupby(["district", "year", "month"])["gwl"].mean().reset_index()
    )
    return district_monthly


def load_imd():
    df = pd.read_csv(IMD_DISTRICT_MONTHLY)
    df["district"] = df["district"].str.strip().str.title()
    return df[["district", "year", "month", "rainfall_mm"]]


def compute_district_correlations(merged: pd.DataFrame) -> pd.DataFrame:
    results = []
    for district, group in merged.groupby("district"):
        group = group.dropna(subset=["rainfall_mm", "gwl"])
        if len(group) < MIN_MONTHS_REQUIRED:
            continue
        r, p_value = pearsonr(group["rainfall_mm"], group["gwl"])
        results.append({"district": district, "correlation": r, "p_value": p_value, "n_months": len(group)})
    return pd.DataFrame(results)


if __name__ == "__main__":
    print("Loading CGWB (this file is large, may take a little while)...")
    cgwb = load_cgwb()
    print(f"  {len(cgwb):,} district-month rows, {cgwb['district'].nunique()} districts")

    print("Loading IMD district-monthly rainfall...")
    imd = load_imd()
    print(f"  {len(imd):,} rows, {imd['district'].nunique()} districts")

    print("Merging on (district, year, month)...")
    merged = pd.merge(cgwb, imd, on=["district", "year", "month"], how="inner")
    matched_districts = merged["district"].nunique()
    print(f"  {len(merged):,} matched rows across {matched_districts} districts")
    if matched_districts < 50:
        print("  WARNING: very few districts matched -- likely a district-name mismatch")
        print("  between CGWB and IMD/GeoJSON. Ask Ayush for his cleaned name-lookup table.")

    print("\nComputing per-district Pearson correlation (rainfall vs GWL)...")
    corr_df = compute_district_correlations(merged)
    corr_df.to_csv(OUT_CORRELATION_CSV, index=False)
    print(f"  saved {len(corr_df)} district correlations to {OUT_CORRELATION_CSV}")
    print(f"  mean correlation across districts: {corr_df['correlation'].mean():.3f}")
    print(f"  ({(corr_df['correlation'] < 0).sum()} negative / {(corr_df['correlation'] > 0).sum()} positive)")

    print("\nBuilding choropleth heatmap...")
    districts_geo = gpd.read_file(GEOJSON_PATH)
    districts_geo["district"] = districts_geo[GEO_DISTRICT_COL].str.strip().str.title()
    geo_merged = districts_geo.merge(corr_df, on="district", how="left")

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
