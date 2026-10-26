# Final release reproduction, 26 October 2026

The final isolated snapshot contains **43,384 genuine observed district-months**, including 542 January 2025 months recovered in this release. Five districts gained their first accepted local observation; 57 districts still have none. Weather definitions, existing measured means and frozen model weights remain unchanged. Coverage of all 725 project districts means all districts receive twelve point estimates; evidence tiers still distinguish local forecasts, limited-history estimates, regional references and missing-weather estimates.

## Recorded identities and evidence

| Artifact | Recorded value |
| --- | --- |
| Final candidate | `reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2` |
| Candidate manifest SHA-256 | `a6e32fab5b3b9f16aa734b53e96a28bc8cf702dd306a27fd559fb549d93f420e` |
| Final features | `data/processed/enrichment/final_release_20261026_v3` |
| Feature generation | `physical-v3-official-c9ade81d95720f91` |
| Feature CSV SHA-256 | `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042` |
| Calibration | `reports/final_release_20261026/calibration_v3.json` |
| Calibration file SHA-256 | `feff5b397b5567b73e62e48a1cb535f51e93b65ced1386cbfc72aa337e139d01` |
| Unchanged model SHA-256 | `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03` |
| Supplied-asset replay generation | `015b39d9-56c3-57eb-839c-6d62ce26de9e` |
| Replay-only PostgreSQL schema | `aquaiq_test_clean_final_20261026` |

The [source catalog](../data_sources/catalog.yaml) preserves earlier investigations and adds current resource checks, licenses, exact hashes and independent status stages. A parsed index, an empty CSV or accessible metadata is not a newly acquired numerical predictor. [Groundwater evidence](../reports/final_release_20261026/groundwater_sources.md), [weather/boundary evidence](../reports/final_release_20261026/weather_boundary_sources.json), [interval disclosure](../reports/final_release_20261026/uncertainty_report.md) and the [fixed diagnostic protocol](../reports/final_release_20261026/diagnostic_protocol.json) state their respective limits.

Two different clean-environment checks were actually executed:

- [Code-only probe](../reports/final_release_20261026/clean_environment_probe.json): independent Python 3.13.15 environment, no shared site packages, pinned dependencies and passing `pip check`. Tracked model bytes verified. Feature loading failed because ignored assets were absent. **A public code-only clone does not reproduce these forecasts.** The probe's `supplied_asset_replay=not_yet_attempted` describes that earlier step.
- [Later supplied-asset replay](../reports/final_release_20261026/clean_supplied_asset_replay.json): all six comparisons passed: feature generation, feature CSV, calibration values, forecast generation ID, 725 districts and 8,700 horizons. All 36 state/UT outputs were available, with district tiers A=551, B=116, C=57, D=1. The test supplied ignored baseline assets, cached official source files and local database configuration. Public source tables and the working service were unchanged. It copied 206 public source files into the separate checkout; its public source-patch hash is recorded. It did not independently reacquire the original baseline.

## Prerequisites and ignored assets

Run from the repository root. Use Python 3.13, the pinned `requirements.txt`, Node 22.12+ and `npm ci --prefix dashboard`. In a new workspace, create the ordinary command environment before the individual-step examples below:

```powershell
py -3.13 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip check
npm.cmd ci --prefix dashboard
```

The replay's PostgreSQL connection comes from a local `.env` prepared from `.env.example`; credential values and hashes are not evidence artifacts. Use a local/test database account allowed to create an `aquaiq_test_*` schema. No hosted deployment is part of this procedure.

Restore matching files at their recorded repository-relative paths before a full replay:

| Baseline input | Required SHA-256 |
| --- | --- |
| `data/raw/india_districts.geojson` | `e724c14bc5ee68bcdd6cee8c89222b80cb61e180e55c1dab3d067f09b3b9dc8f` |
| `data/processed/features_matrix.csv` | `3958737b033a16e722f633a15ad77d80bc5b2a8fb3bea888697f0410362c24ae` |
| `data/processed/feature_manifest.json` | `afc96a9e13655ffa2ccb2bf18a027b9bb1ed34c21260b901301cef6fd35c8b91` |
| `data/raw/cgwb_combined.csv` for rebuilding the original manual candidate | `8d26aad32c4c11a909a27d2d5bc9f624b2225b7338f0f3eaa66acba62db071c7` |

The full source chain also requires:

- `data/raw/official_enrichment/nwdp_20261026/`, including the original manual acquisition manifest and its exact CSV bytes;
- original audited parent `reports/candidates/groundwater_updates/enrichment_20261026/nwdp_manual_v1/`;
- previous snapshot `data/processed/enrichment/nwdp_manual_20261026_v1/` and `reports/data_enrichment/final_evaluation/calibration.json` for the calibration compatibility proof;
- reused PDF `data/raw/updates/20261015/cgwb/January_WL_1994-2025.pdf` and verified extraction `reports/candidates/station_history_20261015/january_2025_verified/`;
- final portable v2 candidate and the matching final V3 snapshot listed above.

Their manifests bind raw files, accepted/rejected rows, monthly aggregates, crosswalk and fixed boundary hashes. The PDF hash is `6ebb9cbf401c3fb7aca65c31b421ccf586c6fadbce5abb4d2a222e538b0534cd`. Its source/extraction/parent paths in v2 are repository-relative; v1 is preserved. Exact source bytes and prior generated assets require separate restoration. A current official catalog is not an exact download recipe for the old combined baseline. Updated metadata or source revisions require a new candidate identity and validation.

CGWB material is attributed under its [copyright policy](https://cgwb.gov.in/en/copyright-policy), without an asserted separate open-data grant. NWDP supplies `Other (Open)` without a specific grant URL. SoI metadata says copyright and references the 2021 Geospatial Guidelines; no raw or derived polygons are redistributed. Review source-specific terms before acquiring or sharing raw material.

## Execute the independent supplied-asset replay

The following commands use a **new** scratch checkout, environment and report. Run the code-only probe before the replay copies baseline assets or `.env` into that checkout. The local clone starts at the current committed revision; the replay script additionally copies the current public runtime source files and records their aggregate hash, matching the executed pre-commit source-patch procedure.

```powershell
git clone --local --no-hardlinks . scratch/final_release_replay/checkout
py -3.13 -m venv scratch/final_release_replay/environment
$replayPython = Join-Path (Get-Location) 'scratch/final_release_replay/environment/Scripts/python.exe'
& $replayPython -m pip install -r requirements.txt
& $replayPython -m pip check

& $replayPython -B -m scripts.clean_release_probe --checkout scratch/final_release_replay/checkout --python $replayPython --output scratch/final_release_replay/code_only_probe.json

& $replayPython -B -m scripts.reproduce_final_release --checkout scratch/final_release_replay/checkout --python $replayPython --candidates reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2 --expected-features data/processed/enrichment/final_release_20261026_v3 --calibration reports/final_release_20261026/calibration_v3.json --schema aquaiq_test_clean_final_replay_20261026 --output scratch/final_release_replay/supplied_asset_replay.json
```

The wrapper verifies cached acquisition bytes, builds a new isolated feature snapshot, proves calibration-prefix equality, initializes only the explicit private schema, computes forecasts and compares all six expected identities/coverage values. Its child interpreter runs with `-I` in the independent environment. It deliberately supplies baseline data and local connection configuration; neither source credentials nor ignored observation rows enter the report. Outputs, source revisions and code changes that alter identity must be investigated rather than overwritten to force a match. For another run, choose new scratch paths, report and schema names.

## Individual offline build and diagnostic commands

These alternatives expose the main steps. All outputs below are new ignored paths. Keep the recorded v2 manifest and V3 snapshot immutable.

```powershell
# Existing cache is checksum-verified; without that cache this is an explicit network acquisition.
.\venv\Scripts\python.exe -B -m data_ingestion.nwdp_manual --acquire data/raw/official_enrichment/nwdp_20261026

# Re-audit local PDF/manual/telemetry evidence into a separate aggregate report.
.\venv\Scripts\python.exe -B -m data_ingestion.groundwater_release --review-output scratch/groundwater_release_replay.json

# Rebuild from the frozen final candidate, preserving baseline measured means and weather.
.\venv\Scripts\python.exe -B -m preprocessing.official_enrichment --candidates reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2 --output data/processed/enrichment/final_release_20261026_replay --as-of 2026-10-26

# Rebind unchanged calibration only after exact pre-origin input/label equality.
.\venv\Scripts\python.exe -B -m scripts.prepare_final_calibration --parent-directory data/processed/enrichment/nwdp_manual_20261026_v1 --candidate-directory data/processed/enrichment/final_release_20261026_replay --calibration reports/data_enrichment/final_evaluation/calibration.json --output scratch/final_release_calibration_replay.json

# No database persistence in this forecast/export check.
.\venv\Scripts\python.exe -B -m scripts.precompute_forecasts --as-of 2026-10-26 --feature-directory data/processed/enrichment/final_release_20261026_replay --checkpoint data/processed/enrichment/final_release_20261026_replay/frozen_bundle/checkpoint.json --calibration-path scratch/final_release_calibration_replay.json --dry-run --export-dir scratch/final_release_forecasts_replay --output scratch/final_release_forecast_check.json

# Expanded retrospective paired comparison; no fitting or model/radius selection.
.\venv\Scripts\python.exe -B -m scripts.evaluate_final_release --parent-directory data/processed/enrichment/nwdp_manual_20261026_v1 --candidate-directory data/processed/enrichment/final_release_20261026_v3 --output scratch/final_release_diagnostic_replay
```

The final calibration proof compares 179,075 rows through 1 July 2022, retaining all original radii and model weights. The diagnostic has 1,278 dependent cases across 639 districts, two origins and only the January 2026 target date. Those targets were previously inspected. Its lower error against the parent does not establish a new blind gain, accuracy in unmonitored districts or superiority to persistence/seasonal baselines.

For a persisted local candidate, replace `--dry-run` with a fresh `--test-schema aquaiq_test_final_release_replay_20261026`. This writes only candidate forecast relations in that explicit namespace. The [nationwide verifier](../scripts/verify_nationwide_release.py) also requires existing canonical source-registry tables in the configured database; a blank database with only forecast relations cannot pass that extra source reconciliation:

```powershell
.\venv\Scripts\python.exe -B -m scripts.verify_nationwide_release --schema aquaiq_test_final_release_replay_20261026 --as-of 2026-10-26 --feature-directory data/processed/enrichment/final_release_20261026_replay --checkpoint data/processed/enrichment/final_release_20261026_replay/frozen_bundle/checkpoint.json --calibration-path scratch/final_release_calibration_replay.json --output scratch/final_release_api_verification.json
```

## Remaining source and reliability limits

Manual/PDF targets use actual source dates, verified `m_bgl` units and conservative coordinate/identity checks. There is no station snapping, invented local history or replacement of groundwater labels with rainfall, resource categories or modeled soil/storage data. The January dataset title does not certify per-well aquifer construction. A newly inspected Sikkim yearbook describes confined piezometers and has inconsistent publication/running-header years; no numerical labels were created from its narrative or graphs.

All 31 refreshed 2026–2030 manual CSV bodies were acquired and checked: each is the same 243-byte header, with zero observations. Telemetry remains quarantined: 274,930 rows, 91 station fingerprints, 41 fingerprints with both signs, 16 accepted manual same-day pairs and zero exact timestamp pairs. `RL_MSL` does not establish sensor datum. The new 2026 CGWB high-frequency guidance requires reference/installation information and manual dip validation; it does not authorize a universal sign flip. Provider-specific metadata and independent overlap remain necessary.

The authorized ERA5 request returned HTTP 403 with a manual dataset-terms gate. No new weather arrays were obtained, so comparison against newly acquired values was impossible. The account owner must review and manually accept the terms before a separately authorized retry; credentials and terms acceptance were not fabricated. The SoI edition-2025 archive and metadata ZIP were downloaded and hashed. Two actual Mumbai district geometries were selected for diagnostics without changing coordinates or production geography. Both polygons lack interior usable ERA5 centers and select the same external coarse cell. Alternative footprint weighting changes 216 historical Mumbai Suburban feature rows and fails frozen-model compatibility. It was not promoted or scored as an improved trained model.

Prior GWRA, aquifer, SoilGrids, WorldCover, SRTM and GRACE investigations remain in the catalog. Resource-assessment categories are context; a VRT/tile index is not downloaded raster data; one soil pixel is not a district predictor; coarse total-water storage is not measured groundwater depth. No auxiliary candidate was promoted by this release.

Numerical error bands require at least ten distinct calibration districts per tier/horizon. Unsupported bands are unavailable; C and D have none. Supported bands retain their original radii. Historical undercoverage and generation mismatch are disclosed, and older pooled coverage is not assigned to V3. Point estimates remain available for all twelve horizons. No radii were widened or tuned on inspected final labels.

## Verification commands

```powershell
.\venv\Scripts\python.exe -B -m pytest tests/test_groundwater_release.py tests/test_release_weather.py tests/test_release_boundaries.py tests/test_interval_evidence.py tests/test_tiered_forecast.py -p no:cacheprovider -q --disable-warnings --basetemp=scratch/pytest-final-release-replay
node --test dashboard/tests/intervalDisclosure.test.js dashboard/tests/tieredForecast.test.js
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build
```

The source-focused results recorded for this release are 24 groundwater tests, 25 weather/boundary tests, 35 interval/forecast Python tests and nine focused frontend tests. Broader release checks are recorded separately by the release coordinator; the counts above must not be summed as a complete distinct-suite total. Source audits and isolated replay do not replace service/API verification or establish future scientific accuracy.
