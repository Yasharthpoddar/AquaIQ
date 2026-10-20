# Academic publication guide — 20 October 2026

This is a reviewed, compact research-evidence publication accompanying the existing AquaIQ presentation changes. The user renewed the instruction to push to GitHub and run the local project after the [stabilization report](../final_stabilization_20261020/REPORT.md) recorded a publication stop. That report and all earlier evidence remain unchanged as historical records. Their statements that no commit/push had occurred describe those earlier tasks.

## Evidence and scientific scope

- [Scientific validation](../scientific_validation_audit_20261018/REPORT.md), [safe fixes](../post_audit_safe_fixes_20261019/REPORT.md), [issuance feasibility](../provenance_issuance_20261019/REPORT.md) and [presentation finalization](../submission_finalization_20261019/FINALIZATION.md).
- [Telangana historical report](../actual_forecast_validation_20261019/REPORT.md), [frozen protocol](../actual_forecast_validation_20261019/protocol.json), [corrected metrics](../actual_forecast_validation_20261019/evaluation_v2/metrics.json) and [saved district predictions](../actual_forecast_validation_20261019/evaluation_v2/historical_predictions_vs_observations.csv).
- [Preservation incident](../preservation_incident_20261019/REPORT.md), [exact diffs](../preservation_incident_20261019/exact_diffs.json) and [later integrity verification](../final_stabilization_20261020/integrity-summary.json). The original failed preservation result remains retained; it is not relabelled as a pass.
- [Public source provenance](PUBLIC_SOURCE_PROVENANCE.json), [explicit release allowlist](ALLOWLIST.txt) and [link-availability inventory](LINK_AVAILABILITY.csv).

On the **594-case, 33-district conditional historical Telangana primary cohort**, seasonal naive RMSE was **1.440 m**, expanding XGBoost **1.472 m**, and locked historical HGB **1.790 m**. Primary targets span January 2024–June 2025. These results use current source vintages and have serious source-name/coordinate conflicts; they do not establish reliable district-specific or operational forecasting skill. The older 209-case benchmark is separate and also favors seasonal naive over HGB. No new training, tuning, selection or forecast issuance is part of this publication.

AquaIQ remains a research prototype. Real shadow issuance remains **NO-GO**, HGB remains abstained, and the six-calendar-month horizon/settings are unchanged. Prospective forecasting skill, nationwide generalization, independent crisis calibration and causal extraction effects remain unverified. The crisis score is a project-defined uncalibrated index; the extraction simulator is heuristic sensitivity analysis.

## What is deliberately absent from GitHub

Original acquisitions, large normalized/well-panel tables, well-level prediction exports, historical model binaries, active runtime checkpoints/data, task XML, rainfall logs, private command/event records, environment/credentials and the database remain local. No ignored runtime artifact is force-added. Historical inventories refer to both published and local-only evidence; their presence does not mean every inventoried file is in the clone.

The preserved original `source_manifest.json` and `acquired/nwic_copyright.html.retrieval.json` contain HTTP session-cookie headers and are **excluded**. Their values were not tested or published. `PUBLIC_SOURCE_PROVENANCE.json` is a new derivative of the original manifest: authentication/cookie headers are removed, remaining response headers are restricted to a metadata allowlist, and the original local manifest's SHA-256 is recorded. The original manifest and receipts are unchanged. The derivative is source documentation, not a point-in-time availability certification or replacement for original acquisition bytes.

Preserved reports contain links to excluded local evidence, including the original source manifest; the old rainfall stdout log, Windows evidence and registration record; and stabilization before/after snapshots, task-state and XML-verification records. Some earlier documents also use machine-specific absolute links. **These links are historical local references, not downloadable public assets.** `LINK_AVAILABILITY.csv` records each selected Markdown link's repository target, whether that target is published and whether its syntax is machine-local. Repository-relative links to included files can be followed directly; machine-local links should be located by the listed repository path.

## Running the existing local prototype

A fresh clone lacks the populated database, configured local environment, raw/processed datasets and trained checkpoints. It is not a self-contained verified runnable distribution. Publishing research/reproduction scripts does not authorize executing their fitting, downloading or mutation steps. Those commands remain historical maintainer references.

With the existing restored local environment, start the API on loopback and the frontend in separate PowerShell terminals:

```powershell
$env:FLASK_HOST = '127.0.0.1'
$env:FLASK_PORT = '5000'
$env:FLASK_DEBUG = 'false'
.\venv\Scripts\python.exe -B -m api.app
```

```powershell
npm.cmd --prefix dashboard run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173/`. The homepage reads saved scores/configuration. District and simulation pages can compute active XGBoost estimates when used; they do not establish validated real-time forecasts. No HGB shadow campaign is started. The earlier 14 focused tests, lint and isolated build passed; their outputs are in the preserved stabilization report. This local run is not deployment or evidence of scientific readiness.

For a later release, retain explicit file selection, repeat secret/link review and verify the remote branch before pushing. Never add the complete local evidence directories indiscriminately.
