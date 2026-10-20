# Academic submission finalization

**2026-10-19 — research prototype; no claim of production readiness.** Starting checkout: `main` at `905f3c32304fa196015b8cd3113ec77f6b0a7d84`, with a clean Git working tree. This pass made presentation and documentation corrections only. It did not train, tune, select, promote or invoke a forecast, start shadow evaluation, download data, install dependencies, connect to the database, commit or push.

Read before editing: [scientific validation](../scientific_validation_audit_20261018/REPORT.md), [safe fixes](../post_audit_safe_fixes_20261019/REPORT.md), and [provenance/issuance feasibility](../provenance_issuance_20261019/REPORT.md). Those reports and their evidence remain unchanged.

## Evidence presented faithfully

The [README](../../README.md) now presents the saved primary historical benchmark on the same **209 observed-flag cases across 32 districts**: origins July 2019–September 2022, targets January 2020–March 2023. These are existing candidate results, not a new evaluation of the current dashboard serving path.

| Existing method | MAE (m) | RMSE (m) | R² |
|---|---:|---:|---:|
| Persistence | 1.234 | 3.698 | .809 |
| Seasonal naive | **1.049** | **2.132** | .937 |
| Ridge | 1.381 | 2.573 | .908 |
| Random Forest | 1.290 | 2.558 | .909 |
| XGBoost candidate | 1.432 | 3.225 | .855 |
| Locked HGB candidate | 1.327 | 3.060 | .869 |

Seasonal naive beats HGB and every tested ML candidate on primary MAE and RMSE. HGB was selected using validation; this finalization does not reselect a model. Its RMSE difference versus persistence has a district-bootstrap 95% interval of −1.234 to +.038 m, crossing zero, and its primary MAE is worse. R² is not an accuracy percentage. This previously inspected historical cohort has uneven sampling and uncertain well composition and acquisition freshness; it does not establish blind prospective performance. See the preserved [experiment report](../candidates/six_month_selection_20261017/REPORT.md) and scientific audit.

## Modified files

Every modified pre-existing file is listed below. API contracts, requests, route handling, calculations, slider ranges, model settings, feature definitions and forecast horizons were preserved.

| File | Presentation correction |
|---|---|
| `README.md` | Research scope, saved benchmark, observation/fill/estimate/projection distinctions, no-go status, runtime-asset limitations and safe verification guidance. |
| `api_spec.md` | Research endpoint terminology; calendar labels versus acquisition/availability; uncalibrated index and noncausal sensitivity disclosure. |
| `docs/phase2_eval/README.md` | Banner identifies historical design targets and demo descriptions as plans rather than verified evidence. |
| `docs/prospective_shadow.md` | Current no-go banner; interface examples and earlier proposed thresholds do not authorize issuance. |
| `dashboard/index.html` | Research-prototype page title. |
| `dashboard/src/App.jsx` | Shared static research-limitations notice. |
| `dashboard/src/components/MapComponent.jsx` | Project-index and district-history estimate labels. |
| `dashboard/src/pages/Home.jsx` | Registry versus observation coverage; historical benchmark; source-month and estimate labels. |
| `dashboard/src/pages/DistrictDetail.jsx` | Source-marked monthly means, fills, estimated depth and weather-assumed projections distinguished. |
| `dashboard/src/pages/Alerts.jsx` | Research indicators, project index and model factors; no official-advisory implication. |
| `dashboard/src/pages/Simulate.jsx` | Rainfall/extraction sensitivity terminology; heuristic extraction effects are not causal policy estimates. |

The crisis score is consistently described as a **project-defined, uncalibrated risk index**, not a probability or official risk classification. ANN agreement with fuzzy-generated labels is not independent crisis-outcome accuracy. Working features, unavailable states and error handling remain available.

New evidence is confined to this report directory: `FINALIZATION.md`, `before.json`, `checks.json`, `preservation.json`, `metadata-tests.xml` and `metadata-final.xml`. The compiled frontend check is a separate ignored scratch artifact, not a dataset or forecast record.

## Safe checks executed

Commands were run from the repository root in the existing environment, without installation or network requests:

```powershell
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir C:/Users/Yasharth/Downloads/AquaIQ/scratch/submission-build-20261019
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_post_audit_metadata.py --junitxml=reports/submission_finalization_20261019/metadata-tests.xml
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_post_audit_metadata.py --junitxml=reports/submission_finalization_20261019/metadata-final.xml
git diff --check
```

Results: **11 offline frontend tests passed; 3 metadata tests passed**, with the same metadata suite repeated after the last README change. These are 14 unique test cases. Lint, isolated build and whitespace checks passed. Tests use mocks/local map data or guarded metadata reads; no estimator fitting or forecast execution was requested. The build reported its existing large-bundle warning and the expected outside-project output-directory notice. Its fresh output directory was checked absent before use. For repetition, choose a new unused scratch directory and new test-output names to preserve this evidence.

This was a source/build check, not a live browser, hosted deployment, database integration, forecast, or fresh-clone demonstration. The broad Python suite was not run because some tests fit estimators. No new tests or dependencies were necessary for these copy changes.

## Preservation and unresolved issues

[Preservation evidence](preservation.json) compares the [before snapshot](before.json) with the final files: **652 pre-existing files checked, exactly 11 allowed presentation files changed and 641 unchanged**. All inventoried data files (110), checkpoint files (18), earlier report files (324), and existing `dashboard/dist` files (6) retain their SHA-256 values. Active model pointers and their referenced model/card hashes remain valid and unchanged. No production backend or database operation was performed. HGB remains abstained with `shadow_artifact_not_approved`.

Consequential issues were documented rather than changed: missing point-in-time provider publication/receipt/revision evidence; uncertain well identities, replacements, datum and panel continuity; stale/incomplete current inputs; and the difference between origin+6 calendar months and the lead remaining after actual issuance. The locked horizon/features were not altered. Real shadow issuance remains **NO-GO** under the current provenance report; resolving its protocol and artifact prerequisites requires a separate approved phase.

Raw/processed data and checkpoints are Git-ignored; a clone alone lacks these runtime assets and a populated database. Existing reports can support an offline academic presentation. No runtime assets were copied or published. The existing `dashboard/dist` was intentionally preserved, so it does not contain this pass's updated copy; the new build is in scratch and has not been deployed. Packaging or deployment remains a separate decision.

## Submission checklist

- [x] README and page source identify AquaIQ as a research prototype and disclose unverified nationwide/realtime forecasting skill.
- [x] Existing benchmark and the stronger seasonal-naive result are reported without retraining, reselection or improved-accuracy claims.
- [x] Source-month observations, fills, estimates and projections are distinguished where supported; missing acquisition/panel evidence is disclosed.
- [x] Uncalibrated index, fuzzy-label dependence and noncausal extraction sensitivity are disclosed.
- [x] Relevant safe checks passed; protected assets and prior evidence were preserved; no commit, push or issuance occurred.
- [ ] Human submission review: use the report evidence and identify the code revision; changes remain uncommitted.
- [ ] If a runnable demo is required, resolve lawful/runtime-asset packaging and separately authorize and verify deployment of the updated presentation. Neither clean-clone operation nor a live demonstration was verified here.

**Demonstrated:** an implemented research pipeline and dashboard, reproducible saved historical comparisons on a limited cohort, explicit missing-data handling, and passing scoped software checks. **Unverified:** reliable improvement over baselines on genuinely new labels, nationwide generalization, validated real-time or six-full-month issuance skill, stable well/datum continuity, calibrated crisis risk, causal extraction effects, and production readiness. No model is claimed ready for release.
