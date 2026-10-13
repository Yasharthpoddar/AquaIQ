CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
ALTER TABLE features ADD COLUMN IF NOT EXISTS is_observed BOOLEAN;
ALTER TABLE features ADD COLUMN IF NOT EXISTS is_imputed BOOLEAN;
ALTER TABLE features ADD COLUMN IF NOT EXISTS months_since_observation INTEGER;
ALTER TABLE features ADD COLUMN IF NOT EXISTS feature_generation TEXT;
CREATE TABLE IF NOT EXISTS scoring_runs (
    run_id UUID PRIMARY KEY, as_of DATE NOT NULL, feature_generation TEXT NOT NULL,
    model_version TEXT NOT NULL, model_sha256 TEXT NOT NULL, district_count INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('completed')), completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE crisis_scores ADD COLUMN IF NOT EXISTS run_id UUID REFERENCES scoring_runs(run_id);
ALTER TABLE scoring_runs ADD COLUMN IF NOT EXISTS scoring_signature TEXT;
ALTER TABLE crisis_scores ADD COLUMN IF NOT EXISTS last_observed_date DATE;
ALTER TABLE crisis_scores ADD COLUMN IF NOT EXISTS feature_generation TEXT;
ALTER TABLE crisis_scores ADD COLUMN IF NOT EXISTS model_version TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS run_id UUID REFERENCES scoring_runs(run_id);
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS origin_date DATE;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS as_of_date DATE;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS model_version TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS feature_generation TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS estimate_type TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS source_zone TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_run_identity ON predictions(run_id, district_id, forecast_date, model_name);
CREATE INDEX IF NOT EXISTS idx_scores_completed_run ON crisis_scores(run_id, district_id);
INSERT INTO schema_migrations(version) VALUES('003_pipeline_provenance') ON CONFLICT DO NOTHING;
