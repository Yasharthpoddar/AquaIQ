# AquaIQ — Persistent XGBoost Forecast Storage and Precomputation Report

**Date:** 2026-10-25  
**Branch:** `feature/xgboost-only-states-ux`  
**System Architecture:** Ahead-of-time XGBoost precomputation, PostgreSQL persistent storage, and sub-50ms indexed API serving  

---

## 1. Executive Summary

AquaIQ provides district-level and state-level 12-month groundwater forecasts across 725 canonical districts and 36 states and Union Territories. Previously, forecast calculation was performed dynamically on-demand during HTTP requests. A cold request to `/api/states/summary?horizon=12` required full feature loading, dataset validation, 725 district readiness evaluations, 426 district XGBoost model inferences, weather climatology path computations, and nationwide aggregations across 36 states. This resulted in an initial cold request latency of **39.42 seconds** (and **40.82 seconds** for the concurrent States page sequence). Although in-memory caching reduced subsequent requests to ~42 ms, that cache was process-local: it was wiped upon server restart, failed across multi-worker environments, and forced any worker or newly restarted process to repeat the full 40-second inference pipeline.

### Architectural Solution
We separated **forecast generation** from **forecast serving**:
1. **Ahead-of-Time Precomputation:** A dedicated, batch-optimized CLI command (`python -m scripts.precompute_forecasts --horizon 12`) verifies model artifacts and feature provenance, executes district inference in batches of 50, performs exact fixed-panel state aggregation, and validates output contracts.
2. **Persistent Versioned Storage:** A dedicated PostgreSQL schema migration (`004_xgboost_forecast_storage.sql`) stores generation metadata, district forecast records, district monthly horizons, state forecast summaries, state monthly horizons, and the nationwide state summary.
3. **Atomic Multi-Worker Publication:** Generations follow a safe lifecycle (`building` → `validated` → `published` / `superseded` / `failed`). The entire generation is written and promoted atomically in a single database transaction, ensuring readers never observe partial or corrupt forecasts.
4. **Input Identity Invalidation:** A cryptographically sound SHA-256 generation signature binds the active forecast to the exact model weights, model card, feature data export, district registry, crosswalk, and state mapping. Any upstream data or artifact change safely invalidates obsolete records without fabricating values.
5. **Sub-50ms Serving:** API routes (`/api/predict/climate-12m/<district_id>`, `/api/predict/state/<state_id>`, `/api/states/summary`) read indexed precomputed records directly from PostgreSQL with a process-local L1 cache. Normal API reads **never invoke XGBoost model inference**. When forecasts have not yet been precomputed, endpoints return an explicit HTTP 503 `model_unavailable` with actionable diagnostics rather than hanging on long synchronous fallback computations.

---

## 2. Benchmark & Performance Outcomes

All measurements were taken using `scripts/benchmark_persistent_forecasts.py` executing against PostgreSQL with an isolated test schema under controlled conditions.

### Latency and Throughput Comparison

| Endpoint / Operation | Previous Architecture (Dynamic Inference) | New Architecture (Persistent Storage + Serving) | Improvement / Impact |
| :--- | :--- | :--- | :--- |
| **Nationwide Summary Cold** (`/api/states/summary`) | **39,424.67 ms** (39.42 s) | **11.99 ms** (DB: 1.28 ms across 2 queries) | **3,287x faster** cold response |
| **Nationwide Summary Warm** (L1 Cache) | 41.74 ms | **8.28 ms** | **5.0x faster** warm response |
| **State Cold** (`/api/predict/state/HR`) | **5,928.77 ms** (5.93 s) | **25.10 ms** (DB: 2.26 ms across 2 queries) | **236x faster** cold response |
| **State Warm** (L1 Cache) | ~10.00 ms | **8.56 ms** | Consistent sub-10ms response |
| **District Cold** (`/api/predict/climate-12m/HR-Kaithal`) | ~150.00 ms | **48.99 ms** (DB: 2.26 ms across 3 queries) | **3.1x faster** cold response |
| **District Warm** (L1 Cache) | ~25.00 ms | **6.63 ms** | Sub-7ms response |
| **States Page Sequence** (Registry + Concurrent State & Summary) | **40,821.64 ms** (40.82 s) | **32.27 ms** | **1,265x faster** page load sequence |
| **Background Precomputation Duration** | N/A (Blocked user requests) | **43.56 s** (725 districts, 36 states) | Shifted entirely out of user path |
| **Model Inferences During Normal API Reads** | 426 district XGBoost calls | **0** (strictly zero inference calls) | Decoupled inference from serving |

---

## 3. Database Schema & Migration Details

Migration `db/migrations/004_xgboost_forecast_storage.sql` creates a versioned, relational forecast schema:

### 1. `forecast_generations`
Tracks each precomputation run's lifecycle and verified input identities.
- `generation_id` (UUID, Primary Key): Deterministic UUIDv5 derived from the generation signature and as-of date.
- `status` (`VARCHAR(32)`): `'building'`, `'validated'`, `'published'`, `'superseded'`, `'failed'`.
- `as_of` (`DATE`), `forecast_origin` (`DATE`), `horizon_months` (`INT`).
- Provenance hashes: `model_id`, `model_version`, `model_sha256`, `model_card_sha256`, `feature_generation_id`, `feature_data_sha256`, `district_registry_hash`, `district_crosswalk_hash`, `state_registry_hash`, `config_hash`.
- `generation_signature` (`CHAR(64)`): SHA-256 digest of all model and feature inputs.
- Coverage summary: `districts_total`, `districts_forecast`, `districts_insufficient`, `districts_unavailable`, `states_total`, `states_available`, `states_insufficient`.
- Timestamps: `started_at`, `completed_at`, `published_at`, `superseded_at`.

### 2. `district_forecast_records`
Stores district-level forecasts and status:
- `generation_id` (UUID, Foreign Key)
- `district_id` (`VARCHAR(64)`): Canonical district ID (e.g., `'HR-Kaithal'`).
- `as_of` (`DATE`), `forecast_origin` (`DATE`).
- `status` (`VARCHAR(32)`): `'forecast'` or `'insufficient_data'`.
- `estimated_current_gwl` (`NUMERIC(8,4)`): Estimated current depth in m_bgl (never zero for missing data).
- `p12_predicted_gwl`, `p12_delta_m`: M+12 depth and delta for quick querying.
- `payload_json` (`JSONB`): Complete structured response payload.
- **Unique Constraint:** `(generation_id, district_id)`.
- **Indexes:** `idx_district_fc_lookup ON (district_id, as_of, status)`.

### 3. `district_forecast_horizons`
Relational normalization of each monthly horizon (M+1 through M+12):
- `(generation_id, district_id, horizon)` (Primary Key).
- `target_date` (`DATE`), `target_month` (`VARCHAR(7)`).
- `predicted_gwl` (`NUMERIC(8,4)`), `delta_from_current_m` (`NUMERIC(8,4)`).
- Weather covariates: `rainfall_mm`, `temperature_c`, `evapotranspiration_mm`.

### 4. `state_forecast_records`
Stores state-level forecasts aggregated over fixed eligible district panels:
- `(generation_id, state_id)` (Primary Key).
- `panel_id` (`CHAR(64)`): Reproducible panel membership hash.
- `total_districts_in_state` (`INT`), `contributing_districts_count` (`INT`), `district_coverage_pct` (`NUMERIC(5,2)`).
- `contributing_district_ids` (`JSONB`), `excluded_districts` (`JSONB`).
- `estimated_current_gwl_m_bgl`, `last_observed_date`, `last_observed_gwl_m_bgl`.
- `p12_predicted_gwl_m_bgl`, `p12_delta_from_current_m`.
- `payload_json` (`JSONB`): Full structured state payload.

### 5. `state_forecast_horizons`
Individual monthly state projections (M+1 through M+12):
- `(generation_id, state_id, horizon)` (Primary Key).
- `predicted_gwl_m_bgl`, `delta_from_current_m`.

### 6. `nationwide_summary_records`
Precomputed comparative summary for all 36 states and territories:
- `(generation_id)` (Primary Key).
- `as_of` (`DATE`), `total_states_count`, `available_states_count`, `insufficient_data_states_count`.
- `payload_json` (`JSONB`): Ready-to-serve JSON payload.

---

## 4. Precomputation CLI & Usage

Module: `scripts/precompute_forecasts.py`

### Standard Usage
```bash
# Precompute and atomically publish 12-month forecasts for default as-of date (latest complete)
python -m scripts.precompute_forecasts --horizon 12

# Precompute for explicit as-of date with custom batch size
python -m scripts.precompute_forecasts --horizon 12 --as-of 2026-10-25 --batch-size 50

# Validation / Dry-Run mode (verifies models, runs batch inference, skips database writes)
python -m scripts.precompute_forecasts --horizon 12 --dry-run

# Force recomputation even if an active generation already exists
python -m scripts.precompute_forecasts --horizon 12 --force
```

### Precomputation Execution Profile
- **Total Runtime:** 43.56 seconds.
- **Districts Processed:** 725 canonical districts (426 successfully forecast with 12 horizons, 299 insufficient data).
- **States Processed:** 36 states and Union Territories (16 available meeting >=50% coverage & >=2 districts, 20 insufficient data).
- **Batch Size:** 50 districts per batch to prevent memory spikes.
- **Idempotency:** When rerun with `--force=False`, detects identical model and feature signatures and exits cleanly in milliseconds without duplicating database rows.

---

## 5. API Response Contracts and Fast Serving

### Endpoints Updated
1. `GET /api/states/summary?horizon=12&as_of=YYYY-MM-DD`
2. `GET /api/predict/state/<state_id>?horizon=12&as_of=YYYY-MM-DD`
3. `GET /api/predict/climate-12m/<district_id>?months=12&as_of=YYYY-MM-DD`

### Serving Workflow
1. Request arrives at Flask endpoint.
2. `forecast_storage.get_active_generation(as_of)` verifies the active generation against the current system input signature.
3. Looks up the deserialized payload from process L1 cache (`_SUMMARY_L1_CACHE`, `_STATE_L1_CACHE`, `_DISTRICT_L1_CACHE`).
4. On L1 cache miss, queries indexed PostgreSQL records (`state_forecast_records`, `district_forecast_records`, `nationwide_summary_records`).
5. Returns defensive copy of structured payload with identical contracts, keys, and values expected by the frontend.
6. **No inference fallback:** If precomputed forecasts are missing or stale, returns HTTP 503 `model_unavailable` with structured diagnostics explaining the reason and providing the CLI command required to precompute.

---

## 6. Regression Testing and Verification Outcomes

Comprehensive test suites were executed across the entire stack:

### 1. Forecast Storage Suite (`tests/test_forecast_storage.py`)
- `test_migration_004_creates_all_tables_and_indexes`: **PASSED**
- `test_precomputation_and_atomic_publication`: **PASSED**
- `test_idempotent_repeated_precomputation`: **PASSED**
- `test_unique_keys_and_duplicate_prevention`: **PASSED**
- `test_exact_equivalence_computed_vs_persisted`: **PASSED**
- `test_invalidation_when_model_or_feature_signature_changes`: **PASSED**
- `test_concurrent_reads_return_independent_defensive_copies`: **PASSED**
- `test_api_serves_persisted_forecasts_and_prevents_inference`: **PASSED**
- `test_api_returns_503_when_generation_missing_and_sync_disabled`: **PASSED**
- `test_six_month_district_api_preserved`: **PASSED**
- **Result: 10 / 10 passed in isolated PostgreSQL schema.**

### 2. Core Climate & Forecasting Suite
- `pytest tests/test_state_forecasting.py tests/test_forecast_storage.py`: **44 / 44 passed**
- `pytest tests/test_forecast_cache.py tests/test_weather_performance.py tests/test_climate_forecast_12m.py tests/test_climate_inputs.py tests/test_climate_forecast.py`: **211 / 211 passed**
- `pytest tests/test_research_forecast_api.py`: **57 / 57 passed**

### 3. Frontend Dashboard Tests & Build
- `npm test -- --run` in `dashboard`: **146 / 146 passed**
- `npm run lint` (`oxlint`): **0 errors, 0 warnings** across 49 files
- `npm run build` (`vite build`): **Built successfully in 338ms**

---

## 7. Operational Workflow for Operators

When updating models or refreshing data:
1. **Refresh Raw Data:** Ingest updated IMD weather or CGWB groundwater observations via approved pipeline.
2. **Export Features:** Run feature engineering pipeline to generate updated `features.csv` and verified `manifest.json`.
3. **Execute Precomputation:**
   ```bash
   python -m scripts.precompute_forecasts --horizon 12
   ```
4. **Inspect Precomputation Output:** Verify that district and state coverage matches expectations (e.g., 426 districts, 16 states).
5. **Atomic Switch:** Upon successful precomputation, the new generation is marked `published` and the old generation is marked `superseded` in a single transaction. API workers immediately begin serving the new generation without restart.
6. **Rollback (if needed):**
   ```sql
   UPDATE forecast_generations SET status = 'superseded' WHERE generation_id = '<faulty-gen-id>';
   UPDATE forecast_generations SET status = 'published' WHERE generation_id = '<previous-gen-id>';
   ```

---

## 8. Scientific and Methodological Integrity

1. **Experimental Status Unchanged:** All forecasts remain experimental research tools. Faster serving and database persistence do not alter the statistical characteristics, model weights, or predictive accuracy of the XGBoost models.
2. **State Mean Clarification:** State predictions represent an **equal-weight covered-district mean depth in metres below ground level (m bgl)** across a fixed eligible district panel (minimum 50% coverage and at least 2 contributing districts). They do not represent total groundwater volume or an area-weighted state aquifer measurement.
3. **Zero Imputation Safeguard:** Missing forecasts are never zero-filled or fabricated. States failing coverage thresholds abstain with structured `insufficient_data` status.
