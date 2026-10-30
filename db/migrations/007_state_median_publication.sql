-- Independent release lifecycle for the versioned States API. Migration 006
-- remains the immutable candidate snapshot store; district outputs are unused.
CREATE TABLE IF NOT EXISTS state_median_releases (
    release_id UUID PRIMARY KEY,
    generation_id UUID NOT NULL REFERENCES state_median_generations(generation_id),
    release_signature TEXT NOT NULL UNIQUE,
    as_of DATE NOT NULL,
    model_version TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    manifest_json JSONB NOT NULL,
    summary_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_state_median_release_origin ON state_median_releases(as_of);
CREATE TABLE IF NOT EXISTS state_median_publications (
    publication_id BIGSERIAL PRIMARY KEY,
    release_id UUID NOT NULL REFERENCES state_median_releases(release_id),
    previous_release_id UUID REFERENCES state_median_releases(release_id),
    action TEXT NOT NULL CHECK (action IN ('publish', 'rollback')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_state_median_published_release ON state_median_publications(release_id);
CREATE TABLE IF NOT EXISTS state_median_active_release (
    product TEXT PRIMARY KEY CHECK (product = 'state_median_groundwater_12m_forecast'),
    release_id UUID NOT NULL REFERENCES state_median_releases(release_id),
    publication_id BIGINT NOT NULL REFERENCES state_median_publications(publication_id)
);
INSERT INTO schema_migrations(version) VALUES ('007_state_median_publication') ON CONFLICT DO NOTHING;
