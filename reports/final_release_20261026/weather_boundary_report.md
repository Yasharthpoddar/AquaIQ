# Weather access and Mumbai boundary investigation — 2026-10-26

The investigation acquired a dated official boundary source and measured its relationship to the existing weather grids. It acquired **zero new weather observations** and changed **zero production weather features**. Mumbai Suburban retains its existing missing-weather treatment and Tier D status. No groundwater records, historical boundary mappings, model artifacts or published database generations were changed by this investigation.

## Authenticated ERA5 request

The existing user-managed Copernicus configuration was used through `cdsapi==0.7.7`; credentials and configuration contents were never printed or serialized. A bounded request submitted on 2026-10-26 requested January 2025 monthly mean 2 m temperature and potential evaporation over the existing India bounding box. The actual server response was **HTTP 403**. In-memory inspection found the specific phrases indicating required licences were not accepted; only boolean evidence and the error category were retained.

The [official API instructions](https://cds.climate.copernicus.eu/how-to-api) require the account holder to accept dataset terms manually. The agent did not accept those terms. The [monthly dataset catalogue](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means?tab=download) displayed a CC-BY licence, DOI `10.24381/cds.f17050d7`, and update date 2026-10-06. Reachable metadata and the configured request attempt do not establish that newer arrays are downloadable by this account. Credential validity was not independently verified.

No data response, source checksum, new-date axis or numerical overlap comparison could be obtained. Newer or revised ERA5 values are therefore **unassessed**, rather than absent. The first immutable probe manifest predates the corrected failure-status code and has `accessible=null`; its HTTP 403 and licence evidence remain intact. Subsequent code records `accessible=false` for 401/403 failures.

The new retrieval module bounds processing time and response size, suppresses provider callbacks and signed download URLs, cancels only its own timed-out job, and creates isolated immutable candidate files. It uses the existing preparation and physical-unit conventions: UTC source month starts, Kelvin to Celsius, and ERA5 `moda`/`avgad` potential evaporation in metres of daily mean accumulation converted once using calendar month length and the existing sign convention. Validation requires the exact requested months and the existing 129 × 121 quarter-degree grid. The comparison helper measures common-month missing masks and numerical differences separately from genuinely new source months. These paths were tested using controlled arrays; no live array validation is claimed after the 403 response.

## Acquired official boundary source

[Survey of India ABDB](https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-) provides a public national archive and metadata archive. Actual HTTP 200 responses and completed downloads established availability. The geometry archive is 202,524,438 bytes, SHA-256 `b8325e5d9dd0f04a6663d775363fe38cd2f23bd9dbae3fb7118b4e6e0ce0bcb7`, downloaded completely at `2026-10-26T14:41:44.271403+00:00`. The 38,879-byte metadata ZIP has SHA-256 `1a14716b73f00fc8391f2708a7975c2f2c1ad4a4e91aafb6dce6546a039e9514`.

The district metadata identifies `SOI/ABDB/VECTOR/50000/2025/DISTRICT/INDIA`, publication 2026-05-06, edition 2025, creation/temporal extent 2022–2025, and Maharashtra harmonization with ORGI in 2025. The stated scale is 1:50,000 and publisher positional-accuracy statement is 12.5 m. This supplies a dated contemporary definition; it does not prove that historical groundwater observations share that vintage.

The metadata marks access and use as **copyright** and requires following Geospatial Guidelines 2021. [SoI terms](https://surveyofindia.gov.in/pages/terms-and-conditions) also qualify the website's accuracy and legal applicability. Attribution is Survey of India. No general redistribution permission was assumed. Raw downloads and the polygon subset remain ignored local files; only code and aggregate provenance are intended for Git.

The initial large download stopped early. Two verified HTTP 206 continuations requested only missing ranges and checked unchanged Last-Modified and exact Content-Range. The completed archive hash was verified; no downloaded prefix was requested again. The native Windows `tar.exe` streamed the national shape member without writing national geometry. Small source sidecars and only two exact polygon records were retained, totalling **50,179 bytes**. Record coordinates and attribute values were preserved; only subset headers and record indexing were rebuilt. Selection used exact Maharashtra LGD codes **519 (Mumbai)** and **518 (Mumbai Suburban)** from 808 source records, with no fuzzy alias or district migration.

Both polygons are valid and distinct. The source-projected geometry areas are 62.3025 km² for Mumbai and 418.3377 km² for Mumbai Suburban. These are geometry diagnostics, not equivalence claims about administrative area figures published under other definitions. The metadata declares EPSG 7755, but the supplied PRJ's standard-parallel values differ slightly from the registered CRS. The supplied PRJ was used directly; the representative-point difference from forcing EPSG 7755 is approximately 2 cm. This discrepancy is retained explicitly in the audit.

The separate [MRSAC Mumbai Suburban PDF](https://mrsac.gov.in/writereaddata/MRSAC/map/15638756425d36d93a68368Dist_Mumbai_Sub.pdf) failed a bounded request with `URLError`/timeout. No body was acquired or parsed, and no availability or licensing conclusion was inferred from the timeout.

## Measured weather attribution

The comparison reused the existing cleaned ERA5 array, SHA-256 `6fe76f7f43a9c389038f189dd49575598d02e9aeb19be3e615934351a0b00eb8`, with 276 months from January 2002 through December 2024. The existing DataMeet artifact was used only to preserve the current processor's usable land-center rule. Its SHA-256 is `e724c14bc5ee68bcdd6cee8c89222b80cb61e180e55c1dab3d067f09b3b9dc8f`.

| District | Interior usable ERA5 centers | Existing nearest land cell | Distance from representative point | Geometric pixel footprints overlapping polygon |
| --- | ---: | --- | ---: | ---: |
| Mumbai (519) | 0 | 19° N, 73° E | 18.522 km | 2 |
| Mumbai Suburban (518) | 0 | 19° N, 73° E | 17.694 km | 4 |

The footprint calculation intersects densified quarter-degree grid-pixel polygons in the supplied source projection. It is an alternative aggregation definition, distinct from selecting grid centers within a district and falling back to the nearest usable land center. All overlapping source fields were finite for the assessed months; available geometric area was effectively **100%** for both districts. This is not a partial-array-coverage problem.

| District | Overlapping grid center | Fraction of source polygon area |
| --- | --- | ---: |
| Mumbai | 19° N, 72.75° E | 97.260% |
| Mumbai | 19° N, 73° E | 2.740% |
| Mumbai Suburban | 19.25° N, 72.75° E | 31.511% |
| Mumbai Suburban | 19.25° N, 73° E | 24.001% |
| Mumbai Suburban | 19° N, 72.75° E | 10.250% |
| Mumbai Suburban | 19° N, 73° E | 34.239% |

None of these grid centers lies inside its corresponding source polygon. Footprint weighting includes offshore-centered source cells excluded by the current land-center rule. Across 276 diagnostic months per district, its maximum absolute difference from current-rule nearest-cell values was **1.4475 °C / 136.328 mm monthly PET** for Mumbai and **0.3955 °C / 22.126 mm monthly PET** for Mumbai Suburban. These are differences between grid aggregation methods, not model error reductions or direct district measurements.

All 34 existing IMD annual files from 1992–2025 were separately checksummed and aggregated only over complete calendar months. They yielded 408 diagnostic months per district. Mumbai selected the nearest usable cell at **19° N, 72.75° E (8.591 km)**; Mumbai Suburban selected **19° N, 73° E (17.694 km)** throughout. No source grid observation was newly acquired. No artificial assignment of equal values was made.

## Historical compatibility and decision

The official polygons improve evidence about boundary identity and vintage. Under the existing ERA5 feature method, both districts still select a shared out-of-district coarse cell; that does not establish independent district weather. The diagnostic alternatives remain separate from production.

An in-memory candidate filling only Mumbai Suburban temperature and PET from the existing-rule proxy changed **216 historical rows before 2020**. `prove_frozen_compatibility(..., '2019-12-31')` correctly rejected that historical weather change. The candidate was not persisted. Footprint weighting would also change the feature definition and historical values. It cannot inherit the original frozen-training proof.

No alternative weather method was promoted or scored as a trained district model. A fair skill comparison would require a separate artifact trained with the candidate feature definition and a prespecified evaluation period that has not already informed selection. The current inspected holdout cannot honestly supply that new independent evidence. This investigation therefore reports measured coverage and feature differences, preserves Tier D, and makes no held-out accuracy improvement claim. No historical observation was moved between boundary vintages.

## Validation and reproduction

Focused tests actually completed: **25 passed, 0 failed, 0 skipped, 13 warnings, 10.67 seconds**. They cover sanitized terms/authorization failures, bounded job cancellation, immutable output scope, exact months/grid/physical conversions, numerical overlap, coordinate/attribute preservation, corrupt and deleted source records, pinned partial-download continuation, and official URL restrictions. Two diagnostic runs produced bitwise-identical CSVs. Aggregate evidence is in `weather_validation.json`, `weather_boundary_sources.json`, `weather_boundary_subset_provenance.json` and `weather_attribution.json` beside this report. Diagnostic CSVs and polygons remain in ignored candidate paths.

From the repository root on Windows:

```powershell
# Optional authenticated client. The account holder must manually review and
# accept the official dataset terms before a successful acquisition is possible.
.\venv\Scripts\python.exe -m pip install "cdsapi>=0.7.7,<1"

# Always choose fresh isolated paths; this probe creates a sanitized failure
# manifest when provider terms or authorization prevent retrieval.
.\venv\Scripts\python.exe -B -m data_ingestion.release_weather --start 2025-01 --end 2025-01 --source-dir data/raw/official_release/weather_rerun --prepared-dir data/processed/final_release/weather_rerun --max-wait-seconds 180

# Pinned public download. A verified completed local source is reused.
.\venv\Scripts\python.exe -B -m data_ingestion.release_boundaries --acquire-dir data/raw/official_release/boundaries_20261026

# Native Windows tar is required for RAR streaming; new output directories only.
.\venv\Scripts\python.exe -B -m data_ingestion.release_boundaries --archive data/raw/official_release/boundaries_20261026/SoI_ABDB_2025.rar --output data/processed/final_release/soi_mumbai_rerun/subset
.\venv\Scripts\python.exe -B -m data_ingestion.release_boundaries --archive data/raw/official_release/boundaries_20261026/SoI_ABDB_2025.rar --output data/processed/final_release/soi_mumbai_rerun/subset --weather-audit data/processed/final_release/soi_mumbai_rerun/weather_audit

.\venv\Scripts\python.exe -B -m pytest -q tests/test_release_weather.py tests/test_release_boundaries.py -p no:cacheprovider
```

The offline attribution command requires the documented existing ERA5, DataMeet and IMD baseline assets. It does not make a clean clone self-contained or establish permission to redistribute those source files. Acquisition, diagnostics and production integration remain separate operations.
