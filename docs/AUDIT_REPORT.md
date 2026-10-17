# AquaIQ: End-to-End Prediction Pipeline Audit & Repair Plan

> Historical audit/plan from 12 October 2026. Current measurements, completed
> repairs and remaining limitations are in [the 17 October audit](../reports/AquaIQ_Audit_2026-10-17.md).
> Counts, metrics and proposed work below describe that earlier snapshot.

**Author:** Senior ML/Data Engineer  
**Date:** October 12, 2026  
**Repository:** Yasharthpoddar/AquaIQ (`main` at commit `0648958`)  
**Target Branch:** `fix/pipeline-repair`  
**Status:** Audit & Plan Approved by User — Ready for Branching and Execution

---

## 1. Executive Summary & Step 0 Recon Baseline

### 1.1 Environment & Baseline Test Suite
- **Operating System:** Windows 11 (PowerShell environment).
- **Working Tree Status:** 9 modified files in working directory (654 insertions, 264 deletions). Audit numbers and sampling were evaluated against the **working tree**, which contains partial pipeline mechanics fixes but none of the core data-integrity or leakage issues.
- **Python Environment:** Python 3.13.15 installed in `venv`.
- **Package Versions Reality Check:**
  - `requirements.txt` has not been edited.
  - The venv packages were installed without `-r requirements.txt`, resulting in newer versions across all pinned packages:
    - `pandas 3.0.6` (pinned: `==2.1.4`)
    - `numpy 2.5.4` (pinned: `==1.26.2`)
    - `xgboost 3.4.1` (pinned: `==2.0.3`)
    - `scikit-learn 1.9.1` (pinned: `==1.3.2`)
    - `statsmodels 0.15.0` (pinned: `==0.14.1`)
    - `scikit-fuzzy 0.5.0` (pinned: `==0.4.2`)
    - `flask 3.1.3` (pinned: `==3.0.0`)
    - `psycopg2-binary 2.9.13` (pinned: `==2.9.9`)
    - `pytest 9.1.1` (pinned: `==7.4.3`)
    - `mlflow 3.17.0` (pinned: `==2.9.2`)
- **Baseline Test Suite Run:**
  ```powershell
  venv\Scripts\python.exe -m pytest -v
  ```
  **Result:** `51 passed, 0 failed, 0 skipped, 1036 warnings in 51.70s`.
  - *Why tests give false assurance (D19):* Every API test in `tests/test_api.py` checks schema shape only and relies on fallback mechanisms (`get_model_components` returning `(50,50,50)`, `predict.py` falling back to synthetic linear forecasts, `alerts.py` catching exceptions with `zone_fallback`). Furthermore, `test_sarima_fill` emits statsmodels `ValueWarning: An unsupported index was provided. As a result, forecasts cannot be generated`, proving SARIMA actually fails and falls back silently to `ffill/bfill`.

### 1.2 Database & Data Asset Reachability
- **PostgreSQL Database:** Connected and reachable at `localhost:5432/aquaiq` (`aquaiq_user`).
  - `districts`: **1,291 rows** (782 distinct `(state, district_name)` pairs — confirms D1).
  - `raw_data`: **1,094,793 rows** across 3 sources.
  - `features`: **402,289 rows** (GWL scaled 0–1, 53k stored `'NaN'` values).
  - `crisis_scores`: **0 rows** (batch scoring never called — confirms D14).
  - `predictions`: **0 rows**.
- **Local Data & Checkpoints Existing:**
  - `data/raw/cgwb_combined.csv` (161 MB) & `cgwb-changes-in-depth-to-water-level.csv` (68 MB) present.
  - `data/raw/india_districts.geojson` (4 MB) present.
  - `data/processed/era5_district_monthly.csv` (7.7 MB) & `imd_rainfall_district_monthly.csv` (7.3 MB) present.
  - `data/processed/imd_climatological_normal.csv` (307 KB) present.
  - `models/checkpoints/aquaiq_xgb.json` (3.5 MB) & `scaler_params.json` present.

### 1.3 End-to-End Execution Order (Raw Files to Served Predictions)

#### Current Order (What exists today):
```
1. db/init_db.py → PostgreSQL schema (districts, raw_data, features, predictions, crisis_scores)
2. data_ingestion/ingest_imd_era5.py::load_districts_from_geojson → populates districts master table
3. data_ingestion/enrich_districts.py → assigns agro_climatic_zone
4. data_ingestion/ingest_cgwb.py → parses CGWB CSVs → inserts districts & raw_data (metric='GWL')
5. data_ingestion/imd_district_climatology.py → creates imd_rainfall_district_monthly.csv & imd_climatological_normal.csv
6. data_ingestion/era5_to_district.py → aggregates NetCDF → era5_district_monthly.csv
7. data_ingestion/ingest_imd_era5.py → inserts IMD & ERA5 into raw_data
8. preprocessing/pipeline.py → pivots raw_data → preprocessed_wide.csv, gap-fills, fits scaler
9. preprocessing/features.py → derives 10 features → writes features_matrix.csv and features table
10. models/xgboost_model.py → trains XGBoost forecaster → saves aquaiq_xgb.json (no purged CV, no model card)
11. models/backtest.py → fits ensemble weights → writes directly to config.yaml (no as_of safety, overwrites comments)
12. (NO batch scoring script — crisis_scores table stays empty)
13. api/app.py → Flask API serves endpoints; /predict scores on-the-fly with fabricated fallbacks
14. dashboard/ → React Vite frontend queries API
```

#### Target Order (After all D1–D19 fixes):
```
1–9: Ingestion & Preprocessing with D1 canonical IDs, D4 monthly grid, D2 physical monsoon deficit, D3 physical units, D5 CGWB aggregation, D6 NaN→NULL, D7 spatial join fallback
10. models/tiers.py & config.yaml → single source of truth for tier thresholds (30/60/80)
11. models/data_readiness.py → quarterly-cadence readiness check & agro-climatic zone aggregation for <60%
12. models/fuzzy_logic.py & linear_regression.py → physically calibrated components (LR trend in m/yr, drought frequency based on training 80th percentile depth, FIS on [0, 100])
13. models/xgboost_model.py → purged walk-forward CV (2014-16, 2018-19, 2020-21) on observed targets only → saves aquaiq_xgb.json + JSON model card
14. models/backtest.py → as_of-safe leakage-free backtest → fits 4 ensemble weights (LR, XGB, Drought, FIS) on validation drought windows (2015-16, 2018-19) → writes reports/backtest_results.json
15. models/score_all.py → batch-scores all districts as-of latest observation date → populates crisis_scores table
16. api/app.py → Flask API serves endpoints; /predict reads crisis_scores or computes with honest error handling (status: insufficient_data, data_age_months, forecast_origin)
17. dashboard/ → React Vite frontend with canonical ID polygon joins, dynamic tier styling from /api/config, and prominent staleness indicator
```

---

## 2. Step 1 Data Audit Results

All numbers below were extracted directly from the live PostgreSQL database and processed data files (stored in `reports/data_audit.json`).

### 2.1 Step 1.a — Districts Audit
| Metric | Value | Finding / Implication |
|---|---|---|
| Total rows in `districts` | **1,291** | Expected ~640–750 districts. Double the real count! |
| Distinct `(state, district_name)` | **782** | At least 509 duplicate records coexist. |
| Pure numeric IDs (`district_code`) | **567** | Ingested by `ingest_cgwb.py` (e.g. `632`, `602`, `308`). |
| Hyphenated IDs (`{state}-{name}`) | **724** | Ingested by `load_districts_from_geojson` (e.g. `MH-Pune`, `LA-Leh`). |
| Distinct districts in `raw_data` | **1,278** | Ingestion matched two disjoint ID namespaces! |
| Distinct districts in `features` | **1,278** | Pervasive across the entire feature store. |

### 2.2 Step 1.b — Raw Data & Join Coverage
| Source | Metric(s) | Total Rows | Distinct Districts | Min Date | Max Date | % NULL | % 'NaN' |
|---|---|---|---|---|---|---|---|
| **CGWB** | `GWL` | 89,601 | 1,083 | 1996-05-01 | 2023-03-01 | 0.0% | 0.0% |
| **IMD** | `rainfall` | 333,960 | 1,210 | 2002-01-01 | 2024-12-01 | 0.0% | 0.0% |
| **ERA5** | `temperature`, `evapotranspiration` | 671,232 | 1,216 | 2002-01-01 | 2024-12-01 | 0.0% | 0.0% |

- **Districts with all 4 base variables in `raw_data`:** 1,017 out of 1,278 (79.58%).
- **Current `features` table 4-variable completeness:**
  - Total `features` rows: 402,289.
  - Rows with all four variables (`gwl_current`, `rainfall_current`, `temperature`, `evapotranspiration` non-null and not `'NaN'`): **336,076 (83.54%)**.
  - **Audit Verdict:** Fails acceptance criterion (target is $\ge 95\%$). 16.46% of features rows lack at least one base variable due to ID mismatch and lack of continuous monthly grid reindexing.

### 2.3 Step 1.c — Measurement Cadence (CGWB Groundwater)
- **Observations by Month (CGWB):**
  - January (Month 1): **22,337**
  - May (Month 5): **20,587**
  - August (Month 8): **20,972**
  - November (Month 11): **21,677**
  - Peak-month subtotal: **85,573** (95.5% of all observations)
  - All other months combined: **4,028** (Feb: 224, Mar: 769, Apr: 1,153, Jun: 273, Jul: 294, Sep: 231, Oct: 484, Dec: 600).
  - Total observations: **89,601**.
- **Average gap between raw observations:** **3.09 months**.
- **Longest gap in history:** **89.95 months**.
- **Gaps $> 3$ months:** **23,192 occurrences**.
- **Audit Verdict:** CGWB data is **strictly quarterly/seasonal** (corresponding to the 4 national monitoring rounds: Post-monsoon Rabi, Pre-monsoon, Monsoon, Post-monsoon Kharif). It is **not monthly**. Row-based `.shift(-6)` or `.shift(1)` without explicit reindexing onto a complete calendar monthly grid creates catastrophic temporal distortions.

### 2.4 Step 1.d — Coverage by Year & Small $n_{test}$ Explanation
- **CGWB Observations by Year:**
  - 1996–2019: ~4,400 observations per year across ~845 districts.
  - 2020: 2,834 observations.
  - 2021: 1,146 observations.
  - 2022: **100** observations (across only 12 districts).
  - 2023: **22** observations (across only 10 districts).
  - 2024: **0** observations.
- **Why config.yaml walk-forward folds had $n_{test}$ of 75, 48, 34 against $n_{train} \approx 42.6\text{k}$:**
  Because the previous un-imputed dataset did not reindex to a complete monthly grid. The target was created via `.shift(-6)` on raw, sparse quarterly rows. A row in 2020 only received a target if a measurement existed exactly 6 rows later; in 2020–2022, CGWB coverage dropped sharply, leaving almost no un-imputed pairs.
- **Why the "12,000+ test points" claim was invalid:**
  In 2022, the features table has 12,252 non-NaN rows, but only 100 of those are real CGWB observations (99.2% are gap-filled/imputed). Evaluating ML models against 2022–2024 imputed data is evaluating against imputation artifacts, not ground truth.

### 2.5 Step 1.e — Features Table Units, Stored NaNs & Climatology
- **PostgreSQL Stored `'NaN'` Strings:**
  - `gwl_current`: **53,820 rows** stored as text `'NaN'`::real!
  - `gwl_lag_3mo`: **57,069 rows** stored as text `'NaN'`.
  - `gwl_lag_6mo`: **60,318 rows** stored as text `'NaN'`.
  - `rainfall_current`: **12,945 rows** stored as text `'NaN'`.
  - `temperature` & `evapotranspiration`: **11,153 rows** stored as text `'NaN'`.
  - *Root Cause:* `psycopg2` adapts Python `float('nan')` to `'NaN'`::float, which PostgreSQL does not treat as SQL `NULL`.
- **GWL Units:**
  - `MIN(gwl_current)`: **0.0**, `MAX(gwl_current)`: **1.0**.
  - **Verdict:** Stored GWL in the database is MinMax-scaled $[0, 1]$, **not in physical metres bgl**, yet the dashboard labels it "m bgl".
- **`monsoon_deficit_pct`:**
  - `MIN`: **-100.0%**, `MAX`: **0.0%**, `MEAN`: **-96.31%**.
  - Distinct values: 16,387 (e.g. `-99.9999%`, `-99.85%`).
  - *Root Cause:* In `features.py::build_rainfall_features`, MinMax-scaled rainfall ($0.0 - 1.0$) was subtracted from climatological normals in millimetres ($50 - 300\text{ mm}$): `(scaled - normal) / normal * 100`, mathematically forcing every value into $[-100\%, -90\%]$.

### 2.6 Step 1.f — Latest Observation Date (Forecast Origin)
- CGWB latest date: **2023-03-01**
- ERA5 latest date: **2024-12-01**
- IMD latest date: **2024-12-01**
- Effective Forecast Origin for Groundwater: **March 2023** (not late 2024). Any forecast beyond March 2023 is projecting into unobserved groundwater territory.

### 2.7 Step 1.g — Live Ensemble Scoring Distribution (60 Sampled Districts)
Running live scoring on 60 sampled districts with working-tree weights (`lr=0.0219`, `xgb=0.9651`, `drought=0.013`):
- **Overall Score Distribution:** Mean = **10.02**, Std = **7.06**, Min = **3**, Max = **39**.
  - 25th percentile: 5.75 | 50th percentile: 7.00 | 75th percentile: 11.25.
- **Component Breakdown:**
  - `lr_trend_score`: Mean = **50.03**, Min = **49.68**, Max = **50.38** (**completely degenerate near-constant 50.0**).
  - `xgb_risk_score`: Mean = **8.04**, Min = **1.02**, Max = **37.98** (skewed low because target was scaled $[0, 1]$).
  - `compute_drought_frequency`: Mean = **88.89**, Min = **5.43**, Max = **100.0** (degenerate due to quantile bug).
- **Tier Counts:**
  - **Safe (0–25):** **58 (96.7%)**
  - **Watch (26–37):** **1 (1.7%)**
  - **Warning (38–43):** **1 (1.7%)**
  - **Crisis (44–100):** **0 (0.0%)**
- **Verdict:** The current scoring pipeline is completely degenerate. 97% of districts score in the single digits ("Safe"), and Crisis is never triggered.

### 2.8 Step 1.h — Per-Year Observed vs Imputed GWL Share (Features Table)

| Year | Raw CGWB Obs | Features Total | Non-NaN GWL | NaN GWL | % Non-NaN | % Observed of Non-NaN |
|---|---|---|---|---|---|---|
| 1996 | 2,462 | 6,642 | 6,642 | 0 | 100.0% | 37.1% |
| 1997 | 3,318 | 10,070 | 10,070 | 0 | 100.0% | 32.9% |
| 1998 | 3,596 | 11,894 | 11,894 | 0 | 100.0% | 30.2% |
| 1999 | 3,744 | 12,504 | 12,504 | 0 | 100.0% | 29.9% |
| 2000 | 3,828 | 12,854 | 12,854 | 0 | 100.0% | 29.8% |
| 2001 | 3,922 | 13,010 | 13,010 | 0 | 100.0% | 30.1% |
| 2002 | 4,055 | 15,336 | 15,336 | 0 | 100.0% | 26.4% |
| 2003 | 4,210 | 15,336 | 15,336 | 0 | 100.0% | 27.5% |
| 2004 | 4,289 | 15,336 | 15,336 | 0 | 100.0% | 28.0% |
| 2005 | 4,312 | 15,336 | 15,336 | 0 | 100.0% | 28.1% |
| 2006 | 4,401 | 15,336 | 15,336 | 0 | 100.0% | 28.7% |
| 2007 | 4,450 | 15,336 | 15,336 | 0 | 100.0% | 29.0% |
| 2008 | 4,482 | 15,336 | 15,336 | 0 | 100.0% | 29.2% |
| 2009 | 4,501 | 15,336 | 15,336 | 0 | 100.0% | 29.3% |
| 2010 | 4,512 | 15,336 | 15,336 | 0 | 100.0% | 29.4% |
| 2011 | 4,520 | 15,336 | 15,336 | 0 | 100.0% | 29.5% |
| 2012 | 4,525 | 15,336 | 15,336 | 0 | 100.0% | 29.5% |
| 2013 | 4,529 | 15,326 | 12,986 | 2,340 | 84.7% | 34.9% |
| 2014 | 4,469 | 15,336 | 12,996 | 2,340 | 84.7% | 34.4% |
| 2015 | 4,639 | 15,336 | 12,996 | 2,340 | 84.7% | 35.7% |
| 2016 | 4,443 | 15,336 | 12,996 | 2,340 | 84.7% | 34.2% |
| 2017 | 4,495 | 15,336 | 12,996 | 2,340 | 84.7% | 34.6% |
| 2018 | 4,337 | 15,336 | 12,996 | 2,340 | 84.7% | 33.4% |
| 2019 | 4,381 | 15,323 | 12,983 | 2,340 | 84.7% | 33.7% |
| **2020** | **2,834** | 15,301 | 12,961 | 2,340 | 84.7% | **21.9%** |
| **2021** | **1,146** | 14,651 | 12,311 | 2,340 | 84.0% | **9.3%** |
| **2022** | **100** | 14,592 | 12,252 | 2,340 | 84.0% | **0.8%** |
| **2023** | **22** | 14,592 | 12,252 | 2,340 | 84.0% | **0.2%** |
| **2024** | **0** | 14,592 | 12,252 | 2,340 | 84.0% | **0.0%** |

**Critical Insight:** Ground truth for groundwater terminates effectively after 2021. Any evaluation fold targeting 2022–2024 evaluates on imputed values, not measurements.

### 2.9 Step 1.i — Data Readiness at Quarterly Cadence
Defined per expected observation round (4 rounds per year):
$$\text{readiness} = \frac{\text{actual CGWB observations}}{\text{year span} \times 4} \times 100$$

| Metric | Value |
|---|---|
| Total districts with any CGWB data | 1,083 |
| Above 60% readiness (quarterly cadence) | **1,057** |
| Below 60% readiness (quarterly cadence) | **26** |
| Average readiness | 91.6% |
| Districts with zero CGWB data | **208** |
| **Total districts needing fallback or `insufficient_data`** | **234** |

*(Note: The 234 count is currently inflated by D1 duplicate IDs; deduplication down to canonical IDs will merge many of the 208 zero-CGWB entries).*

---

## 3. Defect Verification Matrix (D1–D19)

| Defect ID | Layer | Description / Root Cause | Status | Severity | Fix Order |
|---|---|---|---|---|---|
| **D1** | Data | District identity dual ID collision (567 numeric vs 724 hyphenated, 1,291 rows in `districts` for 782 distinct pairs). | **CONFIRMED** | **Critical** | 1 |
| **D5** | Ingestion | CGWB chunk aggregation overwrites within-month averages due to `ON CONFLICT DO NOTHING` inside 100k chunk loop. | **CONFIRMED** | **Medium** | 2 |
| **D7** | Ingestion | Spatial assignment with `within` misses small districts or boundary points. | **CONFIRMED** | **Medium** | 3 |
| **D4** | Preproc | Gap filling index error; SARIMA fallback; missing monthly grid; look-ahead leakage in feature interpolation. | **CONFIRMED** | **Critical** | 4 |
| **D3** | Preproc | Scaling & physical units lost (stored $[0, 1]$ in DB); ERA5 PEV units need `-1000 * days_in_month` for mm/month. | **CONFIRMED** | **High** | 5 |
| **D2** | Features | `monsoon_deficit_pct` constant -96% (scaled $[0, 1]$ subtracted from mm normal; mismatched district names). | **CONFIRMED** | **High** | 6 |
| **D6** | Data/DB | Row-by-row DB writes; float NaN stored as text `'NaN'`::real (53,820 rows in `gwl_current`). | **CONFIRMED** | **High** | 7 |
| **D9** | Models | Component recalibration needed before backtest: LR slope in m/yr; drought frequency (depth > 80th percentile); FIS on [0, 100]; 30/60/80 tiers single source of truth in `config.yaml`. | **CONFIRMED** | **Critical** | 8 |
| **D11** | Models | XGBoost target shift leakage, missing folds, unpurged CV; evaluation on imputed data. | **CONFIRMED** | **Critical** | 9 |
| **D8** | Models | Backtest look-ahead leakage (`xgb_risk_score` queries latest row, not `as_of`); fit weights on validation drought windows. | **CONFIRMED** | **Critical** | 10 |
| **D10** | Spec | Spec drift: wire FIS as 4th component into ensemble (`w1·lr + w2·xgb + w3·drought + w4·fis`); real zone fallback aggregation for readiness $< 60\%$; ANN as demo. | **CONFIRMED** | **Medium** | 11 |
| **D12** | Models | Side scripts (`linear_regression.py`, `statistical_tests.py`) re-read raw CGWB independently instead of unified feature loader. | **CONFIRMED** | **Low** | 12 |
| **D14** | API/DB | No batch scoring script; `crisis_scores` table has 0 rows; `/api/alerts` samples on the fly. | **CONFIRMED** | **High** | 13 |
| **D13** | API | Fabricated fallback answers (`8.5 + 0.4*i`, `(50,50,50)`); silent error suppression; missing staleness metadata. | **CONFIRMED** | **Critical** | 14 |
| **D15** | API | Simulate endpoint uses heuristic rather than model inference; Option A approved (real XGB inference on rainfall, documented extraction heuristic). | **CONFIRMED** | **Medium** | 15 |
| **D16** | API | Health check drift (`xgboost_v1.json` vs `aquaiq_xgb.json`), Flask `debug=True`, CORS hardcoded. | **CONFIRMED** | **High** | 16 |
| **D17** | Dashboard | Hardcoded `localhost:5000`, name-based joins, hardcoded dates (`2024-07` to `2024-12`), missing staleness display. | **CONFIRMED** | **High** | 17 |
| **D18** | Hygiene | Missing `cdsapi` in `requirements.txt`; `backtest.py` strips `config.yaml` comments; missing unified `scripts/run_pipeline.py`. | **CONFIRMED** | **Medium** | 18 |
| **D19** | Testing | 51 tests pass purely due to catch blocks; no synthetic regression tests; no GitHub Actions CI. | **CONFIRMED** | **High** | 19 |

---

## 4. Approved Decisions & Execution Boundaries

1. **Canonical District Identity (D1):**
   - Single canonical key format: `{state_abbrev}-{Normalized_District_Name}` (e.g. `MH-Pune`, `KA-Bengaluru`).
   - Before migration: Crosswalk review table presenting every unmatched/ambiguous name and candidate will be displayed for user review; no silent fuzzy matching.
   - Run `pg_dump` of `raw_data`, `features`, `predictions`, `districts` before touching the DB.
   - Migration runs in a single transaction and keeps a `legacy_district_ids` table for rollbacks.
   - Collapsed row reconciliation rule: where two legacy IDs collapse onto one canonical ID with shared `(date, source, metric)`, average GWL and sum rainfall, logging every collapsed row.
   - Distinct count will reflect true Indian districts (782 distinct pairs). Districts without usable GWL get `insufficient_data` or labelled zone fallback, never borrowed history.

2. **Policy Simulation (D15):**
   - Option A approved: `rainfall_change_pct` re-runs feature transformation and real XGBoost inference.
   - `extraction_change_pct` is applied as an explicitly labelled heuristic delta with named coefficient in `config.yaml`.
   - Response schema matches SRS: `baseline_score`, `simulated_score`, `baseline_tier`, `simulated_tier`, `delta`, `extraction_heuristic_applied`.

3. **Tier Thresholds (D9):**
   - Standardized to `Safe 0–30, Watch 31–60, Warning 61–80, Crisis 81–100` per BR-01.
   - `config.yaml` is the single source of truth; exposed via API `/api/config` for backend and dashboard.
   - After recalibration: verify tier distribution. If $>85\%$ of districts end up in one tier, execution stops for user review.

4. **Scope & Ensemble Formulation (D10, D18):**
   - `cdsapi` added to `requirements.txt`.
   - Fuzzy FIS score wired into ensemble as 4th as-of safe component per BR-03 formula:
     $$\text{crisis\_score} = w_1 \cdot \text{lr\_trend} + w_2 \cdot \text{xgb\_risk} + w_3 \cdot \text{drought\_freq} + w_4 \cdot \text{fuzzy\_score}$$
   - Weights fitted out-of-fold on 2015–2016 and 2018–2019 drought validation windows.
   - `ann_classifier.py` remains as a labelled academic demo.

5. **Honest Evaluation & Purged Folds (D4, D11):**
   - Evaluating ML on imputed targets is strictly banned. In every fold, evaluate only on rows whose target month has an actual CGWB observation.
   - Revised fold structure:
     - Fold 1: Train Start–2013-06, Embargo 6m, Test 2014-01–2016-12 (expanding window)
     - Fold 2: Train Start–2017-06, Embargo 6m, Test 2018-01–2019-12 (drought validation window)
     - Fold 3: Train Start–2019-06, Embargo 6m, Test 2020-01–2021-12 (final test with meaningful observations)
   - Shipped production model retrained on all observed data (Start–2021-12).
   - Features at forecast origin $t$ use only data $\le t$. Between quarterly observations, LOCF (last observation carried forward) is used with a `months_since_observation` staleness indicator.

6. **Component Recalibration Pre-requisite (Plan Change D):**
   - D9 precedes D8: All 4 components calibrated to physical $[0, 100]$ scales before fitting ensemble weights.

---

## 5. Actionable Task List (Steps 3–11)

### Phase 1: Data Layer & Feature Engineering (D1–D7)
- [ ] **Step 3.1: D1 Canonical District Identity & Crosswalk**
  - [ ] Write failing test in `tests/test_districts_canonical.py` asserting uniqueness and join coverage.
  - [ ] Generate crosswalk review table mapping 567 numeric codes and GeoJSON strings to canonical `{state_abbrev}-{Normalized_Name}`.
  - [ ] Perform `pg_dump` backup of `raw_data`, `features`, `districts`.
  - [ ] Execute `db/migrations/001_canonical_districts.sql` in single transaction with `legacy_district_ids` table and logged row collapses.
  - *Acceptance:* 100% unique canonical districts; 0 orphaned FKs; crosswalk logged.
- [ ] **Step 3.2: D5 CGWB Chunk Aggregation**
  - [ ] Write regression test in `tests/test_ingest_cgwb.py` verifying multi-chunk month aggregation.
  - [ ] Update `data_ingestion/ingest_cgwb.py` to aggregate district-month values before insertion with `ON CONFLICT DO UPDATE`.
  - *Acceptance:* No dropped intra-month observations across chunk boundaries.
- [ ] **Step 3.3: D7 Spatial Join Fallback**
  - [ ] Update `data_ingestion/era5_to_district.py` and `imd_district_climatology.py` with centroid-nearest / representative polygon fallback for small/boundary districts.
  - *Acceptance:* Zero valid districts dropped in ERA5 and IMD aggregation.
- [ ] **Step 3.4: D4 Monthly Grid Reindexing & Bounded Imputation (No Look-Ahead)**
  - [ ] Write regression test verifying LOCF past-only imputation and `months_since_observation` tracking.
  - [ ] Update `preprocessing/pipeline.py` to reindex onto complete monthly grid (`MS`) from `2002-01-01` to `2024-12-01`.
  - [ ] Cap interpolation to $\le 3$ months past-only; add explicit `is_imputed` flags.
  - *Acceptance:* No backward interpolation leakage; strictly regular monthly grid per district.
- [ ] **Step 3.5: D3 Physical Units & Scaler Persistence**
  - [ ] Preserve physical units in DB (`m bgl` for GWL, `mm` for rainfall and ET, `°C` for temperature).
  - [ ] Update ERA5 PEV conversion: `et_mm_per_month = pev * -1000 * days_in_month`.
  - [ ] Move MinMax scaling to modeling stage and persist parameters in `models/checkpoints/scaler_params.json`.
  - *Acceptance:* `features` table stores physical units; scaler round-trips without loss.
- [ ] **Step 3.6: D2 Physical Monsoon Deficit Calculation**
  - [ ] Compute `monsoon_deficit_pct = (rainfall_mm - normal_mm) / normal_mm * 100` using physical mm and canonical ID matching against training normals ($\le 2019$).
  - *Acceptance:* Values span realistic range $[-100\%, +100\%]$; mean near $0\%$; no $-96\%$ artifact.
- [ ] **Step 3.7: D6 Bulk DB Upsert & Float NaN Cleanup**
  - [ ] Execute `db/migrations/002_clean_nans_to_null.sql` converting stored text `'NaN'` to SQL `NULL` and altering columns to `DOUBLE PRECISION`.
  - [ ] Update `features.py::write_to_db` to use `psycopg2.extras.execute_values`.
  - *Acceptance:* 0 `'NaN'` text strings in PostgreSQL; feature 4-variable completeness $\ge 95\%$.

### Phase 2: Models, Calibration & Evaluation (D9, D11, D8, D10, D12)
- [ ] **Step 3.8: D9 Component Calibration & Single Source of Truth for Tiers**
  - [ ] Standardize tier thresholds in `config.yaml` to `30 / 60 / 80`; wire `models/tiers.py` to read directly from config.
  - [ ] Recalibrate LR trend score: slope in physical metres/year scaled to $[0, 100]$.
  - [ ] Recalibrate drought frequency: share of training-period months where GWL depth exceeds training 80th percentile depth (as-of safe).
  - [ ] Calibrate Fuzzy FIS score on $[0, 100]$.
  - *Acceptance:* All 4 components produce non-degenerate distributions on $[0, 100]$; tier distribution verified ($<85\%$ in any single tier).
- [ ] **Step 3.9: D11 Purged Walk-Forward Validation & XGBoost Model Card**
  - [ ] Implement 6-month purge/embargo before validation/test boundaries in `models/xgboost_model.py`.
  - [ ] Configure revised 3-fold walk-forward validation (Test 2014-16, 2018-19, 2020-21).
  - [ ] Evaluate only on observed CGWB ground truth; log observed vs imputed target shares.
  - [ ] Benchmark against persistence and seasonal-naive baselines in physical metres RMSE.
  - [ ] Save trained model `models/checkpoints/aquaiq_xgb.json` and JSON model card.
  - *Acceptance:* RMSE reported on real observations; beats naive baselines; model card saved.
- [ ] **Step 3.10: D8 Leakage-Free Backtest & 4-Way Ensemble Weight Fitting**
  - [ ] Update `models/backtest.py` with strict `as_of` date parameter; assert no data $> \text{as\_of}$ is read.
  - [ ] Fit 4 weights ($w_1, w_2, w_3, w_4$) on out-of-fold validation predictions during 2015–2016 and 2018–2019 drought windows.
  - [ ] Save backtest results to `reports/backtest_results.json` without stripping `config.yaml` comments.
  - *Acceptance:* Test proves zero future data leakage; weights fitted exclusively out-of-fold.
- [ ] **Step 3.11: D10 & D12 Spec Alignment & Side Script Hygiene**
  - [ ] Wire FIS into live ensemble formula per BR-03 in `models/ensemble.py`.
  - [ ] Implement real agro-climatic zone data aggregation in `models/data_readiness.py` for districts with readiness $< 60\%$.
  - [ ] Unify feature loading across `linear_regression.py` and `statistical_tests.py`.
  - *Acceptance:* Ensemble uses 4 calibrated components; zone fallback aggregates zone data; side scripts share loader.

### Phase 3: Serving, API & Dashboard (D13–D17)
- [ ] **Step 3.12: D14 Batch Scoring Implementation**
  - [ ] Create `models/score_all.py` to batch-score all districts as-of forecast origin and populate `crisis_scores` table (`model_version`, `as_of`, `estimate_type`).
  - [ ] Update `/api/alerts` to query `crisis_scores` directly for Warning and Crisis districts.
  - [ ] Add `/api/config` and `/api/scores` endpoints.
  - *Acceptance:* `crisis_scores` fully populated for all districts; `/api/alerts` returns all active warnings.
- [ ] **Step 3.13: D13 Eliminate Fabricated Responses & Honest Error Handling**
  - [ ] Remove all hardcoded fallbacks (`8.5 + 0.4*i`, `(50,50,50)`).
  - [ ] Return HTTP 503 or `{"status": "insufficient_data", "reason": ...}` when data is missing.
  - [ ] Add `forecast_origin`, `last_observed_date`, `data_age_months`, and `model_version` to responses.
  - *Acceptance:* 0 fabricated responses; missing data honestly reported.
- [ ] **Step 3.14: D15 Policy Simulation Endpoint (Option A)**
  - [ ] Update `api/routes/simulate.py`: perturb rainfall features and run actual XGBoost inference.
  - [ ] Apply extraction delta as labelled heuristic with config parameter.
  - [ ] Return schema matching SRS keys (`baseline_score`, `simulated_score`, `delta`, `extraction_heuristic_applied`).
  - *Acceptance:* Rainfall changes reflect non-linear model output; extraction heuristic explicitly flagged.
- [ ] **Step 3.15: D16 API Health Check & Production Config**
  - [ ] Update `api/routes/health.py` to verify DB connection, correct model checkpoint name (`aquaiq_xgb.json`), and latest data date; return 503 if degraded.
  - [ ] Configure `debug=False` by default; read host/port/CORS from `config.yaml`.
  - [ ] Update `api_spec.md` to match actual contracts.
  - *Acceptance:* Health check reflects true system readiness; no hardcoded origins.
- [ ] **Step 3.16: D17 React Dashboard Repairs**
  - [ ] Add `VITE_API_URL` environment variable and dev proxy in `dashboard/vite.config.js`.
  - [ ] Update `MapComponent.jsx` to fetch tiers from `/api/config` and join GeoJSON polygons on canonical `district_id`.
  - [ ] Update `DistrictDetail.jsx` to render physical units (`m bgl`), display staleness/forecast origin, and handle `insufficient_data`.
  - [ ] Verify `npm run lint` and `npm run build` succeed cleanly.
  - *Acceptance:* Map renders using canonical IDs and API tier styling; staleness visible; clean production build.

### Phase 4: Hygiene, Pipeline Runner & CI (D18–D19)
- [ ] **Step 3.17: D18 Pipeline Runner & Reproducibility**
  - [ ] Add `cdsapi` to `requirements.txt`.
  - [ ] Create `scripts/run_pipeline.py` (cross-platform runner: ingest $\to$ preprocess $\to$ features $\to$ train $\to$ backtest $\to$ score_all).
  - *Acceptance:* Entire pipeline executes with a single command from raw files.
- [ ] **Step 3.18: D19 Robust Regression Suite & CI**
  - [ ] Add unit tests verifying each D-fix.
  - [ ] Add regression tests asserting 503 / `insufficient_data` when data/checkpoints are absent.
  - [ ] Add `.github/workflows/ci.yml` running pytest and frontend build.
  - *Acceptance:* Pytest coverage $\ge 70\%$; CI passes cleanly.

---

## 6. Verification Gates

| Gate | Acceptance Criteria | Verification Command |
|---|---|---|
| **Districts** | 100% unique `(state, name)` pairs, 1 ID scheme, $\ge 95\%$ 4-variable coverage | `python scratch/run_data_audit.py` |
| **Features** | Complete monthly grid per district, 0 `'NaN'` text strings, physical units preserved | SQL verification query on `features` table |
| **Models** | Purged walk-forward CV, benchmarked against naive baselines in metres, model card saved | `python models/xgboost_model.py` |
| **Backtest** | `as_of` safe (test proves no future row read), 4 weights fit on validation only | `pytest tests/test_backtest.py` |
| **Scoring** | Non-degenerate components, `crisis_scores` populated for all districts | `python models/score_all.py` |
| **API** | Zero fabricated responses, 503 on failures, `/api/health` reports true health | `pytest tests/test_api.py` |
| **Dashboard** | Leaflet joins on canonical IDs, dynamic tier colors from API, clean production build | `npm run lint && npm run build` in `dashboard/` |
| **Pipeline** | End-to-end execution succeeds with one command | `python scripts/run_pipeline.py` |
