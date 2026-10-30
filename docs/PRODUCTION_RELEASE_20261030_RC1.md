# AquaIQ Production Release Runbook & Audit Report: 2026.10.30-production-rc1

**Status:** VERIFIED CANDIDATE (APPROVAL GATE ACTIVE)  
**Target Release Identifier:** `2026.10.30-production-rc1`  
**Candidate Directory:** `models/artifacts/state_median_releases/20261030-production-rc1`  
**Active Production Release:** `2026.10.29-r1` (`eaabeba7-a554-59a6-9110-726221e63cb2`)  

---

## 1. Release Manifest and Checksums

| Asset | Path | SHA-256 Checksum |
|---|---|---|
| **Release Manifest** | `models/artifacts/state_median_releases/20261030-production-rc1/release_manifest.json` | `1f351be60960c9d0cf62ddfe5cad5b71180e9e4891b236bbaa02792c9160ea24` |
| **Release Model Card** | `models/artifacts/state_median_releases/20261030-production-rc1/release_model_card.json` | `c799f3a024a08ea23457d1e8e6431f954f18b20db9c666fe59a4511da7b1fa5e` |
| **XGBoost Algorithm** | `models/state_median_forecast.py` | `e90d1dd62443579cced8d51b4a263c2f115c41eb9cacc7c91f4094f6265cd9f2` |
| **Coverage Policy** | `models/state_median_policy.py` | `86b0845b6c0747f3556ed9c88501847f929a451ad29d537acfe9c0e15c0f5bca` |
| **Source Features CSV** | `data/processed/enrichment/final_release_20261026_v3/features_matrix.csv` | `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042` |
| **Frozen District Model** | `models/artifacts/climate_12m_bundles/20261024T152950484968Z-6369f3e3ec/model.json` | `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03` |

---

## 2. Immutable Predecessors

- **Release r1:** `models/artifacts/state_median_releases/20261029-r1/release_manifest.json`  
  Manifest SHA-256: `4f49c06c40fe96983219c611c483dbcfc87d40937a513fb03023d0fc8851e512` (Unchanged, 17 XGBoost states)
- **Release r2:** `models/artifacts/state_median_releases/20261029-r2/release_manifest.json`  
  Manifest SHA-256: `8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3` (Unchanged, format_version=2)
- **Release r3:** `models/artifacts/state_median_releases/20261030-r3/release_manifest.json`  
  Manifest SHA-256: `c126a622ea86f48eab20830b0d19dfca1b81d95388fe36c8b16a3063dcc722a8` (Unchanged, candidate release)

---

## 3. Policy and National Coverage Summary

- **Total States / UTs Audited:** 36
- **Forecastable States:** 34
- **Unavailable States:** 2 (Ladakh `LA`, Lakshadweep `LD` — 0 recorded observations, no data fabricated)
- **Total Forecast Months:** 408 (12 months per forecastable state, Nov 2026 – Oct 2027)
- **XGBoost States (17):** AP, BR, CG, GJ, HP, HR, JH, KA, KL, MH, MP, OD, PB, RJ, TN, TR, UP
- **Persistence Fallback States (17):** AN, AR, AS, CH, DD, DL, GA, JK, ML, MN, MZ, NL, PY, SK, TS, UK, WB

### Persistence Disclosures
- State median represents the median of reporting district-month means, not total groundwater volume.
- Persistence fallback repeats the latest genuine state median across 12 forecast months.
- Stale references ($>12$ months old) are explicitly flagged (`reference_is_stale: true`).
- Sikkim (`SK`) has 1 observation month (`2025-01-01`) and is marked sparse and stale.
- Low-coverage months ($<50\%$ reporting districts) are disclosed.

---

## 4. District Forecasting Protection

- The production district 12-month model artifact remains `models/artifacts/climate_12m_bundles/20261024T152950484968Z-6369f3e3ec/model.json` with verified SHA-256 `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`.
- District prediction endpoints (`/api/v2/predict/district/<id>`), scenario endpoints, and Home page aggregation are unchanged.

---

## 5. Verification Test Evidence

- **Frontend Tests:** 194 / 194 PASSED (`node --test tests/*.test.js`)
- **Frontend Production Build:** Vite v8.3.3 built clean (`npm run build`)
- **Backend Tests:** 1,943 / 1,943 PASSED (1,936 core suite + 14 comprehensive audit tests)
- **Isolated Database Test:** Staging, publication, 36-state serving, invalid code rejection, and two-release rollback verified in isolated schema `aquaiq_test_production_rc1_test`. Production active pointer remained intact throughout.

---

## 6. Gated Production Promotion Runbook

> [!CAUTION]
> The commands below must ONLY be executed after explicit stakeholder approval. Do not execute automatically.

### Promotion Step 1: Stage Release in Production Database
```bash
.\venv\Scripts\python.exe -m scripts.release_state_median stage \
  --release-dir models/artifacts/state_median_releases/20261030-production-rc1 \
  --input scratch/production_rc1_payloads.json
```
*Note the returned `release_id` UUID.*

### Promotion Step 2: Publish Release (Atomic Pointer Switch)
```bash
.\venv\Scripts\python.exe -m scripts.release_state_median publish \
  --release-id <NEW_RELEASE_ID> \
  --expected-active eaabeba7-a554-59a6-9110-726221e63cb2 \
  --reason "Approved promotion of 2026.10.30-production-rc1 to production"
```

### Rollback Procedure (If Needed)
```bash
.\venv\Scripts\python.exe -m scripts.release_state_median rollback \
  --release-id eaabeba7-a554-59a6-9110-726221e63cb2 \
  --expected-active <NEW_RELEASE_ID> \
  --reason "Emergency rollback to 2026.10.29-r1"
```
