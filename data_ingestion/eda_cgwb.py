"""
AquaIQ — Phase I EDA & Visualizations
Reads cgwb_combined.csv directly (no DB needed).
Generates 6 publication-ready plots saved to data/processed/eda/

Run:
    py data_ingestion/eda_cgwb.py

Outputs (data/processed/eda/):
    01_india_gwl_scatter_map.png      — spatial heatmap of mean GWL across India
    02_state_coverage_bar.png         — data coverage per state
    03_national_gwl_trend.png         — nationwide annual GWL trend 1996-2023
    04_gwl_distribution.png           — GWL distribution by season
    05_district_heatmap.png           — top 20 districts: GWL over years (heatmap)
    06_top_depleting_districts.png    — top 10 districts by GWL rise (depletion)
"""

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")   # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import seaborn as sns

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CSV  = ROOT / "data/raw/cgwb_combined.csv"
OUT  = ROOT / "data/processed/eda"
OUT.mkdir(parents=True, exist_ok=True)

# ── AquaIQ brand colours ──────────────────────────────────────────────────────
BLUE   = "#0ea5e9"
TEAL   = "#06b6d4"
RED    = "#ef4444"
AMBER  = "#f59e0b"
GREEN  = "#22c55e"
BG     = "#0f172a"
CARD   = "#1e293b"
TEXT   = "#f1f5f9"
MUTED  = "#94a3b8"

plt.rcParams.update({
    "figure.facecolor":  BG,
    "axes.facecolor":    CARD,
    "axes.edgecolor":    MUTED,
    "axes.labelcolor":   TEXT,
    "xtick.color":       MUTED,
    "ytick.color":       MUTED,
    "text.color":        TEXT,
    "grid.color":        "#334155",
    "grid.alpha":        0.4,
    "font.family":       "DejaVu Sans",
    "axes.titlesize":    14,
    "axes.titleweight":  "bold",
    "axes.titlepad":     12,
})

# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading cgwb_combined.csv ...")
df = pd.read_csv(CSV, dtype=str, low_memory=False)
df["currentlevel"] = pd.to_numeric(df["currentlevel"], errors="coerce")
df["date"]         = pd.to_datetime(df["date"], errors="coerce")
df["year"]         = df["date"].dt.year
df["month"]        = df["date"].dt.month
df["latitude"]     = pd.to_numeric(df["latitude"],  errors="coerce")
df["longitude"]    = pd.to_numeric(df["longitude"], errors="coerce")
df.dropna(subset=["currentlevel", "date", "latitude", "longitude"], inplace=True)

# Crop season flag
def season(m):
    if m in [6,7,8,9,10]:   return "Kharif"
    if m in [11,12,1,2,3]:  return "Rabi"
    return "Zaid"
df["season"] = df["month"].apply(season)

print(f"  Loaded {len(df):,} valid readings | "
      f"{df['district_name'].nunique()} districts | "
      f"{df['year'].min():.0f}–{df['year'].max():.0f}")

# ── 1. Spatial scatter map ─────────────────────────────────────────────────────
print("\n[1/6] India GWL scatter map ...")
well_mean = df.groupby(["station_name","latitude","longitude"])["currentlevel"].mean().reset_index()

fig, ax = plt.subplots(figsize=(10, 11))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

sc = ax.scatter(
    well_mean["longitude"], well_mean["latitude"],
    c=well_mean["currentlevel"],
    cmap="RdYlGn_r",   # red=deep/depleted, green=shallow/healthy
    s=4, alpha=0.7, linewidths=0,
    vmin=0, vmax=well_mean["currentlevel"].quantile(0.95),
)
cbar = fig.colorbar(sc, ax=ax, fraction=0.025, pad=0.02)
cbar.set_label("Mean GWL (m below ground)", color=TEXT, fontsize=11)
cbar.ax.yaxis.set_tick_params(color=MUTED)
plt.setp(cbar.ax.yaxis.get_ticklabels(), color=MUTED)

ax.set_xlim(66, 98); ax.set_ylim(6, 38)
ax.set_xlabel("Longitude", fontsize=11)
ax.set_ylabel("Latitude",  fontsize=11)
ax.set_title("AquaIQ — India Groundwater Level Spatial Map\n(1996–2023, CGWB Well Readings)", fontsize=13)
ax.grid(True, linestyle="--", alpha=0.3)

# Annotate extreme zones
ax.annotate("Rajasthan\n(Deep)", xy=(73, 27), fontsize=8, color=RED, alpha=0.85)
ax.annotate("Punjab\n(Stressed)", xy=(75, 30.5), fontsize=8, color=AMBER, alpha=0.85)
ax.annotate("Kerala\n(Healthy)", xy=(76.5, 10), fontsize=8, color=GREEN, alpha=0.85)

path = OUT / "01_india_gwl_scatter_map.png"
fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"  Saved -> {path.name}")

# ── 2. State coverage bar ──────────────────────────────────────────────────────
print("[2/6] State data coverage ...")
state_stats = (
    df.groupby("state_name")
    .agg(
        districts=("district_name", "nunique"),
        readings=("currentlevel", "count"),
        wells=("station_name", "nunique"),
    )
    .sort_values("readings", ascending=True)
)
top = state_stats.tail(20)

fig, ax = plt.subplots(figsize=(12, 8))
bars = ax.barh(top.index, top["readings"] / 1000,
               color=BLUE, alpha=0.85, edgecolor="none", height=0.7)
ax.bar_label(bars, labels=[f"{v:.0f}K" for v in top["readings"]/1000],
             padding=4, color=TEXT, fontsize=9)
ax.set_xlabel("CGWB Well Readings (thousands)", fontsize=11)
ax.set_title("State-wise CGWB Data Coverage\n(Top 20 states by reading count)", fontsize=13)
ax.grid(axis="x", linestyle="--", alpha=0.4)
ax.set_xlim(0, top["readings"].max() / 1000 * 1.18)

path = OUT / "02_state_coverage_bar.png"
fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"  Saved -> {path.name}")

# ── 3. National GWL trend ──────────────────────────────────────────────────────
print("[3/6] National annual GWL trend ...")
annual = df.groupby("year")["currentlevel"].agg(["mean","median","std"]).reset_index()
annual = annual[(annual["year"] >= 1996) & (annual["year"] <= 2023)]

fig, ax = plt.subplots(figsize=(13, 5))
ax.fill_between(annual["year"],
                annual["mean"] - annual["std"],
                annual["mean"] + annual["std"],
                alpha=0.15, color=BLUE, label="±1 std dev")
ax.plot(annual["year"], annual["mean"],   color=BLUE,  lw=2.5, label="Mean GWL",   marker="o", ms=4)
ax.plot(annual["year"], annual["median"], color=TEAL,  lw=1.5, label="Median GWL", linestyle="--")

# Mark known drought years
for yr, label in [(2002,"2002\nDrought"), (2009,"2009\nDrought"),
                  (2015,"2015-16\nDrought"), (2018,"2018-19\nDrought")]:
    if yr in annual["year"].values:
        ax.axvline(yr, color=RED, alpha=0.5, linestyle=":", lw=1.2)
        ax.text(yr+0.15, annual["mean"].max() * 0.97, label,
                color=RED, fontsize=7.5, alpha=0.9)

ax.invert_yaxis()   # higher GWL value = deeper = worse
ax.set_xlabel("Year", fontsize=11)
ax.set_ylabel("GWL — depth to water table (m)", fontsize=11)
ax.set_title("India National Groundwater Level Trend (1996–2023)\nHigher value = deeper water table = greater depletion", fontsize=13)
ax.legend(facecolor=CARD, edgecolor=MUTED, labelcolor=TEXT, fontsize=10)
ax.grid(True, linestyle="--", alpha=0.4)
ax.set_xlim(annual["year"].min(), annual["year"].max())

path = OUT / "03_national_gwl_trend.png"
fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"  Saved -> {path.name}")

# ── 4. GWL distribution by season ─────────────────────────────────────────────
print("[4/6] GWL distribution by crop season ...")
sample = df.sample(min(200_000, len(df)), random_state=42)
cap    = sample["currentlevel"].quantile(0.99)
sample = sample[sample["currentlevel"] <= cap]

fig, ax = plt.subplots(figsize=(11, 5))
palette = {"Kharif": BLUE, "Rabi": TEAL, "Zaid": AMBER}
for s, color in palette.items():
    subset = sample[sample["season"] == s]["currentlevel"]
    ax.hist(subset, bins=80, alpha=0.55, color=color,
            label=f"{s} (n={len(subset):,})", density=True, edgecolor="none")

ax.set_xlabel("GWL — depth to water table (m)", fontsize=11)
ax.set_ylabel("Density", fontsize=11)
ax.set_title("Groundwater Level Distribution by Crop Season\n(Kharif = monsoon | Rabi = winter | Zaid = summer)", fontsize=13)
ax.legend(facecolor=CARD, edgecolor=MUTED, labelcolor=TEXT, fontsize=10)
ax.grid(True, linestyle="--", alpha=0.4)

path = OUT / "04_gwl_distribution.png"
fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"  Saved -> {path.name}")

# ── 5. District × Year heatmap ─────────────────────────────────────────────────
print("[5/6] District × Year GWL heatmap ...")
# Pick top 20 districts by reading count for a dense heatmap
top_districts = (
    df.groupby("district_name")["currentlevel"].count()
    .nlargest(20).index.tolist()
)
heat_df = (
    df[df["district_name"].isin(top_districts)]
    .groupby(["district_name","year"])["currentlevel"]
    .mean()
    .unstack("year")
)
# Keep years 2002–2023 for cleaner display
heat_df = heat_df.loc[:, heat_df.columns.intersection(range(2002, 2024))]
heat_df.sort_values(heat_df.columns[-1], ascending=False, inplace=True)

fig, ax = plt.subplots(figsize=(16, 7))
sns.heatmap(
    heat_df,
    cmap="RdYlGn_r",
    ax=ax,
    linewidths=0.3,
    linecolor="#0f172a",
    cbar_kws={"label": "Mean GWL (m)", "shrink": 0.6},
    annot=False,
    fmt=".1f",
    vmin=0,
    vmax=heat_df.stack().quantile(0.92),
)
ax.set_title("Groundwater Level Heatmap — Top 20 Districts × Year (2002–2023)\nRed = deep/depleted   Green = shallow/healthy", fontsize=13)
ax.set_xlabel("Year", fontsize=11)
ax.set_ylabel("District", fontsize=11)
ax.tick_params(axis="x", rotation=45, labelsize=9)
ax.tick_params(axis="y", labelsize=9)

path = OUT / "05_district_heatmap.png"
fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"  Saved -> {path.name}")

# ── 6. Top depleting districts ─────────────────────────────────────────────────
print("[6/6] Top depleting districts ...")
early = df[df["year"].between(2002, 2006)].groupby("district_name")["currentlevel"].mean()
late  = df[df["year"].between(2018, 2023)].groupby("district_name")["currentlevel"].mean()
change = (late - early).dropna().sort_values(ascending=False)
top10  = change.head(10)   # positive = water table dropped = depletion

fig, ax = plt.subplots(figsize=(11, 6))
colors = [RED if v > 0 else GREEN for v in top10.values]
bars = ax.barh(top10.index[::-1], top10.values[::-1], color=colors[::-1],
               alpha=0.85, edgecolor="none", height=0.65)
ax.bar_label(bars, labels=[f"+{v:.2f}m" if v > 0 else f"{v:.2f}m"
                             for v in top10.values[::-1]],
             padding=5, color=TEXT, fontsize=9)
ax.axvline(0, color=MUTED, lw=0.8)
ax.set_xlabel("Change in GWL (m) — 2002-06 avg vs 2018-23 avg", fontsize=11)
ax.set_title("Top 10 Most Depleted Districts\n(Positive = water table dropped deeper = worse)", fontsize=13)
ax.grid(axis="x", linestyle="--", alpha=0.4)

path = OUT / "06_top_depleting_districts.png"
fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"  Saved -> {path.name}")

# ── Summary stats ──────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("  AquaIQ Phase I — Dataset Summary")
print("="*55)
print(f"  Total readings       : {len(df):>12,}")
print(f"  Unique wells         : {df['station_name'].nunique():>12,}")
print(f"  Unique districts     : {df['district_name'].nunique():>12,}")
print(f"  Unique states        : {df['state_name'].nunique():>12,}")
print(f"  Date range           : {df['date'].min().date()} -> {df['date'].max().date()}")
print(f"  Mean GWL (all)       : {df['currentlevel'].mean():>11.2f} m")
print(f"  Median GWL (all)     : {df['currentlevel'].median():>11.2f} m")
print(f"  GWL std dev          : {df['currentlevel'].std():>11.2f} m")
print(f"  Missing values       : {df['currentlevel'].isna().sum():>12,}")
print("="*55)
print(f"\n  All plots saved to: {OUT}")
print("  Open them in any image viewer or drag into your presentation.")
