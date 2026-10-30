-- Candidate-only state median forecasts. These tables have no foreign keys or
-- write paths into production district/state forecast generations.
CREATE TABLE IF NOT EXISTS state_median_generations (
    generation_id UUID PRIMARY KEY,
    generation_signature TEXT NOT NULL UNIQUE,
    as_of DATE NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'experimental'),
    states_total INTEGER NOT NULL CHECK (states_total = 36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_state_median_generation_vintage
    ON state_median_generations(as_of, created_at DESC);

CREATE TABLE IF NOT EXISTS state_median_forecast_records (
    generation_id UUID NOT NULL REFERENCES state_median_generations(generation_id),
    state_id VARCHAR(2) NOT NULL,
    as_of DATE NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('forecast', 'insufficient_data', 'model_unavailable')),
    training_cutoff DATE,
    model_sha256 TEXT,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (generation_id, state_id)
);
CREATE INDEX IF NOT EXISTS idx_state_median_forecast_lookup
    ON state_median_forecast_records(state_id, as_of);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO schema_migrations(version) VALUES ('006_state_median_forecasts') ON CONFLICT DO NOTHING;
