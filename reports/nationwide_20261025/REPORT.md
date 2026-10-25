# AquaIQ nationwide completion and validation — 2026-10-25

## Coverage and generated output

The current registry, feature export and source database were recalculated, not assumed from the old report. Before: **426/725** district forecasts and **299** empty district results; 16/36 states met the old eligible-panel rule. After: **725/725** district results, **8,700/8,700** finite monthly predictions, no missing districts/horizons, and 36/36 state outputs.

| Evidence | Districts | Method |
|---|---:|---|
| A | 547 | Existing climate-conditioned XGBoost |
| B | 104 | Limited-history local persistence |
| C | 73 | Zero-local-history regional/global seasonal reference |
| D | 1 | Missing-environment local persistence (Mumbai Suburban) |

Origin: October 2026; targets **2026-11-01 through 2027-10-01**. Units: absolute depth in metres below ground (`m_bgl`), with changes in separate fields. The generation is published **only in the local test schema `aquaiq_test_nationwide_20261025`**. Public source and production forecast tables were not overwritten. Full local outputs: `scratch/nationwide-complete/districts.json`, `states.json`, `summary.json`. See [generation metadata](generation.json) and [all-endpoint verification](release_verification.json).

## Defects fixed and implementation

- Added a validated canonical registry view from the existing crosswalk; normalize equivalent state aliases and reject conflicting names, membership, ambiguous source IDs, duplicates and unknown feature districts. Reconcile all 725 IDs/names/states to the source database.
- Corrected readiness denominators to begin at the first genuine measurement, retain monitoring gaps through the completed cutoff, and report recency separately. Forecast eligibility follows the existing anchor's actual 24-observation/36-month requirements, not the old 2002-based coverage gate.
- Kept the XGBoost weights and suitable district behavior. Sparse histories do not pass an unsupported anchor fit; persistence and zero-history references are separate methods and versions with honest evidence metadata. All outputs retain genuine observed-month counts, input missingness, dates, fallback reasons, provenance and historical ranges.
- Strengthened atomic publication: reject incomplete/nonfinite/misdated output before writes, validate state means and normalized row counts, serialize publishers with advisory locks, and preserve immutable generations. A failed rebuild cannot hide the last published vintage when current input artifacts change. Remove stale process-local active-pointer reuse.
- Normal API reads use persisted results. Removed implicit synchronous inference enabled merely by importing pytest. Canonical district resolution works independently of source-data availability; recorded legacy aliases retain database precedence. Default reads pin the latest published vintage with its actual dates.
- Reconciled state aggregation across all registered districts with equal weights, tier counts/proportions and per-district methods. No area, well-weighting, volume or representative-state accuracy claim.
- Updated frontend contracts and district/state views for all evidence tiers, ranges, missing features and retry states. Existing six-month APIs remain available. Retained the existing CORS/proxy and state UI repairs, and fixed the missing `deepcopy` import in the stored district entrypoint.
- Expanded ignore rules for private configuration, keys/databases and local row-level/generated artifacts. Removed an existing **empty** SQLite placeholder from Git tracking while preserving its local file.
- Corrected the legal/statutory claim and marked older audit narratives and XGBoost-only state documentation as superseded. The original related working changes are incorporated; the Overleaf directory and unrelated prior benchmark files remain outside this commit.

Main code: `models/district_registry.py`, `tiered_forecast.py`, `forecast_storage.py`, `ensemble.py`; `scripts/precompute_forecasts.py`, `validate_tiered_forecasts.py`, `audit_spatial_recovery.py`, `verify_nationwide_release.py`; API contracts/routes/resolver; dashboard district/state contracts and views; additive migration 004; regression tests. See [methodology and reproducible commands](../../docs/NATIONWIDE_FORECASTS.md).

## Historical backtests

The saved [validation JSON](validation.json) contains results by evidence tier, district, horizon, origin, experiment and genuine observation count. All methods/baselines compare on identical observed targets in their paired sets. Calibration uses 25,356 rows. Evaluation uses **16,705 rows** after purging **6,890** rows whose origins preceded the last calibration target for that tier. Rows across experiments are repeated uses of observed targets, not 16,705 independent measurements.

Fallback calibration origins: January/July 2017–2018; evaluation starts July 2019 and rolls through 2020–2023 plus January 2025. XGBoost calibration origins: January/July 2021, after the frozen 2019 training-label cutoff and twelve-month embargo; evaluation starts July 2022. Every calibration target precedes its tier's first evaluation origin. The evaluation includes actual serving anchors across observation gaps, not only observed origins. Previously computed point predictions were reused to correct the temporal purge and add geographic sensitivity; no prediction refit or test-driven model selection was performed.

| Tier | Cases | Method MAE (m) | Method RMSE (m) | Paired baseline | Baseline MAE (m) | Baseline RMSE (m) | Historical range coverage |
|---|---:|---:|---:|---|---:|---:|---:|
| A | 576 | 2.215 | 4.713 | Persistence | 2.181 | 4.547 | 76.56% |
| B | 5,376 | 2.093 | 3.501 | Persistence | 2.093 | 3.501 | 86.68% |
| C | 5,462 | 3.966 | 7.712 | Global reference | 4.607 | 9.062 | 88.15% |
| D | 5,291 | 2.094 | 3.498 | Persistence | 2.094 | 3.498 | 87.05% |

XGBoost does not beat persistence overall here. B/D are deliberately persistence estimates. Seasonal naive is evaluated on its available paired subset; regional seasonal transfer is a separately reported candidate, not selected on evaluation outcomes. For C, local persistence/seasonal baselines are undefined without local history; global reference is the valid comparison. With the entire target state's histories excluded, the C reference sensitivity has **MAE 4.665 m, RMSE 9.109 m** on the same 5,462 cases. This illustrates transfer risk; it does not confer spatial independence on ordinary within-state or XGBoost results.

Pseudo-sparse experiments retain only the last 1/3/9/23 actual measurements. Pseudo-cold references exclude all target district history, including earlier years, and never use the XGBoost artifact trained on those districts. Tests verify invariance to hidden target/future data. Natural sparse validation has only **seven target cases**; most sparse districts have a lone January 2026 refresh. January 2026 expands horizon-12 evidence but does not establish monthly path accuracy.

Ranges are nominal 90th-percentile historical absolute-error bands, not guaranteed present-day intervals. The table's observed undercoverage is explicit. XGBoost calibration has only 4–7 districts per horizon. Target-region data sparsity, shared donors, changing well panels, unavailable publication times, prior inspection of holdouts and observation gaps limit all results. No superiority or operational readiness claim is made.

## Spatial and environmental findings

The [reproducible spatial audit](spatial_audit.json) found 56,679 Telangana source readings and 2,223 unique named coordinates. The existing strict coordinate/duplicate auditor produced 55,595 accepted candidate readings and 3,222 candidate district-months across 33 districts; 106 negative-depth and 979 unmatched-coordinate rejections can overlap. It does not silently snap ambiguous points. **40,845** accepted readings disagree with the historical parent crosswalk. Boundary dating is mixed, and station identity/coordinate provenance is not independently certified. Candidates remain local and un-ingested; current XGBoost source attribution is not retroactively certified.

The current refresh already gives 23 newer Telangana districts a small amount of genuine history; they are tier B, not zero-history claims copied from old notes. Mumbai Suburban has no distinct supplied polygon. Sixteen of its 18 source coordinates fall within the combined-looking Mumbai polygon, which is insufficient to certify all district attribution. Raw IMD and cleaned ERA5 source-grid probes select the 19°N, 73°E nearest usable cell, about 15.1 km from the polygon's representative point. No unvalidated alias, zero weather or guessed nearest-district assignment is used. Tier D supplies its explicit local reference instead.

## Engineering verification

Executed checks and logs are recorded in [engineering validation](engineering_validation.json). The main unit suite passed **1,288 tests**, with **32 explicit integration skips**. Separate local integration runs passed **49 tests** (forecast storage, twelve-month pipeline, tiered invariants and canonical IDs) and **19 tests** (physical features, ingestion identities and isolated migrations). Frontend: **150 passed**, lint passed, production build passed with its existing large-bundle warning. Nine [real-data browser flows](browser.json) passed at desktop/tablet/mobile widths, including all four tiers and API failure/retry behavior.

The release verifier reads all **725 district + 36 state endpoints**, checks the source registry, normalized and JSON horizon records, units/dates and state mixtures, and forbids model inference during persisted forecast reads. It also checks both six-month products, missing-generation errors, invalid requests, default vintage selection and reads with unavailable live artifacts. Storage tests inject an incomplete generation and a mid-transaction write failure, then prove the previous published generation remains available; corruption of normalized records is detected.

Baseline sandbox tests had six database-access failures; those were investigated. An initial live integration run also exposed an old Delhi fixture assumption, and a migration test caught CSV aliases overriding recorded database aliases. The final fixtures use explicit supported evidence and the alias precedence defect is fixed. Initial browser harness timing/tier-order assumptions were corrected against actual data. Final results above describe inspected successful runs, not the earlier failures.

Fresh dependency installation and hosted/production deployment were not performed. The source data/feature export remain external prerequisites. The build's JavaScript chunk-size warning is unresolved. A fully updated administrative registry, independently verified station/boundary provenance, hydrogeological transfer features, better calibration and new prospective observations remain scientific limitations, while complete labelled local output coverage is achieved.

## Repository safety and GitHub

The initial branch was `feature/xgboost-only-states-ux` at `fe3b22a`, with substantial existing related edits. The baseline diff and hashes are preserved locally under `scratch/completion_baseline/`. No reset, user-change discard, stash, history rewrite or force push was used. Only task-related files are staged. Staged-content scanning checks private keys, credential URLs/tokens, private configuration/database files and large artifacts without printing secret values. The single CORS invalid-URL fixture uses the reserved example.org domain and is explicitly identified as a test literal.

The configured target is `origin` → `https://github.com/Yasharthpoddar/AquaIQ.git`, on the existing task branch. Final commit SHA and push verification are reported in the completion message after checks finish.
