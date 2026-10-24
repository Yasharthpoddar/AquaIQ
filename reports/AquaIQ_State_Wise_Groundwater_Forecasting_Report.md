# AquaIQ State-Wise Groundwater Forecasting Pipeline Report

**Date:** 24 October 2026  
**Repository:** [https://github.com/Yasharthpoddar/AquaIQ](https://github.com/Yasharthpoddar/AquaIQ)  
**Branch:** `feature/state-wise-forecasting`  
**Model Version:** `1.0-state-timeseries-projection`  
**Product Name:** `state_groundwater_12m_forecast`  
**Status:** Experimental State Outlook (Scientifically Evaluated)

---

## 1. Executive Summary & Objective

The objective was to implement a state-wise groundwater forecasting feature in AquaIQ, enabling users to:
1. View groundwater conditions and 12-month projections for all Indian States and Union Territories (m bgl).
2. Compare states nationwide by current water table depth and expected 12-month depletion change.
3. Drill down seamlessly from state-level overviews into individual constituent districts.
4. Strictly preserve the existing district-level 6-month model (`/api/predict/<district_id>`) and experimental 12-month climate model (`/api/predict/climate-12m/<district_id>`).

The state forecasting pipeline is explicitly labeled as **experimental**. It operates on auditable, strictly non-imputed district aggregations, respects Central Ground Water Board (CGWB) periodic monitoring realities, provides matched chronological baseline comparisons (Persistence and Seasonal-Naive), and exposes rich frontend visualizations with an interactive India state choropleth map.

---

## 2. Data Audit & Mapping Source

### 2.1 District-to-State Representation
- **Crosswalk & Identification:** Audited `data_ingestion/district_crosswalk.csv` and `data/processed/features_matrix.csv` (215,325 rows). All 725 canonical districts across India follow the verified standard prefix `{STATE_ID}-{District_Name}` (e.g. `UP-Deoria`, `RJ-Jodhpur`, `TN-Cuddalore`).
- **State Registry (`models/state_mapping.py`):**
  - Authoritative registry of all **36 States and Union Territories** in India.
  - Contains 2-letter canonical ISO/postal codes (`state_id`), official display names, Census state codes (`st_code`), and type (`State` vs `UT`).
  - Includes historical name aliases (e.g. `Orissa` $\rightarrow$ `OD`, `Pondicherry` $\rightarrow$ `PY`, `Uttaranchal` $\rightarrow$ `UK`, `Dadra and Nagar Haveli and Daman and Diu` $\rightarrow$ `DD`).
  - Safe resolver `resolve_state_id(identifier)` handles 2-letter codes, district IDs, and normalized state names. Does not guess ambiguous names.

### 2.2 Observation Characteristics
- **Frequency:** Real CGWB groundwater well measurements in India occur periodically rather than monthly. 94.5% of observations occur in four seasonal monitoring rounds:
  - **January (Rabi post-monsoon):** 27.1%
  - **May (Pre-monsoon / peak summer):** 21.7%
  - **August (Mid-monsoon):** 22.4%
  - **November (Post-monsoon):** 23.3%
- **Coverage Status:**
  - **30 States/UTs:** Ample historical depth records ($\ge 30$ measurement dates spanning 2002–2026).
  - **3 Sparse States/UTs:** Andaman & Nicobar Islands (`AN`, 13 dates), Manipur (`MN`, 6 dates), Mizoram (`MZ`, 1 date).
  - **3 Zero-Observation States/UTs:** Ladakh (`LA`, 0 dates), Lakshadweep (`LD`, 0 dates), Sikkim (`SK`, 0 dates).

---

## 3. State Aggregation Methodology

### 3.1 Auditable Aggregation Function
The target metric is state-level groundwater depth in metres below ground level ($\text{m\_bgl}$):
$$\text{GWL}_{\text{state}, t} = \frac{1}{|\mathcal{D}_{\text{valid}, t}|} \sum_{d \in \mathcal{D}_{\text{valid}, t}} \text{GWL}_{d, t}$$

Where:
- $\mathcal{D}_{\text{valid}, t}$ is the set of districts in the state with verified, non-imputed observations at time $t$ satisfying $\text{is\_observed} = \text{True}$ and $\text{gwl\_current} \ge 0.0$.
- **No Zero Substitution:** Missing districts or periods are **never treated as zero**. Treating missing data as zero would erroneously indicate water surfacing at the ground level.
- **Reporting Counts:** Every state-period estimate explicitly returns `contributing_districts_count`, `total_districts_in_state`, and `district_coverage_pct`.
- **Weighting:** Transparent equal district weighting is used as the defensible standard. Station-level counts vary by monitoring campaign, so equal weighting across reporting districts prevents single over-sampled monitoring clusters from skewing regional averages.

---

## 4. Forecasting Model Architecture & Approach Selection

### 4.1 Competing Approaches Evaluated
We formulated and evaluated two distinct forecasting paradigms on identical held-out chronological test sets:

1. **Approach A (Direct State Time-Series Projection):**
   - Fits a seasonal harmonic and damped secular trend model directly on the aggregated state-level historical time series available up to the forecast origin:
     $$\widehat{\text{GWL}}_{t+h} = \beta_0 + \beta_1 \cdot \left(\frac{1 - e^{-h / \tau}}{\tau}\right) + \beta_2 \sin\left(\frac{2\pi \cdot m_{t+h}}{12}\right) + \beta_3 \cos\left(\frac{2\pi \cdot m_{t+h}}{12}\right) + \delta_{\text{anchor}}$$
   - Estimated via robust M-estimation (Huber weighting) with exponentially downweighted historical evidence ($\tau_{\text{half-life}} = 60\text{ months}$).
2. **Approach B (District Forecast Aggregation):**
   - Fits individual district models for all constituent districts up to the forecast origin, projects each district forward 12 months, and aggregates the forecasts into a state projection:
     $$\widehat{\text{GWL}}_{\text{state}, t+h} = \frac{1}{|\mathcal{D}|} \sum_{d \in \mathcal{D}} \widehat{\text{GWL}}_{d, t+h}$$

### 4.2 Chronological Held-Out Evaluation (2020–2024)
- **Protocol:** Strict temporal embargo. For 20 quarterly forecast origins between `2020-01-01` and `2024-11-01`, models were fitted strictly on data $\le \text{origin}$. Target horizons $M+1$ through $M+12$ were evaluated against actual aggregated state observations across 476 matched test points in 30 states.
- **Results:**

| Model / Approach | MAE (m) | RMSE (m) | Skill vs Persistence ($R^2_\Delta$) | Status |
| :--- | :---: | :---: | :---: | :--- |
| **Approach A1: Direct State Projection** | **1.7652** | **3.8440** | **+0.4400** | **Selected Primary Engine** |
| **Seasonal-Naive Baseline** | **1.8481** | **4.7317** | **+0.1491** | Benchmark |
| **Persistence Baseline** | **2.5785** | **5.2266** | **0.0000** | Benchmark |
| **Approach B: District Aggregation** | **3.5899** | **5.8631** | **-0.2587** | Underperforms Persistence |

### 4.3 Why Approach A Outperformed Approach B
- **Station Noise & Gaps:** Individual district time series are frequently noisy with intermittent quarterly gaps. Fitting separate unconstrained models across 20–75 districts causes variance accumulation and error drift at longer horizons ($h \ge 6$).
- **Spatial Aggregation Regularization:** Aggregating district observations first produces a smooth, regularized state-level signal that captures state-wide monsoon recharge and dry-season depletion dynamics reliably.

---

## 5. Backend API Endpoints

The backend exposes three REST endpoints under `/api/`:

### 5.1 `GET /api/states`
Returns all 36 States/UTs with their display names, 2-letter codes, census codes, and constituent district IDs.
```json
{
  "status": "success",
  "count": 36,
  "states": [
    {
      "state_id": "UP",
      "name": "Uttar Pradesh",
      "type": "State",
      "st_code": "09",
      "districts_count": 75,
      "districts": ["UP-Agra", "UP-Aligarh", "..."]
    }
  ]
}
```

### 5.2 `GET /api/states/summary?horizon=12`
Returns nationwide state rankings, current groundwater depth, projected 12-month delta, risk tier, and district reporting coverage.
```json
{
  "status": "success",
  "horizon_months": 12,
  "evaluated_states_count": 30,
  "insufficient_data_states_count": 6,
  "states": [
    {
      "state_id": "RJ",
      "state_name": "Rajasthan",
      "current_gwl_m_bgl": 18.24,
      "projected_gwl_m_bgl": 19.12,
      "projected_delta_m": 0.88,
      "depth_rank": 1,
      "depletion_rank": 4,
      "status": "available",
      "contributing_districts_count": 33,
      "total_districts_in_state": 33,
      "district_coverage_pct": 100.0
    }
  ]
}
```

### 5.3 `GET /api/predict/state/<state_id>?horizon=12`
Returns 12 chronological forecast points ($M+1$ to $M+12$), historical observations, matched Seasonal-Naive and Persistence baselines, model metadata, and limitation disclosures.
- Validates state IDs (e.g., returns 404 with helpful message for unknown state).
- Validates `horizon` (accepts $1 \le \text{horizon} \le 12$, returns 400 for bad horizons).
- Returns structured `status: "insufficient_data"` with explicit `unavailable_reason` for sparse or zero-observation states (`LA`, `LD`, `SK`, `MZ`, `MN`, `AN`). Never substitutes another state's data.

---

## 6. Frontend Dashboard Integration

1. **Dedicated States Page (`dashboard/src/pages/States.jsx`):**
   - Accessible via the top navigation bar (`/states` and `/states/:id`).
   - **Interactive Leaflet Choropleth Map (`StateMapComponent.jsx`):** Renders India's 36 state boundaries generated from verified district polygons (`public/india_states.geojson`). Supports hover tooltips, click-to-select, and dynamic legends.
   - **Metric Toggle:**
     - `Groundwater Depth (m bgl)`: Depicts current water table depth.
     - `12-Month Depth Change (m)`: Depicts projected depletion (red) versus recharge (cyan/blue).
   - **Explicit Hydrogeological Notice:** Informs users that **greater depth below ground level means lower groundwater availability**.
   - **State Forecast Graph (`StateForecastGraph.jsx`):** SVG time-series chart showing observed historical state levels, 12-month projection curve, seasonal-naive curve, and persistence reference line with interactive tooltips and experimental notices.
   - **District Drill-Down:** Lists constituent districts with direct links to district detail pages (`/district/:id`).
   - **National Comparison Ranking Table:** Tabular view of all states sorted by current depth or expected depletion.

---

## 7. Verification & Test Results

### 7.1 Backend Test Suite
Executed: `.\venv\Scripts\pytest.exe -v tests/test_state_forecasting.py tests/test_climate_forecast_12m.py tests/test_climate_forecast.py tests/test_climate_inputs.py tests/test_deployment_readiness.py tests/test_api.py`

- **Results:** **165 / 165 passed** (100% pass rate).
- **Specific State Suite (`tests/test_state_forecasting.py`):** **17 / 17 passed**.
  - All 36 states and UTs verified in registry.
  - Safe alias resolution and district ID mapping verified.
  - Non-imputation, non-zero missing handling verified.
  - Zero-observation states (`LA`, `LD`, `SK`) verified to return `insufficient_data`.
  - 12-month contract, chronological leakage prevention, and API validations verified.
  - Existing district APIs verified to remain unchanged and functional.

### 7.2 Frontend Test Suite & Build
- `npm --prefix dashboard test`: **137 / 137 passed**.
- `npm --prefix dashboard run lint`: **0 errors, 0 warnings** across 46 files.
- `npm --prefix dashboard run build`: Built production bundle in 399ms without generating untracked files.

---

## 8. Reproducible Commands

### Backend Tests
```powershell
.\venv\Scripts\pytest.exe -v tests/test_state_forecasting.py
```

### Full Backend Verification
```powershell
.\venv\Scripts\pytest.exe -v tests/test_state_forecasting.py tests/test_climate_forecast_12m.py tests/test_climate_forecast.py tests/test_climate_inputs.py tests/test_deployment_readiness.py tests/test_api.py
```

### Frontend Tests, Lint, and Build
```powershell
npm --prefix dashboard test
npm --prefix dashboard run lint
npm --prefix dashboard run build
```

### Start Local Servers
```powershell
# Backend API (port 5000)
.\venv\Scripts\python.exe -m api.app

# Frontend Dashboard (port 5173)
npm --prefix dashboard run dev
```
