# Complete district forecasting

The serving product is a persistent, versioned twelve-month generation for **every district registered in the repository crosswalk**. The 2026-10-25 snapshot contains 725 districts in 36 states/UTs. This is a fixed project inventory, not a claim to match the latest national administrative inventory. Registry metadata is validated and counts are calculated at runtime.

## Methods and evidence

| Tier | Method | Eligibility and interpretation |
|---|---|---|
| A | Existing climate-conditioned XGBoost, unchanged weights | Successful existing anchor fit (24 genuine observed district months spanning 36 months), compatible bundle, complete origin-available weather path. Current depths/lags may be estimated. Data support does not establish current forecasting accuracy. |
| B | Last genuine local depth held constant | Some local history, but the existing anchor cannot be fitted. Includes 1–9 and 10–23 observations, short spans and other insufficient-anchor cases. No invented history or weather. |
| C | District-balanced empirical state seasonal reference, otherwise global reference | No genuine locally mapped depth history. Each donor contributes its past ten-year same-month median; a missing donor phase uses that donor's observed-window median as an estimate. The target district is excluded entirely. Use state donors only when at least two other districts exist; otherwise use the global distribution. State membership is not an aquifer similarity model. |
| D | Local persistence, environmental inputs unused | The groundwater anchor is supportable but required weather is genuinely unavailable. This applies to Mumbai Suburban in this snapshot. |

The two-donor rule is the minimum for a regional multi-district distribution, not a target eligibility cutoff. With no legitimate national donors, generation fails and preserves the old publication. There are no hand-assigned district depths or zero-filled environmental predictors. B/D deliberately retain persistence as a conservative reference; the evaluated regional seasonal-transfer candidate is not selected on evaluation outcomes.

XGBoost is already pooled across 558 training districts. Its training origins have observed groundwater and serving-compatible climate features. Sparse histories cannot support its existing current-depth/lag estimator; simply providing NaNs or relaxing its anchor safeguard would not validate that different input distribution. Its 24/36 requirements are internal implementation rules, not legal mandates. Readiness coverage starts at the first genuine measurement, ends at the latest completed input month and includes subsequent monitoring gaps. Recency and coverage are disclosed separately; monitoring percentage is not used as an additional XGBoost forecasting gate. Legacy six-month products retain their separate contracts.

## Contract and storage

Each district has one header and twelve ordered month-start values, in **metres below ground level (`m_bgl`)**. `predicted_gwl` is absolute depth; `delta_from_current_m` is a separate difference. `model_version` identifies the method, `pipeline_version` identifies the tier router, and `forecast_method`, `evidence_tier`, `evidence_status`, `observation_count`, last observed date, observation age, readiness, feature completeness, missingness, fallback reason, warning, artifact identity and generation provenance explain the evidence.

`observation_count` counts genuine source-marked **district-month aggregates**, not wells. Forward fills never become observations. Weather fields are JSON null for reference methods and explicitly marked unused. Zero-history references have no local observation date or observed depth.

Historical absolute-error ranges use a pre-evaluation 90th percentile by tier/horizon, clipped at zero. These are marginal historical residual ranges, not guaranteed 90% local intervals. Small XGBoost calibration panels (4–7 districts depending on horizon), spatial dependence, observation age and distribution shifts limit them. Empirical held-out coverage was approximately 76.6% / 86.7% / 88.2% / 87.1% for A/B/C/D respectively. Do not interpret them as calibrated present-day confidence. Bounds, calibration identity and sample counts are returned; uncalibratable historical requests retain an explicit unavailable uncertainty status.

`scripts/precompute_forecasts.py` runs the single district workflow and aggregates all registered district results with **equal district weights**. Each state exposes evidence counts, proportions and district methods. This is not area weighting, well weighting or groundwater volume. Donor sharing creates correlated fallback errors, so averaging does not establish a more reliable state estimate. Observed history uses each month's reporting panel and remains separate. No independently observed complete state panel exists to validate nationwide state accuracy.

Migration 004 is additive and repeatable. The storage transaction checks registry equality, dates, horizon counts, finite nonnegative absolute depths, method/evidence consistency, model identity, ranges and state means before publication. Per-origin PostgreSQL advisory locks serialize publishers. Generation identities are immutable. Failed validation or a failed transaction cannot supersede the previous valid generation. Indexed reads select the published snapshot and never require the live training artifact; changing or losing source assets does not hide an already published vintage. Process caches store payloads by immutable generation ID, not an indefinitely cached active pointer.

When `as_of` is omitted, the twelve-month APIs and state registry pin the latest published vintage no later than today. Its explicit `as_of`, generation and forecast dates remain visible; an old vintage is not relabelled as today's forecast. Explicit `as_of=YYYY-MM-DD` selects that date exactly. Missing generations return HTTP 503 with a retryable UI. Normal requests never launch nationwide inference. The opt-in `AQUAIQ_ENABLE_SYNC_FORECAST_FALLBACK=true` exists for legacy diagnostic utilities only; leave it false for normal serving.

## Reproduce in a safe local namespace

Use the existing Python environment or install `requirements.txt` into a clean Python 3.13 environment. Install the dashboard with `npm ci --prefix dashboard` on Node 22.12+. Configure a **local/test PostgreSQL database** using `.env.example`; never commit `.env`. A code-only clone needs the private/local runtime assets: verified `data/processed/features_matrix.csv`, its matching manifest and the existing compact tracked XGBoost bundle. Raw sources are required only for source-audit/reprocessing commands. No downloads or model refits are part of precomputation.

```powershell
.\venv\Scripts\python.exe -m scripts.validate_tiered_forecasts --write-calibration
.\venv\Scripts\python.exe -m scripts.audit_spatial_recovery
.\venv\Scripts\python.exe -m scripts.precompute_forecasts --test-schema aquaiq_test_nationwide_20261025 --as-of 2026-10-25 --export-dir scratch/nationwide-complete --output reports/nationwide_20261025/generation.json
.\venv\Scripts\python.exe -m scripts.precompute_forecasts --test-schema aquaiq_test_nationwide_20261025 --as-of 2026-10-25 --validate-only
$env:AQUAIQ_FORECAST_SCHEMA='aquaiq_test_nationwide_20261025'
.\venv\Scripts\python.exe -m api.app
```

`--test-schema` accepts only `aquaiq_test_*` identifiers and applies migration 004 in that namespace. Public source tables and production forecasts are preserved. The schema remains available for local inspection. `--dry-run` computes/validates without publishing. Repeating identical inputs validates and reuses the existing immutable generation, including with `--force`; different implementation, model, registry, configuration, feature or calibration identities create a new generation. `--validate-only` checks stored JSON and normalized monthly rows, not just the publication status. To deploy elsewhere, apply migrations and run the same precomputation against that deployment's configured test database before publishing there.

API examples: `/api/states`, `/api/states/summary?horizon=12&as_of=2026-10-25`, `/api/predict/state/TS?horizon=12&as_of=2026-10-25`, `/api/predict/climate-12m/AN-Nicobars?months=12&as_of=2026-10-25`. Six-month endpoint and climate projection query parameters are unchanged.

`GET /api/districts` returns every canonical district ID, name and state independently of the database, model artifacts and scoring runs. Home and Simulate use this registry for navigation; optional risk records enrich it without removing districts. Home's primary cards show published forecast evidence counts. The separate six-month risk index may be unavailable or awaiting a matching scoring run without blocking district search, map navigation or twelve-month forecasts. Map colours retain their explicit risk-index meaning; grey does not imply a missing district forecast.

To populate the separate risk index and Alerts locally, reuse the existing scoring pipeline with output-only migration 005. This computes historical six-month index components, not new twelve-month forecasts or calibrated crisis probabilities:

```powershell
.\venv\Scripts\python.exe -m models.score_all --date 2026-10-26 --test-schema aquaiq_test_nationwide_20261025
$env:AQUAIQ_FORECAST_SCHEMA='aquaiq_test_nationwide_20261025'
$env:AQUAIQ_SCORING_SCHEMA='aquaiq_test_nationwide_20261025'
.\venv\Scripts\python.exe -m api.app
```

The scoring namespace contains only `scoring_runs`, `crisis_scores` and legacy `predictions` output tables with their own sequences; source district/feature reads resolve to the existing public data. An uninitialized configured scoring namespace returns a service error instead of falling back to public score storage. Complete output is published in one transaction; computation or write failures preserve the previous complete run. `/scores` and `/alerts` select the configured namespace and a matching model/data/scoring signature. Neither route starts a scoring job. Missing risk evidence remains null. The Home map fits all supplied district bounds, updates on container resize and provides a **Show all India** reset control.

## Validation design and limitations

The [saved validation](../reports/nationwide_20261025/validation.json) contains tier, district, horizon and experiment metrics on identical target observations. Fallback calibration origins are January/July 2017–2018. Evaluation starts July 2019, then rolls across January/July 2020–2023 plus January 2025. XGBoost calibration uses January/July 2021 after its frozen 2019 training-label cutoff and twelve-month embargo; its evaluation starts July 2022, after all calibration targets. Earlier evaluation origins are purged. Empty origins remain recorded. January 2025 tests include the January 2026 refresh at M+12. Tests condition on calendar observation months; provider publication timestamps remain unknown.

Pseudo-sparse experiments retain only the last 1/3/9/23 genuine observations, using a deterministic pre-outcome district hash to select the cap. Pseudo-cold experiments exclude all target district history from donor statistics. Neither sparse nor cold experiments use XGBoost, which saw those districts in earlier training. Mutating hidden history or future observations does not change reference predictions. Tests also mask environmental inputs and exercise the actual XGBoost serving anchor across historical observation gaps. Persistence and available same-month seasonal naive use exactly the same local history as their paired method. Zero-history persistence and seasonal-naive baselines are undefined; global reference is the valid comparable baseline instead.

These are reused historical data, not a blind or prospective study. Donor districts can be spatially correlated; leave-one-district-out is **not** geographically blocked validation. An additional state-blocked reference sensitivity excludes every target-state history and is reported separately. Few target-specific environmental features and uncertain spatial attribution do not support a defensible new geospatial learned model for truly unmonitored districts. The empirical regional reference therefore remains explicitly a fallback. Most natural sparse districts have only a January 2026 observation; natural sparse validation has just seven target cases, so pseudo-sparse evidence must not be overstated. Most post-2021 monthly labels occur in a handful of districts. A January 2026 nationwide refresh expands horizon-12 evidence but does not validate every monthly trajectory.

The [spatial audit](../reports/nationwide_20261025/spatial_audit.json) preserves Telangana candidate assignments from the existing strict coordinate resolver, including invalid/ambiguous/duplicate checks and boundary/source hashes. The boundary contains mixed dates; 40,845 accepted candidate readings disagree with their historical parent crosswalk. These candidates are not ingested into the immutable feature generation. The supplied Mumbai polygon lacks a separate Suburban boundary; raw IMD and cleaned ERA5 grid probes select a nearest usable cell at 19°N, 73°E, approximately 15.1 km from the representative point. A common coarse cell does not verify district-specific weights. No unsupported Mumbai alias or station reassignment is applied.

Source conventions: [CGWB monitoring and source access](https://cgwb.gov.in/en/ground-water-level-monitoring), [CGWB monitoring schedule](https://www.cgwb.gov.in/en/faq-general), [IMD daily 0.25° product](https://www.imdpune.gov.in/cmpg/Realtimedata/Rainfall/Rain_Download.html). These support data conventions; none establishes this project's forecast accuracy or the internal 24-observation rule.
