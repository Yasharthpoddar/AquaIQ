# State median r2 final production readiness audit

Audit date: **2026-10-29**. **Overall decision: NOT READY.** Local artifact,
coverage, software and publication-isolation checks pass. Production identity,
read-only credentials, proven recovery, target runtime/container, HTTPS,
monitoring, visual checks and operational rollback have not been established.
No production migration, stage, publication, pointer change, permission change,
deployment, restart, commit, push, merge or pull request was performed.

`PASS` means directly verified within the stated scope. `FAIL` means an
observed defect. `UNVERIFIED` means evidence is missing. `BLOCKED` means missing
access, information or authorization prevents the next verification/action.
Local/test evidence is never described as a production verification.

## Repository and preservation

The actual checkout is `C:/Users/Yasharth/Downloads/AquaIQ`, remote
`https://github.com/Yasharthpoddar/AquaIQ.git`, branch **main**, HEAD
`027ea4969639912ef73e556975edf7c0d10abff8` (the repository-cleanup merge).
The working tree already contained substantial modified and untracked state
forecast/deployment work. It was inspected in place without reset, clean,
stash, overwrite or commit. All **530 pre-existing nonignored files** were
hashed and remained unchanged; the ignored `.env` was separately checked and
also remained unchanged. The new audit adds documentation/evidence only.

All requested implementation/document paths exist except the production
runbook, which did not exist and was created. No repository or ancestor
`AGENTS.md` was found. A build identified only by HEAD would omit the dirty
release implementation; an approved build-context/source-tree digest remains
required. Current file inventory and preservation evidence are in
`scratch/state_median_readiness_20261029/{git_status.txt,preservation.json,working_tree_before.json}`.

## Readiness findings

| Area | Status | Evidence and scope |
|---|---|---|
| Actual r2 artifact and expected identity | PASS | Recomputed exact manifest/source/card/policy/model hashes; runtime verifier passed |
| Coverage and scientific metadata | PASS | Fresh independent source reconstruction: all 36 responses, 17 XGBoost, 17 persistence, only LA/LD no observations; 408 values Nov 2026–Oct 2027 |
| r1 and district/Home preservation | PASS | All 17 weights and 204 XGBoost predictions exactly match r1; protected model/config/checkpoint/Home bytes unchanged; fresh legacy/district/API tests passed |
| Published-only HTTP reads | PASS | 89 actual requests on ephemeral loopback HTTP servers against existing isolated schemas; r1 published, r2 staged rejected |
| API startup gate | PASS | Actual published r1 accepted with all 36 responses; staged r2 rejected despite valid local artifact |
| Frontend contracts and rendering | PASS | Fresh tests/lint/build and SSR checks for every staged state; generation/vintage guards and persistence disclosures checked |
| Fresh desktop/mobile visual QA | UNVERIFIED | Computer Use stopped because Chrome's URL could not be determined reliably for policy enforcement; no workaround or further UI input attempted |
| Atomic publication/CAS/rollback implementation | PASS | Fresh isolated PostgreSQL tests cover validation, rollback, transaction failure and unexpected active pointer; actual r2 remains unpublished |
| Configured local role as a serving identity | PASS (local template) / OPERATOR GATE | `aquaiq_user` remains local owner; DBA least-privilege script `scripts/provision_readonly_serving_role.sql` prepared and verified by `tests/test_state_median_role_safety.py`. Target role execution requires DBA |
| Actual production role/schema/DB | UNVERIFIED | Only loopback local DB identified; target DBA must run provisioning script with approved credentials |
| Fresh local backup archive | PASS | Full local `pg_dump` succeeded; archive readable with 559 TOC entries (23.6 MB) |
| Full independent recovery restore | PROCEDURE PREPARED / DBA GATE | 5-phase procedure and DBA pre-provisioning SQL documented in Runbook; target execution requires DBA with CREATEDB |
| Target backup and recovery | UNVERIFIED | Target database backup and separate-database restore must be performed by operator on target host |
| Local pinned runtime/dependencies | PASS | Python 3.13.15 and exact r2 NumPy/pandas/sklearn/XGBoost versions; `pip check` and asset preflight passed |
| Target runtime and container images | UNVERIFIED | Docker absent from shell; `deploy/compose.yaml` and `deploy/environment.example` configured for `python:3.13.15-slim` with container test commands |
| Target hosting/HTTPS/logging/monitoring/storage | UNVERIFIED | No provider/host/domain/alert owner/persistent DB configuration established |
| Production environment configuration | TEMPLATE READY / TARGET GATE | `deploy/environment.example` updated with verified r2 identity/hash and rollback mode; target `deploy/.env` requires private secrets |
| Target application/publication rollback pair | BLOCKED | No previous production median UUID, image/config digest pair, or first-publication recovery plan identified/tested |
| Production writes/deployment | BLOCKED | Explicit authorization was not granted; this audit stops before those actions |

## Actual artifacts and source

The immutable directory is
`models/artifacts/state_median_releases/20261029-r2`, artifact release
`2026.10.29-r2`, model `2.0-state-median-tiered`, policy
`1.0-state-median-coverage`, vintage `2026-10-29`.

| Recomputed item | SHA-256 |
|---|---|
| r2 manifest file | `8e97f543b406a83fe854b1501b34c66c4dc1732d0752cf44c2f493ce8c2644c3` |
| V3 source CSV | `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042` |
| Source manifest | `6d98e62cd2d55504e8df74ceb4d8faf099fe712826981bdc787eef56bfab19c0` |
| Source dataframe | `2982c2d53bfe2b747a7d86821323d0f8bd58d1d755baa713d1b8741a40999209` |
| Policy implementation | `86b0845b6c0747f3556ed9c88501847f929a451ad29d537acfe9c0e15c0f5bca` |
| Policy card | `cff7929944d225ed92be94f06b59d03c12e57d78008732238faba7518c6faf77` |
| XGBoost component card | `2ab75da0eeb8dbd8c98a61a275d24e7b76a87582fd8161cfd91b2995d48f0be8` |
| Original district model | `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03` |

The source generation is `physical-v3-official-c9ade81d95720f91`, containing
43,384 genuine district-month observations. A new file-only export was
generated without `--test-schema`; it neither staged nor published anything.
The independent audit rebuilt genuine district-month means then state medians
from the source flags, rather than trusting the production aggregation helper.
It checked every reference/count/date/age/coverage, all finite nonnegative
forecasts, consecutive dates, units and consistent release/source identities.
All 36 fresh payloads match the earlier r2 export after excluding only
`computed_at`. All 17 learned-model files and 204 forecast rows match r1 exactly.

The complete fresh state-by-state table is in
`scratch/state_median_readiness_20261029/artifacts/verification/states.csv` and
`artifacts/coverage_audit/coverage.md`. The
[artifact audit](STATE_MEDIAN_READINESS_ARTIFACTS.md) includes exact replay
commands, hashes and limitations.

Every forecast reference is stale relative to the nominal three-month reporting
interval: **31 states have age 9 months, DD/SK 21 months, AN 42 months**.
AR, JK, MN, MZ and SK have reference coverage below learned-target eligibility.
Those facts are retained in the model card, API metadata and frontend
disclosures. Persistence has no evaluated accuracy; current refitted XGBoost
weights do not have an attached held-out evaluation. Historical XGBoost metrics
belong to frozen 2019 weights. No accuracy or current-measurement claim follows
from complete engineering coverage. Product acceptance of these limits remains
an explicit operator gate.

## Serving and publication trace

The primary States route calls the v2 registry/summary, validates summary
identity, then requests detail with the **same generation UUID and as-of
vintage**. Chart, cards, map and table use the validated summary/detail; rejected
median requests do not silently call the legacy service. Home still calls the
legacy summary. API v2 routes select only previously published releases;
storage validates the full persisted snapshot and manifest on reads and never
trains or generates ad hoc forecasts. Explicit incompatible model selection
is rejected. Published reads do not need to re-run inference from model files;
startup separately verifies the local artifact, runtime and published identity.

Actual local HTTP evidence confirms the existing r1 UUID
`eaabeba7-a554-59a6-9110-726221e63cb2` returns all 36 pinned state responses.
The actual r2 stage UUID `789ce3b5-3170-5866-9ce2-c0ec2f0b1b59` in
`aquaiq_test_state_median_coverage_20261029` has **zero publication events and
zero active-pointer rows**. All 36 pinned staged state requests returned
explicit **503**, with empty forecast and unknown method rather than fabricated
no-observation counts. Registry navigation remains available with unavailable
publication identity. Invalid horizon/state/model/vintage cases behaved as
documented. Actual startup accepted published r1 and refused staged r2.

The file-byte manifest SHA and DB internal manifest digest intentionally differ:
the DB hashes compact sorted canonical JSON, whose r2 digest is
`c4015b766068d83510e468699052106f99b39407316fb5d2a8c8413580bcfab7`.
Stored JSON exactly equals the parsed approved artifact, and all stored payloads
carry the approved file-byte `release_manifest_sha256=8e97...2644c3`.
This is a verified representation distinction, not corrupt staging.

Migrations 006/007 affect only the configured median namespace; production
schema provisioning is explicit, and normal reads/startup do not migrate.
Publication validates stored content inside a transaction, takes an advisory
lock and pointer row lock, enforces expected-active, appends a publication
event and atomically switches the pointer. Rollback requires a previously
published immutable generation. The application never updates old events or
payloads, but no append-only trigger protects them from an unrestricted table
owner. Least-privilege serving credentials and controlled writer access are
therefore essential. The inspected local writer/owner fails that gate; its
permissions were not changed. No median migration was applied to public.

See the [database audit](STATE_MEDIAN_READINESS_DATABASE.md) and
[frontend/HTTP audit](STATE_MEDIAN_READINESS_FRONTEND.md) for exact checks,
line references, test commands and evidence paths.

## Tests executed against this working tree

| Current run | Result |
|---|---|
| Full Python `pytest -q -ra` | **1,903 passed, 47 skipped, 70 warnings**, 123.48 s |
| Complete focused median/release/deployment selection with PostgreSQL plus two legacy/district API regressions | **168 passed, 0 skipped, 0 failures/errors**, 137.50 s |
| Policy/audit/evaluation/release/forecast artifact-focused rerun | **62 passed**, 13.17 s |
| Additional frontend-serving API failure/model guards | **15 passed** |
| Frontend unit tests | **184 passed** |
| Frontend lint and production build | **PASS** |
| Actual staged frontend contract/SSR validation | **36 valid, 34 forecasts, 408 forecast rows, 2,160 history rows, 36 comparison rows, zero errors** |
| Actual read-only HTTP | **89 requests PASS**; both published r1 and unpublished r2 cases |
| Actual median startup-readiness probes | **Published r1 accepted; staged r2 rejected** |
| `pip check`, validation-asset preflight | **PASS**, no broken requirements; 11 required asset paths/bindings verified |
| Compose and CI YAML | **Parsed**; Docker Compose/runtime execution remains UNVERIFIED |
| Fresh desktop/mobile browser verification | **UNVERIFIED**, policy-enforcement stop; historical screenshots were not counted |

The 168-test selection is the prior 166 focused cases plus two real legacy/
district API cases. Its 13 v2 cases plus those two regressions cover the prior
15-case API selection; they are not an additional disjoint 15 tests. The real
725-district fixture was freshly recomputed. Only the test process cleared the
development legacy schema override; `.env` was preserved.

The full suite's 47 skips consist of 46 opt-in PostgreSQL cases and one Windows
directory-symlink privilege/developer-mode case. Relevant median and legacy/
district DB cases were then run with `--integration`; this does not claim all
unrelated DB tests were run. Warnings include 68 netCDF/xarray NumPy-shape
deprecations, one weather-test possible binary-compatibility warning and one
single-class confusion-matrix warning. No warning was suppressed to make the
run pass. Fresh NumPy/pandas/sklearn/XGBoost imports completed without warnings;
the weather warning is a residual runtime issue to review on the actual target,
not evidence that a Linux target's native dependencies have been verified.

Raw logs/XML/validation JSON are retained under
`scratch/state_median_readiness_20261029/`; the full Python log is
`scratch/state_median_readiness_pytest.log`. Remote CI was not rerun and cannot
validate the current uncommitted files. The configured hosted Python job also
requires private validation assets that have no automatic distribution.

## Backup and recovery findings

The verified available connection is **local loopback**, DB `aquaiq`, PostgreSQL
**18.1**, role `aquaiq_user`. PostgreSQL 18.1 client tools exist at
`C:/Program Files/PostgreSQL/18/bin` but are not on PATH. This is not an
identified production database.

The existing `data/backup_pre_d1_migration.dump` is dated
**2026-10-12 04:01:18 UTC**, 22,464,250 bytes. Its readable 48-entry archive
predates the new median releases. It is not proof of current recoverability.

A fresh read-only full dump of the local DB completed at
**2026-10-29 15:52:44 UTC**:

- Location: `scratch/state_median_readiness_20261029/db/aquaiq_local_pre_r2_20261029.dump`
- Scope: full visible local DB schemas, 559 archive TOC entries.
- Size: **23,619,549 bytes**; `pg_dump` and archive listing both exited 0.
- SHA-256: `9b7c589d57a8cf914f4879ee9356dd0d75b187483e266790a6a61ef9fc072a5e`.
- Full restore into a separate recovery DB: **not performed / BLOCKED**.

The current role has no CREATEDB/CREATEROLE, and no isolated recovery DB or DBA
credentials were supplied. No attempt was made to reuse or overwrite a live
database. A DBA must provision a separate recovery DB, supply authorized restore
access, then restore and query both legacy and median tables with matching file
assets before recovery can pass. The archive's existence/readability does not
prove restoration. No production backup was identified or verified. Keep this
private dump outside Git; no credentials were written to the audit report.

## Target environment and required next information

Repository packaging is **Nginx + React, Waitress/Flask and an existing external
PostgreSQL DB via Docker Compose**. This is a supported deployment recipe,
not proof of a selected/working production platform. Compose exposes only a
loopback web port, read-only API filesystem/data/checkpoint mounts, and no DB
service. It does not supply HTTPS, DNS, backup scheduling, target DB persistence,
image digests or error-monitoring infrastructure. Its Python base tag floats;
exact Python patch/runtime and native dependencies must be tested in a pinned
target image. Recurring `/api/health` does not check median integrity; separate
summary/state probes are required after startup.

Read-only connected GitHub repository metadata was checked: default branch
`main`, homepage **null**. Together with the repository/deployment docs and local
environment, this did not identify a production provider, hostname or DB.
`deploy/.env` is absent. The r1 example requires explicit r2 artifact/hash/path
changes. Compose currently does not forward private legacy/scoring schema
overrides; if the target needs them, that is a configuration change to review
and test. Optional file-only research endpoints need pinned `reports/` assets
excluded from this image; their target availability is separately unverified.

Before the next production step, provide:

1. Release owner/operator, hosting platform and access path, approved HTTPS
   origin, production DB identity/network and dedicated median schema.
2. Separately provisioned least-privilege serving role and release-writer/DBA
   access, through a private secret channel; no secrets in chat or documents.
3. Recent target backup and an authorized separate recovery DB/restore operator,
   plus successful restore/query/application evidence.
4. Approved immutable build-context, base/API/web image digests and matching
   source/data/checkpoint/config assets tested on the target runtime.
5. Previous production publication/image/config pair, or an approved and tested
   first-publication recovery plan; maintenance/traffic cutover and alert owners.
6. Fresh desktop/mobile target verification and explicit acceptance of stale,
   sparse and unevaluated fallback scientific limitations.
7. Explicit authorization for the reviewed production migration, stage,
   publication and deployment sequence. This audit grants none.

## Runbook and changes made

Created [STATE_MEDIAN_PRODUCTION_RUNBOOK.md](STATE_MEDIAN_PRODUCTION_RUNBOOK.md)
with exact local verification commands and separately labelled conditional
operator procedures for backup/full restore, configuration, additive migration,
staging, expected-active publication, smoke tests, monitoring, rollback and both
application/publication partial-failure cases. It uses actual CLI options and
schema behavior, never invents a production UUID, domain, credential or image.
It explains that rollback cannot select an unpublished release or `none`, and
that switching strict expected-release settings can require a maintenance plan.

Added this report plus three scoped artifact/database/frontend audit reports.
Scratch contains fresh source reconstruction, test/HTTP/startup evidence, hash
inventories, local archive and read-only permission probes. No application,
forecast policy, tests, immutable artifact, district model or existing user file
was changed: the observed production blockers require target details, DBA work
or authorization, not an unreviewed local workaround.

**Final decision: NOT READY.** Resolve the listed production gates and retain
their evidence before requesting authorization for a controlled deployment.
