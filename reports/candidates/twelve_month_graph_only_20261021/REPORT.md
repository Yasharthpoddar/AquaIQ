# Existing UI: twelve-month graph integration — 21 October 2026

**Implemented locally on `experiment/12-month-horizon`, HEAD `3a4936b` unchanged. Nothing committed, pushed or deployed.** The original Home, navigation, map, summary cards and district layout are restored/preserved. The existing district graph now requests twelve calendar positions using the validated twelve-month endpoint. **A complete twelve-number monthly curve remains unavailable:** the frozen artifact supports only M+12. Unsupported intermediate values stay null; no interpolation, fabricated values or six-month artifact extension is used.

## Original graph and final data flow

Previously: `DistrictDetail.jsx` → `fetchPredict(id, {window:'next_six_months'})` → `/api/predict/<id>` → `forecast_next_six_months`; six weather-conditioned monthly values were validated and plotted in the existing graph card. The original endpoint and horizons 1–6 remain unchanged for explicit legacy requests.

Now: the **same card** → `fetchResearchGraph(id)` → `/api/research/graph/<id>?months=12` → `models/research_graph.py` → the existing `research_forecast()` loader. The loader validates the twelve-month model/card, ordered features, units, generation, configuration, source/model hashes, cutoff and scope before any eligible historical prediction. It never substitutes a six-month checkpoint.

- Exactly twelve target slots are calculated with calendar arithmetic from the observed origin: M+1 through M+12. Returned target order is validated; unknown origins retain null labels rather than guessed dates.
- The compatible artifact supplies **one direct M+12 estimate**, not forecasts for M+1–M+11. Intermediate ML and baseline values remain null with reasons. The final target is exactly origin+12.
- The annual baseline remains the observed-origin reference at M+12, where persistence equals annual seasonal naive. It appears as clearly labelled text, not an ML line or invented monthly baseline curve.
- The existing responsive container, line-chart type, red color, dimensions/margins, axes, tooltip/legend components, dots, card placement and retry interaction are preserved. Only the trace label changes to identify the actual M+12 research estimate. Original responsive tick selection is retained; twelve data-domain months do not guarantee twelve simultaneously visible tick labels on narrow screens.
- The original future-weather table belonged to the replaced six-month graph product. It is removed only from this card because the direct M+12 contract supplies no future monthly-weather series. Its legacy API/model implementation is untouched. Source/input provenance, scope, unavailable reasons and research limitations remain in the card.

Home is source-identical to the six-month baseline `98c7056`. Map, alerts, simulation and CSS also match that baseline. App layout/navigation match it apart from retaining the optional `/research` route/import; there is no research navigation link or prominent replacement panel. District loading/error behavior and outer score/history layout remain in place.

## HTTP 403: diagnosed, deliberately retained

Exact request: **GET `http://127.0.0.1:5051/api/scores`**, issued by the frontend at `http://127.0.0.1:5181/`. The safe diagnostic received HTTP 403 with `Legacy routes are excluded from this read-only demonstration.` CORS allows that frontend origin. The real `/scores` route has no authentication decorator, and the frontend request does not require an authorization token. No credentials were printed or supplied.

The cause is the local demonstration helper's `before_request` allowlist, **before the scoring route/database is reached**. This is a deliberate demo boundary, not missing authentication or a CORS failure. The existing error and dashed-score UI remain. No authorization rule was removed, scores fabricated or database accessed. [Diagnostic evidence](403_diagnostic.json).

The previous helper is unchanged. A **new** helper in this directory permits only the additional file-backed graph route while continuing to block legacy requests, database access, fitting and mutations. Its localhost API was restarted after matching the existing process to the previously launched demo. The first restart attempt was not executed because automatic approval review hit a usage limit; a normal approval retry after its reported reset succeeded. No approval bypass was used.

The protected demo still blocks `/api/district` and other legacy routes. Consequently the original district page can stop at its existing district-error UI before displaying the chart. A full district-page demonstration requires a separately configured matching legacy/database runtime; this task did not weaken the demo guard to obtain it.

## Verification and actual runtime behavior

| Check | Result |
|---|---|
| Final targeted Python run | **259 passed, 1 skipped, 3 deselected**; [command receipt](python-tests-final.json), [JUnit](python-tests-final.xml) |
| Final frontend tests | **35 passed**, zero failures; [receipt](frontend-tests-final-v2.json), [output](frontend-tests-final-v2.txt) |
| Frontend lint | Exit 0; [receipt](frontend-lint-final-v2.json) |
| Isolated build | Exit 0 into `scratch/twelve-month-graph-build-20261021-v2`; existing `dashboard/dist` preserved. Nonfatal bundle-size/output-location warnings retained |
| Syntax/whitespace/preservation | [Checks](checks.json), [preservation](preservation.json), [file inventory](FILES.json) |
| Actual localhost HTTP | Page HTML 200; graph API returns twelve slots; scoring remains 403; [runtime evidence](runtime_http.json) |
| Browser visual check | **Not verified**: browser automation twice failed before accessing the tab, including after reset, with `failed to write kernel assets: ... path ... (os error 3)` |

The skip is the existing Windows directory-symlink privilege test. Three tests that fit unrelated estimators were deliberately excluded. No unrestricted suite was run. New tests cover calendar/year boundaries, twelve ordered slots, null preservation, annual-baseline separation, compatible endpoint dispatch, six-month rejection, unchanged legacy dispatch and the intact demo guard. A synthetic chart-data fixture maps twelve existing numeric values to twelve ordered points; the current direct-M+12 validator **rejects** that fixture's unsupported intermediate values. It does not establish the availability of a twelve-month ML curve. Prior 104-test API and 32/33-test frontend checks are retained, not counted as extra unique coverage.

Actual default graph: observed origin **2026-05**, twelve target slots **2026-06 through 2027-05**, all ML values null because current weather and a historical observed target are unavailable. Annual baseline **6.553333 m** is present only at M+12. Explicit historical `origin_month=2024-01`: twelve slots February 2024–January 2025; the M+12 estimate is **7.571101 m**, annual baseline **6.836667 m**, and the first eleven ML slots remain null. The same frozen artifact, units and scope are used; `forecast_issued_at` remains null. No prospective forecast or shadow record was issued.

## Files and reproduction

Modified existing files:

- `dashboard/src/pages/Home.jsx`, `dashboard/src/App.jsx`: restore original layout/nav; retain only the optional research route.
- `dashboard/src/pages/DistrictDetail.jsx`, `dashboard/src/api.js`: change the existing graph's request/validation/data mapping; preserve legacy API client behavior and outer UI.
- `dashboard/tests/researchForecast.test.js`: update old prominence expectations to the requested original UI.
- `api/routes/research.py`, `api/app.py`: add/discover the isolated graph route; no legacy route modification.
- `README.md`, `api_spec.md`: accurately document the graph, explicit gaps and guarded-runtime limitations.

New source: `models/research_graph.py`, `dashboard/src/components/forecastGraph.js`, `tests/test_research_graph_api.py`, `tests/test_research_graph_demo.py`, `dashboard/tests/forecastGraph.test.js`. New report/helper/evidence files are confined to this directory; `demo_server.py` is the guarded runtime helper and `verify_phase.py` creates preservation/check receipts. Full paths and hashes are in [FILES.json](FILES.json).

Exact test/build argument arrays are saved in the linked JSON receipts. To reproduce, use the same targeted file list and fitting exclusions with **fresh** scratch/JUnit paths. Frontend commands executed were `npm.cmd --prefix dashboard test`, `npm.cmd --prefix dashboard run lint`, and `npm.cmd --prefix dashboard run build -- --outDir ../scratch/twelve-month-graph-build-20261021-v2`. Earlier build/test outputs remain under their original names.

The new guarded API launch is `.\venv\Scripts\python.exe -B reports/candidates/twelve_month_graph_only_20261021/demo_server.py` in PowerShell. The existing Vite server on 5181 retains `VITE_API_URL=http://127.0.0.1:5051`; no config file was changed. Do not start duplicate listeners or replace an unidentified process. The homepage remains `http://127.0.0.1:5181/`; the independently testable graph API is `/api/research/graph/TS-Adilabad?months=12`.

## Preservation and remaining blockers

The before inventory captured **1,009 pre-existing files** with a clean tracked working tree. Final verification permits only the nine intentional source/documentation edits; prior reports, private originals, datasets, trained artifacts/checkpoints, experiment results and the old demo helper remain unchanged. Six existing `dashboard/dist` files additionally match the earlier preserved receipt. The first layout-verifier attempt failed because Windows' default codec misread a UTF-8 source symbol; explicit UTF-8 reading corrected the verifier, without changing application code or data. Its failure is retained in `verification-attempt-01.json`. Database contents were not accessed or independently checksummed. No training, tuning, model promotion, new dependencies/downloads, database writes/migrations, rainfall-task modification, commit, push or deployment occurred.

**Acceptance boundary:** the original UI and twelve-position graph contract are implemented and tested. A populated twelve-month monthly ML curve cannot be supplied by the existing direct-M+12 artifact under the no-training/no-new-model constraints. It needs compatible, separately approved monthly-horizon artifacts/evidence; extending or interpolating a six-month model would be invalid. The annual baseline is historically stronger than this candidate, and no superiority, prospective skill or production readiness is claimed. The guarded scoring/district 403 and failed browser automation also prevent claiming a fully verified interactive district-chart demonstration.
