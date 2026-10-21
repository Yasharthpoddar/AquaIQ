# AquaIQ release and update operations

## Twelve-month research application scope

The primary research panel uses `/api/research/forecast/<district_id>` and the separate local descriptor `research/twelve_month_app.json` (override: `AQUAIQ_RESEARCH_CONFIG`). Its compatible XGBoost artifact and frozen feature/provenance snapshots support historical Adilabad research only. Missing assets and current/future requests produce unavailable ML. Preserve the active six-month checkpoints and database.

The deployment instructions below are maintainer references. No deployment was verified or authorized by twelve-month finalization. A successful legacy readiness check does not validate this research artifact, its scientific skill, or production release. A clean clone lacks ignored runtime assets and a populated legacy database. The [finalization report](../reports/candidates/twelve_month_horizon_finalization_20261020/REPORT.md) gives precise assets and safe local commands; no refresh, migration or scoring run is needed for its file-only route.

This is a concrete local production-style topology: Nginx serves the compiled
SPA and forwards same-origin `/api/` requests to Waitress. The API connects to an
existing PostgreSQL database. No database container, schema initialization or
automatic training is performed. Only the Nginx port is published, bound to
`127.0.0.1` by default. Dockerfiles and Compose require a real build/run check on
a Docker host before any public deployment.

## Prepare one matching release

1. Take a **new** `pg_dump --format=custom` backup plus copies/hashes of
   `config.yaml`, `data/processed`, required `data/raw` inputs (including the
   canonical district GeoJSON), and the entire `models/checkpoints` directory.
   Preserve pointer JSONs, cards, both immutable bundle directories and physical
   feature manifests together. Git alone does not contain these artifacts.
2. Restore the database into a separate database on the serving host using the
   matching PostgreSQL client. Use the matching source/configuration commit and
   model/data release. Do not initialize an empty database and expect it to work.
3. Provision a dedicated serving role with `CONNECT`, schema `USAGE` and `SELECT`
   on AquaIQ tables; keep ingestion/schema-write credentials outside the serving
   application. Configure PostgreSQL to accept only the Docker/private network
   as needed. A container's `localhost` is the container, not the Windows host.
4. Copy `deploy/environment.example` privately to `deploy/.env`. Replace the
   placeholders, including a random private secret of at least 32 characters.
   Set absolute data/checkpoint paths. Bind mounts are read-only and missing
   host folders fail rather than silently creating empty directories.

From the repository root:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
```

Open `http://127.0.0.1:8080`. Waitress refuses startup unless both model bundles
match the feature generation, district/raw/features tables are populated and
`/api/scores` returns a complete matching publication. The expected district
count defaults to 725 and can be configured deliberately for another release.
The healthcheck repeats database/model checks; it is not an accuracy guarantee.
The shipped secret/password placeholders and blank or surrounding-whitespace
credentials are refused at startup. Nginx's upstream uses Docker's embedded DNS
with `resolve` and a shared zone so API container address changes can be refreshed
without pinning the original address. This follows the [Nginx upstream docs](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server)
and [Docker DNS documentation](https://docs.docker.com/engine/network/#dns-services).
Container recreation/recovery still needs a runtime test on a Docker host.

Validate `/api/health`, `/api/scores`, one district/history response, the
six-month graph and a zero-change simulation. Confirm the SPA still opens after
refreshing a district URL. Inspect logs with `docker compose ... logs --tail 100`
(substitute the same `--env-file` and `-f` options; never post credentials).

For public serving, put an HTTPS reverse proxy in front of this loopback port,
configure DNS/certificates and host monitoring, then test the deployed origin.
This package does not create accounts, DNS, certificates or a remote host. The
API uses same-origin requests here, so `AQUAIQ_CORS_ORIGINS` is explicitly empty.
For an intentionally separate frontend, use a comma-separated allowlist such
as `https://aquaiq.example.org`; wildcards, credentials and URL paths are rejected.
Local development retains the four existing localhost/127.0.0.1 origins when
the variable is unset. CORS is not authentication.

## Stage rainfall updates safely

The orchestrator defaults to a read-only, offline plan:

```powershell
.\venv\Scripts\python.exe -m scripts.stage_rainfall_update
.\venv\Scripts\python.exe -m scripts.stage_rainfall_update --run --max-days 10
```

The default `--start auto` checks the published rainfall CSV hash, units,
complete-day aggregation, canonical boundary hash and source manifest entries.
Every district must cover every month from the dataset's first through last
month; missing district/months are refused rather than skipped. The next
unimported month is inferred only after those checks. Publishing a new verified
rainfall artifact therefore advances later scheduled runs; the job does not
infer or alter database publication. Promote that artifact with its matching
database/models through the audited release procedure. If all completed months
are already present, the job returns `no_new_completed_months` without locking,
downloading or writing. An explicit `--start YYYY-MM` remains available for a
reviewed manual range; it is not the scheduling default.

Omitting `--end` selects the last completed month. A run first downloads the
three 2025 overlap dates and compares them to the annual archive. Failed
downloads or differing products stop the job before the target-year batch.
The first-phase limit is at most three dates and the target phase is limited to
ten pending dates by default; retries and connection/read timeouts are bounded.
Cached grids are strictly revalidated. Do not relax comparison thresholds to
force a pass. Every daily record of the requested range is required for export.

Progress is checkpointed at
`reports/candidates/rainfall_refresh/<start>_<end>/progress.json`, with separate
downloader progress in `data/raw/updates/rainfall_refresh`. An OS lock prevents
overlapping manual/scheduled runs and releases on crashes. Verified merged
candidates are reused; unrelated/tampered/partial candidate outputs are refused.
Exit 0 means an offline plan or ready candidate; exit 1 means blocked/incomplete.
Source files and provisional product provenance remain available for review.

This job never ingests, retrains, changes production CSVs or publishes scores.
After a candidate is ready, take a new backup; review source coverage and
provenance; use the existing audited ingestion and rebuild procedure; check
matching generations, evaluate models and publish one complete scoring run.
Only then release the matching database, artifacts and code together.

## Prepare Windows scheduling

```powershell
# Preview only: does not register or start a task.
.\scripts\register_refresh_task.ps1 -EveryHours 24 -MaxDays 10
# After reviewing the concrete preview, install explicitly:
.\scripts\register_refresh_task.ps1 -EveryHours 24 -MaxDays 10 -Install
```

The task invokes the exact project Python and working directory through a hidden
PowerShell window, ignores overlapping instances, and writes per-run logs under
`reports/candidates/rainfall_refresh/task_logs`. It starts five minutes after
registration, repeats for ten years, and has a one-hour execution limit. The
default principal requires the current user to remain logged in and stores no
password. Logged-out operation needs a separately provisioned service identity;
it is not silently enabled. Re-running the installer refuses to replace an
existing task. To remove it deliberately: `Unregister-ScheduledTask -TaskName
'AquaIQ-Rainfall-Staging' -Confirm:$false`.

## Recovery and monitoring

Inspect staging progress/error type, source freshness, API health, complete-score
counts, container restarts and the latest successful backup. Stale sources and
zone estimates remain labelled in the UI. A failed staging run leaves the active
release intact and is safe to resume. If a production release fails checks, stop
the API, restore the **same release's** database dump, configuration, processed
data and complete checkpoint tree, then restart and repeat readiness checks.
Do not mix a restored database with newer model pointers or vice versa. Keep
older backups until the replacement release has been verified.

Software/deployment readiness does not establish current-period forecast
accuracy, prediction intervals or independently calibrated crisis thresholds.
