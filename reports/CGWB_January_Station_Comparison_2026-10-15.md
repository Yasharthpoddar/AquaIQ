# CGWB January station evidence comparison - 15 October 2026

## Verified official source and extraction

The CGWB groundwater monitoring page links the historical January archive:
https://cgwb.gov.in/wl_data/January_WL_1994-2025.pdf

The downloaded archive contains 10,574 pages and is 38,514,524 bytes. Its SHA256
is `6ebb9cbf401c3fb7aca65c31b421ccf586c6fadbce5abb4d2a222e538b0534cd`.
The project raw-source location is
`data/raw/updates/20261015/cgwb/January_WL_1994-2025.pdf`; the PDF belongs in
ignored local source storage, not Git.
Actual table dates on pages 1-332 identify January 2025, independently of the
filename. The following page, 333, begins January 2024. Representative first,
intermediate and final sections were checked by text extraction; pages 1 and 85
were rendered and visually inspected.

The selected section title is **January month Depth to Water Level (In mbgl)
Data of Unconfined Aquifer**. The verified eight-column layout provides state,
district, block, village, latitude, longitude, actual date and depth. The archive
misspells the latitude header as `Latitute`; the parser matches the inspected
header rather than silently assuming a layout. Source dates such as `10-01-25`
are retained and expanded explicitly to January 2025, never inferred from a
filename. Unfamiliar layouts, units, dates or section boundaries fail closed.

`data_ingestion.cgwb_historical_january` extracted **15,892 source rows**. The
existing canonical-boundary audit accepted **15,278** and rejected **614**,
producing **573 candidate canonical district-month averages**. Rejection reason
counts overlap: 271 identical duplicate readings, 174 conflicting station/date
depths, 105 source-state/boundary disagreements and 65 unresolved canonical
district locations. No nearest-district fallback is used.

Dataset-level aquifer wording is preserved in `source_dataset_aquifer` and the
manifest. It is not populated into a per-well `aquifer` field. The January 2026
PDF title actually contains the misspelling `unconfindent`; its source text is
not silently treated as a verified well-specific aquifer description. Neither
dataset supplies independent well construction logs or globally unique well IDs.

## Candidate comparison results

The January 2026 source and previously imported district aggregates are
unchanged: the original audit contains 16,952 source rows, of which 16,605 were
accepted for the original ingestion. For this separate diagnostic, stricter matching requires nonempty
state/block/village names, valid coordinates rounded to five decimals, accepted
source audit, consistent units and actual observation dates. This retains
**14,548 January 2026 location fingerprints**, compared with the prior ingestion
acceptance of 16,605 source rows. The difference is a comparison eligibility
rule, not a deletion or correction of production data.

The tool found **9,543 exact location matches across 554 canonical districts**.
Overlap is 62.46% of eligible January 2025 locations and 65.60% of eligible
January 2026 locations. Known canonical district or well-specific metadata
disagreements are excluded. Matching uses no nearest-neighbor snapping and does
not assert a verified globally unique well identity.

The Gandhinagar example demonstrates why changed monitoring coverage matters:

| Diagnostic | Gandhinagar |
| --- | ---: |
| Eligible locations in January 2025 | 6 |
| Eligible locations in January 2026 | 6 |
| Exact location matches | 3 |
| Mean depth change among those three matched locations | -1.8267 m |
| Change in the mean of all six locations in each year | +19.4550 m |
| Monitoring-network composition changed | Yes |

A positive depth change means a deeper water table. Different sets of six
locations can therefore show a different direction from their three common
locations. The paired statistic applies only to the matched sample. It does not
establish district-wide recovery, a long-term trend, a causal effect or identical
aquifer/well-construction continuity. Sampling dates, source quality and local
conditions still need scientific review.

## Artifacts and production status

Candidate files are under `reports/candidates/station_history_20261015/`:

- `january_2025_verified/station_records.csv` and `extraction_manifest.json`.
- `january_2025_audited/station_audit.csv`, source/rejection CSVs,
  canonical district-month candidate CSV and hashed audit manifest.
- `location_comparison.json`: complete source fingerprints, eligibility counts,
  matched-location versus changing-network summaries and district diagnostics.
- `matched_locations.csv`: the 9,543 source-date/location pairs.
- `source_page_1.png` and `source_page_85.png`: inspected source renderings.

The earlier `january_2025_extracted` scratch directory was an intermediate
metadata representation and is not the final candidate. Use
`january_2025_verified` and `january_2025_audited` only. Dataset-level aquifer
wording was explicitly separated from well-specific fields in the final version.

No January 2025 candidate has been ingested, and no source dataset, feature
artifact, active model, crisis score or database table has been replaced.
Persistent station-history tables and production station-aware trend calculations
remain future implementation work. Independent crisis labels and prospective
score validation remain absent; this station comparison is not score calibration.

All **63** targeted station, archive-parser and crisis-label validation tests
passed. They cover chronology, metadata/identity conflicts, duplicate readings,
actual source dates, output protection and independent-label requirements.
