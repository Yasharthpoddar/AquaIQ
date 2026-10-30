# r2 frontend and serving readiness audit

Audit date: 2026-10-29. Scope: the current local working tree on `main`,
versioned States APIs, frontend contracts and rendering. The working tree
contains the existing uncommitted median implementation and deployment work;
it was preserved. This audit made no application-code, model, artifact,
database, publication, deployment or permission changes.

The findings below establish local software behavior. They do not establish
production readiness, a production target, current browser layout correctness
or forecasting accuracy. The production and operator gates belong to
[STATE_MEDIAN_PRODUCTION_RUNBOOK.md](STATE_MEDIAN_PRODUCTION_RUNBOOK.md).

## Current-run results

| Check | Status | Direct evidence |
|---|---|---|
| Full frontend tests | PASS | `npm test`: 184 passed, zero failed/skipped |
| Frontend lint | PASS | `npm run lint`: exit 0 |
| Frontend production build | PASS | `npm run build`: exit 0, 625 modules; bundle `index-DOk7-p6d.js` |
| Actual staged r2 contract/rendering | PASS | 36 responses, 34 forecasts, 408 month values, 36 table rows, zero errors |
| r2 method labels | PASS | 17 XGBoost, 17 persistence, two no-observation states; strict contract and SSR |
| Published r1 HTTP behavior | PASS | Existing isolated schema: registry/summary and 36 pinned state requests succeeded |
| Staged r2 remains unserved | PASS | Existing isolated schema: summary and all 36 explicit staged-UUID requests returned 503 with no forecast |
| Actual HTTP response contracts/rendering | PASS | 36 published-r1 and 36 unavailable-r2 responses passed the actual JavaScript validator and SSR |
| Model selector, invalid parameters and error handling | PASS | Actual HTTP probes plus 15 fresh focused API tests |
| Fresh desktop/mobile browser verification | UNVERIFIED | Computer Use stopped on a browser-URL policy check; no retry or alternate UI automation occurred |
| Real production frontend/API environment | UNVERIFIED | Local isolated schemas and generated build only; production target/configuration not established here |

All current-run evidence is under
`scratch/state_median_readiness_20261029/frontend/`. The full npm outputs are
`npm-test.log`, `npm-lint.log` and `npm-build.log`. API guard results are in
`api-model-guards.log`. The staged-rendering results are retained as
`staged_ssr_validation.json`; actual HTTP rendering results are in
`actual_http_contract_validation.json`. The combined HTTP probe evidence is
`scratch/state_median_readiness_20261029/db/http_publication.json`.

## One generation and vintage across the States page

The registry supplies canonical navigation membership and remains usable when
no release is published. Its vintage does not silently select a legacy
forecast. The summary establishes the forecast UUID and vintage in
[States.jsx:23](../dashboard/src/pages/States.jsx#L23). The map and comparison
table consume those summary rows, and selected cards consume the validated
detail through `medianStateDetails`.

The detail request includes both summary `as_of` and `generation_id`
([States.jsx:49](../dashboard/src/pages/States.jsx#L49),
[api.js:150](../dashboard/src/api.js#L150)). The JavaScript contract checks
the expected vintage and generation before accepting values
([stateMedianForecastContract.js:52](../dashboard/src/components/stateMedianForecastContract.js#L52)).
The render guard compares selected state, vintage and generation before using
any response ([States.jsx:58](../dashboard/src/pages/States.jsx#L58)); cancelled
effects prevent delayed responses from an earlier selection replacing it.
After summary refresh or publication selection, an older detail is hidden
while a new matching detail loads. Before summary completion, detail can load
independently; the map/table have no competing numerical summary at that point.

Pending HTTP requests are shared by the complete URL, then removed after
settlement ([api.js:10](../dashboard/src/api.js#L10)); there is no permanent
frontend cache of an active-release pointer. URLs for different UUIDs or
vintages are different cache keys. The backend also verifies the complete
stored generation rather than trusting a matching label alone.

## Published selection and failure behavior

The primary helpers use `/api/v2/states`, `/api/v2/states/summary` and
`/api/v2/predict/state/<id>`
([api.js:140](../dashboard/src/api.js#L140)). These routes call persisted
publication readers, never training or forecast-generation functions
([state_median.py:70](../api/routes/state_median.py#L70)).

Explicit UUID selection requires a corresponding publication event;
vintage selection joins publication events, and default selection reads the
active pointer
([state_median_release_storage.py:348](../models/state_median_release_storage.py#L348)).
Stored manifests, payloads and summary signatures are checked on reads
([state_median_release_storage.py:259](../models/state_median_release_storage.py#L259)).
Missing or corrupt reads produce an empty, explicit `model_unavailable`
response; unknown method and observation counts remain null rather than
claiming no observations
([state_median.py:47](../api/routes/state_median.py#L47),
[state_median.py:115](../api/routes/state_median.py#L115)).

The HTTP probes used ephemeral loopback servers and two existing **isolated
test schemas**, without migrating, staging, publishing or changing data:

* Published r1: `aquaiq_test_state_median_primary_20261029`, UUID
  `eaabeba7-a554-59a6-9110-726221e63cb2`, vintage `2026-10-29`.
  All 36 detail requests used that UUID and vintage and returned HTTP 200.
  `model=median_xgboost` returned the matching r1 summary; asking that r1
  generation for `model=median_tiered` returned HTTP 400.
* Staged r2: `aquaiq_test_state_median_coverage_20261029`, UUID
  `789ce3b5-3170-5866-9ce2-c0ec2f0b1b59`. Default and explicit staged summary
  requests returned HTTP 503. All 36 staged-UUID detail requests returned
  empty `model_unavailable` responses. Adding `model=median_xgboost` did not
  expose the tiered generation.
* Missing vintage returned HTTP 503; unsupported horizon returned 400 and an
  unknown state returned 404. An explicitly recorded corrupt-reader failure
  injection returned HTTP 503 with an empty forecast. It patched only a Python
  reader in the temporary test process, without corrupting stored records or
  artifact files.

These were 89 actual HTTP requests, all meeting their expected status. The
focused test `test_v2_serves_explicit_fallback_identity_without_changing_legacy_routes`
also confirms that a tiered payload cannot be returned for
`model=median_xgboost`; the shared guard is
[state_median.py:40](../api/routes/state_median.py#L40). Actual normal serving
of a **published r2** is deliberately not tested, because r2 publication is
outside the authorization boundary.

## Method and evidence presentation

The contract supports the exact known r1 identity and the r2 policy identity.
It rejects incompatible products/models, invalid calendar paths, mismatched
UUIDs/vintages, inconsistent coverage and fabricated unavailable paths.
Persistence additionally requires a genuine dated reference, a constant
twelve-month path, null fitted-model metadata, the prescribed reference
feature and an explicit reason. It rejects inherited XGBoost evaluation
([stateMedianForecastContract.js:77](../dashboard/src/components/stateMedianForecastContract.js#L77)).

The chart legend and tooltip use the actual method, including the explicit
`Persistence fallback` label. Historical qualified values, low-coverage points,
missing months and forecasts remain separate. The low-coverage series has an
opaque circle legend, zero connecting-line width and visible points; forecast
lines are dashed and the boundary marker is retained
([StateMedianForecast.jsx:26](../dashboard/src/components/StateMedianForecast.jsx#L26)).

The forecast panel gives the actual observation date and age, a stale-reference
warning, coverage and reason XGBoost was not used. Persistence has no reported
MAE/RMSE; XGBoost evidence retains its historical sample/horizon period and
frozen-reference qualification. Error units are metres, while depths are
`m bgl`
([StateMedianForecast.jsx:43](../dashboard/src/components/StateMedianForecast.jsx#L43)).
Selected cards and method counts use median fields
([States.jsx:70](../dashboard/src/pages/States.jsx#L70)); the comparison table
has an explicit method column, actual reference date/age and coverage
([StateMedianSummaryTable.jsx:7](../dashboard/src/components/StateMedianSummaryTable.jsx#L7)).
Map colors use the genuine historical reference rather than a relabeled
current-depth estimate, and tooltips disclose method, date/age and coverage
([stateMap.js:31](../dashboard/src/stateMap.js#L31),
[stateMap.js:50](../dashboard/src/stateMap.js#L50)).

The staged fixture is explicitly `preview_only=true`; its 34 forecasts and 408
values are evidence of local staged rendering, not current publication.
All 36 staged responses passed the current validator and SSR, with 17
XGBoost methods, 17 persistence methods and only LA/LD having no observations.

## Legacy isolation and remaining gates

There is no automatic legacy substitution. The default States page mounts one
controlled median chart
([States.jsx:82](../dashboard/src/pages/States.jsx#L82)). Selecting the legacy
page requires the explicit build flag `VITE_STATE_FORECAST_MODE=legacy`
([States.jsx:91](../dashboard/src/pages/States.jsx#L91)). Home continues to use
the existing legacy summary helper
([Home.jsx:79](../dashboard/src/pages/Home.jsx#L79)). The actual legacy summary
HTTP probe returned 200 and the district catalog returned all 725 registered
districts.

A fresh `git diff --exit-code` returned zero for Home, DistrictDetail,
DistrictForecastGraph, district prediction routes, district XGBoost/climate/
tier router modules, `config.yaml` and the tracked compact climate model/card.
The full frontend suite retains Home and district regression tests. This is
source/contract evidence, not a fresh browser review of those pages.

Fresh browser verification is **UNVERIFIED**. Computer Use returned:
"could not determine the current browser URL on Windows with enough confidence
to enforce policy" and explicitly stopped the turn's browser automation.
No browser retry or alternate UI automation followed. Earlier desktop/mobile
screenshots in the coverage and primary scratch directories are historical;
they are not evidence of a fresh readiness-run visual check. An operator must
complete desktop/mobile checks on the approved target build before activation.

No production endpoint, production release pointer or deployment was exercised.
Target-specific HTTPS, API origin, installed build, schema configuration,
credentials/permissions and actual published-r2 smoke tests remain operator
gates documented in the production runbook.
