# Official weather source checks, 26 October 2026

Two official IMD products were downloaded and parsed. Neither supplies a validated replacement for the current weather predictors. The retained software improvement makes the existing split-field ERA5 download reproducible without extracting arbitrary ZIP paths or selecting only one of its fields. The active weather CSVs and trained model weights were preserved.

The complete metadata, source status, source dates, byte counts and SHA-256 values are in [weather_sources.json](weather_sources.json). Downloaded source files and prepared arrays remain local and ignored by Git.

| Checked source | Acquired data | Result |
| --- | --- | --- |
| [IMD 0.25 degree rainfall archive](https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html) | 2025 NetCDF, 25,431,832 bytes; 1,811,860 valid grid-day values | Every valid value and missing mask matches the existing 2025 annual GRD. There are **zero new weather observations**. |
| [IMD 1 degree maximum temperature archive](https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html) | 2025 GRD, 1,403,060 bytes; 129,552 valid grid-day values | A daily maximum is a different variable from monthly mean 2 m temperature. It cannot be substituted into the frozen ERA5 model, and it supplies no potential evaporation. |
| [Copernicus ERA5 monthly means](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means) | Official catalogue JSON, 7,841 bytes | The catalogue advertises observations through September 2026 and CC-BY-4.0. New data were not downloaded: the optional CDS client is absent, and authenticated retrieval and accepted account terms were not tested. This does not establish that the data are unavailable. |
| [IMD real-time rainfall](https://www.imdpune.gov.in/cmpg/Realtimedata/Rainfall/Rain_Download.html) | Three previously acquired overlap probes reviewed; no new daily files | The existing gate correctly rejects equivalence to the quality-controlled annual product. June 15, 2025 differs in 346 of 4,964 shared usable cells, with a maximum difference of 55.666 mm. No tolerance was adjusted to admit it. |
| [IMDWeb](https://imdweb.lwcc.in/) | 419-byte application shell | No independently attributed observation resource was acquired. The page's name does not establish an official IMD publisher; acquisition used the underlying government endpoints instead. |
| [Mumbai Suburban district](https://mumbaisuburban.gov.in/en/about-district/) and [MRSAC district map](https://mrsac.gov.in/writereaddata/MRSAC/map/15638756425d36d93a68368Dist_Mumbai_Sub.pdf) | Indexed official content checked; direct bounded downloads timed out | No verified georeferenced district polygon was acquired. The district page has inconsistent area figures and malformed coordinate headings. No Mumbai alias or invented district centroid was applied. |

The IMD product pages still describe coverage ending in 2024, but their actual form options include 2025, and the downloaded files validate as complete 2025 calendars. Both rainfall and temperature products are latitude/longitude grids; their product pages do not separately identify a geodetic datum. The existing spatial processing conventions were not changed.

IMD requests citation of Pai et al. (2014), *MAUSAM* 65(1), 1-18 for rainfall, and Srivastava, Rajeevan and Kshirsagar (2009), DOI [10.1002/asl.232](https://doi.org/10.1002/asl.232) for temperature. No explicit open redistribution licence was found on the inspected IMD product pages. The raw downloads are not committed. The current Copernicus catalogue explicitly reports CC-BY-4.0 and DOI [10.24381/cds.f17050d7](https://doi.org/10.24381/cds.f17050d7).

## Deterministic ERA5 preparation

The repository's existing `era5_temp_pet_india_2002_2024.nc` is a ZIP despite its extension. It contains separate temperature and evaporation NetCDF members. The old fallback extracted every archive member and returned the first NetCDF found, which could omit a required variable or write an untrusted member path. Preparation now:

1. Bounds archive member count and total uncompressed size, rejects paths, encrypted members and duplicate variable names, and opens NetCDF bytes in memory.
2. Records each member's hash and requires matching spatial coordinates and calendar months. The inspected CDS monthly temperature labels use 00:00 UTC and monthly `pev` `avgad` labels use 06:00 UTC on day one. These labels map to the same calendar month; other sub-month conventions fail closed.
3. Retains Kelvin and the documented evaporation source metadata. Celsius conversion and monthly evaporation definitions are unchanged.
4. Publishes a new file without replacing existing source or output paths, with a provenance manifest. A concurrent output also fails safely.

The prepared file has all 276 months from January 2002 through December 2024. Every coordinate and all values of `pev`, `t2m`, and `t2m_celsius` are bitwise equal to the current cleaned artifact, with identical missing masks and zero maximum absolute difference. [weather_era5_equivalence.json](weather_era5_equivalence.json) records the checksums. The raw ZIP's SHA-256 remains `4edf8ff080ce5e7b380924cac345e87f1e886c6937ceed53268ac254ce4cff41`.

## Reproduction

Run from the repository root with the project environment. Downloads happen only on explicit CLI invocation; API requests do not run these commands.

```powershell
.\venv\Scripts\python.exe -B -m data_ingestion.weather_enrichment --product rainfall_netcdf --year 2025 --out-dir data/raw/official_enrichment/weather_20261026
.\venv\Scripts\python.exe -B -m data_ingestion.weather_enrichment --product temperature_max --year 2025 --out-dir data/raw/official_enrichment/weather_20261026
.\venv\Scripts\python.exe -B -m data_ingestion.weather_enrichment --year 2025 --out-dir data/raw/official_enrichment/weather_20261026 --compare-binary data/raw/imd/Rainfall_ind2025_rfp25.grd --report scratch/weather_rainfall_comparison_reproduced.json
.\venv\Scripts\python.exe -B -m data_ingestion.era5_to_district --prepare-source data/raw/era5/era5_temp_pet_india_2002_2024.nc --prepared-out data/processed/enrichment_reproduction/era5_india_2002_2024_prepared.nc
```

Complete acquired source/manifest pairs can be reused only after their checksum and schema are revalidated. Comparison reports and prepared outputs require a new path; choose another output path for repeated runs. Existing files are never silently overwritten. The downloader enforces a 15 second connection timeout, 30 second read timeout, at most two request attempts by default, response-size limits, expected grids, full calendar alignment and physical value screening. HTML responses and malformed files are rejected before publication.

For future ERA5 acquisition, the existing `data_ingestion.update_weather_sources` CLI already constructs completed-month requests and validates units, requested dates and the India bounding box. Install the optional `cdsapi>=0.7.7` client and configure user-managed credentials only after following the [official CDS API setup](https://cds.climate.copernicus.eu/how-to-api). The account owner must have accepted the dataset's terms manually. No term acceptance or authenticated retrieval was performed in this weather investigation.

## Scientific outcome

Weather completeness remains unchanged: 215,325 feature rows, with 209,960 nonmissing rainfall values and 201,272 nonmissing values for each of temperature and potential evapotranspiration. Mumbai Suburban remains without independently established weather attribution. No new genuine groundwater observations were derived from any weather product. Forecast accuracy cannot improve merely from downloading an identical rainfall representation or substituting a different temperature statistic. New weather values were therefore excluded, while the reproducibility and archive-handling defect was fixed.

The existing future-weather assumptions remain labelled climatology rather than observed future weather. Model training and serving feature definitions were preserved. No new weather candidate was tuned or selected on held-out forecast targets.

The focused verification completed with **41 passed** (48 warnings) in 312.74 seconds. The command is:

```powershell
.\venv\Scripts\python.exe -B -m pytest -q tests/test_weather_enrichment.py tests/test_data_correctness.py tests/test_spatial_fallback.py --disable-warnings --basetemp=scratch/pytest-weather-enrichment-reproduction
```

It covers complete source calendars and units, rainfall representation equivalence, invalid values, malformed downloads, checksum changes, immutable output paths including concurrent creation, unsafe archive paths, duplicate variables, incompatible grids and unknown monthly timestamp conventions. Synthetic fixtures stay under the ignored scratch directory.
