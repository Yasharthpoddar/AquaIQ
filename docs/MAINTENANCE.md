# Maintenance

Use the activated project environment. Run these operations deliberately against the intended database and fresh output paths. Preserve a matching database/configuration/data/checkpoint backup before rebuilding. Ordinary application startup does not require acquisition, training, migrations or scoring. [Release inputs](FINAL_RELEASE_REPRODUCTION.md), [scientific workflows](ACCURACY_EXPERIMENTS.md) and [deployment recovery](../deploy/README.md) define their separate prerequisites.

## Acquisition, derived stages and audits

[config.yaml](../config.yaml) and the [source catalogue](../data_sources/catalog.yaml) identify expected assets. Source permissions, exact raw archives and matching provenance are required. Rainfall staging is bounded and never publishes automatically; see [deployment operations](../deploy/README.md#stage-rainfall-updates).

```powershell
python -m data_ingestion.era5_to_district
python -m data_ingestion.imd_district_climatology --raw-dir data/raw/imd
python scripts/run_pipeline.py --step all
python -m scripts.audit_data_quality --help
python -m scripts.audit_postgres_export
python -m data_ingestion.data_completeness
```

The orchestrator accepts `--step preprocess`, `features`, `train`, `backtest` or `score_all`. Feature rebuilding replaces derived database data transactionally; training writes matching bundles and does not authorize candidate promotion. `--as-of` applies to batch scoring. Historical reconstruction uses `python -m preprocessing.pipeline --as-of YYYY-MM-DD` followed by matching feature/model builds. Observations, physical units, district identities and causal feature policies must be preserved.

Sample commands are `python -m preprocessing.pipeline --sample 10`, `python -m preprocessing.features --input-dir reports/samples`, `python -m preprocessing.features --sample 10` and `python -m preprocessing.features --csv-only`. Sample-only manifests are rejected for production training/loading. Filled or predicted values never become observed targets. `python -m models.audit_evaluation --output-dir reports/candidates/NEW_AUDIT --include-monthly` can fit comparison estimators with train-only preprocessing; historical holdouts remain inspected evidence.

## Isolated pipeline replay

```powershell
python -m scripts.verify_pipeline
python -m scripts.verify_pipeline --run --output-dir scratch/NEW_PIPELINE_REPLAY --as-of 2026-10-17
```

The default prints an offline plan. `--run` needs the real raw-record snapshot, original source archives and a role allowed to create an isolated schema. It writes artifacts/checkpoints to the fresh scratch path, removes its test schema and checks production preservation; it does not download new sources. Generated directories may be recreated as workflows run and are not application installation assets.

## Shadow evidence ledger

The file-only direct-six-month ledger is implemented in [models/shadow_ledger.py](../models/shadow_ledger.py); it does not fit/load models, connect to PostgreSQL or publish production forecasts. Real issuance remains blocked on verified source timing, well panels/datum, a feasible lead definition and a separately approved artifact. The locked HGB candidate is `hist_gradient_boosting-2-delta`, training cutoff 2018-12-31; no approved serialized shadow model exists. Every real HGB slot therefore abstains. A synthetic number is an untrained placeholder and cannot establish skill.

```powershell
python scripts/shadow_evaluation.py plan
python scripts/shadow_evaluation.py demo --run --ledger reports/candidates/shadow_synthetic_NEW
python scripts/shadow_evaluation.py verify --run --ledger reports/candidates/shadow_synthetic_NEW/ledger
```

Without `--run`, every action is a read-only offline plan. Production routes and schedulers never invoke this ledger. `init --run --ledger reports/candidates/shadow_campaign_NEW --lane prospective --campaign preregistered-id` creates a new exclusive ledger. Subsequent `record --input verified_snapshot.json`, `label --input new_observed_label.json`, `evaluate --label-policy first` (or explicit `latest`) and `verify` require the same `--run --ledger ...` arguments. The separate `scripts/record_live_forecasts.py` utility archives a different production-projection contract; its records are not interchangeable.

Lanes are immutable: `prospective` uses actual runtime issuance and rejects caller-supplied `issued_at`; `retrospective` cannot claim advance issuance; `synthetic` accepts only invented, labelled fixtures. All timestamps are timezone-aware. Present inputs require `observed_at <= period_end <= published_at <= received_at <= available_at <= issued_at`, exact calendar lags, source versions/hashes and observed/missing status. Missing evidence produces explicit missingness/abstention, never an invented value. Nominal target is origin+6; seasonal reference is origin-6. Full origin-month weather can arrive too late for six full operational months of lead, so evaluation distinguishes nominal from effective lead.

Panels are registered before issuance with unique well IDs, fixed weights summing to one, geography/version identity and `m_bgl`/datum metadata. Per-value envelopes include value, units, month, source/version, observation/period/availability times and observed status; missing values need a reason. Signed measured depths remain signed. Source hashes and assertions are integrity metadata, not independent certification of stable wells or datum. Any future fitted artifact must retain the fourteen-feature order in `shadow_ledger.FEATURES`, frozen transforms, clipping, code, software and model hashes; the seasonal reference is a baseline input, not an extra model feature.

Records are append-only, unique by campaign/district/origin, hash-checked and bound to their ledger/commit. Source revisions do not permit reissuing the same schedule slot. Label revisions form a single immutable chain using `supersedes_sha256`; `first` evaluates the root and `latest` produces a separate sensitivity snapshot. Labels must be independently observed, non-imputed, datum/panel-compatible and available after issuance for prospective evidence. Paired evaluation requires the complete registered panel and all three prediction slots. Late input, panel mismatches, unavailable predictions, backfills and pending targets remain explicit exclusions/cohorts.

Exclusive locks and reserved records fail closed after interrupted writes; do not delete them to force verification. This is local integrity control, not externally trusted timestamping or protection against an administrator replacing history. Real operation needs a verified point-in-time adapter, retained source bytes/revisions, protected writers/backups, reliable clocks, external/write-once audit retention and preregistered region/season/power/lead policies. Future database integration needs a new append-only schema and migration/rollback plan; no production table migration is implied. Synthetic and software results cannot authorize real issuance, establish prospective skill or promote a model.

## Optional browser regression checks

These harnesses require an existing Playwright installation resolvable through `NODE_PATH`; no browser dependency is installed automatically. Always build the current source into a new directory before selecting it with `AQUAIQ_UI_BUILD`. Old build copies are not prerequisites. For synthetic state fixtures:

```powershell
npm.cmd --prefix dashboard run build -- --outDir ../scratch/browser_verification_new
$env:AQUAIQ_UI_BUILD = Join-Path (Get-Location) 'scratch/browser_verification_new'
node dashboard/tests/stateBrowser.cjs
```

Use an already installed Playwright browser, or set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an existing Chromium executable for `stateBrowser.cjs`. Its API fixtures are synthetic and do not establish forecast skill.

For `nationwideBrowser.cjs`, first complete the [isolated publication/export recipe](NATIONWIDE_FORECASTS.md#reproduce-in-a-safe-local-namespace). Start a separate API with `FLASK_PORT=5057` and `AQUAIQ_FORECAST_SCHEMA=aquaiq_test_nationwide_replay_new`; retain that fresh generation's date. Then use the build above and its newly exported district objects:

```powershell
$env:AQUAIQ_DISTRICT_OUTPUTS = Join-Path (Get-Location) 'scratch/nationwide_replay_new/outputs/districts.json'
$env:AQUAIQ_API_URL = 'http://127.0.0.1:5057'
$env:AQUAIQ_AS_OF = '2026-10-25'
$env:AQUAIQ_BROWSER_REPORT = Join-Path (Get-Location) 'scratch/nationwide_browser_new.json'
node dashboard/tests/nationwideBrowser.cjs
```

That harness uses `AQUAIQ_CHROME` for an existing Chrome executable and optionally `AQUAIQ_PLAYWRIGHT` for an existing module; it requires the published API and matching export, unlike the synthetic state harness. `homeCatalogBrowser.cjs` and `scoredDashboardBrowser.cjs` use an already running frontend at `AQUAIQ_UI_URL` (default port 5173); the scored harness also needs a complete matching risk publication. They use the same Chrome/module overrides. Browser outputs are disposable software verification, not observations or scientific evaluation. Choose fresh paths on subsequent runs and keep authoritative reports and existing `dashboard/dist` intact.

## Verification

Use the [root test commands](../README.md#verify), with `--integration` only on a provisioned local/test database. [scripts/fingerprint_public_data.py](../scripts/fingerprint_public_data.py) reads public-table row/content fingerprints without changing data; [scripts/scan_staged_content.py](../scripts/scan_staged_content.py) checks staged bytes without printing secret values. Keep `.env`, raw observations, database dumps and row-level forecast exports out of commits. Recovery of removed historical files uses the corresponding Git commit; no backup copy is required in the current tree.
