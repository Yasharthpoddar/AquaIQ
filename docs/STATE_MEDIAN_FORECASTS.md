# State median XGBoost

The latest [coverage fix](STATE_MEDIAN_COVERAGE.md) defines a separate versioned
policy: unchanged eligible XGBoost, explicit persistence for limited/stale
genuine history, and no-observations status only when the source is genuinely
empty. Its actual r2 release is staged locally, not published.

The main States page now selects the median model through the versioned
`/api/v2/states` APIs. Cards, map, comparison table and the single primary chart
share a pinned median publication. Home and district forecasting retain their
existing contracts. Selection as the primary product does not establish
validated forecast skill: the model remains experimental with limited
historical evidence.

The current artifact, publication workflow, deployment prerequisites and exact
rollback commands are in [STATE_MEDIAN_RELEASE.md](STATE_MEDIAN_RELEASE.md).
The following sections preserve the original experimental integration and its
original-source comparison as a **historical record**. Their old default page,
API and frozen-artifact statements do not describe the new v2 release workflow.

## Repository audit and isolation

The 2026-10-29 local audit inspected `models/state_forecast.py`,
`api/routes/state.py`, `docs/NATIONWIDE_FORECASTS.md`, `models/xgboost_model.py`,
`models/climate_forecast_12m.py`, `models/tiered_forecast.py`,
`models/district_registry.py`, `models/state_mapping.py`,
`models/forecast_storage.py`, `scripts/precompute_forecasts.py`,
`scripts/evaluate_state_xgboost.py`, `scripts/validate_tiered_forecasts.py`,
`data_ingestion/ingest_cgwb.py`, the updated observation ingestion/provenance
utilities, `preprocessing/pipeline.py`, database migrations and connection
helpers, `api/contracts.py`, state frontend charts/contracts/pages, and their
Python and Node tests. The verified feature CSV, manifest and frozen district
XGBoost bundle were actually loaded; PostgreSQL and frontend dependencies were
available. The working tree was initially clean.

The local original feature generation has 215,325 rows for 725 registered
districts and 36 states/UTs, January 2002–September 2026, including 36,890
genuine district-month values across 652 districts. At 50% coverage plus two
contributors (one for singleton states), 17 states have at least 36 qualified
months. Data are strongly seasonal and sparse after 2021. These counts refer
to this verified local snapshot, not the separate final-release snapshot.

Groundwater is absolute depth in **metres below ground level (`m_bgl`)**.
Larger values indicate a deeper water table. Dates label calendar months and
do not establish publication/acquisition dates. Missing values remain null.

The smallest safe change adds independent median data/model/evaluation/storage
modules, separate training/generation commands, an additive API query mode,
and an independent state-only dashboard panel. The production precompute
workflow averages all registered tiered district predictions; the legacy
`state_forecast.py` helper averages a smaller eligible XGBoost panel. The
comparison uses the actual production tiered mean. Neither is replaced.

## Observations, quality and coverage

`build_state_history` reuses the manifest/hash-verified physical-unit feature
export, canonical district registry and existing observed-mask rules. Both
observed and imputed flags must unambiguously identify a genuine observation;
conflicting/unknown flags, missing/nonfinite depths and negative depths are
excluded. Zero is permitted only when explicitly source-marked as observed.
Unregistered districts and conflicting state mappings fail closed.

Ingestion has already averaged valid well readings into one district-month
mean. The verified export rejects duplicate district/month keys. The candidate
preserves those established means. For explicitly supplied repeated observation
fixtures, exact district/date/depth/provenance duplicates are removed before
date normalization and valid values are averaged per district-month. The
state value is then the **median across these district means**, giving each
contributing district one vote regardless of sampling frequency. No district
forecast, imputed depth, regional donor or other-state value enters a target.

Every state has a full month-start calendar over the source range. Missing
months have null depth, zero contributors and quality `missing`. Low-coverage
medians are retained with quality `low_coverage`, but cannot be targets or
groundwater-history features. Qualified medians have quality
`coverage_qualified` and `training_eligible=true`.

Coverage is contributing canonical districts / all registered districts in
the state. The configurable `--min-coverage` defaults to 0.5; at least two
contributors are also required, except for singleton states. Each row stores
state/date/depth, contributor and registered counts, ratio/percentage,
observation count and quality. In the production feature export, observation
count means genuine district-month aggregates, **not wells or raw readings**;
raw well counts and stable well identifiers are unavailable. The exported
`historical_state_medians.csv` retains all months for auditing. Dashboard/API
history is limited to the last 60 calendar months.

The median describes the typical district in the observed sample. It does
not directly measure groundwater volume, total groundwater availability or
the most severely depleted district. Changing district/well composition can
change the median without a corresponding aquifer-wide change.

## Independent models and temporal separation

`models/state_median_forecast.py` fits one XGBoost regressor per eligible state,
with direct horizons 1–12 as a feature. It does not recursively turn predictions
into historical observations. Features include the last qualified depth and
age; exact calendar lags 1/2/3/6/12; rolling 3/6/12-month median, mean and
standard deviation; recent change; origin and target seasonal sine/cosine;
horizon; previous-month coverage; and prior-month state climate means.

All candidate features stop **strictly before the origin calendar month**,
including month-end requests. Thus a forecast made partway through October
uses September or earlier inputs and predicts November–October. This fixed,
conservative delay makes training, backtesting and serving use the same
availability convention. Rolling windows ignore missing/low-coverage values;
calendar lags stay missing. No backward filling or cross-state imputation is
performed. XGBoost handles missing feature values directly; no scaler or
global imputer is fitted.

Rainfall (`mm/month`), temperature (`degC`) and potential evapotranspiration
(`mm/month`) are equal-district monthly means of the existing historical
physical-unit feature inputs, subject to the same coverage threshold. These
inputs may include the source pipeline's bounded causal fills and are not
claimed to be independently observed state weather. Only the previous month
is supplied. The candidate uses **no forecast-period weather or historical
climatology**. Reanalysis publication timing remains an unverified retrospective
availability assumption. Missing climate stays missing.

Eligibility requires 36 qualified observed months spanning at least 60 calendar
months, at least 24 distinct supervised training target months after a
12-observation warm-up, and chronological development validation with at least
three target months. Forecasts additionally need a qualified pre-origin
reference no more than 12 months old. Unsupported states return
`insufficient_data` with no graph estimates. Missing/mismatched assets return
`model_unavailable`; there is no substitute model.

Fixed parameters: 120 trees, depth 2, learning rate 0.04, squared error,
full sampling, seed 42, histogram tree method and one worker. There is no
hyperparameter tuning on validation or test outcomes. Defaults fit development
labels through December 2016, diagnose later origins/targets during 2017–2019,
then refit through December 2019 for the frozen historical comparison and
candidate forecasts. The model card records actual month-label cutoffs,
features, parameters, runtime version, hashes and per-state eligibility.
Development validation metrics are marked diagnostic and never displayed as
forecast accuracy. Target rows are never randomly split.

## Comparison and promotion

`backtest_state_median` loads frozen candidate and district artifacts, never
retraining a district. Each origin restricts groundwater, climate and donor
inputs to available history. Baseline point predictions call the unchanged
`tiered_forecast.forecast_district` for every registered district in each tested
state and reproduce the production equal mean. Uncertainty calibration is not
needed to compare point forecasts and is not rewritten.

Both methods are scored against the same qualified held-out **state median**,
along with last-qualified-median persistence. Origins have a twelve-month
embargo after both models' final training labels. Default origins include
December 2020 and January/July 2021–2025. December 2020 is evaluated at month
end, exactly twelve months after the frozen district label cutoff. It was
added after inspecting target availability, before examining prediction errors,
to intersect the January 2021 observations. This is a limited retrospective
diagnostic, not an independently selected final test.

Reports retain all attempted state/origin/horizon cases, eligibility and failure
reasons. They show all available cases and identical paired cases separately,
MAE/RMSE, bias, directional performance against the last qualified median,
state and horizon results, unique state-month observations, target coverage,
and absolute/relative error changes. Repeated targets across origins are not
independent observations. Candidate-only improvements cannot be inferred from
panels with different eligible states.

The candidate remains **experimental** regardless of an isolated historical
error reduction. Sparse high-coverage targets, uneven phases, changing panels,
unknown publication times and stale references prevent a claim of validated
nationwide monthly or prospective skill. A comparison run and its actual
numbers are recorded below.

### Actual local comparison, 2026-10-29

The frozen run trained 17 state models and marked 19 states insufficient. It
evaluated 11 origins and 4,752 attempted state/origin/horizon cases. Only 79
cases across 28 states met target coverage, representing 52 distinct observed
state-months. The production baseline returned all 79; the candidate returned
17. Its other 62 cases comprised 28 insufficient-history cases and 34 stale
references. These counts include repeated January 2026 targets at different
origins and must not be treated as 79 independent observations.

The **identical paired panel** consists of 17 states' January 2021 observations,
all M+1 from the December 2020 origin:

| Method | Cases/states | MAE (m) | RMSE (m) | Bias (m) | Direction correct |
|---|---:|---:|---:|---:|---:|
| Production tiered district mean | 17 / 17 | 1.567226 | 2.336003 | +1.314438 | 15 / 17 |
| State median XGBoost | 17 / 17 | 0.545920 | 0.703206 | +0.399377 | 16 / 17 |
| Last-qualified-median persistence | 17 / 17 | 1.067572 | 1.192485 | -0.579467 | 0 / 17 |

Candidate minus production error was -1.021306 m MAE (-65.17%) and -1.632797 m
RMSE (-69.90%) on those cases. Candidate minus persistence was -0.521652 m MAE
(-48.86%) and -0.489279 m RMSE (-41.03%). Mean target district coverage was
85.24%; mean historical-reference coverage was 83.71%, identical for the
paired comparison. Persistence predicts no change, hence its zero directional
match when actual change is nonzero; this is not a calibrated skill score.

On its larger **unmatched** 79-case panel, production MAE/RMSE was
2.097933 / 3.072819 m. Those numbers cannot be compared directly with the
candidate's 17-case errors. No paired candidate evidence exists for M+2–M+12.
The candidate was worse than production in JH, KA, MH and OD on the single
observed January round; its largest state absolute error was KA (1.6303 m).

| State | Production absolute error (m) | Candidate absolute error (m) |
|---|---:|---:|
| AP | 1.7488 | 0.0143 |
| BR | 0.4051 | 0.3373 |
| CG | 0.0789 | 0.0421 |
| GJ | 4.8606 | 1.1385 |
| HP | 1.4654 | 0.8591 |
| HR | 3.8365 | 0.4747 |
| JH | 0.6230 | 0.7820 |
| KA | 0.9672 | 1.6303 |
| KL | 0.2381 | 0.1152 |
| MH | 0.2145 | 0.7632 |
| MP | 0.9943 | 0.4271 |
| OD | 0.0816 | 0.2283 |
| PB | 0.6321 | 0.1604 |
| RJ | 6.1912 | 0.9371 |
| TN | 2.3553 | 0.9067 |
| TR | 0.5031 | 0.0111 |
| UP | 1.4472 | 0.4531 |

Local evidence is in
`scratch/state_median_20261029/comparison_v1/{evaluation.json,cases.csv,comparison.md}`.
An independent December 2020 replay exactly reproduced all 432 attempted rows
and all origin metrics; evidence is in
`comparison_repro_v1/reproducibility.json` under the same run directory. The
source-matched candidate card is `models_v3/model_card.json` in that directory.
All generated artifacts/reports stay local in ignored scratch storage.

The evaluated 2026-10-29 candidate generation contains 17 × 12 predictions
for November 2026–October 2027 and 19 explained unavailable states. It was
saved only in `aquaiq_test_state_median_20261029`, generation
`40414ae8-28fe-5e5d-9879-ab842969c42f`; production publication was preserved.
Current forecasts deliberately use the frozen December 2019 model to retain
artifact identity with the comparison. A more recent refit needs its own
versioned artifact and evaluation; no current skill is inferred from this
old, single-round diagnostic. **Recommendation: do not promote.**

## API, dashboard and storage

`GET /api/predict/state/TN?model=median_xgboost&horizon=12` selects the latest
persisted candidate vintage no later than today. Explicit
`as_of=2026-10-29` selects exactly that candidate date. Omitting `model` or using
`model=current` retains the existing contract and production methodology.
Unknown modes or horizons return 400. No request trains or runs inference.

Candidate identity is product `state_median_groundwater_12m_forecast`, model
`state_median_xgboost`, version `1.0-state-median-xgboost`. Additive fields expose
history, quality/coverage, twelve forecast values, model hash/cutoff,
generation time, source identity, independent held-out error period and
experimental/unavailable status. Unsupported data returns 200
`insufficient_data`; absent assets/vintages return 503 `model_unavailable`.

The existing States page adds an independent experimental panel showing the
candidate's own latest vintage. It separates qualified history, grey
low-coverage observations, missing gaps and future predictions, marks the
forecast boundary, and shows coverage, contributing counts, model version,
held-out MAE/RMSE and evaluation dates separately. No calibrated accuracy
percentage is invented. District pages and production state cards/maps remain
unchanged.

Migration 006 adds only `state_median_generations` and
`state_median_forecast_records` to the existing PostgreSQL system. Candidate
snapshots are complete, immutable, transactionally validated 36-state JSONB
generations, with independent vintage selection; existing district and
production state tables are never written. The new CLI only persists when
an explicit `--test-schema aquaiq_test_*` is supplied, creating candidate
tables in that namespace. No production migration/publication was performed.

## Reproduction

Use the installed environment (or `requirements.txt`) and verified original
feature snapshot with its matching frozen district bundle. Every output path
below must be new. No download or credential assumption is needed for training,
evaluation or JSON export; persistence requires the existing local PostgreSQL
configuration. Commands are PowerShell:

```powershell
.\venv\Scripts\python.exe -B -m scripts.state_median_forecasts train --artifacts scratch/state_median_run/models --train-cutoff 2019-12-31 --validation-start 2017-01-01 --min-coverage 0.5
.\venv\Scripts\python.exe -B -m scripts.backtest_state_median --artifacts scratch/state_median_run/models --output scratch/state_median_run/backtest
.\venv\Scripts\python.exe -B -m scripts.state_median_forecasts generate --artifacts scratch/state_median_run/models --as-of 2026-10-29 --evaluation scratch/state_median_run/backtest/evaluation.json --output scratch/state_median_run/generation.json --test-schema aquaiq_test_state_median_run
$env:AQUAIQ_FORECAST_SCHEMA='aquaiq_test_state_median_run'
.\venv\Scripts\python.exe -B -m api.app
```

The private candidate namespace alone does not contain production forecasts.
To inspect the whole existing dashboard there, first create its production
outputs using the unchanged documented nationwide replay in that same test
namespace. The default production schema is never silently used as a fallback.
Alternatively test the candidate endpoint directly. The API can read a
persisted candidate even if its training assets later become unavailable.

Omit `--test-schema` for JSON export only. `--processed-dir` accepts an explicit
matching verified snapshot on each command. Model directories are immutable;
changed implementations or source/registry/coverage identities require a fresh
candidate model and comparison. Evaluation attachments must match the exact
model-card hash and may not extend beyond the requested forecast vintage.

```powershell
.\venv\Scripts\python.exe -B -m pytest tests/test_state_median_forecast.py tests/test_state_median_evaluation.py tests/test_state_median_storage.py tests/test_state_median_api.py -q --integration
npm test --prefix dashboard
npm run lint --prefix dashboard
npm run build --prefix dashboard
```

## Changed files and executed verification

Only these state-specific/additive files changed:

- Models: `models/state_median_forecast.py`,
  `models/state_median_evaluation.py`, `models/state_median_storage.py`.
- Commands: `scripts/state_median_forecasts.py`,
  `scripts/backtest_state_median.py`.
- API/database: `api/routes/state.py`,
  `db/migrations/006_state_median_forecasts.sql`.
- Frontend: `dashboard/src/api.js`, `dashboard/src/pages/States.jsx`,
  `dashboard/src/pages/States.css`,
  `dashboard/src/components/StateMedianForecast.jsx`,
  `dashboard/src/components/stateMedianForecastContract.js`.
- Tests: `tests/test_state_median_forecast.py`,
  `tests/test_state_median_evaluation.py`, `tests/test_state_median_storage.py`,
  `tests/test_state_median_api.py`,
  `dashboard/tests/stateMedianForecast.test.js`.
- Documentation: this guide and `docs/NATIONWIDE_FORECASTS.md`.

Executed locally:

- Full Python suite: **1,812 passed, 40 skipped**; existing scientific library
  warnings remain. Three additional core tests added after full-suite
  collection passed in the focused run below.
- Final focused candidate suite with PostgreSQL integration: **57 passed**,
  covering aggregation, gaps, quality/mapping, feature leakage, temporal
  separation, insufficient/stale states, real XGBoost fitting/reload,
  twelve-month paths, metadata, metrics/replay, API compatibility and storage.
- A broader DB-enabled existing regression selection returned **132 passed,
  1 failed**. The failure in
  `test_forecast_storage.py::test_api_serves_persisted_forecasts_and_prevents_inference`
  was reproduced with the original HEAD state route loaded in memory, proving
  it predates this change. Local `.env` selects
  `aquaiq_test_final_release_20261026`, which overrides the test fixture's
  private search path and has no requested October 25 vintage. With the
  namespace override cleared in the diagnostic process and its already
  verified real 725-district fixture reused, the same test **passed**, including
  state/summary/district API reads and the inference prohibition. Neither
  `.env` nor production storage logic was changed.
- Frontend: **171 passed**, plus successful lint and production build.
- Actual evaluated PostgreSQL generation: all **36** API reads succeeded;
  their actual JSON passed the real JavaScript contract and server rendering,
  including **2,160 history rows and 204 forecast rows**. Evidence:
  `scratch/state_median_20261029/api_validation.json` and
  `frontend_api_evaluated.json` in that directory.
- Independent real-data replay: **432 attempted rows and all December 2020
  metrics exactly reproduced**.
- District method, artifact, configuration, feature CSV and dashboard files
  have no diff. The verified district model SHA-256 remains
  `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`.
  The public production generation count and identity were unchanged before
  and after persistence. No commit, push, merge or deployment was performed.

Browser screenshots were not generated: the local dashboard environment had
no Playwright/Chromium installation. Chart contracts, chart construction,
actual-payload rendering and build were executed; browser visual inspection
is not claimed.
