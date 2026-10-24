# AquaIQ frontend UX implementation

Started 23 October 2026; completed 24 October 2026 (Asia/Kolkata).

Implemented locally on `codex/next-12-months-ux`, based on `929985142ee634ae840b669010aed9ecc540c57a`. Changes are uncommitted and unpublished; there is no remote branch or PR link yet. Main was not changed or pushed.

## Inspection and exact search diagnosis

Inspected the actual frontend, API client, district mapping, existing tests, scenario/research contracts and simulation route before editing. Reviewed the fetched draft `origin/ui/next-12-months-cleanup-simulator` at `84d30c424c8f21d9ec7b914d5267862cf7365f12` without checking it out or replacing it. Its added search component was not mounted; the draft was not applied wholesale.

The user confirmed, with a screenshot and a direct reply, that the broken control is **“Search district…” at the top right above the Home map**. There was no corresponding district-search field above the district forecast graph.

The original `MapComponent.handleSearch` ran on every input change, depended on `geojsonLayer.current`, searched boundary names and zoomed Leaflet to a match. It did not provide canonical district suggestions, selection/navigation, ambiguity resolution or useful no-match feedback. Before geometry loaded it returned silently; a canonical district without its own polygon could not be found this way.

The same `.map-search` location now mounts `MapDistrictSearch`/`DistrictSearch`, using the existing `fetchScores()` catalog supplied by Home. Query state feeds canonical name/state/ID matching; click or Enter resolves a specific record and invokes Home's existing district-click path. `districtForecastPath()` navigates to the encoded canonical `/district/:id#forecast-graph` route. `DistrictForecastGraph` loads only that district's existing experimental scenario API. Search no longer reads Leaflet geometry. The map header keeps search on the right on desktop and stacks it on mobile.

## Resulting behavior

- Every normal district page displays the existing next-12-calendar-month experimental scenario. Old `origin_month`/`view` URLs cannot select the historical M+12 panel. Historical research components, APIs, artifacts and audit tests remain available.
- Chart and 12-row table share the same validated scenario rows, in API-defined chronological order. Loading, errors, retry and insufficient-history reasons stay visible; other districts or historical numbers are never substituted.
- Condensed the global banner and repeated first-screen explanations. District name, project index/tier, source month/age, experimental label and graph remain prominent. Detailed qualifications, assumptions and hashes are collapsed.
- Original Home search now supports partial name, state, canonical ID, normalization, live labelled suggestions, click/Enter/arrows, ambiguity, no-match, loading and retry. The simulator reuses it; typing clears the confirmed selection so stale districts cannot be submitted.
- Simulator adds six presets, editable sliders, reset, guarded sequential comparisons, per-result failures, accessible bars/table and CSV export. Results retain their submission district and inputs. Missing/invalid values remain unavailable. CSV protects text formula prefixes and escapes commas, quotes and line breaks. State remains in memory.
- Recorded history retains explicit nulls and inserts null calendar buckets where a month is absent. Source-marked observations and forward fills stay separate; neither line connects across nulls.

No backend contract, dependency, horizon, scoring weight, training process or prediction value was changed. `/api/simulate` still adjusts rainfall-related features and applies the existing extraction sensitivity heuristic. Its index changes are not causal groundwater effects.

## Verification

| Check | Actual result | Evidence |
|---|---|---|
| Configured frontend suite | **99/99 passed**, exit 0 | `frontend-tests-03.txt` |
| Configured lint | Passed, exit 0 | `frontend-lint-02.txt` |
| Configured production build | Passed, exit 0 | `frontend-build-01.txt` |
| Relevant guarded Python API tests | **47/47 passed**, exit 0 | `backend-tests-01.txt`, `backend-tests.xml` |
| Diff whitespace | Passed after removing one extra EOF blank line | `git diff --check` |
| Protected local files | **1,467 unchanged; 0 changed/missing; 0 new files in protected folders** | `before.json`, `preservation.json` |

The first full frontend run had six obsolete presentation assertions expecting the removed banner/toggle/long copy; its log is retained as `frontend-tests-01.txt`. Updated only the superseded UI expectations while retaining scientific/API validation assertions. The next run passed 93/93; adding the six exact-map-search workflow tests produced the final 99/99 result. No numerical source expectations were changed.

The build uses the configured Vite build with a fresh output-directory override under this report, preserving the original `dashboard/dist`. Warnings: the output is outside Vite's project root and is deliberately not emptied; the main JS chunk is approximately 838 kB, exceeding Vite's 500 kB advisory. No new dependency or unrelated bundle optimization was introduced.

### Real browser checks

Browser control initially failed in the prior runtime; on resumption it became available. Sandboxed preview processes bound their ports but were unreachable. After verifying their process identities, only those newly launched processes were stopped and restarted outside the network-restricted sandbox. No firewall or security setting was changed. The existing audit server forces DB sessions read-only and blocks active ML `.fit`; its existing transient scenario calculations remain normal endpoint behavior. The Python test wrapper additionally forbids all live DB connections and transient projection fitting.

Verified against the actual localhost frontend and existing API on ports 5183/5053:

1. Typed `Kaith` in the original Home box, saw `Kaithal / Haryana · HR-Kaithal`, clicked the actual option, and reached `/district/HR-Kaithal#forecast-graph`. The page rendered its own 12 months, November 2026–October 2027. Expanded the 12-row table (`kaithal-table.txt`). Source month January 2026 and its nine-month age remained visible.
2. Enter on `Bilaspur` stayed on Home with two state-labelled choices. A nonexistent query showed the no-match message. Enter on `mh_mumbai suburban` opened `MH-Mumbai_Suburban` despite the absent matching boundary; its own source age was visible as 69 months.
3. `PY-Mahe` opened a working page with explicit “Monthly estimates unavailable” and the no-observed-history reason, without a replacement graph.
4. A Kaithal URL with `view=historical&origin_month=2024-01` still rendered “Next 12 months” and no historical-toggle button.
5. Selected Drier monsoon, verified controls −20% rainfall/0% extraction, and compared all six Jaipur presets through the existing API. All six returned available: baseline 70; drier 70; wetter 70; higher extraction 74; reduced extraction 66; combined 74. These are project-index outputs, not accuracy or physical-effect evidence. Export downloaded a CSV with the same six results and source status `historical_forecast`; contents were inspected.
6. Changing simulator query to `HR-Kaithal` disabled Run until Enter confirmed selection. Old Jaipur results retained their name and a different-district notice. Reset restored 0%/0%; rerun returned Kaithal baseline/scenario 79/79, delta 0.
7. Checked the simulator at a requested narrow breakpoint of 390 × 844. Document viewport/page width both measured 382 CSS pixels (scrollbar excluded), with the wide comparison table in its own focusable scrolling region. Presets, controls and bars remained readable. Restored the default viewport afterwards.

Screenshots: `home-search.jpg`, `kaithal-graph.jpg`, `simulator-desktop.jpg`, `simulator-mobile.jpg`. The mobile full-page capture includes the sticky navigation at its capture scroll position; it is not a separate content banner. Browser/API checks are a targeted smoke test, not exhaustive coverage of every district or fault condition. Partial API failures, escaping and retry are covered by automated tests rather than deliberately breaking live services.

## Modified and added implementation files

All paths below are relative to `C:/Users/Yasharth/Downloads/AquaIQ/`.

Modified source:

- `dashboard/src/App.css`
- `dashboard/src/App.jsx`
- `dashboard/src/components/DistrictForecastGraph.jsx`
- `dashboard/src/components/ExperimentalScenario.jsx`
- `dashboard/src/components/MapComponent.jsx`
- `dashboard/src/pages/Alerts.jsx`
- `dashboard/src/pages/DistrictDetail.jsx`
- `dashboard/src/pages/Home.jsx`
- `dashboard/src/pages/Simulate.jsx`

Added source:

- `dashboard/src/components/DistrictSearch.jsx`
- `dashboard/src/components/districtNavigation.js`
- `dashboard/src/components/districtSearch.js`
- `dashboard/src/components/recordedHistory.js`
- `dashboard/src/components/simulationComparison.js`

Modified tests:

- `dashboard/tests/experimentalScenario.test.js`
- `dashboard/tests/forecastGraph.test.js`
- `dashboard/tests/forecastGraphPresentation.test.js`
- `dashboard/tests/researchForecast.test.js`

Added tests and purpose:

- `dashboard/tests/districtSearch.test.js`: normalization, ambiguity, keyboard decisions, callbacks, safe text and accessible states.
- `dashboard/tests/mapSearchWorkflow.test.js`: actual mounted search adapter and option callback through canonical navigation and scenario client; exact Enter, no geometry, API failure/retry. Uses SSR/handler/API-stub contracts, alongside the separate real browser check above.
- `dashboard/tests/districtForecastWorkflow.test.js`: real wrapper/route SSR always uses the monthly scenario, including legacy query strings and loading.
- `dashboard/tests/recordedHistory.test.js`: explicit/absent missing months, provenance distinctions and actual chart `connectNulls={false}`.
- `dashboard/tests/simulationComparison.test.js`: preset/control handlers, exact payloads, sequential requests, duplicate-run guard, partial failures, zero/negative deltas, unavailable values, table/CSV agreement and safe escaping.
- `dashboard/tests/helpers/loadJsx.js`: transforms real JSX with installed Vite for SSR/handler tests; no new library or substitute UI component.

Added evidence is confined to `reports/frontend_ux_20261023_01/`: this report, preservation scripts/manifests, command logs, Python XML/temp output, isolated build and browser screenshots/text. `changed-files.json` lists frontend paths, sizes and hashes; `evidence-files.txt` lists the report artifacts.

## Reproduction

From the repository root in PowerShell, using installed dependencies:

```powershell
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
# Choose a fresh outDir; do not overwrite dashboard/dist or a prior evidence build.
npm.cmd --prefix dashboard run build -- --outDir ../reports/frontend_ux_REPRO_NEW/build
.\venv\Scripts\python.exe -B reports/end_to_end_verification_20261022/run_safe_tests.py tests/test_api.py tests/test_api_audit_regressions.py -q -p no:cacheprovider --basetemp=reports/frontend_ux_REPRO_NEW/pytest_tmp
git diff --check
```

To run the same read-only localhost preview in separate terminals, if ports are free:

```powershell
.\venv\Scripts\python.exe -B -u reports/end_to_end_verification_20261022/audit_server.py
```

```powershell
$env:VITE_API_URL = 'http://127.0.0.1:5053'
npm.cmd --prefix dashboard run dev -- --host 127.0.0.1 --port 5183 --strictPort
```

The preview requires the existing local DB to be available; tests use mocks and forbid DB connections. The default Vite proxy still targets port 5000; the preview's API URL override is process-local and did not modify configuration.

## Preservation and limits

SHA-256 checks cover active models, local datasets, backend/database code, preprocessing, research artifacts, every pre-existing report, configuration/package files and the old built dashboard. No model was trained, tuned, selected or promoted; no saved checkpoint, dataset or research result was rewritten. HGB remains abstained. No shadow record was created. Database contents were protected by read-only connections, not independently proven by a full before/after DB dump.

This work demonstrates functional UI selection, correct monthly-scenario presentation and controlled sensitivity comparisons. It does not establish prospective groundwater skill, nationwide accuracy, causal extraction effects, current observations for stale districts, stable well panels, or production readiness. The existing scenario can extrapolate from very stale history; the visible source age and retained Details qualify this behavior. No methodological change was made to conceal those limitations.

Implementation and targeted verification are complete. Publication remains a separate action: review the local diff/evidence, use a secret-safe allowlist, then explicitly authorize any commit and feature-branch push. No claim is made that the working tree is already on GitHub.
