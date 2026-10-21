# Current-date twelve-month experimental scenario

Implemented after the user's explicit approval of a separate unvalidated scenario using existing local history. The running app now offers **Next 12 months from today (experimental)** at `http://127.0.0.1:5182/district/TS-Adilabad?view=scenario#forecast-graph`. With scenario date **21 October 2026** (Asia/Kolkata), the twelve full calendar months are **November 2026–October 2027**. The calculation is dynamic, not a relabelled historical prediction.

## Method and evidence

This separate adapter reads the existing checksum-validated frozen Adilabad snapshot. It reuses the existing robust penalized seasonal/trend NumPy fit in memory; active ML estimators are neither fitted nor loaded. At least 24 source-marked observed months spanning 36 months are required. It excludes imputed, unknown-observation, current-month and later rows. The fit uses age weighting, robust residual weighting, a recent level adjustment and a damped trend, with annual sine/cosine terms when estimable. Existing method settings remain unchanged. No fitted parameters are saved.

The current example uses **121 observed-marked monthly means**, 2016-05-01–2026-05-01, covering all twelve calendar phases. The latest source-marked month is **2026-05**, depth **6.553333 m below ground**, with latest contributing well count **15.0**. The gap is **5 calendar months**. The scenario-month depth is **estimated** as 1.642629 m below ground. These are reported monthly source labels; actual acquisition, availability and well/datum continuity remain unverified.

Each future monthly value is calculated from the seasonal/trend function across the entire observation gap. Weather, rainfall, evapotranspiration, temperature and extraction effects are omitted. No future weather is asserted, no six-month model is extrapolated and no direct M+12 point is interpolated. A repeating seasonal pattern and damped continuation of historical trend are assumptions. There are no calibrated intervals or new accuracy/skill metrics.

**Illustrative scenario output, not observed measurements or validated forecasts:**

| Target month | Scenario depth (m below ground) |
|---|---:|
| 2026-11 | 2.27 |
| 2026-12 | 3.46 |
| 2027-01 | 4.89 |
| 2027-02 | 6.16 |
| 2027-03 | 6.93 |
| 2027-04 | 7.00 |
| 2027-05 | 6.34 |
| 2027-06 | 5.11 |
| 2027-07 | 3.66 |
| 2027-08 | 2.35 |
| 2027-09 | 1.55 |
| 2027-10 | 1.45 |

The precise example, method/source/configuration hashes and computation timestamp are in `local_scenario_example.json`. This is an isolated demonstration response, not a real shadow/validation ledger record. `forecast_issued_at` remains null, and output is labelled `assumption_based_scenario` / `unvalidated_scenario`.

## Application behavior

The graph stays in the existing district graph position. Its same red line/axes now show twelve actual scenario values when this mode is selected, with an accessible monthly table and prominent stale-observation/current-estimate distinctions. A mode control retains the original historical M+12 graph and origin selector. Default district links select the scenario; explicit `origin_month` links retain historical mode. There is no automatic fallback between modes. Home links to both examples. Only Adilabad has compatible frozen source support; other districts abstain rather than borrowing its data. The historical score, map, tier cards, six-month endpoints and direct M+12 contracts are unchanged.

New endpoint: `GET /api/research/scenario/<district_id>?months=12[&as_of=YYYY-MM-DD]`. Default date uses Asia/Kolkata. Future/invalid dates and unsupported/repeated query parameters are rejected before source access. Past dates produce current-vintage scenarios and do not establish point-in-time historical forecasts. Source failures block the scenario with public-safe errors. No database access occurs in this route.

## Verification

- **154 backend checks passed**, including new scenario date/leakage/observed-only/immutable-history/scope/error/real-source smoke checks and existing graph, direct research and horizon-contract tests. Guards reject DB access and active estimator fitting/loading in the scenario tests.
- **50 frontend checks passed**, including unchanged prior coverage plus scenario sequence, value, unit, district and date-age validation; separate route/mode behavior; disclosure rendering; all twelve table rows; and explicit retry without historical fallback.
- Lint, whitespace checks and an isolated build passed. The build retains its bundle-size advisory; it writes only `scratch/current-twelve-month-scenario-build-01`.
- The restarted read-only local API returned HTTP 200 and twelve finite values, with the expected period and five-month source gap. The real response passed the frontend validator. An unsupported district returned no values. Vite served the district page and transformed new component with HTTP 200. See `runtime_http.json`.
- Browser pixel/interaction verification remains blocked by the browser tool's kernel-assets/path error. Codex queued the direct scenario link. HTTP/component/server-render tests do not establish a visual browser check.

The first backend run had 89 passes and 65 fixture setup errors because its sandbox temporary directory could not be created. A fresh workspace `--basetemp` resolved all errors. The first frontend run had 49 passes and one invalid new synthetic leap-day fixture; correcting its source date/age and strengthening district/age checks produced 50 passes. Original failed receipts remain unchanged. Synthetic fixtures exist only in tests/isolated test directories and were not mixed with the real source or demonstration response.

## Files and preservation

Modified existing files in this phase:

- `README.md`
- `api/app.py`
- `api/routes/research.py`
- `api_spec.md`
- `dashboard/src/api.js`
- `dashboard/src/pages/DistrictDetail.jsx`
- `dashboard/src/pages/Home.jsx`

New source/documentation/test files:

- `models/experimental_scenario.py`
- `tests/test_experimental_scenario.py`
- `dashboard/src/components/ExperimentalScenario.jsx`
- `dashboard/src/components/experimentalScenarioContract.js`
- `dashboard/src/components/DistrictForecastGraph.jsx`
- `dashboard/tests/experimentalScenario.test.js`
- `docs/EXPERIMENTAL_SCENARIO.md`

Of **1058** pre-existing inventoried files, **1051** remain byte-identical. The only **7** changes are the seven intended existing source/documentation files above. Data, existing model code/checkpoints, research configuration and prior reports remain byte-identical. Earlier uncommitted changes remain present. HEAD is unchanged at `3a4936b6950b76dc7413ccfbabace30b67e5891e` and the index is empty. No source download, DB write/migration, active ML training/tuning/promotion, model artifact replacement, real shadow issuance, commit or push occurred. The approved in-memory seasonal scenario fit is the sole new fitting operation. Database contents were not independently checksummed.

Only the verified local read-only API5052 process was restarted using a new helper under `scratch/current-scenario-server-20261021-01`; the earlier helper and guarded5051/5181 demo remain untouched. The helper retains read-only DB connections and active estimator fit guards. Vite5182 was retained with its existing configuration.

## Reproduce and acceptance boundary

```powershell
# Choose fresh absent test/build outputs; do not overwrite completed receipts.
.\venv\Scripts\python.exe -B -m pytest tests/test_experimental_scenario.py tests/test_research_graph_api.py tests/test_research_forecast_api.py tests/test_research_horizon.py -q --basetemp=scratch/pytest-scenario-NEW
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../scratch/scenario-build-NEW
# Running local API; read-only scenario calculation:
Invoke-RestMethod 'http://127.0.0.1:5052/api/research/scenario/TS-Adilabad?months=12'
```

Demonstrated: twelve future calendar estimates from an explicitly approved, deterministic, local seasonal/trend scenario with disclosed evidence age and assumptions, plus preserved historical product contracts. **Unverified:** actual future accuracy, superiority to persistence/seasonal naive, current groundwater state, input availability, well/datum continuity, nationwide generalization, and production readiness. HGB remains abstained. A real prospective campaign still needs its previously documented approvals, provenance and new observed labels; this demonstration does not start it.
