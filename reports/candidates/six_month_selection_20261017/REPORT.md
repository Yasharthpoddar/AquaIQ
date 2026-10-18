# AquaIQ six-month model selection — 17 October 2026

Validation selected **HistGradientBoosting** (`hist_gradient_boosting-2-delta`) by pooled out-of-fold RMSE. Its chronological test RMSE is **3.0602 m**, versus persistence **3.6984 m** (model minus baseline -0.6381 m).

**Decision: no confirmed overall ML winner.** Seasonal naive has the lowest primary-test RMSE and MAE of all six candidates. The validation-selected HistGradientBoosting has a lower primary-test RMSE point estimate than persistence, but higher MAE, and its paired 95% RMSE-difference interval spans zero [-1.2343, +0.0377] m. Its superiority over persistence is therefore not established on the primary cohort. Do not promote it from these results.

Ridge and Random Forest show exploratory primary-test RMSE improvements over persistence with district-bootstrap intervals below zero (Ridge [-2.6472, -0.0428] m; RF [-2.3981, -0.0322] m), but higher pooled MAE and no established MAE advantage. They were not the validation-selected winner; selecting either now would use the final test for model selection. All ML families lose to seasonal naive on primary RMSE/MAE. Thus the evidence does not support a blanket claim that every ML model fails to improve any metric, nor does it confirm an ML model as best overall.

The selected model does improve both errors over persistence in the secondary causal-origin cohort (RMSE 2.7988 vs 3.4125 m; MAE 1.8367 vs 2.2941 m), with both paired intervals below zero. Seasonal naive still has lower errors there. It also improves both errors over both baselines in the separate 74-case source benchmark (RMSE 5.3036 vs persistence 6.1573 m; MAE 2.9535 vs 4.7796 m), with paired intervals below zero. These are conditional findings, not independent confirmation of general operational superiority.

**Concentration check.** One Faridabad case supplies 71.5% of persistence squared error and 72.2% of the selected model’s net squared-error reduction; Faridabad plus Cuddalore supply 91.3% of that reduction. The Faridabad origin is 65.66 m, target 20.445 m, and HGB prediction 57.7744 m. Its station composition may differ, but no erroneous observation was established and the case was retained. HGB has worse absolute error on 147 of 209 cases, while improving 21 of 32 district means; 22 districts contain only one case. Cuddalore, Tiruppur, Sivaganga and Deoria supply 119 of 209 cases (56.9%) and all 2022–2023 cases. These competing weighting effects explain why pooled MAE, pooled RMSE and district-macro errors can point in different directions.

**This is a retrospective, newly locked selection run.** Final-period labels were excluded from fitting and hyperparameter selection here, but historical periods were inspected by earlier project audits/training. The 209-case holdout is untouched within this run, not a pristine prospective blinded trial. The separate unused-source benchmark has unresolved vertical datum, well composition and publication-lag limitations. No active model was replaced or promoted.

**Reproduction before changes.** Saved XGBoost, persistence, seasonal naive, Ridge and Random Forest metrics reproduced at absolute tolerance 1e-12; maximum numeric difference 6.66e-16. The old validation contained 108 cases (seasonal 97); its final test contained 10 cases in 4 districts. Nine of the 10 final targets exactly equal both baseline predictions, so that test cannot establish broad forecasting skill.

**Common-case comparison.** MAE/RMSE are metres; lower is better. R² is a pooled coefficient of determination, not prediction accuracy. Within each cohort every model and baseline uses exactly the same district/origin/target cases. ML rows use the best validation settings for their family; only the validation-selected family is the confirmatory ML candidate.

| Model | Validation MAE | Validation RMSE | Validation R² | Test MAE | Test RMSE | Test R² |
| --- | --- | --- | --- | --- | --- | --- |
| Persistence | 2.7311 | 3.5033 | 0.7860 | 1.2339 | 3.6984 | 0.8090 |
| Seasonal naive | 1.4857 | 2.4360 | 0.8965 | 1.0487 | 2.1317 | 0.9366 |
| Ridge | 1.4738 | 2.2478 | 0.9119 | 1.3807 | 2.5734 | 0.9075 |
| Random Forest | 1.3641 | 2.1965 | 0.9159 | 1.2897 | 2.5583 | 0.9086 |
| XGBoost | 1.3706 | 2.1750 | 0.9175 | 1.4322 | 3.2247 | 0.8548 |
| HistGradientBoosting | 1.3620 | 2.1477 | 0.9196 | 1.3274 | 3.0602 | 0.8692 |

**Sample sizes and actual date ranges.** Both the primary origins and labels are genuinely observed; the exact observed seasonal reference is required for every paired evaluation. Training does not require a seasonal reference.

| Cohort | Cases | Districts | Origins | Target labels |
| --- | --- | --- | --- | --- |
| validation | 3522 | 514 | 2009-11-01 to 2018-06-01 | 2010-05-01 to 2018-12-01 |
| primary_observed_origin | 209 | 32 | 2019-07-01 to 2022-09-01 | 2020-01-01 to 2023-03-01 |
| secondary_causal_origin | 962 | 507 | 2019-07-01 to 2022-09-01 | 2020-01-01 to 2023-03-01 |
| external_source_conditional | 74 | 34 | 2021-11-01 to 2022-11-01 | 2022-05-01 to 2023-05-01 |

Final refit uses 14,817 observed-origin training pairs with labels through 2018-12-01. All horizons are exactly six calendar months. No intermediate 1–5 month skill is implied; `horizon_metrics.csv` explicitly records horizon 6.

| Validation fold | Training label cutoff | First allowed origin | Cases | Actual targets |
| --- | --- | --- | --- | --- |
| validation-2010 | 2008-12-31 | 2009-07-01 | 826 | 2010-05-01 to 2010-11-01 |
| validation-2013 | 2011-12-31 | 2012-07-01 | 816 | 2013-05-01 to 2013-11-01 |
| validation-2016 | 2014-12-31 | 2015-07-01 | 1110 | 2016-01-01 to 2016-12-01 |
| validation-2018 | 2016-12-31 | 2017-07-01 | 770 | 2018-01-01 to 2018-12-01 |

**Protocol.** Four expanding training windows use evaluation target years 2010, 2013, 2016, 2018. Six full calendar months separate the training label cutoff from the first allowed evaluation origin. Final training labels stop 2018-12-31; final origins begin 2019-07-01 and targets begin 2020-01-01. The final period was fixed by label coverage before tuning, and validation physically removes all post-2018 rows before constructing labels. Per-family hyperparameters and absolute-depth versus depth-change targets were selected from 24 fixed configurations (96 fold fits), using pooled validation RMSE. The immutable selection lock was saved before any final predictions. There is no test-driven retuning.

Ridge uses training-only median imputation, missing indicators and scaling; Random Forest uses training-only median imputation and indicators. XGBoost and HistGradientBoosting handle missing features natively. HistGradientBoosting is justified by installed scikit-learn and this tabular dataset; no dependency was added. Its internal random early-stopping split is disabled. All families share the same inputs and training cases. Origin-month sine/cosine is deterministic at issuance; no target-month weather is supplied. Canonical rainfall normals use previous years only; lags use exact calendar joins; targets are never filled. All ML predictions are truncated at 0 under the policy frozen before validation.

**Locked ML settings.**

| Family | Candidate | Target form | Parameters |
| --- | --- | --- | --- |
| Ridge | ridge-3-absolute | absolute | `{"alpha": 100.0}` |
| Random Forest | random_forest-1-absolute | absolute | `{"max_depth": 12, "max_features": 0.85, "min_samples_leaf": 5, "n_estimators": 150}` |
| XGBoost | xgboost-1-delta | delta | `{"learning_rate": 0.01, "max_depth": 6, "min_child_weight": 1, "n_estimators": 500, "reg_lambda": 1.0, "subsample": 0.8}` |
| HistGradientBoosting | hist_gradient_boosting-2-delta | delta | `{"l2_regularization": 20.0, "learning_rate": 0.05, "max_iter": 250, "max_leaf_nodes": 31, "min_samples_leaf": 50}` |

**Primary test by target year.** All six models are also available in `period_metrics.csv`.

| Year | Cases | Selected ML MAE | Selected ML RMSE | Persistence RMSE | Seasonal RMSE |
| --- | --- | --- | --- | --- | --- |
| 2020 | 107 | 1.4716 | 3.9260 | 4.9115 | 2.3595 |
| 2021 | 44 | 1.8652 | 2.4936 | 2.5116 | 2.8303 |
| 2022 | 48 | 0.6722 | 0.8017 | 0.0000 | 0.1814 |
| 2023 | 10 | 0.5636 | 0.5961 | 0.0093 | 0.0093 |

**District performance.** `district_metrics.csv` and the saved JSON give every district/model/cohort, including sample size, MAE, RMSE and R². R² is null for one-case or constant-target groups. Equally weighted district metrics reduce domination by districts with more measurements; they do not establish spatial independence.

| Model | Primary district macro MAE | Primary district macro RMSE |
| --- | --- | --- |
| Persistence | 3.6710 | 3.7805 |
| Seasonal naive | 2.0713 | 2.1856 |
| Ridge | 2.2196 | 2.3074 |
| Random Forest | 2.2363 | 2.3288 |
| XGBoost | 2.7086 | 2.8072 |
| HistGradientBoosting | 2.5477 | 2.6551 |

**Paired uncertainty for the selected ML model.** Negative differences favor ML. Intervals use 2000 paired district-block bootstrap resamples, seed 42, retaining complete district histories. They are descriptive and do not resolve spatial dependence, few time periods, prior historical exposure or source changes.

| Cohort | Baseline | 95% MAE difference interval (m) | 95% RMSE difference interval (m) |
| --- | --- | --- | --- |
| primary_observed_origin | Persistence | -0.4010, 0.3993 | -1.2343, 0.0377 |
| primary_observed_origin | Seasonal naive | -0.0733, 0.7395 | -0.6240, 2.9282 |
| secondary_causal_origin | Persistence | -0.6022, -0.3149 | -0.7780, -0.4357 |
| secondary_causal_origin | Seasonal naive | 0.1479, 0.3608 | -0.1815, 0.6965 |
| external_source_conditional | Persistence | -2.5827, -1.0438 | -1.9810, -0.2023 |
| external_source_conditional | Seasonal naive | -4.4652, -0.5461 | -9.2758, -1.5478 |

**Additional cohorts.** The secondary cohort permits only causal groundwater fills of up to 3 months at the forecast origin, still requiring observed targets and exact observed seasonal references. It is a sensitivity analysis, not extra independent evidence: the primary cases are a subset. The same observed-origin training pairs and frozen models are used.

| Model | Secondary MAE | Secondary RMSE | Secondary R² | Conditional source MAE | Conditional source RMSE | Conditional source R² |
| --- | --- | --- | --- | --- | --- | --- |
| Persistence | 2.2941 | 3.4125 | 0.8474 | 4.7796 | 6.1573 | 0.8691 |
| Seasonal naive | 1.5782 | 2.5979 | 0.9115 | 5.2650 | 11.0106 | 0.5814 |
| Ridge | 1.7758 | 2.6180 | 0.9102 | 3.8207 | 6.6469 | 0.8475 |
| Random Forest | 1.8487 | 2.7346 | 0.9020 | 3.1987 | 5.7425 | 0.8861 |
| XGBoost | 1.9108 | 2.8701 | 0.8920 | 3.1837 | 5.5801 | 0.8925 |
| HistGradientBoosting | 1.8367 | 2.7988 | 0.8973 | 2.9535 | 5.3036 | 0.9029 |

The separate Gujarat source contributes 74 previously unused target district-months across 34 districts (6 in May 2022, 34 in November 2022, 34 in May 2023). None was used for fitting or selection. Source dates were parsed explicitly day-first and rows spatially audited: 6244 accepted, 460 excluded. Its header establishes metres but does not explicitly establish below-ground datum; no original transport manifest or successful current byte verification is available. Of 26 overlapping active observed months, 25 have different means, consistent with differing station composition. It therefore stays separate from active district means and cannot certify a general m_bgl improvement. All 74 origin/target pairs share at least one station-location proxy; stable well identifiers are absent. See `coverage/source_manual_optional_audit.json` for exclusions and source hashes. The [official NWDP resource](https://nwdp.nwic.gov.in/dataset/gwl-manual-quarterly-central-ground-water-board-department/resource/ef17ded9-be74-48e6-9359-f3a19daeea4a) is linked for provenance; the local CSV actually ends August 2023 despite its 2021–2025 filename.

**Why the old test has 10 cases.** There are only 11 active observed labels in 2023, of which one lacks a finite groundwater origin six months earlier. The 639 January 2026 observations lack usable July 2025 groundwater origins; 2024–2025 have no active observed labels. The unadopted January 2025 candidate likewise lacks July 2024 origins. Filling targets or extending groundwater carries would fabricate evaluation coverage. Moving the new final cutoff earlier expands legitimate historical evidence to 209 strict cases and 962 causal-origin cases, but cannot create a fresh prospective test. Label coverage was inspected without scoring the new test.

**Changes and protections.** Added `models/six_month_selection.py`, `tests/test_six_month_selection.py`, this candidate directory and scoped `.gitignore` patterns for large artifacts. Fixed the confirmed ambiguous native `Data Acquisition Time` parser in `scripts/audit_data_quality.py` and added its regression in `tests/test_audit_data_quality.py`. Fixed `models/xgboost_model.py` to return undefined R²/NSE for targets constant within floating-point resolution, with `tests/test_forecast_metric_precision.py`. This prevents misleading enormous negative district scores; MAE/RMSE are unchanged. The initial validation-only run is preserved in `experiment/`; the corrected protocol was rerun from scratch in `experiment_v2/` before any test scoring. These changes affect audit date/metric interpretation; they do not regenerate active features or previous reports. No other feature bug was confirmed in the verified causal generation. Checksums confirm all 145 protected processed/checkpoint/config/source/report files stayed unchanged through both stages. No database access, active checkpoint replacement, promotion, commit or push occurred.

**Remaining limits.** The test covers 32 districts and sparse measurement months, with only 10 cases in 2023 and none later. Validation spans 514 districts; the final geographic/seasonal distribution differs substantially. 3312 of 3522 validation cases target May or November. `calendar_metrics.csv` reports every calendar month separately; sparse other months cannot establish general year-round skill. District aggregates can change because the set of measured wells changes. There are no operational publication/revision timestamps proving every origin feature was available in real time. A prospective test on new observed labels and stable well panels is needed before deployment claims. A high pooled R² can reflect between-district depth differences even when persistence is stronger.

**Reproduce.** Run the PowerShell commands in `REPRODUCE.ps1` from the repository root. They create a new sibling candidate directory and refuse to reuse the saved result paths. Validation and test are separate commands. Coverage helpers operate on local copies; the optional network byte verification can remain unavailable without changing source features. The report renderer itself reads only saved predictions/metrics and does not fit or retune models.

**Tests.** Full local suite without database integration: 839 passed, 1 skipped, 0 failed, 0 errors. See `pytest-final-results.xml`. Targeted selection regressions cover exact calendar labels, observed provenance, causal-origin separation, embargo, future-row invariance, training-only preprocessing, deterministic paired identities, finite predictions, undefined R² and protected output paths.
