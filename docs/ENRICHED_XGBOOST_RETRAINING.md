# Enriched XGBoost retraining

This workflow fits a separate candidate for AquaIQ's existing twelve-month climate product. It does not train the legacy six-month absolute-depth model, change the canonical district registry, or replace the deployed model pointer. The model has 17 ordered features and predicts groundwater-depth change from an observed origin at horizons 1–12. Serving adds that change to the current-depth anchor and clips predicted depth at zero.

The experiment is defined by [the locked protocol](../reports/retraining_20261027/protocol.json). The [data audit](../reports/retraining_20261027/data_audit.md) verifies 215,325 feature rows, 43,384 measured district-months, the accepted source chain and unchanged existing measurements. Telemetry with unresolved datum/sign conventions, generated forecasts and imputed values cannot become targets. Two pre-existing depths above 100 m are flagged and retained without arbitrary clipping. The local snapshot and raw inputs remain excluded from Git.

## Training and evaluation policy

`models/enriched_training_data.py` joins observed origins to observed targets at exact calendar offsets. Weather climatology and lag fallback use only the origin-available prefix. Its NumPy encoder is tested against production feature functions, including the M+12 origin-month boundary and missing-lag projection. Training anchors are observed; current-depth estimates across later observation gaps remain a separate serving limitation.

The frozen artifact's card records realized-weather conditional training. The new candidate uses origin-available weather assumptions and fixes the current trainer's month-start/month-end mismatch. A difference in results therefore cannot be attributed exclusively to the additional observations.

Three prespecified parameter sets are compared on two earlier chronological folds. Training targets end December 2021/2022; validation origins follow the existing twelve-month embargo in 2023/2024, with validation targets ending January 2024/2025. Early stopping occurs on these validation periods only. Mean fold district-macro MAE selects settings; mean fold RMSE breaks ties. The median selected best tree count is locked before the final fit through January 2025. Fold case exports and checksums preserve all subgroup comparisons.

January 2026 labels do not enter fitting, early stopping or selection. They have already been inspected in earlier work. There are no accepted observations after January 2026 and no observed-origin/future-target pair strictly after January 2025. Consequently, the final comparison uses the actual tiered serving path at twelve month-end origins in 2025 and is explicitly retrospective. Its repeated district/target cases do not establish independent twelve-month trajectories or prospective accuracy. Historical source-publication availability is also unverified.

Promotion requires all checks in the protocol, including an untouched post-refit test. Without one, the candidate remains experimental even if retrospective errors improve. The old calibration binds the frozen weights and cannot be transferred to the new model. Candidate intervals remain unavailable.

## Commands

Use the existing Python 3.13 environment and the verified final V3 assets documented in [the release reproduction guide](FINAL_RELEASE_REPRODUCTION.md). No acquisition, preprocessing refresh, public migration or production scoring is needed. Each output/model directory must be new; report and model directories cannot overlap. Preserve the recorded run and choose versioned paths for another experiment.

```powershell
.\venv\Scripts\python.exe -B -m scripts.audit_retraining_data --feature-directory data/processed/enrichment/final_release_20261026_v3 --output scratch/retraining_data_audit_replay.json

.\venv\Scripts\python.exe -u -B -m scripts.retrain_enriched_xgboost --feature-directory data/processed/enrichment/final_release_20261026_v3 --frozen-checkpoint data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json --output reports/retraining_20261027/replay_training --checkpoint models/artifacts/enriched_retraining_20261027_replay/checkpoint.json

.\venv\Scripts\python.exe -B -m scripts.evaluate_retrained_model --features data/processed/enrichment/final_release_20261026_v3 --frozen-checkpoint data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json --candidate-checkpoint models/artifacts/enriched_retraining_20261027_replay/checkpoint.json --output reports/retraining_20261027/replay_diagnostic --origins 2025-01-31 2025-02-28 2025-03-31 2025-04-30 2025-05-31 2025-06-30 2025-07-31 2025-08-31 2025-09-30 2025-10-31 2025-11-30 2025-12-31
```

The trainer fits the final model twice with the same seed and checks exact model bytes/predictions, then validates saved-model reload and the rollback bundle. It records source/code/data/model hashes, selected settings, counts of new target/origin pairs, dependency versions and dates. Full target/case CSVs remain ignored; compact aggregate reports and the separate experimental model can be retained.

To test complete output coverage without publishing or reusing old calibration:

```powershell
.\venv\Scripts\python.exe -B -m scripts.precompute_forecasts --as-of 2026-10-27 --feature-directory data/processed/enrichment/final_release_20261026_v3 --checkpoint models/artifacts/enriched_retraining_20261027_replay/checkpoint.json --calibration-path scratch/retraining_no_matching_calibration.json --dry-run --export-dir scratch/retraining_candidate_forecasts --output scratch/retraining_candidate_generation.json
```

The calibration path above must remain absent. For a separate local API check, replace `--dry-run` with a fresh `--test-schema aquaiq_test_retraining_replay_20261027`, then use `scripts.verify_nationwide_release` with the same explicit inputs. All publication writes stay in that test namespace. The configured public source-registry tables are read only for reconciliation.

## Rollback and production safety

The active pointer `models/artifacts/aquaiq_climate_12m.json` is not modified. The frozen model SHA is `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`. The trainer also saves a verified local rollback copy under `scratch/retraining_20261027/rollback/`. Candidate generation uses an explicit checkpoint and private schema, leaving current API namespaces intact.

Since this experiment does not promote a model, rollback means continuing to use the original pointer and existing published forecast schema. To check the saved rollback explicitly, load `scratch/retraining_20261027/rollback/checkpoint.json` with `climate_forecast_12m.load_bundle(..., expected_generation='physical-v3-official-c9ade81d95720f91')`. Do not copy an experimental pointer over the deployed one or attach old uncertainty bands to its new weights.

The executed metrics, artifact identity, checks and promotion decision are recorded in the [retraining report](../reports/retraining_20261027/REPORT.md).
