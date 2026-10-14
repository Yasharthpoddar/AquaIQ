# Weather refresh readiness — 13 October 2026

The local project has rainfall through 2024 and ERA5 temperature/potential evaporation through December 2024. This review inspected source metadata and access readiness only; it did not change weather data, features, models or the database.

## Rainfall

The [official IMD 0.25° binary archive](https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html) returned HTTP 200 and lists **2025** in its year selector. Its form submits a POST to `https://imdpune.gov.in/cmpg/Griddata/rainfall.php` with `rain=2025`. The archive therefore provides a concrete candidate to extend the existing IMD dataset by one complete year. The response and the downloaded file still need validation before ingestion; a year selector alone does not prove complete coverage.

The existing project reader uses 129 × 135 grid cells and one float32 field per calendar day. A complete 2025 file should contain 365 × 129 × 135 float32 values, or **25,425,900 bytes**. Preserve the documented grid orientation, missing-value handling, and requirement that every day be available before calling a cell's rainfall sum a monthly total. District aggregation must use the same boundary artifact and state-aware canonical ID matching.

The [IMD real-time daily rainfall page](https://imdpune.gov.in/cmpg/Realtimedata/Rainfall/Rain_Download.html) is the candidate for 2026. Access was unreliable during this review. Its daily downloads must be validated against their own control metadata, not assumed to have the annual archive's identical dimensions or layout. Current partial October observations must not be presented as a complete October total. The bare host `imdpune.gov.in` was reachable for the archive while `www.imdpune.gov.in` timed out.

## Temperature and potential evaporation

Use [ERA5 monthly single-level means](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means?tab=overview), preserving the current source family and variables. The [catalogue](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means?tab=overview) describes monthly release around the sixth of the following month and possible later revision of preliminary ERA5T values. January 2025 through September 2026 is therefore the appropriate request window as of this review, subject to actual catalogue availability. Do not request future or incomplete October 2026 data.

Use separate year requests to avoid requesting October–December 2026 through a Cartesian year/month combination:

```json
{
  "dataset": "reanalysis-era5-single-levels-monthly-means",
  "product_type": ["monthly_averaged_reanalysis"],
  "variable": ["2m_temperature", "potential_evaporation"],
  "year": ["2025"],
  "month": ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"],
  "time": ["00:00"],
  "area": [38, 68, 6, 98],
  "data_format": "netcdf"
}
```

Repeat with `year=["2026"]` and only months `01` through `09`. Use the dataset download form's generated API request to confirm current request syntax before submitting. Record request, retrieval time, SHA-256, source dates, preliminary/reanalysis provenance, and units with each immutable downloaded artifact.

The existing clean source contains 276 monthly timestamps, January 2002 through December 2024, on the same bounding box at 0.25° resolution. `t2m` has Kelvin units. `pev` has metres units and `GRIB_stepType=avgad`. Convert `t2m` to °C by subtracting 273.15. The [ERA5 documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=669811810) specifies daily effective accumulation for monthly-mean accumulated fields: for this negative evaporation convention, monthly demand is `max(0, -pev × 1000 × calendar_days_in_month)` in mm/month. Retain explicit aggregation metadata and perform the conversion exactly once. Never replace missing potential evaporation with zero or silently substitute ERA5-Land potential evaporation, which uses a different definition.

## Access blockers

- No `C:\Users\Yasharth\.cdsapirc` file was found.
- Neither `CDSAPI_KEY` nor `CDSAPI_URL` was configured in the inspected process environment or project `.env`. Only presence was checked; secret values were not printed.
- The project virtual environment has `xarray` and `netCDF4`, but no `cdsapi`. The optional `requirements-download.txt` includes the client.
- [CDS access instructions](https://cds.climate.copernicus.eu/how-to-api) require an account, a personal access token, and manual acceptance of the dataset's terms from its download page. No registration, acceptance, credential changes or dependency installation was attempted during this readiness review.
- The existing `data_ingestion/download_era5.py` is fixed to 2002–2024 and creates a CDS client on import. An incremental command with explicit dates/output and no import-time authentication is needed before retrieval.

Once the legitimate CDS access is configured locally, download the missing months into new files, verify exact calendar coverage and physical units, aggregate to new district CSVs/manifests, then perform the separately backed-up ingestion and feature/model regeneration. Groundwater refresh can proceed independently while weather access is configured. Until ingestion succeeds, the application must continue reporting its actual weather record age rather than claiming a 2026 refresh.
