# AquaIQ — Design of Algorithm / Prototype

**Phase II Evaluation — P3 (5 marks)**

---

## 1. System Architecture Overview

AquaIQ uses a 7-layer pipeline architecture:

```
Data Sources → Ingestion → Preprocessing → Core ML → Advanced ML → Crisis Score → API → Dashboard
```

Each layer is independently testable and loosely coupled via CSV/PostgreSQL interfaces.

---

## 2. Algorithm Design

### 2.1 Preprocessing Algorithm

```
ALGORITHM: PreprocessingPipeline

INPUT:  raw_data table (district_id, date, source, metric, value)
OUTPUT: preprocessed_wide.csv (district_id, date, gwl, rainfall, temp, et)

1. PIVOT raw_data from long format to wide format
   - One row per (district_id, date)
   - Columns: gwl, rainfall, temperature, evapotranspiration

2. FOR EACH district:
   FOR EACH numeric column:
     a. STAGE 1 — Linear Interpolation:
        - Identify consecutive NaN runs
        - IF run_length <= 3 months:
            Fill using linear interpolation between boundary values
        - ELSE: leave as NaN

     b. STAGE 2 — SARIMA Gap-Fill:
        - IF series has >= 24 non-NaN values:
            Fit SARIMA(1,1,1)(1,1,1,12) on non-NaN values
            Predict and fill remaining NaN positions
        - ELSE:
            Forward-fill then back-fill (fallback)

3. STAGE 3 — MinMaxScaler:
   - Compute min, max for each column using ONLY train period (2002-2019)
   - Apply: scaled = (value - min) / (max - min)
   - Clip to [0, 1]
```

### 2.2 Feature Engineering Algorithm

```
ALGORITHM: FeatureEngineering

INPUT:  preprocessed_wide.csv
OUTPUT: features_matrix.csv (10 features per district-month)

1. CGWB Features:
   - GWL_current = gwl[t]
   - GWL_lag_3mo = gwl[t-3]     (per-district shift)
   - GWL_lag_6mo = gwl[t-6]     (per-district shift)

2. IMD Features:
   - rainfall_current = rainfall[t]
   - rainfall_3mo_avg = mean(rainfall[t], rainfall[t-1], rainfall[t-2])
   - monsoon_deficit_pct = (rainfall[t] - normal[month]) / normal[month] * 100

3. ERA5 Features:
   - temperature = temp[t]         (already in preprocessed data)
   - evapotranspiration = et[t]    (already in preprocessed data)

4. Derived Features:
   - water_balance_proxy = rainfall[t] - evapotranspiration[t]
   - crop_season_flag = Kharif if month in [6..10]
                        Rabi   if month in [11,12,1,2,3]
                        Zaid   if month in [4,5]
```

### 2.3 Linear Regression Algorithm

```
ALGORITHM: PerDistrictLinearRegression

INPUT:  features_matrix (train: 2002-2019, test: 2023-2024)
OUTPUT: R², RMSE, MAE per district

FOR EACH district with >= 24 months of data:
  1. X_train = features[date <= 2019-12-31]
  2. y_train = GWL_current[date <= 2019-12-31]
  3. X_test  = features[date >= 2023-01-01]
  4. y_test  = GWL_current[date >= 2023-01-01]

  5. model = LinearRegression()
  6. model.fit(X_train, y_train)
  7. y_pred = model.predict(X_test)

  8. Compute: R² = 1 - SS_res/SS_tot
             RMSE = sqrt(mean((y_test - y_pred)²))
             MAE  = mean(|y_test - y_pred|)

AGGREGATE: Report mean R², RMSE, MAE across all districts
TARGET: R² > 0.75 for majority of districts
```

### 2.4 Perceptron ANN Algorithm

```
ALGORITHM: PerceptronANNClassifier

INPUT:  features_matrix + Fuzzy Logic tier labels
OUTPUT: accuracy, precision, recall, F1, confusion matrix

1. Generate labels using Fuzzy Logic FIS:
   FOR EACH row in features_matrix:
     - Map monsoon_deficit_pct → rainfall_deficit (0-100%)
     - Map GWL change rate → depletion_rate (0-15 cm/yr)
     - tier = FIS.compute(rainfall_deficit, depletion_rate)

2. Encode tiers: Safe=0, Watch=1, Warning=2, Crisis=3

3. Split: train (2002-2019), test (2023-2024)

4. Scale features: StandardScaler (fit on train only)

5. Train:
   model = MLPClassifier(
     hidden_layer_sizes = (64,),    # 1 hidden layer, 64 neurons
     activation = 'relu',
     solver = 'adam',
     max_iter = 300,
     early_stopping = True
   )
   model.fit(X_train, y_train)

6. Evaluate on test set:
   - Accuracy = correct / total
   - Precision, Recall, F1 per class
   - Confusion Matrix [4x4]
```

### 2.5 XGBoost Forecasting Algorithm

```
ALGORITHM: XGBoostGWLForecaster

INPUT:  features_matrix with 6-month target
OUTPUT: predicted GWL 6 months ahead, RMSE, R², NSE

1. Create target:
   target_gwl_6mo[t] = GWL_current[t+6]  (per-district shift)
   Drop rows without valid target (last 6 months)

2. Temporal split (NO random — prevents data leakage):
   train: 2002-2019
   val:   2020-2022
   test:  2023-2024

3. One-hot encode crop_season_flag

4. Train:
   model = XGBRegressor(
     n_estimators = 500,
     max_depth = 7,
     learning_rate = 0.05,
     subsample = 0.8,
     objective = 'reg:squarederror'
   )
   model.fit(X_train, y_train, eval_set=[(X_val, y_val)])

5. Walk-forward validation:
   FOR year in [2020, 2021, 2022]:
     Predict on that year's data
     Compute RMSE, R², NSE

6. Final test evaluation on 2023-2024

7. Log to MLflow: hyperparams, val_rmse, val_r2, model artifact
```

### 2.6 Fuzzy Logic Crisis Scoring Algorithm

```
ALGORITHM: MamdaniFuzzyInferenceSystem

INPUT:  rainfall_deficit (0-100%), depletion_rate (0-15 cm/yr)
OUTPUT: crisis_score (0-100), tier (Safe/Watch/Warning/Crisis)

1. MEMBERSHIP FUNCTIONS (Triangular):

   rainfall_deficit:
     low    = trimf(0, 0, 25)
     medium = trimf(15, 35, 55)
     high   = trimf(40, 100, 100)

   depletion_rate:
     stable   = trimf(0, 0, 2.5)
     moderate = trimf(1.5, 3.5, 5.5)
     severe   = trimf(4, 15, 15)

   crisis_score:
     safe    = trimf(0, 10, 35)
     watch   = trimf(25, 45, 65)
     warning = trimf(55, 70, 85)
     crisis  = trimf(75, 100, 100)

2. RULE BASE (9 rules):

   | Rainfall Deficit | Depletion Rate | → Crisis Score |
   |------------------|----------------|----------------|
   | low              | stable         | safe           |
   | low              | moderate       | watch          |
   | low              | severe         | warning        |
   | medium           | stable         | watch          |
   | medium           | moderate       | warning        |
   | medium           | severe         | crisis         |
   | high             | stable         | warning        |
   | high             | moderate       | crisis         |
   | high             | severe         | crisis         |

3. DEFUZZIFICATION: Centroid method

4. TIER MAPPING:
   Safe    = score in [0, 30]
   Watch   = score in [31, 60]
   Warning = score in [61, 80]
   Crisis  = score in [81, 100]
```

### 2.7 Ensemble Crisis Score Algorithm

```
ALGORITHM: EnsembleCrisisScore

INPUT:  Linear Regression trend, XGBoost risk prediction, drought history
OUTPUT: final crisis_score (0-100)

1. Component scores:
   a. linear_regression_trend = normalized LR slope (0-100)
      Higher slope = faster depletion = higher score
   b. xgboost_risk = normalized XGBoost 6-month prediction (0-100)
      Higher predicted GWL = deeper wells = higher score
   c. drought_frequency = historical drought count / total years * 100
      More droughts = higher baseline risk

2. Weighted average:
   crisis_score = 0.25 * linear_regression_trend
                + 0.50 * xgboost_risk
                + 0.25 * drought_frequency

3. Apply Fuzzy Logic refinement:
   final_score = FIS.compute(rainfall_deficit, depletion_rate)
   tier = score_to_tier(final_score)
```

---

## 3. Prototype Status (as of Phase II)

| Component | Status | Script |
|-----------|--------|--------|
| Data Ingestion (CGWB) | ✅ Working | `data_ingestion/ingest_cgwb.py` |
| Data Ingestion (IMD+ERA5) | ✅ Working | `data_ingestion/ingest_imd_era5.py` |
| Preprocessing Pipeline | ✅ Working (17/17 tests pass) | `preprocessing/pipeline.py` |
| Feature Engineering | ✅ Working | `preprocessing/features.py` |
| Linear Regression | ✅ Working | `models/linear_regression.py` |
| Statistical t-test | ✅ Working | `models/statistical_tests.py` |
| Perceptron ANN | ✅ Working | `models/ann_classifier.py` |
| XGBoost Skeleton | ✅ Working | `models/xgboost_model.py` |
| XGBoost Grid Search | ✅ Working | `models/xgboost_gridsearch.py` |
| Fuzzy Logic FIS | ✅ Working (verified: Safe→Crisis mapping) | `models/fuzzy_logic.py` |
| Policy Recommendations | ✅ Working | `models/policy_recommendations.py` |
| Flask API (5 endpoints) | ✅ Stub endpoints live | `api/app.py` + `api/routes/` |
| React Dashboard | ✅ Builds (Leaflet + Recharts) | `dashboard/` |
| Unit Tests | ✅ 17/17 pass | `tests/test_preprocessing.py` |
| Data Completeness Report | ✅ Working | `data_ingestion/data_completeness.py` |

---

## 4. Testing Summary

### Unit Tests (17/17 passing)

| Test Class | Tests | Status |
|-----------|-------|--------|
| TestInterpolateGaps | 4 | ✅ All pass |
| TestSarimaFill | 2 | ✅ All pass |
| TestMinMaxScaler | 3 | ✅ All pass |
| TestFeatureEngineering | 4 | ✅ All pass |
| TestTrainTestSplit | 4 | ✅ All pass |

### Smoke Test (28/28 passing)

- CGWB: rows, columns, date parsing, GWL numeric
- IMD: file exists, parseable, rainfall values
- ERA5: file exists, parseable
- GeoJSON: valid structure, district count
