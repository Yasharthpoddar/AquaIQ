# State median coverage policy — local r2 release

The coverage fix is generated and independently validated locally. Every state
with genuine source observations receives twelve forecast values: 17 retain
their existing XGBoost predictions and 17 use explicitly named persistence.
Ladakh and Lakshadweep have no usable observations and remain unavailable.
This is **34 forecast states, not 36**.

The actual r2 release was **staged only, never published or deployed**. Normal
serving APIs continue to read published generations and reject the staged r2
UUID with HTTP 503. The clearly labelled local browser preview uses a verified
staged-response fixture; it does not change the production API or active
pointer. Activation remains outside this task's explicit safety boundary.

## Root cause and the nineteen prior exclusions

The primary pipeline conflated eligibility to train a state-specific XGBoost
model with eligibility to provide any state forecast. Historical medians below
50% district coverage (or fewer than two reporting districts, except singleton
states) correctly remained ineligible for learned-model targets, but the
forecast path discarded them as possible reference observations too.

The unchanged XGBoost gates are: at least 36 qualified months spanning 60
calendar months; twelve prior observations before supervised examples; 24
distinct supervised training targets; at least 24 development targets before
the January 2017 validation boundary; at least three chronological validation
targets; and a qualified pre-origin reference no more than twelve months old.
Seven excluded states pass the overall 36/60 history gates but fail the
pre-validation development count. Ten other data-bearing states fail qualified
history requirements. Two have no genuine observations at all.

Counts below are **genuine district-month aggregates, not wells**. Values were
read independently from the verified V3 source and checked against the generated
release. A dash means a later gate was not reached; it is not an invented zero.

| State | Genuine district-months | Qualified months | Exact first rejected condition(s) |
|---|---:|---:|---|
| AN — Andaman and Nicobar Islands | 32 | 16 | 16 qualified months < 36 |
| AR — Arunachal Pradesh | 339 | 0 | 0 qualified months < 36; 0 calendar-month span < 60 |
| AS — Assam | 1146 | 40 | 2 pre-validation development targets < 24 |
| CH — Chandigarh | 46 | 46 | 4 pre-validation development targets < 24 |
| DD — Dadra and Nagar Haveli and Daman and Diu | 96 | 32 | 32 qualified months < 36 |
| DL — Delhi | 42 | 42 | 4 pre-validation development targets < 24 |
| GA — Goa | 90 | 45 | 4 pre-validation development targets < 24 |
| JK — Jammu and Kashmir | 427 | 3 | 3 qualified months < 36; 22 calendar-month span < 60 |
| LA — Ladakh | 0 | 0 | No valid genuine observation |
| LD — Lakshadweep | 0 | 0 | No valid genuine observation |
| ML — Meghalaya | 478 | 37 | 6 pre-validation development targets < 24 |
| MN — Manipur | 14 | 0 | 0 qualified months < 36; 0 calendar-month span < 60 |
| MZ — Mizoram | 5 | 0 | 0 qualified months < 36; 0 calendar-month span < 60 |
| NL — Nagaland | 136 | 3 | 3 qualified months < 36; 37 calendar-month span < 60 |
| PY — Puducherry | 111 | 44 | 3 pre-validation development targets < 24 |
| SK — Sikkim | 1 | 0 | 0 qualified months < 36; 0 calendar-month span < 60 |
| TS — Telangana | 1055 | 12 | 12 qualified months < 36 |
| UK — Uttarakhand | 221 | 7 | 7 qualified months < 36; 37 calendar-month span < 60 |
| WB — West Bengal | 1382 | 42 | 4 pre-validation development targets < 24 |

The detailed CSV/JSON additionally retain the exact rejected gate identifiers,
qualified spans, supervised target counts and validation counts:
`scratch/state_median_coverage_20261029/audit_after/coverage.{csv,json}`.

## Policy and scientific interpretation

- **Tier A, `state_median_xgboost`:** all previous training/coverage/validation/
  recency safeguards and model bytes remain unchanged. The 204 existing monthly
  predictions for these 17 states exactly match r1.
- **Tier B, `persistence_fallback`:** whenever genuine observations exist but
  XGBoost is ineligible, repeat the latest genuine state-month median for all
  twelve future months. One observation is sufficient. Multiple observations
  use the same deterministic rule; no fitted trend, future climate, other-state
  donor or legacy state prediction is substituted.
- **Tier C, `no_observations`:** only zero genuinely usable observations support
  this unavailable status. Depth, reference date and age remain null; no
  forecast or score is invented. Asset/source failures are separate errors and
  never trigger persistence to hide a corrupt or missing model.

The state median is still the median of reporting **district-month means**.
Invalid/nonfinite/negative/missing values, imputation and conflicting observation
flags are excluded by the existing quality pipeline. Genuine zero depth can be
valid; missing values are never converted to zero. Low-coverage observations can
support persistence while remaining excluded from XGBoost training targets.
No district-month is weighted by its number of samples. Source dates remain
calendar month labels, not verified publication/acquisition timestamps.

Every r2 forecast exposes its method, exact reference row, genuine observation
counts, actual latest observation date, calendar-month age, coverage and source
identity. The project's existing nominal reporting interval is three months;
older references are explicitly stale. AN's last median is 42 months old; DD
and SK are 21 months old at this vintage. No age limit is imposed on persistence.
References older than the chart window are retained with all intervening null
months. Future readings cannot enter an earlier snapshot.

Fallbacks have null model-weight hash/training cutoff and explicit
`not_evaluated_for_fallback` errors: MAE/RMSE remain unavailable. The historical
XGBoost comparison does not describe fallback accuracy. A constant reference
does not establish stable present groundwater, calibrated confidence, total
availability, groundwater volume or the most depleted district. District/well
composition changes and sparse/stale observations remain material limitations.

## Complete independently validated state coverage

| State | Genuine district-months | Latest genuine observation | Forecast method | Horizon | Final status |
|---|---:|---|---|---:|---|
| AN — Andaman and Nicobar Islands | 32 | 2023-04-01 | `persistence_fallback` | 12 | forecast |
| AP — Andhra Pradesh | 1110 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| AR — Arunachal Pradesh | 339 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| AS — Assam | 1146 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| BR — Bihar | 2905 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| CG — Chhattisgarh | 1410 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| CH — Chandigarh | 46 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| DD — Dadra and Nagar Haveli and Daman and Diu | 96 | 2025-01-01 | `persistence_fallback` | 12 | forecast |
| DL — Delhi | 42 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| GA — Goa | 90 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| GJ — Gujarat | 2126 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| HP — Himachal Pradesh | 577 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| HR — Haryana | 1773 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| JH — Jharkhand | 1898 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| JK — Jammu and Kashmir | 427 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| KA — Karnataka | 2081 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| KL — Kerala | 1251 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| LA — Ladakh | 0 | None | `no_observations` | 0 | insufficient_data |
| LD — Lakshadweep | 0 | None | `no_observations` | 0 | insufficient_data |
| MH — Maharashtra | 2538 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| ML — Meghalaya | 478 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| MN — Manipur | 14 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| MP — Madhya Pradesh | 4366 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| MZ — Mizoram | 5 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| NL — Nagaland | 136 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| OD — Odisha | 2579 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| PB — Punjab | 1682 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| PY — Puducherry | 111 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| RJ — Rajasthan | 2591 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| SK — Sikkim | 1 | 2025-01-01 | `persistence_fallback` | 12 | forecast |
| TN — Tamil Nadu | 3199 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| TR — Tripura | 379 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| TS — Telangana | 1055 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| UK — Uttarakhand | 221 | 2026-01-01 | `persistence_fallback` | 12 | forecast |
| UP — Uttar Pradesh | 5298 | 2026-01-01 | `state_median_xgboost` | 12 | forecast |
| WB — West Bengal | 1382 | 2026-01-01 | `persistence_fallback` | 12 | forecast |

The totals are 43,384 genuine district-month observations across 34 states.
The generated set contains all 36 states, 408 forecast rows and 2,160 historical
calendar rows. Source generation is `physical-v3-official-c9ade81d95720f91`,
CSV SHA-256 `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042`.
Sikkim's sole source-marked observation is a 19.26 m district-month mean in
January 2025, at 25% registered-district coverage. Its twelve predictions repeat
19.26 m, preserve the original month and disclose the 21-month age.

## Immutable release and storage

The new directory is `models/artifacts/state_median_releases/20261029-r2`;
artifact release is `2026.10.29-r2`, algorithm/policy model version is
`2.0-state-median-tiered`, and policy version is `1.0-state-median-coverage`.
Manifest SHA-256:
`8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3`.
Its policy model card records the per-state method, source counts, references,
rejection reason and unchanged XGBoost training eligibility. The base model card
and all seventeen XGBoost files are copied byte-for-byte from r1. No model was
retrained for this coverage change; district artifacts were never modified.

The stage UUID is `789ce3b5-3170-5866-9ce2-c0ec2f0b1b59` in the isolated schema
`aquaiq_test_state_median_coverage_20261029`. It has zero publication events and
zero active-pointer rows. Staging validates every method-specific response,
constant fallback path, consecutive dates, units, finite depths, source identity,
policy/card hashes, reference provenance, count/age/coverage coherence and
evaluation scope. Existing atomic publication, compare-and-swap and rollback
mechanisms are preserved and tested with isolated synthetic fixtures. No new
database migration is necessary: existing nullable model hashes already support
non-learned methods. Old r1 generations retain their original validation and
summary bytes. Explicit `model=median_xgboost` never silently returns an r2
tiered release; callers normally omit `model` and pin a published generation.

## Reproduce without publication

These commands require the verified local source and existing r1 assets. Every
output directory/path must be new. The historical evaluation attachment requires
its exact frozen model card; do not pair a newly regenerated card with an old
report. If that private/local frozen artifact is missing, reproduce training and
evaluation together as documented in the prior release guide, or omit both
evaluation arguments and disclose unavailable historical errors.

```powershell
$coveragePython = '.\venv\Scripts\python.exe'
$coverageSource = 'data/processed/enrichment/final_release_20261026_v3'
& $coveragePython -B -m scripts.audit_state_median_coverage --processed-dir $coverageSource --release-dir models/artifacts/state_median_releases/20261029-r1 --as-of 2026-10-29 --output scratch/coverage_NEW/before
& $coveragePython -B -m scripts.release_state_median prepare --release-dir models/artifacts/state_median_releases/COVERAGE_NEW --artifact-release COVERAGE_NEW --forecast-policy tiered_observed --processed-dir $coverageSource --as-of 2026-10-29 --trained-artifacts models/artifacts/state_median_releases/20261029-r1/models --evaluation models/artifacts/state_median_releases/20261029-r1/evaluation.json --evaluation-artifacts scratch/state_median_primary_20261029/frozen_v3data
& $coveragePython -B -m scripts.release_state_median verify --release-dir models/artifacts/state_median_releases/COVERAGE_NEW --expected-release COVERAGE_NEW
& $coveragePython -B -m scripts.release_state_median generate --release-dir models/artifacts/state_median_releases/COVERAGE_NEW --processed-dir $coverageSource --as-of 2026-10-29 --output scratch/coverage_NEW/generation.json --test-schema aquaiq_test_coverage_new
& $coveragePython -B -m scripts.audit_state_median_coverage --processed-dir $coverageSource --release-dir models/artifacts/state_median_releases/20261029-r1 --as-of 2026-10-29 --generation scratch/coverage_NEW/generation.json --output scratch/coverage_NEW/after
```

The commands end at generation, private staging and independent validation.
There is deliberately no publication/deployment command in this procedure.
Changing the forecast vintage requires a new immutable r2 policy artifact.
Ordinary HTTP requests still read published snapshots only, never train or
generate forecasts. The local staged browser fixture is separately labelled
`LOCAL STAGED PREVIEW — RELEASE NOT PUBLISHED` and is not a serving fallback.

## Files and verification

The state-only changes are `models/state_median_policy.py`, version dispatch in
`models/state_median_release.py`, method-aware validators/storage in
`models/state_median_storage.py` and `models/state_median_release_storage.py`,
the state release/audit commands, and `api/routes/state_median.py`. The state
chart/contract, cards, map and comparison table disclose actual methods and
reference ages. `.gitattributes` preserves the policy implementation's hash.
New policy/audit/storage/frontend regression tests and this documentation cover
the change. Earlier working-tree changes and immutable r1 assets are preserved.

Executed results:

- Full Python suite: **1,903 passed, 47 skipped** (existing scientific-library warnings remain).
- Complete focused state-model/policy/audit/evaluation/storage/API/release/deployment selection with PostgreSQL integration: **166 passed**.
- Fresh legacy persisted state/district API, six-month district API and v2 API regressions: **15 passed**. The real 725-district test fixture was recomputed; only that test process's legacy namespace override was cleared. `.env`, model and checkpoint bytes were preserved (79 files verified unchanged).
- Frontend: **184 passed**, lint and final production build passed.
- Actual staged-response contracts and rendering: all **36** responses validated, with **34 forecasts**, **408 monthly forecast values**, **2 no-observation states**, all **36 table rows**, and zero validation errors.
- Independent source audit: zero violations. All 17 XGBoost states' **204 predictions and model hashes exactly match r1**.
- Real browser: desktop 1280×900 and mobile 390×844. Sikkim's single historical point, dated/aged low-coverage reference, named persistence line and 12 values were verified. The low-coverage legend is visible. Mobile page width was 389 px within a 390 px viewport; Ladakh had no chart or forecast rows. No browser console errors; viewport restored.
- Actual r2 staging has **zero publication events and no active pointer**; all 36 normal published-API requests to its UUID returned explicit 503. Existing r1 publication and public district generation stayed unchanged. No production migration or publication occurred.

Commands used for the main checks:

```powershell
& $coveragePython -B -m pytest -q
& $coveragePython -B -m pytest tests/test_state_median_forecast.py tests/test_state_median_policy.py tests/test_state_median_coverage_audit.py tests/test_state_median_evaluation.py tests/test_state_median_storage.py tests/test_state_median_api.py tests/test_state_median_release.py tests/test_state_median_release_storage.py tests/test_state_median_policy_storage.py tests/test_state_median_v2_api.py tests/test_deployment_readiness.py -q --integration
npm test --prefix dashboard
npm run lint --prefix dashboard
npm run build --prefix dashboard
node scratch/state_median_coverage_20261029/validate_frontend.mjs scratch/state_median_coverage_20261029/stage_bundle.json
```


Independent evidence is saved under `scratch/state_median_coverage_20261029/`:
`audit_after/coverage.{md,csv,json}`, `audit_after/xgboost_preservation.json`,
`stage_validation.json`, `frontend_validation.json` and browser screenshots.
The stage validation also confirms that every normal API request to this
unpublished UUID returns explicit 503, not an ad hoc fallback. No actual release
was published, production database modified, environment changed, deployment
performed, commit created, push made or merge performed.
