# XGBoost-only product and States page verification

Date: 25 October 2026. Branch: `feature/xgboost-only-states-ux`, based on `fe3b22a` (the locally updated main/origin-main revision inspected for this task). Changes remain uncommitted; nothing was merged, pushed or deployed.

## Outcome

The district forecast chart, tooltip and monthly table now show only the existing climate-conditioned XGBoost predictions. The States page has a searchable selector, local boundary map with selected-state highlighting, coverage cards, separate observed history, twelve-month XGBoost chart, monthly values, district links and a state comparison table. It has mobile layouts, keyboard controls, loading/error/unavailable states and retries. Forecast methods cannot be switched or substituted after an error. Existing six-month APIs, sensitivity simulation, scores/history and scientific baselines remain intact.

The previous state implementation actually used harmonic/trend projection directly on aggregated state history. It also bypassed manifest validation with a direct-CSV fallback and could use a hardcoded September 2026 origin. Its old evaluation must not be relabelled as XGBoost evidence. These serving paths were replaced with fixed-panel aggregation of the unchanged district XGBoost model. The old state report and all existing artifacts remain preserved.

The old States layout combined extensive inline styling, a rigid minimum column width, fixed map sizing and crowded chart content. The replacement uses scoped responsive grids, a full-width chart, a horizontally scrollable table and the existing AquaIQ palette/typography. No dependencies were added.

## Pipeline and availability

| Product | Request and actual computation |
|---|---|
| District twelve-month view | `fetchClimate12mForecast` → `/api/predict/climate-12m/<id>?months=12` → existing climate-conditioned XGBoost bundle |
| States summary and chart | `/api/states/summary?horizon=12`, `/api/predict/state/<id>?horizon=12` → verified monthly features → eligible individual districts → same twelve-month XGBoost → equal mean over a fixed panel |
| Existing six-month product | `/api/predict/<id>?window=next_six_months` → existing six-month climate XGBoost; unchanged |
| Simulation | Existing project-index sensitivity calculation; not a groundwater forecasting algorithm |

State panels require at least 50% of registered districts and two contributors, except one for a single-district state. These are explicit coverage safeguards, not validated representativeness thresholds. Zone fallback evidence is excluded. Missing districts are never assigned zero depth. Identity, model, feature generation, exact as-of date, units and all twelve target months are checked. Corrupt model/data returns a structured 503; insufficient coverage returns an empty forecast. Cache keys include state, date, model card, registry membership and verified feature identity. Caller mutation cannot change cached predictions.

On the existing local export at `as_of=2026-10-25`, **16/36** states/territories have available outlooks. Haryana contributes **19/22** districts; Tamil Nadu **30/37**; Ladakh **0/2**, with no forecast. The returned Haryana/Tamil Nadu/Ladakh payloads and nationwide summary passed frontend contract validation. A real Flask Haryana route returned HTTP 200 and twelve values identical to the earlier local smoke payload after the final cache/identity hardening. Cold nationwide computation took approximately **70 seconds** while another evaluation was running; repeated matching inputs are cached. Deployment latency and load testing remain outstanding.

History represents the districts reporting in each month; the future curve represents a fixed eligible panel. Neither is a representative state water-volume measure. Current anchors/lags may be estimated by the existing district history fit. Future weather uses origin-limited historical climatology, not realized future weather or live predictions. Provider acquisition/publication times and stable well composition remain unknown. Completed-month cutoffs are retrospective assumptions about timing.

## Frozen-model historical diagnostic

No production model was trained, tuned, selected or promoted. The existing artifact hash is `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`, with training-label cutoff **2019-12-31**. Origins were fixed at Jan/May/Aug/Nov in **2021–2025**, leaving 2020 embargoed. Each target required an exact source-marked observed label for every origin-selected panel district. The panel was never shrunk using target availability.

Across **720** state/origin attempts, **320** produced eligible forecast panels, **400** abstained, and **3,780** horizon cases lacked a complete observed target panel. Only **60** cases could be scored: the same **15 state targets in January 2026**, each forecast from four 2025 origins. They are not 60 independent target observations, a new blind test or a prospective campaign. No eligible target panels existed for origins in 2021–2024. Evaluation uses covered-district means, not independently acquired statewide ground truth.

| Matched cohort/method | N | MAE (m) | RMSE (m) | Pooled R² |
|---|---:|---:|---:|---:|
| XGBoost | 60 | 1.505 | 2.314 | .837 |
| Latest-observed persistence | 60 | 1.457 | 2.234 | .849 |
| All-three matched, including annual seasonal naive | 0 | unavailable | unavailable | unavailable |

Persistence holds each district's latest observed origin depth, then averages the same panel. This differs from a persistence reference holding an *estimated* current anchor; the anchor is saved separately. Seasonal naive requires the exact target-minus-twelve-month observation for every panel member. No complete January 2025 panel was available; no replacement seasonal values were fabricated.

| Horizon | N | XGBoost MAE / RMSE (m) | Persistence MAE / RMSE (m) |
|---|---:|---:|---:|
| M+2 | 15 | 1.407 / 2.179 | 1.457 / 2.234 |
| M+5 | 15 | 1.718 / 2.388 | 1.457 / 2.234 |
| M+8 | 15 | 1.497 / 2.428 | 1.457 / 2.234 |
| M+12 | 15 | 1.399 / 2.254 | 1.457 / 2.234 |

Other horizons have no eligible labels. **XGBoost does not beat persistence overall.** Its lower M+2 error and M+12 MAE do not establish a reliable horizon advantage from this single target month. High pooled R² is not evidence of superiority. No model choice or threshold was changed after these results. State-wide, all-season and prospective skill remain unverified; HGB remains abstained.

Evidence: [evaluation.json](evaluation.json), [cases.csv](cases.csv), [panels.json](panels.json), [exclusions.csv](exclusions.csv). The runner never trains or accesses the database. The original source loader already rejects conflicting observed/imputed flags; the state layer adds a defensive exclusion, with regression coverage. The current export has zero conflicting flags, so this hardening did not alter the completed evaluation.

## Tests and preservation

- Full backend suite: **1,202 passed, 14 skipped**, 11 warnings. After the final metadata/cache hardening, all **22 state tests passed**. Database integration tests were not enabled. Existing unit tests may fit tiny isolated fixtures; production artifacts were not trained or changed.
- Frontend: **146 passed**. Lint passed. Production build passed; the existing large-bundle warning remains (about 865 kB uncompressed). Builds went to ignored scratch folders.
- Browser regression passed on the final build: search/keyboard selection, map selection/highlight, late-response rejection, twelve rows, hover values, unavailable/model failure and retries, boundary failure and retry, and 1440/768/390-pixel layouts without page overflow. Screenshots were visually inspected. Browser API fixtures are explicitly synthetic, blocked external requests, and were never mixed with real observations. Evidence is in `scratch/state-browser-54Ntbl/`.
- Initial restricted backend runs failed because pytest could not create temporary directories. The approved rerun with normal local permissions passed. The browser initially could not reach its local test server; the approved local rerun passed. These unsuccessful runs are not counted as successful tests.
- [preservation.json](preservation.json) verifies **1,520 protected files unchanged**, covering existing data, model bundles/checkpoints, prior reports, configuration and the local SQLite file. This baseline was recorded before verification in this continuation; it does not certify external PostgreSQL contents. No PostgreSQL integration or production write was performed. No source refresh, download, migration or real shadow issuance occurred.
- The twelve-month pointer, card and referenced model are already tracked under `models/artifacts/` and included by the existing Docker configuration. No artifact, pointer, `.gitignore`, dependency or deployment configuration changed. Verified features and the legacy runtime database/checkpoints remain external deployment prerequisites; a code-only clone is insufficient. Deployment was not tested or performed.

## Frontend method audit

| Matches | Classification and disposition |
|---|---|
| District baseline lines, tooltip/table columns; old state projection/controls | User-facing alternative forecast functionality removed or replaced with actual XGBoost aggregation |
| `ResearchForecast`, `ExperimentalScenario`, `ForecastGraphPanel`, their contracts and API helper exports | Retained internal/historical research modules with existing tests; absent from the active application component/route graph |
| District methodology, Home historical benchmark text, preserved README result tables | Accurate explanatory/historical material; retained without competing prediction lines or superiority claims |
| `Simulate` and `simulationComparison` baseline/scenario references | Existing uncalibrated index sensitivity analysis, explicitly not groundwater-depth prediction; preserved |
| `ClimateInputs` | Retained separate six-month XGBoost input view; obsolete seasonal/trend wording corrected |

## Changed files and reproduction

See [changed_files.txt](changed_files.txt) for the exact list. Core changes are `models/state_forecast.py`, `api/routes/state.py`, district/state chart components and contracts, `States.jsx`/`States.css`, `StateMapComponent.jsx`/`stateMap.js`, routing/API helpers, regression tests, the README and [state methodology](../../docs/STATE_XGBOOST.md). All old reports and research artifacts are preserved.

From the repository root, using the existing installed environment:

```powershell
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m pytest tests/test_state_forecasting.py -q
npm --prefix dashboard test
npm --prefix dashboard run lint
npm --prefix dashboard run build -- --outDir ../scratch/xgb-states-build-final
.\venv\Scripts\python.exe -m scripts.evaluate_state_xgboost --output reports/xgboost_states_reproduction_new
```

The evaluation destination must be new. Optional browser commands using the already installed local runtime (no installation/download required):

```powershell
$env:NODE_PATH='C:\Users\Yasharth\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE='C:\Users\Yasharth\AppData\Local\ms-playwright\chromium_headless_shell-1243\chrome-headless-shell-win64\chrome-headless-shell.exe'
$env:AQUAIQ_UI_BUILD='scratch/xgb-states-build-final'
node dashboard/tests/stateBrowser.cjs
```

The product cleanup and local checks are complete. This demonstrates an integrated experimental XGBoost interface and a reproducible limited historical diagnostic. It does not demonstrate representative statewide accuracy, improved accuracy, validated real-time weather inputs, prospective forecasting skill or production readiness.
