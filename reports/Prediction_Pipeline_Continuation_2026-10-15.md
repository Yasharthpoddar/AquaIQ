# Prediction pipeline continuation — 15 October 2026

This continues the remaining-work paragraph in `Prediction_Pipeline_Implementation_2026-10-14.md`. Work was applied to `C:\Users\Yasharth\Downloads\AquaIQ`. Scientific validation and software verification are different: passing tests does not establish forecast accuracy.

## Status of the remaining items

| Item | Result |
| --- | --- |
| Source availability and annual/daily rainfall overlap | The scheduled downloader obtained all three historical samples. The overlap test failed on actual rainfall values, so target-month download/export/merge stopped. |
| Current-period forecast accuracy | Prospective archive/evaluation infrastructure is implemented. Independent observations for future targets are still required. |
| Gap-aware and zone-aware uncertainty | Candidate replay and chronological calibration/evaluation tools are implemented. Fallback intervals are grouped by the actual source zone; sparse groups have no interval. Operational uncertainty is not established. |
| Comparable monitoring locations | A verified January 2025 snapshot was extracted and compared with January 2026: 9,543 exact location matches across 554 districts. Unique well identity and aquifer continuity remain unverified. |
| Independent crisis-score calibration | Strict independent-label diagnostics are implemented. No real independent labels or calibrated replacement weights are available. |
| Unattended updates | The Windows task `AquaIQ-Rainfall-Staging` is registered and its execution has been verified. It stages candidates only and requires the user to be logged in. |
| Production deployment | Docker/Nginx/Waitress configuration, environment validation and release-readiness checks are implemented. Docker is absent locally; container execution and a public host remain unverified. |

## Real rainfall findings

The task downloaded 2025-01-01, 2025-06-15 and 2025-09-30 from the official IMD daily endpoint. For each day, the annual and daily grids have 4,964 shared usable cells and matching usable-cell masks. Value agreement nevertheless fails the existing predeclared tolerances (`atol=0.001 mm`, `rtol=0.00001`).

| Sample date | Cells outside tolerance | Mean absolute difference | Maximum absolute difference |
| --- | ---: | ---: | ---: |
| 2025-01-01 | 2 | 0.0000261 mm | 0.0902 mm |
| 2025-06-15 | 346 | 0.16462 mm | 55.6660 mm |
| 2025-09-30 | 261 | 0.009501 mm | 7.8523 mm |

The real result is `overlap_requires_review`, not verified equivalence. Daily provisional and annual products may differ after quality-control revisions; the observed differences do not identify their cause. The implementation preserves both sources and does not weaken thresholds or rewrite observations to force agreement.

The publishable overlap evidence snapshot is `reports/candidates/rainfall_overlap_20261015.json`. Local execution state is in `reports/candidates/rainfall_refresh/2026-01_2026-09/overlap.json` and `progress.json`; the runtime directory is ignored so a fresh checkout does not inherit another machine's resume state. No target-month download phase was entered. Earlier manual probes timed out; the later task runs succeeded in obtaining the samples, superseding the availability-only blocker.

The task runs every 24 hours through Windows Task Scheduler, with hidden processes, per-run logs, a process lock and bounded requests. The checked run at 13:41:57 India time returned exit code 1 because the overlap gate required review; its stderr log was empty. The next recorded run was 16 October 2026 at 13:41:57 India time. This is a controlled data-quality stop, not evidence of a successful update publication.

Automatic start-month selection verifies the published rainfall CSV, manifest, canonical geography hash, source hashes and complete contiguous district-month coverage. The current artifact has 724 districts and 408 contiguous months through December 2025, giving a January–September 2026 staging plan. After a coordinated production release advances that artifact, the task advances its start month. Missing months, altered provenance and future months are rejected. A current artifact produces a no-work result.

## Real groundwater comparison

The official historical January PDF was downloaded using normal Windows TLS verification. Its SHA256 is `6ebb9cbf401c3fb7aca65c31b421ccf586c6fadbce5abb4d2a222e538b0534cd`. Actual table dates, units, layout and the next section boundary establish January 2025 on pages 1–332; the filename alone is not used to establish dates.

There are 15,892 source rows. The existing spatial/source audit accepted 15,278 and rejected 614, producing 573 candidate district-month averages. The original January 2026 ingestion remains unchanged. Stricter location-comparison eligibility yields 14,548 January 2026 locations and 9,543 exact matches with January 2025.

Gandhinagar illustrates the effect of monitoring-network composition. Each year has six eligible locations, but only three match. Those three locations have a mean depth change of **−1.8267 m**; the mean across all six locations in each year changes **+19.4550 m**. A positive change means deeper groundwater. These statistics describe their respective samples, not district-wide recovery or a validated long-term trend.

Matching requires normalized state/block/village names and coordinates to five decimals, with consistent canonical district and available well metadata. No nearest-location snapping is used. Dataset-level aquifer wording is retained separately from per-well metadata. The source does not establish stable unique well IDs or aquifer/construction continuity.

See `CGWB_January_Station_Comparison_2026-10-15.md` and `Station_and_Crisis_Validation_2026-10-15.md`. Raw PDFs, row-level candidates and source renderings are local ignored artifacts. January 2025 candidates have not been ingested. Persistent station-history storage and station-aware production trend calculations remain separate work.

## Forecast replay and uncertainty

`models/uncertainty.py` and `scripts/evaluate_forecast_replay.py` replay the full monthly serving path, including current-depth estimation and future-weather assumptions. They hide groundwater observations across the relevant district/zone panel and rebuild calendar-based fills and lags before inference. Truth is joined after prediction.

Explicit fit, development, calibration and later evaluation windows are required. The model cutoff must fit the declared training window. Calibration and evaluation targets cannot cross their reserved stage boundaries. Interval support is separated by horizon, data age, district/fallback source and the actual fallback zone. Unsupported groups remain `uncertainty_not_established`; another zone's residuals are not substituted.

Finite-sample residual ranks are experimental empirical intervals. Temporal/spatial dependence, unavailable historical publication vintages and model-selection independence still limit their interpretation. No interval was added to the live graph.

A small real **development-only** replay used Gandhinagar, Krishna and Delhi, July–December 2020 origins and simulated gaps of 0, 12 and 36 months. It produced 42 observed-target comparisons across three districts and four origins. The aggregate RMSE was **14.42 m**. This deliberately small, dependent sample contains substantial stale-data errors and is not a national or current-period accuracy estimate. It was not used to fit uncertainty intervals or select replacement model settings.

The original result is preserved in `reports/candidates/forecast_replay/development_full_path_20261015.json`. It predates the final per-zone interval schema (1.1); final interval tools reject the older artifact version. New replays also record the last observed depth and paired persistence-baseline errors. The preserved result has not been rewritten to imply that those new fields were present during its run.

## Prospective evidence and independent labels

`scripts/record_live_forecasts.py` archives selected current monthly forecasts with actual issue time, full weather assumptions, district/zone evidence, observation age, model card and model/data/config/geography hashes. Its CLI offers no backdating option. New candidate files use exclusive creation; records are checked for integrity before evaluation. Local hashes provide integrity checks, not an external timestamp authority.

Later evaluation requires independently measured, non-imputed district-month depths in metres below ground, actual observation and publication timestamps, source identity/checksum and matching canonical geography. Future, unpublished, duplicate, imputed or misaligned labels are rejected. Missing targets remain pending. Reports include horizon/source/gap errors and paired persistence comparison where available. No real observation labels are synthesized.

The real archive command succeeded for Gandhinagar and Krishna (district evidence) and Delhi (zone fallback). All three records have issue date 15 October 2026 and targets November 2026–April 2027. The checked archives contain **18 pending targets and zero independent outcome labels**. Their pending-evidence report is `reports/candidates/prospective_forecasts/pending_independent_observations_20261015.json`.

From the project root:

```powershell
.\venv\Scripts\python.exe -m scripts.record_live_forecasts
.\venv\Scripts\python.exe -m scripts.record_live_forecasts --run --district GJ-Gandhinagar --district AP-Krishna --district DL-Delhi
```

For later evaluation, supply existing archive files and a separately verified label CSV using `--run --archive ... --labels ...`. The offline plan prints the required columns. The station-comparison data are not automatically labels for these future targets.

`models/crisis_validation.py` separately validates external crisis-tier evidence and prospective score chronology. It rejects circular model-derived labels and requires a documented external tier/geography mapping. CGWB resource categories are not silently equated to AquaIQ tiers. Historical scores published after their target date cannot be relabeled as prospectively issued forecasts. Existing score weights and thresholds have not been recalibrated.

## Deployment and operating checks

`deploy/` provides Nginx SPA serving and API proxying, Waitress, read-only data/model mounts and an external existing PostgreSQL database. Startup rejects missing/mismatched models, empty/incomplete district/features/raw data, incomplete score publication and shipped credential placeholders. CORS can be configured with explicit origins or disabled for same-origin deployment. Docker DNS resolution follows API container replacement.

Read-only validation against the actual local release passed: 725 districts, 215,325 feature rows, 741,628 raw rows and 725 published score rows. Health, scores, district, history and monthly forecast requests returned HTTP 200. The forecast dates were November 2026–April 2027. Zero-change simulation preserved its baseline, and configured CORS allowed the listed origin and excluded an unlisted one. Hashes of the protected configuration, processed artifacts and model files were unchanged.

Docker is not installed here, so image builds, container runtime, HTTPS, DNS and public hosting are not claimed complete. `deploy/README.md` documents provisioning, a matching release restore, serving credentials, checks and recovery.

## Verification and release boundary

The first integrated full Python suite passed **683 tests**, with **12 opt-in database tests skipped** and 10 pre-existing NumPy/netCDF warnings. Subsequent review added tests for credential placeholders, automatic update progression, real historical PDF parsing, prospective archives and zone-specific interval isolation. The final consolidated run is recorded below.

The final consolidated suite passed **739 tests**, with **12 opt-in database tests deselected**, in 97.29 seconds. It reported the same 10 pre-existing NumPy/netCDF binary-size/deprecation warnings. Full output is preserved in `reports/candidates/pipeline_final_tests_20261015.txt`. The Windows scheduler scripts parse cleanly, Compose YAML structure was checked, and `git diff --check` passed. Container syntax/runtime validation still requires Docker.

After the live archive run, all **30 protected configuration/data/model files** matched their recorded hashes. The final guard report is `reports/candidates/final_artifact_verification_20261015.json`. An independent recomputation from `matched_locations.csv` confirmed 9,543 unique matched keys, no paired canonical-district disagreements, and the three-location Gandhinagar statistic.

At the end of the 15 October continuation, these changes were local. Publication is handled separately; consult Git history for the current state. No production observations, features, active models or scores were replaced. Source evidence and candidate diagnostics are available for review. Current forecast accuracy, calibrated intervals, independently calibrated crisis weights and public deployment remain unestablished.
