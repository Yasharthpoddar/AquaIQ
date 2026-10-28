# Release, deployment and recovery

The package runs Nginx for the React SPA and same-origin `/api/` proxy, with Waitress/Flask connected to an existing PostgreSQL database. It does not provision a database, train models or initialize schema automatically. Only the Nginx port is published, bound to loopback by default. Docker build/run, host recovery, HTTPS and monitoring require verification on the target host; passing local tests is not a deployment or scientific guarantee.

The default product reads persisted twelve-month generations. [Serving contracts](../docs/NATIONWIDE_FORECASTS.md) explain publication selection, separate risk outputs and namespace configuration. [Required assets](../docs/FINAL_RELEASE_REPRODUCTION.md) include matching data, models/cards, registry and database publications. The file-only historical research APIs also require `research/twelve_month_app.json` and its pinned local artifact; their Adilabad-only scope never expands merely because the dashboard covers all districts.

## Prepare and verify one matching release

1. Take a new `pg_dump --format=custom` backup plus exact copies/hashes of `config.yaml`, processed/raw prerequisites and the complete checkpoint/pointer/card trees. Restore the database into a separate database on the serving host using the matching PostgreSQL client. Source, data, configuration and models must belong to the same release; Git alone is insufficient.
2. Provision a serving role with `CONNECT`, schema `USAGE` and `SELECT`; keep ingestion/schema-write credentials separate. Permit only the necessary private/container network. A container's `localhost` is the container itself.
3. Copy `deploy/environment.example` privately to `deploy/.env`. Replace placeholders, set a random private secret of at least 32 characters and specify the absolute host data/checkpoint paths. Read-only bind mounts refuse missing host directories rather than creating empty ones.

From the repository root:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
```

Open `http://127.0.0.1:8080`. Waitress requires all three matching model bundles to pass health, populated district/raw/features tables and a complete matching `/api/scores` publication. Expected district count defaults to 725. Secret/password placeholders and blank/surrounding-whitespace credentials are refused. The healthcheck repeats real database/model checks, not forecast validation. Nginx uses Docker DNS with `resolve` and a shared upstream zone to follow API container address changes; container recreation still needs a host runtime test.

Verify `/api/health`, registry, a published twelve-month district/state forecast, `/api/scores`, history, a six-month graph, zero-change simulation and a district SPA URL after browser refresh. Inspect `docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail 100` privately. Public serving additionally needs a tested HTTPS reverse proxy, DNS, certificates and host monitoring. These are not created by Compose.

The package uses same-origin API requests and explicitly empty `AQUAIQ_CORS_ORIGINS`. A separate frontend requires an exact comma-separated origin allowlist; wildcards, credentials and URL paths are rejected. Unset local-development settings retain the existing localhost/127.0.0.1 origins. CORS is not authentication. Keep synchronization fallback disabled for normal persisted twelve-month serving.

## Stage rainfall updates

```powershell
.\venv\Scripts\python.exe -m scripts.stage_rainfall_update
.\venv\Scripts\python.exe -m scripts.stage_rainfall_update --run --max-days 10
```

Default invocation prints a read-only offline plan. `--start auto` verifies the published rainfall CSV hash, units, complete-day aggregation, boundary hash, source manifest and complete district/month grid before finding the next unimported month. Omitting `--end` selects the last completed month. A fully current dataset returns `no_new_completed_months` without locking/downloading/writing. Explicit `--start YYYY-MM` is available for an inspected range.

A run first checks three 2025 overlap dates against the annual archive; missing/different products stop acquisition. Default limits are three comparison dates and ten pending target dates, with bounded retries/timeouts. Cached grids are revalidated and every requested date is required for export. Progress stays under `reports/candidates/rainfall_refresh/<start>_<end>/progress.json`, with downloader progress under `data/raw/updates/rainfall_refresh`. An OS lock prevents overlapping runs and releases on crashes. Verified merged candidates can resume; tampered/unrelated/partial outputs fail closed. Exit 0 means a plan or ready candidate; exit 1 means blocked/incomplete.

Staging never ingests, retrains, replaces production CSVs or publishes scores. Before promotion, preserve a matching backup, inspect source coverage/provenance, use the audited ingestion/rebuild/evaluation process and publish a complete matching database/model/configuration release. A successful staging run is not approval to change the service.

## Windows scheduling and recovery

```powershell
# Preview; no registration or execution.
.\scripts\register_refresh_task.ps1 -EveryHours 24 -MaxDays 10
# Explicit installation after inspecting the preview.
.\scripts\register_refresh_task.ps1 -EveryHours 24 -MaxDays 10 -Install
```

The task invokes the exact project interpreter/working directory in a hidden PowerShell window, ignores overlapping instances and writes per-run logs to `reports/candidates/rainfall_refresh/task_logs`. It begins five minutes after registration, repeats for ten years and has a one-hour execution limit. Default operation requires the current user logged in and stores no password. Logged-out execution needs a separately provisioned service identity. Existing tasks are never silently replaced. Deliberate removal uses `Unregister-ScheduledTask -TaskName 'AquaIQ-Rainfall-Staging' -Confirm:$false`.

Monitor source freshness, progress/errors, complete-score counts, API health, restarts and verified backups. Failed staging leaves the active release intact. If release checks fail, stop the API and restore the same release's database, configuration, processed data and complete model/checkpoint trees, then repeat readiness checks. Do not mix generations. Retain old backups until replacement verification finishes. Neither deployment readiness nor software checks establishes forecast skill, calibrated probability or operational suitability.
