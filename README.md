# AquaIQ

AquaIQ uses CGWB groundwater observations, IMD rainfall, and ERA5 weather to estimate groundwater depth six calendar months after an observed origin date. A Flask API and React dashboard expose that endpoint and a project-defined 0–100 crisis score for 725 canonical districts. The district prediction graph separately projects the next six full calendar months from today with one shared monthly XGBoost model that uses the forecast horizon, rainfall, temperature, and evapotranspiration assumptions alongside estimated groundwater depth.

The repaired pipeline keeps groundwater in metres below ground level, rainfall and evapotranspiration in millimetres per month, and temperature in degrees Celsius. Features and model bundles carry generation identifiers, units, dates, and checksums. Missing evidence produces an unavailable result; districts with sparse evidence may use an explicitly labelled aggregate of their agro-climatic zone.

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

The production model defaults to the label cutoff in `config.yaml` (`2019-12-31`). A six-month embargo separates training from evaluation origins, and the final holdout remains independent of model fitting. Training publishes an immutable model/card bundle through one atomic manifest. The training stage builds both the historical endpoint model and the separate monthly climate model. To rebuild only the monthly model, run `python -m models.climate_forecast`; it writes its independent verified bundle and `reports/climate_forecast_evaluation.json`. Backtests and synthetic tests write separate reports and cannot replace the historical checkpoint or automatically promote candidate weights.

Use the evaluation-only or candidate modes for model experiments:

```powershell
python -m models.climate_forecast --eval
python -m models.climate_forecast --candidate-checkpoint reports/candidates/monthly/candidate.json
python -m models.climate_forecast --eval --checkpoint reports/candidates/monthly/candidate.json --output reports/candidates/monthly/saved_evaluation.json
python -m scripts.validate_monthly_candidates --run --fold all --n-jobs 1
```

Saved evaluation uses the bundle's recorded cutoff and never fits or republishes it. Candidate training writes a separate pointer, model-card sidecar and report. The development runner excludes all 2020 onward rows before label construction, uses fixed chronological panel folds with six-month embargoes, and writes only experimental candidate reports. Without `--run` it prints a plan. These development comparisons are for model selection, not independent interval calibration or current-period accuracy; later independent observations are still required.

For batch scoring, an optional historical cutoff selects only evidence available through that date:

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
| `GET /api/predict/<district_id>?months=6` | One validated six-calendar-month endpoint |
| `GET /api/predict/<district_id>?window=next_six_months` | Six future monthly XGBoost projections using rainfall and weather assumptions |
| `GET /api/alerts` | Scores and unavailable districts from the same complete run |
| `POST /api/simulate` | Labelled sensitivity analysis using the same baseline evidence |

District identifiers resolve through the canonical master or recorded legacy crosswalk. They are never borrowed from a similarly named district in a different state. Use `window=next_six_months` for the future monthly graph and `as_of=YYYY-MM-DD` for a retrospective window. Arbitrary target-year requests remain unsupported.

## Interpretation and limitations

The six-month forecast starts at the **last observed groundwater month**, which may precede today's date substantially. If its target is already in the past, the response and dashboard label it as a historical forecast. Forward-filled months do not advance the reported observation date. The October 2026 refresh added January 2026 groundwater for 639 districts and complete rainfall through December 2025; other districts can still have older groundwater observations. ERA5 temperature and potential evaporation remain through December 2024. Inspect each district's observation date and source coverage rather than assuming nationwide current observations. These updates do not independently validate 2026 or 2027 projections. See `reports/AquaIQ_Data_Refresh_Update.md` for the refreshed data snapshot.

The **prediction graph** starts with the next full calendar month after today's month and shows six monthly depth estimates. For example, on 13 October 2026 it covers November 2026 through April 2027. A seasonal regression with a damped trend estimates the current groundwater depth across the unobserved gap. A separate monthly XGBoost model predicts groundwater changes for horizons of one through six months, using the horizon, rainfall, temperature, and evapotranspiration as inputs. An estimated current depth is shown explicitly as an estimate; it is not a newly recorded reading. The history fit needs 24 actual observations spanning 36 months, and sparse districts may use the labelled zone evidence selected by the pipeline. Missing usable groundwater or weather evidence returns an empty graph with a reason.

Future rainfall, temperature, and evapotranspiration are **assumed historical same-month averages**, calculated only from past weather records using up to ten recent usable same-calendar-month reference years per weather field, with at least three years required. They are model inputs, not observed 2026 weather or live weather forecasts. The dashboard shows each month's assumptions beside the graph and reports the last available weather record. Pumping/extraction remains excluded because measured future pumping data is unavailable. This climate-conditioned projection does not replace the historical XGBoost endpoint, crisis score, or simulation baseline. Its present-period accuracy is unvalidated. Inspect source age and the weather assumptions before interpreting the estimates. Historical evaluation does not establish accuracy after the current multi-year observation gap.

The crisis tiers and depth-to-score transformation are project definitions, not official groundwater classifications. Initial ensemble weights are explicitly uncalibrated; candidate backtest weights require independent validation before promotion. A zone fallback is a real zone aggregate and is labelled accordingly. When district and zone evidence are insufficient, the score and tier remain null.

Simulation shows model and heuristic sensitivity to changed inputs. Its extraction adjustment is explicitly heuristic and does not establish a causal policy effect. Zero-change simulation preserves the available baseline, including a null baseline.

Read held-out metrics, their metre units, observed sample counts, and temporal boundaries from `models/checkpoints/aquaiq_xgb_model_card.json`. Older normalized-scale metrics and evaluation targets in planning documents should not be interpreted as the repaired model's measured performance.

## Verification

Run the deterministic regression suite without a database:

```bash
python -m pytest -v -m "not requires_db"
python -m pip check
```

Tests marked `requires_db` are opt-in with `--integration` and assume a populated test dataset. Use an isolated PostgreSQL database for those tests; an empty CI database is used only for schema smoke checks.

```bash
python -m pytest --integration -m requires_db
cd dashboard
npm run lint
npm run build
```

CI uses Python 3.13 for unit tests, initializes a PostgreSQL 18 schema twice and checks provenance constraints, and runs strict `npm ci`, lint, request-handling tests (`npm test`), and build on Node 22. Failed initialization or dependency installation fails the workflow.
