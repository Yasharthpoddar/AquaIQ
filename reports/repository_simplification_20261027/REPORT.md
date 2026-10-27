# Repository simplification — 2026-10-27

This pass simplifies navigation and removes verified generated or redundant payloads. It does not change application code, forecast logic, observations, model weights, production pointers, dependencies, existing test assertions or academic deliverables. The experiments still do not justify replacing frozen production.

## Git baseline and outcome

- Initial branch: `main`, clean and synchronized with `origin/main`; commit `6660e24d356cfc5794b9fb0bffad0bc050ade217`.
- Remote: `https://github.com/Yasharthpoddar/AquaIQ.git`. Fetch succeeded before isolation; no reset, rebase or merge.
- Cleanup branch: `chore/aquaiq-repository-simplification-20261027`.
- A separate local cleanup commit is created only after validation and staged-scope review. Its exact SHA is recorded in the ignored local `commit_receipt.json` after committing. It can also be resolved with `git log -1 --format=%H -- reports/repository_simplification_20261027/REPORT.md`.
- No push, merge into main, branch deletion or history rewrite is part of this task. The initial main commit remains the archive source and branch ancestor.

## Decisions and exact inventories

The before-deletion [proposal](PROPOSED.md), [inventory](inventory.csv.gz), [deletion plan](deletions.json.gz), [reference checks](reference_checks.json) and [review record](review_approval.json) precede [application](applied.json). Files were inspected by purpose, Git status, size, timestamp, checksum and repository references. [Local asset groups](local_assets_inventory.json) include ignored datasets, models, rollback, builds, dependencies and experimental work; their location alone was not a deletion criterion.

| Removed group | Files | Logical bytes | Reason |
| --- | ---: | ---: | --- |
| Tracked historical pytest captures | 372 | 1,078,414 | Generated fixture copies, including deliberately tiny placeholder models; no current source/test/CI input reference. Real test source and result manifests remain. |
| Tracked accuracy drafts/duplicates | 8 | 1,257,313 | Four superseded Markdown drafts, three identical old plot/checksum copies and completed progress identical to final results. |
| Ignored historical pytest payloads | 9,077 | 3,763,166,613 | Generated test output in 12 individually reviewed roots; references were dated inventories/preservation snapshots, not scientific or runtime inputs. |
| Source-backed bytecode | 25 | 503,468 | Regenerable bytecode with retained source. |
| **Total pre-existing files** | **9,482** | **3,766,005,808** | **380 tracked files; 2,730 empty directories also removed.** |

All exact paths, reasons and original hashes are in the machine-readable plans. Every target was checked for unchanged size, modification time, SHA-256 and absence of reparse points before leaf-only deletion. Empty directories were removed only after their verified files; no mixed parent was recursively deleted.

Tracked bytes are recoverable from the pinned source commit using [archive instructions](../ARCHIVE.md) and [per-file representations/hashes](archives.json). Actual recovery of **all 380 files** succeeded with checksum verification; the helper also has 11 passing cases for safe paths, raw/CRLF recovery, corruption and overwrite/preflight refusal. Historical manifests retain their original dated meaning and require recovery before reproducing whole-tree preservation checks.

Unique accuracy evidence, corrected `REPORT.md`/`analysis_v2`, failed acceptance gates, the rejected grouped artifact, original/corrected metric trail, protocols and negative conclusions remain. Only duplicate/superseded working copies were pruned. Earlier cleanup history remains intact.

## Documentation and retained material

The shortened [root README](../../README.md) covers installation prerequisites, current serving, architecture/API, limitations and verification. Unique maintenance/sample/audit/replay instructions moved to [MAINTENANCE.md](../../docs/MAINTENANCE.md). New [documentation](../../docs/README.md), [evidence](../README.md) and [accuracy](../accuracy_experiments_20261027/README.md) indices identify authoritative and historical material. The generation-specific historical warning remains explicit. Narrow ignore rules prevent restored captures/drafts from being accidentally recommitted.

Retained: all current source/tests/fixtures/CI, dependency manifests and installed environments; production/research/rollback bundles; raw and accepted processed observations; official archives, provenance, evaluation panels and baseline artifacts; final-release/retraining/accuracy evidence; seven already tracked large scientific CSVs; existing dashboard/build copies; academic TeX, SRS, presentations, diagrams, attribution and licenses. No private local environment/database contents were added to Git. No meaningful test was removed or weakened.

Ambiguities deliberately retained are listed in [review.json](review.json): five historical fixture files whose Git bytes cannot be verified against their working bytes using the known newline transforms, and one bytecode file without a source counterpart. Seven historical frontend builds also remain because process inspection returned `CimException`; active local use could not be ruled out. Installed dependencies, `dashboard/dist` and the independent reproduction environment were preserved. These are possible later review opportunities, not approved deletions.

## Storage measurements

Pre-existing leaf-file logical sizes total **3.766 GB (3.507 GiB)** removed. Volume free space rose from **16,780,840,960** to **20,560,166,912** bytes immediately around deletion (a **3,779,325,952-byte** difference). Volume allocation, compression and concurrent activity can differ from logical lengths; neither figure claims Git-history savings. No Git garbage collection was performed.

Tracked files: **1,789 before; 1,455 after**. Initial tracked working-file size was **456,388,173 bytes**; the remaining tracked tree is approximately 455 MB. The exact final count and logical working-file size are in `staged_review.json`. This measures tracked file content, not `.git`, external data, installed dependencies or total filesystem allocation.

After validation, **399 newly generated files / 40,331,852 logical bytes** were removed separately: recovered archive copies, fresh test fixtures and the scratch frontend build. These are excluded from the pre-existing savings above. Their [exact plan](verification_transients.json.gz), [proposal](VERIFICATION_PRUNING.md) and [receipt](verification_pruning_applied.json) use the same bounded leaf-file method. Existing builds and verification logs were retained.

## Validation and preservation

| Check | Actual result |
| --- | --- |
| Python final full suite, including integration | **1,786 passed, 1 skipped, 70 warnings**, exit 0, 190.08 seconds; [JUnit](pytest_final.xml), [command](python_final_exit.json). |
| Focused rerun after correction | **38 passed**, exit 0; existing metadata/export tests plus 11 new archive cases. |
| Frontend | **160 tests passed**; lint and fresh scratch build exit 0. Existing `dashboard/dist` untouched. |
| Syntax/imports | In-memory compile and eight core imports passed; see [receipt](syntax_import_schema.json). |
| Database migration safety | All 15 migration-safety cases passed, including isolated rollback/idempotence integration. Public-schema reinitialization was deliberately not run against populated data. |
| API and bundles | HTTP 200 healthy, database connected, legacy/monthly/twelve-month models loaded; five production/research/frozen/rollback bundles loaded. [Runtime receipt](runtime_checks.json). |
| Protected bytes | **1,017 protected files plus 73 existing scripts/docs/CI files** unchanged after validation; [final receipt](final_preservation.json). |
| Public data | All **14 public-table row counts and sorted-row content fingerprints** identical [before](public_before.json) and [after](public_after.json), using a read-only repeatable-read transaction. |
| Links, commands, CI and staged review | Recorded in `links_syntax_final.json` and `staged_review.json`; strict staged secret scan recorded in `staged_scan.json`. |

The final link check resolves **625 local file links across 102 Markdown files**; 18 retained historical links use machine-specific `file:` URLs and remain a portability opportunity. All 295 tracked/new Python sources compile in memory. `links_syntax.json` is explicitly marked as the superseded provisional check, before this report existed and before file/line link suffix handling was corrected. Setup, ingestion, training and public-schema migrations were checked for references but were not executed as housekeeping.

The **first full run failed**: 1,784 passed, two failed and one skipped. One existing metadata test caught a historical generation warning omitted by the shortened README; the warning was restored. A separate test hit Windows `WinError 5` during atomic replacement of a test-only export. The unchanged test passed on fresh paths in both the focused and full final runs. No application logic, assertions, expected outputs or skip policy changed. [Validation history](validation.json) records both attempts. The remaining skip requires Windows symlink privileges/developer mode; warnings include existing xarray/netCDF deprecations. Local raw logs remain available and ignored.

Two explicitly identified synthetic negative-test userinfo labels were sanitized only in the published JUnit; test outcomes/counts are unchanged and raw/published hashes are in [the receipt](junit_sanitization.json). Source tests remain byte-identical. No forecast skill, probability calibration, independent current-period accuracy or target-host deployment readiness is inferred from passing software checks.

The active pointer SHA-256 remains `1a0dde587ccd6b005a4bac32cbc81105b80ef956052191dbdb5cf2b6bec1e83b`. Production model SHA-256 remains `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`. Retained enriched model SHA-256 remains `e4e57de9f681b2f2702c9b86a00be06b04147123ecea0579f6abcf3cdc586192`; its checkpoint pointer remains `cda6d6197fb0d646df041ddefb61ca96aa390b583215941ffdb43ed3316be634`. [Before identities](models_before.json), runtime loads and the final preservation check agree. No promotion or new production dataset generation occurred.
