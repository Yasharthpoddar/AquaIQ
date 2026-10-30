# Independent r2 artifact and source verification

Verified on 2026-10-29 against the current checkout and local supplied source snapshot. This report covers local artifacts, source reconstruction, a fresh forecast export and focused tests. It does not certify a production host, database role, backup restore or publication. No artifact was retrained or rewritten; no database connection, staging, publication or deployment was performed by these checks.

## Results

| Check | Status | Direct evidence |
|---|---|---|
| Exact r2 release and pinned manifest | PASS | `2026.10.29-r2`, format 2, `2.0-state-median-tiered`, policy `1.0-state-median-coverage` |
| Source CSV, manifest, dataframe and registry identities | PASS | Recomputed hashes and manifest-verified source loading |
| Core, policy, cards, evaluation and all 17 weight files | PASS | Runtime release verifier plus independent file inventory |
| Complete 36-state inventory | PASS | 17 XGBoost, 17 persistence, Ladakh/Lakshadweep alone with no observations |
| Forecast dates, values, units and provenance | PASS | 408 finite nonnegative monthly values, November 2026–October 2027 |
| Genuine observation counts and state medians | PASS | Independently rebuilt district-month means followed by equal-district medians from source observation flags |
| Fallback reference date, age, count, depth and coverage | PASS | All 17 constant paths match their latest genuine state median, including low-coverage and stale references |
| Honest method and evaluation disclosure | PASS | Persistence has no learned-model hash/cutoff or inherited XGBoost scores; frozen XGBoost evidence is distinguished from released weights |
| Preservation of r1 XGBoost | PASS | All 17 model files and all 204 corresponding forecast rows exactly match r1 |
| Fresh r2 repeatability | PASS | All 36 payloads exactly match the preceding r2 export after excluding only `computed_at` |
| Immutable r2 tree | PASS | Complete file hashes unchanged before/after independent verification |
| District and Home file compatibility | PASS | No Git diff in the explicitly checked district/model/Home paths; original district model hash unchanged |
| Focused current-tree tests | PASS | 62 passed in 13.17 seconds |
| Persisted UUID, publication state and serving permissions | UNVERIFIED here | This fresh JSON export was intentionally not staged; use the separate database-readiness findings |
| Production host/runtime/image and restored source assets | UNVERIFIED here | Local runtime verification does not verify an unidentified target host |
| Production backup recovery and operational authorization | UNVERIFIED here | No production access or restore was attempted |

## Recomputed identities

| Item | SHA-256 |
|---|---|
| r2 release manifest | `8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3` |
| Source CSV | `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042` |
| Source manifest | `6d98e62cd2d55504e8df74ceb4d8faf099fe712826981bdc787eef56bfab19c0` |
| Source dataframe fingerprint | `2982c2d53bfe2b747a7d86821323d0f8bd58d1d755baa713d1b8741a40999209` |
| Coverage policy implementation | `86b0845b6c0747f3556ed9c88501847f929a451ad29d537acfe9c0e15c0f5bca` |
| Policy model card | `cff7929944d225ed92be94f06b59d03c12e57d78008732238faba7518c6faf77` |
| XGBoost component model card | `2ab75da0eeb8dbd8c98a61a275d24e7b76a87582fd8161cfd91b2995d48f0be8` |
| Historical evaluation report | `335865b1dc9b4cbe90c470b5b50692d44996ba1b6b45d95156701df6b3461732` |
| Original district model | `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03` |

Source generation is `physical-v3-official-c9ade81d95720f91`, containing 43,384 genuine district-month aggregates. The local release verifier passed with Python 3.13.15, NumPy 2.5.4, pandas 3.0.6, scikit-learn 1.9.1 and XGBoost 3.4.1. Matching versions and artifact hashes must still be checked on the target runtime.

## Scientific and freshness limits

All 34 forecast reference observations are stale under the explicitly documented three-month reporting interval: 31 references are nine months old, DD and SK are 21 months old, and AN is 42 months old. These actual ages and dates are preserved in both the policy card and response metadata. The source calendar extending through September 2026 does not imply September groundwater observations.

AR, JK, MN, MZ and SK use references below XGBoost target-coverage eligibility. They receive explicitly named persistence references, with their true district coverage preserved; those records do not become qualified XGBoost training labels.

Persistence has no attached held-out accuracy evaluation. It predicts a constant reporting-district median, not a trend or groundwater volume. The released XGBoost component was refitted through the allowed September 2026 month-label cutoff; the latest actual qualified training labels are from January 2026. Its displayed historical evidence belongs to frozen December 2019 weights, not the current refit. That comparison contains 892 repeated forecast cases, 208 distinct state-month targets and 23 observation dates across 17 states. All horizons have evidence, but M+12 has only 68 cases during January–November 2022. These limitations remain material despite successful local engineering checks.

## Executed commands

All commands ran from the repository root with the existing project environment. The fresh generation command deliberately omitted `--test-schema`, so it exported only and returned `staged: null`.

```powershell
.\venv\Scripts\python.exe -B -m scripts.release_state_median verify --release-dir models/artifacts/state_median_releases/20261029-r2 --expected-release 2026.10.29-r2 --expected-manifest-sha256 8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3
.\venv\Scripts\python.exe -u -B -m scripts.release_state_median generate --release-dir models/artifacts/state_median_releases/20261029-r2 --processed-dir data/processed/enrichment/final_release_20261026_v3 --as-of 2026-10-29 --output scratch/state_median_readiness_20261029/artifacts/generation.json
.\venv\Scripts\python.exe -u -B -m scripts.audit_state_median_coverage --processed-dir data/processed/enrichment/final_release_20261026_v3 --release-dir models/artifacts/state_median_releases/20261029-r1 --as-of 2026-10-29 --generation scratch/state_median_readiness_20261029/artifacts/generation.json --output scratch/state_median_readiness_20261029/artifacts/coverage_audit
.\venv\Scripts\python.exe -B -m pytest tests/test_state_median_policy.py tests/test_state_median_coverage_audit.py tests/test_state_median_evaluation.py tests/test_state_median_release.py tests/test_state_median_forecast.py -q -p no:cacheprovider
.\venv\Scripts\python.exe -u -B scratch/state_median_readiness_20261029/artifacts/verify_artifacts.py
```

Fresh export results: 36 states, 34 forecasts, 408 monthly values, no staging or publication. Focused tests returned **62 passed in 13.17s**, with no skips or failures in this selection. Repeat runs must use fresh output paths; existing evidence is never overwritten.

## Evidence

Local evidence is under `scratch/state_median_readiness_20261029/artifacts/`:

- `generation.json`: freshly generated actual responses.
- `coverage_audit/coverage.{json,csv,md}`: all 36 source counts, old eligibility gates and independently checked new coverage.
- `verification/verification.json`: complete artifact hash inventory and verification results.
- `verification/states.csv`: every state's method, status, observation count, date, age, coverage and forecast count.
- `verify_artifacts.py`: reproducible independent reconstruction and artifact checks.
- `r2_repeatability.json`: exact comparison of all 36 fresh r2 payloads against the preceding export, excluding only generation timestamps.
- `focused_tests.txt`: complete current-run focused test output.

The checked unchanged Git paths include district XGBoost/12-month/tiered implementations, the existing state mean helper, nationwide precomputation, district prediction routes, Home, DistrictDetail, DistrictForecastGraph, configuration and the original tracked district artifact tree. Runtime district API behavior and database isolation are covered by the separate application/database audit, not inferred from this file check.

**Local artifact gate: PASS.** Production deployment still requires the separate verified database/serving-role, backup-recovery and target-host gates, and explicit operator authorization. No production-readiness claim follows from these local checks alone.
