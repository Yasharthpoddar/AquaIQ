# AquaIQ repair report — 13 October 2026

The repaired project is `C:\Users\Yasharth\Downloads\AquaIQ`. Source changes, regenerated physical-unit datasets, verified model bundles, and the PostgreSQL feature/scoring outputs have been applied locally. Changes remain uncommitted; no remote deployment was performed.

**Follow-up:** the district prediction graph now shows six future monthly statistical projections from today. This is a separate exploratory method; historical XGBoost endpoints and scores retain their original dates. The updated full suite passes **169 tests**. See [AquaIQ_Monthly_Prediction_Update.md](AquaIQ_Monthly_Prediction_Update.md) for the new behavior, all-district checks, and historical evaluation limits.

**Latest follow-up:** the seasonal-only future graph in that follow-up has been superseded by a monthly XGBoost model using rainfall, temperature, and evapotranspiration assumptions. See [AquaIQ_Weather_Prediction_Update.md](AquaIQ_Weather_Prediction_Update.md) for the current behavior and verification; the original repair results below remain a record of that earlier work.

## Completed repairs

- Regenerated IMD district rainfall and ERA5 district weather with corrected spatial fallback and explicit monthly units. Audited upserts corrected 779 IMD values and 192,259 ERA5 values. Original groundwater observations were preserved; a subsequent full ingestion run produced zero additional weather corrections.
- Replaced mixed legacy/normalized feature rows with one causal physical-unit generation. Stored provenance distinguishes actual observations, bounded forward fills, and missing values. Rainfall normals use earlier years instead of future-period climatology.
- Rebuilt six-calendar-month labels using date joins and observed future targets. Training/evaluation use label-date cutoffs, temporal separation, and persistence/seasonal baselines. Immutable model/card bundles have checksums, named features, units, and generation checks.
- Backtests use genuine held-forward predictions and the serving components. They write candidate calibration reports without replacing production weights or checkpoints. Initial weights are explicitly uncalibrated.
- Removed invented monthly/2027 curves and missing-data scores of 50. Forecasts expose one supported endpoint, the actual observation month, historical status, source zone, and model limitations. Partial-month cutoffs exclude incomplete monthly aggregates.
- Implemented real zone aggregation for districts without adequate local evidence. Four districts with inadequate district/zone evidence return null scores instead of manufactured tiers.
- Publish complete scoring batches in one transaction. Prediction origins, model/data identity, and source provenance are persisted. Deterministic run IDs prevent duplicate forecasts for identical inputs; serving refuses batches from mismatched scoring code, settings, models, or feature generations.
- Canonical migration now preserves already canonical and unmapped valid districts, audits collisions, rejects cross-state conflicts, preserves provenance, and rolls back unsafe changes. It was tested in isolated PostgreSQL schemas; the identity migration was not needed or executed on the live district master.
- APIs return strict JSON, validate inputs, close connections, preserve unavailable evidence, and return service errors rather than fake scores. Zero-change simulation matches ordinary scoring. Extraction changes are labelled project sensitivity heuristics.
- Dashboard pages show failures/retry, unavailable evidence, historical observation dates, forecast target dates, and zone provenance. District navigation and scenario edits cannot leave a previous district/scenario result displayed as the new selection. Map matching uses district/state identity.
- Sample runs write to `reports/samples`; CSV-only candidates write to `reports/candidates`. They preserve the active manifests, CSVs, database, and model. Production loading rejects sample manifests.
- Updated Python 3.13 dependencies, added NetworkX, separated optional download/tracking dependencies, repaired setup commands, and removed silent CI installation/database fallbacks. CI includes PostgreSQL migration regression checks and a locked dashboard build. Remote CI and a fresh Linux installation have not been executed locally.

## Verification

The real `python -m scripts.run_pipeline --step all --as-of 2026-10-13` command completed all six stages successfully. A final scoring run incorporated the completed-month cutoff guard.

| Check | Result |
|---|---|
| Complete pytest suite with explicit integration | **135 passed** |
| Database-independent suite | **123 passed**, 12 integration tests deselected |
| Canonical migration checks | **14 passed**, including isolated rollback tests |
| Dashboard lint / production build | Passed; existing large JavaScript bundle advisory remains |
| Python compilation / installed dependency consistency | Passed |
| Feature generation | `physical-v3-causal-monthly-90a24f1f2574` |
| Derived feature rows / districts | **200,100 / 725** |
| Observed feature values compared with raw CGWB data | **36,251 checked; zero mismatches** |
| Invalid stored feature provenance / GWL values | **Zero** |
| Latest completed batch | **725 districts**: 427 district estimates, 294 zone estimates, 4 unavailable |
| Persisted endpoint predictions in latest batch | **721** |

Live checks covered health, scores, alerts, district/history/prediction routes, canonical Mumbai Suburban, unknown IDs, unsupported horizons, historical/future cutoffs, unchanged and changed simulations, and strict JSON. Browser checks covered Home, Jaipur detail, Alerts, and Simulate. Temporarily stopping the test API produced a visible error and no fabricated counts; restarting and retrying restored the dashboard.

Details: [repair_live_verification.json](repair_live_verification.json), [backtest_results.json](backtest_results.json), and the verified model card at `models/checkpoints/aquaiq_xgb_model_card.json`. The complete pipeline log is retained at `D:\AquaIQ\fix-tools\final-pipeline.log`.

## Remaining evidence limits

The latest groundwater observation in the database is March 2023, covering only five districts that year. Many district histories end in 2021. The app therefore presents historical estimates; fresh observations are required for a current outlook.

The final held-out period has only **10 observed targets**. XGBoost RMSE is **0.619 m** and persistence RMSE is **0.0093 m** on those same targets. This tiny sample does not establish nationwide accuracy, and XGBoost does not beat persistence there. These limitations are included in the model card and district page. Candidate weights were not promoted. Zone estimates have not been independently calibrated as operational forecasts.

Monthly timestamps represent observation months. Completed-month checks prevent using unfinished monthly aggregates, but source publication/revision dates are unavailable; evaluation uses retrospective data and cannot prove publication-time availability.

## Backups and recovery evidence

Before database changes, a PostgreSQL custom dump and the original processed data/checkpoints/reports were saved under `D:\AquaIQ\fix-backups\20261012T170300Z`. The dump `aquaiq-before-fix.dump` was successfully read by `pg_restore --list`. Original source files are also preserved under `D:\AquaIQ\fix-backups\source-before-fix`, and overwritten files are retained in the timestamped backup's `applied-files-before` directory.

The running local preview uses `http://127.0.0.1:5173` with the API on `http://127.0.0.1:5000`. Startup and isolated sample commands are documented in the project README.
