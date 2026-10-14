# Prediction pipeline implementation — 14 October 2026

## Implemented and exercised locally

- `data_ingestion.imd_realtime` now has explicit download modes for complete-month ranges or a few selected historical dates. Downloads use the official HTTPS endpoint, bounded response size, strict date/filename/grid checks, atomic staged files, retries and saved progress. Valid cached files are rechecked before reuse; corrupt cached files are replaced only after a valid response. Consecutive/total failure budgets stop a failing endpoint. The default remains an offline plan.
- `data_ingestion.imd_realtime_comparison` compares staged historical days against a verified annual archive, including source provenance, checksums, missing masks and rainfall values. Default tolerances are 0.001 mm absolute and 0.00001 relative. A passing report requires three distinct months with samples inside and outside June–September. Agreement is limited to sampled dates, not a declaration of every date's quality or model accuracy. A later export rechecks sources and reruns the comparison.
- `data_ingestion.imd_realtime_monthly` requires verified sampled overlap and every daily record of every requested month before producing candidate CSVs/manifests. Missing cells remain missing for the month. The existing canonical boundary/spatial aggregation is retained. Outputs are restricted to candidate/update folders; unrelated, partial or changed existing output files cannot be overwritten. Provisional status is preserved through candidate export and rainfall merge.
- `models.climate_forecast --eval` evaluates a saved monthly bundle without fitting or publishing it. `--candidate-checkpoint` isolates experimental training. Protected outputs include both active forecast models, model cards, immutable bundles and feature inputs.
- `scripts.validate_monthly_candidates` runs development comparisons using explicit calendar folds and six-month embargoes, excluding all 2020 onward rows before label construction. Models are fitted only in memory and never published. Optional per-case exports are explicitly development residuals, not independent interval calibration.
- README now describes January 2026 groundwater and complete 2025 rainfall rather than the old March 2023 groundwater cutoff. Candidate model binaries are excluded from Git.

## Live source attempt

The official endpoint timed out for all three historical overlap samples: 1 January, 15 June and 30 September 2025, with two attempts per date. Results are staged at `data/raw/updates/20261014/imd_overlap/probe_download_results.json`.

The 2026 staging run reused all three previously validated grids (1 January, 15 June and 30 September). Three additional requests, for 2–4 January, timed out. The consecutive-failure guard stopped the run: **3 of 273 days complete, 270 unavailable** (three failed this run and 267 not attempted). Progress and errors are saved in `data/raw/updates/20261014/imd_realtime/download_progress.json`. No complete month or passing overlap report exists, so no 2026 rainfall candidate was promoted. The working dataset remains rainfall through December 2025, latest imported groundwater January 2026, and ERA5 through December 2024.

No database ingestion, feature replacement, active model replacement or score publication was performed by this implementation work.

## Model checks performed

The saved monthly model reproduced **1,936 observed evaluation labels and RMSE 2.455514 m**. `reports/candidates/monthly_validation/current_saved_evaluation_20261014.json` is the separate result. Source data, configuration, both active model pointers/cards/assets and the original training report were hashed before and after; `saved_evaluation_integrity_20261014.json` confirms preservation.

Development comparisons used the current fixed model parameters with one worker:

| Fold | Evaluation target period | Paired seasonal cases | XGBoost RMSE (m) | Seasonal RMSE (m) | Result |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | Origins from July 2011, targets through December 2013 | — | — | — | Skipped: early training history lacks a required horizon |
| 2 | Origins from July 2014, targets through December 2016 | 10,219 | 2.093775 | 2.224139 | Development evaluation |
| 3 | Origins from July 2017, targets through December 2019 | 8,611 | 2.689256 | 2.817341 | Development evaluation |

Full fold definitions, observed counts, input fingerprints and per-horizon metrics are in `reports/candidates/monthly_validation/development_evaluation_20261014.json`. Better development results do not overturn the existing final-period seasonal comparison or establish present-period accuracy. No candidate was promoted and no uncertainty bands or calibrated crisis weights were claimed.

## Repeat source verification when the endpoint is available

Run from the project root with its Python environment. First retrieve only the selected overlap samples:

```powershell
.\venv\Scripts\python.exe -m data_ingestion.imd_realtime `
  --dates 2025-01-01 2025-06-15 2025-09-30 --download `
  --staged-dir data/raw/updates/20261014/imd_overlap

.\venv\Scripts\python.exe -m data_ingestion.imd_realtime_comparison `
  --annual-file data/raw/updates/20261013/imd/Rainfall_ind2025_rfp25.grd `
  --annual-year 2025 --staged-dir data/raw/updates/20261014/imd_overlap `
  --dates 2025-01-01 2025-06-15 2025-09-30 `
  --output reports/candidates/rainfall_20261014/overlap.json
```

An incomplete download exits 1; a completed download exits 0. The comparison exits 2 for differences requiring review. Investigate annual/provisional quality-control differences; do not widen thresholds simply to force a pass. Only after that review, resume the target-year batch and validate complete months:

```powershell
.\venv\Scripts\python.exe -m data_ingestion.imd_realtime `
  --start 2026-01 --end 2026-09 --download `
  --staged-dir data/raw/updates/20261014/imd_realtime

.\venv\Scripts\python.exe -m data_ingestion.imd_realtime `
  --start 2026-01 --end 2026-09 --validate-staged `
  --staged-dir data/raw/updates/20261014/imd_realtime

.\venv\Scripts\python.exe -m data_ingestion.imd_realtime_monthly `
  --start 2026-01 --end 2026-09 `
  --staged-dir data/raw/updates/20261014/imd_realtime `
  --overlap-report reports/candidates/rainfall_20261014/overlap.json `
  --output reports/candidates/rainfall_20261014/monthly.csv `
  --normals-output reports/candidates/rainfall_20261014/normals.csv
```

These commands stage and export only. Before a production promotion, take a new database/dataset/model backup of the current January 2026/2025 generation, merge into separate candidate artifacts, validate source coverage, ingest and rebuild matching features and both bundles, evaluate and publish a complete scoring run. The 13 October backup is the older pre-refresh recovery point and must be preserved.

## Verification

All **528 database-independent Python tests passed**, with 12 opt-in database tests deselected. The suite includes retry/resume, strict source verification, missing-day/cell handling, source/output preservation, candidate ownership, chronological development isolation and saved-model evaluation guards. Ten existing NumPy/netCDF deprecation/binary-size warnings were reported; no tests failed. No database schema or data writes were introduced in this implementation, so the database integration suite was not repeated.

`git diff --check` passed. A final post-development/post-test comparison against `active_artifact_snapshot_20261014.json` confirmed **zero changes** to the frozen configuration, feature/rainfall artifacts, both active model pointers/cards/assets and original monthly training report.

## Remaining work

Source availability and actual annual/daily overlap remain unresolved. Current-period accuracy, gap-aware and zone-aware uncertainty calibration, comparable monitoring-station trends, independent crisis-score calibration, unattended update scheduling and production deployment remain separate work. Fresh observations are necessary to evaluate current projections; development residuals alone cannot establish their uncertainty. Code and reports are local changes and have not been pushed by this implementation run.
