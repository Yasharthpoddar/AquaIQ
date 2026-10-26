# Auxiliary sources and operational review, 26 October 2026

These checks acquired useful source evidence, but did not establish a better
groundwater forecasting method. **No auxiliary value was added to the active
features, no new groundwater observation was created, and no model was refitted.**
The machine-readable companion, `auxiliary_sources.json`, contains exact URLs,
download timestamps, byte counts, SHA-256 checksums, separate acquisition states,
and the frontend verification record. Raw files remain ignored local inputs.

| Source actually checked | Acquired and parsed | Decision |
|---|---|---|
| [CGWB GWRA 2025](https://cgwb.gov.in/en/ground-water-resource-assessment-0) | The 956,257-byte official block categorization PDF: all 97 pages, 6,762 sequential assessment records, 36 state/UT labels and 709 source district labels. Categories: safe 4,945; semi-critical 759; critical 201; over-exploited 730; salinity 127. | Contextual resource-assessment classes have no monthly groundwater-depth units. They are distinct from AquaIQ's risk index. No target replacement or model input. |
| CGWB 2025 fact-sheet index | A 137,344-byte two-page PDF with 36 numbered state/UT entries and 37 underlying report links. | The index was acquired; those 37 fact-sheet reports were not. No measurement coverage claimed from links alone. |
| [CGWB aquifer mapping](https://cgwb.gov.in/en/aquifer-mapping) | Official landing page and pilot-report links inspected. | No nationwide numeric aquifer feature matrix or GIS layer was acquired. Per-report boundaries, units and availability at historical origins still require validation. |
| [ISRIC SoilGrids](https://isric.org/explore/soilgrids) | A 5,929,079-byte clay VRT referencing 12,970 rasters; two API point responses. Rural 77.5°E, 28.5°N: modeled 0–5 cm clay 196 g/kg = 19.6%; urban 77.2°E, 28.6°N: null. | The VRT is an index, not downloaded raster values. One modeled soil pixel cannot represent a district or replace groundwater depth. No complete district aggregation or transfer evaluation. |
| [ESA WorldCover](https://esa-worldcover.org/en/data-access) | A 543,674-byte GeoJSON index with 2,651 tile footprints. | No land-cover pixels or district fractions acquired. The 2021 map was released in October 2022; retrospective use needs explicit vintage handling. Algorithm changes also affect 2020/2021 comparisons. |
| [NASA SRTMGL1 V003](https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003) | Catalog metadata, describing 30 m elevation from 11–21 February 2000. | Individual raster access, datum, aggregation and specific usage terms were not checked. This is an unchecked raster acquisition, not a claim that data are unavailable. |
| [NASA GSFC GRACE/GRACE-FO](https://earth.gsfc.nasa.gov/geo/data/grace-mascons) | Current catalog and exact NetCDF HEAD request succeeded. Advertised April 2002–March 2026; 530,877,840 bytes. | The NetCDF was not downloaded. Mass/water-storage changes have coarse spatial support and include multiple water compartments; conversion to district depth requires a validated hydrological model. The older JPL URL returned 404. |

The GWRA PDF SHA-256 is
`7a30b79ce2b25020da5c574f6ae50ee4335fbe409ee2600a9f2a8f9449e2231f`;
the fact-sheet index is
`6d59fb18c5c7eacf41dd7450de5eec5efc2ffe601232f0f6ddf754045401b553`.
The SoilGrids VRT is
`ad1a77d56090bf543e3600bc48d4cd6fa80f8e1a9eb37177044de65a64848ede`;
the WorldCover index is
`eeb5074bf182c411b3872b2494f6514401ecd9ba8ba0c353fe282f1e2b822f5b`.
API point responses include variable query-duration metadata, so each response
gets its own exact-byte checksum rather than a falsely fixed response hash.

## Reproduce safely

The new acquisition command uses fixed official HTTPS URLs, the system trust
store, bounded file sizes, timeouts, at most two retries, explicit output
directories and exclusive file creation. Fixed published resources require the
inspected SHA-256. Changed bytes fail rather than silently updating the catalog.
Normal API requests never import or call this command.

```powershell
.\venv\Scripts\python.exe -m data_ingestion.auxiliary_sources
.\venv\Scripts\python.exe -m data_ingestion.auxiliary_sources --download --output-dir data/raw/official_enrichment/auxiliary_reproduction_NEW
```

The first command is an offline plan. The second requires a new directory and
continues collecting per-source failures, returning nonzero when acquisition
fails. It never downloads the 531 MB GRACE file; that source uses HEAD only.
Parsing the contextual assessment tables is an explicit offline operation,
requiring optional `pdfplumber` (the bundled document runtime was used here):

```powershell
python -m data_ingestion.auxiliary_sources --parse-gwra data/raw/official_enrichment/auxiliary_reproduction_NEW/cgwb_gwra_2025_blocks.pdf --output-dir data/raw/official_enrichment/gwra_context_NEW
```

The parser verifies the exact source hash, 97-page layout, five columns,
consecutive serial numbers, allowed categories and 6,762 final rows. Puducherry's
title-case categories are normalized while their raw spelling is retained.
Output retains state, district, assessment-unit and source-page provenance.
This is contextual extraction, not canonical district assignment or predictive
validation. The source's 709 district labels cannot be equated to the fixed
725-district project registry.

CGWB's `requests`/certifi path failed certificate validation locally. Secure
`urllib.request` with Windows system trust succeeded; certificate verification
was never disabled. HTTP `Last-Modified` is recorded as a server header, not
claimed as an independently verified first-publication date.

## Attribution and scientific limits

[CGWB's copyright policy](https://cgwb.gov.in/en/copyright-policy) permits accurate,
nonmisleading reproduction with prominent source acknowledgment, excluding
third-party material. It does not declare a separate blanket open-data license.
[SoilGrids](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html) and
[WorldCover](https://esa-worldcover.org/en/data-access) use CC BY 4.0. Cite Poggio
et al. (2021), *SoilGrids 2.0*, DOI 10.5194/soil-7-217-2021, and Zanaga et al.
(2022), *ESA WorldCover 10 m 2021 v200*, DOI 10.5281/zenodo.7254221. NASA catalog
access was checked; dataset-specific terms were not fully audited and no NASA
raster or mascon values are redistributed.

These sources did not provide a complete, origin-available district predictor
matrix with spatially blocked, genuinely held-out groundwater validation. No
claim of auxiliary predictive improvement is justified. The frozen forecasting
artifact remains the comparison baseline. No performance metric was fabricated
for candidates that were not fitted.

## Verified operational improvement

The previous production frontend emitted one **876.52 kB** JavaScript chunk and
the existing 500 kB warning. The Vite 8 configuration now groups stable React,
map and chart dependencies using supported Rolldown `codeSplitting` options.
The resulting app/maps/React/charts chunks are **142.03 / 148.73 / 218.84 /
365.50 kB**, plus a 0.71 kB bundler runtime. No warning threshold was raised.
This improves chunk/cache granularity; all pages remain statically imported,
and no first-paint or total-bandwidth speedup is claimed.

Validation actually completed:

- 13 acquisition/parser unit tests passed, covering checksum changes, immutable
  paths, malformed formats, schema/coordinate/unit/depth changes, null and zero
  soil values, source size limits, timeouts, HEAD-only access, assessment serials
  and categories, and the offline plan.
- A real CLI acquisition verified the fixed GWRA PDF and WorldCover index hashes
  and parsed the rural SoilGrids response. The full contextual PDF parse passed.
- All 155 frontend tests passed; lint and the production build passed.
- The 31 existing CORS and deployment-readiness tests passed. Inspection found no
  additional substantiated CORS defect: explicit origins, rejection of wildcard
  and credential/path origins, and empty same-origin configuration are covered.
- The production build was served locally on port 5184. The existing scored
  browser suite passed all five flows: actual 725-district risk rendering,
  country bounds/reset at 1440/768/390 widths, map-to-district navigation, all
  alert filters including four unavailable indices, and alert-to-forecast
  navigation. No page errors occurred.

All model, source-database and forecast-publication behavior remained unchanged
by this auxiliary/operations subtask. Root data-enrichment evaluation and tests
are reported separately in the main release report.
