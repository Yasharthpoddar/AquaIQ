# AquaIQ — UML Diagrams

## 1. Use Case Diagram

```mermaid
graph TB
    subgraph AquaIQ System
        UC1["View Choropleth Map"]
        UC2["View District Forecast"]
        UC3["View Alerts"]
        UC4["Run Policy Simulation"]
        UC5["Export PDF Report"]
        UC6["Ingest Data"]
        UC7["Train Models"]
        UC8["Compute Crisis Scores"]
        UC9["Monitor System Health"]
    end

    User["District Water Authority"]
    PM["Policy Maker"]
    Admin["System Admin"]
    Citizen["General Public"]

    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC4
    User --> UC5
    PM --> UC1
    PM --> UC3
    PM --> UC4
    Citizen --> UC1
    Citizen --> UC2
    Admin --> UC6
    Admin --> UC7
    Admin --> UC8
    Admin --> UC9
```

---

## 2. Class Diagram

```mermaid
classDiagram
    class District {
        +String district_id
        +String district_name
        +String state
        +String agro_climatic_zone
        +String geojson_name
    }

    class RawData {
        +int id
        +String district_id
        +Date date
        +String source
        +String metric
        +float value
    }

    class Feature {
        +int id
        +String district_id
        +Date date
        +float GWL_current
        +float GWL_lag_3mo
        +float GWL_lag_6mo
        +float rainfall_current
        +float rainfall_3mo_avg
        +float monsoon_deficit_pct
        +float temperature
        +float evapotranspiration
        +float water_balance_proxy
        +String crop_season_flag
        +float data_readiness_score
    }

    class Prediction {
        +int id
        +String district_id
        +Date forecast_date
        +String model_type
        +float predicted_gwl
        +float confidence_lower
        +float confidence_upper
    }

    class CrisisScore {
        +int id
        +String district_id
        +Date score_date
        +float crisis_score
        +String tier
        +JSON ensemble_weights
    }

    class PreprocessingPipeline {
        +interpolate_gaps(series, max_gap)
        +sarima_fill(series, period)
        +fit_transform(df, columns)
        +run_pipeline(df)
    }

    class LinearRegressionModel {
        +train_per_district(df)
        +predict(district_id, features)
        +evaluate(test_df)
    }

    class ANNClassifier {
        +generate_fuzzy_labels(df)
        +train_ann(df, max_iter)
        +predict_tier(features)
    }

    class XGBoostModel {
        +load_feature_matrix()
        +create_target(df)
        +temporal_split(df)
        +train_xgboost(train, val)
        +walk_forward_validate(model, val)
        +evaluate_on_test(model, test)
    }

    class FuzzyLogicFIS {
        +build_fuzzy_system()
        +compute_crisis_score(rd, dr)
        +score_to_tier(score)
    }

    class PolicyRecommendation {
        +get_recommendation(tier)
        +format_alert_message(district, score, tier)
    }

    class FlaskAPI {
        +get_prediction(district_id)
        +get_history(district_id)
        +get_alerts()
        +simulate(params)
        +health_check()
    }

    District "1" --> "*" RawData : has
    District "1" --> "*" Feature : has
    District "1" --> "*" Prediction : has
    District "1" --> "*" CrisisScore : has
    RawData --> PreprocessingPipeline : feeds
    PreprocessingPipeline --> Feature : produces
    Feature --> LinearRegressionModel : inputs
    Feature --> ANNClassifier : inputs
    Feature --> XGBoostModel : inputs
    FuzzyLogicFIS --> CrisisScore : computes
    CrisisScore --> PolicyRecommendation : maps
    FlaskAPI --> XGBoostModel : calls
    FlaskAPI --> FuzzyLogicFIS : calls
```

---

## 3. Sequence Diagram — Prediction Flow

```mermaid
sequenceDiagram
    participant User as Dashboard User
    participant React as React Frontend
    participant API as Flask API
    participant DB as PostgreSQL
    participant XGB as XGBoost Model
    participant FIS as Fuzzy Logic FIS

    User->>React: Click district on map
    React->>API: GET /api/predict/RJ-Jaipur
    API->>DB: SELECT features WHERE district_id='RJ-Jaipur'
    DB-->>API: Feature vector (10 values)
    API->>XGB: model.predict(features)
    XGB-->>API: predicted_gwl = [8.5, 8.9, 9.4, 10.1, 10.8, 11.2]
    API->>FIS: compute_crisis_score(rainfall_deficit, depletion_rate)
    FIS-->>API: score=72, tier="Warning"
    API-->>React: JSON response
    React-->>User: Display score badge + forecast chart
```

---

## 4. Sequence Diagram — Policy Simulation

```mermaid
sequenceDiagram
    participant User as Policy Maker
    participant React as React Frontend
    participant API as Flask API
    participant FIS as Fuzzy Logic FIS

    User->>React: Adjust rainfall slider (-20%)
    User->>React: Adjust extraction slider (+10%)
    User->>React: Click "Simulate"
    React->>API: POST /api/simulate {district_id, rainfall: -20, extraction: +10}
    API->>FIS: compute_crisis_score(adjusted_deficit, adjusted_depletion)
    FIS-->>API: simulated_score=81, tier="Crisis"
    API-->>React: {baseline: 72, simulated: 81, delta: +9}
    React-->>User: Show before/after comparison
```

---

## 5. Activity Diagram — Data Pipeline

```mermaid
flowchart TD
    A[Start] --> B[Download CGWB CSV]
    B --> C[Download IMD Rainfall]
    C --> D[Download ERA5 Climate]
    D --> E[Ingest CGWB into PostgreSQL]
    E --> F[Ingest IMD into PostgreSQL]
    F --> G[Ingest ERA5 into PostgreSQL]
    G --> H{All 3 sources loaded?}
    H -->|No| I[Log missing source warning]
    I --> J[Continue with available data]
    H -->|Yes| J
    J --> K[Run Preprocessing Pipeline]
    K --> L[Linear Interpolation]
    L --> M[SARIMA Gap-Fill]
    M --> N[MinMaxScaler Normalization]
    N --> O[Feature Engineering - 10 features]
    O --> P[Save features_matrix.csv]
    P --> Q[Train Linear Regression]
    Q --> R[Train ANN Classifier]
    R --> S[Train XGBoost]
    S --> T[Compute Fuzzy Logic Scores]
    T --> U[Store predictions in DB]
    U --> V[End]
```

---

## 6. Component Diagram

```mermaid
flowchart LR
    subgraph "Data Layer"
        CGWB[(CGWB CSV)]
        IMD[(IMD CSV)]
        ERA5[(ERA5 NetCDF)]
        PG[(PostgreSQL)]
    end

    subgraph "Processing Layer"
        ING[Data Ingestion]
        PP[Preprocessing Pipeline]
        FE[Feature Engineering]
    end

    subgraph "Model Layer"
        LR[Linear Regression]
        ANN[Perceptron ANN]
        XGB[XGBoost]
        FIS[Fuzzy Logic FIS]
    end

    subgraph "API Layer"
        FLASK[Flask API Server]
        H["/health"]
        PR["/predict"]
        HI["/history"]
        AL["/alerts"]
        SI["/simulate"]
    end

    subgraph "Presentation Layer"
        MAP[Leaflet Choropleth]
        CHART[Recharts Forecast]
        ALERT[Alert Cards]
        SIM[Policy Simulator]
    end

    CGWB --> ING
    IMD --> ING
    ERA5 --> ING
    ING --> PG
    PG --> PP
    PP --> FE
    FE --> LR
    FE --> ANN
    FE --> XGB
    FE --> FIS
    LR --> FLASK
    XGB --> FLASK
    FIS --> FLASK
    FLASK --> MAP
    FLASK --> CHART
    FLASK --> ALERT
    FLASK --> SIM
```

---

## 7. ER Diagram (Database)

```mermaid
erDiagram
    DISTRICTS ||--o{ RAW_DATA : has
    DISTRICTS ||--o{ FEATURES : has
    DISTRICTS ||--o{ PREDICTIONS : has
    DISTRICTS ||--o{ CRISIS_SCORES : has

    DISTRICTS {
        varchar district_id PK
        varchar district_name
        varchar state
        varchar agro_climatic_zone
        varchar geojson_name
    }

    RAW_DATA {
        serial id PK
        varchar district_id FK
        date date
        varchar source
        varchar metric
        float value
    }

    FEATURES {
        serial id PK
        varchar district_id FK
        date date
        float GWL_current
        float GWL_lag_3mo
        float GWL_lag_6mo
        float rainfall_current
        float rainfall_3mo_avg
        float monsoon_deficit_pct
        float temperature
        float evapotranspiration
        float water_balance_proxy
        varchar crop_season_flag
        float data_readiness_score
    }

    PREDICTIONS {
        serial id PK
        varchar district_id FK
        date forecast_date
        varchar model_type
        float predicted_gwl
        float confidence_lower
        float confidence_upper
    }

    CRISIS_SCORES {
        serial id PK
        varchar district_id FK
        date score_date
        float crisis_score
        varchar tier
        jsonb ensemble_weights
    }
```
