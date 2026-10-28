# AquaIQ

AquaIQ is an **academic groundwater forecasting application** for a fixed project registry of 725 districts and 36 states/UTs. It makes forecast dates, source observations and evidence limitations visible rather than treating nationwide output coverage as nationwide predictive accuracy.

## Capabilities

- District search and map navigation, twelve-month district outlooks and equal-district state summaries.
- Observed/imputed history, source provenance, observation age, evidence tiers and disclosed fallback methods.
- Explicit unavailable results when publications, artifacts or local evidence are missing.
- Separate historical six-month risk, sensitivity simulation and labelled research/scenario APIs.

## Architecture and stack

Official source snapshots feed offline ingestion, causal preprocessing and forecasting. Validated generations are published transactionally to PostgreSQL; Flask reads those immutable publications and the React dashboard displays them. Normal twelve-month API requests do not run nationwide inference.

| Layer | Implementation |
| --- | --- |
| Frontend | React 19, Vite 8, Leaflet/React Leaflet and Recharts |
| API | Flask, strict JSON contracts and Waitress deployment entry point |
| Data and models | PostgreSQL, pandas/NumPy, XGBoost, scikit-learn, statsmodels and fuzzy inference |
| Verification | pytest, Node's test runner, Oxlint and isolated PostgreSQL migration checks |

See [API contracts](api_spec.md) and [serving architecture](docs/NATIONWIDE_FORECASTS.md) for product boundaries, evidence fields and publication behavior.

## Requirements and external assets

Use **Python 3.13**, **Node 22.12+** and PostgreSQL (**18 is the verified local/CI target**). Python dependencies are pinned in [requirements.txt](requirements.txt); frontend dependencies use [package-lock.json](dashboard/package-lock.json). Optional download/tracking extras are separate manifests.

A GitHub clone contains code, registries, compact frozen artifacts and selected scientific evidence. It does not contain the full source observations/archives, canonical raw boundaries, matching processed feature CSVs/manifests, legacy checkpoint bundles, or a populated database with published forecast/risk generations. Restore these exact release-matched assets before expecting forecasts or full backend validation. [Asset hashes, provenance and restoration requirements](docs/FINAL_RELEASE_REPRODUCTION.md) are authoritative; current source downloads cannot automatically reconstruct the old baseline.

Create a local PostgreSQL database and role, then configure `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` in a private `.env` based on [.env.example](.env.example). Setup initializes schema in that database; it does not supply observations, train models or publish forecasts. Existing provisioned environments do not need to be reinstalled or rebuilt merely to display the application.

## Quick start

Run from the repository root. These are new-workspace setup commands; configure the database and restore required assets first. Keep credentials private. Windows checks use the provisioned local environment; the Linux/macOS script is provided but a native fresh installation was not executed in this session.

**Windows — PowerShell**

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env for the intended existing local PostgreSQL database before setup.
.\setup.ps1
.\venv\Scripts\Activate.ps1
npm.cmd ci --prefix dashboard
python -B -m api.app
# In a second terminal:
npm.cmd --prefix dashboard run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

**Linux/macOS — Bash**

```bash
test -f .env || cp .env.example .env
# Edit .env for the intended existing local PostgreSQL database before setup.
PYTHON_BIN=python3.13 bash setup.sh
source venv/bin/activate
npm ci --prefix dashboard
python -B -m api.app
# In a second terminal:
npm --prefix dashboard run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`; Vite forwards `/api` to `http://127.0.0.1:5000`. Select an already published forecast/scoring namespace using the [serving guide](docs/NATIONWIDE_FORECASTS.md); missing publications remain unavailable. [Deployment and recovery](deploy/README.md) require the same matching database/data/model release plus verification on the target host.

## Verify

Use an activated project environment, the verified external validation assets and a local/test database. Some backend regressions require real pinned feature/model evidence even when they do not access PostgreSQL; a code-only checkout is insufficient for the full suite. The validation-asset preflight must pass before running it. In PowerShell, use `npm.cmd` instead of `npm` below.

```bash
python -B -m scripts.check_validation_assets
python -B -m pytest --integration -q -p no:cacheprovider -o tmp_path_retention_policy=failed --basetemp scratch/pytest-verification
npm --prefix dashboard test
npm --prefix dashboard run lint
npm --prefix dashboard run build -- --outDir ../scratch/frontend-verification
```

Choose fresh temporary paths for each run and preserve an existing `dashboard/dist`. Integration tests use isolated schemas and require a test role allowed to create them; they do not authorize production migrations. Tests can fit temporary estimators. CI intentionally fails with actionable configuration errors when genuine validation assets are unavailable; it does not substitute synthetic data, silently skip checks or claim full validation from a code-only clone. [Reproduction requirements](docs/FINAL_RELEASE_REPRODUCTION.md) distinguish software checks from scientific replay.

## Project structure

| Paths | Purpose |
| --- | --- |
| `api/`, `dashboard/` | Backend routes/contracts and frontend source/assets/tests |
| `db/` | Database access, schema and versioned migrations |
| `data_ingestion/`, `data_sources/`, `preprocessing/` | Registries, source attribution, ingestion and causal features |
| `models/`, `research/` | Forecasting, verified bundle contracts and required research configuration |
| `tests/`, `scripts/`, `.github/workflows/` | Regression coverage, supported operations and CI |
| `docs/`, `deploy/`, `reports/` | Essential guidance, deployment files and indispensable scientific/runtime evidence |

`scratch/` and build/report outputs are generated locally; ignored files may include indispensable external observations or model assets and must not be deleted indiscriminately. [Maintenance](docs/MAINTENANCE.md) covers deliberate updates, audits, isolated replay and optional browser checks.

## Scientific evidence and limitations

The [frozen production pointer](models/artifacts/aquaiq_climate_12m.json) remains active. The [enriched candidate](models/artifacts/enriched_retraining_20261027/checkpoint.json) is unpromoted, and grouped-horizon experiments did not establish a robust replacement improvement. Authoritative results are the [data release](docs/SCIENTIFIC_LIMITATIONS.md#data-and-source-provenance), [retraining](docs/SCIENTIFIC_LIMITATIONS.md#evaluation-and-model-status), [accuracy experiment](docs/SCIENTIFIC_LIMITATIONS.md#evaluation-and-model-status) and [tiered validation](docs/SCIENTIFIC_LIMITATIONS.md#nationwide-output-and-uncertainty); [scientific workflows](docs/ACCURACY_EXPERIMENTS.md) describe reproduction prerequisites.

Coverage is not predictive accuracy; historical validation is not prospective validation. Historical error ranges are not guaranteed calibrated local probabilities, the risk index is uncalibrated, and simulation is sensitivity analysis. Source publication times, well continuity and datum remain unverified in important settings. Passing tests, loading models or reproducing a supplied snapshot does not establish forecasting skill or production deployment readiness.

The retained climate review for `physical-v3-causal-monthly-90a24f1f2574` is historical evidence and does not verify a later generation. Compare release-specific data/model fingerprints before interpreting metrics.

## Academic attribution and license

AquaIQ is a B.Tech CSE mini project by **Yasharth, Yash and Ayush**, with preserved [academic requirements](docs/phase2_eval/SRS_AquaIQ.md) and [TeX submission sources](Mini_Project__Report_Overleaf_Template/synopsis.tex). See [contribution conventions](CONTRIBUTING.md).

The repository does **not currently declare a project-wide software license**; this README does not create a new license grant. Third-party software and source datasets retain their own terms. The [source catalogue](data_sources/catalog.yaml) records source-specific attribution, access and licensing limitations; do not assume that publicly accessible data can be redistributed without checking those terms.
