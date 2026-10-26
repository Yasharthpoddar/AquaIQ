# Groundwater evidence review, 26 October 2026

The reused, verified CGWB January 2025 archive supplies **542 additional genuine district-month observations**. Five districts gain their first local observation: `AR-Kamle`, `AR-Longding`, `SK-East_Sikkim`, `UK-Pithoragarh` and `UK-Rudraprayag`. **57 districts still have no accepted local history.** New downloads supplied documentation and availability checks; they supplied no additional accepted numerical groundwater records.

The frozen candidate is `reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2/manifest.json`, SHA-256 `a6e32fab5b3b9f16aa734b53e96a28bc8cf702dd306a27fd559fb549d93f420e`. Its new metadata paths are repository-relative. The original v1 candidate remains intact, and both candidates contain identical physical monthly CSV bytes. Generation of this candidate and this review does not write the database, deployed features or models.

## Measured targets and source precedence

The source contains 15,892 January 2025 rows. Strict date, units, coordinates, state agreement, boundary-margin and source-location identity checks accept **15,075 rows** and quarantine **817**. Overlapping reason counts are: conflicting location/date depths 174; state disagreement 105; near-boundary coordinates 89; ambiguous colocated labels 125; unresolved district 65; exact duplicate location/date/depth 271. Reasons can overlap, so they must not be summed as distinct rejected records.

Accepted rows yield 571 PDF district-months. The existing measured snapshot retains its 29 overlapping months; the other 542 months use 14,213 accepted source readings. Within the PDF, repeated dates are averaged by source location before equally weighting locations. Across products, whole-month precedence preserves every existing measured mean and prevents pooling mirrored products into that mean. A separate comparison finds no common rounded-coordinate/day keys between the 680 NWDP 2025 source rows and the 14,213 contributing PDF rows. This is a collision screen, not proof that two records describe different physical wells.

The target remains generic measured groundwater depth in `m_bgl`. Block/village/coordinate fingerprints are not certified well IDs. The archive title's aquifer classification does not certify each well's construction or establish an unconfined water table. Fixed, mixed-vintage project boundaries remain unchanged. These already inspected 2025 observations cannot establish a new blind accuracy improvement.

## Official sources actually checked

The machine-readable companion `groundwater_sources.json` records exact source URLs, hashes, byte counts, status and validation scope. CGWB material follows its [copyright/attribution policy](https://cgwb.gov.in/en/copyright-policy); no separate open-data grant was supplied. NWDP metadata labels its resources `Other (Open)` without a specific license URL. Raw downloads remain local and ignored by Git.

| Source | Acquisition and use | SHA-256 |
| --- | --- | --- |
| [CGWB January archive](https://cgwb.gov.in/wl_data/January_WL_1994-2025.pdf) | Reused 38,514,524-byte archive; extraction pages 1–332 identify actual January 2025 observations. Accepted missing-month targets as described above; no fresh accessibility claim. | `6ebb9cbf401c3fb7aca65c31b421ccf586c6fadbce5abb4d2a222e538b0534cd` |
| [February 2026 high-frequency groundwater guidance](https://cgwb.gov.in/cgwbpnm/public/publication-detail/1932) ([PDF](https://cgwb.gov.in/cgwbpnm/public/download/1932)) | Downloaded 7,653,133 bytes, 124 pages. PDF pages 49–50 require installation/reference information; pages 54–55 and 115 address depth screening and manual validation. Documentation only. | `b07dcc160175153df97f36ddac04170e89b42224b6bd7179109df776932fff12` |
| [Current NWDP manual package metadata](https://nwdp.nwic.gov.in/api/3/action/package_show?id=gwl-manual-quarterly-central-ground-water-board-department) | Actual GET of metadata and all 31 changed 2026–2030 resources. All bodies are 243-byte headers, zero rows; 7,533 bytes total. Nightly metadata changes do not establish new observations. | Metadata `906d2428da89779237b994b9032fe8dbe890fce9455c5081cc56996b102731b7`; every header `cc7824b6b3b72f9e9818f1ca4edab27eeb37b82d6af4092c9d7801d5389d03b6` |
| [WB/Andaman/Sikkim yearbook, publication label 2024–2025](https://cgwb.gov.in/cgwbpnm/public/publication-detail/2027) ([PDF](https://cgwb.gov.in/cgwbpnm/public/download/2027)) | Downloaded 15,855,569 bytes, 197 pages. Sikkim pages 194–196 describe four confined-aquifer piezometers. No new numerical station-depth table accepted. | `2414bae680e56f54035f31621b7d9d97a3fe7909ffed7d8f43e1dc268e08d530` |

The yearbook's Sikkim running header says 2023–24 while its publication label says 2024–2025 and its narrative discusses 2024 monitoring. Dates must therefore come from actual observation tables. Narrative, maps and plotted curves were not transcribed into numerical depth targets. The confined-aquifer caveat does not by itself invalidate generic measured `m_bgl` values in the January source.

## Telemetry remains quarantined

The four existing NWDP downloads contain 274,930 rows at 91 source station fingerprints. This review reuses their verified bytes; exact resource URLs and hashes are in the JSON. **41 station fingerprints have both negative and positive values.** `RL_MSL` is an elevation attribute; it does not establish the sensor/reference datum or export sign convention.

| Resource | Rows | Negative | Zero | Positive | Zero `RL_MSL` |
| --- | ---: | ---: | ---: | ---: | ---: |
| Assam 2021–2025 | 160,859 | 152,135 | 45 | 8,679 | 2,166 |
| Bihar 2021–2025 | 52,998 | 52,520 | 60 | 418 | 0 |
| Assam 2026–2030 | 45,061 | 43,697 | 0 | 1,364 | 677 |
| Bihar 2026–2030 | 16,012 | 15,926 | 0 | 86 | 0 |

All rows have numeric `RL_MSL`; a zero elevation alone is not a proof of error. Against accepted manual records there are 53 common station fingerprints, **16 same-day pairs and no exact timestamp pairs**. Their 9.9740625 m mean absolute raw signed daily difference is a source disagreement diagnostic, not forecast error or evidence validating a sign conversion.

The new official guidance requires fixed measuring points, reference elevation, sensor/cable information, calibration and manual dip checks. It screens negative/zero depths and supplies no blanket sign-flip instruction or station-specific correction logs. No sign flip, elevation subtraction or telemetry integration was performed. Release requires provider-certified variable/sign/units, stable well IDs, installation/reference metadata and correction/maintenance/clock logs, followed by independent overlap checks and station-balanced aggregation.

## Offline verification

`data_ingestion/groundwater_release.py` creates a new ignored candidate only when its output directory does not exist; it verifies immutable input hashes. The focused suite covers date/flag validation, identity and duplicates, conflicts, coordinate/state/boundary quarantine, location-balanced aggregation, source-chain checks and portable metadata paths. **24 tests passed.**

```powershell
.\venv\Scripts\python.exe -B -m pytest tests/test_groundwater_release.py -p no:cacheprovider -q --disable-warnings --basetemp=scratch/pytest-final-groundwater-verified
.\venv\Scripts\python.exe -B -m data_ingestion.groundwater_release --review-output reports/final_release_20261026/groundwater_sources.json
```

Both commands operate on restored local evidence. Acquisition evidence, source raw files, the original NWDP candidate, verified PDF extraction, fixed boundaries and prior feature snapshot must be present for full reproduction; this report alone does not replace them.
