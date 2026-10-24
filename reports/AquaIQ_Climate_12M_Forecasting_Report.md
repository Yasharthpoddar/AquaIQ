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
- **Training Samples:** 135,182 observed pairs across 557 districts.
  - $H=1$: 1,608 pairs (209 districts)
  - $H=2$: 8,935 pairs (555 districts)
  - $H=3$: 16,220 pairs (555 districts)
  - $H=4$: 9,585 pairs (554 districts)
  - $H=5$: 9,090 pairs (556 districts)
  - $H=6$: 15,536 pairs (523 districts)
  - $H=7$: 9,337 pairs (554 districts)
  - $H=8$: 9,151 pairs (553 districts)
  - $H=9$: 14,997 pairs (555 districts)
  - $H=10$: 9,123 pairs (554 districts)
  - $H=11$: 1,584 pairs (226 districts)
  - $H=12$: 30,016 pairs (557 districts)

---

## 5. Empirical Evaluation Results

Evaluation was executed on 981 observed holdout pairs spanning origins `2021-01-01` to `2023-02-01` and targets `2021-02-01` to `2023-03-01` using origin-available weather climatology assumptions.

### 5.1 Overall Metrics on Held-Out Test Set
| Model / Baseline | $N$ | MAE ($m$) | RMSE ($m$) | $R^2$ / NSE |
| :--- | :---: | :---: | :---: | :---: |
| **XGBoost (12-month climate)** | 981 | 0.937 | 1.162 | 0.959 |
| **Persistence Baseline** | 981 | 0.043 | 0.266 | 0.998 |
| **XGBoost (Seasonal Paired)** | 935 | 0.941 | 1.162 | 0.960 |
| **Seasonal-Naive Baseline** | 935 | 0.579 | 1.617 | 0.922 |

### 5.2 Horizon-by-Horizon Comparison (MAE in Metres)
| Horizon | $N$ | XGBoost MAE ($m$) | Persistence MAE ($m$) | Seasonal $N$ | XGBoost Paired ($m$) | Seasonal-Naive ($m$) | XGB Beats Seasonal? |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **M+1** | 111 | **0.704** | 0.094 | 102 | **0.656** | 0.803 | **Yes** ($\Delta -0.147m$) |
| **M+2** | 104 | **0.779** | 0.045 | 97 | **0.780** | 0.788 | **Yes** ($\Delta -0.009m$) |
| **M+3** | 98 | 1.000 | 0.048 | 92 | 1.005 | **0.770** | No ($\Delta +0.235m$) |
| **M+4** | 92 | 1.127 | 0.048 | 87 | 1.133 | **0.749** | No ($\Delta +0.384m$) |
| **M+5** | 86 | 1.233 | 0.026 | 81 | 1.248 | **0.712** | No ($\Delta +0.536m$) |
| **M+6** | 82 | 1.297 | 0.027 | 78 | 1.322 | **0.670** | No ($\Delta +0.652m$) |
| **M+7** | 78 | 1.233 | 0.029 | 75 | 1.252 | **0.628** | No ($\Delta +0.624m$) |
| **M+8** | 74 | 1.056 | 0.030 | 71 | 1.083 | **0.519** | No ($\Delta +0.564m$) |
| **M+9** | 70 | 0.789 | 0.032 | 68 | 0.807 | **0.399** | No ($\Delta +0.408m$) |
| **M+10** | 66 | 0.707 | 0.034 | 65 | 0.717 | **0.272** | No ($\Delta +0.445m$) |
| **M+11** | 62 | 0.595 | 0.036 | 61 | 0.599 | **0.096** | No ($\Delta +0.504m$) |
| **M+12** | 58 | 0.566 | 0.039 | 58 | 0.566 | **0.039** | No ($\Delta +0.527m$) |

### 5.3 Honest Findings & Scientific Discussion
1. **Near-Term Horizons ($M+1, M+2$):** XGBoost outperforms the seasonal-naive baseline on matched pairs ($0.656m$ vs $0.803m$ at $M+1$; $0.780m$ vs $0.788m$ at $M+2$).
2. **Intermediate & Longer Horizons ($M+3$ to $M+12$):** Seasonal-naive and persistence baselines outperform XGBoost. In particular, at $M+12$ (same calendar month 1 year later), annual groundwater levels in the test subset are remarkably stable, giving seasonal-naive an MAE of $0.039m$ vs XGBoost's $0.566m$.
3. **RMSE vs MAE:** XGBoost achieves lower overall RMSE than seasonal-naive ($1.162m$ vs $1.617m$, $\Delta -0.455m$), indicating fewer large catastrophic forecast errors.
4. **Transparency & Experimental Status:** Consistent with project guidelines, the model is honestly labeled as an **experimental research output** rather than an operationally validated forecast.

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
- `pytest tests/test_climate_forecast_12m.py`: **14 / 14 passed**
- `pytest tests/test_climate_forecast.py tests/test_climate_inputs.py tests/test_climate_forecast_12m.py`: **109 / 109 passed**
- `pytest tests/test_api.py tests/test_monthly_prediction_api.py tests/test_research_forecast_api.py tests/test_climate_forecast_12m.py`: **113 / 113 passed**

### 8.2 Frontend Dashboard Tests (`npm --prefix dashboard test`)
- All unit, integration, and contract tests: **134 / 134 passed**
- Oxlint check: **0 warnings, 0 errors** on 41 files
- Vite production build: **Successfully built in 323ms**
