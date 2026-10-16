# Comparable station evidence and independent crisis-label validation

These offline tools prepare and evaluate candidate evidence. They do not write
the database, retrain models, change score weights, or publish production data.

## Comparable station snapshots

`data_ingestion.station_comparability` accepts two or more CGWB-style station
CSVs from distinct observation months. It retains the existing audit exclusions,
dates, units, source digests, canonical district IDs and optional `aquifer` and
source `station_id` fields. The current `station_audit.csv` schema is supported.
Raw `station_records.csv` is also accepted after structural validation; it does
not acquire a canonical district mapping by being compared.

Matches require identical normalized state, block and village names and
coordinates rounded to five decimal places. District names do not identify a
well and are excluded from the fingerprint. There is no nearest-well snapping or
inferred global well ID. Conflicting same-date readings, source-audit rejections,
ambiguous well IDs, metadata conflicts, future dates, inconsistent audited/source
dates and unsupported units are excluded. When both snapshots carry aquifer or
source station IDs, those fields must agree. One-sided metadata is insufficient
for a comparable pair.

Each month averages repeated readings within each retained location first. The
report then separates matched-location depth changes from changes in the mean of
the entire monitoring network, with station counts, overlap fractions,
composition flags and canonical-district summaries. A positive change means a
deeper water table. Different calendar months include seasonality. Even exact
location matches do not establish unchanged well construction or aquifer when
those fields are missing. These reports do not assert groundwater recovery or
estimate a causal or long-term trend.

From the project root, with independently verified second and subsequent
snapshots:

```powershell
.\venv\Scripts\python.exe -m data_ingestion.station_comparability `
  --snapshots reports/candidates/station_history_20261015/january_2025_audited/station_audit.csv `
              reports/candidates/groundwater_updates/20261013/station_audit.csv `
  --as-of 2026-10-15 `
  --output reports/candidates/station_comparability_20261015/report.json `
  --matched-output reports/candidates/station_comparability_20261015/matched.csv
```

The January 2025 archive section has now been extracted and audited as a local
candidate. See `CGWB_January_Station_Comparison_2026-10-15.md` for source hashes,
actual extraction and matched-location results. Neither snapshot supplies a
verified globally unique well ID or well-specific aquifer log. No persistent
station database or production station-history migration is implemented here.

Omitting inputs prints an offline requirements plan. Output files must be new
and under this checkout's `reports/candidates` or `data/raw/updates` directories.

## Independent crisis-label diagnostics

`models.crisis_validation` requires two CSVs and a canonical geography version.

Score columns:

```text
district_id,score,tier,evidence_as_of,published_at,target_date,
model_version,scoring_signature,evidence_kind
```

Independent evidence columns:

```text
district_id,target_date,label,assessed_at,available_at,source_url,
source_sha256,evidence_id,label_definition,mapping_provenance,
independent_of_aquaiq,derivation_method,geography_version
```

Dates must be explicit valid `YYYY-MM-DD` values. Each dataset must be unique by
district and target date. Chronology is enforced:

```text
score evidence_as_of <= published_at <= target_date
outcome target_date <= assessed_at <= available_at <= evaluation cutoff
```

Only exact district/target dates are joined, with no nearest-month substitution.
`evidence_kind` must identify `district` or `zone_fallback` evidence; results are
reported separately. Scores must be integers between 0 and 100, with the current
documented tier boundaries 30/60/80. Model and scoring identities are required.

Labels must explicitly declare independence, provide an HTTPS source URL and
SHA256 digest, and use `independent_external_assessment` or
`independently_adjudicated_field_assessment` as their derivation method. Labels
made from AquaIQ depth thresholds, fuzzy rules, predictions, simulations or
scores cannot be supplied as independent assessments. The four tiers must have
an externally justified documented mapping; CGWB Safe/Semi-critical/Critical/
Over-exploited categories must not be silently equated to AquaIQ tiers.

These are provenance attestations, not automatic proof of scientific
independence. Human review of source definitions and mapping remains necessary.

```powershell
.\venv\Scripts\python.exe -m models.crisis_validation `
  --scores reports/candidates/crisis_validation/archived_scores.csv `
  --evidence reports/candidates/crisis_validation/independent_labels.csv `
  --geography-version CANONICAL_BOUNDARY_SHA256 `
  --as-of 2026-10-15 `
  --output reports/candidates/crisis_validation/evaluation.json
```

The command reports a confusion matrix, exact agreement, within-one-tier
agreement, tier-distance error, per-tier precision/recall, unmatched counts and
district/zone breakdowns. It never converts the score to a probability, changes
weights or claims calibration. Supplied-case agreement does not establish
representative national accuracy. No real independent outcome CSV is currently
included in this implementation.

Without score/evidence files the command emits a readiness report and exits 2:

```powershell
.\venv\Scripts\python.exe -m models.crisis_validation `
  --output reports/candidates/crisis_validation/readiness.json
```

The current historical score publication can occur after its six-month target.
Such scores cannot be retrospectively relabeled as prospectively issued
predictions. A compatible archived score and independent later outcome are
needed for the prospective validation contract.

## Verification

63 targeted tests passed for the archive parser, duplicate/conflicting station identities, matched
versus changing-network summaries, dates and source provenance, absent aquifer
metadata, exact target joins, future/retrospective leakage, independent label
requirements, duplicate outcomes, candidate-output protection and offline modes.
Test fixtures are synthetic and never exported as real validation evidence.
