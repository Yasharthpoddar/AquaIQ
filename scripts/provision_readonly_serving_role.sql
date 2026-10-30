-- ============================================================================
-- AquaIQ — Production Serving Role Least-Privilege Provisioning Procedure
-- ============================================================================
--
-- PURPOSE:
-- Provision or reconfigure a strictly read-only database identity for the
-- AquaIQ serving layer (Waitress / Flask API).
--
-- SAFETY BOUNDARIES:
-- - This script must be executed by an authorized PostgreSQL DBA or superuser.
-- - It must NOT be run automatically during application startup or CI.
-- - No passwords are hardcoded in this script. The DBA must set a secure,
--   randomly generated password using ALTER ROLE ... WITH PASSWORD.
-- - This script does NOT alter or revoke privileges of the administrative/migration role.
-- - Do NOT run against production without explicit change-window authorization.
--
-- USAGE VIA PSQL:
--   psql -h <host> -p <port> -U <dba_user> -d <target_db> -f scripts/provision_readonly_serving_role.sql
--
-- ============================================================================

\set ON_ERROR_STOP on

-- Display current execution context
SELECT current_database() AS target_database, current_user AS executing_user;

-- ----------------------------------------------------------------------------
-- 1. Create or ensure least-privilege role attributes
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'aquaiq_serving_readonly') THEN
        CREATE ROLE aquaiq_serving_readonly WITH
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOREPLICATION;
        RAISE NOTICE 'Role aquaiq_serving_readonly created with LOGIN (password must be set separately).';
    ELSE
        ALTER ROLE aquaiq_serving_readonly WITH
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOREPLICATION;
        RAISE NOTICE 'Role aquaiq_serving_readonly already exists; reset attributes to least-privilege.';
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 2. Database connection permissions: strictly CONNECT only
-- ----------------------------------------------------------------------------
REVOKE ALL ON DATABASE current_database() FROM aquaiq_serving_readonly;
GRANT CONNECT ON DATABASE current_database() TO aquaiq_serving_readonly;

-- ----------------------------------------------------------------------------
-- 3. Schema-level permissions: strictly USAGE only (NO CREATE)
-- ----------------------------------------------------------------------------
-- The serving role must never be permitted to create schemas, tables or types.
-- USAGE allows lookup of objects in the schema; CREATE is strictly denied.
REVOKE ALL ON SCHEMA public FROM aquaiq_serving_readonly;
GRANT USAGE ON SCHEMA public TO aquaiq_serving_readonly;

-- If a dedicated non-public state-median schema is configured (e.g., aquaiq_states),
-- execute USAGE grant for that schema as well:
-- GRANT USAGE ON SCHEMA <dedicated_schema> TO aquaiq_serving_readonly;

-- ----------------------------------------------------------------------------
-- 4. State Median Release tables: strictly SELECT only
-- ----------------------------------------------------------------------------
-- Defined in db/migrations/006_state_median_forecasts.sql and 007_state_median_publication.sql:
--   1. state_median_generations
--   2. state_median_forecast_records
--   3. state_median_releases
--   4. state_median_publications
--   5. state_median_active_release

REVOKE ALL ON TABLE
    public.state_median_generations,
    public.state_median_forecast_records,
    public.state_median_releases,
    public.state_median_publications,
    public.state_median_active_release
FROM aquaiq_serving_readonly;

GRANT SELECT ON TABLE
    public.state_median_generations,
    public.state_median_forecast_records,
    public.state_median_releases,
    public.state_median_publications,
    public.state_median_active_release
TO aquaiq_serving_readonly;

-- ----------------------------------------------------------------------------
-- 5. District, Feature, and Legacy Serving tables: strictly SELECT only
-- ----------------------------------------------------------------------------
-- Required by /api/health, /api/districts, /api/scores, and legacy routes.
REVOKE ALL ON TABLE
    public.districts,
    public.raw_data,
    public.features,
    public.forecast_generations,
    public.forecast_records,
    public.score_publications
FROM aquaiq_serving_readonly;

GRANT SELECT ON TABLE
    public.districts,
    public.raw_data,
    public.features,
    public.forecast_generations,
    public.forecast_records,
    public.score_publications
TO aquaiq_serving_readonly;

-- ----------------------------------------------------------------------------
-- 6. Sequences: revoke all access
-- ----------------------------------------------------------------------------
-- The serving role only performs SELECT queries and never generates IDs.
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aquaiq_serving_readonly;

-- ----------------------------------------------------------------------------
-- 7. Audit verification: check effective table privileges
-- ----------------------------------------------------------------------------
SELECT
    table_schema,
    table_name,
    privilege_type
FROM information_schema.table_privileges
WHERE grantee = 'aquaiq_serving_readonly'
ORDER BY table_schema, table_name, privilege_type;

-- ----------------------------------------------------------------------------
-- DBA ACTION REQUIRED AFTER RUNNING THIS SCRIPT:
-- ----------------------------------------------------------------------------
-- Set the private password for the role:
--   ALTER ROLE aquaiq_serving_readonly WITH PASSWORD '<REPLACE_WITH_PRIVATE_RANDOM_PASSWORD>';
--
-- Configure this credential in deploy/.env on the target host:
--   POSTGRES_USER=aquaiq_serving_readonly
--   POSTGRES_PASSWORD=<the_private_password>
-- ============================================================================

