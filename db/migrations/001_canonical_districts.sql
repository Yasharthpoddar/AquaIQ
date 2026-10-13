-- Migration 001: reconcile only explicitly mapped district identities.
-- Run with run_migration_001.py, which validates the crosswalk and owns the
-- transaction. Unmapped district IDs retain their rows and foreign keys.
-- No source table, mapping table, or foreign-key constraint is truncated.

CREATE TABLE IF NOT EXISTS canonical_migration_runs (
    run_id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    before_counts JSONB NOT NULL,
    after_counts JSONB,
    raw_collapsed_rows BIGINT,
    feature_collapsed_rows BIGINT
);
CREATE TABLE IF NOT EXISTS canonical_migration_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES canonical_migration_runs(run_id),
    table_name TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    row_key JSONB NOT NULL,
    before_rows JSONB NOT NULL,
    after_row JSONB NOT NULL
);

DROP TABLE IF EXISTS pg_temp.migration_001_run;
DROP TABLE IF EXISTS pg_temp.migration_001_raw;
DROP TABLE IF EXISTS pg_temp.migration_001_features;
CREATE TEMP TABLE migration_001_run (run_id BIGINT) ON COMMIT DROP;
WITH inserted AS (
    INSERT INTO canonical_migration_runs(before_counts)
    SELECT jsonb_build_object(
        'districts', (SELECT COUNT(*) FROM districts),
        'raw_data', (SELECT COUNT(*) FROM raw_data),
        'features', (SELECT COUNT(*) FROM features))
    RETURNING run_id
) INSERT INTO migration_001_run SELECT run_id FROM inserted;

-- A canonical row participates only when a mapped alias collides with it.
-- Prefer its existing ID so references and unaggregated metadata survive.
CREATE TEMP TABLE migration_001_raw ON COMMIT DROP AS
WITH affected AS (
    SELECT r.*, COALESCE(m.canonical_id, r.district_id) AS target_id
    FROM raw_data r
    LEFT JOIN legacy_district_ids m ON m.legacy_id = r.district_id
    WHERE COALESCE(m.canonical_id, r.district_id) IN (
        SELECT canonical_id FROM legacy_district_ids
        WHERE legacy_id <> canonical_id
    )
)
SELECT target_id, date, source, metric,
       COALESCE(MIN(id) FILTER (WHERE district_id = target_id), MIN(id)) AS keep_id,
       COUNT(*) AS row_count, AVG(value)::REAL AS mean_value,
       jsonb_agg(to_jsonb(affected) - 'target_id' ORDER BY id) AS before_rows
FROM affected
GROUP BY target_id, date, source, metric;

CREATE TEMP TABLE migration_001_features ON COMMIT DROP AS
WITH affected AS (
    SELECT f.*, COALESCE(m.canonical_id, f.district_id) AS target_id
    FROM features f
    LEFT JOIN legacy_district_ids m ON m.legacy_id = f.district_id
    WHERE COALESCE(m.canonical_id, f.district_id) IN (
        SELECT canonical_id FROM legacy_district_ids
        WHERE legacy_id <> canonical_id
    )
)
SELECT target_id, date,
       COALESCE(MIN(id) FILTER (WHERE district_id = target_id), MIN(id)) AS keep_id,
       COUNT(*) AS row_count,
       AVG(gwl_current)::REAL AS gwl_current,
       AVG(gwl_lag_3mo)::REAL AS gwl_lag_3mo,
       AVG(gwl_lag_6mo)::REAL AS gwl_lag_6mo,
       AVG(rainfall_current)::REAL AS rainfall_current,
       AVG(rainfall_3mo_avg)::REAL AS rainfall_3mo_avg,
       AVG(monsoon_deficit_pct)::REAL AS monsoon_deficit_pct,
       AVG(temperature)::REAL AS temperature,
       AVG(evapotranspiration)::REAL AS evapotranspiration,
       AVG(water_balance_proxy)::REAL AS water_balance_proxy,
       AVG(data_readiness_score)::REAL AS data_readiness_score,
       -- Crop season, generation, observation provenance, and any future
       -- metadata columns must agree. Differing generations cannot be averaged.
       COUNT(DISTINCT (to_jsonb(affected) - ARRAY[
           'id', 'district_id', 'target_id', 'gwl_current', 'gwl_lag_3mo',
           'gwl_lag_6mo', 'rainfall_current', 'rainfall_3mo_avg',
           'monsoon_deficit_pct', 'temperature', 'evapotranspiration',
           'water_balance_proxy', 'data_readiness_score'])) AS metadata_variants,
       jsonb_agg(to_jsonb(affected) - 'target_id' ORDER BY id) AS before_rows
FROM affected
GROUP BY target_id, date;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM migration_001_features WHERE metadata_variants > 1) THEN
        RAISE EXCEPTION 'Feature collisions contain conflicting provenance or season; rebuild features from canonical raw data instead of averaging them';
    END IF;
END $$;

-- Delete only the audited duplicate rows. Every other row retains its ID.
DELETE FROM raw_data r
USING migration_001_raw g
WHERE r.id <> g.keep_id
  AND r.date = g.date AND r.source = g.source AND r.metric = g.metric
  AND COALESCE((SELECT canonical_id FROM legacy_district_ids m
                WHERE m.legacy_id = r.district_id), r.district_id) = g.target_id;
UPDATE raw_data r SET value = g.mean_value
FROM migration_001_raw g WHERE r.id = g.keep_id AND g.row_count > 1;
UPDATE raw_data r SET district_id = m.canonical_id
FROM legacy_district_ids m
WHERE r.district_id = m.legacy_id AND m.legacy_id <> m.canonical_id;

DELETE FROM features f
USING migration_001_features g
WHERE f.id <> g.keep_id AND f.date = g.date
  AND COALESCE((SELECT canonical_id FROM legacy_district_ids m
                WHERE m.legacy_id = f.district_id), f.district_id) = g.target_id;
UPDATE features f SET
    gwl_current = g.gwl_current, gwl_lag_3mo = g.gwl_lag_3mo,
    gwl_lag_6mo = g.gwl_lag_6mo, rainfall_current = g.rainfall_current,
    rainfall_3mo_avg = g.rainfall_3mo_avg,
    monsoon_deficit_pct = g.monsoon_deficit_pct,
    temperature = g.temperature, evapotranspiration = g.evapotranspiration,
    water_balance_proxy = g.water_balance_proxy,
    data_readiness_score = g.data_readiness_score
FROM migration_001_features g WHERE f.id = g.keep_id AND g.row_count > 1;
UPDATE features f SET district_id = m.canonical_id
FROM legacy_district_ids m
WHERE f.district_id = m.legacy_id AND m.legacy_id <> m.canonical_id;

INSERT INTO canonical_migration_audit(
    run_id, table_name, canonical_id, row_key, before_rows, after_row)
SELECT run.run_id, 'raw_data', g.target_id,
       jsonb_build_object('date', g.date, 'source', g.source, 'metric', g.metric),
       g.before_rows, to_jsonb(r)
FROM migration_001_raw g JOIN raw_data r ON r.id = g.keep_id
CROSS JOIN migration_001_run run WHERE g.row_count > 1;
INSERT INTO canonical_migration_audit(
    run_id, table_name, canonical_id, row_key, before_rows, after_row)
SELECT run.run_id, 'features', g.target_id, jsonb_build_object('date', g.date),
       g.before_rows, to_jsonb(f)
FROM migration_001_features g JOIN features f ON f.id = g.keep_id
CROSS JOIN migration_001_run run WHERE g.row_count > 1;

-- Unmapped numeric districts are valid master records and must survive too.
DELETE FROM districts d USING legacy_district_ids m
WHERE d.district_id = m.legacy_id AND m.legacy_id <> m.canonical_id
  AND NOT EXISTS (SELECT 1 FROM raw_data r WHERE r.district_id = d.district_id)
  AND NOT EXISTS (SELECT 1 FROM features f WHERE f.district_id = d.district_id)
  AND NOT EXISTS (SELECT 1 FROM predictions p WHERE p.district_id = d.district_id)
  AND NOT EXISTS (SELECT 1 FROM crisis_scores s WHERE s.district_id = d.district_id);

UPDATE canonical_migration_runs r SET
    completed_at = CURRENT_TIMESTAMP,
    after_counts = jsonb_build_object(
        'districts', (SELECT COUNT(*) FROM districts),
        'raw_data', (SELECT COUNT(*) FROM raw_data),
        'features', (SELECT COUNT(*) FROM features)),
    raw_collapsed_rows = COALESCE((SELECT SUM(row_count - 1) FROM migration_001_raw), 0),
    feature_collapsed_rows = COALESCE((SELECT SUM(row_count - 1) FROM migration_001_features), 0)
FROM migration_001_run run WHERE r.run_id = run.run_id;

DO $$ DECLARE r canonical_migration_runs%ROWTYPE; BEGIN
    SELECT audit.* INTO r FROM canonical_migration_runs audit
    JOIN migration_001_run run ON run.run_id = audit.run_id;
    IF (r.before_counts->>'raw_data')::BIGINT - r.raw_collapsed_rows
         <> (r.after_counts->>'raw_data')::BIGINT
       OR (r.before_counts->>'features')::BIGINT - r.feature_collapsed_rows
         <> (r.after_counts->>'features')::BIGINT THEN
        RAISE EXCEPTION 'Canonical migration loss audit failed; transaction must roll back';
    END IF;
END $$;
