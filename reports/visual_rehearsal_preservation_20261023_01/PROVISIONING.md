# AquaIQ: static local provisioning and source continuity

23 October 2026. This review supports the separate visual rehearsal. It starts no server, sends no HTTP requests, opens no database, imports no application, deserializes no estimator, and runs no build, training, backtest, pipeline, Docker command or deployment. It reads no `.env` values or private transport headers. New files are confined to this report directory.

## Result and evidence

**The retained local files support attempting the established audit launch, subject to the existing PostgreSQL service and browser/runtime checks. A clean Git checkout and the default Docker package remain incomplete for the same application.** These are static findings; they do not certify an active API, rendered UI or operational forecast.

Fresh evidence is [provisioning_receipts.json](provisioning_receipts.json), generated create-only by [provisioning_receipt.py](provisioning_receipt.py). This independently rehashes the assets from the prior [source audit](../end_to_end_verification_20261022/api_source/API_SOURCE.md) and [receipt](../end_to_end_verification_20261022/api_source/source_asset_receipts.json), and reads the prior [end-to-end report](../end_to_end_verification_20261022/REPORT.md).

- HEAD remains `090626df28ad6414b355e2b1a4e24a4163693de5`, local branch `main`. Tracked working tree and index are clean at receipt time. No remote fetch is implied.
- Sixty selected tracked source/configuration files match HEAD after CRLF/LF normalization. The existing untracked `audit_server.py` is recorded separately, for 61 source receipts. The 50 files in the prior source receipt also retain identical working-byte hashes.
- All 17 inventoried runtime assets exist and have identical SHA-256 values to the prior audit; all 13 descriptor-linked asset checksums agree. Fifteen of those 17 assets are absent from HEAD. Hashes establish byte continuity and metadata agreement, not estimator behavior or source validity.
- The local venv reports Python `3.13.15`; all 24 platform-applicable pinned requirements match installed distribution metadata. Windows skips the requirements file's Linux-only Gunicorn entry. No package import/DLL compatibility check was run.
- Existing Node is `v22.18.0`. Vite `8.3.0` and its executable entry exist, as do installed package metadata for all 11 declared frontend dependencies/devDependencies. React/React DOM are `19.3.0`, Leaflet `1.9.4`, Recharts `3.10.1`, router `7.18.3`, and Oxlint `1.82.0`. Metadata presence does not certify module loading or rendering. The recorded Node version falls within this installed Vite package's declared engine range.

## Minimum assets by product

All file paths below are relative to `C:\Users\Yasharth\Downloads\AquaIQ`. Full per-file bytes/hashes and HEAD membership appear in the JSON receipt.

| Product / surface | Required retained assets | DB needed for this product? | Clean HEAD |
|---|---|---|---|
| Historical direct M+12 catalog/forecast/graph, exact `TS-Adilabad` scope | Tracked `research/twelve_month_app.json` plus the six frozen files below | No direct-route DB access | Descriptor present; six bundle files absent |
| Adilabad experimental scenario | Same frozen bundle; serving still verifies the whole bundle, including model bytes/card | No scenario DB access | Bundle absent |
| Other canonical district scenarios | Tracked `research/experimental_scenario_sources.json`, tracked `data_ingestion/district_crosswalk.csv`, plus exact pinned `data/processed/features_matrix.csv` and `data/processed/feature_manifest.json` | No scenario DB access | CSV/manifest absent |
| Home scores, legacy district/history, alerts, simulator | Existing matching PostgreSQL data and score publication, tracked configuration, processed feature manifest, six-month pointer/model/card | Yes | DB and ignored runtime artifacts absent |
| Legacy next-six climate projection and `/api/health` | Above plus monthly-climate pointer/model/card | Yes | Checkpoints/DB absent |
| Frontend local map geometry | Tracked `dashboard/public/india_districts.geojson`, source, and installed frontend packages | Scores are a separate DB-backed API dependency | Boundary/source present; packages not in Git |

The direct descriptor names exactly `reports/candidates/twelve_month_horizon_finalization_20261020/artifact/manifest.json`. The six file minimum is:

1. `manifest.json` — `e390b0e78221560e66b50610d4ef37cb37225d34232589c4d52064713ef27165`
2. `xgb_fixed_2021_card.json` — `c399ed9cfa5c1746c874659d89bd1d69d92ea841dc262b7d0dfab89bac9e0bd7`
3. `features.csv` — `728677ebfbe103f0d38b53fd0bd02deb8a4d647f15f5bb199d392a29be33569e`
4. `input_provenance.json` — `d069f1c623dead6c8678a2e8be6d90bc0f51135682973b75f6bbdd3f948ac3e3`
5. `provenance.json` — `2e6b5e5d43db8df0b681b82ac4ec6fbf4d84ff359c1c006acd6b93da4f0322f1`
6. `xgb_fixed_2021.json` — `f94911f5e1a6c3e8b4bbbb82d6a4c6ec87b5d601abbfd774801afc046aa5455f`

The national scenario CSV hash is `3958737b033a16e722f633a15ad77d80bc5b2a8fb3bea888697f0410362c24ae`; feature-manifest hash is `afc96a9e13655ffa2ccb2bf18a027b9bb1ed34c21260b901301cef6fd35c8b91`; crosswalk hash is `5765965f7cf0fbbaecfb93983e72d248baaeca07e1b9b43e47ad80921dda7835`. Both descriptor canonical hash checks match the serving code. The physical generation is `physical-v3-causal-monthly-a3f9468a2569`; the separate direct bundle generation is `research-telangana-exact-name-coordinate-h12-app-v1`.

Legacy pointer `models/checkpoints/aquaiq_xgb.json` selects `bundles/20261013T170456589578Z-ca138883556b/model.json` and `model_card.json`. Monthly-climate pointer `models/checkpoints/aquaiq_monthly_climate.json` selects `climate_bundles/20261013T170824590468Z-16aefd7cb4/model.json` and `model_card.json`. Preserve the pointer and immutable child pair together. No replacement, retraining or inference was performed in this review.

The separate ignored `data/raw/india_districts.geojson` is retained and hashed. The frontend serves its tracked public boundary, rather than reading the raw path. Local district geometry and external OpenStreetMap base tiles have separate availability: `MapComponent.jsx` requests the latter from its configured HTTPS tile URL during browser use.

## Existing external PostgreSQL dependency

The server's normal legacy paths use `db/connection.py` and `psycopg2`; `aquaiq.db` is not their configured database backend. A local SQLite file is therefore not a substitute. The role/service/credentials and SQL contents were not checked here. `.env` existence was recorded, but its contents were not read, copied or printed.

Full UI serving needs an existing compatible PostgreSQL release with canonical districts/aliases, physical features and provenance columns, raw records, and a completed matching score publication. `api/routes/scores.py` selects the most recent completed `scoring_runs` row matching feature generation, card version, model SHA-256 and scoring signature, then joins its `crisis_scores`; arbitrary pre-existing score rows do not suffice. The additions in `db/migrations/003_pipeline_provenance.sql` illustrate why the original base schema alone is insufficient. No schema/migration/initialization or score generation is proposed for this rehearsal.

The production-style `deploy/serve.py` readiness gate additionally checks legacy health, district/raw/feature population and complete scores, with expected district count 725 by default. `/api/health` checks a DB read plus the two legacy bundles; it does not validate the direct research artifact, scenario pins, research skill or rendered app. The existing audit helper bypasses that production startup gate and lets ordinary routes return their own availability/error responses.

## Existing local audit launch contract

These are reviewed commands for the parent rehearsal; this worker did not execute them. They reuse installed packages and existing files. Use the explicit working directory for each process and check port ownership before launch.

```powershell
# API process: working directory C:\Users\Yasharth\Downloads\AquaIQ
.\venv\Scripts\python.exe -B reports/end_to_end_verification_20261022/audit_server.py

# Frontend process: working directory C:\Users\Yasharth\Downloads\AquaIQ\dashboard
$env:VITE_API_URL='http://127.0.0.1:5053'
& 'C:\Program Files\nodejs\node.exe' '.\node_modules\vite\bin\vite.js' --host 127.0.0.1 --port 5183 --strictPort
```

`audit_server.py` loads the existing local `.env` privately at runtime, patches `psycopg2.connect` to append `default_transaction_read_only=on` and call `set_session(readonly=True)`, and blocks the listed XGBoost/sklearn `.fit` methods before creating the normal Flask factory app. It binds `127.0.0.1:5053`, with debug/reloader disabled and CORS allowing only `http://127.0.0.1:5183`. The existing twelve-month scenario and next-six serving code may perform their documented transient NumPy seasonal/trend fit in memory; those calculations are not covered by the sklearn/XGB fit guards and do not save checkpoints.

The frontend needs the explicit API environment value above. Its unchanged Vite proxy sends relative `/api` requests to port 5000; with the explicit API URL, application client requests go directly to 5053. Launching from the repository root can produce the wrong Vite root, as the prior audit documented. `--strictPort` avoids silently selecting another frontend origin that the helper's CORS allowlist does not contain.

The separate older `reports/candidates/twelve_month_graph_only_20261021/demo_server.py` binds 5051 and intentionally returns 403 for `/api/scores`, district/history/predict/health/simulate and the scenario route. Its allowlist supports the older file-only research demonstration. That 403 is expected for that helper and makes it unsuitable for a full dashboard rehearsal. There is no reason to edit its guard for this task.

## Default Docker gap

This is source inspection only; no Docker build/config/run was executed.

- Both Docker build contexts are the repository root. `.dockerignore` excludes `data`, `models/checkpoints`, `reports`, local venv/packages, environment files and existing dashboard output.
- The API Dockerfile installs Python requirements and copies the remaining context. Compose provides read-only mounts only for `/app/data` and `/app/models/checkpoints`, with `create_host_path: false`. The direct bundle under `/app/reports/candidates/...` is therefore missing even if the two existing mounts are correctly supplied.
- As a result, the default package cannot provide direct research endpoints or the special Adilabad scenario source from the current descriptor. Other scenarios require the exact pinned national CSV/manifest through the data mount. Matching external PostgreSQL remains required for the full legacy UI.
- Compose neither creates a DB service nor restores schema/data/scores. Nginx forwards same-origin `/api/` and falls back to SPA `index.html` for deep links. These source settings have not been exercised by this review.

Small proposed follow-up fixes, **not implemented**: explicitly package or read-only mount the six immutable research files at their descriptor path; add a separate research/scenario asset readiness probe alongside legacy health; document the complete pinned release inventory and UI-default scenario in deployment/root metadata; distinguish the restricted 5051 helper from the normal full-dashboard audit helper in launch documentation. No model/data changes are needed to make those proposals reviewable.

## Source continuity and manual expectations

Reference commit `98c7056057b2a0370d377afa831f528f6d408481` is the preceding academic/six-month UI reference. Comparing Git blobs proves:

| Source surface | Continuity to reference |
|---|---|
| `dashboard/src/App.css`, `index.css` | Exact blob equality |
| `MapComponent.jsx`, `districtMap.js` | Exact blob equality |
| `pages/Alerts.jsx`, `pages/Simulate.jsx` | Exact blob equality |
| `App.jsx` navigation markup | Exact `<nav>...</nav>` equality; overall file differs |
| `Home.jsx` tier summary-card markup | Exact selected markup equality; overall file differs |
| `pages/DistrictDetail.jsx` | Overall file differs; independent graph/default view and loading/error mounting changed |

These findings are source continuity, **not a pixel or responsive-layout comparison**. The following are source-derived expectations to inspect manually; none is marked visually passed by this worker.

| Browser route / action | Expected interface / distinction |
|---|---|
| `/` | Academic prototype banner; Home/Alerts/Simulate navigation; four retained tier cards; source-qualified counts; Leaflet map and district list when a complete score response exists; score loading/error/retry messages otherwise |
| Click a matched map district / district-list row | Canonical `/district/<id>` navigation; unmatched geometry does not invent a scored district |
| `/district/HR-Kaithal` and `/district/HR-Kurukshetra` | Default experimental next-12-month view; own-district source, latest observation and estimated current depth disclosed; 12 explicit monthly scenario estimates if eligible; legacy score/history remain distinct |
| `/district/TS-Adilabad?view=scenario#forecast-graph` | Separate frozen-source Adilabad scenario, red curve and expandable 12-row estimate table; assumption/unvalidated disclosures |
| `/district/TS-Adilabad?origin_month=2024-01#forecast-graph` | Historical view selected by explicit origin; twelve calendar slots February 2024–January 2025, with M+1…M+11 gaps; final red ML marker and separate blue annual-baseline marker. Prior numerical values are historical evidence, not a new result from this static review |
| `/district/TS-Adilabad?view=historical#forecast-graph`, then Latest observed origin | Latest origin requested explicitly; unavailable ML remains unavailable with reasons; no silent older-origin fallback |
| `/district/AN-Nicobars?view=scenario#forecast-graph` | Own-history unavailable state rather than a borrowed district/zone curve, subject to current retained-source/runtime agreement |
| View buttons | Scenario removes `origin_month`; Historical selects direct graph. Explicit `view=scenario` takes precedence over an origin query |
| Recorded history | Source-marked monthly means and forward-filled history labeled separately; axis and text explain metres below ground and line direction |
| `/alerts` | Research risk indicators; All/Crisis/Warning/Watch/Safe filters; returned category count, historical-source qualification, loading/error/retry states |
| `/simulate` | District selector, rainfall/extraction controls, baseline/simulated index; extraction explicitly called a heuristic. Zero-change is the existing baseline parity contract; do not infer causal policy effectiveness |
| Browser refresh / narrow viewport | District deep link resolves; nav/cards/map/chart controls/text remain usable and do not overflow; inspect manually |
| Loading/error/retry | Forecast panel stays mounted during legacy district loading/failure; research/scenario retry buttons issue fresh requests. A transient state that never appears cannot be marked observed merely from source |

Any January-2024 direct value, current scenario date/value, score count or availability shown by a fresh runtime must be attributed to that runtime's evidence. This report only establishes retained source/asset continuity and prerequisites. Physical-well identity, datum continuity, historical input availability, prospective skill and production readiness remain unverified by this review.
