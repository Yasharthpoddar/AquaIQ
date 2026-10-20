# Preservation incident — 19 October 2026

**Finding: timestamp-only staging metadata refresh; no change detected in the scientific artifacts.** Windows events confirm PowerShell PID15428 executing `scripts/run_refresh_task.ps1`; the retained source and output explain the progress-file writes. The previously installed daily Windows task is the **most likely launcher**; its exact parent/task-instance link is not directly recorded. The original preservation failure remains valid and was not relabelled as a pass.

This investigation read the original [report](../actual_forecast_validation_20261019/REPORT.md), `preservation.json`, `checks.json`, the failed `diagnostics.log`, corrected `diagnostics_v2/verification.json` / `diagnostics-v2.log`, and both unexpected task logs. Only this new incident directory was created. No affected file was deleted, reverted, overwritten or regenerated; no refresh, download, database access, model pipeline, task start/stop/change, commit or push occurred.

## Exact changes — confirmed

| File / JSON field | Before UTC | After UTC |
|---|---|---|
| `data/raw/updates/rainfall_refresh/overlap/2025/download_progress.json` → `updated_at_utc` | 2026-10-18T08:12:08.010686+00:00 | 2026-10-19T09:04:25.737486+00:00 |
| `reports/candidates/rainfall_refresh/2026-01_2026-09/progress.json` → `phases.overlap_download.updated_at_utc` | 2026-10-18T08:12:08.010686+00:00 | 2026-10-19T09:04:25.737486+00:00 |
| Same candidate file → root `updated_at_utc` | 2026-10-18T08:12:08.167414+00:00 | 2026-10-19T09:04:25.981147+00:00 |

These are the **only differences**. Counts, statuses, paths, source hashes, comparison results and flags are identical; CRLF formatting and lengths remain 1,883 / 12,224 bytes. Ten / 22 byte positions differ, respectively.

| File | Recorded before SHA-256 prefix | Recorded after / current prefix |
|---|---|---|
| Download progress | `5139576f3da5471b` | `1e100216ead8c847` |
| Candidate progress | `58b8d98f31eff8f8` | `810261dfa6eefff1` |

Full hashes and byte positions are in [exact_diffs.json](exact_diffs.json); textual patches are [download_progress.diff](download_progress.diff) and [candidate_progress.diff](candidate_progress.diff).

The retained [October18 stdout](../candidates/rainfall_refresh/task_logs/refresh-20261018T134200-25188.stdout.log) matches the candidate's recorded **before** hash exactly. No standalone before-copy of download progress was found. Substituting its prior timestamp from that authentic log **in memory only** exactly reproduces the recorded before hash, establishing the single-field difference under the SHA-256 integrity assumption. No reconstructed JSON was written to disk. Both current affected files match their archived `discrepancy_after_bytes` copies; current candidate progress also equals October19 stdout byte for byte. October19 stderr is empty. Git ignores both progress files, so Git history does not recover their contents.

## Activity, commands and launcher

**Confirmed evidence:**

- A prior local command record on **October15,08:06:50.715UTC** invoked `register_refresh_task.ps1 -EveryHours 24 -MaxDays 10 -Install`; its recorded response at08:06:58.253 says `Installed=true`. The selected command/response is retained in [historical_registration_record.json](historical_registration_record.json), without unrelated conversation content.
- The existing `AquaIQ-Rainfall-Staging` task is **enabled/Ready**, repeats daily, has `StartWhenAvailable=true`, and invokes this repository's wrapper with `-StartMonth auto -MaxDays 10`. Its reported last run is **October19,09:04:19UTC**, result1. Current next scheduled boundary is **October20,08:11:57UTC / 13:41:57IST**; actual execution may be later. It was left unchanged.
- Windows PowerShell event400, record111732, directly records **PID15428**, wrapper command/arguments, and engine start **09:04:21.2995823UTC**. Event403, record111733, records the same process/host stopping **09:04:26.9824791UTC**. The log filename's `143421` is local IST and `15428` is the wrapper's PowerShell PID, not a demonstrated Python child PID. See [Windows evidence](windows_evidence.json).
- The wrapper ([source:13–15](../../scripts/run_refresh_task.ps1)) constructs the exact stdout/stderr filename pattern, starts Python `-m scripts.stage_rainfall_update --run`, and redirects both streams. The observed file creation/write times fall within that engine interval; [file timestamps](file_timestamps.json) retain UTC values.
- Source review shows cached retries still rewrite progress timestamps: `imd_realtime.py` inventories existing files and calls `save_progress()`; `stage_rainfall_update.py` stamps a fresh report even when reusing the existing overlap comparison. The log records **three already-present files, zero downloaded, zero failed**, then `overlap_requires_review`. All three overlap probes still fail the declared rainfall tolerance; control flow returns before the target-download/export/merge phase. Planned actions listed in the report are not evidence that those actions executed.

**Inference:** the installed daily task caused a cached retry of the wrapper, updating two timestamps and adding fresh stream logs. Matching action, last-run time, PID-confirmed wrapper interval, exit1 and repeated daily logs strongly support this explanation. Result1 is consistent with the retained source's refusal to proceed past the overlap gate. Source control flow plus cache counts support no HTTP download in this attempt; the `network_requests_made=0` field itself describes the comparison phase, not an independent network trace.

**Remaining uncertainty:** Task Scheduler's Operational history is disabled; no task-instance/parent-process event establishes whether the daily trigger, a manual task start or another caller launched PID15428. The Python child PID and OS file-write audit were not captured. No direct ultimate-launcher identity or reason for the delayed start is claimed. Initial sandbox task/event queries were denied; elevated **read-only** queries produced the evidence above. History was not enabled and no task was modified.

## Integrity verification

All **154 files** listed in the completed research `INVENTORY.json` still match their recorded hashes. Verification used bytes only, with no deserialization or model execution.

| Artifact group | Verified unchanged |
|---|---:|
| Telangana acquisition and retained metadata/receipts | 16 files |
| Original and corrected normalized research data | 7 + 7 files |
| Original and corrected evaluation, including row predictions and historical models | 33 + 33 files |
| Well-baseline evidence | 11 files |
| Active checkpoint directory | 18 files |
| Scientific audit / safe-fixes / provenance / submission evidence | 14 / 6 / 9 / 6 files |

The production feature export also matches. Against the original 658-file baseline, the same **656 unchanged / two timestamp-only discrepancies** remain; there is no additional scientific-file change. Commit remains `905f3c32304fa196015b8cd3113ec77f6b0a7d84`; the 11 pre-existing user edits are intact. This investigation's separate 815-file snapshot is checked again at completion. [Verification details](verification.json) retain individual hashes. Local inventories are not an independently signed custody record, and filesystem checks do not inspect database contents.

## Recommended containment — not performed

1. Obtain approval to pause the enabled `AquaIQ-Rainfall-Staging` task before further frozen audits, checking for duplicate launchers first. Preserve task configuration and execution evidence; do not delete the historical files.
2. In a separately approved change, make future staging attempts use distinct run directories and keep mutable progress outside immutable research snapshots. Record wrapper/child/parent IDs, task-instance ID, exact command, code hashes and cache/network counts.
3. Enable appropriate task execution history after review so future parent/trigger attribution is possible. Do not infer a human actor from a PID or filename.
4. Keep the failed original preservation evidence. Establish a new baseline only after activity is controlled and explicitly acknowledged; do not replace old hashes or normalize away timestamp changes retrospectively.

The discrepancy is explained at the **write mechanism and content** level. Ultimate launch attribution remains qualified. This finding does not remove the forecasting study's geographic/provenance limitations or approve real shadow issuance.
