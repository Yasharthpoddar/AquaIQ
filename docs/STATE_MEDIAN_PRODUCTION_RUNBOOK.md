# State median r2 production runbook

Audit date: 2026-10-29. **Overall decision: NOT READY.** This document prepares
an operator-controlled release; it is not permission to change production.
The [current readiness report](STATE_MEDIAN_PRODUCTION_READINESS.md) records
executed checks, evidence, failures and remaining gates. The
[coverage report](STATE_MEDIAN_COVERAGE.md) contains all 36 state methods.

## 1. Approved candidate identity

| Item | Required value |
|---|---|
| Artifact directory | `models/artifacts/state_median_releases/20261029-r2` |
| Artifact release | `2026.10.29-r2` |
| Model version | `2.0-state-median-tiered` |
| Policy version | `1.0-state-median-coverage` |
| Vintage | `2026-10-29` |
| Manifest SHA-256 | `8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3` |
| Source generation | `physical-v3-official-c9ade81d95720f91` |
| Source CSV SHA-256 | `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042` |
| Source directory | `data/processed/enrichment/final_release_20261026_v3` |
| Runtime | Python **3.13.15**, NumPy **2.5.4**, pandas **3.0.6**, scikit-learn **1.9.1**, XGBoost **3.4.1** |
| Expected output | 36 responses; 17 XGBoost + 17 persistence + LA/LD no observations; 408 monthly values, Nov 2026–Oct 2027 |

The local stage `789ce3b5-3170-5866-9ce2-c0ec2f0b1b59` lives only in
`aquaiq_test_state_median_coverage_20261029`. It is **not a production
publication or production identifier**. Record the identifier returned by the
authorized target's own staging operation; never copy a test pointer into a
production database. Do not rewrite r1/r2, re-date their vintage, retrain district
models, or treat a successful software check as measured forecast skill.

There are two intentional manifest digest representations. The approved
**file-byte** SHA above is used by runtime configuration and response
`release_manifest_sha256`. The database column
`state_median_releases.manifest_sha256` hashes canonical JSON (sorted keys,
compact separators): r2's value is
`c4015b766068d83510e468699052106f99b39407316fb5d2a8c8413580bcfab7`.
The stored JSON was checked equal to the parsed artifact. Do not compare this
canonical JSON digest directly with the file-byte checksum and call it damage.

All 34 forecast references are older than the nominal three-month reporting
interval: 9–42 months at this vintage. Persistence has no evaluated accuracy.
Product approval must explicitly accept those disclosures. If a later vintage
is required, prepare and review a new immutable artifact.

## 2. Pre-deployment operator gates

Do not continue past local verification until every gate has an owner and
retained evidence:

- Identify the actual hosting platform, host/runtime, HTTPS origin, database
  identity/network, and release window. These are **UNVERIFIED** in this audit.
- Designate separate DBA/release-writer and read-only application identities.
  The inspected local `aquaiq_user` is a table owner with write privileges and
  must not be reused as a production serving role. A dedicated least-privilege
  provisioning procedure is provided in `scripts/provision_readonly_serving_role.sql`
  and verified by `tests/test_state_median_role_safety.py`.
- Choose and explicitly configure an existing, reviewed state-median schema.
  Neither `public` (the Compose default) nor a local `aquaiq_test_*` schema is an
  approved production choice merely because it appears in an example.
  Migration CLI does not create a missing production schema; DBA provisioning
  needs separate authorization. Preserve legacy/district namespaces.
- Obtain a recent full target backup, matching file/config/image backups and a
  successful full restore into a **separate recovery database** following the
  5-step recovery procedure in Section 5. A readable archive or `pg_restore --list`
  alone does not satisfy this gate.
- Build and test the actual target image with the exact runtime, dependencies,
  r2 artifact and data/checkpoint mounts. Record immutable image digests for API
  and web and a source-tree/build-context digest. The checkout is dirty;
  `027ea4969639912ef73e556975edf7c0d10abff8` alone does not identify this build.
- Verify frontend/API compatibility on the target, all 36 pinned responses,
  fallback disclosures, Home/district regressions and desktop/mobile layout.
  Fresh visual browser checks were blocked in this audit; historical screenshots
  are not evidence for the current target.
- Confirm HTTPS certificates, health probes, private logs, alert routing,
  persistent database storage, backup retention and a tested rollback pair
  (old image/configuration plus previously published database release).
- Obtain explicit human authorization for migration/staging/publication and
  deployment. No such production authorization was given for this audit.

## 3. Configuration and credentials

Use the target's approved secret store or a private environment file. Never
commit it or print `docker compose config` without `--quiet`. Do not source the
development `.env` as production configuration. `deploy/environment.example`
has been updated to the approved r2 identity (`2026.10.29-r2`, r2 manifest hash,
`AQUAIQ_PYTHON_IMAGE=python:3.13.15-slim`, and `VITE_STATE_FORECAST_MODE=median`).
Copy it to private `deploy/.env` and replace operator placeholders.

| Variable | Purpose / required target setting |
|---|---|
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB` | Verified target connection; container localhost is not the host DB |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Read-only serving identity (`aquaiq_serving_readonly`); separate privileged operator session for writes |
| `SECRET_KEY` | Private, random, non-placeholder value at least 32 characters |
| `AQUAIQ_STATE_MEDIAN_SCHEMA` | Explicit approved median namespace, isolated from district/legacy selection |
| `AQUAIQ_REQUIRE_STATE_MEDIAN_RELEASE` | `true` |
| `AQUAIQ_STATE_MEDIAN_ARTIFACT_DIR` | `/app/models/artifacts/state_median_releases/20261029-r2` inside API image |
| `AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE` | `2026.10.29-r2` |
| `AQUAIQ_STATE_MEDIAN_MANIFEST_SHA256` | Exact r2 manifest hash above: `8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3` |
| `AQUAIQ_PYTHON_IMAGE` | Target-tested image **digest** providing Python 3.13.15; default `python:3.13.15-slim` |
| `AQUAIQ_DATA_DIR` | Existing absolute host directory containing matching `data/` assets, mounted read-only |
| `AQUAIQ_CHECKPOINT_DIR` | Existing absolute host checkpoint directory, mounted read-only |
| `AQUAIQ_EXPECTED_DISTRICTS` | `725` |
| `AQUAIQ_WEB_PORT` | Reviewed loopback HTTP port behind the target HTTPS reverse proxy |
| `AQUAIQ_CORS_ORIGINS` | Compose uses empty, same-origin access; review any separate-frontend allowlist |
| `AQUAIQ_ENABLE_SYNC_FORECAST_FALLBACK` | Keep `false` for persisted district/legacy serving |
| `VITE_STATE_FORECAST_MODE` | `median` (default tiered release) or `legacy` (mean-based States UI rollback) |

`AQUAIQ_FORECAST_SCHEMA` controls legacy/district snapshots and
`AQUAIQ_SCORING_SCHEMA` controls score storage when running directly. Preserve
their approved values. Current Compose does not forward these variables, so it
uses the existing public/default namespaces. If the actual target needs private
legacy/scoring namespaces, review and test an explicit Compose change before
deployment; setting them only in `deploy/.env` will not forward them by itself.

Read-only role acceptance must check effective privileges, not just direct
grants: CONNECT on the DB, USAGE on required schemas, SELECT on required tables;
no CREATE on the median schema, no ownership, superuser, CREATEROLE, CREATEDB or
inherited writer access, and no INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER/REFERENCES
on its five release tables or sequence writes. Include executable SECURITY
DEFINER functions and database CREATE privilege in the DBA review. Use the
dedicated procedure in `scripts/provision_readonly_serving_role.sql` to provision
the serving role. Only a separately authorized DBA may execute role/grant changes.

## 4. Safe local artifact verification

These commands were exercised locally against supplied matching assets. Run
from the repository root; select a new output directory on each replay.
`generate` without `--test-schema` creates files only, never a DB publication.

```powershell
$medianPython = '.\venv\Scripts\python.exe'
$medianArtifact = 'models/artifacts/state_median_releases/20261029-r2'
$medianSource = 'data/processed/enrichment/final_release_20261026_v3'
$medianManifestHash = '8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3'
& $medianPython -B -m scripts.check_validation_assets
& $medianPython -B -m pip check
& $medianPython -B -m scripts.release_state_median verify --release-dir $medianArtifact --expected-release 2026.10.29-r2 --expected-manifest-sha256 $medianManifestHash
& $medianPython -B -m scripts.release_state_median generate --release-dir $medianArtifact --processed-dir $medianSource --as-of 2026-10-29 --output scratch/readiness_NEW/generation.json
& $medianPython -B -m scripts.audit_state_median_coverage --processed-dir $medianSource --release-dir models/artifacts/state_median_releases/20261029-r1 --as-of 2026-10-29 --generation scratch/readiness_NEW/generation.json --output scratch/readiness_NEW/independent_audit
```

Check `$LASTEXITCODE` after every native command and stop on any failure.
Retain the generated file hash and independent audit, and validate the same
candidate before target staging. Do not run `prepare` over the existing r2.

## 5. Backup and independent recovery verification

**Conditional operator procedure — not executed against a production target.**
Configure PostgreSQL `PGHOST`, `PGPORT`, `PGUSER` and private authentication for
the reviewed target. `POSTGRES_*` application variables alone are not libpq
`PG*` variables. Use a protected password file/secret mechanism; never put a
password or connection URI in command text.

The full verification procedure requires five distinct phases:

### Phase 1: Target database backup creation
Create a full custom-format archive of the active production target:
```powershell
if (!$targetDatabase -or !$backupPath) { throw 'Specify approved target database and backup path' }
if (Test-Path -LiteralPath $backupPath) { throw 'Choose a new non-existing backup path' }
pg_dump --format=custom --dbname=$targetDatabase --file=$backupPath
if ($LASTEXITCODE -ne 0) { throw 'Target database backup failed' }
```

### Phase 2: Archive integrity and listing validation
Verify the dump file is readable and non-corrupt:
```powershell
$archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $backupPath).Hash
pg_restore --list $backupPath | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Archive table of contents is unreadable or corrupt' }
Write-Host "Archive validated. SHA-256: $archiveHash"
```

### Phase 3: Separate recovery database provisioning and full restore
*DBA Requirement:* Because non-administrative roles lack `CREATEDB`, an authorized
DBA must pre-create the empty isolated recovery database on the target instance:
```sql
-- DBA command on target cluster:
CREATE DATABASE aquaiq_recovery WITH OWNER = aquaiq_admin ENCODING = 'UTF8';
```
Then execute full restoration into the isolated recovery database (never use `--clean` or restore over production):
```powershell
if (!$recoveryDatabase -or $targetDatabase -eq $recoveryDatabase) { throw 'Separate recovery database required' }
pg_restore --exit-on-error --dbname=$recoveryDatabase $backupPath
if ($LASTEXITCODE -ne 0) { throw 'Full restore into recovery database failed' }
psql --dbname=$recoveryDatabase -X -v ON_ERROR_STOP=1 -c 'SELECT current_database(), inet_server_addr(), inet_server_port();'
```

### Phase 4: Post-restore schema and table integrity check
Verify both core legacy tables and state-median release tables exist and contain matching records:
```powershell
$verifySql = @"
SELECT 'districts' AS tbl, count(*) FROM districts
UNION ALL SELECT 'raw_data', count(*) FROM raw_data
UNION ALL SELECT 'features', count(*) FROM features
UNION ALL SELECT 'forecast_generations', count(*) FROM forecast_generations
UNION ALL SELECT 'score_publications', count(*) FROM score_publications;
"@
psql --dbname=$recoveryDatabase -X -v ON_ERROR_STOP=1 -c $verifySql

# If state-median tables exist on target, verify their 5 tables:
$medianSql = @"
SELECT 'state_median_generations' AS tbl, count(*) FROM state_median_generations
UNION ALL SELECT 'state_median_forecast_records', count(*) FROM state_median_forecast_records
UNION ALL SELECT 'state_median_releases', count(*) FROM state_median_releases
UNION ALL SELECT 'state_median_publications', count(*) FROM state_median_publications
UNION ALL SELECT 'state_median_active_release', count(*) FROM state_median_active_release;
"@
psql --dbname=$recoveryDatabase -X -v ON_ERROR_STOP=1 -c $medianSql
```

### Phase 5: Retention of recovery evidence
Retain the following signed evidence in the change record:
1. `pg_dump` and `pg_restore` versions.
2. Backup timestamp (UTC), file size, and file SHA-256.
3. Exit status (0) of `pg_dump`, `pg_restore --list`, and `pg_restore`.
4. Row counts from legacy and median tables matching the production source.
5. DBA sign-off confirming the recovery database was isolated and successfully queried.

CLI `--backup` checks only custom-format header, file existence and size. It
does **not** verify backup age, correct DB/scope, archive completeness or tested
recovery. The operator must supply the above five-phase evidence separately.

## 6. Database migration, staging and publication

**STOP: every production command in this section requires explicit approval,
verified recovery and the separate release-writer connection. None was run by
this audit.** Use an operator environment with all target connection settings
explicitly supplied so development `.env` cannot supply missing values.

The additive CLI migration applies only 006/007 in
`AQUAIQ_STATE_MEDIAN_SCHEMA`. Normal startup/reads do not migrate, stage or
publish. Production stage/publish do not auto-migrate. Do not run `db.init_db`
as a shortcut for the median release, and never use `--test-schema` on target.

```powershell
if (!$approvedExpectedActive -or !$approvedGenerationFile -or !$approvedPublicationReason -or
    !$backupPath -or !(Test-Path -LiteralPath $backupPath) -or
    !(Test-Path -LiteralPath $approvedGenerationFile)) { throw 'Missing approved release inputs' }
if (!$approvedMedianSchema -or $approvedMedianSchema -match '^aquaiq_test_' -or
    $approvedMedianSchema -notmatch '^[a-z][a-z0-9_]{0,62}$') { throw 'Unapproved target median schema' }
$env:AQUAIQ_STATE_MEDIAN_SCHEMA = $approvedMedianSchema
function Invoke-MedianRelease {
    $medianOutput = & $medianPython -B -m scripts.release_state_median @args
    if ($LASTEXITCODE -ne 0) { throw 'Median release operation failed; inspect private operator logs' }
    $medianOutput | ConvertFrom-Json
}
Invoke-MedianRelease migrate --allow-production-write --backup $backupPath
$before = Invoke-MedianRelease status
$expectedActive = if ($before.generation_id) { [string]$before.generation_id } else { 'none' }
# $approvedExpectedActive comes from the approved change record: UUID or literal 'none'.
if ($expectedActive -ne $approvedExpectedActive) { throw 'Target pointer differs from approved previous pointer' }
$staged = Invoke-MedianRelease stage --release-dir $medianArtifact --input $approvedGenerationFile --allow-production-write --backup $backupPath
$targetReleaseId = [string]$staged.release_id
if (!$targetReleaseId) { throw 'Target did not return a staged release UUID' }
# Retain and independently review this target stage, all 36 payloads and its manifest.
# A stage must still be unavailable through normal published-only APIs.
$published = Invoke-MedianRelease publish --release-id $targetReleaseId --expected-active $expectedActive --reason $approvedPublicationReason --allow-production-write --backup $backupPath
Invoke-MedianRelease status
```

Before `publish`, compare `$expectedActive` with the approved change record.
Publication revalidates the stored complete release inside one transaction,
takes a transaction advisory lock, locks the pointer row, checks expected-active,
appends the event, then switches the pointer. Any mismatch must stop; do not
automatically retry with a newly observed pointer. A retry of the already active
same release is idempotent. Retain event ID, previous/current UUID, vintage,
manifest and reason. Event immutability is enforced by application behavior and
privilege separation; a table owner/DBA can change rows, so unrestricted serving
ownership is unacceptable.

Stage and inspect r2 before the maintenance window. Plan a coordinated
publication/application transition: an old process expecting r1 can return 503
after r2 activation; a new process expecting r2 refuses startup while r1 remains
active. The repository does not implement a verified zero-downtime blue/green
cutover. Use a reviewed maintenance/traffic plan rather than assuming both
identities can be swapped without an availability gap.

## 7. Application deployment and health

**Conditional Compose procedure only.** Docker Compose is the repository's
provided packaging, not a verified hosting platform. No provider, production
host, domain, image digest or Docker runtime was established. If the operator
selects another platform, supply and test its actual commands before approval.

With the verified API/web image build context and private r2 `deploy/.env`:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml images
# Record approved image IDs/digests and exact runtime/artifact checks before activation.
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
```

Check each exit code. Do not use the floating `python:3.13-slim` default as
evidence of Python 3.13.15. Validate `python --version`, `python -m pip check`
and release `verify` inside the built API image on target before deployment.
The API startup checks exact local/published manifests and all 36 states with
read-only queries. Data/checkpoints must be mounted at their reviewed paths.
Compose does not provision PostgreSQL, backups, persistent DB volumes, DNS,
certificates, an external TLS proxy or an alert service. API has no published
host port; web binds loopback by default.

Inspect `/api/health` through the real HTTPS origin, healthcheck status,
restarts and private logs. **The recurring health endpoint checks DB and three
district/legacy model bundles, not median release integrity.** Monitor summary
and pinned-state probes separately; a green healthcheck alone is insufficient.
The file-only research API has additional ignored `reports/` assets excluded
from this image; if that separate research product is required on target,
verify/package its pinned assets under a separately reviewed plan.

## 8. Smoke tests and success criteria

Run actual HTTP requests against `$approvedBaseUrl` (approved HTTPS origin),
never the local staged preview. Do not embed credentials in URLs or retained
responses. Retain response status and release identity with the test timestamp.

1. `/api/v2/states` returns 36 registry entries and the approved published
   UUID/release/vintage. Read `/api/v2/states/summary`, require r2 and the same
   identity. Pin `generation_id` **and** `as_of` for subsequent requests.
2. Request `/api/v2/predict/state/<state_id>` for every summary state using
   those pins. Require 200, same generation/vintage/release/source, `m_bgl`,
   method counts 17/17/2, the approved file-byte `release_manifest_sha256`, and
   a validated complete 36-state snapshot. Require
   finite depths, 12 consecutive Nov 2026–Oct 2027 dates for 34 states and no
   forecast for LA/LD. Validate through
   `models.state_median_storage.validate_generation` and
   `models.state_median_release_storage.validate_release` using the approved
   manifest. Verify summary row methods/reference/age match detail responses.
3. Require Sikkim: one genuine observation, `2025-01-01`, age 21,
   25% district coverage, persistence, twelve values 19.26; AN: reference
   `2023-04-01`, age 42; DD: `2025-01-01`, age 21. No fallback MAE/RMSE or fitted
   weight hash. Inspect all stale/low-coverage labels across cards/map/table.
4. Explicit `model=median_xgboost` with r2 UUID must return 400; it cannot return
   r2 as XGBoost. A nonexistent/staged UUID must yield summary/detail 503, with
   registry navigation permitted but `publication_status=unavailable`.
5. Refresh `/states/SK`, change state, use desktop and mobile; inspect one chart,
   separate real/forecast points, monthly table, legend, map and summary cards.
   Verify no legacy substitution on a failed median request and no console
   errors or horizontal overflow. Browser verification is an operator gate.
6. Compare Home's legacy `/api/states/summary`, `/api/predict/state/<id>`,
   `/api/districts`, persisted district `/api/predict/<district_id>`, scores,
   history and existing six-month district response with captured approved
   pre-change fixtures. Preserve all legacy/district generation/weight hashes.

Example read-only HTTP commands after the target origin is approved:

```powershell
if (!$approvedBaseUrl -or $approvedBaseUrl -notmatch '^https://') { throw 'Approved HTTPS origin required' }
$health = Invoke-RestMethod "$approvedBaseUrl/api/health"
$summary = Invoke-RestMethod "$approvedBaseUrl/api/v2/states/summary"
if ($summary.artifact_release -ne '2026.10.29-r2' -or !$summary.generation_id -or
    $summary.as_of -ne '2026-10-29' -or $summary.states.Count -ne 36) { throw 'Wrong or incomplete publication' }
$pin = 'generation_id={0}&as_of={1}' -f $summary.generation_id,$summary.as_of
$registry = Invoke-RestMethod "$approvedBaseUrl/api/v2/states?$pin"
if ($registry.generation_id -ne $summary.generation_id -or $registry.as_of -ne $summary.as_of -or
    $registry.total -ne 36 -or $registry.publication_status -ne 'published') { throw 'Registry identity mismatch' }
$stateResponses = @{}
foreach ($state in $summary.states) {
    $payload = Invoke-RestMethod "$approvedBaseUrl/api/v2/predict/state/$($state.state_id)?$pin"
    if ($payload.generation_id -ne $summary.generation_id -or $payload.as_of -ne $summary.as_of -or
        $payload.artifact_release -ne '2026.10.29-r2') { throw 'Mixed release identity' }
    $stateResponses[$state.state_id] = $payload
}
# Save privately and pass to the validators above; HTTP 200 alone is not validation.
```

## 9. Monitoring, rollback and partial-failure recovery

Monitor HTTPS/DB availability, median summary identity and method counts,
per-state 503/error rates, district/Home invariants, process restarts, latency,
disk/DB capacity, backup freshness and the explicit observation ages. Select an
operator, polling/alert thresholds, dashboard/log destination and escalation
path before approval. Retain private sanitized logs; do not expose secrets.

Rollback triggers include incorrect identity/hash, incomplete/mixed state data,
missing persistence/stale disclosures, repeated state failures, unacceptable
latency/restarts or district/Home regression. Do not alter immutable payloads
to repair a published release. With approval, a valid backup and release-writer
credentials, switch only to an **already published** immutable prior target:

```powershell
if (!$approvedPreviousReleaseId -or !$observedCurrentReleaseId) { throw 'Verified rollback pair required' }
Invoke-MedianRelease rollback --release-id $approvedPreviousReleaseId --expected-active $observedCurrentReleaseId --reason $approvedRollbackReason --allow-production-write --backup $backupPath
Invoke-MedianRelease status
```

Restore the matching previous application image and artifact environment
(expected release/path/hash) using the target's reviewed image-digest rollback
procedure, then repeat health, all-state and legacy/district smoke tests. That
target-specific procedure/digest pair remains **UNVERIFIED**; Compose source
rebuild is not proof that the previous immutable image has been restored.

- **Publication succeeds, app deployment fails:** hold traffic under the
  maintenance plan. Either complete the pre-tested r2 application deployment,
  or approve CAS rollback to the captured prior publication and restore its
  matching image/configuration. Do not leave an r1-pinned process on an r2
  active pointer. Retain both immutable releases and all publication events.
- **App deployment succeeds, publication fails:** the r2 startup gate should
  refuse service. Restore the prior image/configuration while preserving the
  unchanged prior pointer; inspect the failed stage/CAS result before any retry.
- **No prior published median release:** rollback CLI cannot select `none` or
  an unpublished stage and does not deactivate a first publication. This needs
  an explicitly approved first-release recovery/traffic plan. Never silently
  substitute legacy forecasts. Keep this as a blocker until the operator has
  tested that plan.
- **Database/file recovery required:** stop changes under operator approval;
  restore the verified backup into a new recovery DB, verify it with the
  matching configuration/data/models/images, and use the approved target
  connection/traffic cutover. Never restore over the live DB or add `--clean`
  as an improvised repair. Restoring an entire older DB also rolls back unrelated
  data, so use the median pointer rollback where appropriate.

## 10. Retained release evidence and final sign-off

Retain the approved source/build-tree hash, API/web/base image digests, runtime
and dependency inventory, all manifest/model/source hashes, independent audit,
36 validated payloads, staged/previous/published UUIDs, publication event/reason,
target schema and redacted privilege report, backup/restore verification,
pre/post district/Home comparisons, HTTPS/health checks, browser screenshots,
monitoring ownership and tested rollback result. Record operator approvals and
timestamps. Keep dumps, credentials, private observations and environment files
out of Git and public reports.

The release owner must resolve target identity, read-only role, full recovery,
container/runtime, HTTPS/monitoring, browser and rollback gates before changing
the readiness decision. Successful local tests alone do not authorize release.

## 11. Controlled release and launch sequence (12-stage checklist)

Execute this sequence in order during an authorized maintenance window:

### Stage 1: Local artifact and code verification
```powershell
python -B -m scripts.check_validation_assets
python -B -m pip check
python -B -m scripts.release_state_median verify --release-dir models/artifacts/state_median_releases/20261029-r2 --expected-release 2026.10.29-r2 --expected-manifest-sha256 8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3
```
- [ ] Asset preflight passes (11 required bindings verified).
- [ ] Dependencies check clean (0 broken requirements).
- [ ] Release artifact status is `verified` (17 trained states, cutoff 2026-09-01).

### Stage 2: Target infrastructure and runtime verification
- [ ] Target PostgreSQL 18 instance reachable at `$env:POSTGRES_HOST:$env:POSTGRES_PORT`.
- [ ] Container runtime available on target host.
- [ ] Pinned base image `python:3.13.15-slim` (or verified digest) pulled.
- [ ] `python --version` confirmed as `3.13.15` inside target runtime.

### Stage 3: Target database backup and independent restore
```powershell
# Run the 5-phase recovery procedure from Section 5:
# Phase 1: pg_dump --format=custom --dbname=$targetDb --file=backups/pre_r2.dump
# Phase 2: Get-FileHash -Algorithm SHA256; pg_restore --list backups/pre_r2.dump
# Phase 3: DBA creates empty aquaiq_recovery; pg_restore --exit-on-error --dbname=aquaiq_recovery
# Phase 4: Query legacy (districts, features, raw_data) and median tables in recovery DB
# Phase 5: Record backup hash and restore verification in change record
```
- [ ] Backup created and archive list validated without errors.
- [ ] Recovery DB restored independently; table counts verified matching source.

### Stage 4: Dedicated read-only serving role provisioning
```powershell
# DBA executes scripts/provision_readonly_serving_role.sql against target database:
psql -h $targetHost -p $targetPort -U $dbaUser -d $targetDb -f scripts/provision_readonly_serving_role.sql
# DBA sets private password for serving identity:
# ALTER ROLE aquaiq_serving_readonly WITH PASSWORD '<secure_password>';
```
- [ ] Role `aquaiq_serving_readonly` has CONNECT on DB, USAGE on schema, SELECT on release/legacy tables.
- [ ] Role has zero INSERT/UPDATE/DELETE/TRUNCATE permissions and zero sequence permissions.

### Stage 5: Target schema and migration preflight
```powershell
$env:AQUAIQ_STATE_MEDIAN_SCHEMA = $approvedMedianSchema
python -B -m scripts.release_state_median migrate --allow-production-write --backup backups/pre_r2.dump
```
- [ ] Migrations 006 and 007 applied cleanly to target schema.
- [ ] No district or public legacy tables modified.

### Stage 6: Release staging and validation
```powershell
python -B -m scripts.release_state_median stage --release-dir models/artifacts/state_median_releases/20261029-r2 --input $approvedGenerationFile --allow-production-write --backup backups/pre_r2.dump
```
- [ ] Returns status `staged` with target staged UUID.
- [ ] Normal public API calls to this staged UUID return HTTP 503 (staged is not published).

### Stage 7: Capture currently active published generation
```powershell
$status = python -B -m scripts.release_state_median status | ConvertFrom-Json
$expectedActive = if ($status.generation_id) { $status.generation_id } else { 'none' }
Write-Host "Current active generation UUID: $expectedActive"
```
- [ ] Captured `$expectedActive` matches the pre-approved change record (or `none` for initial publication).

### Stage 8: Authorized atomic publication using CAS
```powershell
python -B -m scripts.release_state_median publish --release-id $targetStagedUuid --expected-active $expectedActive --reason 'Authorized primary States median release r2' --allow-production-write --backup backups/pre_r2.dump
$afterStatus = python -B -m scripts.release_state_median status | ConvertFrom-Json
if ($afterStatus.generation_id -ne $targetStagedUuid) { throw "Publication failed to switch pointer" }
```
- [ ] CAS publication succeeds under transaction advisory lock.
- [ ] Active pointer now points to `$targetStagedUuid`.

### Stage 9: Application deployment
```powershell
# Copy deploy/environment.example to deploy/.env with target credentials
# Build and start services:
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
```
- [ ] API service passes startup readiness check (`deploy/serve.py` validates r2 publication and all 36 state records).
- [ ] Web service healthy and listening on configured port.

### Stage 10: Smoke tests (API, UI, district regressions, state coverage)
```powershell
# Follow smoke test procedure in Section 8:
# 1. /api/health -> 200 healthy
# 2. /api/v2/states/summary -> 200, 36 states, r2 identity
# 3. All 36 /api/v2/predict/state/<id> -> 200 (or 503 for LA/LD), correct methods & ages
# 4. Legacy routes /api/states/summary & /api/predict/state/AP -> 200, district-mean
# 5. UI check: States page loads, chart dashed forecast, table methods, no console errors
```
- [ ] All 36 state endpoints verified; Sikkim persistence 19.26 m, age 21 m.
- [ ] District forecasting and Home page verified unaffected.

### Stage 11: Monitoring and release sign-off
- [ ] Monitor container logs (`docker compose logs -f --tail 100`) for 30 minutes.
- [ ] Error rate on `/api/v2/` is 0%.
- [ ] Sign off release change ticket with retained hashes and publication UUID.

### Stage 12: Rollback procedure and triggers
- **Triggers:** Corrupt payloads, broken district forecasts, unhandled API 500 errors, or operational directive.
- **Pointer Rollback:**
  ```powershell
  python -B -m scripts.release_state_median rollback --release-id $previousPublishedUuid --expected-active $targetStagedUuid --reason 'Authorized rollback' --allow-production-write --backup backups/pre_r2.dump
  ```
- **App Image Rollback:**
  ```powershell
  docker compose --env-file deploy/.env.previous -f deploy/compose.yaml up -d
  ```
- **Partial Failure Recovery:**
  - *Publication succeeds, app fails:* Hold traffic. Either deploy pre-tested r2 container or execute CAS rollback to `$previousPublishedUuid`.
  - *App succeeds, publication fails:* API container startup fails readiness check safely (fails closed). Revert container image.

