# SOFTWARE REQUIREMENTS SPECIFICATION (SRS)

## AquaIQ — Groundwater Crisis Forecasting & Decision Support System

**Prepared By:** Yasharth (2024800092), Yash, Ayush  
**Guide:** [Faculty Name]  
**Version:** 2.0  
**Date:** September 2026  
**Course:** B.Tech CSE — Semester V Mini Project

---

## Revision History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | Aug 2026 | Yasharth, Yash, Ayush | Initial SRS |
| 2.0 | Sep 2026 | Yasharth, Yash, Ayush | Updated post-Phase I: LSTM/SHAP dropped, PostgreSQL migration, XGBoost-only scope |

---

## Table of Contents

1. Introduction
2. Overall Description
3. Specific Requirements
4. External Interface Requirements
5. Non-functional Requirements
6. Other Requirements
7. Appendix

---

## 1. Introduction

### 1.1 Purpose

The purpose of this document is to specify the software requirements for **AquaIQ**, a machine learning-based groundwater crisis forecasting and decision support system. AquaIQ predicts groundwater level (GWL) depletion 6 months ahead for 640+ Indian districts, computes a Crisis Score (0–100), and recommends policy interventions through a web dashboard.

This SRS acts as a formal agreement between the project team and the evaluation guide, following IEEE Std 830-1998.

### 1.2 Scope

AquaIQ shall provide:

- **Data Ingestion** — Automated loading of CGWB borewell readings, IMD rainfall, and ERA5 climate data into PostgreSQL
- **Preprocessing** — Gap-filling (interpolation + SARIMA), normalization, and feature engineering (10 features)
- **Core ML Models** — Linear Regression (trend baseline), Perceptron ANN (tier classification)
- **Advanced ML** — XGBoost regressor (6-month GWL forecast, self-study extension)
- **Crisis Scoring** — Mamdani Fuzzy Inference System + ensemble weighting
- **Policy Simulator** — What-if analysis for rainfall/extraction scenarios
- **REST API** — 5 Flask endpoints serving predictions to the frontend
- **Dashboard** — React + Leaflet.js choropleth map with alerts, history charts, and simulator

The system aims to provide early warning for groundwater depletion to enable proactive policy intervention by district authorities.

### 1.3 Definitions, Acronyms and Abbreviations

| Term | Definition |
|------|-----------|
| GWL | Groundwater Level (metres below ground level) |
| CGWB | Central Ground Water Board — source of borewell readings |
| IMD | India Meteorological Department — source of district rainfall |
| ERA5 | ECMWF Reanalysis v5 — source of temperature and evapotranspiration |
| FIS | Fuzzy Inference System |
| NARP | National Agricultural Research Project (defines 15 agro-climatic zones) |
| NSE | Nash-Sutcliffe Efficiency (hydrology accuracy metric) |
| bgl | Below ground level |
| XGBoost | Extreme Gradient Boosting (tree-based ML algorithm) |
| ANN | Artificial Neural Network |
| RMSE | Root Mean Squared Error |
| R² | Coefficient of Determination |
| MAE | Mean Absolute Error |

### 1.4 References

- IEEE Std. 830-1998 — Software Requirements Specification
- CGWB India-WRIS Portal (india-wris.nrsc.gov.in)
- IMD Pune Data Portal (imdpune.gov.in)
- ERA5/Copernicus CDS API Documentation
- scikit-learn, XGBoost, scikit-fuzzy library documentation
- Flask REST API Documentation
- Leaflet.js and Recharts Documentation

### 1.5 Overview

This document describes:
- System overview and architecture
- Functional requirements (14 features)
- External interfaces (data sources, API, dashboard)
- Performance and security requirements
- Design constraints and assumptions

---

## 2. Overall Description

### 2.1 Product Perspective

AquaIQ is a full-stack web application consisting of:

- **Data Pipeline** — Python scripts ingesting 3 data sources into PostgreSQL
- **ML Engine** — Linear Regression, Perceptron ANN, XGBoost, Fuzzy Logic
- **Flask API Server** — 5 REST endpoints serving predictions
- **React Dashboard** — Leaflet.js map + Recharts visualizations
- **PostgreSQL Database** — 5 tables (districts, raw_data, features, predictions, crisis_scores)

```
┌─────────────────────┐
│   React Dashboard   │  (Leaflet.js + Recharts)
│   localhost:5173     │
└────────┬────────────┘
         │ HTTP/JSON
┌────────▼────────────┐
│   Flask API Server  │  (5 endpoints)
│   localhost:5000     │
└────────┬────────────┘
         │ SQL
┌────────▼────────────┐
│   PostgreSQL DB     │  (5 tables)
│   localhost:5432     │
└────────┬────────────┘
         │
┌────────▼────────────┐
│   ML Engine         │
│   XGBoost + FIS +   │
│   LinReg + ANN      │
└────────┬────────────┘
         │
┌────────▼────────────┐
│   Data Pipeline     │
│   CGWB + IMD + ERA5 │
└─────────────────────┘
```

### 2.2 Product Functions

The system shall provide:

1. Ingest and validate CGWB, IMD, ERA5 datasets
2. Preprocess: interpolation, SARIMA gap-fill, MinMaxScaler normalization
3. Engineer 10 features from 3 data sources
4. Train Linear Regression (per-district trend baseline)
5. Train Perceptron ANN (crisis tier classification)
6. Train XGBoost regressor (6-month GWL forecast)
7. Compute Fuzzy Logic crisis scores (9 rules, 4 tiers)
8. Generate ensemble predictions (LR trend + XGBoost risk + drought frequency)
9. Serve predictions via REST API
10. Display India choropleth map with crisis score coloring
11. Show district-level GWL forecast charts
12. Generate policy alerts for Warning/Crisis districts
13. Run what-if policy simulations
14. Export PDF crisis reports

### 2.3 User Classes / Characteristics

**District Water Authority (Primary User)**
- View crisis scores for their district
- View 6-month GWL forecast
- Receive alerts when tier = Warning or Crisis
- Run what-if simulations (e.g., "what if rainfall drops 20%?")
- Export reports for policy briefings

**State/Central Policy Maker**
- View India-wide choropleth map
- Filter districts by crisis tier
- Compare districts within a state
- Review ensemble model explanations

**Researcher / Academic**
- Access raw data and model metrics via API
- Review feature importance and model accuracy
- Validate against local monitoring data

**General Public / Citizen**
- View district-level groundwater availability and forecasts
- Access public maps to understand local water crisis risk
- Download publicly available reports

### 2.4 Operating Environment

- **Server:** Python 3.11+, Flask, PostgreSQL 15+, Node.js 18+
- **Client:** Modern web browser (Chrome, Firefox, Edge, Safari)
- **Deployment:** Docker containers (optional), runs on any Linux/macOS/Windows machine
- **No GPU required** — all ML models train on CPU in < 10 minutes

### 2.5 Design Constraints

- CGWB data is the **only** GWL source (no satellite-derived estimates)
- All 10 features must be traceable to the 3 downloaded sources — no external API calls at inference time
- PostgreSQL is mandatory (not SQLite)
- XGBoost is the only advanced ML model (LSTM and SHAP were dropped on 10 Sep 2026)
- Districts with insufficient history fall back to agro-climatic zone aggregation

### 2.6 Assumptions

- Users have a modern web browser with JavaScript enabled
- PostgreSQL server is running and accessible
- All 3 datasets (CGWB, IMD, ERA5) have been downloaded during Week 1
- GeoJSON district boundaries are pre-loaded for the map

---

## 3. Specific Requirements

Each functional requirement is assigned a unique ID for traceability.

### FR-01 Data Ingestion — CGWB

| Field | Value |
|-------|-------|
| **Description** | Load CGWB borewell CSV into the `raw_data` table |
| **Inputs** | `data/raw/cgwb_combined.csv` |
| **Processing** | Parse CSV, validate district codes, deduplicate, aggregate to monthly mean GWL |
| **Output** | `raw_data` table populated with source='CGWB', metric='GWL' |
| **Priority** | High |

### FR-02 Data Ingestion — IMD + ERA5

| Field | Value |
|-------|-------|
| **Description** | Load IMD rainfall and ERA5 temperature/ET into `raw_data` |
| **Inputs** | `imd_rainfall_district_monthly.csv`, `era5_district_monthly.csv` |
| **Processing** | Parse CSV, match district names to `districts` table, insert with ON CONFLICT DO NOTHING |
| **Output** | `raw_data` table with source='IMD' and source='ERA5' rows |
| **Priority** | High |

### FR-03 Preprocessing Pipeline

| Field | Value |
|-------|-------|
| **Description** | Clean and normalize raw data for feature engineering |
| **Inputs** | `raw_data` table (all 3 sources) |
| **Processing** | Stage 1: Linear interpolation (gaps ≤ 3 months). Stage 2: SARIMA(1,1,1)(1,1,1,12) for longer gaps. Stage 3: MinMaxScaler fitted on train period only (2002-2019) |
| **Output** | `data/processed/preprocessed_wide.csv` |
| **Priority** | High |

### FR-04 Feature Engineering

| Field | Value |
|-------|-------|
| **Description** | Build 10 features from preprocessed data |
| **Inputs** | `preprocessed_wide.csv` |
| **Processing** | Build: GWL_current, GWL_lag_3mo, GWL_lag_6mo, rainfall_current, rainfall_3mo_avg, monsoon_deficit_pct, temperature, evapotranspiration, water_balance_proxy, crop_season_flag |
| **Output** | `data/processed/features_matrix.csv` + `features` table |
| **Priority** | High |

### FR-05 Linear Regression Training

| Field | Value |
|-------|-------|
| **Description** | Train per-district Linear Regression (2002-2019) |
| **Inputs** | Feature matrix (train split) |
| **Processing** | scikit-learn LinearRegression, per-district. Evaluate R², RMSE, MAE on 2023-2024 test set |
| **Output** | `linear_regression_results.csv`, trend predictions |
| **Priority** | Medium |

### FR-06 Perceptron ANN Training

| Field | Value |
|-------|-------|
| **Description** | Train MLPClassifier to classify districts into crisis tiers |
| **Inputs** | Feature matrix + Fuzzy Logic labels |
| **Processing** | MLPClassifier([64], ReLU, Adam), 4-class output (Safe/Watch/Warning/Crisis) |
| **Output** | Accuracy, precision, recall, F1, confusion matrix |
| **Priority** | Medium |

### FR-07 XGBoost Training

| Field | Value |
|-------|-------|
| **Description** | Train XGBoost regressor for 6-month GWL forecast |
| **Inputs** | Feature matrix with 6-month target |
| **Processing** | XGBRegressor(n_estimators=500, max_depth=7, lr=0.05). Walk-forward validation. MLflow tracking |
| **Output** | `models/checkpoints/xgboost_v1.json`, RMSE, R², NSE metrics |
| **Priority** | High |

### FR-08 Fuzzy Logic Crisis Scoring

| Field | Value |
|-------|-------|
| **Description** | Compute crisis score (0-100) using Mamdani FIS |
| **Inputs** | rainfall_deficit (0-100%), depletion_rate (0-15 cm/yr) |
| **Processing** | 3 membership functions per input (triangular), 9 fuzzy rules |
| **Output** | Crisis score → tier mapping: Safe (0-30), Watch (31-60), Warning (61-80), Crisis (81-100) |
| **Priority** | High |

### FR-09 REST API — Predict

| Field | Value |
|-------|-------|
| **Description** | Return 6-month GWL forecast + crisis score for a district |
| **Endpoint** | `GET /api/predict/<district_id>` |
| **Output** | JSON: `{ crisis_score, tier, forecast[], ensemble_weights, recommendation }` |
| **Priority** | High |

### FR-10 REST API — History

| Field | Value |
|-------|-------|
| **Description** | Return historical GWL + rainfall data |
| **Endpoint** | `GET /api/history/<district_id>?start=YYYY-MM&end=YYYY-MM` |
| **Output** | JSON: `{ data[]: { date, gwl, rainfall } }` |
| **Priority** | Medium |

### FR-11 REST API — Alerts

| Field | Value |
|-------|-------|
| **Description** | Return all districts in Warning or Crisis tier |
| **Endpoint** | `GET /api/alerts?tier=Crisis` |
| **Output** | JSON: `{ count, alerts[]: { district_id, score, tier, recommendation } }` |
| **Priority** | Medium |

### FR-12 REST API — Simulate

| Field | Value |
|-------|-------|
| **Description** | What-if policy simulation |
| **Endpoint** | `POST /api/simulate` |
| **Input** | JSON: `{ district_id, rainfall_change_pct, extraction_change_pct }` |
| **Output** | JSON: `{ baseline_score, simulated_score, baseline_tier, simulated_tier, delta }` |
| **Priority** | Medium |

### FR-13 Dashboard — Choropleth Map

| Field | Value |
|-------|-------|
| **Description** | Interactive India map with district-level crisis coloring |
| **Processing** | Leaflet.js loads GeoJSON boundaries, colors polygons by tier |
| **Features** | Hover tooltip, click-to-detail, district search bar, color legend |
| **Priority** | High |

### FR-14 Dashboard — PDF Report Export

| Field | Value |
|-------|-------|
| **Description** | Generate downloadable PDF crisis report for a district |
| **Processing** | ReportLab generates PDF with score, forecast chart, recommendation |
| **Output** | PDF file download |
| **Priority** | Low |

---

## 4. External Interface Requirements

### 4.1 User Interfaces

- **Web Dashboard:** React SPA at `http://localhost:5173`
  - Home page: India choropleth map + summary cards
  - District detail: Score badge + 6-month forecast chart (Recharts)
  - Alerts page: Warning/Crisis district list with policy recommendations
  - Simulator page: Rainfall/extraction sliders + before/after comparison

### 4.2 Hardware Interfaces

- No specialized hardware required
- Any machine with 8GB+ RAM, 4-core CPU
- No GPU required for training

### 4.3 Software Interfaces

| Interface | Protocol | Purpose |
|-----------|----------|---------|
| PostgreSQL 15+ | TCP/SQL | Primary data store |
| Flask API | HTTP/JSON | Model inference serving |
| React Dashboard | HTTP | Client-side rendering |
| MLflow | HTTP | Experiment tracking |

### 4.4 Communication Interfaces

- Flask API communicates with React dashboard via HTTP REST (JSON)
- CORS enabled for `localhost:3000` and `localhost:5173`
- All API responses follow consistent JSON schema

---

## 5. Non-functional Requirements

### NFR-01 Performance

| ID | Requirement |
|----|-------------|
| NFR-P-01 | API response time < 2 seconds for single-district prediction |
| NFR-P-02 | Dashboard initial load < 5 seconds |
| NFR-P-03 | XGBoost training completes in < 10 minutes on CPU |
| NFR-P-04 | Batch prediction for all 640+ districts < 30 seconds |

### NFR-02 Accuracy

| ID | Requirement |
|----|-------------|
| NFR-A-01 | Linear Regression R² > 0.75 for majority of districts |
| NFR-A-02 | XGBoost RMSE < 2.0m on 2023-2024 test set |
| NFR-A-03 | Fuzzy Logic crisis tiers match domain expert expectations |
| NFR-A-04 | ANN classification accuracy > 70% |

### NFR-03 Availability

| ID | Requirement |
|----|-------------|
| NFR-Av-01 | System shall be available during demo/evaluation hours |
| NFR-Av-02 | API shall serve cached predictions if model service is down |

### NFR-04 Security

| ID | Requirement |
|----|-------------|
| NFR-S-01 | Database credentials stored in `.env`, never committed to git |
| NFR-S-02 | API uses CORS whitelist, not wildcard |
| NFR-S-03 | No authentication required for read-only endpoints (academic project) |

### NFR-05 Reproducibility

| ID | Requirement |
|----|-------------|
| NFR-R-01 | All dependencies pinned in `requirements.txt` |
| NFR-R-02 | `config.yaml` is the single source of truth for all hyperparameters |
| NFR-R-03 | Random seeds set for all ML models |
| NFR-R-04 | MLflow tracks all experiment runs |

### NFR-06 Testability

| ID | Requirement |
|----|-------------|
| NFR-T-01 | Minimum 70% code coverage for preprocessing module |
| NFR-T-02 | All 5 preprocessing functions have unit tests |
| NFR-T-03 | Smoke test validates all input datasets parse correctly |

---

## 6. Other Requirements

### 6.1 Course Subject Mapping

| Subject | Code | AquaIQ Component |
|---------|------|-------------------|
| Python for Data Science | AS202 | Data pipeline, preprocessing, EDA |
| Statistical Methods for AI | CS205 | t-test, correlation, regression |
| AI & Soft Computing | CS303 | Fuzzy Logic FIS, Perceptron ANN |
| Database Management | CS204 | PostgreSQL schema, SQL queries |
| Web Development | CS301 | Flask API, React dashboard |
| Software Engineering | CS302 | SRS, testing, project management |

### 6.2 Ethical Considerations

- No personally identifiable information is processed
- All data sources are government open-data portals
- Predictions are advisory — not meant to replace expert hydrological assessment

---

## 7. Appendix

### 7.1 Feature Traceability Matrix

| # | Feature | Source | Script |
|---|---------|--------|--------|
| 1 | GWL_current | CGWB | `preprocessing/features.py` |
| 2 | GWL_lag_3mo | CGWB | `preprocessing/features.py` |
| 3 | GWL_lag_6mo | CGWB | `preprocessing/features.py` |
| 4 | rainfall_current | IMD | `preprocessing/features.py` |
| 5 | rainfall_3mo_avg | IMD | `preprocessing/features.py` |
| 6 | monsoon_deficit_pct | IMD | `preprocessing/features.py` |
| 7 | temperature | ERA5 | `preprocessing/features.py` |
| 8 | evapotranspiration | ERA5 | `preprocessing/features.py` |
| 9 | water_balance_proxy | Derived | `preprocessing/features.py` |
| 10 | crop_season_flag | Calendar | `preprocessing/features.py` |

### 7.2 Database Schema (5 Tables)

```sql
districts       (district_id PK, district_name, state, agro_climatic_zone, geojson_name)
raw_data        (id PK, district_id FK, date, source, metric, value)
features        (id PK, district_id FK, date, 10 feature columns, data_readiness_score)
predictions     (id PK, district_id FK, forecast_date, model_type, predicted_gwl)
crisis_scores   (id PK, district_id FK, score_date, crisis_score, tier, ensemble_weights)
```

### 7.3 API Endpoint Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/predict/<district_id>` | 6-month forecast + crisis score |
| GET | `/api/history/<district_id>` | Historical GWL + rainfall |
| GET | `/api/alerts` | Warning/Crisis district list |
| POST | `/api/simulate` | What-if policy simulation |
| GET | `/api/health` | API status + DB connectivity |
