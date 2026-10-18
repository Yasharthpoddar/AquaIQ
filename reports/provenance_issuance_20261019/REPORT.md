# AquaIQ — data provenance and forecast-issuance feasibility

**Investigation date: 2026-10-19. Decision: NO-GO for starting real shadow issuance from the current local data and locked protocol.** The files support historical arithmetic, source-backed monthly values and some location matching. They do not establish the acquisition, panel continuity and point-in-time input provenance needed for a defensible prospective campaign. Real HGB remains `shadow_artifact_not_approved`; no artifact or forecast was created.

Read first: the [scientific audit](C:/Users/Yasharth/Downloads/AquaIQ/reports/scientific_validation_audit_20261018/REPORT.md) and [safe-fixes report](C:/Users/Yasharth/Downloads/AquaIQ/reports/post_audit_safe_fixes_20261019/REPORT.md). Current checkout remains `main`, commit `fc7fdcf20d9f8eb8991dc509b7d581168058de3e`. The three existing modified files (README, ANN comments, OLS reporting) and prior untracked reports/tests were preserved. This investigation only reads local evidence and adds this new directory; no database was accessed, source downloaded, model fitted/selected/invoked, test fixture generated, shadow record issued, commit made or push performed.

**Evidence notation:** **Fact** = observed in local files/code or recomputed here; **Unknown** = not established locally; **Conditional deduction** = follows only under stated timing/input assumptions; **Recommendation** = future action, not implemented or approved here. “Source-backed” does not independently certify a freshly acquired field measurement.

## 1. Source → feature → forecast lineage

The table traces implemented paths and saved outputs. It does not assert that a live database was independently reconciled in this investigation.

| Source / local evidence | Ingestion and aggregation | Feature / serving destination | Provenance retained or lost |
|---|---|---|---|
| Legacy [cgwb_combined.csv](C:/Users/Yasharth/Downloads/AquaIQ/data/raw/cgwb_combined.csv): row ID, reported date, district code, station name/coordinates, basin/sub-basin, `currentlevel` | [ingest_cgwb.py:126](C:/Users/Yasharth/Downloads/AquaIQ/data_ingestion/ingest_cgwb.py:126) replaces the day with month start; :135 averages finite readings across mapped district-months; :180 upserts the monthly scalar. | `raw_data(CGWB,GWL)` → preprocessing → GWL current and exact calendar lags. | Raw row IDs are not established well IDs. Reading frequency supplies implicit weights; `well_count` counts readings. Original row dates, well membership and input vintages do not propagate into production features. |
| [January 2026 PDF](C:/Users/Yasharth/Downloads/AquaIQ/data/raw/updates/20261013/cgwb_january_2026.pdf) and [candidate manifest](C:/Users/Yasharth/Downloads/AquaIQ/reports/candidates/groundwater_updates/20261013/manifest.json) | [cgwb_updates.py:185](C:/Users/Yasharth/Downloads/AquaIQ/data_ingestion/cgwb_updates.py:185): reject invalid/conflicting records, resolve actual locations to fixed district polygons, deduplicate and average unique station-month means. :339 inserts only missing district-months. Saved `applied.json` records 639 inserts. | Adopted January 2026 monthly values are present in the current feature export. | Hash, source page/line, reported dates and station-location proxies retained in candidates; scalar DB/feature rows lack those identities. This station-weighted policy differs from legacy reading weighting. |
| [January 2025 candidate](C:/Users/Yasharth/Downloads/AquaIQ/reports/candidates/station_history_20261015/january_2025_audited/manifest.json) | Local PDF extraction/audit: 15,892 rows, 15,278 accepted, 573 district-months; same station-month aggregation. | Candidate only; not silently merged into active features. | Dataset title supports mbgl/unconfined at dataset level, not per-well logs or replacement histories. |
| [Quarterly manual Gujarat CSV](C:/Users/Yasharth/Downloads/AquaIQ/data/raw/updates/20261013/gwl_manual_quarterly_cgwb_gj_2021_2025.csv) | Saved spatial/source audit accepts 6,244 of 6,704 rows → 298 district-months / 34 districts. | Separate optional research-source features; not an active groundwater replacement. | Metres explicit; below-ground datum not explicit, all `RL_MSL` null. Station/date/location proxies do not certify persistent wells. Filename does not establish 2025 coverage. |
| IMD annual daily grids → [district rainfall CSV](C:/Users/Yasharth/Downloads/AquaIQ/data/processed/imd_rainfall_district_monthly.csv) | [imd_district_climatology.py:80](C:/Users/Yasharth/Downloads/AquaIQ/data_ingestion/imd_district_climatology.py:80): require all daily values for a monthly sum; :157 district usable-cell means with recorded spatial fallback. [ingest_imd_era5.py:136](C:/Users/Yasharth/Downloads/AquaIQ/data_ingestion/ingest_imd_era5.py:136) checks hashes/units, maps state-qualified districts, upserts monthly values. | `raw_data(IMD,rainfall)` → bounded filling → current rainfall, rolling average, prior-year anomaly and water balance. | Source/CSV/boundary hashes, units and spatial metadata exist; provider release, daily accumulation timezone and per-input revision/availability chain do not. Weather corrections can be logged, but this is not a full release-vintage archive. |
| ERA5 monthly NetCDF → [district climate CSV](C:/Users/Yasharth/Downloads/AquaIQ/data/processed/era5_district_monthly.csv) | [era5_to_district.py:59](C:/Users/Yasharth/Downloads/AquaIQ/data_ingestion/era5_to_district.py:59): validate units/accumulation metadata, convert temperature to degC and `pev` to monthly mm once; district usable-cell means → weather ingester. | `raw_data(ERA5,temperature/ET)` → bounded filling → temperature, ET, water balance. | Manifest records source hash, conversion and monthly period; retrieval/publication/revision chronology remains unknown. |
| All active monthly scalars | [pipeline.py:232](C:/Users/Yasharth/Downloads/AquaIQ/preprocessing/pipeline.py:232) reads district/date/source/metric/value; :246 pivots; :278 calendar-filters/reindexes; GWL LOCF ≤3 months and climate LOCF ≤2 months. [features.py:54](C:/Users/Yasharth/Downloads/AquaIQ/preprocessing/features.py:54) creates calendar lags and derived features. | Preprocessed CSV → feature CSV/DB; units and content-derived generation hashes. | GWL `is_observed`, `is_imputed`, age survive. Weather-specific observed/fill flags, well panels, acquisition days and first-availability timestamps do not. A month index and completeness score are not an issuance snapshot. |

**Serving contracts are different.** [predict.py:13](C:/Users/Yasharth/Downloads/AquaIQ/api/routes/predict.py:13) routes the default observed endpoint to [ensemble.py:267](C:/Users/Yasharth/Downloads/AquaIQ/models/ensemble.py:267): latest observed origin, direct twelve-feature XGB, target origin+6, with past targets labelled historical. `next_six_months` reaches [climate_forecast.py:292](C:/Users/Yasharth/Downloads/AquaIQ/models/climate_forecast.py:292): estimated current/lag groundwater, assumed historical same-month weather, separate 1–6-month climate XGB. It is not the locked fourteen-feature direct HGB contract and cannot substitute for that campaign. Sparse serving may use a labelled zone aggregate; that does not establish a fixed district/well target panel.

## 2. Timestamp and provenance inventory

| Field / file family | What is established locally | What remains unknown or must not be inferred |
|---|---|---|
| Legacy `date` and PDF station `observation_date` | Reported source day; normalized later to a month. All 16,605 accepted January 2026 rows report **2026-01-10**; all 15,278 accepted January 2025 rows report **2025-01-10**. | Whether each is fresh physical acquisition versus republication/carry-forward; clock/timezone, first publication and first receipt. Uniform dates are not proof of fabrication or fresh synchronized measurements. |
| Quarterly `Data Acquisition Time` | Provider column parses **2021-01-10–2023-08-30 18:00**, without a timezone. | Independent freshness certification and timezone; publication, receipt and revision chronology. The “2026–2030” companion file contains a header only. |
| PDF manifest `as_of=2026-10-13` | Audit cutoff/process context. Saved monitoring HTML footer also says updated 13/10/2026. | Neither is the PDF's first release, a per-value publication date, or actual model-input availability. No groundwater transport sidecar establishes first retrieval. |
| IMD year/month/day, ERA5 `valid_time` | Weather observation/aggregation-period labels; active IMD through **2025-12**, ERA5 through **2024-12**. | Provider release latency and revision vintages; daily IMD accumulation interval/timezone is not established. Calendar coordinates are not issue times. |
| IMD 2025 `.download.json` `retrieved_at_utc` | Recorded local retrieval **2026-10-13T11:53:54.006177Z**, bound to the staged annual grid's SHA. | Provider first publication or historical 2025/January 2026 availability. Local presence now does not prove prior receipt. |
| ERA5 clean-file history / source manifest | Processing metadata includes a GRIB conversion timestamp; hashes identify retained bytes. | A processing time is not independently authenticated retrieval/publication. Old absolute source paths are not source-release histories. |
| `raw_data.date`, `features.date`, CSV `date` | First-of-month bucket; [schema.sql:29](C:/Users/Yasharth/Downloads/AquaIQ/db/schema.sql:29) stores monthly values, not source event chains. Migration flags add observation/generation metadata. | Acquisition day, provider publication, receipt, revision and well-panel identity are not recoverable from these scalar rows. |
| Model-card `created_at`, scoring-run `completed_at`, report `created_at_utc` | Build/run/report timestamps for those objects. | They do not date every input's first availability or prove a historical forecast was issued before its outcome. |
| Shadow `issued_at` / commit archive time; source and input envelopes | Code requires timezone-aware actual issuance/archive and `observed_at ≤ period_end ≤ published_at ≤ received_at ≤ available_at ≤ issued_at`; panel registration precedes issuance. | Real provider envelopes, independently retained source bytes, registered well panels and trusted external archival timing are absent. No such values were fabricated or records created here. |

**Well identity and datum:** names plus coordinates can support local matching, not certified identity across renaming, relocation, replacements or colocated wells. PDF title checks establish dataset-level mbgl; the legacy `currentlevel` header and quarterly CSV do not independently certify that datum. No per-well measuring-point/ground-datum history, construction/screen/aquifer continuity or replacement register was established. Current weights can be reconstructed arithmetically; a stable hydrological population and scientifically fixed weights cannot. Saved station comparisons show proxy-panel differences, not verified replacement rates.

**Weather freshness caveat:** finite rainfall extends to February 2026 only through December 2025 carry-forward; finite temperature/ET extend to February 2025 only through December 2024 carry-forward. [climate_inputs.py:109](C:/Users/Yasharth/Downloads/AquaIQ/models/climate_inputs.py:109) explicitly warns that weather histories may contain fills when weather-specific flags are absent. Neither endpoint is a new weather observation.

**Staged alternatives do not resolve this:** the latest local rainfall-refresh progress is `overlap_requires_review`; [overlap.json](C:/Users/Yasharth/Downloads/AquaIQ/reports/candidates/rainfall_refresh/2026-01_2026-09/overlap.json) records `verified_overlap=false` on all three sampled annual-versus-provisional dates. Old real-time staging has three isolated 2026 days, no complete month. Product/accumulation/revision compatibility needs provider clarification; these samples are not an adopted current monthly release. No download or replacement was attempted.

## 3. District freshness, recomputed from local exports

[All 725 districts](C:/Users/Yasharth/Downloads/AquaIQ/reports/provenance_issuance_20261019/district_freshness.csv), [monthly input status](C:/Users/Yasharth/Downloads/AquaIQ/reports/provenance_issuance_20261019/monthly_input_status.csv) and [summary](C:/Users/Yasharth/Downloads/AquaIQ/reports/provenance_issuance_20261019/freshness_summary.json) were generated by direct CSV arithmetic, without importing AquaIQ's model/DB modules. “Stale” here describes absence of a source-backed value in the latest completed feature month, September 2026; it is not a newly chosen release threshold.

| Latest source-backed month in active release | Districts | Age in calendar months at October 2026 |
|---|---:|---:|
| January 2026 | 639 | 9 |
| January 2021 | 9 | 69 |
| November 2019 | 2 | 83 |
| November 2018 | 1 | 95 |
| May 2013 | 1 | 161 |
| None in active feature history | 73 | Unknown / unavailable |

**Facts:** 652 districts have source-backed history, all older than September; zero have only-imputed lifetime history; 73 have neither finite GWL nor an observed flag in this release. The 215,325 feature rows contain **36,890 source-backed, 72,110 finite imputed, 106,325 missing GWL values**. At September 2026, **all 725 current GWL values are missing**, with no observed or finite imputed current values. A finite six-month lag remains for 639 districts through an older carried-forward dependency; it is not a current observation.

| Feature month | Observed GWL | Imputed GWL | Missing GWL | Finite current rainfall | Finite temperature / ET |
|---|---:|---:|---:|---:|---:|
| January 2026 | 639 | 0 | 86 | 724, carried from December 2025 | 0 / 0 |
| February 2026 | 0 | 639 | 86 | 724, carried from December 2025 | 0 / 0 |
| March–April 2026, each month | 0 | 639 | 86 | 0 | 0 / 0 |
| May–September 2026, each month | 0 | 0 | 725 | 0 | 0 / 0 |

Active weather CSVs contain 295,392 IMD rows / 724 district-state pairs (1992–2025) and 199,824 ERA5 rows / 724 pairs (2002–2024). Finite rolling rainfall may outlast finite current rainfall because its window accepts partial finite history; it must not be mistaken for complete new rainfall evidence.

**Separate unadopted evidence:** the local January 2025 candidate has source-backed means for five districts with no observed active history: **AR-Kamle, AR-Longding, SK-East_Sikkim, UK-Pithoragarh, UK-Rudraprayag**. It also contains later candidate months for four of the thirteen older active districts: Dadra and Nagar Haveli, Daman, Diu and Rampur. The optional quarterly candidate adds no district outside active observed-history coverage. [Candidate coverage](C:/Users/Yasharth/Downloads/AquaIQ/reports/provenance_issuance_20261019/candidate_coverage.json) keeps these distinctions explicit. No candidate was adopted or combined. “Missing in the active release” does not mean a district was never measured.

## 4. Input-month dependencies and issuance timeline

Let **M** be the origin month, **I** the actual archive/issuance time, **T** the earliest target acquisition. The locked direct target is exactly **M+6**; its exact seasonal reference is **M−6**, i.e. target−12. The following dependencies cannot be replaced merely to obtain a longer lead.

| Direct input | Calendar dependency | Availability implication |
|---|---|---|
| GWL current / 3-month / 6-month lag | M / M−3 / M−6 | GWL features can carry an earlier reading forward ≤3 months. Thus lag source evidence can be as old as M−6 or M−9; true acquisition age and vintage must remain visible. |
| Rainfall current / 3-month average | M / buckets M−2…M | Climate carry-forward ≤2 months; rolling mean permits fewer than three finite buckets. A complete nonmissing origin-month observation cannot be available before its accumulation period finishes. |
| Rainfall deficit | M rainfall plus prior-year same-calendar expanding normal, minimum three years | All contributing historical releases/revisions must have been available by I, not merely have earlier observation-year labels. |
| Temperature, ET, water balance | M means/totals; balance = M rainfall−M ET | Availability is bounded by completion and the latest actual dependency's release/receipt/processing. |
| Crop indicators, month sine/cosine | Origin calendar | Known before issuance; not the blocking dependency. |
| Persistence / seasonal naive | Observed M / observed exact M−6 | Must be available at I; missing or unobserved references abstain. Fills cannot silently become observed baselines. |

**Conditional timing deduction:** with complete origin-month weather received/processed after month end, let `S(M)` denote the start of month M. Then:

```text
origin observations and complete weather during M
    → origin month closes
    → provider release → local receipt → validation/feature processing → I
    → acquisition T within the unchanged target month M+6

If I ≥ S(M+1), then T < S(M+7) ≤ I + six calendar months.
```

Therefore **post-origin-month issuance using complete origin-month weather cannot deliver six full calendar months of lead to an acquisition within M+6**. The publication/receipt delays are unknown, so the actual shorter lead cannot be quantified. Exact calendar bucket spacing remains correct; it is not an operational lead guarantee. The ledger classifies actual acquisition versus archive time separately ([shadow_ledger.py:514](C:/Users/Yasharth/Downloads/AquaIQ/models/shadow_ledger.py:514)).

**Qualification, not a workaround:** HGB natively accepts missing numerical inputs and the ledger permits explicitly absent values. This is not a proof that every conceivable missing-weather information regime is mathematically impossible. Deliberately blanking not-yet-available weather, selecting an earlier issuance/missingness policy, or changing target/feature definitions would need explicit human approval and preregistration; none was done. A formal zero-latency final-second release chain permitted by timestamp granularity is not an evidenced realistic operating schedule.

**Existing local January 2026 case:** source-reported GWL day is January 10; origin bucket is January; nominal target is July 2026. January features have no finite GWL 3/6-month lags, temperature or ET, and rainfall is a December carry-forward. There is no observed July 2025 reference. The July target is already past on October 19; a forecast issued now cannot retrospectively create prospective evidence. This is a calendar/input assessment, not a forecast or model invocation.

The API's completed-month selection is a date heuristic: it admits a month on its last calendar day ([ensemble.py:33](C:/Users/Yasharth/Downloads/AquaIQ/models/ensemble.py:33)), without proving intraday completion or provider release. It cannot supply missing point-in-time provenance. The monthly serving alternative estimates anchors and future weather assumptions; its future graph does not repair the direct contract's lead or measurement gaps.

## 5. Baselines and prospective eligibility

**Numerical references versus availability:** persistence can be read from each of the 652 districts' latest observed active origins. Only **one** latest origin has an exact observed M−6 seasonal reference: Imphal East, origin May 2013, target November 2013. For the 639 January 2026 origins, the observed July 2025 seasonal-reference count is **zero**. All 652 latest observed origins' nominal targets are already past. These are calendar joins, not proof that the values had been published/received before a historical issuance.

The direct protocol requires exact target−12; the monthly-climate historical evaluator instead selects its latest available same-calendar-month observation, potentially older than one year. Those baseline definitions are not interchangeable. The locally retained monitoring page describes seasonal rounds; January→July does not have the routine six-month counterpart supplied by May↔November. This does not prove July observations are unavailable from every provider/network; they are absent from the relevant active local years.

Eligible prospective evaluation additionally requires newly acquired target readings after I, verified datum/units, the complete preregistered well panel and both pre-issuance baseline references, with all missing labels/abstentions reported. Later historical backfills or revisions cannot be treated as observations first acquired after I. No independent prospective outcome cohort was established here. Although the ledger can retain baseline-only abstention records, that cannot create an eligible three-way HGB comparison or cure today's provenance gaps.

## 6. Existing evidence versus missing prerequisites

| Can be established from existing files now | Requires provider documentation, genuinely new evidence or explicit approval |
|---|---|
| Exact calendar joins, feature order, bounded fill rules, model/config/source hashes and research lock. | A defensible issuance-time availability envelope for every actual dependency, including weather vintages, processing latency and provider acquisition semantics/timezones. |
| Reported dates, dataset-level PDF mbgl checks, location proxies, arithmetic aggregation and district coverage. | Stable provider well IDs, replacement/relocation and datum/measuring-point continuity; fresh-versus-republished flags; reviewed aggregation and panels/weights fixed before outcomes. |
| Certain recorded retrieval times and retained source bytes. | Authenticated receipt/version archive for future inputs, source release/revision semantics, and complete provenance adapters. Current ledger requires a real `published_at`; copying retrieval into that unknown field is prohibited. |
| Code support for timezone-aware issuance, availability rejection, immutable versions, missing baselines and lead classification. | Trusted clock/archive, registered panel/campaign, approved frozen HGB artifact and later separately reviewed inference adapter. HGB abstention remains mandatory. |
| Source-backed historical origins and limited seasonal reference coverage. | Current observed origins, required histories/references and subsequently acquired target labels on stable panels. Without recoverable verified history, a seasonal-reference→origin→target chain spans about twelve months of observations; provider latency and sampling add uncertainty. |

For prospective no-lookahead evidence, a demonstrably retained source receipt before issue can establish availability even if first publication is unknown. **That does not permit inventing publication times to satisfy the present ledger.** If providers cannot supply release timestamps, accepting a different provenance contract would require separate explicit review/approval, not a change in this investigation.

**Human protocol decision required:** choose whether the intended claim is the existing **nominal origin+6 month with its honestly measured shorter effective lead**, or **at least six full months from actual issuance to target acquisition**. The latter conflicts with post-month issuance using complete origin-month weather; it needs separately approved protocol work. Neither target, features nor missingness policy was changed. Even the nominal option remains no-go today because data age, panel/timestamp provenance, baseline eligibility and approved HGB artifact prerequisites are unmet.

## Verification and preservation

Only new report/evidence files were created here. Freshness/reference counts were recomputed directly with pandas/NumPy; source/metadata were inspected without calling ingestion, serving or ledger APIs. No tests were run in this investigation, because no implementation was changed and shadow tests can create synthetic records. Prior reports' test results are historical evidence, not new execution claims.

[before.json](C:/Users/Yasharth/Downloads/AquaIQ/reports/provenance_issuance_20261019/before.json) fingerprints 635 pre-existing tracked/data/checkpoint/report files. [Additional source snapshot](C:/Users/Yasharth/Downloads/AquaIQ/reports/provenance_issuance_20261019/additional_untracked_source_before.json) fingerprints the two pre-existing untracked test files. [Preservation verification](C:/Users/Yasharth/Downloads/AquaIQ/reports/provenance_issuance_20261019/preservation.json) checks all **637** without permitted source changes, active bundle identity and unchanged pre-existing Git status. No previously completed evidence was replaced.

**Single highest-priority dependency:** obtain a **provider-backed acquisition and first-availability/release timing specification for the intended groundwater and monthly-weather products**. It must distinguish acquisition from republication, define periods/timezones and release/revision timing, and support an honest issue/target schedule. Use that evidence for the explicit human horizon-contract decision before any artifact creation or real shadow issuance.
