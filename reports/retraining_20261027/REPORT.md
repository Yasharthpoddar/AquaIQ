# Enriched XGBoost retraining — 27 October 2026

A new XGBoost model was fitted on the enriched measured dataset, selected using earlier chronological validation and saved separately. The final fit uses **145,494 observed-origin/observed-target pairs across 641 districts**, including **20,720 pairs with newly accepted targets and 431 January 2025 target pairs**. This is an actual refit with changed model bytes. The candidate remains **experimental and unpromoted**: all supported validation-accuracy and contract gates pass, but no genuinely untouched post-refit test observations exist. The frozen production model stays active.

## Model and dataset identities

| Artifact | Identity |
| --- | --- |
| Frozen model version | `1.0-climate-conditioned-12m-xgb` |
| Frozen model SHA-256 | `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03` |
| Frozen training | Labels through December 2019; 116,601 pairs, 558 districts |
| Original feature generation | `physical-v3-causal-monthly-a3f9468a2569` |
| Original feature CSV SHA-256 | `3958737b033a16e722f633a15ad77d80bc5b2a8fb3bea888697f0410362c24ae` |
| Enriched feature generation | `physical-v3-official-c9ade81d95720f91` |
| Feature CSV SHA-256 | `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042` |
| New experimental candidate version | `2.0-enriched-retraining-experimental` |
| New model SHA-256 | `e4e57de9f681b2f2702c9b86a00be06b04147123ecea0579f6abcf3cdc586192` |
| Candidate card SHA-256 | `30d837e15fac7184609330197c1bb3ff6d3e6daf6154dcb4267fe26784662176` |
| Shared ordered feature-schema SHA-256 | `89ec17cedc0751550639232ead3b952b34c28c0bdc23c31275325628d8071113` |
| Training implementation seal | `6c0d584514bd456eb164dc13be4e61fe096f51ab9048ce6d5fd1946d9203bcf2` |
| Saved pair CSV SHA-256 | `a2eefb9a076f93117edbdab594ff6fa729a7a98c9bff584ad7d3e4031a5c4806` |

The candidate [checkpoint](../../models/artifacts/enriched_retraining_20261027/checkpoint.json) resolves its separate [model](../../models/artifacts/enriched_retraining_20261027/climate_12m_bundles/20261027T011601230842Z-27202aaa56/model.json) and [card](../../models/artifacts/enriched_retraining_20261027/climate_12m_bundles/20261027T011601230842Z-27202aaa56/model_card.json). Its recorded training timestamp is **2026-10-27 01:16:01 UTC**. The deployed pointer `models/artifacts/aquaiq_climate_12m.json` and its original bundle remain intact. [Training summary](training/training_summary.json), [locked selection](training/selection.json) and [protocol](protocol.json) bind the experiment's actual inputs and settings.

## Accepted data, quality checks and inclusion

The [executed data audit](data_audit.json) verifies the local `data/processed/enrichment/final_release_20261026_v3` snapshot: **215,325 rows**, **725 districts**, and a complete 297-month grid from January 2002 through September 2026. It contains **43,384 observed**, **85,816 causally imputed** and **86,125 missing groundwater rows**. Fifty-seven districts have no accepted local observation. The matrix's end date does not establish equally recent labels.

Across both enrichment releases, CGWB/NWIC manual quarterly records add **5,952** missing measured months, and the strictly verified CGWB January archive adds **542**, for **6,494** gains across 653 districts compared with the original 36,890-label baseline. Sixteen districts gain their first local history. Against the immediate NWDP parent, the gain is 542 January 2025 months and five newly local districts. Existing measured values take precedence: zero original observations were removed or changed. The recursively hashed source chain, accepted monthly aggregates and exact union of old plus new measured keys were checked. The prior [source catalog](../../data_sources/catalog.yaml) and [groundwater report](../final_release_20261026/groundwater_sources.md) retain official URLs, acquisition dates, licenses and acceptance/quarantine details.

The audit rejects duplicate district-month keys, unknown IDs or flags, observed/imputed overlap, nonfinite or negative measured depths, untraced finite values, altered source means and inconsistent physical units. All checks passed. Groundwater targets remain generic measured depth in `m_bgl`; a dataset title does not certify per-well aquifer construction or a stable well panel. No telemetry, predicted values, regional references or filled groundwater values become training labels.

The 274,930 telemetry rows with unresolved sign/datum conventions remain quarantined. The PDF source retains its prior 817 quarantined rows under overlapping quality reasons; this task does not reconsider them or acquire replacement labels. Two pre-existing Gandhinagar measurements above 100 m—106.156 m in November 2020 and 102.51 m in January 2021—are flagged in the audit and retained unchanged. There is no arbitrary clipping of measured labels or silent data repair.

Observed rows have zero observation age. Imputed groundwater carries a prior observation forward for at most three months; later gaps stay missing. Exact three/six-calendar-month lag and carry reconstruction checks pass. Among observed rows, 4,159 lack the stored three-month lag and 5,506 lack the six-month lag; 709 lack stored temperature/PET. The candidate reproduces the existing origin-available weather/projection fallback where supported and otherwise keeps missing lag values as native XGBoost NaNs. No scaler or global imputation is fitted using validation/future rows. Full missingness, year/month counts and dtypes are in [data_audit.json](data_audit.json).

The saved pair file has 146,057 usable pairs after weather/origin eligibility. The final fit excludes its 563 January 2026 target pairs, leaving **145,494**. The data audit's 164,323 calendar-join count is explicitly a pre-weather upper bound; 18,829 of those pairs lack the required eligible origin weather/history.

| Final-fit enrichment inclusion | Count |
| --- | ---: |
| Pairs with newly accepted target measurements | 20,720 |
| Pairs with newly accepted origin measurements | 17,620 |
| Distinct added measured months used as targets | 6,071 |
| Distinct added months used in either role | 6,165 |
| Added months unable to form an eligible pair | 329 |
| January 2025 target pairs in fitting | 431 |

These counts were independently recomputed from the saved pairs and genuine source flags. Not all 6,494 gains can form an origin/target pair, and only eight of the 16 newly local districts enter the final fit. No examples are fabricated to include the others.

## Training objective, chronology and leakage controls

The existing twelve-month product uses one horizon-conditioned XGBoost regressor with **17 ordered features**, predicting **target measured depth minus observed-origin depth** for exact horizons M+1 through M+12. Serving adds the predicted change to the current-depth anchor and floors predicted depth at zero. The legacy six-month absolute-depth model, API schema and canonical geography remain unchanged.

The new pure pair builder requires observed endpoints and computes features from the origin-available prefix. Weather uses same-calendar-month historical climatology through the completed origin month, with the existing minimum three/reference maximum ten-year policy. Calendar groundwater lag lookups and any projection fallback use only history through the origin. Future source rows identify genuine labels, never input features. Tests compare every field with production encoding, including month-end/M+12 handling, future perturbations and missing-lag behavior.

The frozen model's card records realized historical conditional weather during its old fit. The candidate uses serving-time weather assumptions and corrects the trainer's origin-month boundary mismatch. Results therefore reflect both retraining on expanded observations and better alignment of feature construction; they do not identify the isolated causal effect of enrichment.

| Phase | Actual train labels through | Train pairs / districts | Actual validation origins | Actual validation targets | Cases / districts |
| --- | --- | ---: | --- | --- | ---: |
| Rolling 2023 | December 2021 | 127,402 / 626 | January–November 2023 | February 2023–January 2024 | 2,692 / 477 |
| Rolling 2024 | December 2022 | 136,791 / 632 | January–November 2024 | February 2024–January 2025 | 910 / 277 |
| Final fit | January 2025 | 145,494 / 641 | None used for final selection | No untouched later test available | — |

Earlier folds preserve the existing twelve-month origin embargo. Train targets precede every validation origin. Final-fit origins run January 2005–November 2024 and targets May 2005–January 2025. The final label cutoff is 31 January 2025. January 2026 labels enter neither fitting, early stopping nor hyperparameter selection.

The folds respect time and report district-macro MAE to limit domination by densely sampled districts. Districts may recur across periods; these dependent cases are not independent trials or a state/geography-held-out transfer experiment. Historical publication/receipt availability at each origin is unverified. There are no accepted observations after January 2026, and 2025 observations occur only in January. Even without an embargo, no observed-origin/future-target pair exists strictly after January 2025. The existing `train()` requirement for an independent later holdout cannot be satisfied by inventing rows; this workflow separates earlier selection from the explicitly labelled final experimental fit.

## Model settings and earlier validation

Three prespecified configurations were compared on identical earlier-fold cases. Maximum trees were 480, with early stopping after 40 validation rounds. Selection used the mean of the two district-macro MAEs, with mean fold RMSE and then name as tie breakers. The selected configuration's best tree counts were 447 and 475; their median locked the final **461 trees** before any January 2026 diagnostic.

| Candidate | Depth / min child weight / L2 / L1 | Mean fold district-macro MAE (m) | Mean fold RMSE (m) |
| --- | --- | ---: | ---: |
| Current structure | 3 / 30 / 20 / 0.1 | 1.940 | 3.458 |
| Shallow regularized | 2 / 60 / 40 / 0.2 | 1.984 | 3.514 |
| **Selected deeper regularized** | **4 / 60 / 40 / 0.2** | **1.913** | **3.421** |

The final model uses squared-error regression with histogram trees, learning rate **0.04**, subsample **0.85**, column sample **0.9**, random seed **42** and four XGBoost workers. It was fitted twice with these fixed settings; serialized model bytes and predictions match exactly. Saving/reloading and restoring the original rollback bundle also pass.

The following are ordinary case-weighted errors on each fold's same eligible population; selection's district-macro statistic is a separate quantity. Cells show **MAE / RMSE in metres**.

| Fold | Cases / districts | Frozen XGBoost | Retrained fold model | Persistence |
| --- | ---: | ---: | ---: | ---: |
| Rolling 2023 | 2,692 / 477 | 1.999 / 3.985 | 1.946 / 3.822 | 2.559 / 4.593 |
| Rolling 2024 | 910 / 277 | 1.904 / 3.137 | 1.794 / 3.019 | 2.485 / 3.686 |

Seasonal naive uses the **observed same month in the previous year**, only when that value was available by the origin. Its missing cases are excluded from every method in the paired table; these populations must not be compared as if they were the full table above.

| Seasonal-eligible fold | Cases / districts | Frozen XGBoost | Retrained fold model | Persistence | Seasonal naive |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rolling 2023 | 2,487 / 470 | 1.854 / 3.502 | 1.788 / 3.264 | 2.443 / 4.249 | 2.195 / 3.813 |
| Rolling 2024 | 837 / 272 | 1.916 / 3.179 | 1.807 / 3.058 | 2.505 / 3.733 | 1.998 / 3.374 |

The [locked acceptance assessment](acceptance.json) reports mean fold district-macro MAE of **1.913 m**, against **1.978 m** for frozen XGBoost and **2.517 m** for persistence: relative reductions of **3.26%** and **23.99%**. These are reductions in a historical error statistic, not accuracy probabilities. Seasonal-paired macro MAE is also no worse under the prespecified gate.

The supported subgroup gate permits at most a 10% relative MAE regression and requires at least 30 cases and ten districts. All **22 supported panels** pass; **eight panels lack support**, including M+1/M+9/M+11 panels and newly local-history groups. Passing a gate does not mean every point estimate improved: rolling-2023 M+12 MAE changes from 2.080 to 2.088 m. Newly local history has only 17 cases in three districts in rolling 2023, with frozen/retrained MAE 0.872/1.026 m, and zero cases in rolling 2024. No broad improvement is claimed for that group. For substantial original history, case MAE is 1.955→1.891 m across 2,384 cases/406 districts and 1.919→1.814 m across 829 cases/246 districts. Full per-horizon and group values/counts are retained in the selection and acceptance JSON.

The earlier per-horizon comparison uses **3,324 identical seasonal-supported cases for all four methods**, from 3,602 eligible earlier-validation cases; 278 cases lack seasonal support. It reports pooled case-weighted MAE of fold-specific models, while selection used mean fold district-macro MAE. It is not a final-refit or blind-test curve. M+1 has only 13 common cases and M+11 only two, so their plotted errors have very weak support.

## Completed twelve-origin retrospective serving diagnostic

The [complete executed summary](retrospective/summary.json) contains **7,668 cases across 639 districts and 31 states**, from twelve month-end origins in 2025. Every scored target is **January 2026**. These are twelve dependent forecasts per measured district, not twelve independent future target months or a blind test. Fitting/selection remained locked and no uncertainty calibration was performed.

The unchanged original evaluator ran in three disjoint origin groups, all successful; the complete merged case set passed the model/code/identity checks. Wall time was 1,838.35 seconds. An earlier serial run stopped after four origins solely to use this parallel execution. The optional shared-input helper was **not used** for these primary results.

**Label coverage differs from output coverage.** Of 104,400 potential district/origin/horizon target slots, 7,668 have accepted measured targets and 96,732 lack a target. The scoring population covers 639 of 725 districts. The separate complete-generation contract still produces all 725 district outputs and 36 state/UT outputs; missing truth is not silently filled to enlarge the evaluation.

Cells below are **MAE / RMSE in metres**. Every row pairs methods on the same keys. Baseline eligibility changes the population, so the rows are not interchangeable.

| Matched population | Cases / districts | Frozen XGBoost | Retrained model | Persistence | Seasonal naive |
| --- | ---: | ---: | ---: | ---: | ---: |
| All measured targets | 7,668 / 639 | 1.778 / 3.056 | 1.729 / 3.009 | — | — |
| Persistence available | 7,560 / 630 | 1.716 / 2.831 | 1.666 / 2.779 | 1.619 / 2.797 | — |
| Four-way seasonal-supported | 6,756 / 563 | 1.777 / 2.939 | 1.723 / 2.885 | 1.634 / 2.885 | 1.634 / 2.885 |

Persistence is unavailable for 108 cases and seasonal naive for 912. On the four-way panel, the candidate MAE of **1.723 m** remains worse than **1.634 m** for both simple baselines, although its RMSE is nearly equal. On the persistence panel, candidate MAE is also worse while RMSE is lower. Retraining does not make XGBoost uniformly best.

The horizon table uses **the same 563 districts for all four methods at each horizon**, totaling 6,756 paired cases. Each horizon corresponds to a different 2025 origin and the same January 2026 target; horizon differences therefore also reflect origin/recency. The full 639-district horizon panels and all pair fingerprints remain in the JSON.

| Horizon | Common cases / districts | Frozen XGBoost | Retrained model | Persistence | Seasonal naive |
| --- | ---: | ---: | ---: | ---: | ---: |
| M+1 | 563 / 563 | 1.763 / 3.008 | 1.748 / 2.993 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+2 | 563 / 563 | 1.796 / 3.055 | 1.768 / 3.013 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+3 | 563 / 563 | 1.849 / 3.089 | 1.829 / 3.043 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+4 | 563 / 563 | 1.811 / 3.015 | 1.753 / 2.946 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+5 | 563 / 563 | 1.797 / 2.925 | 1.695 / 2.832 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+6 | 563 / 563 | 1.845 / 2.900 | 1.656 / 2.767 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+7 | 563 / 563 | 1.890 / 3.001 | 1.738 / 2.885 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+8 | 563 / 563 | 1.751 / 2.883 | 1.693 / 2.817 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+9 | 563 / 563 | 1.753 / 2.844 | 1.714 / 2.788 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+10 | 563 / 563 | 1.751 / 2.880 | 1.755 / 2.889 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+11 | 563 / 563 | 1.739 / 2.890 | 1.747 / 2.886 | 1.634 / 2.885 | 1.634 / 2.885 |
| M+12 | 563 / 563 | 1.574 / 2.757 | 1.585 / 2.740 | 1.634 / 2.885 | 1.634 / 2.885 |

On the full 639-district panels, M+11 and M+12 MAE regress from 1.771 to 1.779 m and 1.597 to 1.604 m. M+10 RMSE also rises slightly. The aggregate improvement does not hide these horizon regressions.

| Tier | Cases / districts | Frozen MAE / RMSE (m) | Retrained MAE / RMSE (m) |
| --- | ---: | ---: | ---: |
| A | 6,516 / 543 | 1.715 / 2.830 | 1.657 / 2.770 |
| B | 1,044 / 87 | 1.722 / 2.837 | 1.722 / 2.837 |
| C | 108 / 9 | 6.101 / 10.099 | 6.101 / 10.099 |
| D | 0 / 0 | Unavailable | Unavailable |

B retains local persistence and C retains the regional reference, so changing XGBoost weights does not alter their errors. C has only nine labelled districts here and still has large errors; D has no valid target cases. None of these panels establishes performance for every current member of its tier.

The any-enrichment group has **7,560 cases / 630 districts**, frozen→retrained 1.716 / 2.831→1.666 / 2.779 m; the other group has 108 cases / 9 districts and unchanged 6.101 / 10.099 m. Here 'enriched' means any accepted added history, not first-ever local history. The sixteen newly local districts have no January 2026 labels, so this diagnostic does not establish their post-refit accuracy. Their limited earlier validation is reported above.

The [history-cohort receipt](retrospective/history_cohorts.json) separately compares added history with substantial original history. The latter requires at least 24 original measured months **through January 2025**, excluding future target counts. Cohorts can overlap and their case counts must not be summed.

| Data cohort | Registered cohort districts | Scored cases / districts | Frozen MAE / RMSE (m) | Retrained MAE / RMSE (m) |
| --- | ---: | ---: | ---: | ---: |
| Any accepted added month | 653 | 7,560 / 630 | 1.716 / 2.831 | 1.666 / 2.779 |
| First-ever local history | 16 | 0 / 0 | Unavailable | Unavailable |
| Substantial original history, ≥24 months | 548 | 6,468 / 539 | 1.705 / 2.822 | 1.646 / 2.759 |

Zero target support for the sixteen first-local districts is explicit absence of validation, not zero error or evidence of reliable transfer.

Among **19 state panels** meeting the existing minimum of 30 cases and ten districts, Punjab, Assam and Karnataka have the largest absolute MAE reductions. Uttarakhand is the sole state in that supported subset with higher MAE. All 31 state panels, including smaller unsupported panels, remain in the JSON. These retrospective rankings did not affect selection.

| Selected state change | Cases / districts | Frozen MAE / RMSE (m) | Retrained MAE / RMSE (m) |
| --- | ---: | ---: | ---: |
| PB | 264 / 22 | 3.112 / 3.745 | 2.932 / 3.552 |
| AS | 360 / 30 | 0.642 / 0.984 | 0.516 / 0.842 |
| KA | 360 / 30 | 1.964 / 2.878 | 1.880 / 2.742 |
| UK | 132 / 11 | 6.301 / 9.924 | 6.409 / 9.956 |

The largest district MAE decreases and increases are shown together. Each has **12 dependent forecasts of one measured target**, not twelve independent measurements; even the improved Gandhinagar panel retains a large absolute error. Complete district MAE/RMSE panels are linked in the summary.

| District | Cases / distinct targets | Frozen MAE / RMSE (m) | Retrained MAE / RMSE (m) |
| --- | ---: | ---: | ---: |
| RJ-Jodhpur | 12 / 1 | 7.210 / 7.447 | 5.919 / 6.049 |
| GJ-Gandhinagar | 12 / 1 | 17.015 / 17.037 | 15.789 / 15.796 |
| RJ-Alwar | 12 / 1 | 2.305 / 2.745 | 1.250 / 1.629 |
| UK-Nainital | 12 / 1 | 2.061 / 2.199 | 3.576 / 3.613 |
| KA-Chikkaballapura | 12 / 1 | 0.772 / 1.141 | 1.628 / 2.278 |
| RJ-Sikar | 12 / 1 | 0.419 / 0.463 | 1.089 / 1.332 |

**Matched prior-release comparison.** The [executed subset proof](retrospective/prior_release_subset.json) verifies all 1,278 February/July-origin case keys, measured targets and frozen predictions match the previous release exactly. Its old `candidate` column meant frozen weights on enriched V3 inputs. This comparison holds those inputs and keys fixed; it does not compare the two-origin average with the twelve-origin average.

| Previous-release matched panel | Cases | Frozen on V3 MAE / RMSE (m) | Retrained on V3 MAE / RMSE (m) |
| --- | ---: | ---: | ---: |
| Both origins | 1278 | 1.802 / 3.025 | 1.729 / 2.969 |
| M+6 | 639 | 1.833 / 3.022 | 1.679 / 2.912 |
| M+11 | 639 | 1.771 / 3.028 | 1.779 / 3.026 |

The matched comparison supports a small retrospective aggregate reduction with an M+11 MAE regression. Previously inspected targets, stable-panel uncertainty and the absent untouched test remain unchanged.

## Selection decision, uncertainty and production safety

The [acceptance decision](acceptance.json) is **`keep_frozen_production`**. Relative validation gains against frozen XGBoost and persistence, seasonal comparison, supported subgroup regression checks, complete contracts and rollback all pass. The sole blocking gate is **absence of a genuinely untouched post-refit test**. The rule requires every gate to pass; inspected retrospective improvements cannot remove that requirement. The candidate is retained for research and prospective verification.

Old empirical radii bind the old model weights. They are not transferred to the refit. Candidate numerical intervals remain **unavailable**; no calibrated local 90% probability is claimed. Observed-origin training does not establish accuracy for a current anchor estimated across stale gaps. Tier B/D persistence and Tier C regional references remain explicitly labelled; zero-history districts do not acquire invented local evidence or XGBoost training labels.

The isolated verification generation is `14544bb9-8ce0-5dfc-b5c7-2907dfc1392b`, as of **27 October 2026**, in `aquaiq_test_retraining_20261027`. It has all **725 districts**, **8,700 finite monthly district outputs**, all **36 states/UTs**, and an evidence mix of **551 A / 116 B / 57 C / 1 D**. This local test-namespace publication is separate from production model promotion. [Candidate identity/contract verification](candidate_contracts.json) binds the stored generation to the new model and final V3 features. State aggregation and legacy six-month contracts passed.

At the conclusion of this experiment, the default pointer SHA-256 remained `1a0dde587ccd6b005a4bac32cbc81105b80ef956052191dbdb5cf2b6bec1e83b`, with unchanged frozen model bytes and running generation `600edc35-506d-501d-82c2-5cc2ebcfe699`. The candidate bundle remains separate from the deployed pointer.

Environment recorded by training: Python **3.13.15**, XGBoost **3.4.1**, NumPy **2.5.4**, pandas **3.0.6**, scikit-learn **1.9.1**, SciPy **1.18.1**. Frontend: Node **22.18.0**, npm **10.9.3**, Vite **8.3.3**. The pinned runtime files are unchanged by this experiment.

## Reproduce, inspect and roll back

The [reproduction guide](../../docs/FINAL_RELEASE_REPRODUCTION.md) contains prerequisites and isolated-publication details. A code-only clone still needs the exact ignored final V3/raw/baseline assets described there. This task reuses accepted local evidence; it does not reacquire a new source revision. Use new output directories so the executed evidence and candidate remain immutable.

```powershell
.\venv\Scripts\python.exe -B -m scripts.audit_retraining_data --feature-directory data/processed/enrichment/final_release_20261026_v3 --output scratch/retraining_data_audit_replay.json

.\venv\Scripts\python.exe -u -B -m scripts.retrain_enriched_xgboost --feature-directory data/processed/enrichment/final_release_20261026_v3 --frozen-checkpoint data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json --output reports/retraining_20261027/replay_training --checkpoint models/artifacts/enriched_retraining_20261027_replay/checkpoint.json

.\venv\Scripts\python.exe -u -B -m scripts.evaluate_retrained_model --features data/processed/enrichment/final_release_20261026_v3 --frozen-checkpoint data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json --candidate-checkpoint models/artifacts/enriched_retraining_20261027_replay/checkpoint.json --added-districts reports/retraining_20261027/gained_history_districts.json --output reports/retraining_20261027/replay_diagnostic --origins 2025-01-31 2025-02-28 2025-03-31 2025-04-30 2025-05-31 2025-06-30 2025-07-31 2025-08-31 2025-09-30 2025-10-31 2025-11-30 2025-12-31

.\venv\Scripts\python.exe -B -m scripts.precompute_forecasts --as-of 2026-10-27 --feature-directory data/processed/enrichment/final_release_20261026_v3 --checkpoint models/artifacts/enriched_retraining_20261027_replay/checkpoint.json --calibration-path scratch/retraining_no_matching_calibration.json --dry-run --export-dir scratch/retraining_candidate_forecasts --output scratch/retraining_candidate_generation.json

.\venv\Scripts\python.exe -B -m pytest --integration --basetemp scratch/pytest-retraining-replay --junitxml scratch/retraining-replay.xml -q
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build
```

The calibration path in this example must remain absent. For the acceptance assessment of a replay, pass the locked protocol, the new replay selection file and its matching contract receipt to `scripts.assess_retraining_candidate`; no diagnostic labels participate in that calculation. The parallel evaluator invokes the same original CLI for disjoint origin chunks and validates model/code identities and the complete merged case set before publishing an aggregate.

As an alternative to the serial diagnostic command, reproduce the three-worker execution with fresh paths:

```powershell
.\venv\Scripts\python.exe -u -B -m scripts.evaluate_retraining_parallel --features data/processed/enrichment/final_release_20261026_v3 --frozen-checkpoint data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json --candidate-checkpoint models/artifacts/enriched_retraining_20261027_replay/checkpoint.json --protocol reports/retraining_20261027/protocol.json --added-districts reports/retraining_20261027/gained_history_districts.json --work-dir scratch/retraining_parallel_replay --output reports/retraining_20261027/replay_diagnostic_parallel --workers 3
```

**Rollback:** no production switch was made, so the original pointer and existing production forecast namespace remain the default. The retained frozen V3 bundle is available at `data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json`. It can be checked without writes:

```powershell
.\venv\Scripts\python.exe -B -c "from models.climate_forecast_12m import load_bundle; _, card = load_bundle('data/processed/enrichment/final_release_20261026_v3/frozen_bundle/checkpoint.json', expected_generation='physical-v3-official-c9ade81d95720f91'); assert card['model_sha256'] == '4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03'"
```

To leave a candidate-only API session, restore that session's previous `AQUAIQ_FORECAST_SCHEMA` and retain its original checkpoint configuration. Do not replace the deployed pointer with an experimental pointer or reuse old-model calibration with new weights. Same-seed refit, saved-model reload, frozen-input preservation and backup loading are checked by the executed trainer and tests.

## Remaining limits and next experiment

The remaining scientific blocker is an independent later observed test period with documented source availability. Other limits include changing station/datum panels, seasonal sampling, missing/currently stale weather, omitted pumping/extraction, weak geographic transfer support and uncertain estimated anchors. Eight newly local districts do not contribute final-fit pairs, and newly local validation is too small to establish local skill. No historical average is a present-district accuracy guarantee.

The next experiment should freeze this candidate and prespecify prospective forecast issuance, later measurement collection, stable panel/datum checks and evaluation before inspecting those outcomes. New interval calibration would require independent matching residuals for the new weights. Until that evidence exists, the candidate stays an experimental artifact and the frozen release remains production.
