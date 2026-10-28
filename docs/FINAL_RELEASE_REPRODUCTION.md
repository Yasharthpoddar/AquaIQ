# Data, models and release reproduction

A code-only clone is not a populated forecasting service. Match the source commit, configuration, source observations, feature generation, model cards/checkpoints, calibration and PostgreSQL publications before running AquaIQ. The [final release](../reports/final_release_20261026/REPORT.md) is an isolated supplied-asset result, not proof that all historical inputs can be downloaded afresh. The canonical registry has 725 project districts; it is not a verified current national administrative inventory.

## Environment and required assets

Use Python 3.13 with [requirements.txt](../requirements.txt), Node 22.12+ with `npm ci --prefix dashboard`, and a local/test PostgreSQL database. Prepare private `.env` values from [.env.example](../.env.example). A replay role must be allowed to create a new `aquaiq_test_*` namespace; the serving role should be read-only. Setup initializes schema and must target the intended database.

```powershell
py -3.13 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip check
npm.cmd ci --prefix dashboard
.\venv\Scripts\Activate.ps1
```

On Linux/macOS, activate with `source venv/bin/activate`. Unqualified `python` commands below use that matching environment.

Restore these exact baseline assets at repository-relative paths; source acquisition alone does not reconstruct the old combined baseline:

| Input | SHA-256 |
| --- | --- |
| `data/raw/india_districts.geojson` | `e724c14bc5ee68bcdd6cee8c89222b80cb61e180e55c1dab3d067f09b3b9dc8f` |
| `data/raw/cgwb_combined.csv` | `8d26aad32c4c11a909a27d2d5bc9f624b2225b7338f0f3eaa66acba62db071c7` |
| `data/processed/features_matrix.csv` | `3958737b033a16e722f633a15ad77d80bc5b2a8fb3bea888697f0410362c24ae` |
| `data/processed/feature_manifest.json` | `afc96a9e13655ffa2ccb2bf18a027b9bb1ed34c21260b901301cef6fd35c8b91` |
| Model resolved by `models/artifacts/aquaiq_climate_12m.json` | `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03` |

Legacy six-month/monthly checkpoints and matching cards under `models/checkpoints/`, raw/source archives, the populated database and local feature exports are external prerequisites. Restore them together from the matching release backup; do not substitute a different generation. File-only historical research additionally needs `research/twelve_month_app.json` and its manifest-bound snapshots under `reports/candidates/twelve_month_horizon_finalization_20261020/artifact/`. The scenario API uses the separately pinned `research/experimental_scenario_sources.json` contract.

The V3 enriched snapshot is `data/processed/enrichment/final_release_20261026_v3`, generation `physical-v3-official-c9ade81d95720f91`, CSV SHA-256 `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042`. It contains 43,384 source-marked observed district-months; previous measured means, weather definitions and frozen model weights remain unchanged. Its frozen bundle is `frozen_bundle/checkpoint.json`. Calibration is `reports/final_release_20261026/calibration_v3.json`, SHA-256 `feff5b397b5567b73e62e48a1cb535f51e93b65ced1386cbfc72aa337e139d01`.

A complete V3 source replay also requires the original `data/raw/official_enrichment/nwdp_20261026/` acquisition manifest and exact CSVs; manual parent candidate `reports/candidates/groundwater_updates/enrichment_20261026/nwdp_manual_v1/`; parent snapshot `data/processed/enrichment/nwdp_manual_20261026_v1/`; parent calibration `reports/data_enrichment/final_evaluation/calibration.json`; PDF `data/raw/updates/20261015/cgwb/January_WL_1994-2025.pdf` (SHA-256 `6ebb9cbf401c3fb7aca65c31b421ccf586c6fadbce5abb4d2a222e538b0534cd`); verified extraction `reports/candidates/station_history_20261015/january_2025_verified/`; and final candidate `reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2/` (manifest SHA-256 `a6e32fab5b3b9f16aa734b53e96a28bc8cf702dd306a27fd559fb549d93f420e`). These local generated inputs and raw observations require separate restoration where excluded from Git. Manifest-relative paths and hashes bind the chain; a newer source revision needs a new identity and evaluation.

## Acquisition and measurement policy

The [source catalogue](../data_sources/catalog.yaml) records access stages, attribution, licenses and rejected sources. CGWB's copyright policy requires attribution and does not imply a separate open-data grant; NWDP declares `Other (Open)` without a specific grant URL; IMD citations do not establish redistribution permission. ERA5 retrieval requires authentication and account-owner acceptance of dataset terms. SoI metadata is copyrighted and refers to the 2021 Geospatial Guidelines; no SoI raw/derived polygons are redistributed here. Check the terms for every exact source before sharing raw material.

```powershell
# Explicit acquisition; an existing cache is verified rather than overwritten.
python -B -m data_ingestion.nwdp_manual --acquire data/raw/official_enrichment/nwdp_20261026
# Initial manual overlay only: use new paths when replaying an existing result.
python -B -m data_ingestion.nwdp_manual --acquisition-manifest data/raw/official_enrichment/nwdp_20261026/manual_acquisition.json --output-dir reports/candidates/groundwater_updates/NEW_MANUAL --as-of 2026-10-26
python -B -m preprocessing.official_enrichment --candidates reports/candidates/groundwater_updates/NEW_MANUAL --output data/processed/enrichment/NEW_MANUAL --as-of 2026-10-26
```

The parser requires inspected columns, units and actual timestamps. Station names alone are not stable well IDs. Ambiguous labels, conflicts, invalid values, named springs and review-required depths are quarantined; coordinates must identify one district, agree with source state and exceed the boundary margin. No snapping, fuzzy merging or telemetry sign reversal is permitted. Unique readings form station-month means, then equal-station district means. Existing measured district-months take precedence. Observed, imputed and missing rows stay distinct. The overlay proves training-period feature equality and preserves environmental values before copying unchanged frozen model bytes into a generation-bound bundle; explicit snapshots cannot fall back to database features.

Empty refreshed manual CSVs are not new observations. Telemetry remains quarantined because datum/sign and comparable-time overlap are unresolved. A district polygon with no interior usable ERA5 center cannot establish independent local weather; nearest-cell/footprint alternatives changed frozen training inputs and were not promoted. Resource categories, modeled storage, a raster index or a single pixel cannot become measured groundwater-depth targets. Source publication/receipt times, per-well datum and continuity remain limitations even when month dates are known.

## Rebuild and validate a supplied snapshot

Use new directories and schema names. These commands preserve the recorded candidate and public tables; they do not authorize acquisition, production publication or model replacement:

```powershell
python -B -m data_ingestion.groundwater_release --review-output scratch/groundwater_release_NEW.json
python -B -m preprocessing.official_enrichment --candidates reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2 --output data/processed/enrichment/final_release_NEW --as-of 2026-10-26
python -B -m scripts.prepare_final_calibration --parent-directory data/processed/enrichment/nwdp_manual_20261026_v1 --candidate-directory data/processed/enrichment/final_release_NEW --calibration reports/data_enrichment/final_evaluation/calibration.json --output scratch/final_calibration_NEW.json
python -B -m scripts.precompute_forecasts --as-of 2026-10-26 --feature-directory data/processed/enrichment/final_release_NEW --checkpoint data/processed/enrichment/final_release_NEW/frozen_bundle/checkpoint.json --calibration-path scratch/final_calibration_NEW.json --dry-run --export-dir scratch/final_forecasts_NEW --output scratch/final_generation_NEW.json
python -B -m scripts.evaluate_final_release --parent-directory data/processed/enrichment/nwdp_manual_20261026_v1 --candidate-directory data/processed/enrichment/final_release_20261026_v3 --output scratch/final_diagnostic_NEW
```

Calibration reuse requires exact pre-origin inputs/labels and unchanged weights; unsupported tier/horizon bands are unavailable. No ranges are widened or tuned on inspected final labels. The expanded diagnostic reuses dependent January 2026 cases; it is neither an untouched test nor proof of superiority to persistence/seasonal baselines. [Scientific workflows](ACCURACY_EXPERIMENTS.md) describe candidate evaluation separately. `scripts.evaluate_official_enrichment --candidate-directory ... --output reports/candidates/NEW_EVALUATION --phase development` followed by `--phase final` uses one sealed calibration/development/final protocol; changed sources or code are rejected, not silently rebound.

To publish an inspected local candidate, replace `--dry-run` with a fresh `--test-schema aquaiq_test_final_new`. The namespace must contain ordinary private output tables; computation/validation/export/transaction failure preserves prior generations. A missing explicit calibration file produces unavailable ranges. `scripts.verify_nationwide_release` must receive the same schema, date, features, checkpoint and calibration; it also needs existing canonical source-registry tables in the configured database. [Serving operations](NATIONWIDE_FORECASTS.md) explain environment selection; risk outputs and original source/history endpoints are separate from the candidate twelve-month publication.

## Independent supplied-asset environment

A code-only probe previously verified the independent interpreter/dependencies and tracked model bytes but could not load absent ignored data. A later supplied-asset replay verified feature/calibration/generation identities, complete district/state coverage and exact forecast-object equality apart from computation timestamps. It reused supplied baseline assets and a local database; it did not independently reacquire the old baseline or verify remote deployment.

```powershell
git clone --local --no-hardlinks . scratch/final_release_NEW/checkout
py -3.13 -m venv scratch/final_release_NEW/environment
$replayPython = Join-Path (Get-Location) 'scratch/final_release_NEW/environment/Scripts/python.exe'
& $replayPython -m pip install -r requirements.txt
& $replayPython -m pip check
& $replayPython -B -m scripts.clean_release_probe --checkout scratch/final_release_NEW/checkout --python $replayPython --output scratch/final_release_NEW/code_probe.json
& $replayPython -B -m scripts.reproduce_final_release --checkout scratch/final_release_NEW/checkout --python $replayPython --candidates reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2 --expected-features data/processed/enrichment/final_release_20261026_v3 --calibration reports/final_release_20261026/calibration_v3.json --schema aquaiq_test_clean_final_new --output scratch/final_release_NEW/replay.json
```

The wrapper requires its separate checkout under `scratch/`, copies current public runtime source and records hashes, supplies the matching ignored assets/private connection configuration, runs a child interpreter with `-I`, initializes only the explicit test schema and compares expected identities. Choose new paths on every replay. Investigate a changed identity rather than overwrite evidence. With two completed export directories, `scripts.compare_release_replay --expected <directory> --replay <directory> --output scratch/NEW_COMPARISON.json` compares complete forecast objects.

Use the [root test commands](../README.md#verify) for software checks. No current-period accuracy, calibrated probability or production readiness follows from successful replay, coverage or tests. Matching data/model/database backups remain necessary for rollback; an experimental checkpoint must never replace the active pointer during cleanup or reproduction.
