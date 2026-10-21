# AquaIQ — Twelve-Month Groundwater Research Prototype

AquaIQ is an academic research prototype. Its district graph defaults to an **experimental monthly scenario for the next 12 full calendar months from today**, using only the selected district's own source-marked observed history. All 725 canonical district IDs are supported by the view; current evidence meets the method's history requirements in 548, with explicit unavailability in the other 177. The in-memory seasonal/trend scenario is **unvalidated**; it estimates the old observation gap and omits weather and extraction effects. It is not evidence of nationwide accuracy or real-time forecasting skill.

The separate **historical M+12 research** mode preserves the question of whether groundwater depth 12 calendar months after an observed origin M improves on an annual baseline. Its fixed XGBoost artifact is limited to the Adilabad source-name/polygon-agreement population and estimates only M+12; months 1–11 remain gaps in that mode. Its default observed origin is May 2026, targeting May 2027, with unavailable ML because weather is missing and the artifact is historical-only. Explicit January 2024 targets January 2025. These historical calculations are distinct from the default monthly scenario; neither inherits the other's validation. Acquisition/publication/receipt times, well continuity and datum remain unverified.

The original navigation, Home layout, map, summary cards and district views remain in place over a registry of 725 canonical districts. The six-month endpoint and explicitly requested monthly climate projection (horizons 1–6) remain available as separate API products. The project-defined 0–100 risk index still uses its legacy components; it has not been recalibrated for twelve months. Registry coverage establishes neither observed coverage nor nationwide predictive accuracy. The graph's twelve-position domain does not establish a validated monthly trajectory. Neither prospective skill nor production readiness has been established.

The repaired pipeline keeps groundwater in metres below ground level, rainfall and evapotranspiration in millimetres per month, and temperature in degrees Celsius. Features and model bundles carry generation identifiers, units, dates, and checksums. Missing evidence produces an unavailable result. Zone fallback remains confined to legacy products; the twelve-month research path never borrows another district's model.

## Primary twelve-month research experience

The user adopted twelve months as the primary **research objective**, not because the experiment proved superiority. On 792 paired conditional historical cases in 33 Telangana districts:

| Method | MAE (m) | RMSE (m) |
|---|---:|---:|
| Persistence = annual seasonal naive | 1.191 | 1.458 |
| Expanding XGBoost | 1.159 | 1.420 |
| Per-district Linear Regression | 1.928 | 2.456 |
| Separate twelve-month HGB | 1.222 | 1.505 |

The paired XGBoost RMSE-difference interval is **−0.317 to +0.264 m**, crossing zero. Its advantage reverses in 2025 and on unchanged-panel cases. The exact-agreement Adilabad sensitivity favored the baseline (RMSE .877 m versus XGBoost 2.518 m on 24 cases). These are preserved expanding-window study results, **not accuracy scores for the new fixed-cutoff application artifact**. The latter uses the same fixed XGBoost settings with a 2021-12-31 training-label cutoff and a twelve-month embargo, and remains an unselected historical comparator. HGB has not been refitted for the application or approved for real shadow prediction.

Use the [original twelve-month study](reports/candidates/twelve_month_horizon_20261020/REPORT.md), its frozen protocol and saved predictions for evaluation. The [application finalization report](reports/candidates/twelve_month_horizon_finalization_20261020/REPORT.md) records the separate artifact, scope, contracts, checks and limitations. Earlier reports retain their original decisions and dates; the later change of primary research objective does not rewrite their evidence.

The new fixed-cutoff artifact's own **24-case Adilabad historical check** is worse than the annual baseline: XGBoost MAE **2.145 m**, RMSE **2.664 m**, R² **−.101**; baseline MAE **.645 m**, RMSE **.877 m**, R² **.881**. These are previously inspected historical cases, not a new blind test. Its predictions reload consistently but differ from the old 2024 fit despite matching training rows and settings; the exact cause remains unresolved. No refitting or tuning was used to chase the old outputs.

For a restored local demonstration, use the existing environment and run `python -B -m api.app` and `npm.cmd --prefix dashboard run dev -- --host 127.0.0.1 --port 5173 --strictPort` in separate terminals, with `FLASK_HOST=127.0.0.1` and `FLASK_DEBUG=false`. Home retains its original layout; `/research` remains an optional file-only page rather than the main experience. The research forecast/graph APIs do not need the database; legacy scores/history/monthly projections do. The guarded local demonstration intentionally returns HTTP 403 for legacy requests, rather than bypassing that boundary or fabricating scores. `AQUAIQ_RESEARCH_CONFIG` optionally selects a local descriptor; its default is `research/twelve_month_app.json`. Required local model/snapshot/manifests are hashed separately from active six-month checkpoints. Missing or incompatible assets produce explicit unavailable results. See the [graph implementation report](reports/candidates/twelve_month_graph_only_20261021/REPORT.md) for current behavior and the finalization report for original artifact details. Do not run setup, refresh, scoring, migrations or training merely to display a demonstration.

## Legacy six-month scope and historical evidence

The submission preserves the existing XGBoost, ANN/MLP, Linear Regression and Fuzzy Logic components. ANN learns fuzzy-generated labels; its agreement is not independent crisis-outcome accuracy. HGB remains a locked research candidate, with real predictions abstained (`shadow_artifact_not_approved`). Real shadow issuance is currently **no-go** because source availability, stable well panels, current observations and effective issuance lead remain unresolved.

The saved primary historical benchmark uses the **same 209 observed-flag cases in 32 districts**, with origins July 2019–September 2022 and targets January 2020–March 2023. Values below are existing candidate experiment results, not a new evaluation of the dashboard's current monthly serving path. No six-month model was retrained or reselected for this finalization.

| Method | MAE (m) | RMSE (m) | R² |
|---|---:|---:|---:|
| Persistence | 1.234 | 3.698 | .809 |
| Seasonal naive | **1.049** | **2.132** | .937 |
| Ridge, existing benchmark | 1.381 | 2.573 | .908 |
| Random Forest, existing benchmark | 1.290 | 2.558 | .909 |
| XGBoost candidate | 1.432 | 3.225 | .855 |
| Locked HGB research candidate | 1.327 | 3.060 | .869 |

**Seasonal naive outperformed HGB and the other tested ML candidates on primary MAE and RMSE.** HGB was selected on validation. Its RMSE advantage over persistence has a district-bootstrap 95% difference interval crossing zero (−1.234 to +.038 m); its primary MAE is worse than persistence. No reliable prospective ML winner has been demonstrated. R² is not an accuracy percentage. The historical period was previously inspected, sampling is uneven, and well composition/freshness are uncertain; this is not a pristine blind or prospective test.

Submission evidence: [finalization checklist](reports/submission_finalization_20261019/FINALIZATION.md), [scientific validation](reports/scientific_validation_audit_20261018/REPORT.md), [safe reporting fixes](reports/post_audit_safe_fixes_20261019/REPORT.md), [provenance and issuance feasibility](reports/provenance_issuance_20261019/REPORT.md), and [saved selection experiment](reports/candidates/six_month_selection_20261017/REPORT.md). The issuance report distinguishes the nominal origin+6 target from six full months after actual issuance; no horizon or feature definition was changed to resolve that constraint.

A later **conditional Telangana historical comparison** contains 594 paired cases across 33 districts: seasonal-naive RMSE **1.440 m**, expanding XGBoost **1.472 m**, and locked historical HGB **1.790 m**. Seasonal naive again outperformed the tested ML methods. Serious source-name/coordinate conflicts and unverified historical input availability prevent operational or trustworthy location-specific accuracy claims. See the [publication guide and evidence index](reports/github_release_20261020/PUBLICATION.md) for the preserved reports, corrected district predictions, local-only evidence exclusions and public provenance summary. These are historical results; HGB remains abstained and real shadow issuance remains NO-GO.

For presentation, distinguish **source-marked monthly observations**, **bounded forward-filled values**, **estimated current depth**, and **future projections under weather assumptions**. Source flags do not independently certify fresh acquisition, datum continuity or a fixed well panel. The index is uncalibrated and extraction is heuristic sensitivity, not a causal policy estimate. Keep unavailable results visible rather than fabricating a demonstration value.

The repository tracks code and reports, but raw/processed data and trained checkpoints are Git-ignored; a GitHub clone alone does not contain the populated database or those runtime assets. Use the existing configured local environment for any separately authorized runtime demonstration, or present the committed historical reports offline. Fresh installation, hosted deployment and runtime demonstration were not verified by submission finalization. The setup, refresh, training, scoring and replay commands below are maintainer references, **not steps to rerun for this frozen submission**; they can change state or compute new outputs.

## Setup

Use Python **3.13**, PostgreSQL **18** (the local verification version), and Node **22.12 or later**. The dashboard's Vite dependencies require Node `^20.19.0 || >=22.12.0`; CI uses Node 22. Create a PostgreSQL database and user, copy `.env.example` to `.env`, and enter that database's credentials. Keep `.env` private.

On Windows PowerShell, run these commands from the project directory:

```powershell
.\setup.ps1
.\venv\Scripts\Activate.ps1
```

On Linux or macOS:

```bash
bash setup.sh
source venv/bin/activate
```

Setup installs `requirements.txt`, checks dependency consistency, and initializes the schema and additive provenance migration. Database initialization can be repeated. Setup reuses an existing Python 3.13 environment and stops on errors. Optional extras are installed separately:

```bash
python -m pip install -r requirements-download.txt  # CDS downloads and your own CDS credentials
python -m pip install -r requirements-tracking.txt  # MLflow experiment tracking
```

Core pins match the environment used for local repair verification. They include NetworkX, which fuzzy inference needs. Optional CDS downloads are not part of the core runtime or the offline verification suite.

## Data and pipeline

Place the district GeoJSON and source files under `data/raw/` using the paths in `config.yaml` and the ingestion modules. CGWB inputs contain observations; IMD uses daily `.grd` files; ERA5 processing uses a local NetCDF artifact with explicit source units. Download access and authentication are managed through the source portals.

| Source | Data |
| --- | --- |
| CGWB / India-WRIS | Observed groundwater depth |
| IMD | Daily rainfall aggregated to complete monthly totals |
| ECMWF ERA5 | Temperature and evapotranspiration |
| District boundaries | State-qualified district polygons for spatial aggregation |

Regenerate climate artifacts before ingesting them when replacing legacy processed files:

```bash
python -m data_ingestion.era5_to_district
python -m data_ingestion.imd_district_climatology --raw-dir data/raw/imd
```

Both outputs include manifests. The weather ingester rejects artifacts without matching provenance and records corrected existing weather values in `data/processed/weather_corrections/`. Existing CGWB observations are retained.

Incremental daily rainfall can now be staged with bounded retries and resume support:

```powershell
python -m data_ingestion.imd_realtime --dates 2025-01-01 2025-06-15 2025-09-30 --download --staged-dir data/raw/updates/<run>/overlap
python -m data_ingestion.imd_realtime_comparison --annual-file data/raw/updates/20261013/imd/Rainfall_ind2025_rfp25.grd --annual-year 2025 --staged-dir data/raw/updates/<run>/overlap --dates 2025-01-01 2025-06-15 2025-09-30 --output reports/candidates/<run>/overlap.json
python -m data_ingestion.imd_realtime --start 2026-01 --end 2026-09 --download --staged-dir data/raw/updates/<run>/daily
```

Replace `<run>` with a staging directory name. The default command without `--download` makes an offline plan. Interrupted runs reuse only files that still pass their source/date/checksum/grid checks. Incomplete downloads return exit code 1 and save `download_progress.json`; a passing sampled comparison returns 0, while differences requiring review return 2. Format validation alone does not establish rainfall product identity. Provisional and annual products can differ after quality control; investigate differences instead of widening tolerances to force a pass.

After sampled overlap and every daily file are verified, `python -m data_ingestion.imd_realtime_monthly --start 2026-01 --end 2026-09 --staged-dir data/raw/updates/<run>/daily --overlap-report reports/candidates/<run>/overlap.json --output reports/candidates/<run>/rainfall_monthly.csv --normals-output reports/candidates/<run>/rainfall_normals.csv` creates candidate artifacts. It requires the configured boundaries and writes only candidate/update folders. The data remains provisional and no production ingestion happens automatically. The latest staging result and repeat commands are in `reports/Prediction_Pipeline_Implementation_2026-10-14.md`.

Run the complete pipeline after the source inputs are available:

```bash
python scripts/run_pipeline.py --step all
```

Ingestion includes state-qualified district/map matching and zone enrichment
before weather is loaded. Zone labels are the project's documented state-level
proxies; they are not independently verified district aquifer classifications.

For a database that already contains the ingested source data, run the derived stages individually:

```bash
python scripts/run_pipeline.py --step preprocess
python scripts/run_pipeline.py --step features
python scripts/run_pipeline.py --step train
python scripts/run_pipeline.py --step backtest
python scripts/run_pipeline.py --step score_all
```

Feature rebuilding replaces the derived feature table in one transaction. Back up the database before a full rebuild. A sample preprocessing run is for inspection and cannot replace the production feature generation. Model training uses exact calendar targets and only observed future labels; bounded causal carry-forward values may be input features but never become observed labels. Rainfall anomalies use prior-year same-month history, excluding future climatology.

Sample and CSV-only checks write isolated artifacts, preserving the active feature CSV, manifest, database and checkpoint:

```powershell
python -m preprocessing.pipeline --sample 10
python -m preprocessing.features --input-dir reports/samples
python -m preprocessing.features --sample 10
python -m preprocessing.features --csv-only
```

The first two commands build a sample timeline and its features under `reports/samples`. The third samples the production preprocessing input into the same isolated directory. `--csv-only` writes a full candidate feature matrix under `reports/candidates`. Production model loading and training reject sample-only manifests.

The configured serving model uses the label cutoff in `config.yaml` (`2019-12-31`). A six-month embargo separates training from evaluation origins; historical holdout periods have been inspected during development and are not pristine blind tests. Training publishes an immutable model/card bundle through one atomic manifest. The training stage builds both the historical endpoint model and the separate monthly climate model. To rebuild only the monthly model, run `python -m models.climate_forecast`; it writes its independent verified bundle and `reports/climate_forecast_evaluation.json`. These are maintenance operations, not submission checks. Backtests and synthetic tests write separate reports and cannot replace the historical checkpoint or automatically promote candidate weights.

Use the evaluation-only or candidate modes for model experiments:

```powershell
python -m models.climate_forecast --eval
python -m models.climate_forecast --candidate-checkpoint reports/candidates/monthly/candidate.json
python -m models.climate_forecast --eval --checkpoint reports/candidates/monthly/candidate.json --output reports/candidates/monthly/saved_evaluation.json
python -m scripts.validate_monthly_candidates --run --fold all --n-jobs 1
```

Saved evaluation uses the bundle's recorded cutoff and never fits or republishes it. Candidate training writes a separate pointer, model-card sidecar and report. The development runner excludes all 2020 onward rows before label construction, uses fixed chronological panel folds with six-month embargoes, and writes only experimental candidate reports. Without `--run` it prints a plan. These development comparisons are for model selection, not independent interval calibration or current-period accuracy; later independent observations are still required.

Climate reports are specific to their recorded feature generation. The preserved `reports/climate_forecast_review.json` reviews `physical-v3-causal-monthly-90a24f1f2574`; it is historical evidence and does not verify a later generation. For the release being inspected, compare `data/processed/feature_manifest.json`, the card resolved by `models/checkpoints/aquaiq_monthly_climate.json`, and `reports/climate_forecast_evaluation.json`. Check their generation and source/model identities before citing results; retain old reports with their original references.

For batch scoring, an optional historical cutoff filters observation-month labels through that date; it does not establish provider publication or actual input availability at that time:

```bash
python scripts/run_pipeline.py --step score_all --as-of 2023-03-31
```

`--as-of` on the orchestrator applies to batch scoring. To rebuild an earlier input timeline explicitly, use `python -m preprocessing.pipeline --as-of YYYY-MM-DD`, then regenerate its features and matching model bundle. Scoring rejects future cutoffs and cannot serve a bundle against a different feature generation.

## API and dashboard

Start the API from an activated environment:

```bash
python -m api.app
```

For a local WSGI process on Windows or Linux:

```bash
waitress-serve --listen=127.0.0.1:5000 --call api.app:create_app
```

Start the dashboard in a second terminal:

```bash
cd dashboard
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to `http://localhost:5000`. The API routes are:

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Check PostgreSQL access and both matching verified model bundles |
| `GET /api/config` | Expose score configuration and calibration status |
| `GET /api/scores` | Read one complete scoring run for the current model and feature generation |
| `GET /api/district/<district_id>` | District score, components, readiness, and evidence metadata |
| `GET /api/history/<district_id>` | Monthly features with observed/imputed flags and strict JSON nulls |
| `GET /api/predict/<district_id>?months=6` | One six-calendar-month research endpoint from the last observed month |
| `GET /api/predict/<district_id>?window=next_six_months` | Six future monthly XGBoost projections using rainfall and weather assumptions |
| `GET /api/alerts` | Scores and unavailable districts from the same complete run |
| `POST /api/simulate` | Labelled sensitivity analysis using the same baseline evidence |

District identifiers resolve through the canonical master or recorded legacy crosswalk. They are never borrowed from a similarly named district in a different state. Use `window=next_six_months` for the future monthly graph and `as_of=YYYY-MM-DD` for a retrospective window. Arbitrary target-year requests remain unsupported.

## Interpretation and limitations

The six-month forecast starts at the **last observed groundwater month**, which may precede today's date substantially. If its target is already in the past, the response and dashboard label it as a historical forecast. Forward-filled months do not advance the reported observation date. The October 2026 refresh added January 2026 groundwater for 639 districts and complete rainfall through December 2025; other districts can still have older groundwater observations. ERA5 temperature and potential evaporation remain through December 2024. Inspect each district's observation date and source coverage rather than assuming nationwide current observations. These updates do not independently validate 2026 or 2027 projections. See `reports/AquaIQ_Data_Refresh_Update.md` for the refreshed data snapshot.

The separate **legacy six-month climate projection API** (`window=next_six_months`) begins with the next full calendar month and returns six monthly depth estimates. For example, on 13 October 2026 it covers November 2026 through April 2027. It is not the district graph's default twelve-month seasonal/trend scenario. In this legacy API, a seasonal regression with a damped trend estimates current groundwater depth across the unobserved gap; a separate monthly XGBoost model predicts changes for horizons one through six using rainfall, temperature and evapotranspiration assumptions. The estimated current depth is not a new reading. That history fit needs 24 source-marked monthly observations spanning 36 months; its labelled zone evidence is confined to the legacy product. Missing usable groundwater or weather evidence returns no climate projection and a reason.

In the legacy climate API, future rainfall, temperature, and evapotranspiration are **assumed historical same-month averages**, calculated only from past weather records using up to ten recent usable same-calendar-month reference years per field, with at least three required. Its response includes the assumptions and last usable weather dates; these are not observed 2026 weather or live forecasts. Pumping/extraction is excluded. This separate climate projection does not replace the historical endpoint, crisis score, simulation baseline or twelve-month seasonal/trend scenario. Its present-period accuracy is unvalidated. Historical evaluation does not establish accuracy after the current observation gap.

The 0–100 crisis score is a **project-defined, uncalibrated risk index**, not a probability or percentage likelihood of crisis. Safe, Watch, Warning and Crisis are project tiers, not official groundwater classifications. Initial ensemble weights are uncalibrated; candidate backtest weights require independent validation before promotion. A zone fallback is a real zone aggregate and is labelled accordingly. When district and zone evidence are insufficient, the score and tier remain null.

Simulation shows model and heuristic sensitivity to changed inputs. Its extraction adjustment is explicitly heuristic and does not establish a causal policy effect. Zero-change simulation preserves the available baseline, including a null baseline.

Read held-out metrics, their metre units, observed sample counts, and temporal boundaries from `models/checkpoints/aquaiq_xgb_model_card.json`. Older normalized-scale metrics and evaluation targets in planning documents should not be interpreted as the repaired model's measured performance.

## Verification

For frozen-submission checks, use fixed-array/metadata tests and the offline frontend tests with existing dependencies:

```bash
python -m pytest -q tests/test_post_audit_reporting.py tests/test_post_audit_metadata.py tests/test_forecast_metric_precision.py
npm --prefix dashboard test
npm --prefix dashboard run lint
```

These selected tests do not fit models or contact the database. The broader non-database suite can fit test estimators and is not required for this submission. If temporary paths are restricted, give the targeted pytest command a fresh `--basetemp=scratch/<new-name>`. Build the frontend to a fresh scratch `--outDir` when preserving an existing `dashboard/dist`. Latest scientific limits are in the submission evidence linked above; older reports retain their original scope.

The data-quality commands inspect local inputs and write separate reports:

```bash
python -m scripts.audit_data_quality --help
python -m scripts.audit_postgres_export
python -m data_ingestion.data_completeness
python -m models.audit_evaluation --output-dir reports/candidates/<new-audit-run> --include-monthly
```

The comparison fits Ridge and Random Forest using training-only preprocessing,
selects against persistence/seasonal-naive/XGBoost on validation errors, and
reports final test errors separately. These experiments do not replace the
active model. Small sample sizes and previously inspected holdouts limit what
the results establish; do not infer an accuracy percentage from aggregate R².

For a complete replay that preserves the active release, use a PostgreSQL role
allowed to create a temporary schema and a new scratch output directory:

```bash
python -m scripts.verify_pipeline
python -m scripts.verify_pipeline --run --output-dir scratch/pipeline-verification --as-of 2026-10-17
```

The default prints an offline plan. `--run` copies the existing real raw-record
snapshot into a fresh isolated schema, ingests the local archives, and runs all
six stages with derived artifacts/checkpoints directed into scratch. This
retains verified incremental observations that are not in the original CGWB
CSV. It exports non-empty prediction/score CSVs, removes its temporary schema,
and records hashes confirming that production tables and artifacts stayed
unchanged. It refuses an existing output directory. Restore the original
source/refresh artifacts and database snapshot before expecting the same
2026 coverage on another machine. No download is performed by this replay.

Tests marked `requires_db` are opt-in with `--integration` and assume a populated test dataset. Use an isolated PostgreSQL database for those tests; an empty CI database is used only for schema smoke checks.

```bash
python -m pytest --integration -m requires_db
cd dashboard
npm run lint
npm run build
```

CI uses Python 3.13 for unit tests, initializes a PostgreSQL 18 schema twice and checks provenance constraints, and runs strict `npm ci`, lint, request-handling tests (`npm test`), and build on Node 22. Failed initialization or dependency installation fails the workflow.

### Experimental monthly scenario from today

District pages now offer **Next 12 months from today (experimental)** for all 725 registered district IDs, separately from the historical M+12 research graph. Each scenario uses only that district's own source-marked observation history and an in-memory damped seasonal/trend fit. With current local evidence, **548 districts meet the method's history requirements**; 177 show explicit insufficient/no-observation states. This includes Kaithal, Haryana. Adilabad retains its separate frozen research history; other districts use a pinned version of the existing national feature export. Neither a zone nor another district supplies replacement values.

The graph returns twelve following full calendar months: on 21 October 2026, November 2026–October 2027. It estimates the gap since the latest source-marked observation; today's depth is an estimate. Most eligible districts' latest source-marked month is January 2026; nine have January 2021 evidence, while the separate Adilabad source extends to May 2026. Observation age and sampled calendar phases are disclosed. Sparse seasonal observations do not become monthly measurements. Current-month, future and imputed history are excluded from fitting; future weather and extraction effects are omitted, and no calibrated interval is supplied.

This user-approved scenario is **unvalidated** and separate from the saved six-month ML and direct M+12 artifacts. It has no demonstrated accuracy, baseline superiority, prospective skill or production readiness. Source availability, actual acquisition, well-panel continuity and datum remain unverified. The transient fit is not saved or promoted; active checkpoints, source datasets and completed experiments are preserved. Historical `origin_month` links retain their original product. See [scenario methodology](docs/EXPERIMENTAL_SCENARIO.md).
