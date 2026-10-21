# AquaIQ: twelve-month research application finalization

Started 20 October; finalized **21 October 2026, Asia/Kolkata**. The directory retains its creation date. Local branch: `experiment/12-month-horizon`. HEAD and recoverable `main`: `98c7056057b2a0370d377afa831f528f6d408481`. Nothing staged, committed, pushed or deployed.

## Result

**Twelve calendar months is now the primary research objective and application experience.** This follows the user's explicit research-scope decision, not a demonstrated accuracy advantage. Home and district pages present a new direct M+12 panel above the retained legacy products. A dedicated `/research` page mounts only this file-backed panel, avoiding legacy score/history requests. Unsupported districts and missing evidence remain visible as unavailable; the map, six-month requests, monthly 1–6 chart, simulation and active checkpoints retain their meanings.

A new fixed-settings XGBoost artifact enables an explicit **historical Adilabad research demonstration**. It is an unselected comparator and performs substantially worse than the annual baseline on its own historical check. **Current ML is unavailable, HGB real-shadow prediction remains blocked, and production release is NO-GO.** No prospective forecast or shadow record was created.

All seven requested reports were found at their stated paths and inspected. Existing experimental helpers, evaluator, protocol, cohorts, model fits, predictions and reports were reused read-only. The old report's decision to retain six months remains historical evidence; this later user-authorized objective does not rewrite it.

## API, UI and artifact contracts

| Component | Final contract |
|---|---|
| Catalog | `GET /api/research/forecast`: primary horizon 12, canonical scope, observed origin months, model identity and limitations; no database resolver |
| Detail | `GET /api/research/forecast/TS-Adilabad[?origin_month=YYYY-MM]`; optional `months=12` only; unknown/repeated query parameters rejected |
| Target | Exact calendar M+12, never row shifting. Origin must be finite and explicitly observed; historical evaluation labels must also be explicitly observed and not imputed |
| Baseline | One effective annual baseline: persistence = annual seasonal naive = observed origin depth, because target−12 = origin. Baseline can remain available while ML abstains |
| Output | `historical_research` or `current_vintage_research`; `computed_at` aware UTC, `forecast_issued_at=null`; ML and baseline separately nullable |
| Evidence | Selected/latest source month, reported-date bounds, well count, panel hash, observed/imputed status and per-feature observed/carried/derived/missing provenance. Acquisition and availability remain unknown |
| ML gate | Historical-only artifact; observed origin and exact observed target; first permitted origin January 2023 after cutoff plus twelve full embargo months; finite inputs and compatible provenance; weather carry ≤2 months, GWL carry ≤3 |
| Byte/schema gate | Before loading: horizon, ordered features/schema hash, physical units, source generation, fixed settings, scope, cutoff, protocol/configuration identity and manifest/card/model/snapshot/provenance checksums. Confined research namespace; no six-month substitution |
| Geographic scope | `TS-Adilabad` only, strict source-name/polygon-agreement reaggregation; no zone fallback or national generalization. Agreement is metadata consistency, not independently verified geography |
| Legacy | `/api/predict/<id>` still defaults to six months; `window=next_six_months` remains monthly horizons 1–6. `/api/config` and API root explicitly distinguish primary and secondary products |

Twelve inputs, in fixed order: `gwl_current`, `gwl_lag_3mo`, `gwl_lag_6mo`, `rainfall_current`, `rainfall_3mo_avg`, `monsoon_deficit_pct`, `temperature`, `evapotranspiration`, `water_balance_proxy`, `season_Kharif`, `season_Rabi`, `season_Zaid`. Units: groundwater m below ground level; rainfall/ET mm per month; temperature °C. No learned preprocessing was newly fitted. Native XGBoost missing handling preserves the six early training cases with missing lag inputs; inference requires complete inputs. Carry age is relative to the feature's required source month, so an observed six-month lag has carry age zero.

The loader requires explicit `m_bgl` for every observed measurement. Four unobserved padded calendar rows may omit measurement units; they cannot supply an observed baseline or label. Explicit incompatible units remain rejected. Derived features retain recursively checked historical dependencies; historical target values classify/display the retrospective output but never enter the estimator input vector.

## New isolated artifact and historical evidence

Version: this directory's `artifact/`; descriptor: `research/twelve_month_app.json`. Fixed XGBoost: 500 trees, depth 6, learning rate .01, subsample .8, seed 42, square-error objective, `n_jobs=4`. **One fit**, no tuning, family selection, HGB fit or active-pointer replacement. Training has **164 observed target pairs**, origins May 2007–December 2020, target months May 2008–December 2021; cutoff **2021-12-31**, first permitted application origin **2023-01**. All training cases are Adilabad; 158 are fully complete, but all 164 remain in native-missing training.

The retained strict grid has 233 months, May 2007–September 2026; 229 source-marked observed months end May 2026. There are 2,817 accepted well-months, 15 provider IDs, unconfined aquifer records, and changing panels of 6–15 wells. A panel hash identifies agency/provider-ID/equal-weight membership, not certified physical continuity. Measuring-point datum changes, replacements, correct physical locations and actual acquisition/publication/receipt/availability times remain unverified. No coordinates, dates or identifiers were invented or repaired.

| Own fixed-artifact check: 24 paired historical cases | MAE (m) | RMSE (m) | R² |
|---|---:|---:|---:|
| Annual baseline | .645 | .877 | .881 |
| New fixed-2021 XGBoost | 2.145 | 2.664 | −.101 |

Origins January 2023–December 2024; observed targets January 2024–December 2025; one district. These cases were previously inspected, **not a fresh blind test**. [Saved rows](artifact/historical_checks.csv) and [build verification](artifact_build.json) preserve their own identities and results. No subgroup/result was used to retune or select the application artifact.

The first builder fitted/reloaded successfully but exited 1 on an overly strong assumption of exact agreement with the old 2024 checkpoint. Training case IDs/order, feature values including NaNs, labels and parameters were confirmed identical. Nevertheless the maximum difference on twelve 2024 cases is **.188841 m**. The old runner used an outer `threadpool_limits(1)` context; the new builder omitted it while retaining `n_jobs=4`. That runtime difference is confirmed; **its causal responsibility is not established**. No refit was made. A separate completion helper packaged the existing fit and checked its own reload predictions, retaining the failed log and original builder. This artifact must not be described as reproducing the old fit.

The **unchanged original expanding study** remains a separate 792-pair, 33-district historical comparison:

| Method | MAE (m) | RMSE (m) |
|---|---:|---:|
| Persistence = annual seasonal naive | 1.191 | 1.458 |
| Expanding XGBoost | 1.159 | 1.420 |
| Per-district Linear Regression | 1.928 | 2.456 |
| Separate twelve-month HGB | 1.222 | 1.505 |

Its XGBoost RMSE-difference interval **[−.317, +.264] m** crosses zero; temporal and panel sensitivities reverse the advantage. Source-name/coordinate conflicts undermine geographic interpretation. These scores cannot be assigned to the new fixed-cutoff artifact. The earlier six-month primary benchmark also remains unchanged: seasonal naive outperformed HGB on primary MAE/RMSE. No reliable prospective ML advantage has been established at either horizon.

### Artifact identity (SHA-256)

| Identity | SHA-256 |
|---|---|
| Protocol | `1a93abf0a52eb44263d05090137df2c7000f83c3d0cf2c3e2843c56ac1ec57c2` |
| Canonical configuration contract | `1a539e3647ae4e0a343e23d3252ca41f7994f09301be8c773cfc94b31e55bac2` |
| Whole descriptor file | `1b66b49fb66439c1c1f2f27215fccd49cb62451d6ce8bcc466bbc1765c3f5e24` |
| XGBoost model | `f94911f5e1a6c3e8b4bbbb82d6a4c6ec87b5d601abbfd774801afc046aa5455f` |
| Model card | `c399ed9cfa5c1746c874659d89bd1d69d92ea841dc262b7d0dfab89bac9e0bd7` |
| Manifest | `e390b0e78221560e66b50610d4ef37cb37225d34232589c4d52064713ef27165` |
| Feature snapshot | `728677ebfbe103f0d38b53fd0bd02deb8a4d647f15f5bb199d392a29be33569e` |
| Per-input provenance | `d069f1c623dead6c8678a2e8be6d90bc0f51135682973b75f6bbdd3f948ac3e3` |
| Source provenance | `2e6b5e5d43db8df0b681b82ac4ec6fbf4d84ff359c1c006acd6b93da4f0322f1` |

Configuration hash means canonical compact/sorted contract JSON, not the descriptor's file checksum. The descriptor separately pins the manifest, which pins the card, snapshot and provenance; the card pins model bytes. Source hashes, training membership, fixed settings and caveats are in the card and frozen build plan. No active pointer references this bundle.

## Demonstration and checks actually executed

- **229 Python tests passed, 1 skipped, 3 deliberately deselected** in the final targeted run. The Windows directory-symlink test requires privileges/developer mode; two preprocessing tests plus one production-bundle test were deselected because they fit unrelated estimators. No unrestricted suite or DB-dependent physical-feature test was run. [JUnit](python-tests-final-03.xml), [command/exit receipt](python-tests-final-03.json).
- **23 frontend tests passed**, lint exit 0, fresh isolated Vite build exit 0. Tests include response validation, exact M+12 arithmetic, baseline/null states, mocked APIs, escaped text and in-memory React rendering. Existing monthly and map tests remain. Build retains a nonfatal >500 kB bundle warning and an out-of-root output notice; no old `dashboard/dist` build was replaced. [Tests](frontend-tests-final-03.txt), [lint](frontend-lint-final-03.txt), [build](frontend-build-final-03.txt).
- The [in-process file-only demonstration](local-demo-verification.json) passed under database/fitting guards. All 24 API estimates match archived fixed-artifact predictions within `1e-8 m`; explicit January/February 2025 weather carries from December 2024 are disclosed. January 2024 → January 2025 returns ML **7.571101 m**, baseline **6.836667 m**, observed target **6.831333 m**. The target is displayed separately, not supplied to the model.
- Default May 2026 → May 2027 returns **ML null**, annual baseline **6.553333 m**, and explicit missing rainfall/three-month-rain/deficit/temperature/ET/water-balance plus historical-only reasons. It does not fall back to February 2025 merely because that older row has complete weather. Unsupported districts never borrow Adilabad or legacy artifacts.
- The first real-bundle smoke check failed on the four padded rows' missing unit cells. Only the new adapter was corrected, with positive/negative regression tests; frozen bundle bytes were preserved. Preliminary runs (45/149 agent checks, broad 205 passes, focused 57 passes, frontend 22 then 23) are retained and **not added as unique coverage**.
- Guarded Flask and Vite development servers reported startup on temporary localhost ports 5051/5181. **HTTP/browser end-to-end verification did not pass**: sandbox socket reads failed with WinError 10013; host and direct no-proxy probes timed out; browser automation twice failed before opening a tab because kernel assets could not be written (OS error 3). The cause of localhost timeouts is unresolved. No full browser rendering, legacy runtime or public deployment is claimed. Both temporary server sessions were stopped; existing 5000/5173 services were not changed. [Attempt records](http-demo-attempt-02.json).
- Python AST/strict-JSON checks, tracked `git diff --check`, new-source whitespace and narrowly scoped sensitive-value checks are recorded in [quality/security evidence](quality-and-security.json). This is not publication approval or a whole-private-tree sanitization claim.

## Preservation and security

[Before inventory](before.json), intermediate [receipt](preservation.json) and [final receipt](preservation-final.json) compare **936 pre-existing files: 926 unchanged and exactly 10 authorized source/documentation changes; zero unexpected changes**. The receipts include active checkpoint/pointer/card files, existing datasets, Telangana acquisition and normalized research data, saved row predictions, old twelve-month code/artifacts and prior reports. Database entry points were not used; no database checksum or independent database-contents verification is claimed.

The two original cookie-bearing provenance files remain unchanged and private. Their sensitive values are never emitted; the scoped review checks that known private header values are absent from this change set. No publication bundle was prepared, and no blanket Git add was performed. Publication still requires a separate reviewed allowlist and explicit authorization; ignored assets must not be bulk-added.

`AquaIQ-Rainfall-Staging` was read-only verified **Disabled / enabled=false**, both before and after implementation; [final scheduler receipt](scheduler-final-state.json). No task change, refresh, ingestion, data download, schema/database operation, production scoring, new dependency or HGB fit was performed.

Modified existing files: `README.md`, `api/app.py`, `api/routes/scores.py`, `api_spec.md`, `dashboard/index.html`, `dashboard/src/App.jsx`, `dashboard/src/api.js`, `dashboard/src/pages/Home.jsx`, `dashboard/src/pages/DistrictDetail.jsx`, `deploy/README.md`.

New integration files: `api/routes/research.py`, `models/research_forecast.py`, `tests/test_research_forecast_api.py`, `dashboard/src/components/ResearchForecast.jsx`, `dashboard/src/components/researchForecastContract.js`, `dashboard/tests/researchForecast.test.js`, `research/twelve_month_app.json`. New artifact, helper, report and evidence files are confined to this finalization directory; isolated builds/test fixtures use fresh `scratch/` paths. [FILES.json](FILES.json) inventories them. The earlier untracked twelve-month implementation remains pre-existing preserved work, not newly created by this phase.

## Academic packaging and remaining limitations

[COMMANDS.md](COMMANDS.md) gives executed checks and local demonstration commands. Existing Python 3.13, Node 22.18 and installed requirements/dashboard packages were reused. No setup/download/install was performed. A clean GitHub clone lacks ignored datasets, checkpoints, this uncommitted integration and populated legacy DB; it cannot reproduce this local state by itself. The twelve-month panel requires its descriptor and **complete exact hashed artifact bundle**, plus the existing Python/runtime source. Legacy pages additionally require the matching active assets, processed data, configuration and populated database. Do not run setup, migrations, scoring or refresh merely to display research evidence.

Names of relevant environment settings (no values/credentials disclosed): optional `AQUAIQ_RESEARCH_CONFIG`, `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG`, `AQUAIQ_CORS_ORIGINS`, and frontend `VITE_API_URL`. Legacy-only DB settings are `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`; retain local `.env` privately. The guarded demo helper supplies its own localhost-only port/CORS configuration and blocks legacy routes/DB/fitting. Actual browser connectivity must still be checked by an evaluator on the host.

The 0–100 crisis score remains a project-defined, uncalibrated index, not a probability or official classification; its legacy components were not recalibrated for twelve months. ANN/MLP agreement with fuzzy-generated labels is not independent crisis-outcome validation. Extraction remains heuristic sensitivity analysis, not a proven causal intervention estimate. These components were preserved, not expanded.

## Submission/release checklist

- [x] Primary direct M+12 research flow and explicit observed origin/target; separate legacy six-month/monthly products.
- [x] One mathematically correct annual baseline, honest historical comparison, current/unavailable states and supported geography visible in UI/docs.
- [x] Dedicated file-only research page, strict incompatible-artifact rejection, fixed historical artifact/card/provenance and targeted tests/build.
- [x] Existing models/data/reports/user work preserved; rainfall task disabled; no DB, downloads, HGB refit, shadow issuance, staging, commit, push or deployment.
- [ ] Host browser/end-to-end demonstration verified; automation and localhost connectivity remain unresolved.
- [ ] Publication approved after sensitive-file/asset allowlist review; this work remains local and uncommitted.
- [ ] Prospective accuracy, stable physical wells/datum/geography, contemporaneous input availability, actual acquisition lead and broader generalization established.
- [ ] Production release: **NO-GO**. It would require separately approved prospective design/artifact workflow and real archived forecasts before newly arriving observed targets, reliable provenance/current inputs, independent outcome validation and operational/security checks. Do not change M+12 or features to bypass these gates.

**Demonstrated:** exact calendar targets, historical observed-label comparison, explicit annual reference, restricted artifact loading, honest API/UI states and preservation. **Unverified:** useful future ML skill (the new artifact loses to baseline historically), twelve full months of operational lead, nationwide accuracy, calibrated crisis risk, causal extraction effects and production readiness.
