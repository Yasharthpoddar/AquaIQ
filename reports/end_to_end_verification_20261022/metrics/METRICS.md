# Independent saved-row metrics audit

Executed 2026-10-23 UTC against the retained GitHub-version workspace. All prediction values were read from archived CSVs; this audit performed arithmetic, joins, hashes, and resampling only. No estimator was deserialized or invoked, and no fitting, tuning, ingestion, database, downloads, pipelines, or serving writes occurred. All outputs are new files in this directory.

The broad 12-month XGB result shows a small descriptive improvement over the annual baseline, with both paired uncertainty intervals crossing zero. The fixed application artifact performs substantially worse than its own baseline on its 24 retained Adilabad checks. These are distinct artifacts and geographic cohorts.

## Broad Telangana 12-month primary cohort

792 paired cases, 33 districts, 24 cases per district and 66 per calendar month. Origins January 2023–December 2024; observed targets January 2024–December 2025. All four methods share exactly the same finite cases. Exact 12-calendar-month joins, explicitly observed non-imputed origins and targets, persistence values, and annual-seasonal equivalence were independently checked. At this horizon annual seasonal naive equals persistence by construction.

| Method | n | MAE (m) | RMSE (m) | Pooled R² | Bias (m) |
|---|---:|---:|---:|---:|---:|
| persistence | 792 | 1.191078911 | 1.457722579 | 0.721469802 | -0.242430636 |
| xgb_expanding | 792 | 1.159118991 | 1.419907531 | 0.735733172 | 0.456614234 |
| linear_expanding | 792 | 1.927978646 | 2.455645515 | 0.209587363 | 1.512081691 |
| hgb_12month_fixed | 792 | 1.222150707 | 1.505470268 | 0.702924462 | 0.493834378 |

XGB ΔRMSE = -0.037815047472839147 m (2.594118252% lower); ΔMAE = -0.031959919353399036 m. XGB beats baseline RMSE in 20/33 districts and 8/12 calendar months; linear in 7/33 and 0/12; HGB in 16/33 and 7/12. XGB loses in September–December calendar groups. The pooled R² includes differences between district target levels; it is not a prospective accuracy guarantee or a district-average R².

## Paired dependent resampling

Stored procedure reproduced independently: sort districts, create the contiguous monthly target axis, seed NumPy default_rng(42), draw D districts with replacement, then ceil(T/12) circular block starts and truncate to T months; 2,000 replicates per entry. District-only replicates still consume the time draws, preserving the exact stored RNG sequence. Both compared methods retain identical sampled rows. The v1 helper used weighted error totals; v2/v3 independently materialized sampled row indices and reduced row errors. All 228 archived interval pairs (456 endpoints, 19 cohort/model entries × 2 methods × 6 quantities) agree within 1e-10, including the paired six-versus-twelve-month results. Point MAE/RMSE/bias/R² also agree with independent math.fsum arithmetic.

Differences below are method minus persistence; negative MAE/RMSE favors the method. All primary replicates are nonempty and contain 792 sampled rows.

| Method | Resampling | ΔMAE 95% interval (m) | ΔRMSE 95% interval (m) |
|---|---|---:|---:|
| persistence | district | [0.000000000, 0.000000000] | [0.000000000, 0.000000000] |
| persistence | district_x_12month_blocks | [0.000000000, 0.000000000] | [0.000000000, 0.000000000] |
| xgb_expanding | district | [-0.117046452, 0.060182589] | [-0.123912569, 0.055973884] |
| xgb_expanding | district_x_12month_blocks | [-0.359119868, 0.272407466] | [-0.317330099, 0.264464667] |
| linear_expanding | district | [0.373558593, 1.147299855] | [0.518425651, 1.477515350] |
| linear_expanding | district_x_12month_blocks | [0.309696626, 1.221971621] | [0.457466476, 1.568277126] |
| hgb_12month_fixed | district | [-0.067232370, 0.138954996] | [-0.048071453, 0.160780960] |
| hgb_12month_fixed | district_x_12month_blocks | [-0.268606575, 0.297081622] | [-0.207321410, 0.321194979] |

Intervals are descriptive percentile intervals for dependent regional current-vintage evidence. The 24-month primary cohort supplies only two annual blocks; the two-month secondary cohort cannot support meaningful annual-block temporal uncertainty. District-only intervals condition on the retained time window. With one district, district-only intervals degenerate; they do not establish geographic generalization.

## Geographic and panel sensitivities

The strict exact-name-plus-coordinate primary cohort contains only 24 Adilabad cases, compared with 792 broad full-coordinate cases. It uses a different well panel and different observed target values. Its historical annual expanding models are also distinct from the fixed application artifact.

| Method | n | MAE (m) | RMSE (m) | Pooled R² | Bias (m) |
|---|---:|---:|---:|---:|---:|
| persistence | 24 | 0.645164072 | 0.876995610 | 0.880638108 | 0.066662241 |
| xgb_expanding | 24 | 1.987887163 | 2.517816636 | 0.016172282 | 1.888394617 |
| linear_expanding | 24 | 1.455098490 | 1.905400919 | 0.436565291 | 1.317949036 |
| hgb_12month_fixed | 24 | 1.565044114 | 1.882595422 | 0.449971931 | 1.395214088 |

On the broad identical-origin/target-panel sensitivity, only 380 cases in 32 districts remain. Baseline MAE/RMSE = 1.133739801/1.382523452 m; XGB = 1.182743649/1.437133908 m. The XGB advantage reverses. This subset is unbalanced, so district/calendar macro weighting differs from pooled weighting; full macro/group results and independently calculated subset intervals are retained. The strict identical-panel subset has only 19 cases/one district. Panel equality is a useful sensitivity, not proof of measurement validity or historical availability.

The 66-case broad January–February 2026 secondary cohort has XGB RMSE 1.202969265 versus baseline 1.490132988 m; it is two target months. Strict secondary has two cases. Neither expands the primary cohort or supplies another full annual evaluation period.

## Fixed Adilabad application artifact: its own 24 cases

Origins January 2023–December 2024 and targets January 2024–December 2025. Model SHA-256 f94911f5e1a6c3e8b4bbbb82d6a4c6ec87b5d601abbfd774801afc046aa5455f. Descriptor, canonical contract, manifest, card, snapshot, provenance, model-file hash, ordered feature schema, supported geography, and all 24 row model identities were checked without loading the estimator.

| Method | n | MAE (m) | RMSE (m) | Pooled R² | Bias (m) |
|---|---:|---:|---:|---:|---:|
| persistence | 24 | 0.645164072 | 0.876995610 | 0.880638108 | 0.066662241 |
| fixed_xgb_2021 | 24 | 2.144769916 | 2.664045122 | -0.101422665 | 2.052587344 |

| Method | Resampling | ΔMAE 95% interval (m) | ΔRMSE 95% interval (m) |
|---|---|---:|---:|
| persistence | district | [0.000000000, 0.000000000] | [0.000000000, 0.000000000] |
| persistence | district_x_12month_blocks | [0.000000000, 0.000000000] | [0.000000000, 0.000000000] |
| fixed_xgb_2021 | district | [1.499605844, 1.499605844] | [1.787049512, 1.787049512] |
| fixed_xgb_2021 | district_x_12month_blocks | [1.259537485, 1.739683756] | [1.534352569, 2.103300330] |

This artifact's training membership independently reconstructs to 164 eligible origin/target pairs, 158 complete-feature pairs, maximum target December 2021, cutoff 2021-12-31, and first permitted/evaluated origin January 2023. Its canonical JSON ordered-membership hash is 15ad0e1401be81f4b9f3bd68cc09e98efd0e25732dabbda985aa341274e4eed0. The historical annual expanding evaluation instead has year-specific artifact hashes/cutoffs; its 792-case XGB score cannot be assigned to this fixed artifact.

For the stored January 2024 origin → January 2025 target example: actual 6.831333333333332 m, annual baseline 6.836666666666668 m, fixed XGB 7.571100711822510 m. The latest observed fixed snapshot is May 2026 (nominal target May 2027), but six weather features are missing; it contains no acquisition/available-at timestamps. This audit did not create a prediction for it.

## Original six-month selection test

209 observed-origin, observed-target paired cases in 32 districts across eight state prefixes: AS, CG, HR, MP, RJ, TN, UP, WB. Origins July 2019–September 2022; targets January 2020–March 2023. Exact six-calendar-month targets, all-method common finite cases, and source origin/target/seasonal values and observed flags were independently joined to retained nationwide features. This is a different geography, horizon, and period from the 12-month Telangana evidence.

| Method | n | MAE (m) | RMSE (m) | Pooled R² | Bias (m) |
|---|---:|---:|---:|---:|---:|
| persistence | 209 | 1.233872880 | 3.698361603 | 0.809024840 | 0.339005423 |
| seasonal_naive | 209 | 1.048686087 | 2.131713658 | 0.936552301 | 0.678894808 |
| ridge | 209 | 1.380663210 | 2.573416436 | 0.907534807 | 0.698998350 |
| random_forest | 209 | 1.289729700 | 2.558294341 | 0.908618315 | 0.811260474 |
| xgboost | 209 | 1.432185427 | 3.224708881 | 0.854809177 | 0.683202209 |
| hist_gradient_boosting | 209 | 1.327448258 | 3.060216372 | 0.869243765 | 0.679322382 |

The validation-selected HGB is not the best method on this retained test: seasonal naive has lower MAE and RMSE, and ridge/random forest also have lower RMSE than HGB. HGB's largest absolute error is 37.329406256 m at HR-Faridabad|2020-02-01|2020-08-01|6 and contributes 71.195347% of its total squared error. The large pooled R² therefore needs the error distribution and cohort context. No post-test model selection was performed by this audit.

## Retained Telangana six-month context and horizon joins

594 cases, 33 districts, origins July 2023–December 2024 and targets January 2024–June 2025.

| Method | n | MAE (m) | RMSE (m) | Pooled R² | Bias (m) |
|---|---:|---:|---:|---:|---:|
| persistence | 594 | 3.359445429 | 3.733498920 | -1.186174598 | -1.144183754 |
| seasonal_naive | 594 | 1.159635770 | 1.440453987 | 0.674574513 | -0.663460791 |
| xgb_expanding | 594 | 1.205193305 | 1.472178537 | 0.660082325 | -0.434308965 |
| xgb_active_frozen | 594 | 1.503472287 | 1.798777676 | 0.492533051 | -0.903419997 |
| hgb_locked_historical | 594 | 1.495575017 | 1.789873220 | 0.497544825 | -0.285133436 |
| linear_expanding | 594 | 1.399955836 | 1.752076572 | 0.518541400 | -0.398149013 |

On 594 identical observed targets, twelve-month XGB MAE/RMSE/R² = 1.039498626/1.317859779/0.727609981 versus six-month XGB 1.205193305/1.472178537/0.660082325. The paired ΔRMSE district interval is [-0.253390778,-0.062819335] m; district×12-month interval [-0.343215342,0.059924876] m crosses zero. Twelve-month persistence exactly equals six-month annual seasonal naive on these targets (RMSE 1.440453987 m). Against that appropriate annual baseline, six-month seasonal naive beats six-month XGB in aggregate. The same-origin 594-case join changes outcomes: twelve-month XGB RMSE 1.478463953 versus baseline 1.332002337 m. Neither join isolates a controlled horizon effect because origins, training cutoffs, and/or targets differ.

## Identity, cutoff, availability, and preservation receipts

The primary and strict frozen inventory ordering/common-eligibility flags, input hashes, model card hashes, per-row model hashes, target horizon, protocol identity, and all saved 12-month expanding training membership counts/hashes and fold cutoffs passed. Training membership reconstruction used retained rows only. Point and interval comparisons were checked against retained reports as a cross-check after recomputation, not accepted as truth.

All evaluated 12-month rows lack issuance timestamps and declare availability unverified. Source and app snapshot acquisition/available-at fields are empty. Calendar-causal dates and embargoes do not prove what was known at historical issuance. These are retrospective current-vintage nominal-horizon results. Hashes bind saved predictions to metadata/artifact bytes; without estimator execution this audit does not independently prove that a saved prediction was produced by the associated estimator.

The initial helper retained 688 checks: 686 raw passes and two raw implementation hash mismatches. Both are exclusively Windows CRLF bytes: converting CRLF to LF in memory exactly matches the frozen implementation hashes. No file was normalized or modified. The independent supplement retained 430 checks: 428 passes and two incorrect audit encoding assumptions. The six-month archived ID includes the documented `telangana|` prefix and no horizon suffix; the fixed artifact hashes a canonical JSON ordered training-ID list rather than newline-sorted IDs. `encoding_resolution_v3.json` verifies both documented formats and preserves every earlier failure record. These are audit-assumption resolutions, not repaired data or artifacts.

The original 72 hashed input files were unchanged after the first run; supplemental inputs also remain unchanged. Full precision binary64 JSON results: `metrics.json`, `bootstrap.json`, `independent_arithmetic_v2.json`, `direct_row_bootstrap_v2.json`, and `direct_row_horizon_bootstrap_v3.json`. Cohort membership/value/prediction fingerprints: `cohort_fingerprints_v2.json`. Detail: `group_metrics.csv`, `adverse_cases_v2.json`, `artifact_checks.json`, `newline_normalization_receipt.json`, `fixed_training_membership_v2.json`, `encoding_resolution_v3.json`. Commands/run scope/runtime/input hashes: the three audit scripts and their `run.json`, `supplement_run_v2.json`, `report_run_v3.json` receipts. Scripts refuse to replace outputs.
