# AquaIQ

AI-powered groundwater depletion forecasting for India's districts. SPIT CSE, Sem V Mini Project I, AY 2026–27. Maps to SIH25068 (Ministry of Jal Shakti).

Forecasts district-level groundwater levels 6 months ahead using a two-layer ML system — a core layer mapped to the Sem I–V syllabus (Linear Regression, Fuzzy Logic, Perceptron ANN) and an advanced self-study layer (LSTM, XGBoost, SHAP) — and outputs a 0–100 Crisis Score per district through a Flask API + React dashboard.

## Team

Yasharth (2024800092) · Yash · Ayush — task ownership rotates across all three every week; see `AquaIQ_ProjectPlan.html` for the full 14-week breakdown.

## Quick start

```bash
git clone <this-repo>
cd AquaIQ
bash setup.sh
source venv/bin/activate
```

`setup.sh` creates a virtualenv, installs pinned dependencies, and initializes the SQLite database. It does **not** download data — that needs your own registration on each portal (see below).

**No paid compute needed.** The LSTM is small (~500K params, 3 layers, hidden=128) and trains in well under an hour on a normal laptop CPU, even with all 640 districts pooled into one training run. XGBoost and the Perceptron are CPU-native by design. If a laptop turns out to be slow, Google Colab's **free** tier or Kaggle Notebooks (also free) work as backups — nobody needs a paid subscription for this project.

## Data sources — download these into `data/raw/` before running anything

| Source | Portal | Gets you |
|---|---|---|
| CGWB | india-wris.nrsc.gov.in | Borewell groundwater level readings, ~15,000 wells |
| IMD | imdpune.gov.in | Monthly district rainfall + 30-year climatological normal |
| ERA5 | cds.climate.copernicus.eu | Temperature, evapotranspiration |
| District boundaries | datameet.org | GeoJSON for the dashboard map |

Registration is required for IMD (institutional access) and ERA5 (free CDS API key). CGWB and the GeoJSON boundaries are open download.

**Deliberately not used:** GRACE-FO, GLDAS, NDVI, irrigation/population census data. Considered during design, excluded because a fully-traceable 3-source pipeline was worth more than partial satellite coverage for a project this size. Full reasoning is in the ESE report's Limitations & Future Work section.

## When a district has thin or no CGWB history

CGWB's ~15,000 wells aren't evenly spread across all 640+ districts — some remote or hilly districts genuinely have sparse coverage. Rather than reintroducing satellite data (GRACE's own resolution is ~300km, similar to what zone-level aggregation already gives) or silently failing, the fallback is two-stepped:

1. **Zone fallback** — below `data_readiness_min_pct` (config.yaml), aggregate CGWB data across every district in the same `agro_climatic_zone` instead of training on that one district alone. Same smoothing effect as a coarse regional estimate, no new external source.
2. **Insufficient data** — only if the zone itself lacks enough history. Shown honestly on the dashboard, never fabricated.

Every score in `crisis_scores` carries an `estimate_type` (`district_level` / `zone_fallback` / `insufficient_data`) so the dashboard can label which kind of estimate the person is looking at.

## The 10 features

All ten trace back to one of the three sources above — nothing is invented:

| # | Feature | Source |
|---|---|---|
| 1 | `GWL_current` | CGWB |
| 2 | `GWL_lag_3mo` | CGWB |
| 3 | `GWL_lag_6mo` | CGWB |
| 4 | `rainfall_current` | IMD |
| 5 | `rainfall_3mo_avg` | IMD |
| 6 | `monsoon_deficit_pct` | IMD (current vs. 30-yr normal) |
| 7 | `temperature` | ERA5 |
| 8 | `evapotranspiration` | ERA5 |
| 9 | `water_balance_proxy` | derived = rainfall − ET |
| 10 | `crop_season_flag` | derived, calendar rule (Kharif/Rabi/Zaid) |

## Project structure

```
AquaIQ/
├── data_ingestion/     # CSV/API parsers for CGWB, IMD, ERA5
├── preprocessing/      # cleaning, SARIMA gap-fill, feature engineering
├── models/             # linear_regression.py, fuzzy_logic.py, perceptron.py, lstm.py, xgboost_model.py, ensemble.py
├── api/                # Flask app + 6 REST endpoints
├── dashboard/          # React frontend (added Week 4)
├── db/                 # schema.sql + init_db.py
├── data/raw/           # downloaded, gitignored
├── data/processed/     # engineered features, gitignored
├── notebooks/          # exploratory / reproducibility notebooks
├── tests/              # pytest suite, target ≥70% coverage
└── config.yaml         # every hyperparameter, path, and threshold — nothing hardcoded
```

## API endpoints (built Week 9)

`GET /predict/{district_id}` · `GET /district/{district_id}` · `GET /shap/{district_id}` · `GET /history/{district_id}` · `GET /alerts` · `POST /simulate`

## Evaluation targets

LSTM Pearson r ≥ 0.85 · RMSE < 2.5cm · Linear Regression R² > 0.75, RMSE < 4.0cm · Test coverage ≥ 70% · API response < 3s

## Full project plan

See `AquaIQ_ProjectPlan.html` for the week-by-week task breakdown, and `AquaIQ_Context_Brief.md` for the full architecture/decision record — both are the source of truth for anything not covered here.
