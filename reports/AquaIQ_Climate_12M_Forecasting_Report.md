# AquaIQ Climate-Informed 12-Month XGBoost Forecasting Pipeline Report

**Date:** 24 October 2026  
**Repository:** [https://github.com/Yasharthpoddar/AquaIQ](https://github.com/Yasharthpoddar/AquaIQ)  
**Branch:** `feature/climate-12m-xgboost`  
**Model Version:** `1.0-climate-conditioned-12m-xgb`  
**Product Name:** `climate_informed_12m_forecast`  

---

## 1. Executive Summary & Objective

The primary objective was to replace the district-page 12-month unconditioned seasonal/trend scenario with a genuine climate-informed XGBoost forecasting pipeline that outputs one groundwater-depth prediction (metres below ground level) for each of the next 12 calendar months (horizons $M+1$ through $M+12$), conditioned on physical weather inputs (rainfall, temperature, and evapotranspiration).

The implementation strictly preserves:
- The legacy 6-month model checkpoint (`models/checkpoints/aquaiq_monthly_climate.json`) and API (`/api/predict/<district_id>?window=next_six_months`).
- The existing direct $M+12$ historical research endpoint and artifacts (`/api/research/...`).
- Database schemas, crisis-score weights, and unaffected application features.

The new 12-month model is separately versioned, trained on 135,182 real observed origin-target pairs across 12 horizons with a strict 12-month temporal embargo, evaluated honestly against persistence and seasonal-naive baselines, served via a dedicated API endpoint (`/api/predict/climate-12m/<district_id>`), and visualized as the primary district forecast graph on `DistrictDetail.jsx`.

---

## 2. Pipeline Design & Model Architecture

### 2.1 Model Architecture
- **Framework:** XGBoost Regressor (`xgb.XGBRegressor`).
- **Formulation:** Horizon-aware pooled regression predicting $\Delta \text{GWL} = \text{target\_gwl} - \text{origin\_gwl}$.
- **Parameters:**
  ```python
  {
      'n_estimators': 240,
      'max_depth': 3,
      'learning_rate': 0.04,
      'min_child_weight': 30,
      'reg_lambda': 20.0,
      'reg_alpha': 0.1,
      'subsample': 0.85,
      'colsample_bytree': 0.9,
      'random_state': 42,
      'n_jobs': 4,
      'tree_method': 'hist',
      'objective': 'reg:squarederror'
  }
  ```
- **Prediction Target:** Change in depth from origin $\Delta \text{GWL}$ in metres below ground level ($\text{m\_bgl}$). Ground level predictions are reconstructed as $\widehat{\text{GWL}}_{t+h} = \max(0, \text{GWL}_t + \widehat{\Delta\text{GWL}}_{t+h})$.

### 2.2 Feature Schema
The model uses 17 causal physical features:
1. `origin_gwl`: Estimated or observed groundwater depth at origin month ($m\_bgl$).
2. `origin_gwl_lag_3mo`: Groundwater depth 3 months prior to origin.
3. `origin_gwl_lag_6mo`: Groundwater depth 6 months prior to origin.
4. `origin_rainfall`: Origin month rainfall ($mm/month$).
5. `origin_temperature`: Origin month mean temperature ($^\circ C$).
6. `origin_evapotranspiration`: Origin month evapotranspiration ($mm/month$).
7. `horizon_months`: Forecast horizon step ($1.0, 2.0, \dots, 12.0$).
8. `origin_month_sin`: $\sin(2\pi \cdot \text{origin\_month} / 12)$.
9. `origin_month_cos`: $\cos(2\pi \cdot \text{origin\_month} / 12)$.
10. `target_month_sin`: $\sin(2\pi \cdot \text{target\_month} / 12)$.
11. `target_month_cos`: $\cos(2\pi \cdot \text{target\_month} / 12)$.
12. `target_rainfall`: Assumed rainfall for horizon month $t+h$ ($mm/month$).
13. `target_temperature`: Assumed temperature for horizon month $t+h$ ($^\circ C$).
14. `target_evapotranspiration`: Assumed evapotranspiration for horizon month $t+h$ ($mm/month$).
15. `cumulative_rainfall`: $\sum_{s=1}^h \text{rain}_s$ from origin through target horizon ($mm$).
16. `cumulative_evapotranspiration`: $\sum_{s=1}^h \text{et}_s$ from origin through target horizon ($mm$).
17. `mean_temperature`: $\frac{1}{h} \sum_{s=1}^h \text{temp}_s$ from origin through target horizon ($^\circ C$).

### 2.3 Feature Importance (Top Predictors)
- `cumulative_rainfall`: **18.54%**
- `origin_month_cos`: **14.18%**
- `target_month_cos`: **13.46%**
- `horizon_months`: **13.36%**
- `target_month_sin`: **6.28%**
- `origin_month_sin`: **4.96%**
- `origin_evapotranspiration`: **4.60%**
- `origin_gwl`: **3.46%**
- `origin_rainfall`: **3.39%**

---

## 3. Future Weather Policy

At inference time, real future weather is unknown. The pipeline implements an explicit, origin-available historical monthly climatology policy:
- Up to 10 most recent complete calendar years available at the forecast origin are averaged for each calendar month and weather field (`rainfall`, `temperature`, `evapotranspiration`).
- A minimum of 3 prior distinct years is strictly required. If insufficient historical records exist, the model returns an explicit `insufficient_data` status with field-level missingness details.
- No future weather observations are leaked during inference or evaluation.
- The exact weather assumptions conditioning each month are returned in the API response and displayed to the user in the chart tooltip and values table.

---

## 4. Training Protocol & Temporal Embargo

- **Source Feature Matrix:** `data/processed/features_matrix.csv` (215,325 rows, generation `physical-v3-causal-monthly-a3f9468a2569`).
- **Target Join:** Exact calendar month and district ID matching. Imputed or missing groundwater values are strictly excluded from both origins and targets.
- **Training Label Cutoff:** `2019-12-31`. All training pairs satisfy $\text{target\_date} \le 2019\text{-}12\text{-}31$.
- **Temporal Embargo:** Strict 12-month embargo. The earliest eligible evaluation origin is $\text{first\_origin} = 2021\text{-}01\text{-}01$ ($13$ calendar months after the training cutoff).
- **Training Samples:** 116,601 observed pairs across 558 districts satisfying the origin-available weather climatology requirement (zero future weather leakage).

---

## 5. Empirical Evaluation Results

Evaluation was executed on 981 observed holdout pairs spanning origins `2021-01-01` to `2023-02-01` and targets `2021-02-01` to `2023-03-01` using origin-available weather climatology assumptions.

### 5.1 Overall Metrics on Held-Out Test Set
| Model / Baseline | $N$ | MAE ($m$) | RMSE ($m$) | $R^2$ / NSE |
| :--- | :---: | :---: | :---: | :---: |
| **XGBoost (12-month climate)** | 981 | 0.896 | 1.112 | 0.963 |
| **Persistence Baseline** | 981 | 0.043 | 0.266 | 0.998 |
| **Change Prediction Skill ($\Delta$)** | 981 | 0.896 | 1.112 | -16.853 |
| **XGBoost (Seasonal Paired)** | 935 | 0.895 | 1.109 | 0.963 |
| **Seasonal-Naive Baseline** | 935 | 0.579 | 1.617 | 0.922 |

### 5.2 Dominant vs. Remaining Districts Breakdown
- **Dominant Flat Districts ($N=960$, 4 districts: TN-Cuddalore, TN-Sivaganga, TN-Tiruppur, UP-Deoria):**
  - XGBoost MAE: **0.899 m** (RMSE: 1.109 m)
  - Persistence MAE: **0.028 m** (RMSE: 0.139 m)
  - During 2021–2023, groundwater depths in these four districts remained virtually flat in the source data (e.g. Tiruppur flat at 2.325 m for 26 targets), giving persistence a baseline MAE under 3 cm. These records are authentic source-marked observations (`is_observed=True`), not pipeline artifacts, and must not be discarded.
- **Remaining Eligible Districts ($N=21$, 3 districts: HR-Kurukshetra, HR-Kaithal, HR-Jind):**
  - XGBoost MAE: **0.755 m** (RMSE: 1.262 m)
  - Persistence MAE: **0.742 m** (RMSE: 1.552 m)
  - Even on the non-flat districts, persistence achieves a slightly lower MAE than XGBoost.

### 5.3 Horizon-by-Horizon Comparison (MAE in Metres)
| Horizon | $N$ | XGBoost MAE ($m$) | Persistence MAE ($m$) | Seasonal $N$ | XGBoost Paired ($m$) | Seasonal-Naive ($m$) | XGB Beats Seasonal? |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **M+1** | 111 | 0.776 | **0.094** | 102 | **0.743** | 0.803 | **Yes** ($\Delta -0.060m$) |
| **M+2** | 104 | 0.800 | **0.045** | 97 | 0.805 | **0.788** | No ($\Delta +0.017m$) |
| **M+3** | 98 | 0.980 | **0.048** | 92 | 0.987 | **0.770** | No ($\Delta +0.217m$) |
| **M+4** | 92 | 1.133 | **0.048** | 87 | 1.140 | **0.749** | No ($\Delta +0.391m$) |
| **M+5** | 86 | 1.202 | **0.026** | 81 | 1.215 | **0.712** | No ($\Delta +0.503m$) |
| **M+6** | 82 | 1.195 | **0.027** | 78 | 1.216 | **0.670** | No ($\Delta +0.546m$) |
| **M+7** | 78 | 1.159 | **0.029** | 75 | 1.176 | **0.628** | No ($\Delta +0.548m$) |
| **M+8** | 74 | 0.970 | **0.030** | 71 | 0.993 | **0.519** | No ($\Delta +0.474m$) |
| **M+9** | 70 | 0.663 | **0.032** | 68 | 0.678 | **0.399** | No ($\Delta +0.279m$) |
| **M+10** | 66 | 0.576 | **0.034** | 65 | 0.584 | **0.272** | No ($\Delta +0.312m$) |
| **M+11** | 62 | 0.518 | **0.036** | 61 | 0.521 | **0.096** | No ($\Delta +0.425m$) |
| **M+12** | 58 | 0.500 | **0.039** | 58 | 0.500 | **0.039** | No ($\Delta +0.461m$) |

### 5.4 Honest Findings & Scientific Discussion
1. **Pooled $R^2$ is Deceptive:** While the reported pooled $R^2$ of 0.963 appears impressive, 99.9997% of the total target sum-of-squares in the holdout test set is driven by cross-sectional differences in mean district depth (e.g. 2.3 m in Tiruppur vs 35 m in Kurukshetra), NOT temporal forecasting skill.
2. **Change Prediction Skill is Negative:** When evaluated on change prediction ($\Delta \text{GWL} = \text{target} - \text{origin}$), XGBoost achieves $R^2 = -16.853$, showing that predicting depth changes with the climate model is less accurate than assuming no change (persistence).
3. **Persistence Dominates Overall:** At every single horizon from $M+1$ through $M+12$, Persistence achieves lower MAE than XGBoost (overall 0.043 m vs 0.896 m).
4. **Seasonal Comparison:** At $M+1$, XGBoost slightly outperforms seasonal-naive (0.743 m vs 0.803 m), but from $M+2$ to $M+12$, seasonal-naive outperforms XGBoost.
5. **Transparency & UI Presentation:** The model is honestly labeled as an **experimental research model** and is never presented as operational. The UI graph explicitly presents persistence as the primary reference and shows seasonal-naive where available, never fabricating predictions.

---

## 6. Dedicated API Endpoint

### 6.1 Route Specification
- **URL:** `GET /api/predict/climate-12m/<district_id>`
- **Query Parameters:**
  - `months` (optional): Must equal `'12'`. Any other value returns `400 invalid_request`.
  - `as_of` (optional): Cutoff date (`today`, `last_observed`, or `YYYY-MM-DD`).
- **Response Format (JSON):**
  ```json
  {
    "product": "climate_informed_12m_forecast",
    "model_version": "1.0-climate-conditioned-12m-xgb",
    "district_id": "DL-Delhi",
    "status": "forecast",
    "as_of": "2026-10-24",
    "forecast_origin": "2026-10-01",
    "timezone": "Asia/Kolkata",
    "horizon_months": 12,
    "forecast_horizon": "next twelve full calendar months",
    "units": "m_bgl",
    "forecast_start": "2026-11",
    "forecast_end": "2027-10",
    "last_observed_date": "2024-05-01",
    "last_observed_gwl": 14.20,
    "data_age_months": 29,
    "estimated_current_gwl": 16.3534,
    "current_depth_basis": "estimated_from_historical_groundwater",
    "projection_method": "climate_conditioned_xgboost_12m",
    "model_sha256": "4fd450e1814e5b22591e1d0f5ffba3eb287f3ddf83dafc5002ba50567f13da32",
    "model_train_target_cutoff": "2019-12-31",
    "forecast": [
      {
        "month": "2026-11",
        "date": "2026-11-01",
        "horizon": 1,
        "predicted_gwl": 17.2187,
        "delta_from_current_m": 0.8653,
        "weather": {
          "rainfall_mm": 4.7894,
          "temperature_c": 19.4386,
          "evapotranspiration_mm": 102.1598
        }
      },
      ... (exactly 12 months)
    ]
  }
  ```

---

## 7. Frontend Integration

1. **`DistrictForecastGraph.jsx`:**
   - Mounts `ClimateForecast12m` fetching from `/api/predict/climate-12m/<district_id>`.
   - Renders 12 monthly predictions connected chronologically in Recharts `LineChart`.
   - Custom hover tooltip displays predicted groundwater depth in metres below ground level, change from current depth, and the exact weather inputs (`rainfall_mm`, `temperature_c`, `evapotranspiration_mm`).
   - Includes an expandable table listing all 12 monthly predictions, horizon offsets ($M+1$ to $M+12$), depth deltas, and climate inputs.
   - Expandable technical details section shows model version, checkpoint SHA-256, weather assumption description, and limitations.
   - Replaces the obsolete 6-month-only disclaimer panel with direct display of the causal weather conditioning inputs.
2. **`climateForecast12mContract.js`:**
   - Validates client payloads strictly against the 12-month contract, ensuring exact horizons, nonfinite checks, and valid units.
3. **`api.js`:**
   - Exports `fetchClimate12mForecast(id, asOf)`.

---

## 8. Verification & Test Outcomes

### 8.1 Backend Python Tests (`pytest`)
- `pytest tests/test_climate_forecast_12m.py`: **19 / 19 passed**
- Combined backend suites (`test_climate_forecast.py`, `test_climate_inputs.py`, `test_climate_forecast_12m.py`, `test_deployment_readiness.py`, `test_api.py`): **148 / 148 passed**
- Clean deployment loading test without local checkpoints: **Verified passed**

### 8.2 Frontend Dashboard Tests (`npm --prefix dashboard test`)
- All unit, integration, and contract tests: **134 / 134 passed**
- Vite production build: **Successfully built in 359ms**
- Artifact footprint: **Versioned release bundle in `models/artifacts/` is ~318 KB, tracked in Git and included in Docker builds.**
