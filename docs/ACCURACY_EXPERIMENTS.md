# Scientific evaluation and candidate reproduction

The [retraining report](../reports/retraining_20261027/REPORT.md), [accuracy experiment](../reports/accuracy_experiments_20261027/REPORT.md) and their locked protocols are authoritative. Experiments did not establish a sufficiently robust improvement to replace frozen production. The enriched candidate remains unpromoted; grouped horizons are a rejected replacement. Inspected historical diagnostics, coverage and software tests do not establish prospective forecasting skill or calibrated uncertainty.

Use the activated Python 3.13 project environment and the exact V3, original baseline and source assets in [release requirements](FINAL_RELEASE_REPRODUCTION.md). Generated case exports, per-fold learners and full observations remain local. Every replay needs new report/model paths; never overwrite a locked study, active pointer or published production generation. The following commands are deliberate research operations and are not application startup or cleanup steps.

## Enriched XGBoost candidate

[The retraining protocol](../reports/retraining_20261027/protocol.json) fixes the 17 ordered serving features, observed-origin/observed-target calendar joins and horizons 1-12. The model predicts depth change; inference adds the observed anchor and clips depth at zero. Weather climatology/lag fallback use origin-available prefixes. Generated/imputed labels and unresolved telemetry are excluded; pre-existing deep observations remain flagged rather than arbitrarily clipped.

Three prespecified parameter sets use two earlier chronological folds: training targets end December 2021/2022; validation origins follow the twelve-month embargo in 2023/2024 and targets end January 2024/2025. Mean fold district-macro MAE selects settings, RMSE breaks ties, and median selected best tree count is locked before the final fit through January 2025. Earlier validation alone controls early stopping. The frozen artifact used realized-weather conditional training; the candidate uses origin-available assumptions and fixes a month-boundary mismatch, so differences cannot be attributed only to added observations.

January 2026 labels are excluded from fitting/selection but were previously inspected. There are no accepted post-January-2026 observations or untouched observed-origin/future-target pairs strictly after January 2025. The final 2025 serving-origin comparison is retrospective and dependent. Promotion still requires every locked gate, including an untouched post-refit test; the absence of that test blocks promotion. Old calibration binds frozen weights and cannot be transferred to the candidate.

```powershell
python -B -m scripts.audit_retraining_data --feature-directory data/processed/enrichment/final_release_20261026_v3 --output scratch/retraining_data_NEW.json
python -u -B -m scripts.retrain_enriched_xgboost --feature-directory data/processed/enrichment/final_release_20261026_v3 --frozen-checkpoint data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json --output reports/candidates/retraining_NEW/training --checkpoint models/artifacts/enriched_retraining_NEW/checkpoint.json
python -B -m scripts.evaluate_retrained_model --features data/processed/enrichment/final_release_20261026_v3 --frozen-checkpoint data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json --candidate-checkpoint models/artifacts/enriched_retraining_NEW/checkpoint.json --output reports/candidates/retraining_NEW/diagnostic --origins 2025-01-31 2025-02-28 2025-03-31 2025-04-30 2025-05-31 2025-06-30 2025-07-31 2025-08-31 2025-09-30 2025-10-31 2025-11-30 2025-12-31
```

The trainer checks same-seed model-byte/prediction equality, saved-model reload and a frozen rollback copy; it records data/code/model/software hashes and eligibility counts. The recorded enriched model SHA-256 is `e4e57de9f681b2f2702c9b86a00be06b04147123ecea0579f6abcf3cdc586192`; active frozen SHA-256 remains `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`.

For candidate output verification, use `scripts.precompute_forecasts` with the explicit candidate checkpoint, V3 features, a new export/output path and `--dry-run`. Specify a deliberately absent `--calibration-path` so candidate ranges stay unavailable. A separately inspected persisted trial uses a fresh `--test-schema aquaiq_test_retraining_new` and `scripts.verify_nationwide_release` with identical inputs. The source registry is read for reconciliation; no public production namespace or pointer is changed. Continuing to use the frozen pointer and existing published schema is the rollback for an unpromoted experiment. A saved rollback bundle must verify against its own card/generation before loading.

## Nested accuracy development

The executed [protocol_v2.json](../reports/accuracy_experiments_20261027/protocol_v2.json) prespecified seventeen recipes, with sixteen eligible for all required folds, and two baselines. [The acceptance assessment](../reports/accuracy_experiments_20261027/acceptance_assessment.json) records failed gates. Fresh replays seal support before fitting rather than removing validation cases to rescue a recipe.

```powershell
python -u -B -m scripts.audit_accuracy_baselines --output reports/candidates/accuracy_NEW/audit
python -u -B -m scripts.run_accuracy_experiments prepare --audit reports/candidates/accuracy_NEW/audit --protocol reports/candidates/accuracy_NEW/protocol.json
python -u -B -m scripts.run_accuracy_experiments run --protocol reports/candidates/accuracy_NEW/protocol.json --output reports/candidates/accuracy_NEW/run
```

`prepare` requires a successful serving audit and seals data, source, software, candidate recipes, folds and ranking before fitting. `run` rejects changed inputs/code or an existing output directory. Per-fold models/cards/traces/predictions stay in the new local report tree; any final research learner uses a separate `models/artifacts/accuracy_experiments_*` identity. A stopped run is incomplete and must not be overwritten or represented as a completed comparison.

The primary statistic averages inner-fold district-macro MAE on the same seasonal-eligible cases for every candidate and baseline; RMSE breaks ties. Full-population macro/case MAE, RMSE, signed error and coverage remain separate. Districts with one case contribute to the macro mean but do not support local findings. Subgroup interpretation requires thirty cases across ten districts.

Outer origin years are 2020/2021, with full twelve-horizon target windows ending before 2023. Inner targets end by their outer training cutoff. Outer folds evaluate the inner-selection procedure; secondary recipe comparisons on outer labels cannot select a replacement winner. The existing frozen artifact is temporally valid only after its 2019 cutoff; the enriched artifact fit through January 2025 is contaminated on these earlier folds and cannot be selection evidence. Refitted current/production recipes supply chronological controls. Previously inspected 2023/2024 folds and January 2026 labels remain historical references.

Research loading uses `models.accuracy_challengers.load(checkpoint)`, then `model.depth(pairs)` with the seventeen ordered serving features and observed anchors. The loader verifies hashes, feature order and exact horizon coverage. Ridge transforms are train-fitted JSON; trend artifacts require explicit source history. Research checkpoints use a separate format and cannot replace the production pointer. Historical publication times and current stale-anchor behavior remain unverified by this controlled observed-origin experiment. Fresh prospective observations and all promotion gates are still necessary.

To rebuild corrected tables/figures from the retained local case exports, use `python -B -m scripts.summarize_accuracy_experiments --root reports/accuracy_experiments_20261027 --run reports/accuracy_experiments_20261027/run_v2 --protocol reports/accuracy_experiments_20261027/protocol_v2.json --analysis-version analysis_NEW`; existing output/report names are refused. Use the [root software checks](../README.md#verify) independently of any scientific reproduction.
