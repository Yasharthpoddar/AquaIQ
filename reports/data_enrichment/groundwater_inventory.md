# Official groundwater source inventory, 26 October 2026

The primary enrichment uses **quarterly manual CGWB records actually downloaded from NWDP**, rather than dates advertised by a portal. The fixed project registry and mixed-vintage boundary artifact remain the geographic reference. Production tables, legacy raw files, and existing genuine district-month aggregates are preserved.

## Acquired and processed sources

| Source | Acquired bytes / rows | Actual observations | Processing and decision |
|---|---:|---|---|
| [NWDP CGWB quarterly manual](https://nwdp.nwic.gov.in/dataset/gwl-manual-quarterly-central-ground-water-board-department), advertised 2021–2025 | 31 CSV files; 171,107 rows | 2021-01-01 through 2025-01-30; substantial differences by state | 156,176 source timestamps accepted; 14,931 rows quarantined. 6,513 district-month candidates across 641 districts. The feature overlay fills 5,952 previously unobserved district-months in 639 districts, including 11 with no earlier local observed month. |
| Same manual dataset, advertised 2026–2030 | 31 CSV files, 243 bytes each | **Zero observations**, header only | Downloaded and parsed, contributes no measured data. Together the 62 manual files total 22,812,707 bytes. |
| [NWDP CGWB telemetry](https://nwdp.nwic.gov.in/en/dataset/ground-water-level-telemetry-hourly-central-ground-water-board-cgwb), Assam and Bihar | Four CSV files; 33,020,518 bytes; 274,930 rows / 91 exact location fingerprints | 2023-03-02 through 2026-10-23 | Separate sign, cadence and overlap review; **not integrated** into manual targets. |

Exact resource URLs, source modification dates, actual date spans, sizes, SHA-256 checksums, licensing fields and independent discovery/access/download/parse/integration/validation status are in [the machine-readable catalog](../../data_sources/nwdp_resources.json). Status `validated` for manual files means source integrity and mechanical audit checks; it does not certify a physical well's construction, datum or future forecast accuracy. `integrated` means accepted source rows contribute to missing district-months in the isolated candidate feature generation.

NWDP declares **Other (Open)** and supplies no specific license URL in the dataset metadata. Attribute **Central Ground Water Board (CGWB), National Water Informatics Centre (NWIC), Ministry of Jal Shakti**. Raw source files remain ignored and are not redistributed in Git. [CGWB's monitoring description](https://www.cgwb.gov.in/ground-water-level-monitoring) establishes the depth-below-ground convention. The manual CSV has a separate `RL_MSL` field; that field is never substituted for depth. CRS is geographic latitude/longitude, EPSG:4326. The provider supplies station labels rather than certified globally unique well IDs.

## Conservative audit and before/after coverage

The parser requires the exact inspected 21-column manual CSV schema and acquisition time format `DD-MM-YYYY HH:MM`, verifies immutable input SHA-256, and retains source file, resource ID, URL, physical CSV row, timestamp and original provider fields. It never manufactures observation dates from filenames.

Station fingerprints use exact case/whitespace-normalized station label and state with coordinates rounded to five decimal places. District labels are excluded from identity to allow administrative renaming; suffixes, punctuation and similar names are not fuzzily merged. Differently named stations sharing a coordinate within a month are all quarantined rather than presumed identical or double weighted. Exact station/timestamp duplicates contribute once; conflicting depths are excluded. Comparison with the older raw source uses **station-day** precision because that source has no acquisition times.

Coordinates must intersect exactly one named canonical district polygon and agree with the source state. Points within **0.001 degree** of its dissolved district boundary are quarantined; this is an explicit conservative margin (approximately 95–111 m in India), not an assertion about GPS accuracy. There is no snapping or nearest-district fallback. The boundary SHA-256 is `e724c14bc5ee68bcdd6cee8c89222b80cb61e180e55c1dab3d067f09b3b9dc8f`; mixed boundary vintages and historical Telangana attribution remain limitations.

Nonfinite measurements, negatives, values over 300 m, missing station labels, unfamiliar agencies, and named springs are retained in rejection evidence. The upper limit is a **review quarantine**, not a learned threshold or assertion that deep or artesian measurements are impossible. It does not silently correct a decimal or reverse a sign. Accepted timestamps first form station-month means; district-month depths then give each station equal weight. Provenance remains available through the accepted rows and station-month table. Existing genuine district-month aggregates take precedence over the new candidates.

| Comparable source statistic | Existing raw | Existing raw + accepted NWDP |
|---|---:|---:|
| Exact location fingerprints | 52,304 | 58,527 |
| Distinct station-days | 1,470,970 | 1,627,123 |
| Distinct station-day-depth records | 1,513,938 | 1,670,094 |
| Last observation date | 2023-03-31 | 2025-01-30 |

For this comparison, old raw records require a finite nonnegative depth, valid India coordinates and a valid date. It does not independently certify old spatial attribution. Accepted new data add **6,223** fingerprints and **156,153** distinct station-days; the 156,176 accepted source timestamps collapse to 156,156 new station-day-depth records. Fingerprints are matching aids, so these are not claims of independently verified new physical wells. The deployed baseline already includes January 2026 from a separate CGWB refresh; these historical additions do not imply fresher observations for every current district.

Principal quarantine reason counts are 10,173 colocated-label ambiguities, 1,873 source-state/boundary disagreements, 1,161 nonfinite depths, 778 near-boundary coordinates, 755 unresolved district coordinates, 334 negative depths, 62 conflicting station timestamps, 29 conflicts with old raw readings, 11 depths over 300 m, eight exact old-raw matches, five spring records and four exact duplicate timestamps. Reasons can overlap and must not be summed as mutually exclusive counts. [Groundwater source evidence](groundwater_sources.json) and the local hashed station audits provide the complete counts and state/district coverage.

## Telemetry review and other checked candidates

Telemetry includes 264,278 negative values, 105 zeros and 10,547 positive values in provider metres. Six-hour intervals account for 269,150 consecutive station intervals; other gaps are recorded in [the telemetry audit](telemetry_review.json). There are 55 exact manual/telemetry fingerprint overlaps but only 17 same-station/day comparisons in the checked manual archive. The 9.6168 m mean absolute **signed source difference** is an exploratory source comparison across all parsed manual rows, not a forecast error, validated calibration, or permission to flip the telemetry sign. Individual well reference datum, sign convention, aquifer and construction continuity need verification before pooling these products. The parser labels telemetry units as `m_provider_sign_unverified`, and the manual auditor rejects that product.

[CGWB archives](https://cgwb.gov.in/en/ground-water-level-monitoring) were inspected as a complementary source. The previously acquired January 1994–2025 PDF and its inspected January 2025 section are already available locally from the earlier project audit. They are not represented as new downloads in this run and are not pooled with NWDP: the two products have no certified common well IDs, and mixing overlapping station aggregates could duplicate evidence. The primary experiment uses the reproducible NWDP manual source alone.

[GSDA's National Hydrology Project page](https://gsda.maharashtra.gov.in/en-national-hydrology-project-2/) describes its monitoring recorders linked to WIMS. The [NWDP Maharashtra GW telemetry dataset](https://nwdp.nwic.gov.in/dataset/ground-water-level-telemetry-daily-maharashtra-gw) and its public metadata API were checked. Metadata advertises two files of 529,251,877 and 144,733,521 bytes, but its author/maintainer fields incorrectly say **Madhya Pradesh GW** while the title says Maharashtra. Only metadata was acquired; the two large resource bodies were **not checked or downloaded**, not declared unavailable. Exact advertised URLs and this distinction are recorded in the catalog. Resolve provenance and datum conventions before attempting an additional integration.

## Reproduction

From the repository root, with the documented project environment installed:

```powershell
# Explicit acquisition only; cached files and hashes are checked, never overwritten.
.\venv\Scripts\python.exe -B -m data_ingestion.nwdp_manual --acquire data/raw/official_enrichment/nwdp_20261026

# Choose a fresh output directory; do not overwrite the release candidate.
.\venv\Scripts\python.exe -B -m data_ingestion.nwdp_manual --acquisition-manifest data/raw/official_enrichment/nwdp_20261026/manual_acquisition.json --output-dir reports/candidates/groundwater_updates/enrichment_20261026/nwdp_manual_replay01 --as-of 2026-10-26

# Separate telemetry source audit, no sign reversal or manual pooling.
.\venv\Scripts\python.exe -B -m data_ingestion.nwdp_manual --acquire-telemetry-review data/raw/official_enrichment/nwdp_20261026
.\venv\Scripts\python.exe -B scripts/audit_nwdp_sources.py --candidate-dir reports/candidates/groundwater_updates/enrichment_20261026/nwdp_manual_replay01 --output-dir reports/data_enrichment/replayed_source_audit

.\venv\Scripts\python.exe -B -m pytest -q tests/test_nwdp_manual.py
```

Input acquisition is separate from ordinary application requests. Network timeouts, bounded retries, explicit sizes, atomic create-only output and source checksums are enforced. Ordinary parser/audit runs are offline; inaccessible optional resources do not initiate retraining or delete a published generation. A fresh clone must first obtain the ignored legacy raw/processed baseline and boundary assets described in the project setup; the source acquisition commands alone do not reconstruct those earlier assets. Candidate feature generation, comparable forecast evaluation and safe publication are documented in the main enrichment report.
