-- AquaIQ database schema
-- 5 core tables from the SRS + 1 districts master table (Week 2 task).
-- Run via: python3 db/init_db.py

-- District master table — 640+ districts, built Week 2.
-- geojson_name exists because CGWB and GeoJSON district names don't always match verbatim.
CREATE TABLE IF NOT EXISTS districts (
    district_id         TEXT PRIMARY KEY,
    district_name       TEXT NOT NULL,
    state                TEXT NOT NULL,
    agro_climatic_zone  TEXT,
    geojson_name         TEXT
);

-- Raw ingested readings from all 3 sources. One row per district/date/source/metric.
CREATE TABLE IF NOT EXISTS raw_data (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id  TEXT NOT NULL REFERENCES districts(district_id),
    date         TEXT NOT NULL,                -- 'YYYY-MM-01', monthly
    source       TEXT NOT NULL CHECK(source IN ('CGWB', 'IMD', 'ERA5')),
    metric       TEXT NOT NULL,                -- 'GWL', 'rainfall', 'temperature', 'evapotranspiration'
    value        REAL,
    UNIQUE(district_id, date, source, metric)
);

-- Engineered 10-feature table. One row per district per month.
CREATE TABLE IF NOT EXISTS features (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id            TEXT NOT NULL REFERENCES districts(district_id),
    date                   TEXT NOT NULL,
    gwl_current             REAL,
    gwl_lag_3mo             REAL,
    gwl_lag_6mo             REAL,
    rainfall_current        REAL,
    rainfall_3mo_avg        REAL,
    monsoon_deficit_pct     REAL,
    temperature             REAL,
    evapotranspiration      REAL,
    water_balance_proxy     REAL,
    crop_season_flag        TEXT CHECK(crop_season_flag IN ('Kharif', 'Rabi', 'Zaid')),
    data_readiness_score    REAL,               -- % of months with valid, non-imputed data
    UNIQUE(district_id, date)
);

-- Model outputs. Every model (LR, Perceptron, LSTM, XGBoost) writes here.
CREATE TABLE IF NOT EXISTS predictions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id          TEXT NOT NULL REFERENCES districts(district_id),
    forecast_date        TEXT NOT NULL,
    model_name           TEXT NOT NULL CHECK(model_name IN ('linear_regression', 'perceptron', 'lstm', 'xgboost')),
    predicted_gwl        REAL,
    predicted_risk_tier  TEXT CHECK(predicted_risk_tier IN ('Safe', 'Watch', 'Warning', 'Crisis')),
    confidence           REAL,
    created_at           TEXT DEFAULT CURRENT_TIMESTAMP
);

-- SHAP attribution, per district per feature per forecast.
CREATE TABLE IF NOT EXISTS shap_values (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id    TEXT NOT NULL REFERENCES districts(district_id),
    forecast_date  TEXT NOT NULL,
    feature_name   TEXT NOT NULL,
    shap_value     REAL,
    feature_value  REAL
);

-- Final ensemble AquaIQ Score — what the dashboard actually reads.
-- estimate_type matters: not every district has enough CGWB history for its
-- own model. Below data_readiness_min_pct (config.yaml), fall back to a
-- zone-level aggregate (same agro_climatic_zone) instead of a fabricated
-- district-specific number. If even the zone lacks data, say so honestly.
CREATE TABLE IF NOT EXISTS crisis_scores (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id           TEXT NOT NULL REFERENCES districts(district_id),
    forecast_date         TEXT NOT NULL,
    aquaiq_score          REAL,                 -- NULL when estimate_type = 'insufficient_data'
    tier                  TEXT CHECK(tier IN ('Safe', 'Watch', 'Warning', 'Crisis')),
    estimate_type         TEXT NOT NULL DEFAULT 'district_level'
                              CHECK(estimate_type IN ('district_level', 'zone_fallback', 'insufficient_data')),
    zone_fallback_reason  TEXT,                 -- e.g. "Only 9 months of CGWB data available (need 24)"
    top_factor_1          TEXT,
    top_factor_2          TEXT,
    top_factor_3          TEXT,
    updated_at            TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(district_id, forecast_date)
);

CREATE INDEX IF NOT EXISTS idx_raw_data_district_date ON raw_data(district_id, date);
CREATE INDEX IF NOT EXISTS idx_features_district_date ON features(district_id, date);
CREATE INDEX IF NOT EXISTS idx_crisis_scores_tier ON crisis_scores(tier);
