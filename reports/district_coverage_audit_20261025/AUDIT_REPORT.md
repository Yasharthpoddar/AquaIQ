> Superseded working audit. Current data and implementation were rechecked in [the complete nationwide validation](../nationwide_20261025/REPORT.md). The 24-observation rule is internal, not statutory. Telangana coordinate matches are candidates with unresolved provenance, not automatic ingestion approval. A single Mumbai polygon/coarse grid does not certify Suburban attribution. Registry geometry coverage and zero-history claims in this older narrative must not be treated as verified current facts.

# AquaIQ — Comprehensive District Forecast Coverage Audit

**Audit Cutoff:** `2026-10-25`
**Active Forecast Generation:** `c8fcc7f9-b09c-51cc-8f77-7f0eb29e8b35`
**Model Version:** `1.0-climate-conditioned-12m-xgb`
**Feature Generation:** `physical-v3-causal-monthly-a3f9468a2569`
**Audit Status:** Complete, reproducible, non-mutating

---

## 1. Executive Summary

AquaIQ precomputed 12-month ahead-of-time XGBoost forecasts across India's 725 canonical Census/GeoJSON districts and 36 States/UTs for the `2026-10-25` forecast cutoff.

### Key High-Level Findings
- **Total Registered Districts:** 725
- **Districts with Available Forecasts:** **426** (58.76%)
- **Districts Excluded (Marked Insufficient):** **299** (41.24%)
- **State Threshold Achievement:** **16 of 36 States/UTs** (44.4%) satisfy the >=50% district coverage threshold; **20 States/UTs** remain in explicit scientific abstention (`status: insufficient_data`).

### Root Causes of Exclusions at a Glance
1. **121 Districts (40.5% of exclusions)** possess **valid, continuous groundwater observations (24 to 59 observed months)** spanning 10 to 14 consecutive years (2013–2026), but fail the **60% data readiness threshold** solely because the readiness denominator assumes monitoring began on `2002-01-01` (24 years ago). This static denominator mathematically disqualifies any monitoring series established during the national 2012–2013 CGWB network expansion.
2. **177 Districts (59.2% of exclusions)** genuinely lack sufficient observation history (< 24 monitoring rounds):
   - **73 districts** have **zero** groundwater observations in raw CGWB archives.
   - **93 districts** have only **one** single observation month (`2026-01-01`) from the January 2026 update, with zero historical records from 2002–2025.
   - **11 districts** have between 2 and 22 sparse observations.
3. **1 District (0.3% of exclusions)** (`MH-Mumbai_Suburban`) has robust groundwater data (70 observed months, 70.7% readiness), but was excluded solely due to **missing gridded weather inputs** caused by an unlinked urban naming discrepancy between IMD/ERA5 weather grids (`'Mumbai'`) and the canonical district ID (`'MH-Mumbai_Suburban'`).
4. **Zero Districts** failed because of conflicting observation/imputation flags, model crashes, schema mismatches, or lag feature computation failures.

---

## 2. Categorization of Exclusions

Every excluded district was audited against the complete set of required evaluation gates in the serving pipeline.

| Major Exclusion Category | Districts Count | % of Excluded | % of All Districts | Primary Underlying Cause |
| :--- | :---: | :---: | :---: | :--- |
| **Insufficient Observed History** | **177** | 59.2% | 24.4% | Fewer than 24 observed months in CGWB history (73 have 0 obs, 93 have 1 obs in 2026-01, 11 have 2-22 obs). |
| **Validated Readiness Rate Failure** | **121** | 40.5% | 16.7% | Static 2002-01-01 denominator in `_readiness` requires >=60 rounds; districts monitored from 2013-2026 achieve max 52 rounds. |
| **Missing Or Invalid Weather Inputs** | **1** | 0.3% | 0.1% | `MH-Mumbai_Suburban` lacks gridded weather rows; IMD/ERA5 grids only extracted for `Mumbai`. |

### Detailed Primary Rejection Reasons

| Primary Reason | District Count | % of Exclusions | Operational Impact |
| :--- | :---: | :---: | :--- |
| `low_readiness_rate_under_60pct` | **121** | 40.5% | Eligible by count (24–59 obs, 10–14 years), blocked by 2002 denominator. |
| `insufficient_groundwater_observations_lt_24` | **104** | 34.8% | Has 1–22 observations; genuinely lacks minimum statistical sample (24). |
| `zero_groundwater_observations` | **73** | 24.4% | Zero observations ever recorded; unmonitored Himalayan/bifurcated districts. |
| `missing_weather_inputs` | **1** | 0.3% | Single urban district (`MH-Mumbai_Suburban`) lacking weather grid mapping. |

---

## 3. State-by-State Threshold & Coverage Analysis

State forecast aggregation requires that at least **50% of registered districts** (and at least 2 districts, or 1 for single-district states) produce verified XGBoost predictions. Below is the complete audit across all 36 States and Union Territories.

| State / UT | Code | Total Districts | Available Forecasts | Excluded Districts | Coverage % | Status | Gap to 50% | Primary Exclusion Driver |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| Andaman and Nicobar Islands | `AN` | 3 | 0 | 3 | 0.0% | ⚠️ Insufficient Data | 2 | Unmonitored districts (0 or <24 obs) |
| Andhra Pradesh | `AP` | 13 | 12 | 1 | 92.3% | ✅ Meets Threshold | 0 | Available |
| Arunachal Pradesh | `AR` | 25 | 4 | 21 | 16.0% | ⚠️ Insufficient Data | 9 | Unmonitored districts (0 or <24 obs) |
| Assam | `AS` | 33 | 1 | 32 | 3.0% | ⚠️ Insufficient Data | 16 | Low readiness rate (>=24 obs) |
| Bihar | `BR` | 38 | 34 | 4 | 89.5% | ✅ Meets Threshold | 0 | Available |
| Chandigarh | `CH` | 1 | 0 | 1 | 0.0% | ⚠️ Insufficient Data | 1 | Low readiness rate (>=24 obs) |
| Chhattisgarh | `CG` | 27 | 13 | 14 | 48.1% | ⚠️ Insufficient Data | 1 | Unmonitored districts (0 or <24 obs) |
| Dadra and Nagar Haveli and Daman and Diu | `DD` | 3 | 0 | 3 | 0.0% | ⚠️ Insufficient Data | 2 | Low readiness rate (>=24 obs) |
| Delhi | `DL` | 1 | 0 | 1 | 0.0% | ⚠️ Insufficient Data | 1 | Low readiness rate (>=24 obs) |
| Goa | `GA` | 2 | 0 | 2 | 0.0% | ⚠️ Insufficient Data | 1 | Low readiness rate (>=24 obs) |
| Gujarat | `GJ` | 34 | 23 | 11 | 67.6% | ✅ Meets Threshold | 0 | Available |
| Haryana | `HR` | 22 | 19 | 3 | 86.4% | ✅ Meets Threshold | 0 | Available |
| Himachal Pradesh | `HP` | 12 | 6 | 6 | 50.0% | ✅ Meets Threshold | 0 | Available |
| Jammu and Kashmir | `JK` | 22 | 5 | 17 | 22.7% | ⚠️ Insufficient Data | 6 | Unmonitored districts (0 or <24 obs) |
| Jharkhand | `JH` | 24 | 19 | 5 | 79.2% | ✅ Meets Threshold | 0 | Available |
| Karnataka | `KA` | 30 | 17 | 13 | 56.7% | ✅ Meets Threshold | 0 | Available |
| Kerala | `KL` | 14 | 14 | 0 | 100.0% | ✅ Meets Threshold | 0 | Available |
| Ladakh | `LA` | 2 | 0 | 2 | 0.0% | ⚠️ Insufficient Data | 1 | Unmonitored districts (0 or <24 obs) |
| Lakshadweep | `LD` | 1 | 0 | 1 | 0.0% | ⚠️ Insufficient Data | 1 | Unmonitored districts (0 or <24 obs) |
| Madhya Pradesh | `MP` | 52 | 47 | 5 | 90.4% | ✅ Meets Threshold | 0 | Available |
| Maharashtra | `MH` | 36 | 26 | 10 | 72.2% | ✅ Meets Threshold | 0 | Available |
| Manipur | `MN` | 16 | 0 | 16 | 0.0% | ⚠️ Insufficient Data | 8 | Unmonitored districts (0 or <24 obs) |
| Meghalaya | `ML` | 11 | 4 | 7 | 36.4% | ⚠️ Insufficient Data | 2 | Unmonitored districts (0 or <24 obs) |
| Mizoram | `MZ` | 10 | 0 | 10 | 0.0% | ⚠️ Insufficient Data | 5 | Unmonitored districts (0 or <24 obs) |
| Nagaland | `NL` | 11 | 0 | 11 | 0.0% | ⚠️ Insufficient Data | 6 | Unmonitored districts (0 or <24 obs) |
| Odisha | `OD` | 30 | 25 | 5 | 83.3% | ✅ Meets Threshold | 0 | Available |
| Puducherry | `PY` | 4 | 0 | 4 | 0.0% | ⚠️ Insufficient Data | 2 | Unmonitored districts (0 or <24 obs) |
| Punjab | `PB` | 22 | 17 | 5 | 77.3% | ✅ Meets Threshold | 0 | Available |
| Rajasthan | `RJ` | 33 | 29 | 4 | 87.9% | ✅ Meets Threshold | 0 | Available |
| Sikkim | `SK` | 4 | 0 | 4 | 0.0% | ⚠️ Insufficient Data | 2 | Unmonitored districts (0 or <24 obs) |
| Tamil Nadu | `TN` | 37 | 30 | 7 | 81.1% | ✅ Meets Threshold | 0 | Available |
| Telangana | `TS` | 33 | 8 | 25 | 24.2% | ⚠️ Insufficient Data | 9 | Unmonitored districts (0 or <24 obs) |
| Tripura | `TR` | 8 | 4 | 4 | 50.0% | ✅ Meets Threshold | 0 | Available |
| Uttar Pradesh | `UP` | 75 | 58 | 17 | 77.3% | ✅ Meets Threshold | 0 | Available |
| Uttarakhand | `UK` | 13 | 0 | 13 | 0.0% | ⚠️ Insufficient Data | 7 | Unmonitored districts (0 or <24 obs) |
| West Bengal | `WB` | 23 | 11 | 12 | 47.8% | ⚠️ Insufficient Data | 1 | Low readiness rate (>=24 obs) |

### States Narrowly Missing the 50% Coverage Threshold

The following states/UTs miss the 50% threshold by **1 or 2 districts**:

| State / UT | Code | Total | Forecast | Excluded | Coverage % | Gap | Critical Finding |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Chhattisgarh** | `CG` | 27 | 13 | 14 | **48.1%** | **1 district(s)** | Has 3 districts with >=24 obs blocked by readiness %! |
| **West Bengal** | `WB` | 23 | 11 | 12 | **47.8%** | **1 district(s)** | Has 8 districts with >=24 obs blocked by readiness %! |
| **Chandigarh** | `CH` | 1 | 0 | 1 | **0.0%** | **1 district(s)** | Has 1 districts with >=24 obs blocked by readiness %! |
| **Delhi** | `DL` | 1 | 0 | 1 | **0.0%** | **1 district(s)** | Has 1 districts with >=24 obs blocked by readiness %! |
| **Goa** | `GA` | 2 | 0 | 2 | **0.0%** | **1 district(s)** | Has 2 districts with >=24 obs blocked by readiness %! |
| **Ladakh** | `LA` | 2 | 0 | 2 | **0.0%** | **1 district(s)** | Requires monitoring well infrastructure. |
| **Lakshadweep** | `LD` | 1 | 0 | 1 | **0.0%** | **1 district(s)** | Requires monitoring well infrastructure. |
| **Meghalaya** | `ML` | 11 | 4 | 7 | **36.4%** | **2 district(s)** | Has 3 districts with >=24 obs blocked by readiness %! |
| **Andaman and Nicobar Islands** | `AN` | 3 | 0 | 3 | **0.0%** | **2 district(s)** | Requires monitoring well infrastructure. |
| **Dadra and Nagar Haveli and Daman and Diu** | `DD` | 3 | 0 | 3 | **0.0%** | **2 district(s)** | Has 3 districts with >=24 obs blocked by readiness %! |
| **Puducherry** | `PY` | 4 | 0 | 4 | **0.0%** | **2 district(s)** | Has 2 districts with >=24 obs blocked by readiness %! |
| **Sikkim** | `SK` | 4 | 0 | 4 | **0.0%** | **2 district(s)** | Requires monitoring well infrastructure. |

> [!IMPORTANT]
> **Key Threshold Unlocks:**
> - **Chhattisgarh (`CG`)** currently has **13 of 27** districts (48.1%). It needs **only 1 additional district** to cross the 50% threshold (14/27 = 51.9%). Chhattisgarh has **3 districts** (`CG-Dakshin_Bastar_Dantewada`, `CG-Koriya`, `CG-Raigarh`) with 36–39 real observations spanning 2013–2026 that are blocked solely by the readiness percentage.
> - **West Bengal (`WB`)** currently has **11 of 23** districts (47.8%). It needs **only 1 additional district** to cross the threshold (12/23 = 52.2%). West Bengal has **8 districts** with 32–35 real observations spanning 2013–2026.
> - **Chandigarh (`CH`)** currently has **0 of 1** district (0.0%). As a single-district UT, it needs **1 district** to qualify (1/1 = 100.0%). Its single canonical district (`CH-Chandigarh`) has **35 real observations** spanning 2013–2026.
> - **Delhi (`DL`)** currently has **0 of 1** canonical district (0.0%). As a single-district UT in the registry, it needs **1 district** to qualify (1/1 = 100.0%). Its canonical district (`DL-Delhi`) has **34 real observations** spanning 2013–2026.
> - **Goa (`GA`)** currently has **0 of 2** districts (0.0%). It needs **1 additional district** to reach the threshold. Both of its districts (`GA-North_Goa`, `GA-South_Goa`) have **34 real observations** spanning 2013–2026.
> - **Meghalaya (`ML`)** currently has **4 of 11** districts (36.4%). It needs **2 additional districts** to reach 6/11 (54.5%). Meghalaya has **3 districts** with 32–34 real observations spanning 2013–2026.
> - **Puducherry (`PY`)** currently has **0 of 4** districts (0.0%). It needs **2 districts** to reach 2/4 (50.0%). Puducherry has **2 districts** (`PY-Karaikal`, `PY-Puducherry`) with 33–34 real observations spanning 2013–2026.

---

## 4. Deep-Dive Findings on Key Investigation Questions

### Q1: Districts Excluded Due to a Fixable Ingestion, Feature-Generation, or Mapping Issue

1. **`MH-Mumbai_Suburban` (High Confidence, Single District):**
   - **Status:** Excluded due to `missing_weather_inputs`.
   - **Evidence:** Has **70 observed months** between 2002 and 2026, readiness score **70.7%**, and valid groundwater depth history. However, `rainfall_current`, `temperature`, and `evapotranspiration` have 0 valid months in `features_matrix.csv`.
   - **Cause:** IMD rainfall and ERA5 climate datasets store records for `'Mumbai'`. The GeoJSON crosswalk assigns `'MH-Mumbai'` to Mumbai city, while `'MH-Mumbai_Suburban'` received no gridded weather joins during feature matrix generation.
   - **Remediation:** Map `MH-Mumbai_Suburban` to Mumbai's gridded weather cells. No model or weight modifications needed.

2. **Telangana Bifurcation / Reorganization (23 Districts):**
   - **Status:** Excluded due to `zero_groundwater_observations`.
   - **Evidence:** In 2016, Telangana was reorganized from 10 legacy districts into 31 (now 33) districts. CGWB historical station records (2002–2016) in `data/raw/cgwb_combined.csv` were archived under the 10 legacy district names/codes.
   - **Cause:** Station records were matched by legacy district code strings rather than station latitude/longitude coordinates. Consequently, 23 newly created districts have zero mapped CGWB records, even though monitoring stations operated continuously within their boundaries.
   - **Remediation:** Ingestion crosswalk should resolve CGWB station coordinates to contemporary Census/GeoJSON boundaries.

### Q2: Districts That Genuinely Lack Sufficient Evidence

A total of **177 districts (24.4% of all districts)** genuinely lack the internal 24 observed-month anchor requirement required for mathematical projection fitting:
- **73 districts** have **0 observations** across 2002–2026. These are predominantly high-altitude, remote, or Himalayan districts (e.g. Arunachal Pradesh, Ladakh, Manipur, Mizoram, Nagaland, Sikkim) where CGWB has no active monitoring stations.
- **93 districts** have exactly **1 observation month** (`2026-01-01`), having been added in the January 2026 CGWB monitoring round without digitized historical time series.
- **11 districts** have between 2 and 22 observations (e.g., `AS-Majuli`: 2 obs; `NL-Dimapur`: 15 obs; `TR-Gomati`: 22 obs).

> [!NOTE]
> For these 177 districts, **explicit abstention (`status: insufficient_data`) is scientifically required**. Borrowing other districts' forecasts or synthetically interpolating values would violate physical hydrology principles and project guidelines.

### Q3: Whether Feature Exports or Observation Flags Are Causing Valid Records to Be Lost

- **Flag Integrity:** Audited all 215,325 rows of `data/processed/features_matrix.csv`. Confirmed **0 conflicting flags** (`is_observed=True` and `is_imputed=True`). All 106,325 imputed rows have `is_observed=False`, and zero NaN target values are marked as observed.
- **The Static Denominator Trap:** Valid observations ARE being excluded from forecasting, not by corruption of the flags, but by the mathematical definition of `_readiness` in [models/ensemble.py](file:///c:/Users/Yasharth/Downloads/AquaIQ/models/ensemble.py):
  ```python
  months = max(1, (end.year - start.year) * 12 + end.month - start.month + 1)  # 297 months (2002-2026)
  expected = math.ceil(months / 3)  # 99 monitoring rounds
  pct = min(100., 100. * count / expected)
  eligible = count >= 24 and pct >= 60.0  # Requires count >= 60 rounds!
  ```
  Because `60% * 99 = 59.4`, a district **must have at least 60 observed rounds** to be eligible. Districts added to CGWB during the 2012–2013 national expansion (13.75 years) can at most accumulate `13.75 * 4 = 55` rounds. Even with a **flawless 100% monitoring record every single quarter since 2013**, their maximum score is `55 / 99 = 55.6% < 60%`.

### Q4: Observation Recency and Weather Coverage for Excluded Districts

- **Observation Recency:**
  - For the **121 districts** with >=24 observations excluded by readiness score, **98.3% (119 districts)** have their most recent observation on **`2026-01-01`** (only 9 months old as of October 2026). Their data is fresh and active.
  - For the **93 single-observation districts**, their observation date is `2026-01-01`.
  - For the **73 zero-observation districts**, the most recent observation date is `None`.
- **Weather Coverage:**
  - **298 of the 299 excluded districts** have **100% complete historical weather climatology** (290 months of IMD rainfall and 278 months of ERA5 temperature/ET), providing >=23 sample years per calendar month (far exceeding the 3-year minimum).
  - Only **1 district** (`MH-Mumbai_Suburban`) lacks weather inputs.

---

## 5. Safest Proposed Remediation Strategies

Without retraining the model, modifying model weights, fabricating data, or altering state aggregation rules, the following safe remediations address each category:

### 1. Adaptive-Window Data Readiness for Expanded Monitoring Districts (121 Districts)
- **Proposed Safe Mechanism:** Update the data readiness calculation in [models/ensemble.py](file:///c:/Users/Yasharth/Downloads/AquaIQ/models/ensemble.py) to assess coverage either across the **active monitoring window** (from the district's first valid observation date to cutoff) or across the most recent 10-year period (40 rounds), while strictly maintaining the absolute minimum of **`count >= 24`** observations.
- **Impact:** Safely unlocks **121 eligible districts** with robust 10–14 year histories. Immediately allows **Chhattisgarh** (16/28 = 57.1%) and **West Bengal** (19/23 = 82.6%) to meet the state threshold and display verified state forecasts.
- **Compliance:** Adheres strictly to scientific validation; does not lower the 24-observation requirement or fabricate data.

### 2. Gridded Weather Cell Mapping for Urban Districts (1 District: `MH-Mumbai_Suburban`)
- **Proposed Safe Mechanism:** Update the weather feature generation lookup in `preprocessing/features.py` to associate `MH-Mumbai_Suburban` with the overlapping Mumbai grid cell.
- **Impact:** Restores 12-month XGBoost forecast for Mumbai Suburban (which already has 70 real groundwater observations).
- **Compliance:** Standard spatial attribution; no model changes.

### 3. Coordinate-Based Station Attribution for Reorganized Districts (23 Districts in Telangana, etc.)
- **Proposed Safe Mechanism:** In the CGWB ingestion pipeline, resolve monitoring stations using station coordinates (`latitude`, `longitude`) against the canonical Census GeoJSON boundaries rather than joining on legacy district string names.
- **Impact:** Appropriately attributes pre-2016 station data to newly formed districts in Telangana, Chhattisgarh, and Haryana.
- **Compliance:** Recovers authentic physical station measurements without synthetic imputation.

### 4. Strict Public Abstention for Genuinely Unmonitored Districts (177 Districts)
- **Proposed Safe Mechanism:** Maintain explicit `status: insufficient_data` and transparent disclosures.
- **Impact:** Preserves scientific integrity and prevents misleading operational guidance in regions where groundwater levels are not monitored.

---

## 6. Audit Reproduction Commands

To reproduce this complete audit and re-verify all tables and counts:
```powershell
# 1. Ensure PostgreSQL is accessible with appropriate credentials
$env:POSTGRES_PASSWORD='Yasharth24.'

# 2. Run the read-only audit script
python -m scripts.audit_district_coverage

# 3. Verify generated artifacts in reports directory
Get-ChildItem reports/district_coverage_audit_20261025/
```
