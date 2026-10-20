# Actual forecast-validation investigation — 19 October 2026

**Result: new official data acquired and historical fits executed; no ML improvement over seasonal naive established.** On the new paired regional cohort, seasonal-naive RMSE is **1.440 m**, expanding XGBoost **1.472 m**, and persistence **3.733 m**. These are **conditional, current-vintage historical results**, not validated operational accuracy: the new source has serious location inconsistencies, and historical input availability cannot be certified. Genuine prospective performance remains unmeasured. Real shadow issuance remains **NO-GO**; HGB's real-serving abstention is unchanged.

Starting state: `main`, commit `905f3c32304fa196015b8cd3113ec77f6b0a7d84`; 11 presentation/documentation edits and the submission-finalization directory already existed. Those user changes were preserved. Read first: the [scientific audit](../scientific_validation_audit_20261018/REPORT.md), [safe fixes](../post_audit_safe_fixes_20261019/REPORT.md), [provenance investigation](../provenance_issuance_20261019/REPORT.md), and [submission finalization](../submission_finalization_20261019/FINALIZATION.md). Prior completed analyses were used as context; the new source justified new fits and evaluation.

## 1. Data actually acquired

The selected source is the [official Telangana monthly groundwater dataset](https://nwdp.nwic.gov.in/dataset/ground-water-level-manual-monthly-telangana-ground-water-department), published through NWIC by Telangana's groundwater agency. It was selected for its explicit **provider Well ID**, **Water Level in mbgl**, monthly history, well depth/type and aquifer metadata, before computing forecast errors.

- Full retained CSV: **25,564,190 bytes; 188,877 rows; 1,769 provider IDs**, reported dates **2007-05-01–2026-05-01**. SHA-256: `f8222245721c421bc2f82b6afbd387ee5cd0e263790515ac7d3ffcce0c521302`.
- Additional small acquisitions: Telangana metadata and ten-row API sample; CGWB manual/telemetry catalog metadata; Uttar Pradesh telemetry metadata and five-row sample; NWIC reuse policy. The much larger telemetry datasets were not downloaded. No new IMD/ERA5 download was needed for the initial period.
- Raw responses remain immutable under `acquired/`; strict `cp1252` decoding was recorded after UTF-8 decoding failed. No production data was merged or replaced by the research workflow.
- Catalog license: **Other (Open)**. Source acknowledgement: Telangana Ground Water Department / National Water Informatics Centre. The retained [NWIC copyright policy](https://nwdp.nwic.gov.in/footer/copyrightPolicy) permits accurate reproduction with attribution, subject to explicit third-party exceptions. This is not a claim of a different standard license.

[Acquisition manifest](source_manifest.json) records exact URLs, actual retrieval timestamps, hashes and catalog information. A response's HTTP date or catalog modification time is not a per-observation release/acquisition time. API samples are partial datasets even though their complete JSON responses were retained.

## 2. Compatibility and important source defects

The corrected adapter accepts **188,458 records, 1,764 IDs and 7,555 district-months** in the fixed 33-district Telangana geography. It excludes 345 out-of-state spatial assignments, 42 records in conflicting well-month metadata groups, 27 nonnumeric/missing depths, and five negative depths. Negative mbgl may represent artesian conditions; exclusion preserves the existing nonnegative model contract rather than proving those readings erroneous. All exclusions are retained, with reasons.

Each accepted well-month supplies one equally weighted reading, so the district arithmetic mean follows the existing reading-mean definition without duplicate telemetry weighting. Groundwater LOCF remains bounded to three months; target/reference labels never use fills. Existing verified district-weather columns and their missingness are copied by exact key, with no new weather assumptions, normalization or feature changes. The initial 12-feature direct definition and origin+6 calendar target are preserved. This is a **new provider/population**, not the original CGWB cohort or the monthly serving model.

The geographic defect is substantial: **125,400 accepted rows with resolvable source names disagree with the fixed polygon containing their coordinates**, while 58,034 have unresolved source names. Only 5,024 accepted rows have exact name/polygon agreement. For example, source ID1087 names Hyderabad/S.R.Nagar but coordinates `18.4223,78.45427` map to Kamareddy. Every primary district case includes a name/coordinate disagreement in its origin or target panel; the mean target-panel disagreement share is **65.9%**. Geometry checks work for independent reference coordinates; no authoritative correction to the provider's well-location mapping was available. Consequently the district labels **and weather assignment are uncertain**. The table below preserves the protocol's coordinate-based arithmetic but cannot establish trustworthy location-specific AquaIQ skill.

Further limitations: ID20220673 has overlapping coordinate/depth identities; only conflicted months are rejected, avoiding exclusion of past rows based on later metadata. There are 1,077 raw readings exceeding listed well depth, 17 coordinate pairs shared by different IDs, mixed unconfined/semi-confined/confined wells, and repeated monthly readings. These are disclosed rather than removed because of prediction errors. Provider IDs improve traceability but do not certify replacements, measuring-point continuity or fresh acquisition. Reported days include 1, 18 and 19; they are not assumed to be actual acquisition days. See [source QC](well_baselines/data_quality_notes.json), [adapter QC](normalized_v2/quality.json), and [mapping/panel diagnostics](diagnostics_v2/panel_and_mapping_summary.json).

## 3. Frozen historical protocol and actual fitting

[Protocol](protocol.json), SHA-256 `06af4e6aab2e7d71ab573ecc6196fad7c5cbc9b825243c9d1aa624ce4193ce45`, was frozen after source/schema inspection and **before fitting or scoring**. No hyperparameter search, model reselection, early stopping on the test cohort, or active-configuration change occurred.

| Evaluation | Cases / districts | Origin months | Target months | Meaning |
|---|---|---|---|---|
| Primary common and native cohorts | **594 / 33**; 1,711 IDs across origin/target panels | 2023-07–2024-12 | **2024-01–2025-06**, 18 months | All 12 features finite; all six methods share every case. Native cohort is identical, not replication. |
| Later native cohort | **363 / 33**; 1,763 IDs across origin/target panels | 2025-01–2025-11 | **2025-07–2026-05**, 11 months | Existing weather becomes missing; preserve native missingness and report separately. |

Primary dates were chosen because origins remain within ERA5 coverage through December 2024 and targets are later than the old primary ending March 2023. All **957 registered district-month slots** have observed source-backed origin, target and exact seasonal references after aggregation; none were removed for large errors. Individual missing well labels remain visible in the separate well analysis. “Observed” here means provider-reported manual measurements, not independently certified fresh field acquisition.

For target year Y, expanding fits use only observed training labels through **December 31 of Y−2**; evaluation origins start no earlier than July of Y−1. This imposes six complete embargo months. Actual pooled training sizes were **6,004 / 6,400 / 6,796** for target years 2024/2025/2026. Training origins may use the existing bounded causal fill; evaluation origins and both references must be observed. Persistence is M; seasonal naive is the **exact observed M−6 = target−12**, never a nearest seasonal round.

- **Expanding XGBoost:** existing 12-feature absolute-depth approach, fixed 500 trees, depth6, learning rate .01, subsample .8, seed42. New annual fits use this provider's eligible historical district means, not a promoted production model.
- **Expanding OLS:** existing per-district, complete-case LinearRegression approach; at least 12 eligible training rows. No learned imputation/scaling. All primary cases supported; **297/363 later cases abstain for missing inputs**, so OLS is not compared on a more favorable secondary subset.
- **Frozen active XGB:** existing 2019-cutoff checkpoint loaded read-only to measure source transfer; no refit.
- **Locked HGB:** historical-only reconstruction on the original **14,817 observed-origin/observed-target pairs**, cutoff **2018-12-31**, exact existing lock/settings/14 features/delta target. Its research binary is explicitly **HISTORICAL_ONLY**, not an approved shadow artifact. This reconstruction was justified by the new source comparison and did not change real HGB abstention.

All research models are under `evaluation_v2/historical_models/`; no active pointer/card was rewritten. ANN/fuzzy-label classification was not misused as depth regression. Raw OLS/XGB evaluation outputs retain their existing evaluation semantics; HGB retains its locked nonnegative reconstruction.

## 4. Results on identical cases

**Primary conditional district comparison; metres, bias = prediction−observation.** R² is not an accuracy percentage.

| Method | MAE | RMSE | Bias | R² | Absolute-error p95 / max |
|---|---:|---:|---:|---:|---:|
| Persistence | 3.359 | 3.733 | −1.144 | −1.186 | 5.766 / 7.377 |
| **Seasonal naive** | **1.160** | **1.440** | −.663 | .675 | 2.694 / 4.707 |
| Expanding XGBoost | 1.205 | 1.472 | −.434 | .660 | 2.764 / 4.644 |
| Expanding per-district OLS | 1.400 | 1.752 | −.398 | .519 | 3.524 / 5.199 |
| Frozen active XGBoost | 1.503 | 1.799 | −.903 | .493 | 3.310 / 5.800 |
| Locked historical HGB | 1.496 | 1.790 | −.285 | .498 | 3.298 / 4.632 |

All ML methods beat persistence on these conditional aggregates; **none beats seasonal naive on pooled MAE or RMSE**. Expanding XGB minus seasonal RMSE is +.032 m. Its paired 95% district interval is **[−.054,+.115] m**; crossing district resampling with six-month moving blocks gives **[−.237,+.420] m**. Versus persistence the latter interval is **[−2.517,−2.020] m**. These 2,000-resample, seed42 intervals are descriptive: 18 target months, spatial dependence and uncertain labels/locations prevent confirmatory claims.

| Primary RMSE weighting | Persistence | Seasonal | Expanding XGB | Historical HGB |
|---|---:|---:|---:|---:|
| Pooled | 3.733 | **1.440** | 1.472 | 1.790 |
| Equal district | 3.702 | **1.385** | 1.434 | 1.774 |
| Equal calendar month | 3.482 | **1.375** | 1.376 | 1.751 |

Macro RMSE means arithmetic mean of group RMSEs, not pooled RMSE. XGB has lower district RMSE than seasonal in 15/33 districts and lower calendar-month RMSE in 5/12 months (February, April, May, July, August). In 2024 its RMSE is 1.531 versus seasonal1.628; January–June2025 reverses this to1.347 versus .961. Omitting any single district leaves XGB-minus-seasonal RMSE positive (+.013…+.054m); no difficult district was dropped. Its largest retained error is4.644m, labelled Hyderabad/May2024. Full error percentiles, district/month/year results and large cases are saved.

Later native MAE/RMSE: persistence **3.924/4.375**, seasonal **1.305/1.502**, expanding XGB **1.649/1.936**, frozen XGB **1.397/1.681**, HGB **2.018/2.421**. This is a distinct missing-weather regime, not an opportunity to reselect a model. Existing historical primary seasonal2.132m/HGB3.060m remain context; differences across providers, populations and aggregations are **not an accuracy improvement claim**.

Panel continuity is incomplete: 320/594 primary origin/target panels match, only241/594 match all three reference dates; minimum origin/target Jaccard .615. District averaging also obscures well-level errors. A separate same-ID analysis requires matching location/depth/aquifer/type across all three dates:

| Primary well comparison | Cases / IDs | Persistence MAE / RMSE | Seasonal MAE / RMSE |
|---|---:|---:|---:|
| All consistent-ID chains | 28,505 / 1,632 | 3.872 / 5.342 | **2.143 / 3.463** |
| Exact name/location agreement at all three dates | 1,114 / 71, five districts | 3.583 / 5.402 | **2.730 / 5.055** |

Of29,616 accepted primary well targets,1,111 lack an eligible reference chain; overlapping reason counts are972 missing seasonal and507 missing origin. The stricter geographic subset is an input-QC sensitivity, not a replacement primary test or certified station population. District-trained ML was **not presented as a well-depth model**. Secondary well results and all exclusions are retained separately.

## 5. Leakage, timing and claims supported

Independent checks recompute labels/baselines, district means, all saved MAE/RMSE, and unchanged weather values/missingness. Rebuilding actual histories truncated at December2018, July2023 and December2024 reproduces every earlier model feature. Training cutoffs, exact targets and observed-only labels pass calendar checks; preprocessing is not fit on held-out rows. No source revision is silently represented as an earlier archived vintage.

| Claim | Evidence / status |
|---|---|
| Historical out-of-time forecasting | Executed fixed-settings expanding fits and frozen transfer on new reported labels; conditional on source/location quality and current export. |
| Verifiably available information at historical issuance | **Unestablished.** Export metadata identifies an August2026 vintage; per-value publication/receipt/revision history and weather vintages are unavailable. Calendar causality does not establish point-in-time validity. |
| Genuine prospective skill | **Unmeasured.** Predictions were computed in October2026 after these outcomes. `forecast_issued_at` is null; no backdating, shadow records or future-label claims. |
| Nationwide generalization | **Unestablished.** One state, changing mixed-aquifer panels and unresolved location metadata. |

The nominal target stays M+6. If complete origin-month weather requires issuance after M closes, the earliest zero-latency next-month issue precedes the provider's reported target date by only **150–153 days** in these chains. This is a conditional calendar calculation, **not actual lead time**: acquisition semantics and release latency remain unknown. Six full months from actual issue cannot be claimed under the unchanged post-month input contract.

## 6. Reproduction, failures and preservation

Start with [COMMANDS.md](COMMANDS.md), [commands/checks](checks.json), the [replay script](REPRODUCE.ps1), [row-level historical predictions](evaluation_v2/historical_predictions_vs_observations.csv), [input features](evaluation_v2/input_features.csv), [metrics](evaluation_v2/metrics.json), [paired intervals](evaluation_v2/paired_uncertainty.json), and [independent verification](diagnostics_v2/verification.json). Raw/normalized files and full panel memberships remain local research artifacts. **24 scoped pytest tests passed in7.05s**, plus independent well-baseline arithmetic/identity checks. No new dependency was installed.

Failures are retained: an initial test had a sandbox temporary-fixture setup error; the unnecessary fixture was removed. The first adapter failed to reject nullable missing depths; new regression cases and explicit float conversion correct this. `normalized/`, `evaluation/`, logs and the v1 code snapshot remain; corrected evidence is **`normalized_v2/` and `evaluation_v2/`**. Case IDs, targets, baselines and XGB/HGB predictions are unchanged; OLS rerun differences are at most8.53×10⁻¹⁴m. No retuning occurred. The first small-sample approval was rejected under the older task's no-download restriction; the same action was approved after checking the newer explicit authorization.

**Full preservation check failed:** 656/658 inventoried pre-existing files match. Two existing progress records changed at09:04:25UTC during this work: `data/raw/updates/rainfall_refresh/overlap/2025/download_progress.json` and `reports/candidates/rainfall_refresh/2026-01_2026-09/progress.json`. Two new `reports/candidates/rainfall_refresh/task_logs/refresh-20261019T143421-15428.*.log` files also appeared. Their stdout records a rainfall staging comparison with zero network requests and `source_data_modified=false` / `production_changes_made=false`; this identifies the activity, not its launcher. No corresponding refresh/staging command was invoked in this mission, the user was not aware of another refresh, and process inspection was unavailable. The files were **not reverted or overwritten to conceal the discrepancy**. [Preservation evidence](preservation.json) retains hashes and current-byte copies. All18 active-checkpoint files, the locked feature export, source code/configuration, the 11 existing user edits, and completed scientific/selection/submission reports remain unchanged. The database was not accessed. Do not interpret the broader preservation check as passing.

Only this new research directory was intentionally added. No production model promotion, forecast issuance, database operation, commit or push occurred. The historical HGB binary grants no shadow approval.

## 7. Decision and next gate

**Continue research; do not start real shadow issuance or claim production accuracy.** Resolve the provider Well-ID-to-location discrepancies first, alongside acquisition/month-label semantics, measuring-point/replacement history and actual release/receipt/revision documentation. Retain the present results as conditional evidence; do not repair coordinates by guessing or tune to these outcomes.

Before any prospective campaign, obtain human approval of the unchanged nominal-calendar versus six-full-month lead claim, a feasible actual issue schedule, independently documented source availability, verified well population/weights and missing-label policy, an approved frozen shadow artifact/adapter, and a trusted immutable archive. Register RMSE as the primary metric, MAE/harm checks, paired dependence-aware analysis, geographic/seasonal coverage and practical benefit margins **before** new outcomes; determine adequacy from domain requirements rather than this test's winning numbers. A release claim would require approved evidence of meaningful benefit against **both** baselines on genuinely issue-before-acquisition outcomes, with no test-driven retuning. None of those release gates is satisfied by this historical run.
