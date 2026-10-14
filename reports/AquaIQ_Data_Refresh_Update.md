# AquaIQ data refresh — 13 October 2026

The local project and PostgreSQL database were refreshed with **January 2026 CGWB groundwater observations** and the **complete 2025 IMD rainfall archive**. Both forecast models were rebuilt against the new feature generation, and a complete district scoring run was published. ERA5 temperature and potential evaporation remain through December 2024, as requested.

## Verified sources and applied coverage

| Input | New source coverage | Applied update |
| --- | --- | --- |
| Groundwater depth | CGWB January 2026 station report | 639 new district-month averages, based on 16,605 accepted readings |
| Rainfall | IMD annual 2025 daily 0.25° grid | 8,688 district-month totals, 724 districts, January–December 2025 |
| Temperature | Existing ERA5 source through December 2024 | No new source observations |
| Potential evaporation | Existing ERA5 source through December 2024 | No new source observations |

Groundwater source: [CGWB January 2026 PDF](https://cgwb.gov.in/wl_data/January_2026.pdf), retrieved from the [official monitoring page](https://cgwb.gov.in/hi/ground-water-level-monitoring). Its title explicitly specifies depth in metres below ground level and January 2026; original station observation dates are retained in the audit. Source SHA-256: `b4a23c8073b3b0b61c242a865930eff2c13c3e8ff1433a7a6a7990e27c037beb`.

Rainfall source: [official IMD annual archive](https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html), POST `rain=2025` to its `rainfall.php` endpoint. The binary contains exactly 365 × 129 × 135 little-endian float32 values, **25,425,900 bytes**, with 4,964 usable land cells each day. Source SHA-256: `b4fa5ffb389496c0fa7d5a468d1cb47e4db0bcabcd11be4f273c0e6cfa7d611d`.

The Gujarat NWIC resource labelled 2026–2030 was header-only. The 2021–2025 resource contained readings only through August 2023. Those downloads were not presented as fresh 2026 observations or merged over existing historical groundwater averages.

## Validation and preservation

All 447 groundwater PDF pages passed the inspected header/layout/unit/month checks. Actual station coordinates were mapped into the project's fixed district polygons, preserving its canonical geography despite modern district splits. There was no nearest-district or guessed parent-district assignment. Unnamed state outlines in the GeoJSON were excluded from the district join.

Of 16,952 source rows, 347 were excluded. Reasons can overlap: 121 state/coordinate conflicts, 115 unresolved district locations, 111 conflicting station/date depths, 25 invalid coordinates, and five identical duplicate readings. Within each district, accepted readings were averaged within each unique station-month first, then across stations. Existing groundwater months were retained; the 639 January 2026 months were new inserts only.

Station/audit/candidate CSVs remain locally in `reports/candidates/groundwater_updates/20261013/`; their hashes and counts are recorded in `manifest.json`, and `applied.json` records the database insert result. January is the observation **month** in the application; this does not claim that each station was measured on January 1. Original dates are in the station and district candidate artifacts.

Rainfall processing requires every calendar day before producing a monthly total. Missing cells remain missing, with the existing district spatial aggregation method retained. The 2025 update was appended without overlapping older months. Database ingestion verified **zero changes to older rainfall values**.

Backup before promotion: `D:\AquaIQ\fix-backups\data-refresh-20261013T115427Z`. It includes processed datasets, model bundles, configuration/reports and a verified PostgreSQL custom-format dump. Backup metadata is in `reports/data_refresh_backup.json`.

## Rebuilt pipeline

- Feature timeline: January 2002–September 2026, 215,325 rows, 725 canonical districts.
- Feature generation: `physical-v3-causal-monthly-a3f9468a2569`.
- All 156,600 feature rows through December 2019 match the backup's values, within numerical round-trip tolerance; the training cutoff remains December 2019.
- Groundwater carry-forward remains limited to three months; weather carry-forward remains limited to two. Multi-year gaps were not filled with invented observations.
- Historical six-month endpoint XGBoost and the separate monthly climate-conditioned XGBoost were rebuilt, evaluated, and published with the new generation.
- Batch scoring completed for all 725 districts; run `13c89f63-a87d-5ef0-93fb-bab6089d6f34` contains 721 historical model endpoints. Missing evidence remains explicitly unavailable.
- Monthly forecasts still target November 2026 through April 2027 for the October 13 request date.

The monthly model's historical evaluation remains 1,936 observed labels across 510 districts: RMSE 2.456 m against persistence 2.770 m. On the 1,893 paired seasonal comparisons, seasonal persistence is better (2.398 m versus XGBoost 2.473 m). These new isolated January 2026 observations do not create adjacent observed origin/target pairs to validate the current projection. The historical endpoint still has only ten independent final holdout labels and underperforms persistence. Neither result establishes operational accuracy.

## Dashboard and remaining limits

Weather history end dates are shown separately for rainfall, temperature and evapotranspiration, with an explicit caveat for limited filled history. The application reports usable feature history, which can extend beyond actual source observations by the bounded carry-forward limit. Actual source coverage is in the table above and `data_refresh_live_verification.json`.

For example, January 2026 Gandhinagar is 39.205 m below ground from six accepted stations, and Krishna is 4.9167 m from 43. Differences from previous district averages can reflect different wells and aquifer coverage; they must not be interpreted as a measured change at identical wells. Coordinates preserve district geography, not identical monitoring-station composition. The January readings are still nine months old as of October 13, so current depth is estimated.

Future rainfall, temperature and evaporation remain assumptions from historical calendar-month averages, not live weather forecasts. Pumping is not included. Crisis scores retain their historical observation/model target dates and uncalibrated project weights.

2026 real-time rainfall was not promoted: three daily probes do not constitute a complete month, and intermittent IMD timeouts prevented a complete verified batch and annual-product overlap comparison. See `reports/IMD_Realtime_2026_Verification.md`. ERA5 refresh can follow once the user configures CDS access and dataset terms locally; no credentials were requested in chat or changed.

## Checks

339 Python unit checks and 12 PostgreSQL integrity/migration checks passed; the latter use read-only queries and rolled-back temporary schemas. Six frontend API checks, dashboard lint and production build passed. A temporary Windows resource error required retrying the final unit run outside the sandbox; the retry passed all checks.

Live source coverage, all-district monthly forecast validation, sample district responses and API checks are recorded in `reports/data_refresh_live_verification.json`: all 725 districts checked, 720 projections, five explicit insufficient-data results, and zero errors. API health verifies the database and both models; scores, alerts, district details and history returned HTTP 200. The local dashboard was verified with January 2026 groundwater, distinct weather coverage labels and November 2026–April 2027 forecast months; its captured view is `reports/data_refresh_graph.jpg`. Earlier audit/forecast reports describe their earlier data snapshots; this report and its new verification artifact describe the refreshed generation.

During concurrent rebuilding/testing, the machine hit a temporary memory/resource shortage and its long-running development servers stopped responding. They were restarted after the rebuild and the dashboard was rechecked. The production data update and scoring publication had completed successfully; no database restore was needed.

## Repeat the update

Download into a new staging folder; take a database/dataset/model backup before promotion. Do not replace the old groundwater CSV with the new quarterly snapshot.

```powershell
# Optional extraction/download libraries; CDS credentials are only needed for ERA5.
python -m pip install -r requirements-download.txt
python -m data_ingestion.update_weather_sources imd --year 2025 --out-dir data/raw/updates/<run>/imd
python -m data_ingestion.imd_district_climatology --raw-dir data/raw/updates/<run>/imd --out data/raw/updates/<run>/imd/monthly.csv --normals-out data/raw/updates/<run>/imd/normals.csv
python -m data_ingestion.merge_rainfall_update --existing data/processed/imd_rainfall_district_monthly.csv --update data/raw/updates/<run>/imd/monthly.csv --output data/raw/updates/<run>/imd/merged.csv --normals-output data/raw/updates/<run>/imd/merged_normals.csv
python -m data_ingestion.cgwb_updates --pdf <downloaded-cgwb.pdf> --output-dir reports/candidates/groundwater_updates/<run> --as-of <today> --expected-month <YYYY-MM> --source-url <official-source-url>
python -m data_ingestion.cgwb_updates --apply-candidates reports/candidates/groundwater_updates/<run> --as-of <today>
```

Inspect candidate audits before applying. The rainfall merger refuses overlapping months, changed/missing boundary provenance, unverified units, incomplete-day aggregation, invalid values, and output paths that would overwrite inputs. The groundwater apply command checks candidate hashes, units, geographic provenance, observation dates and district identities, then inserts missing months only. Reapplying the same groundwater candidate retains existing months. For subsequent rainfall years, stage and validate the new year rather than appending 2025 again.

After promoting verified rainfall CSVs/manifests, ingest them, extend `date_range.end` only to the intended completed month, then run preprocessing, features, training, backtest and scoring in that order. Both checkpoints must match the rebuilt feature generation before serving predictions. Raw updates and trained bundles are local artifacts excluded from Git; a code push alone does not update another machine's database or trained models.
