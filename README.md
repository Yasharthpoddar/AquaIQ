# AquaIQ

AquaIQ is an academic groundwater-forecasting prototype with a canonical registry of **725 districts and 36 states/UTs**. It serves twelve-month district outlooks and equal-district state summaries, with explicit evidence tiers and fallback methods. Coverage does not establish forecast accuracy or operational readiness.

The current implementation reads published PostgreSQL forecast generations through Flask and displays them in React. Missing observations, stale anchors and unavailable forecasts remain visible. A source-only clone needs the external data, verified bundles and database publications described in the [reproduction guide](docs/FINAL_RELEASE_REPRODUCTION.md).

## Model and scientific status

| Asset | Status |
| --- | --- |
| [Frozen twelve-month production pointer](models/artifacts/aquaiq_climate_12m.json) | Remains active; model SHA-256 starts `4b22e2165664`. |
| [Enriched retraining candidate](models/artifacts/enriched_retraining_20261027/checkpoint.json) | Retained for research; SHA-256 starts `e4e57de9f681`. It is unpromoted. |
| [Grouped-horizon research artifact](models/artifacts/accuracy_experiments_20261027_run_v2_three_horizon_groups/checkpoint.json) | Rejected as a replacement; retained for reproducibility. |
| Legacy six-month models and research APIs | Separate contracts and artifacts remain supported. |

The latest [accuracy experiment](reports/accuracy_experiments_20261027/REPORT.md) did not establish a robust improvement over the current recipe. Baselines remain competitive or better in important settings, and no untouched post-refit test is available. Experimental weights have not replaced production. Historical uncertainty ranges are not calibrated local 90% probabilities; the risk index is uncalibrated and simulation is sensitivity analysis.

The retained climate review for `physical-v3-causal-monthly-90a24f1f2574` is historical evidence and does not verify a later generation. Compare each release's data/model fingerprints before interpreting its metrics.

The [evidence index](reports/README.md) identifies authoritative release, retraining and accuracy records, including negative findings and historical studies. The [documentation index](docs/README.md) separates current operator guides from academic/design material.

## Installation and required assets

Supported local environment: **Python 3.13**, **Node 22.12+**, and PostgreSQL (verified with version 18). Dependencies are pinned in [requirements.txt](requirements.txt) and [dashboard/package-lock.json](dashboard/package-lock.json).

For a new installation, create a dedicated database and prepare a private `.env` from [.env.example](.env.example). Then use the platform setup script:

```powershell
.\setup.ps1
.\venv\Scripts\Activate.ps1
npm.cmd ci --prefix dashboard
```

On Linux/macOS, use `bash setup.sh` and `source venv/bin/activate`. Setup installs dependencies and initializes database schema; use it deliberately against the intended database. An existing provisioned environment does not need to be recreated merely to display or verify the application.

Restore the exact raw/processed assets and matching database/bundles before expecting forecasts. See [required inputs and fingerprints](docs/FINAL_RELEASE_REPRODUCTION.md), [config.yaml](config.yaml) and the [source catalogue](data_sources/catalog.yaml). Raw data, legacy checkpoints, credentials and full generated exports are intentionally excluded from Git. Keep credentials private and preserve accepted observation provenance.

## Run the provisioned application

From the repository root, in separate terminals:

```powershell
.\venv\Scripts\python.exe -B -m api.app
npm.cmd --prefix dashboard run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`; Vite proxies `/api` to `http://127.0.0.1:5000`. Waitress is available for a local WSGI process: `waitress-serve --listen=127.0.0.1:5000 --call api.app:create_app`.

Normal requests read a published generation and do not run nationwide inference. The complete historical demonstration was published in an isolated namespace, not promoted automatically to public production. To inspect that already-provisioned local example, configure `AQUAIQ_FORECAST_SCHEMA=aquaiq_test_nationwide_20261025` and, for its risk snapshot, `AQUAIQ_SCORING_SCHEMA=aquaiq_test_nationwide_20261025` before launching the API. These namespaces must already exist. See [serving, publication and namespace operations](docs/NATIONWIDE_FORECASTS.md).

Do not run ingestion, refresh, training, scoring or migrations merely to display the application. Missing publications return unavailable responses. Deployment packaging and release/rollback procedures are in [deploy/README.md](deploy/README.md); Docker/host deployment still requires verification on the target host.

## Architecture and API

Official source snapshots feed causal preprocessing and feature generation. Verified model bundles produce offline district forecasts; state values aggregate all registered districts with disclosed evidence counts. A transactional publisher stores immutable generations in PostgreSQL. Flask reads those publications and React displays their dates, methods and limitations.

| Area | Location |
| --- | --- |
| Acquisition and provenance | [data_ingestion/](data_ingestion/), [data_sources/](data_sources/) |
| Causal preprocessing/features | [preprocessing/](preprocessing/) |
| Models and inference contracts | [models/](models/) |
| Database schema/migrations | [db/](db/) |
| API and dashboard | [api/](api/), [dashboard/](dashboard/) |
| Verification and offline operations | [tests/](tests/), [scripts/](scripts/), [.github/workflows/ci.yml](.github/workflows/ci.yml) |

Current twelve-month endpoints include `/api/districts`, `/api/states`, `/api/states/summary?horizon=12`, `/api/predict/climate-12m/<district_id>?months=12` and `/api/predict/state/<state_id>?horizon=12`. State summaries use equal weights over registered districts, not well/area weighting or groundwater volume. Omitted `as_of` selects the latest published vintage and retains its actual date.

Health, history, risk, simulation, six-month and historical research contracts remain separate. See [current serving contracts](docs/NATIONWIDE_FORECASTS.md) and the [detailed API specification](api_spec.md), whose research sections retain their original historical scope.

## Verify

Use the existing environment and fresh temporary paths:

```powershell
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -o tmp_path_retention_policy=failed --basetemp scratch/pytest-unit-verification
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../scratch/frontend-verification
```

The ordinary Python run skips explicitly marked database integration tests. For a provisioned test database, add `--integration`; those tests use isolated schemas. The suite can fit test estimators and generate temporary fixtures. Retaining only failed temporary fixtures prevents old test rasters accumulating. Build to a fresh scratch directory to preserve an existing `dashboard/dist`.

The CI workflow checks Python syntax/unit tests, PostgreSQL migration idempotence and frontend tests/lint/build. Local executed results are in the dated reports indexed above. Passing software checks does not validate current-period forecasting skill.

## Maintenance and reproducibility

[Maintenance commands](docs/MAINTENANCE.md) cover deliberate ingestion, sample features, audits and isolated pipeline replays. Use the dedicated [data-release](docs/FINAL_RELEASE_REPRODUCTION.md), [retraining](docs/ENRICHED_XGBOOST_RETRAINING.md) and [accuracy](docs/ACCURACY_EXPERIMENTS.md) guides for exact source versions, cutoffs, protocols, checksums and fresh output paths.

Historical source-marked observations, bounded imputations, estimated current depths and future projections are distinct. Observation dates do not certify publication/receipt time, well continuity or datum. Previously inspected retrospective results are not untouched or prospective tests. No current-period, nationwide or production-superiority claim is established.

[Archived report payloads](reports/ARCHIVE.md) can be recovered from pinned Git history when needed. Runtime assets, final scientific evidence, academic deliverables and meaningful tests remain preserved. Follow [CONTRIBUTING.md](CONTRIBUTING.md) for contribution conventions.
