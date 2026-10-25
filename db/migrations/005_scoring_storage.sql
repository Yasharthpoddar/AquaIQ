-- Output-only scoring tables. Also usable in an isolated test schema whose
-- source districts/features are read from public; never clone source data or
-- reuse public serial sequences. Existing legacy output tables are retained.
CREATE TABLE IF NOT EXISTS scoring_runs (
    run_id UUID PRIMARY KEY,
    as_of DATE NOT NULL,
    feature_generation TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_sha256 TEXT NOT NULL,
    district_count INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed')),
    completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scoring_signature TEXT
);

CREATE TABLE IF NOT EXISTS crisis_scores (
    id BIGSERIAL PRIMARY KEY,
    district_id VARCHAR(64) NOT NULL,
    forecast_date DATE NOT NULL,
    aquaiq_score REAL,
    tier TEXT CHECK (tier IN ('Safe','Watch','Warning','Crisis')),
    estimate_type TEXT NOT NULL CHECK (estimate_type IN ('district_level','zone_fallback','insufficient_data')),
    zone_fallback_reason TEXT,
    top_factor_1 TEXT,
    top_factor_2 TEXT,
    top_factor_3 TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_id UUID REFERENCES scoring_runs(run_id),
    last_observed_date DATE,
    feature_generation TEXT,
    model_version TEXT,
    UNIQUE (district_id,forecast_date)
);

CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,
    district_id VARCHAR(64) NOT NULL,
    forecast_date DATE NOT NULL,
    model_name TEXT NOT NULL CHECK (model_name IN ('linear_regression','perceptron','xgboost')),
    predicted_gwl REAL,
    predicted_risk_tier TEXT CHECK (predicted_risk_tier IN ('Safe','Watch','Warning','Crisis')),
    confidence REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_id UUID REFERENCES scoring_runs(run_id),
    origin_date DATE,
    as_of_date DATE,
    model_version TEXT,
    feature_generation TEXT,
    estimate_type TEXT,
    source_zone TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_run_identity ON predictions(run_id,district_id,forecast_date,model_name);
CREATE INDEX IF NOT EXISTS idx_scores_completed_run ON crisis_scores(run_id,district_id);
CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT INTO schema_migrations(version) VALUES ('005_scoring_storage') ON CONFLICT DO NOTHING;
