# Twelve-month research publication — 21 October 2026

The user explicitly requested a GitHub push after local finalization and startup. This authorizes publication of the **51-file allowlist** accompanying this guide. The target is `experiment/12-month-horizon`; `main` remains the recoverable six-month baseline. Earlier reports' publication holds and no-commit statements describe their original dates; they are preserved rather than rewritten. This publication does not promote a model or approve deployment.

## What this branch contains

The primary research experience now targets the observed calendar month M+12, shows one annual baseline (persistence = annual seasonal naive), and keeps legacy six-month/monthly products separate. `/research` mounts the independent file-backed panel. Compatible historical artifact loading checks horizon, features, units, generation, scope and hashes. Unsupported geography and missing evidence produce explicit unavailable results.

- [Application finalization](../candidates/twelve_month_horizon_finalization_20261020/REPORT.md), [execution/local commands](../candidates/twelve_month_horizon_finalization_20261020/COMMANDS.md), [fixed-artifact build verification](../candidates/twelve_month_horizon_finalization_20261020/artifact_build.json).
- [Preserved twelve-month study](../candidates/twelve_month_horizon_20261020/REPORT.md), [protocol](../candidates/twelve_month_horizon_20261020/protocol.json), [aggregate metrics](../candidates/twelve_month_horizon_20261020/evaluation/metrics.json), [paired uncertainty](../candidates/twelve_month_horizon_20261020/evaluation/uncertainty.json).
- [Exact publication allowlist](ALLOWLIST.txt), [review summary](REVIEW.json), [link-availability inventory](LINK_AVAILABILITY.csv). The review script performs no training, database access or downloads.

The original 792-case/33-district comparison has annual baseline RMSE 1.458 m versus expanding XGBoost 1.420 m; its difference interval crosses zero and sensitivities reverse the apparent advantage. These are conditional historical results with serious geographic/provenance limitations. The new fixed-cutoff Adilabad artifact has a separate 24-case historical check: **annual baseline RMSE .877 m versus ML 2.664 m**. Those previously inspected cases favor the baseline and establish no prospective skill. The code change follows an explicitly chosen research objective, not an accuracy-based promotion.

Final local checks recorded 229 Python passes, one Windows symlink-privilege skip and three deliberately deselected unrelated fitting tests; 23 frontend passes, lint and isolated build passed. The published sources match the checked versions. Source/publication integrity and secret checks accompany this branch; unit fixtures remain synthetic and separate from the historical study.

## Deliberately local assets and references

The descriptor `research/twelve_month_app.json` contains the frozen contract and hashes, **not the model or inputs**. Its referenced runtime bundle is deliberately absent: model JSON, feature CSV, per-input provenance rows and bundle manifests/cards remain local. A clean clone therefore returns research-artifact unavailability until the exact locally retained assets are restored. It must never substitute a six-month checkpoint, fabricate a result or train automatically.

Raw acquisitions, normalized/panel/well tables, row-level predictions, all trained checkpoints, database contents, environment credentials, task XML/state exports, private command/event records, local logs, large filesystem inventories and scratch outputs are excluded. In particular, the original cookie-bearing `reports/actual_forecast_validation_20261019/source_manifest.json` and `acquired/nwic_copyright.html.retrieval.json` remain unchanged and private. Their header values are compared in memory for absence from the allowlist and are never printed or copied. No new sanitized acquisition manifest is needed for this publication; the earlier tracked public provenance companion remains available.

Historical reports intentionally retain links to local-only rows, artifacts, receipts and test logs. These are not downloadable assets in this branch. `LINK_AVAILABILITY.csv` distinguishes tracked/included targets, existing local exclusions, missing references, machine-local paths and external links. This compact branch is a source/evidence publication, not a self-contained data/model distribution.

## Local application versus verified science

The separately requested local run started a guarded research API at port 5051 and Vite at port 5181; host HTTP checks confirmed the page HTML and the default research response. Open `http://127.0.0.1:5181/research` on that running host; select origin `2024-01` for the historical comparison. Current/default May 2026 → May 2027 ML remains unavailable because weather is missing and the artifact is historical-only. The run receipt is local under `scratch/local-research-run-*`. Full interactive browser rendering was not independently verified by the publication check. Earlier finalization-time browser/HTTP failures remain recorded unchanged.

Reproduction and demonstration commands in the linked reports require existing compatible local assets and dependencies. No refresh, ingestion, training, scoring, schema or database operation was executed to publish or run this guarded panel. The demo blocks database access/fitting and legacy endpoints; normal legacy pages additionally require the matching populated database and active six-month assets. A server response or successful model load establishes neither forecasting accuracy nor production readiness.

Real shadow issuance remains **NO-GO** and HGB remains abstained. Acquisition/availability times, stable physical well/datum continuity, geographic correctness, useful future ML skill, twelve full months of operational lead and national generalization remain unverified. The 0–100 score remains an uncalibrated project index; ANN agreement with fuzzy labels is not independent outcome validation; extraction remains heuristic sensitivity analysis. Nothing is deployed by this Git push.
