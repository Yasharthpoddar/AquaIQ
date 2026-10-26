# Official-data enrichment: isolated reproduction

The 26 October 2026 candidate adds audited CGWB/NWIC manual measurements to missing district months. It preserves the original feature export, public database, model weights, weather definitions, risk index and previous publication. See the [executed report](../reports/data_enrichment/REPORT.md), [source inventory](../reports/data_enrichment/source_inventory.md), [catalog](../data_sources/catalog.yaml) and [district coverage](../reports/data_enrichment/source_coverage.csv).

## Prerequisites and licensing

Use the existing Python 3.13 environment or install `requirements.txt`; use Node 22.12+ with `npm ci --prefix dashboard`. Configure a **local/test** PostgreSQL database using `.env.example`. Credentials remain local. The publication command applies migration 004 only in the explicit candidate namespace. The separate risk demonstration continues to use `aquaiq_test_nationwide_20261025`.

A clean clone contains code, catalogs, compact reports and the frozen XGBoost artifact. It does **not** contain the legacy source observations, district boundary, verified baseline features, newly downloaded files, candidate features, populated database or local forecasts. Restore the matching assets before replay; source acquisition alone cannot reconstruct the earlier baseline:

| Input | SHA-256 |
|---|---|
| `data/raw/cgwb_combined.csv` | `8d26aad32c4c11a909a27d2d5bc9f624b2225b7338f0f3eaa66acba62db071c7` |
| `data/raw/india_districts.geojson` | `e724c14bc5ee68bcdd6cee8c89222b80cb61e180e55c1dab3d067f09b3b9dc8f` |
| `data/processed/features_matrix.csv` and matching `feature_manifest.json` | `3958737b033a16e722f633a15ad77d80bc5b2a8fb3bea888697f0410362c24ae` |
| Model bytes resolved by `models/artifacts/aquaiq_climate_12m.json` | `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03` |

The fixed boundary has mixed administrative vintages. The 725 districts are a project inventory, not a verified current national registry. Do not rebind the frozen bundle to a different baseline without proving identical training inputs and feature definitions.

NWDP declares **Other (Open)** without a specific license URL: attribute CGWB/NWIC and retain raw files locally. IMD requests product citations without an inspected open redistribution grant. CGWB assessment reproduction requires attribution and excludes third-party material. The ERA5 catalogue reports CC-BY-4.0; authenticated retrieval and accepted account terms were not verified. SoilGrids, WorldCover and GRACE terms/access distinctions are recorded per source. No raw datasets are committed.

## Acquisition and feature generation

```powershell
# Explicit network acquisition; cached files are hash-checked, not overwritten.
.\venv\Scripts\python.exe -B -m data_ingestion.nwdp_manual --acquire data/raw/official_enrichment/nwdp_20261026

# Offline audit and overlay. Choose new directories for a repeated build.
.\venv\Scripts\python.exe -B -m data_ingestion.nwdp_manual --acquisition-manifest data/raw/official_enrichment/nwdp_20261026/manual_acquisition.json --output-dir reports/candidates/groundwater_updates/enrichment_20261026/nwdp_manual_v1 --as-of 2026-10-26
.\venv\Scripts\python.exe -B -m preprocessing.official_enrichment --candidates reports/candidates/groundwater_updates/enrichment_20261026/nwdp_manual_v1 --output data/processed/enrichment/nwdp_manual_20261026_v1 --as-of 2026-10-26
```

The exact acquisition metadata, source hashes, accepted/rejected station rows, station-month means and monthly aggregates remain linked through the manifest. The parser requires inspected columns, units and actual timestamps. Station names are not certified well IDs. Ambiguous colocated labels, conflicts, invalid values, named springs and depths requiring review are quarantined. Coordinates must identify exactly one district, agree with source state and exceed a 0.001-degree boundary margin. No snapping, fuzzy merging or telemetry sign reversal is used.

Unique timestamps form station-month means, then districts weight stations equally. Existing genuine district-month values take precedence, with overlap differences retained locally. The overlay recomputes groundwater carry-forward and calendar lags using the existing physical-v3 rules. Observed, imputed and missing values remain distinct. It compares all training-period feature values exactly and preserves all environmental values. The candidate bundle copies identical model bytes and records the parent card, generation and compatibility proof; incompatibility fails before output creation. Default loading still uses the original baseline. Explicit snapshots cannot fall back to database features.

The recorded snapshot is `physical-v3-official-a891508e320439f9`, with CSV SHA-256 `e83990a7fc66e58bd74829f5523dd021dd9cff87894271a99c6202d2a1872115`. Generation identity includes exact source/manifests/code bytes; another source revision or checkout representation may create a different identity and requires its own matching card/evaluation. The evaluation code seal normalizes only Git LF/CRLF representation, retaining every other source-text change.

Manual file acquisition dates are 26 October 2026 IST; their reconstructed manifest timestamps record cache verification rather than a certified initial download instant. Telemetry retains exact download timestamps. Weather/auxiliary commands and licensing details are in the [weather report](../reports/data_enrichment/weather_sources.md), [groundwater inventory](../reports/data_enrichment/groundwater_inventory.md) and [auxiliary report](../reports/data_enrichment/auxiliary_sources.md). Ordinary API requests never acquire sources or retrain models.

## Evaluation and publication

The [fixed protocol](../reports/data_enrichment/evaluation_protocol.json) defines calibration, development and final origins, identical target joins and development-MAE selection. The seal binds protocol, feature CSVs, model bytes, both cards and predictive/evaluation code. Final evaluation rejects changed inputs. Calibration precedes evaluation origins; unsupported tier/horizon ranges remain unavailable. No final-period labels tune or select the candidate. Publication-time snapshots and stable well panels remain unavailable, so this is retrospective conditional-on-observation-date evaluation.

```powershell
.\venv\Scripts\python.exe -B -m scripts.evaluate_official_enrichment --candidate-directory data/processed/enrichment/nwdp_manual_20261026_v1 --output reports/data_enrichment/final_evaluation --phase development
.\venv\Scripts\python.exe -B -m scripts.evaluate_official_enrichment --candidate-directory data/processed/enrichment/nwdp_manual_20261026_v1 --output reports/data_enrichment/final_evaluation --phase final

# Inspect evaluation and test results before publishing the candidate locally.
.\venv\Scripts\python.exe -B -m scripts.precompute_forecasts --as-of 2026-10-26 --feature-directory data/processed/enrichment/nwdp_manual_20261026_v1 --checkpoint data/processed/enrichment/nwdp_manual_20261026_v1/frozen_bundle/checkpoint.json --calibration-path reports/data_enrichment/final_evaluation/calibration.json --test-schema aquaiq_test_enrichment_20261026 --export-dir reports/data_enrichment/outputs/verified --output reports/data_enrichment/generation.json
.\venv\Scripts\python.exe -B -m scripts.verify_nationwide_release --schema aquaiq_test_enrichment_20261026 --as-of 2026-10-26 --feature-directory data/processed/enrichment/nwdp_manual_20261026_v1 --checkpoint data/processed/enrichment/nwdp_manual_20261026_v1/frozen_bundle/checkpoint.json --calibration-path reports/data_enrichment/final_evaluation/calibration.json --output reports/data_enrichment/release_verification.json
```

Explicit candidate publication requires all paths and a test connection. The guard verifies all six output relations are ordinary private tables and removes public/temp fallback. Complete horizons, state means and provenance pass validation before an atomic publication. Failed computation/export/transaction preserves earlier generations. `--dry-run` skips database writes. A missing explicit calibration file means unavailable ranges, not borrowed mismatched bands.

To inspect the candidate, set `AQUAIQ_FORECAST_SCHEMA=aquaiq_test_enrichment_20261026`, `AQUAIQ_SCORING_SCHEMA=aquaiq_test_nationwide_20261025`, `AQUAIQ_ENABLE_SYNC_FORECAST_FALLBACK=false`, `FLASK_HOST=127.0.0.1`, `FLASK_PORT=5000` and `FLASK_DEBUG=false`, then run `python -B -m api.app`. In a separate terminal run `npm.cmd --prefix dashboard run dev -- --host 127.0.0.1 --port 5173 --strictPort`.

Twelve-month endpoints read the enriched persisted snapshot. Source/history endpoints, six-month products and risk scores retain the protected original inputs. Their evidence and dates differ; the risk index remains uncalibrated. Public-table fingerprints verify isolation. No hosted deployment or fresh-machine database restoration is claimed.
