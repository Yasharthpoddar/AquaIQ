# All-district experimental twelve-month completion

The default district graph now supports **all 725 canonical IDs**, with twelve next-calendar-month seasonal/trend estimates where enough own-district history exists. The running Kaithal view is `http://127.0.0.1:5182/district/HR-Kaithal?view=scenario#forecast-graph`. On **21 October 2026**, the period is **November 2026–October 2027**. This is an explicitly approved **unvalidated experimental scenario**, not a validated national forecasting model or a twelve-month risk score.

## Coverage verified across every district

| Result | Districts |
|---|---:|
| Twelve finite monthly scenario estimates | 548 |
| Insufficient observed history | 104 |
| No source-marked observed history | 73 |
| Total IDs checked | 725 |

All 548 available paths contain exactly twelve ordered calendar points (6,576 estimates total), with finite nonnegative depth values. The other 177 return no curve and an explicit reason; no missing observations were manufactured or borrowed. Unknown IDs also abstain.

**Kaithal, Haryana:** 77 observed-marked monthly values, latest January 2026, with a nine-calendar-month observation gap. Its live API returns twelve values, and the live path is semantically identical to the independently executed functional verification. Gandhinagar also returns its own path. Adilabad retains its frozen May 2026 source, its 121 used observations and its exact previous numerical scenario. The historical direct ML research artifact remains Adilabad-only.

Available paths' latest source months are **January 2026 in 538 districts**, **January 2021 in nine**, and **May 2026 for Adilabad**. The nine oldest available paths therefore estimate a 69-month gap. National observations are often seasonal: 297 eligible paths have only four observed calendar phases, 115 have five; unsampled phases rely on the assumed seasonal function. The UI discloses observation age, fit counts and inferred phases. A recent 120-month history is used only where the existing method has enough observations; otherwise its unchanged full-history branch applies. Numerical availability does not establish scientific reliability.

See `scope_verification/district_coverage.csv` for all district outcomes and `scope_verification/summary.json` for counts. Five clearly labelled scenario examples are retained separately from source data and production outputs. No prospective ledger was created and no accuracy evaluation was performed.

## Implementation and source safeguards

A new file-only source adapter reads the existing canonical feature export, manifest and district crosswalk through a separate versioned lock, `research/experimental_scenario_sources.json`. It pins the actual source bytes, generation, declared units and 725 canonical identities. It validates unique district/month-start keys, strict observed/imputed flags, groundwater aliases, finite nonnegative observed values and generation/date metadata. Every request verifies all pinned byte hashes before using cached parsing; revised sources fail closed until separately reviewed/versioned. Each returned frame is a private slice for the requested exact canonical ID. Canonical self-rows supply display names where available; recorded display spelling variants do not change identities. No guessed aliases, database fallback, zone borrowing or cross-district substitution is used.

The method is the already approved in-memory robust damped seasonal/trend calculation, using observed/non-imputed history strictly before the scenario month. It does not fit/load active ML, extend six-month model horizons, interpolate a historical M+12 endpoint, download data or save fitted parameters. Adilabad's separately validated frozen source has explicit precedence; a failure there does not silently select the national source.

National export units follow the repository's `m_bgl` convention. Actual per-well datum, acquisition/publication/availability times and stable panel continuity remain unverified. Missing national well counts, panel IDs and timestamps remain null. Source-specific unit qualifications are displayed. Current depth is estimated across the observation gap; weather, temperature, evapotranspiration, pumping and intervention effects are omitted. No calibrated uncertainty intervals or accuracy claims are supplied.

The original map, list, summary cards, score calculation and navigation remain. District graph mode defaults to this separate twelve-month scenario; explicit historical origins retain the original direct M+12 view and gaps. The existing historical risk score and six-month API contracts are preserved; they are not relabelled as twelve-month trained products. README/API/methodology documentation now explains these distinctions, including correcting an older description of the default graph as six months. HGB remains abstained.

## Checks and runtime

- **175 backend checks passed**, covering new source integrity/cache isolation, district isolation, observed-only and calendar filtering, malformed units/flags/schema, missing history, Kaithal and unchanged Adilabad values, plus existing research/graph/horizon contracts. Tests prohibit DB access and active ML fitting/loading for the new scenario paths.
- **57 frontend checks passed**; lint, whitespace checks and isolated build passed. Coverage includes arbitrary districts, twelve chart/table values, zero depths, district mismatch, unavailable reasons, source qualifications and sparse calendar phases. Existing UI tests remain covered. Build output is confined to `scratch/all-district-twelve-month-build-01`; its bundle-size advisory remains.
- **725 actual source-backed functional scenario calls completed** under DB/active-estimator guards, with zero shape/value failures. This checks software behavior, not prediction accuracy. `verify_scope.py` creates new candidate evidence only and refuses existing output directories.
- Representative live API calls returned HTTP 200: Kaithal/Gandhinagar/Adilabad have twelve points; Nicobars and an unknown ID have explicit empty results. The real response examples all passed the frontend validator. The page and transformed component return HTTP 200. See `runtime_http.json` and `frontend-live-contract-02.txt`.
- An initial live-versus-batch comparison used JSON string equality, which differed only because Flask sorts object keys. The corrected semantic comparison shows exact equality and **0.0 m maximum prediction difference**; both source/history hashes match. See `live_batch_comparison.json`. No calculation was altered to obtain agreement.
- Browser pixel/interaction verification remains blocked before tab access by the browser tool's kernel-assets/path error. Codex queued the Kaithal link; HTTP/component tests do not replace a browser visual check.

Only the verified local API5052 listener was restarted, using a new read-only helper in `scratch/all-district-scenario-server-20261021-01`. Existing helpers, the separate guarded5051/5181 demo and Vite5182 were retained. DB connections remain read-only and active-estimator fit guards remain enabled.

## Files and preservation

Modified pre-existing source/documentation/test files in this phase:

- `README.md`
- `api_spec.md`
- `dashboard/src/components/ExperimentalScenario.jsx`
- `dashboard/src/components/experimentalScenarioContract.js`
- `dashboard/src/pages/Home.jsx`
- `dashboard/tests/experimentalScenario.test.js`
- `docs/EXPERIMENTAL_SCENARIO.md`
- `models/experimental_scenario.py`
- `tests/test_experimental_scenario.py`

New source/configuration/test files:

- `models/scenario_sources.py`
- `tests/test_scenario_sources.py`
- `research/experimental_scenario_sources.json`

The new report directory contains the before inventory, checks, functional-verification script/results, live evidence and preservation receipts. Of **1081** pre-existing inventoried files, **1072** remain byte-identical; only the **9** intended existing source/documentation/test files changed. Dataset, active checkpoint, prior-report, previous research-configuration and existing API byte hashes are unchanged. Prior uncommitted changes remain present; HEAD is `3a4936b6950b76dc7413ccfbabace30b67e5891e` and the index remains empty. No active ML training/tuning/promotion, dataset modification, DB write/migration, source download, real shadow issuance, commit or push occurred. Only approved transient seasonal fits were calculated. Database contents were not independently checksummed.

## Reproduce safely

```powershell
# Use fresh absent output directories rather than overwriting these receipts.
.\venv\Scripts\python.exe -B -m pytest tests/test_scenario_sources.py tests/test_experimental_scenario.py tests/test_research_graph_api.py tests/test_research_forecast_api.py tests/test_research_horizon.py -q --basetemp=scratch/pytest-all-district-NEW
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../scratch/all-district-build-NEW
.\venv\Scripts\python.exe -B reports/candidates/all_district_twelve_month_scenario_20261021/verify_scope.py reports/candidates/all_district_twelve_month_scenario_20261021/scope-verification-NEW
Invoke-RestMethod 'http://127.0.0.1:5052/api/research/scenario/HR-Kaithal?months=12'
```

Submission boundary: the twelve-month experimental software flow is implemented across the registry, with tested eligible and unavailable states. **177 districts cannot receive an own-data curve without additional usable observations.** Accuracy, present groundwater conditions, baseline superiority, acquisition/availability provenance, stable well/datum continuity, nationwide generalization and production readiness remain unverified. A real prospective campaign still requires its separate prerequisites and approvals.
