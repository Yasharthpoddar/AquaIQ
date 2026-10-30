# State median r2 database readiness audit

Audit date: **2026-10-29**. This is local evidence and conditional operator
guidance. No production migration, staging, publication, permission change or
deployment was performed. The production target remains unidentified.

| Check | Result | Evidence / limit |
|---|---|---|
| Actual r2 stage and integrity | PASS | 36 verified records, 34 forecasts, 408 monthly values, methods 17/17/2 |
| r2 publication boundary | PASS | Zero events and active-pointer rows; normal HTTP rejects its staged UUID |
| Atomic pointer, expected-active and rollback | PASS | Fresh isolated PostgreSQL regression tests, including failure inside publication |
| Inspected local connection is read-only | FAIL | `aquaiq_user` owns all five release tables and has DML/TRUNCATE and schema CREATE |
| Actual production serving role | UNVERIFIED | No approved target or private deployment configuration was supplied |
| Fresh local backup and archive readability | PASS | New complete custom-format dump; `pg_dump` and `pg_restore --list` exited 0 |
| Full independent restore | BLOCKED | Current local role has neither CREATEDB nor superuser; no fresh recovery DB or DBA credentials supplied |
| Production backup/recovery | UNVERIFIED | The verified source is the local development DB, not an identified production target |

## Actual database and staged release

The inspected connection is `aquaiq` on verified loopback `::1`, port 5432,
PostgreSQL 18.1 for Windows. Its inspected size was 391,149,285 bytes. The
development connection role is `aquaiq_user`, not a superuser and without
CREATEDB or CREATEROLE. It nevertheless owns the release tables and can create
objects in the inspected median schema and `public`. It must **not** be reused
as a production serving identity.

The supplied stage UUID was directly verified:

- Schema: `aquaiq_test_state_median_coverage_20261029`.
- Release UUID: `789ce3b5-3170-5866-9ce2-c0ec2f0b1b59`.
- Candidate generation UUID: `75fc4bb1-5766-51bc-be71-1462c98da44e`.
- Artifact: `2026.10.29-r2`, vintage `2026-10-29`.
- 17 XGBoost states, 17 persistence states, LA/LD alone without observations.
- Publication events: **0**. Active-pointer rows: **0**.

These are isolated-test identifiers, not proposed production identifiers.
`_verified_release` independently validated the stored snapshot and manifest.
The parsed artifact manifest equals stored `manifest_json` exactly.

The two manifest digests use different byte representations:

| Digest | Value and use |
|---|---|
| Artifact file bytes | `8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3`; runtime expected hash and all 36 stored detail payloads' `release_manifest_sha256` |
| Canonical manifest JSON | `c4015b766068d83510e468699052106f99b39407316fb5d2a8c8413580bcfab7`; database `state_median_releases.manifest_sha256` |

Canonical JSON means UTF-8 `json.dumps(manifest, sort_keys=True,
separators=(',', ':'), allow_nan=False)`. The HTTP summary/detail contract does
not expose a separate top-level canonical `manifest_sha256`. r2 is unpublished,
so its verified stored details are not available through ordinary HTTP. The
different hashes do not indicate corruption and were not rewritten.

## Publication and HTTP checks

The existing isolated r1 publication remains readable at UUID
`eaabeba7-a554-59a6-9110-726221e63cb2` in
`aquaiq_test_state_median_primary_20261029`. Actual loopback HTTP probes made
**89 requests** across two temporary local servers: registry/summary and all 36
pinned r1 details succeeded; all 36 staged-r2 detail requests returned 503.
Missing vintages, explicit model mismatch and an injected storage corruption
also failed explicitly. The tested servers neither inferred nor published.

The existing publication code revalidates the complete release inside a
transaction, takes its advisory lock, checks the exact expected active UUID,
appends an event and switches the pointer. Rollback requires a previously
published immutable target. Normal API and startup code have no migration or
publication call. Events are append-only through application behavior; table
owners/DBAs can edit them. Effective privilege separation is therefore a
deployment gate, not a property guaranteed by the table definitions alone.

## Read-only credential acceptance

Run these checks **as the actual serving login**, against the approved target
and schema. Running them as an owner or an administrative account does not
verify serving credentials. No grants were changed in this audit.

```sql
SELECT current_database(), session_user, current_user,
       rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls,
       has_database_privilege(current_user,current_database(),'CONNECT') AS db_connect,
       has_database_privilege(current_user,current_database(),'CREATE') AS db_create
FROM pg_roles WHERE rolname=current_user;

-- In psql, set median_schema explicitly with -v median_schema=APPROVED_SCHEMA.
SELECT has_schema_privilege(current_user,:'median_schema','USAGE') AS schema_usage,
       has_schema_privilege(current_user,:'median_schema','CREATE') AS schema_create;

WITH required(name) AS (VALUES
 ('state_median_generations'),('state_median_forecast_records'),
 ('state_median_releases'),('state_median_publications'),('state_median_active_release'))
SELECT t.name, pg_get_userbyid(c.relowner) AS owner,
       pg_has_role(current_user,c.relowner,'USAGE') AS owns_or_inherits_owner,
       has_table_privilege(current_user,c.oid,'SELECT') AS can_select,
       has_table_privilege(current_user,c.oid,'INSERT') AS can_insert,
       has_table_privilege(current_user,c.oid,'UPDATE') AS can_update,
       has_table_privilege(current_user,c.oid,'DELETE') AS can_delete,
       has_table_privilege(current_user,c.oid,'TRUNCATE') AS can_truncate,
       has_table_privilege(current_user,c.oid,'TRIGGER') AS can_trigger,
       has_table_privilege(current_user,c.oid,'REFERENCES') AS can_reference
FROM required t LEFT JOIN pg_namespace n ON n.nspname=:'median_schema'
LEFT JOIN pg_class c ON c.relnamespace=n.oid AND c.relname=t.name AND c.relkind='r'
ORDER BY t.name;
```

Require all five real tables, CONNECT/USAGE/SELECT, and no ownership, effective
writer privileges, schema/database CREATE or elevated role attributes. A DBA
must additionally inspect role memberships, sequence USAGE/UPDATE, executable
SECURITY DEFINER functions, and write capabilities in legacy/source/scoring
schemas. `schema_migrations` must not be writable by serving credentials.
The retained `permissions_gate.sql` is a **partial diagnostic**: it checks the
five tables, basic DML, owner inheritance, schema/database creation and role
attributes; it does not establish all of those additional security properties.
Its local `read_only_median_gate_pass` result was **false**.

No separate serving-role credentials or target role grants were available.
Consequently the audit cannot prove that a real production login is unable to
migrate, stage, publish or roll back. That proof requires the authorized DBA to
provision the separate owner/release-writer and read-only roles, then repeat
the catalog checks and denied-write tests in a disposable target-like database.

## Backup and recovery

PostgreSQL clients exist at `C:/Program Files/PostgreSQL/18/bin`; they are not
on the inspected shell PATH. All three clients report version 18.1.

The pre-existing `data/backup_pre_d1_migration.dump` was modified
`2026-10-12T04:01:18.281774Z`, is 22,464,250 bytes, and has SHA-256
`4c2a3310fe3bd288e8974062b4e3e3bd84a5be2a38fbffefeb96e64c63f87556`.
Its archive list is readable but predates r1/r2 and has no proven full restore.

A new read-only dump of the entire local `aquaiq` database was successfully
created **before** this audit's database integration tests:

- Path: `scratch/state_median_readiness_20261029/db/aquaiq_local_pre_r2_20261029.dump`.
- Started `2026-10-29T15:52:40.737132Z`; completed `2026-10-29T15:52:44.298313Z`.
- Size: **23,619,549 bytes**.
- SHA-256: `9b7c589d57a8cf914f4879ee9356dd0d75b187483e266790a6a61ef9fc072a5e`.
- Default full-database scope without schema filters; 559 archive TOC entries.
- `pg_dump` exit **0**, empty stderr; `pg_restore --list` exit **0**.

Authentication was supplied only through a child-process environment variable,
never a command argument or retained output. Dumps and lists remain in ignored
local scratch storage. This is a local backup, not proof that the unknown
production database is backed up. No restore was attempted over an existing DB.

The supplied role cannot create a fresh recovery DB. The DBA must create a
separate, empty, appropriately owned recovery DB and provide authorized access.
Conditional recovery commands, after independently verifying source/recovery
host and database identities, are:

```powershell
# Configure approved PGHOST/PGPORT/PGUSER and private authentication separately.
# These variables must name the DBA-provisioned empty recovery DB and real dump.
& 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe' --list $backupPath
if ($LASTEXITCODE -ne 0) { throw 'Archive unreadable' }
& 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe' --exit-on-error --single-transaction --dbname=$recoveryDatabase $backupPath
if ($LASTEXITCODE -ne 0) { throw 'Full restore failed; do not declare recovery verified' }
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -X --dbname=$recoveryDatabase -v ON_ERROR_STOP=1 -c 'SELECT current_database(),inet_server_addr(),inet_server_port();'
```

Preserving dump ownership/ACLs requires the referenced owner/grantee roles and
appropriate restore privileges. `--no-owner --no-privileges` is an explicitly
different recovery plan requiring separate grants; it does not verify restored
production permissions. Check restored public legacy/source/score tables, all
five median tables, exact generation/pointer IDs and hashes against the source
snapshot, then run matching application/file assets read-only against recovery.
Archive readability alone is not successful restoration. No full restore result
or production recoverability claim is made here.

## Fresh tests and evidence

The current focused run executed **168 tests, all passed, zero skipped**, in
137.54 seconds: 166 state-model/policy/source-audit/evaluation/storage/API/
release/deployment checks plus two real legacy/district API regression tests.
The latter freshly recomputed the 725-district fixture. This is one combined
run, not a sum of historical overlapping 166/15-test reports.

The test process alone set `AQUAIQ_FORECAST_SCHEMA=''` before pytest to prevent
the development `.env` namespace from overriding the existing private legacy
test fixture. Global environment files were untouched. All database writes
were isolated fixtures; no actual r2 publication was created. A before/after
check verified **87 protected files unchanged**, including `.env`, config,
district/Home code, every artifact and checkpoint.

Evidence directory: `scratch/state_median_readiness_20261029/db/`:
`local_database_audit.json`, `actual_stage_integrity.json`,
`http_publication.json`, `backup_audit.json`, archive lists,
`permissions_gate.sql`, `permissions_gate_local.txt`,
`focused_postgres_and_legacy.xml`, and `protected_bytes_and_test_counts.json`.
The production runbook owns the conditional migration/publication/CAS/rollback
sequence. Production readiness remains blocked on target identification,
credential isolation and a demonstrated independent full restore.
