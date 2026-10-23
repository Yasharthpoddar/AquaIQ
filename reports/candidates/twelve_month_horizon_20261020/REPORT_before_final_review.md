# Experimental twelve-month groundwater forecasting — 20 October 2026

**Decision 1: keep six months as the existing primary research horizon and twelve months exploratory.** A genuine M+12 implementation and historical backtest were executed. Twelve-month XGBoost has a small pooled point advantage over its baseline, but uncertainty crosses zero and the advantage fails geographic/panel and temporal sensitivities. No model was selected or promoted. This decision preserves the existing application contract; it does not certify six-month production accuracy.

## Implementation and isolation

Verified baseline: local `main` and GitHub `main` were both **`98c7056057b2a0370d377afa831f528f6d408481`**. The requested branch did not exist locally or remotely; `experiment/12-month-horizon` was created from that commit. Existing untracked work was retained. The experimental branch is **local and uncommitted**; no staging, commit, push, deployment or remote branch creation occurred.

Four new source/test files implement the experiment:

- [models/research_horizon.py](../../../models/research_horizon.py): exact calendar targets, explicit provenance, embargo splits, isolated write-once models/cards and horizon-aware loading. The helper's default is six months; production code remains untouched.
- [scripts/backtest_twelve_month.py](../../../scripts/backtest_twelve_month.py): offline cohort preparation and fixed-parameter twelve-month backtest.
- [tests/test_research_horizon.py](../../../tests/test_research_horizon.py) and [tests/test_twelve_month_backtest.py](../../../tests/test_twelve_month_backtest.py): target, leakage, compatibility, common-case, uncertainty and preservation contracts.

All new models, cohorts, predictions, logs and reports are under this directory. No existing tracked source, dataset, report, configuration, active checkpoint/pointer, ANN/MLP, Fuzzy Logic, application endpoint or database/schema was changed. The running application retains its six-month behavior. ANN's fuzzy-label classification was not treated as depth regression. No new model family or dependency was introduced.

[Preservation verification](preservation.json) found **853/853 existing files unchanged**, including previously untracked research evidence, retained datasets, active models/cards, historical model artifacts and prior reports. Both local `main` and experiment HEAD still resolve to the baseline commit; the index remains empty. Git does not preserve these new untracked research outputs automatically; do not discard them during a later checkout/cleanup. No database connection or write was made by the experiment; database contents were not independently checksummed.

## Frozen design and what was actually fitted

[Protocol](protocol.json) was frozen before fitting at `2026-10-20T10:51:44+00:00`; SHA-256 **`1a93abf0a52eb44263d05090137df2c7000f83c3d0cf2c3e2843c56ac1ec57c2`**. A create-only [implementation clarification](protocol_implementation_addendum.json) explicitly names the new CLI runner without changing settings/cohorts. [Cohort/code lock](cohorts/lock.json) was saved before fitting. All source/input/code/cohort hashes still match. No tuning, early stopping against evaluation data, model ranking for deployment, or outcome-driven exclusion occurred. The evaluation is chronologically held out from these fits, **not a pristine blind test**: some target periods were previously inspected in six-month research.

- Target: exactly origin month **M+12**, joined on district/calendar month. Missing, imputed or unknown-provenance targets remain missing. Observed origin/target flags describe provider-reported monthly values, not independently certified field acquisitions.
- Persistence and standard annual seasonal naive are **one effective baseline**: `target−12 = origin`. Their predictions and eligibility were verified identical on every common case. They are not two independent benchmarks. No additional climatological baseline was introduced.
- Inputs: existing physical-unit twelve-feature direct schema (including 3/6-month groundwater lags) and known-origin month sine/cosine for HGB. Existing causal LOCF ≤3 months may support training origins, never target labels. Existing weather and its missingness are copied unchanged. No future weather, scaling, fitted imputation or future panel membership enters the models.
- XGBoost: fixed existing 500 trees, depth 6, learning rate .01, subsample .8, seed 42; absolute depth target. OLS: existing per-district LinearRegression with intercept, ≥12 complete training pairs; no learned scaling/imputation. HGB: installed sklearn, prior fixed settings (250 iterations, .05 learning rate, 31 leaves, leaf minimum 50, L2 20, seed 42, early stopping false), twelve-month depth-change target added to origin and clipped at zero. It is a **new, separately fitted regional research comparator**, not the six-month selected HGB or an approved shadow artifact.
- All four reported methods use the exact pre-frozen common cases: observed references, finite shared inputs and sufficient OLS training support. Nonfinite predictions would fail execution rather than trigger model-specific case deletion.

| Target year | Training-label cutoff | Earliest evaluation origin | Full XGB/HGB training pairs | Full OLS complete pairs | Strict XGB/HGB / OLS pairs |
|---|---|---|---:|---:|---:|
| 2024 | 2021-12-31 | 2023-01-01 | 5,410 | 5,212 | 164 / 158 |
| 2025 | 2022-12-31 | 2024-01-01 | 5,806 | 5,608 | 176 / 170 |
| 2026 | 2023-12-31 | 2025-01-01 | 6,202 | 6,004 | 188 / 182 |

Twelve complete calendar months separate the cutoff month and earliest evaluation origin. XGB/HGB use native missing-value handling for training; OLS uses only complete rows. See [actual fit log](evaluation/execution.json). There are **18 model/card bundles** (three families × three annual folds × two data definitions); OLS bundles contain separate district estimators. No six-month model was loaded as a twelve-month estimator.

All 18 saved bundles were reloaded through the strict research loader and reproduced archived predictions within `1e-8 m`. Checks reject horizon/schema/units/protocol/hash/path mismatches before estimator deserialization, including the active six-month card as a twelve-month candidate. Cards include horizon/embargo 12, training cutoffs, feature order/hash, model hash, source/configuration/code hashes and research-only/unapproved-shadow status. [Verification](result_verification.json) records the actual results.

## Data, geographic limitations and common cases

No new data was downloaded. Inputs are the retained official Telangana source and corrected normalized research data, with the existing weather release. The accepted source contains **188,458 records and 1,764 provider IDs**. Explicit source units are metres below ground level. Measuring-point/datum continuity, replacements and fresh acquisition remain uncertified.

Of accepted rows, **125,400** have a resolvable name/polygon conflict, **58,034** have unresolved district names, and only **5,024** have exact name/polygon agreement. **All 792 primary target panels contain a conflict**; their mean conflicting-well share is **65.803%**, with another **29.674%** unresolved. Some readings exceed listed well depth in 106 primary target panels. These records were retained in the full analysis, not removed because of errors. No coordinates or well identities were guessed or corrected.

The strict sensitivity filters each well-month for exact nonmissing source-name/polygon agreement, then **separately reaggregates and rebuilds causal features**. Its different target/panel is never scored using full-panel district predictions. Agreement of two metadata fields is not authoritative location verification. Other strict districts first appear too late for embargoed OLS support; only Adilabad supports the full comparison.

| Cohort | Registered / observed reference pairs | Common cases / districts | Origin range | Target range |
|---|---:|---:|---|---|
| Full conditional primary | 792 / 792 | **792 / 33** | 2023-01–2024-12 | 2024-01–2025-12 |
| Full identical origin/target panel diagnostic | Subset of primary | **380 / 32** | Same primary span | Same primary span |
| Exact-agreement reaggregation, primary | 144 / 116 | **24 / 1** | 2023-01–2024-12 | 2024-01–2025-12 |
| Full later period | 165 / 165 | **66 / 33** | 2025-01–2025-02 | 2026-01–2026-02 |
| Exact-agreement later period | 30 / 30 | **2 / 1** | 2025-01–2025-02 | 2026-01–2026-02 |

The later registered target period extends to May 2026. Its **99 March–May cases** have observed groundwater references but missing common weather inputs, so no method receives a more favorable comparison subset. The January–February 2025 temperature/evapotranspiration inputs are existing two-month carries of December 2024 values, **not fresh 2025 ERA5 observations**; [weather-tail audit](weather_tail_audit.json) confirms all 66 rows. No new weather filling was introduced.

The identical-panel subset uses target membership after labels arrive, under a rule fixed before errors; it is a retrospective composition diagnostic, not an issuance-time eligibility rule. Its hash checks provider identities and weights, not physical replacement/datum continuity. Strict sensitivity changes training data and population, so it does not identify the causal effect of location errors.

Actual source-prefix rebuilds through December 2022 compared **6,204 full-grid rows and 188 strict-grid rows**: all 14 earlier features and observation flags were unchanged when later source rows were removed. See [cohort counts](cohorts/cohort_counts.csv), [quality/prefix audit](cohorts/data_quality.json), [target panel QC](target_panel_quality.csv) and frozen full/strict case inventories under `cohorts/`.

## Primary results: 792 identical cases

Depth errors and bias are metres; bias = prediction minus observation. R² is explained variance on this cohort, not an accuracy percentage.

| Method | MAE | RMSE | Bias | R² | Absolute-error p95 | Maximum error |
|---|---:|---:|---:|---:|---:|---:|
| Persistence = annual seasonal naive | 1.191 | 1.458 | −.242 | .721 | 2.700 | 4.707 |
| Expanding XGBoost | 1.159 | 1.420 | +.457 | .736 | 2.499 | 5.637 |
| Per-district OLS | 1.928 | 2.456 | +1.512 | .210 | 4.914 | 7.890 |
| Separate fixed twelve-month HGB | 1.222 | 1.505 | +.494 | .703 | 2.809 | 6.240 |

XGB's pooled RMSE point gain is **.0378 m / 2.59%**, but its absolute bias is larger. It is not selected as a winner. There are 0/1/39/2 errors above 5 m for baseline/XGB/OLS/HGB; no primary error exceeds 10 m. Full quantiles and counts remain in [metrics](evaluation/metrics.json).

Paired 95% percentile intervals below use 2,000 district × circular twelve-month-block resamples, seed 42. Negative MAE/RMSE differences favor the model. Signed bias differences have no universally favorable direction.

| Method | RMSE interval | MAE difference vs baseline | RMSE difference vs baseline |
|---|---|---|---|
| Baseline | [1.098, 1.786] | [0, 0] by identity | [0, 0] by identity |
| XGBoost | [1.223, 1.585] | [−.359, +.272] | **[−.317, +.264]** |
| OLS | [1.877, 3.000] | [+.310, +1.222] | [+.457, +1.568] |
| HGB | [1.313, 1.673] | [−.269, +.297] | [−.207, +.321] |

District-only XGB RMSE-difference interval also crosses zero: [−.124, +.056] m. [Uncertainty output](evaluation/uncertainty.json) includes each model's MAE/RMSE/bias intervals and both resampling methods. Only two annual target cycles and 33 dependent regional districts exist; intervals are descriptive, unadjusted for multiplicity and not prospective/predictive confidence. Single-district/two-month strict intervals can be degenerate and do not establish generalization.

## Geographic, weighting and temporal sensitivity

RMSE on the same cases within each row:

| Cohort | Cases | Baseline | XGBoost | OLS | HGB |
|---|---:|---:|---:|---:|---:|
| Full primary | 792 | 1.458 | 1.420 | 2.456 | 1.505 |
| Identical origin/target panels | 380 | **1.383** | 1.437 | 2.256 | 1.502 |
| Exact-agreement reaggregation, Adilabad | 24 | **.877** | 2.518 | 1.905 | 1.883 |
| Full complete later cases, Jan–Feb 2026 | 66 | 1.490 | 1.203 | 1.603 | 1.257 |

The two strict later cases have baseline/XGB/OLS/HGB RMSE 1.567/1.186/.272/2.510 m; their tiny sample and unstable R² do not support a performance claim. No subgroup was used to change the locked settings or declare a new model winner.

| Primary RMSE weighting | Baseline | XGBoost | OLS | HGB |
|---|---:|---:|---:|---:|
| Pooled | 1.458 | 1.420 | 2.456 | 1.505 |
| Arithmetic mean of district RMSEs | 1.407 | 1.386 | 2.198 | 1.479 |
| Arithmetic mean of calendar-month RMSEs | 1.439 | 1.398 | 2.423 | 1.478 |

MAEs are unchanged by macro weighting because the primary cohort has equal cases per district and per calendar month. Group R² values are not averaged. XGB has lower RMSE in 20/33 districts and 8/12 calendar months, but loses in September–December. OLS wins RMSE in 7 districts and no calendar month; HGB wins in 16 districts and seven months. These are descriptive counts under uncertain geography.

The temporal ordering reverses: in **2024**, baseline/XGB RMSE is **1.628/1.335**; in **2025**, it is **1.265/1.500** (396 cases each). OLS/HGB 2024 RMSE is 2.808/1.468 and 2025 RMSE 2.044/1.542. [Complete district/month/year/target-period breakdowns](evaluation/group_metrics.csv) contain all four methods, MAE/RMSE/bias/R² and error distributions; [group highlights](group_comparison_highlights.json) records the comparison counts.

At the well level, the metadata-matched annual baseline has **38,496 primary pairs / 1,683 provider IDs**, MAE **2.154**, RMSE **3.464** m. Exact name/polygon agreement at both dates leaves **1,554 pairs / 74 IDs**, MAE **2.527**, RMSE **4.653** m. These avoid district-weather assignment but still lack certified well/datum continuity and freshness. They are baseline-only well analyses, not ML evaluation, and their errors cannot be compared to smoother district means as an accuracy contest. See [well metrics](evaluation/well_baseline_metrics.csv); original observations are retained.

## Six versus twelve months

The original six-month primary result remains historical context: 594 cases, seasonal naive 1.440 m RMSE, expanding XGB 1.472, locked historical HGB 1.790. The primary twelve-month cohort has additional targets and a different horizon; its 792-case metrics are **not** a controlled comparison to that table.

A separate inner join matches the same **594 district/target observations, January 2024–June 2025**:

| Method/reference | Six months RMSE | Twelve months RMSE |
|---|---:|---:|
| Origin persistence | 3.733 | 1.440 |
| Annual seasonal reference | 1.440 | 1.440 (same value as twelve-month persistence) |
| Expanding XGB | 1.472 | 1.318 |
| Per-district OLS | 1.752 | 2.514 |

The twelve-month origin is six months earlier, and its embargoed training cutoffs are older. Thus this matches outcomes but not feature origins/training membership; it does not isolate a horizon effect. The matched XGB twelve-minus-six RMSE interval is **[−.343, +.060] m**, crossing zero. The large persistence improvement merely changes the seasonal phase of its reference; twelve-month persistence equals saved six-month seasonal naive row by row.

A different join matches **594 origins, July 2023–December 2024**, but the outcomes differ: twelve-month XGB RMSE is **1.478** versus six-month **1.472**. This is also not a controlled accuracy comparison. No six-month model was retrained. See [comparison context](evaluation/six_vs_twelve_context.json), [paired intervals](evaluation/six_vs_twelve_uncertainty.json) and the two `six_vs_twelve_same_*.csv` row exports.

## Issuance timing and lead claim

All accepted source values lack populated actual acquisition, first-publication, first-receipt and availability timestamps. Provider-reported dates/month labels do not certify fresh field acquisition. Current-vintage historical inputs may include revisions; no contemporaneous issuance archive exists.

The implementation genuinely targets **M+12**, but cannot certify **twelve full months from issuance to target acquisition**. For example, January-origin whole-month weather generally cannot be complete before February; a target reported as next January 1 would then have about eleven months of lead, before considering publication/receipt delays. Unknown actual target acquisition days prevent assigning an exact operational lead. No horizon, features, dates or labels were shifted to make this appear feasible. Any future change to an issuance-relative target or feature-availability protocol needs a separate human decision and a new frozen study.

All row predictions are labelled retrospective current-vintage results with `forecast_issued_at=null`; no real/synthetic shadow records or prospective forecasts were created. HGB real-shadow abstention remains unchanged. Nationwide skill, calibrated crisis probabilities, causal extraction effects and production readiness remain unverified.

## Tests, actual execution and reproduction

- **74 new tests passed** in the final focused run (55 horizon/artifact tests + 19 evaluator tests), with fitting/DB guards and synthetic unit fixtures only. Final [JUnit evidence](final_tests.xml) is separate from real-data backtest outputs.
- **76 existing six-month regressions passed**, one skipped because Windows symlink creation requires privileges, and three real-fitting tests deliberately deselected. See [six-month JUnit](six_month_regressions.xml).
- The first new-test run had 38 passes and 11 sandbox TEMP setup errors; fresh workspace-local `--basetemp` paths resolved these. All original XML evidence remains retained. Repeated test runs are not counted as additional unique tests: **150 unique passes**, one skip.
- Source syntax/whitespace checks passed; `git diff --check` passed. Cohort preparation, actual backtest and 18-model reload/metric verification all exited 0. [prepare.log](prepare.log), [backtest.log](backtest.log), [verification.log](verification.log), [execution metadata](evaluation/execution.json) and [result verification](result_verification.json) preserve outcomes. No unrestricted suite, database operation, source download, active model fit, checkpoint publication, commit or push occurred.
- Primary/secondary and strict [row-level predictions](evaluation/full_coordinate_predictions.csv) and [strict predictions](evaluation/exact_name_coordinate_predictions.csv) retain case IDs, inputs, observed labels, missing/exclusion reasons, train cutoffs, model hashes, nominal horizon and retrospective timestamps. All comparison methods use the frozen common membership.

Exact commands and safe fresh-directory reproduction instructions are in [COMMANDS.md](COMMANDS.md). Local source/runtime inputs listed in the protocol are required; a GitHub clone alone does not include them. Use the recorded environment versions. Existing outputs deliberately refuse overwriting.

**Final decision 1: keep six months as the primary horizon and twelve months exploratory.** There is enough data and implemented infrastructure for further conditional historical research, but no reliable twelve-month ML advantage or verified issuance-lead claim, and no basis to replace the existing horizon or start real shadow evaluation.
