# AquaIQ — Context Brief
*Updated 29 Sep 2026. Self-contained — written so it can be pasted into a new chat, tool, or given to a teammate with no other history. This revision folds in the full text of the current SRS, Algorithm Design doc, and UML set (uploaded 29 Sep 2026) — not just the summary version from the last regeneration.*

## What it is
AquaIQ forecasts groundwater depletion six months ahead for each of India's 640+ districts, via a two-layer ML system that outputs a 0–100 Crisis Score per district (tiers: Safe 0–30 / Watch 31–60 / Warning 61–80 / Crisis 81–100). Served through a Flask REST API and a React 18 (Vite) dashboard: choropleth map, district search, alerts, a policy simulator, and downloadable PDF reports.

## Course & team
- **Course:** Mini Project I, TE Sem V CSE, Sardar Patel Institute of Technology (SPIT), Mumbai — AY 2026–27 Odd Semester
- **Mapped to:** SIH25068 (Ministry of Jal Shakti — Real-Time Groundwater Evaluation using DWLR Data)
- **Team:** Yasharth Poddar (2024800092), Yash Sathe (2025801011), Ayush Khatavkar (2025801007)
- **Task rotation:** every workstream (data, core ML, advanced ML, API, dashboard, testing) rotates across all three people across the 14 weeks; presentation duty at each evaluation also rotates — no permanent presenter
- **History:** chosen after exploring a financial-AI concept (FinSentinel) first
- **Constraints:** no paid subscriptions beyond Colab Pro; no recreating already-submitted documents
- **Budget:** ~₹3,949 (Colab Pro + poster printing; everything else free/open-source) — *still unreconciled against the repo README, which says no paid compute is actually needed (see Open items)*

## System architecture
- **Layered view (per the UML deployment diagram):** Data Layer (PostgreSQL + CGWB/IMD/ERA5 sources) → Processing Layer (Preprocessing Pipeline → Feature Engineering) → ML Layer (XGBoost, Linear Regression, ANN Classifier, Fuzzy Logic FIS, Policy Recommendation) → API Layer (Flask REST API) → Presentation Layer (React Dashboard → Leaflet Map, Recharts)
- **Product perspective:** React dashboard (browser client) + Flask REST API (app server) + PostgreSQL + an offline/batch ingestion layer for CGWB/IMD/ERA5
- **Operating environment:** Python 3.x/Flask backend, PostgreSQL 14+, React 18 (Vite) frontend, model training on a standard laptop CPU or Colab/Kaggle
- **Core layer maps only to SPIT Sem I–V courses:** AS202 (Python for Data Science), CS205 (Statistical Methods), CS303 (AI & Soft Computing — Fuzzy Logic + Perceptron/ANN), CS204 (DBMS), CS301 (Distributed Computing), CS302 (Software Engineering)
- **Advanced/self-study layer:** XGBoost only (CS307, Sem VI)
- **Four user classes** (SRS §2.3): Policy Maker/Government Official (Crisis Scores, alerts, simulations, PDF downloads), Researcher/Analyst (forecasts, trends, model comparison, feature contributions), System Administrator — the project team (data ingestion/refresh, batch predictions, Data Readiness monitoring), General Public (search a district, view score/forecast, opt into tier alerts — no simulation or admin access)

## Functional requirements (SRS §3, FR-01–FR-12)
| ID | Requirement | Key detail |
|---|---|---|
| FR-01 | Data Ingestion | CGWB (~15,000 wells), IMD (rainfall + 30-yr normal), ERA5 (temp/ET) → `raw_data`; idempotent, chunked, validates district IDs against the master table |
| FR-02 | Preprocessing & Feature Engineering | Linear interpolation (short gaps) + SARIMA gap-fill (longer gaps) + MinMaxScaler → populates the 10-column `features` table |
| FR-03 | Trend Forecasting (Linear Regression) | Per-district; train 2002–2019, test 2023–2024; reports R²/RMSE/MAE; target R² > 0.75 |
| FR-04 | Crisis Tier Classification (Fuzzy Logic) | Mamdani FIS (scikit-fuzzy), 9 rules, inputs rainfall_deficit + depletion_rate → Safe/Watch/Warning/Crisis |
| FR-05 | Risk-Tier Classification (Perceptron ANN) | MLPClassifier, layers [10, 64, 4], ReLU, Adam; trained on the Fuzzy Logic tier output as labels; reports accuracy/precision/recall/F1/confusion matrix |
| FR-06 | Depletion Forecasting (XGBoost) | 500 trees, max_depth=6, lr=0.01, subsample=0.8, seed=42; walk-forward validation (rolling 2020→21→22→23 + 2023–24 held-out test); reports RMSE/R²/NSE |
| FR-07 | Ensemble Crisis Score | Weighted combination of LR forecast + XGBoost risk + historical drought frequency (CGWB-only); weights fit via 2015–16/2018–19 backtesting; stored in `crisis_scores` |
| FR-08 | District Search & Detail | Search by name or map click; score badge, readiness/confidence indicator, forecast chart, top-feature breakdown; zone fallback if readiness < 60% |
| FR-09 | Alerts | Districts at tier ≥ Warning, sorted by score descending |
| FR-10 | Policy Simulation | District + intervention type (rainfall change, extraction reduction, etc.) + magnitude → re-run the ensemble, show simulated vs. baseline |
| FR-11 | PDF Report | ReportLab-generated: score badge, forecast chart, feature breakdown, policy recommendations |
| FR-12 | Data Readiness & Zone Fallback | % of months with valid, non-imputed CGWB data; below 60% → aggregate by `agro_climatic_zone` instead of fabricating a district-specific number; affects ~75 of 640+ districts |

## Non-functional requirements (SRS §5)
- **Performance:** API response < 3s; batch prediction for all 640+ districts in one scheduled run; map renders within a few seconds
- **Reliability:** SARIMA gap-fill; zone-level fallback; idempotent/chunked ingestion (safe to re-run without duplicating rows)
- **Security:** no PII — all data is aggregate/district-level; input validation and structured error handling on every endpoint; HTTPS for any non-local deployment
- **Availability:** available for scheduled evaluations/demos; no 24×7 SLA required for an academic project
- **Scalability:** built for 640+ districts; schema allows sub-district granularity later without a redesign
- **Usability:** map-first navigation, one click through to any district; tier colours consistent across map, detail panel, and PDF
- **Maintainability:** modular pipeline (ingestion/preprocessing/core ML/advanced ML/API/dashboard separated by module); ≥ 70% automated test coverage (pytest); MLflow experiment tracking; pinned `requirements.txt`

## Business rules (SRS §6)
- **BR-01** Crisis tiers are fixed: Safe 0–30, Watch 31–60, Warning 61–80, Crisis 81–100
- **BR-02** Readiness < 60% → zone-level (`agro_climatic_zone`) fallback instead of a fabricated district-specific score
- **BR-03** Ensemble weights are fit via validation-set backtesting against the 2015–16 and 2018–19 droughts — never hand-set
- **BR-04** Core-layer models may only use concepts covered in SPIT Sem I–V coursework
- **BR-05** Only CGWB, IMD, and ERA5 data — and the ten features derived from them. GRACE-FO, GLDAS, NDVI/vegetation, irrigation, population, and soil-type data stay out unless the team explicitly reopens the decision
- **BR-06** The ensemble Crisis Score must remain computable from the three approved sources alone — no external drought dataset

## The five algorithms (Algorithm Design doc)
The current Algorithm Design doc specifies **five** algorithms, not six — zone-fallback logic lives inside the Ensemble algorithm itself rather than as a separate step (see Documentation consistency notes for the FR-numbering caveat on this doc).

1. **Linear Regression — 6-Month GWL Forecast.** Per-district OLS: `y = b0 + b1·t + b2·rainfall_3mo_avg + …`, train 2002–2019 / test 2023–2024. Accept if R² > 0.75 AND RMSE < 4.0 cm; else flag the district for zone-level fallback (FR-12/BR-02).
2. **Fuzzy Logic — Crisis Assessment.** Mamdani FIS; inputs rainfall_deficit (rd) and depletion_rate (dr), each fuzzified Low/Medium/High via triangular membership functions. Example rules: rd=High & dr=High → Critical; rd=Medium & dr=Medium → Moderate; rd=Low & dr=Low → Low. Defuzzified via weighted centroid into a 0–100 score + tier.
3. **ANN (Perceptron) — Risk-Tier Classification.** Training labels come from the Fuzzy Logic tier output, not independent ground truth. 10-feature input (MinMax-scaled) → 64-unit ReLU hidden layer → 4-unit softmax output (Safe/Watch/Warning/Crisis). Cross-entropy loss, Adam optimiser; inference returns the predicted tier plus confidence (max softmax probability).
4. **XGBoost — Depletion Risk + Feature Importance.** 500 trees, max_depth=6, learning_rate=0.01, subsample=0.8, seed=42. Walk-forward validation: rolling folds 2020→2021→2022→2023, plus a 2023–2024 held-out test — deliberately not one static split. Feature importances are gain-based, averaged across folds; the top 3 feed the district-detail explanation.
5. **Ensemble AquaIQ Crisis Score.** Checks each district's Data Readiness Score: ≥ 60% → district-level forecast + risk; below that → aggregate to the district's `agro_climatic_zone`; if zone data is still insufficient → return `insufficient_data` (BR-02). Computes `fuzzy_score` from the Fuzzy Logic FIS on (rd, dr) and `drought_freq` (% of past months below the district's own 20th-percentile GWL, from CGWB history alone). Final score = `w1·forecast + w2·risk + w3·fuzzy_score + w4·drought_freq`, with weights fit on the 2015–16/2018–19 backtests (BR-03). Stores `{score, tier, estimate_type, ensemble_weights}` in `crisis_scores` and feeds a policy recommendation.

## Database schema (PostgreSQL — per the ER diagram)
| Table | Fields |
|---|---|
| `districts` | district_id (PK) · district_name · state · agro_climatic_zone · geojson_name |
| `raw_data` | id (PK) · district_id (FK) · date · source (CGWB/IMD/ERA5) · metric · value |
| `features` | id (PK) · district_id (FK) · date · GWL_current · GWL_lag_3mo · GWL_lag_6mo · rainfall_current · rainfall_3mo_avg · monsoon_deficit_pct · temperature · evapotranspiration · water_balance_proxy · crop_season_flag · data_readiness_score |
| `predictions` | id (PK) · district_id (FK) · forecast_date · model_type · predicted_gwl · confidence_lower · confidence_upper |
| `crisis_scores` | id (PK) · district_id (FK) · score_date · crisis_score · tier · ensemble_weights (JSON) |

*(`crisis_scores` doesn't yet have an `estimate_type` column — see Documentation consistency notes.)*

## Data & features
- **Exactly 3 sources:** CGWB (india-wris.nrsc.gov.in, ~15,000 borewells), IMD (imdpune.gov.in, monthly district rainfall + 30-yr normal), ERA5 (cds.climate.copernicus.eu, temperature + evapotranspiration)
- **Deliberately dropped, not to be reintroduced:** GRACE-FO, GLDAS, NDVI/MODIS, irrigation_fraction, population_density, soil type, rainwater-harvesting infrastructure — reasoning goes in the ESE report's Limitations & Future Work section, not silently omitted
- **Ten features:** GWL_current, GWL_lag_3mo, GWL_lag_6mo, rainfall_current, rainfall_3mo_avg, monsoon_deficit_pct, temperature, evapotranspiration, water_balance_proxy (rainfall − ET, derived), crop_season_flag (Kharif Jun–Oct / Rabi Nov–Mar / Zaid Apr–May)
- **Real CGWB data:** actual date range 2013–2023, quarterly measurement cadence (needs interpolation), ~75 of 640+ districts need zone-level fallback
- **Merged historical dataset** (1996–2017 + 2013–2023): ~1.2M clean rows after deduplication

## System design (UML set)
- **Use-case actors:** Policy Maker, District Water Authority, General Public, System Admin. Key use cases: View Alerts / Run Policy Simulation / View Choropleth Map (Policy Maker); View Choropleth Map / Export PDF Report / View District Forecast (District Water Authority); View District Forecast (General Public); Ingest Data / Train Models / Compute Crisis Scores / Monitor System Health (System Admin)
- **Class structure (key classes):** `FlaskAPI` (get_prediction, get_history, get_alerts, simulate, health_check) · `District` · `RawData` · `PreprocessingPipeline` (interpolate_gaps, sarima_fill, fit_transform, run_pipeline) · `Feature` · `XGBoostModel` (load_feature_matrix, create_target, temporal_split, train_xgboost, walk_forward_validate, evaluate_on_test) · `LinearRegressionModel` · `ANNClassifier` · `FuzzyLogicFIS` · `CrisisScore` · `PolicyRecommendation` · `Prediction`
- **Sequence flow (district click → score):** Dashboard User clicks a district → React Frontend sends `GET /api/predict/{district_id}` → Flask selects features from PostgreSQL → calls `XGBoostModel.predict` and `FuzzyLogicFIS.compute_crisis_score` → JSON response → frontend renders the score and forecast chart

## Scope decisions (what changed and why)
- **10 Sep 2026:** PyTorch LSTM (CS321) and SHAP (CS424) dropped from scope — XGBoost is now the only advanced/self-study model. With one advanced model left, the ensemble design and walk-forward backtesting are the stronger self-study talking points at the ESE.
- **19 Sep 2026:** General Public added as a 4th user class. Evaluator-facing SRS cleaned (no revision history, no SIH25068/Smart India Hackathon mention). Decided **not** to demo a live prototype at Phase II — a separate runnable notebook (`AquaIQ_Prototype.ipynb`) was built and tested working, but isn't part of the submission.
- **Database:** SQLite → PostgreSQL.

## Evaluation timeline
| Milestone | Date | Marks | Status (as of 29 Sep 2026) |
|---|---|---|---|
| Phase I | 17 Aug 2026 | 50 · guide only | Done |
| Phase II | 10 Sep 2026 | 25 — SRS 10 / UML 5 / Algorithm Design 5 / Presentation 5 | Done |
| Phase III | 30 Sep 2026 | 50 · guide only | Upcoming |
| Phase IV | 12 Oct 2026 | 50 · guide only | Upcoming |
| ESE | 2 Nov 2026 | 100 · industry expert / alumni panel | Upcoming |

Plan runs 14 weeks from 1 Aug 2026; week boundaries are deliberately irregular so each evaluation lands cleanly inside a week (see `AquaIQ_ProjectPlan.html` for the full week-by-week breakdown).

## Open items
1. **NOT NULL constraint bug** — the districts-table build script fails for the 72 districts that only have historical (pre-2013) coverage. Pending fix.
2. **Run the ensemble-weight backtest** — the formula and method are fully specified (`score = w1·forecast + w2·risk + w3·fuzzy_score + w4·drought_freq`, fit against the 2015–16 and 2018–19 droughts, BR-03); fitting w1–w4 against those windows hasn't actually been run yet.
3. **Run XGBoost's walk-forward validation** — fold structure is specified (rolling 2020→21→22→23, plus a 2023–24 held-out test); executing it is still pending, same pass as #2.
4. **SPIT title page course list** — open question flagged for the guide, not yet confirmed: the student confirmation table allows CS301/CS302 as acceptable Sem I–V courses, but the faculty certification line restricts to Sem I–IV only, and CS303 (used to justify Fuzzy Logic/Perceptron ANN as core) isn't on the table at all.
5. **Budget line** — ~₹3,949 (mostly Colab Pro) hasn't been reconciled with the repo's own README, which says no paid compute is actually needed for the current model stack.
6. **FR numbering mismatch between the SRS and the Algorithm Design doc** — the Algorithm Design doc labels the five algorithms FR-04 through FR-08; the current SRS has the same five at FR-03 through FR-07 (Linear Regression = FR-03, Fuzzy Logic = FR-04, Perceptron ANN = FR-05, XGBoost = FR-06, Ensemble = FR-07). The Algorithm Design doc's XGBoost step also references feature importances "feeds FR-09/explain" — the current SRS's FR-09 is Alerts, not an explainability endpoint, which suggests the Algorithm Design doc was written against an earlier SRS draft (likely from before SHAP/explainability was dropped) and hasn't been fully reconciled to the current FR numbering. Worth fixing in one of the two docs before submission.
7. **`crisis_scores` schema is missing an `estimate_type` column** — the Ensemble algorithm's own pseudocode stores `{score, tier, estimate_type, ensemble_weights}`, but the ER diagram's `crisis_scores` entity only has `id, district_id, score_date, crisis_score, tier, ensemble_weights`. Needs a column added (or the algorithm spec adjusted) before implementation.

**Accepted, not an action item:** the already-submitted (frozen) SRS on file from 3 Aug still lists the old 11-feature scope and references GRACE-FO/SHAP/LSTM/SQLite — that's the original, pre-pivot draft, not the current one. It's explained in the ESE report's Limitations & Future Work section, not silently fixed.

## Documentation consistency notes (lower-priority, worth a quick look)
- The UML use-case actor list (Policy Maker, District Water Authority, General Public, System Admin) doesn't include "Researcher/Analyst" as its own actor, and introduces "District Water Authority" as a name not used in the SRS's four official user classes. Likely just diagram simplification, but worth a glance.
- The `FlaskAPI` class's five methods (get_prediction, get_history, get_alerts, simulate, health_check) include an operational `health_check()` but nothing named for FR-08's District Search & Detail specifically — probably served by combining get_prediction + get_history, but worth a quick confirm that the detail view doesn't need its own endpoint.

## Documentation on file
- `AquaIQ_IEEE_Proposal_v2.docx` — IEEE-format project proposal
- `AquaIQ_SRS_IEEE830.docx` — SRS in IEEE 830-1998 format, 24 pages, v1.0
- `AquaIQ_SRS.docx` — current evaluator-facing SRS (cleaned 19 Sep 2026; full content reviewed 29 Sep 2026)
- `AquaIQ_UML_Diagrams.docx` — use case, class, sequence, and deployment/layered diagrams, plus an ER diagram (12 Sep 2026; full content reviewed 29 Sep 2026)
- `AquaIQ_Algorithm_Design.docx` — 5 algorithms (not 6 as previously logged): Linear Regression, Fuzzy Logic, Perceptron ANN, XGBoost, Ensemble (zone-fallback logic lives inside Ensemble); design/implementation-status only, no prototype demo
- `AquaIQ_Prototype.ipynb` — runnable prototype notebook, built and tested working, not part of the submission
- `AquaIQ_Phase2_Flow.docx` — Phase II evaluation-day run-of-show (updated 19 Sep 2026); still references the old 5-vs-current algorithm count per earlier notes — not re-checked against the SRS/Algorithm Design content in this pass
- `AquaIQ_Phase2_Script.docx` — full spoken presentation script (updated 19 Sep 2026) — same caveat as above
- `AquaIQ_SPIT_MiniProject.docx` — SPIT official title page
- `AquaIQ_ProjectPlan.html` — 14-week interactive project plan (last regenerated 24 Sep 2026)
- Portable context brief (this document; this regeneration: 29 Sep 2026, with full SRS/Algorithm Design/UML content folded in)

## Repository
https://github.com/Yasharthpoddar/AquaIQ
