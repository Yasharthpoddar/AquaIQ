# AquaIQ — safe reporting fixes and shadow readiness, 2026-10-19

**Decision: continue research-only shadow preparation.** F6/F10 are corrected within the authorized reporting/documentation scope. No training, tuning, selection, promotion, new forecast, database access, ingestion or artifact regeneration occurred. No new forecasting-accuracy claim is made. Real HGB remains in abstention mode; this task prepares a plan, not an operational shadow campaign.

## Initial verification and changes

The complete [authoritative audit](C:/Users/Yasharth/Downloads/AquaIQ/reports/scientific_validation_audit_20261018/REPORT.md) was read, and current source/metadata were checked again after the pause. Branch `main`, commit `fc7fdcf20d9f8eb8991dc509b7d581168058de3e`, no tracked changes at task entry. Fourteen untracked files already existed under the October 18 scientific audit directory; all are preserved. [before.json](C:/Users/Yasharth/Downloads/AquaIQ/reports/post_audit_safe_fixes_20261019/before.json) records the snapshot state, existing-file hashes and active bundle identities. Its status includes this task's newly created preservation helper.

| Finding | Verified initial state | Confirmed change |
|---|---|---|
| F6: inconsistent R² | OLS called `r2_score` directly, yielding finite replacements for constant targets; shared evaluation already returned null for singleton/constant/numerically unresolved targets. | [linear_regression.py](C:/Users/Yasharth/Downloads/AquaIQ/models/linear_regression.py) now maps shared metrics to its existing four-decimal `r2`, `rmse`, `mae` columns. Undefined R² stays `None`/blank CSV. Summaries retain null when no value is available, count unavailable entries separately and omit them from rankings. A genuinely defined zero/negative R² remains meaningful. |
| F10: ANN input comments | Comments said ten inputs, although runtime derives twelve ordered canonical columns: nine numerical signals and three crop indicators. | [ann_classifier.py](C:/Users/Yasharth/Downloads/AquaIQ/models/ann_classifier.py) docstrings now describe the current twelve-input schema. Executable code, input order and model settings are unchanged. |
| F10: OLS split/scope comments | Header claimed a fixed 2023–2024 test and that these models supplied the serving trend. Actual split uses configured label cutoff and `heldout_origin_start` through configured origin end; serving trend is separate. | OLS header now describes the actual contract. Current configuration implies earliest held-out origin **2022-07-01**: the later of the six-month embargo boundary and configured final-label start minus six months. Actual usable rows still depend on observed targets and complete features. No split was changed. |
| F10: historical generation identity | Preserved climate review identifies `physical-v3-causal-monthly-90a24f1f2574`; current manifest/card/evaluation identify `physical-v3-causal-monthly-a3f9468a2569`. | [README.md](C:/Users/Yasharth/Downloads/AquaIQ/README.md) now explains that reports verify only their recorded generation and identifies which metadata to compare. The old report and its identifiers remain byte-identical. |

**Already working / no reapplication:** shared float64-resolution R² semantics; runtime ANN schema derivation; current monthly card/evaluation generation agreement; immutable historical review identity; real-HGB abstention. Neither F6 nor the requested F10 comment discrepancies had already been fixed. The old climate review itself is valid historical evidence, not a corrupt artifact to relabel. Unused planning fields in configuration were left intact; changing configuration is unnecessary for these fixes and would alter a frozen configuration hash.

OLS estimator construction, feature selection, complete-case filtering, district eligibility, fit/predict calls and split arguments are unchanged. Future execution of the standalone reporting script will display the corrected null semantics; no stored result was regenerated. ANN executable AST is unchanged after removing docstrings. Serving APIs, scoring, feature engineering and shadow implementation were not edited.

## Targeted verification

Executed from the repository root:

```powershell
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_post_audit_reporting.py tests/test_post_audit_metadata.py tests/test_forecast_metric_precision.py --basetemp=scratch/pytest-post-audit-safe-fixes-20261019 --junitxml=reports/post_audit_safe_fixes_20261019/targeted-tests.xml
```

**33 passed in 12.31 seconds; no failures.** [Test XML](C:/Users/Yasharth/Downloads/AquaIQ/reports/post_audit_safe_fixes_20261019/targeted-tests.xml) retains the actual execution.

- Nineteen new reporting cases cover constant/perfect-constant, singleton, adjacent float values, small but resolvable variance, ordinary/perfect/zero/negative R², four-decimal errors, rejected empty/nonfinite arrays, null/mixed/empty summaries, unavailable rankings, and blank R² CSV cells. Output tests redirect exclusively to pytest temporary paths using synthetic district labels.
- Three metadata cases check twelve encoded ANN inputs, truthful OLS split documentation, and separate historical/current climate identities. Metadata reads do not deserialize estimators or evaluate forecasts. Model fitting/prediction, training factories, production feature loading and database entry points are guarded in the new tests.
- Eleven existing metric-precision cases use fixed arrays only. The unrestricted suite was not run because other files fit estimators.

Additional executed checks: `git diff --check`; active pointer/model/card checksum validation; protected-file hash comparison; static AST comparison confirming ANN executable code and the OLS per-district processing prefix through `predict` are unchanged. No production dataset was loaded by tests; the preservation helper reads bytes only. No database connection, source download, estimator fit or model-selection operation was invoked. No new ledger, fixture timestamps, well IDs, label outcomes or forecast records were created. Tests' fixed prediction arrays are metric fixtures, not model forecasts.

To repeat the targeted tests without replacing this evidence or reusing its temporary directory:

```powershell
Set-Location C:\Users\Yasharth\Downloads\AquaIQ
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_post_audit_reporting.py tests/test_post_audit_metadata.py tests/test_forecast_metric_precision.py
.\venv\Scripts\python.exe -B reports/post_audit_safe_fixes_20261019/verify_preservation.py verify --check-only
git diff --check
```

The helper's `snapshot` and `verify` creation modes use exclusive writes; use `verify --check-only` to repeat integrity checks without replacing either manifest. Do not run model-training, ingestion or ledger-recording commands as part of this verification.

## Preservation and exact active identities

**629 pre-existing files checked; 626 unchanged; only three authorized existing files changed:** README, ANN comments and OLS reporting/comments. All **110 data files**, **18 checkpoint files** and **309 previous report/evidence files** are byte-identical. This includes the fourteen pre-existing untracked audit files, model-card copies, selection locks, synthetic demo records and all completed experiments. No additional file was introduced in the protected directories outside this new report directory.

[after.json](C:/Users/Yasharth/Downloads/AquaIQ/reports/post_audit_safe_fixes_20261019/after.json) records before/after active hashes and the three permitted source diffs. Hashes establish file integrity; source/command review and test guards establish the absence of fitting, forecast issuance and database operations.

| Active artifact | SHA-256 before **and** after (identical) |
|---|---|
| Direct XGB pointer | `e6722ef6cb77242ba982a5763a0ff28499a05d93147df30828ab822bbf26ff92` |
| Direct XGB model | `ef58264b9c1fa43f727fef9d4d180e59f091c9778eb48f128f2ab81d40a97789` |
| Direct XGB bundle card | `aee8c2862268af07300f563a7582ea7cb218d1b74bb729b7bbb2d1341a1e01ee` |
| Monthly-climate pointer | `59827055a401dee258e8ab9d2c1d7e81bfaab3bf8240f10bd5798f882f52ec43` |
| Monthly-climate model | `54f535f57bcd62f0bea38cf5c545eb253b37d5bdd6bae1794ec27a3e73a43d97` |
| Monthly-climate bundle card | `e9885a71e00c0a1eabaddf3ed850257740293ddbec8ddba2a58a41cdc820a813` |

Resolved bundle paths are retained in both manifests. Configuration, preprocessing, active model settings, production predictions, database/schema and serving behavior are unchanged. The only behavioral change is the explicitly authorized standalone OLS reporting correction. No commit or push was made.

## Prospective shadow-readiness checklist — plan only

Roles below identify responsibilities, not assigned people or approved work. Every unresolved gate must be satisfied and reviewed before the dependent step; no missing metadata may be invented or inferred from file modification dates.

| Requirement / accountable boundary | Available evidence | Missing prerequisite / gate | Safe next action |
|---|---|---|---|
| **1. Well identity, datum, replacements, aggregation** — data steward + groundwater specialist; ingestion/crosswalk boundary | Legacy station-name/coordinate proxies, district crosswalk and raw lineage; January update station means; ledger panel hash/weights. | Provider-stable well IDs, relocation/replacement and aquifer/screen histories, measuring-point/ground datum, units/freshness certification; one defensible aggregation policy. Legacy reading-weighted and newer station-weighted aggregates differ. | Obtain a provider data dictionary and retained per-well evidence. Propose versioned identity/datum/aggregation rules for review; preserve old labels and datasets. Do not substitute a name/location proxy as a certified ID. |
| **2. Acquisition versus republication and source vintages** — source custodian + future export adapter | Some reported measurement dates, source hashes and local retrieval manifests. Ledger validates timezone-aware timestamp ordering. | Certified acquisition window/freshness, provider first publication, local receipt, per-value availability and complete revision history, including feature dependencies. Reported dates/retrieval are not proof of historical availability. | Obtain real provenance and source bytes. Specify adapter validation for acquisition/period-end/publication/receipt/availability order and version identity; reject unprovable or late inputs. No timestamps fabricated, backdated or filled from month indexes. |
| **3. Registered panels and completeness** — scientific owner + panel registry boundary | Canonical district IDs; ledger panel version, weights, datum/geography hash, registration time and label-panel compatibility checks. | Approved districts/aquifers/months, exact well membership/weights, replacement and completeness rules, missingness/exclusion policy fixed before outcomes. | Draft and review a preregistration using real identities after gates 1–2. Require the complete issued panel for primary labels. Retain partial-panel/missing cases separately; never choose a favorable matched-well intersection after outcomes. |
| **4. Issuance and immutable archives** — operations owner; file-ledger/archive boundary | Existing create-only forecast/label/evaluation transactions, duplicate-slot protection, hash/commit checks and explicit abstentions. | Trusted clock, externally anchored or write-once retention, restricted writers, archived source bytes, monitored backups and approved upstream adapter. Local hashes alone are insufficient against privileged replacement. | Review a minimal isolated retention/clock/recovery design, including interrupted-write handling. Preserve prediction/input/model/config/source hashes and abstentions. No new campaign, forecast or integration is created now. |
| **5. Exact lead and input availability** — forecasting owner; feature contract/issuance boundary | Exact origin+6 target and target−12 seasonal reference; ledger rejects late inputs and distinguishes nominal from six-full-month evaluation. | Feasible actual issuance schedule and target-acquisition window. Complete origin-month weather generally arrives too late for six full months to that nominal target. | Register the exact claim and effective-lead calculation. Resolve infeasibility before issuance through a separately approved protocol; do not shift targets, substitute weather or change features to manufacture lead. Confirm every dependency is available before issue. |
| **6. Independent observed labels and both baselines** — measurement steward + evaluator boundary | Observed-label checks, immutable revisions, panel matching and paired-case evaluation; real HGB currently abstains. | Newly acquired independent target observations, certified units/datum, complete panel, observed origin and exact prior-year seasonal reference available at issue. No completed eligible prospective three-way skill cohort. | Design a no-overwrite label intake/adjudication procedure. Primary comparisons use identical eligible cases for fixed ML, persistence and seasonal naive. Report all registered/issued cases, missing labels, delays, absent baselines and abstentions alongside paired scores. Keep backfills and revision sensitivity separate. |
| **7. Preregistered analysis and adequacy** — scientific/statistical reviewer; protocol boundary | Saved historical cohort diagnostics, district bootstrap and known district/month concentration. | Scope, primary metric, pooled/district/calendar weighting, practical benefit/harm margins against both baselines, uncertainty/multiplicity method, sample-size/precision and independent temporal/geographic coverage requirements. | Use development-only cluster-aware power/precision work and decision costs to draft requirements before new labels; account for shared districts and contiguous periods. Set one analysis date, no favorable stopping or test-driven retuning/reselection. Prior 500/50/5% planning proposals are not approved universal gates or demonstrated sufficiency. |
| **8. Independent crisis-outcome calibration** — domain adjudication + crisis-validation boundary | Project-defined 0–100 risk index, uncalibrated weights, ANN fuzzy-label imitation, existing disclosure/readiness checks. | Independent observed crisis definition, adjudicated outcomes, calibration and external validation protocol. Depth skill or fuzzy agreement cannot establish crisis probability. | Draft outcome criteria and a separate approved evaluation plan. Retain project-index wording; do not claim probability, official tiers or real-world crisis accuracy. No training/calibration implemented. |
| **9. Isolation, rollback and human approval** — ML artifact owner + operations/release reviewer | HGB selection lock, preserved production bundles, isolated ledger interface, no approved final HGB binary; code enforces `shadow_artifact_not_approved`. | Explicit approval for an isolated deterministic artifact workflow, reproducible frozen model/preprocessing state and later inference adapter; reviewed rollback and operational gates. | Keep HGB abstaining. If approved later, build only the fixed candidate in isolation with its exact training cutoff/settings, freeze and verify artifacts, then review shadow inference separately. Any production promotion needs fresh preregistered evidence, rollback tests and explicit human approval; never alter production pointers automatically. |

The frozen research identity remains `hist_gradient_boosting-2-delta`, training-label cutoff **2018-12-31**, **14,817** original eligible pairs, seed 42, `early_stopping=False`, max_iter 250, learning_rate .05, max_leaf_nodes 31, min_samples_leaf 50 and l2_regularization 20. No artifact build, refit, inference adapter or change to abstention is authorized by this report.

**Dependency order:** resolve source identity/datum/vintages and issuance feasibility → preregister panels/analysis and approve isolated artifact workflow → review frozen shadow adapter/archive → collect real issue-before-acquisition evidence → conduct the scheduled confirmatory analysis → consider a separately approved promotion review. Insufficient evidence means continued research; a running ledger or passing unit tests cannot satisfy scientific gates.

## Changed and added files

Existing files changed: `models/linear_regression.py` (F6/reporting and F10 header), `models/ann_classifier.py` (F10 comments only), `README.md` (generation citation guidance).

Added tests: [test_post_audit_reporting.py](C:/Users/Yasharth/Downloads/AquaIQ/tests/test_post_audit_reporting.py), [test_post_audit_metadata.py](C:/Users/Yasharth/Downloads/AquaIQ/tests/test_post_audit_metadata.py). Added evidence in this new directory: `REPORT.md`, `verify_preservation.py`, `before.json`, `after.json`, `checks.json`, `targeted-tests.xml`. No unrelated source refactor or dependency was introduced.

**Final recommendation:** continue research-only shadow preparation. Real issuance and any promotion remain blocked on the explicit prerequisites above. Existing models, data, model cards, databases and production behavior were preserved; this task supplies corrected reporting and a reviewable plan only.
