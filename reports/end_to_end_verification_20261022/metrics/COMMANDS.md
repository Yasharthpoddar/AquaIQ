# Saved-row metric audit command receipt

Working directory: `C:\Users\Yasharth\Downloads\AquaIQ`.

Interpreter: `C:\Users\Yasharth\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.

All invocations used `-B` to suppress bytecode writes. Only Python standard library, NumPy, and pandas were imported; the report writer also executed the new v2 audit helper's definitions through `runpy.run_path` without running its main routine. No project model/app modules were imported, and no model artifact was deserialized.

```powershell
& 'C:/Users/Yasharth/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B 'reports/end_to_end_verification_20261022/metrics/audit_saved_metrics.py'
```

Executed 2026-10-23 04:02:30–04:02:36 UTC. Exit 1. Results: 688 checks; 686 passes, two raw-byte implementation hash mismatches. Both mismatches exactly disappear after in-memory CRLF→LF normalization. Original raw failures and raw hashes are preserved in `run.json`, `artifact_checks.json`, and `newline_normalization_receipt.json`. No source bytes were changed. Seventy-two registered inputs unchanged.

```powershell
& 'C:/Users/Yasharth/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B 'reports/end_to_end_verification_20261022/metrics/audit_saved_metrics_v2.py'
```

Executed 2026-10-23 04:04:49–04:04:53 UTC. Exit 1. Results: 430 checks; 428 passes, two audit encoding-assumption mismatches. The retained six-month case ID format differs from twelve-month IDs, and the fixed app training membership uses canonical JSON rather than newline-sorted hashing. Source-text inspection establishes both formats; original failure evidence remains in `supplement_run_v2.json` and `supplement_checks_v2.json`. No source/data/artifact changes. All registered inputs unchanged.

```powershell
& 'C:/Users/Yasharth/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -B 'reports/end_to_end_verification_20261022/metrics/write_metrics_report_v3.py'
```

Executed 2026-10-23 04:07:13–04:07:14 UTC. Exit 0. Results: 46 checks, all pass, including documented encoding resolution and direct sampled-row reconstruction of the three retained horizon-comparison bootstrap entries. Combined direct-row verification covers 228 saved interval pairs/456 endpoints across 19 cohort/model entries, within absolute tolerance 1e-10. All registered inputs unchanged. Produces `METRICS.md`, `encoding_resolution_v3.json`, `direct_row_horizon_bootstrap_v3.json`, and `report_run_v3.json`.

Each audit script opens output files with exclusive create mode and refuses to replace them. Do not rerun against these existing output names. Prior scripts, failed audit attempts, and all evidence were retained.
