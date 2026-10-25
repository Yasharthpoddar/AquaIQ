-- AquaIQ Migration 004: Persistent XGBoost Forecast Storage
-- Stores district-level 12-month XGBoost predictions, state-level aggregated
-- forecasts, and nationwide summaries with complete input provenance and lifecycle states.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Forecast generation lifecycle and input provenance
CREATE TABLE IF NOT EXISTS forecast_generations (
    generation_id           UUID PRIMARY KEY,
    status                  TEXT NOT NULL CHECK(status IN ('building', 'validated', 'published', 'failed', 'superseded')),
    as_of                   DATE NOT NULL,
    forecast_origin         DATE NOT NULL,
    horizon_months          INTEGER NOT NULL DEFAULT 12,
    model_id                TEXT NOT NULL,
    model_version           TEXT NOT NULL,
    model_sha256            TEXT NOT NULL,
    model_card_sha256       TEXT NOT NULL,
    feature_generation_id   TEXT NOT NULL,
    feature_data_sha256     TEXT NOT NULL,
    district_registry_hash  TEXT NOT NULL,
    district_crosswalk_hash TEXT NOT NULL,
    state_registry_hash     TEXT NOT NULL,
    config_hash             TEXT NOT NULL,
    generation_signature    TEXT NOT NULL,
    districts_total         INTEGER NOT NULL DEFAULT 0,
    districts_forecast      INTEGER NOT NULL DEFAULT 0,
    districts_insufficient  INTEGER NOT NULL DEFAULT 0,
    districts_unavailable   INTEGER NOT NULL DEFAULT 0,
    states_total            INTEGER NOT NULL DEFAULT 0,
    states_available        INTEGER NOT NULL DEFAULT 0,
    states_insufficient     INTEGER NOT NULL DEFAULT 0,
    started_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at            TIMESTAMPTZ,
    published_at            TIMESTAMPTZ,
    superseded_at           TIMESTAMPTZ,
    notes                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_forecast_generations_lookup
    ON forecast_generations(as_of, status, generation_signature);

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_published_generation
    ON forecast_generations(as_of) WHERE status = 'published';

-- District forecast headers and cached response payloads
CREATE TABLE IF NOT EXISTS district_forecast_records (
    id                      BIGSERIAL PRIMARY KEY,
    generation_id           UUID NOT NULL REFERENCES forecast_generations(generation_id) ON DELETE CASCADE,
    district_id             VARCHAR(64) NOT NULL,
    as_of                   DATE NOT NULL,
    forecast_origin         DATE NOT NULL,
    status                  TEXT NOT NULL CHECK(status IN ('forecast', 'insufficient_data', 'model_unavailable')),
    estimate_type           TEXT,
    source_zone             TEXT,
    zone_fallback_reason    TEXT,
    last_observed_date      DATE,
    last_observed_gwl       REAL,
    data_age_months         INTEGER,
    estimated_current_gwl   REAL,
    current_depth_basis     TEXT,
    message                 TEXT,
    weather_basis_json      JSONB,
    payload_json            JSONB NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(generation_id, district_id)
);

CREATE INDEX IF NOT EXISTS idx_district_forecast_lookup
    ON district_forecast_records(generation_id, district_id);

-- Normalized monthly predictions for district forecasts (M+1 to M+12)
CREATE TABLE IF NOT EXISTS district_forecast_horizons (
    id                      BIGSERIAL PRIMARY KEY,
    generation_id           UUID NOT NULL REFERENCES forecast_generations(generation_id) ON DELETE CASCADE,
    district_id             VARCHAR(64) NOT NULL,
    horizon                 INTEGER NOT NULL CHECK(horizon >= 1 AND horizon <= 12),
    target_date             DATE NOT NULL,
    target_month            VARCHAR(7) NOT NULL,
    predicted_gwl           REAL NOT NULL,
    delta_from_current_m    REAL NOT NULL,
    rainfall_mm             REAL,
    temperature_c           REAL,
    evapotranspiration_mm   REAL,
    persistence_gwl         REAL,
    seasonal_gwl            REAL,
    seasonal_reference_date DATE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(generation_id, district_id, horizon)
);

CREATE INDEX IF NOT EXISTS idx_district_horizons_lookup
    ON district_forecast_horizons(generation_id, district_id, horizon);

-- State forecast records
CREATE TABLE IF NOT EXISTS state_forecast_records (
    id                          BIGSERIAL PRIMARY KEY,
    generation_id               UUID NOT NULL REFERENCES forecast_generations(generation_id) ON DELETE CASCADE,
    state_id                    VARCHAR(10) NOT NULL,
    as_of                       DATE NOT NULL,
    forecast_origin             DATE NOT NULL,
    status                      TEXT NOT NULL CHECK(status IN ('available', 'insufficient_data', 'model_unavailable', 'forecast')),
    panel_id                    TEXT,
    total_districts             INTEGER NOT NULL,
    contributing_districts      INTEGER NOT NULL,
    district_coverage_pct       REAL NOT NULL,
    contributing_district_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    excluded_districts          JSONB NOT NULL DEFAULT '[]'::jsonb,
    estimated_current_gwl_m_bgl REAL,
    last_observed_date          DATE,
    last_observed_gwl_m_bgl     REAL,
    forecast_12m_gwl_m_bgl      REAL,
    projected_change_12m_m      REAL,
    message                     TEXT,
    payload_json                JSONB NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(generation_id, state_id)
);

CREATE INDEX IF NOT EXISTS idx_state_forecast_lookup
    ON state_forecast_records(generation_id, state_id);

-- Normalized monthly predictions for state forecasts (M+1 to M+12)
CREATE TABLE IF NOT EXISTS state_forecast_horizons (
    id                      BIGSERIAL PRIMARY KEY,
    generation_id           UUID NOT NULL REFERENCES forecast_generations(generation_id) ON DELETE CASCADE,
    state_id                VARCHAR(10) NOT NULL,
    horizon                 INTEGER NOT NULL CHECK(horizon >= 1 AND horizon <= 12),
    target_date             DATE NOT NULL,
    target_month            VARCHAR(7) NOT NULL,
    predicted_gwl           REAL NOT NULL,
    delta_from_current_m    REAL NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(generation_id, state_id, horizon)
);

CREATE INDEX IF NOT EXISTS idx_state_horizons_lookup
    ON state_forecast_horizons(generation_id, state_id, horizon);

-- Complete nationwide summary cache record
CREATE TABLE IF NOT EXISTS nationwide_summary_records (
    generation_id                   UUID PRIMARY KEY REFERENCES forecast_generations(generation_id) ON DELETE CASCADE,
    as_of                           DATE NOT NULL,
    total_states                    INTEGER NOT NULL,
    available_states_count          INTEGER NOT NULL,
    insufficient_data_states_count  INTEGER NOT NULL,
    payload_json                    JSONB NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_migrations(version) VALUES('004_xgboost_forecast_storage') ON CONFLICT DO NOTHING;
