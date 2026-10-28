# AquaIQ

AquaIQ is an academic groundwater forecasting application covering a fixed registry of **725 districts and 36 states/UTs**. It displays twelve-month district outlooks, state summaries, observation history, evidence tiers and explicit unavailable results.

A Flask API reads versioned PostgreSQL publications; a React/Vite dashboard displays them. Offline Python ingestion, causal preprocessing and forecasting produce those publications from CGWB, IMD and ERA5 inputs. [API contracts](api_spec.md) and [serving architecture](docs/NATIONWIDE_FORECASTS.md) describe the separate forecast, risk and research products.

## Install and run

Use **Python 3.13**, **Node 22.12+** and PostgreSQL (verified with version 18). Prepare a private `.env` from [.env.example](.env.example), pointing to the intended local database. A code-only clone lacks the matching observations, processed features, legacy checkpoints and database publications: follow the [asset and reproduction requirements](docs/FINAL_RELEASE_REPRODUCTION.md) first.

For a new installation, setup installs the pinned Python dependencies and initializes database schema:

```powershell
.\setup.ps1
npm.cmd ci --prefix dashboard
```

On Linux/macOS use `bash setup.sh`. Existing provisioned environments need no reinstall or rebuild to display the application. From the repository root, run these in separate terminals:

```powershell
.\venv\Scripts\python.exe -B -m api.app
npm.cmd --prefix dashboard run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`; `/api` proxies to port 5000. Select an already published forecast/scoring namespace as described in the [serving guide](docs/NATIONWIDE_FORECASTS.md). Missing publications return unavailable results. [Deployment and recovery](deploy/README.md) require a matching database, data and model release plus verification on the target host.

## Capabilities

- District search/map, twelve-month published forecasts and equal-district state summaries.
- Observation dates, provenance, missingness, fallback methods and uncertainty limitations.
- Separate historical six-month risk, sensitivity simulation and explicitly labelled research APIs.

## Verify

Use the installed environment and new temporary paths:

```powershell
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -o tmp_path_retention_policy=failed --basetemp scratch/pytest-verification
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../scratch/frontend-verification
```

Add `--integration` only with a provisioned local/test database; integration tests use isolated schemas. Tests may fit temporary estimators. [Maintenance](docs/MAINTENANCE.md) covers deliberate updates, audits and isolated replay. Preserve an existing `dashboard/dist` by building to a fresh directory.

## Models, evidence and limitations

The [frozen production pointer](models/artifacts/aquaiq_climate_12m.json) remains active. The [enriched candidate](models/artifacts/enriched_retraining_20261027/checkpoint.json) is unpromoted; grouped-horizon experiments did not establish a robust replacement improvement. Authoritative evidence: [data release](reports/final_release_20261026/REPORT.md), [retraining](reports/retraining_20261027/REPORT.md), [accuracy experiments](reports/accuracy_experiments_20261027/REPORT.md) and [tiered validation](reports/nationwide_20261025/REPORT.md). [Scientific workflows](docs/ACCURACY_EXPERIMENTS.md) preserve the protocol and reproduction limits.

Coverage is not accuracy. Passing software tests does not establish forecasting skill or production deployment readiness. Historical error ranges are not calibrated local probabilities, risk scores are uncalibrated, and simulation is sensitivity analysis. Observed, imputed and estimated depths remain distinct; source publication times, well continuity and datum are not independently established.

The retained climate review for `physical-v3-causal-monthly-90a24f1f2574` is historical evidence and does not verify a later generation. Compare release-specific data/model fingerprints before interpreting metrics.

[Source catalogue and attribution](data_sources/catalog.yaml), [academic deliverables](docs/phase2_eval/), [academic TeX sources](Mini_Project__Report_Overleaf_Template/) and [contribution conventions](CONTRIBUTING.md) remain available.
