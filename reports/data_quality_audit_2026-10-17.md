# AquaIQ data quality audit — 2026-10-17

All measurements are from local files and an explicitly read-only database transaction. Original datasets were preserved. Scratch fixtures and isolated replay artifacts are inventoried separately.

Canonical crosswalk: **725 districts**, **1291 legacy mappings**. GeoJSON: **760 polygons/features**, **758 distinct state/name pairs**. These are repository boundary identities; the audit does not assert coverage of every current Indian administrative district.

| CSV | Rows | Canonical districts | Dates | Duplicate rows | Invalid dates |
|---|---:|---:|---|---:|---:|
| data/processed/district_rainfall_gwl_correlation.csv | 519 | — (not a mapped district series) | —–— | 0 | 0 |
| data/processed/era5_district_monthly.csv | 199,824 | 724 | 2002-01-01–2024-12-01 | 0 | 0 |
| data/processed/features_matrix.csv | 215,325 | 725 | 2002-01-01–2026-09-01 | 0 | 0 |
| data/processed/imd_climatological_normal.csv | 8,688 | 724 | —–— | 0 | 0 |
| data/processed/imd_rainfall_district_monthly.csv | 295,392 | 724 | 1992-01-01–2025-12-01 | 0 | 0 |
| data/processed/preprocessed_wide.csv | 215,325 | 725 | 2002-01-01–2026-09-01 | 0 | 0 |
| data/processed/ttest_results.csv | 1 | — (not a mapped district series) | —–— | 0 | 0 |
| data/processed/weather_corrections/ERA5_a93d7d938ec9.csv | 0 | 0 | —–— | 0 | 0 |
| data/processed/weather_corrections/IMD_0bc3ec52da36.csv | 0 | 0 | —–— | 0 | 0 |
| data/processed/weather_corrections/IMD_bef3627e2c61.csv | 0 | 0 | —–— | 0 | 0 |
| data/raw/cgwb-changes-in-depth-to-water-level.csv | 550,850 | 490 | 2013-01-01–2023-03-31 | 0 | 0 |
| data/raw/cgwb_combined.csv | 1,514,984 | 559 | 1996-05-01–2023-03-31 | 0 | 0 |
| data/raw/updates/20261013/gwl_manual_quarterly_cgwb_gj_2021_2025.csv | 6,704 | 24 | 2021-05-30–2023-10-01 | 0 | 0 |
| data/raw/updates/20261013/gwl_manual_quarterly_cgwb_gj_2026_2030.csv | 0 | 0 | —–— | 0 | 0 |
| data/raw/updates/20261013/imd/imd_1992_2025_combined.csv | 295,392 | 724 | 1992-01-01–2025-12-01 | 0 | 0 |
| data/raw/updates/20261013/imd/imd_1992_2025_normals.csv | 8,688 | 724 | —–— | 0 | 0 |
| data/raw/updates/20261013/imd/imd_2025_district_monthly.csv | 8,688 | 724 | 2025-01-01–2025-12-01 | 0 | 0 |
| data/raw/updates/20261013/imd/imd_2025_normals.csv | 8,688 | 724 | —–— | 0 | 0 |
| data_ingestion/district_crosswalk.csv | 1,291 | — (not a mapped district series) | —–— | 0 | 0 |
| notebooks/district_name_validation.csv | 522 | — (not a mapped district series) | —–— | 0 | 0 |
| reports/audit-2026-10-17/model_comparison_cases.csv | 118 | 11 | —–— | 0 | 0 |
| reports/candidates/correlation/district_rainfall_gwl_correlation.csv | 532 | 532 | —–— | 0 | 0 |
| reports/candidates/forecast_replay/canonical_zones_20261015.csv | 725 | 725 | —–— | 0 | 0 |
| reports/candidates/groundwater_updates/20261013/canonical_district_month_candidates.csv | 639 | 639 | 2026-01-01–2026-01-01 | 0 | 0 |
| reports/candidates/groundwater_updates/20261013/rejected_station_records.csv | 347 | 110 | 2026-01-01–2026-01-01 | 0 | 0 |
| reports/candidates/groundwater_updates/20261013/retained_existing_district_months.csv | 0 | 0 | —–— | 0 | 0 |
| reports/candidates/groundwater_updates/20261013/station_audit.csv | 16,952 | 643 | 2026-01-01–2026-01-01 | 0 | 0 |
| reports/candidates/groundwater_updates/20261013/station_records.csv | 16,952 | 600 | 2026-10-01–2026-10-01 | 0 | 0 |
| reports/candidates/groundwater_updates/20261013/unmapped_districts.csv | 57 | 52 | —–— | 0 | 0 |
| reports/candidates/station_history_20261015/january_2025_audited/canonical_district_month_candidates.csv | 573 | 573 | 2025-01-01–2025-01-01 | 0 | 0 |
| reports/candidates/station_history_20261015/january_2025_audited/rejected_station_records.csv | 614 | 128 | 2025-01-01–2025-01-01 | 0 | 0 |
| reports/candidates/station_history_20261015/january_2025_audited/station_audit.csv | 15,892 | 581 | 2025-01-01–2025-01-01 | 0 | 0 |
| reports/candidates/station_history_20261015/january_2025_audited/station_records.csv | 15,892 | 527 | 2025-10-01–2025-10-01 | 0 | 0 |
| reports/candidates/station_history_20261015/january_2025_audited/unmapped_districts.csv | 34 | 34 | —–— | 0 | 0 |
| reports/candidates/station_history_20261015/january_2025_verified/station_records.csv | 15,892 | 527 | 2025-10-01–2025-10-01 | 0 | 0 |
| reports/candidates/station_history_20261015/matched_locations.csv | 9,543 | — (not a mapped district series) | —–— | 0 | 0 |

Per-column missing percentages, physical ranges, observed/imputed counts, unmapped identities, canonical omissions, chronological gaps and source hashes are in the JSON report.

## Findings

- **Medium — Legacy completeness reporting repaired**: data_ingestion/data_completeness.py previously joined numeric CGWB codes to state-less weather names, counted weather rows across 1992–2025 and divided by a fixed276 months. It now maps all sources to canonical IDs, counts distinct finite months inside the configured297-month window, includes zero-coverage districts and exposes source diagnostics.
- **Medium — 725-versus-716 coverage concern measured**: The crosswalk has 725 canonical IDs and 724 have an unambiguous state-qualified GeoJSON name/alias match. 1 canonical districts lack a matching boundary; they must remain explicit records in APIs even when no polygon can represent them.
- **Medium — 166-versus-24 has separate meanings**: The legacy readiness helper's fixed276-month denominator required166 observed months at60%. Serving uses configured dates, quarterly expected monitoring rounds, and a minimum24 actual observations. For2002-01–2026-09:297 calendar months,99 expected rounds and60 observed months at60%. The monthly history model separately requires24 observations spanning36 months. The legacy helper is repaired in this audit.
- **Medium — No predictions.csv export exists**: No predictions.csv was present outside scratch test fixtures at inventory time; this is an absent export, not evidence that database predictions are empty. The database audit measures stored predictions separately.
- **Info — data/processed/features_matrix.csv**: 215325 rows/725 mapped districts; 2002-01-01 through 2026-09-01; 0 exact duplicate rows; 0 duplicate monthly keys; 0 unmapped source rows.
- **Info — data/processed/preprocessed_wide.csv**: 215325 rows/725 mapped districts; 2002-01-01 through 2026-09-01; 0 exact duplicate rows; 0 duplicate monthly keys; 0 unmapped source rows.
- **Info — data/processed/imd_rainfall_district_monthly.csv**: 295392 rows/724 mapped districts; 1992-01-01 through 2025-12-01; 0 exact duplicate rows; 0 duplicate monthly keys; 0 unmapped source rows.
- **Info — data/processed/era5_district_monthly.csv**: 199824 rows/724 mapped districts; 2002-01-01 through 2024-12-01; 0 exact duplicate rows; 0 duplicate monthly keys; 0 unmapped source rows.

## Database

Read-only setting: on.

| Table | Rows | Districts |
|---|---:|---:|
| districts | 725 | 725 |
| raw_data | 741,628 | 725 |
| features | 215,325 | 725 |
| predictions | 4,326 | 721 |
| crisis_scores | 2,175 | 725 |

Orphan foreign keys: 0. Observed feature/raw GWL mismatches: 0.
Stored run coverage and per-source dates/ranges are in the JSON report.

## Reproduce

```powershell
.\venv\Scripts\python.exe -m scripts.audit_data_quality --database --as-of 2026-10-17
.\venv\Scripts\python.exe -m data_ingestion.data_completeness --output reports/candidates/data_completeness.csv
```

Source units are checked against available manifests. Metadata and physical-range checks do not independently prove source authenticity, publication-time availability, aquifer comparability, or scientific accuracy. No synthetic records are introduced.
