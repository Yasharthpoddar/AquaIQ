# Executed commands and reproduction

Run from the AquaIQ repository root using its existing environment. No installation, download, database, schema or serving operation is part of this experiment. Experimental source remains uncommitted on `experiment/12-month-horizon`; main remains `98c7056057b2a0370d377afa831f528f6d408481`.

## State and branch

Read-only `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, `git remote -v`, `git show-ref --verify refs/heads/experiment/12-month-horizon`, and `git ls-remote origin refs/heads/main refs/heads/experiment/12-month-horizon` verified the baseline and absence of the branch. Then:

```powershell
git switch -c experiment/12-month-horizon 98c7056057b2a0370d377afa831f528f6d408481
```

The local Git write and remote read used authorized host access. No commit or push followed. Initial files/hashes and Git state are in `before.json`; final hashes/state are in `preservation.json`.

## Actual successful research execution

The protocol and its implementation clarification were created once before fitting. Actual commands (all exit 0):

```powershell
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_20261020/preserve.py before
.\venv\Scripts\python.exe -B scripts/backtest_twelve_month.py --stage prepare --protocol reports/candidates/twelve_month_horizon_20261020/protocol.json
.\venv\Scripts\python.exe -B scripts/backtest_twelve_month.py --stage run --protocol reports/candidates/twelve_month_horizon_20261020/protocol.json --output-dir reports/candidates/twelve_month_horizon_20261020/evaluation
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_20261020/verify_results.py
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_20261020/preserve.py after
git diff --check
```

The prepare/run/verify commands were wrapped with `Tee-Object` to fresh `prepare.log`, `backtest.log` and `verification.log`, checking `$LASTEXITCODE`. Preparation froze case membership and implementation hashes before predictions. The run fitted the specified twelve-month research models; verification only reloaded those new artifacts and recomputed arithmetic. Existing output/cohort/model paths are immutable and these commands cannot be repeated in place.

## Focused tests

Final new tests: **74 passed**:

```powershell
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_research_horizon.py tests/test_twelve_month_backtest.py --basetemp=scratch/twelve-month-final-tests-20261020 --junitxml=reports/candidates/twelve_month_horizon_20261020/final_tests.xml
```

Existing contracts: **76 passed, 1 skipped, 3 deselected**:

```powershell
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_six_month_selection.py tests/test_forecast_integrity.py tests/test_monthly_candidate_validation.py tests/test_preprocessing_causal.py tests/test_serving_integrity.py tests/test_post_audit_metadata.py -k 'not imputation_and_scaling_statistics_fit_only_training_rows and not production_bundle_and_eval_use_matching_cutoff' --basetemp=scratch/twelve-month-six-regressions-20261020 --junitxml=reports/candidates/twelve_month_horizon_20261020/six_month_regressions.xml
```

The skip is Windows symlink privilege availability. Deselected tests fit real six-month estimators; retained tests use arrays, metadata or fake fit recorders. The new test artifact serializers are fake, and unit fixtures are synthetic; they are not mixed with real backtest cohorts. No full pytest suite was run. Earlier XML files retain the initial TEMP-permission setup errors and subsequent 49/55-test passes. `combined_tests.xml` records an earlier 74-test pass, not additional unique coverage.

## Fresh research reproduction, preserving this run

Choose a new unused directory under `reports/candidates/twelve_month_horizon_*`; never remove/reuse this completed run. The following creates another isolated historical experiment using the same frozen protocol and retained inputs. It fits new research models and must remain separately authorized research work:

```powershell
$reproRun = 'reports/candidates/twelve_month_horizon_repro_20261020'
if (Test-Path -LiteralPath $reproRun) { throw 'Choose an unused reproduction directory' }
New-Item -ItemType Directory -Path $reproRun | Out-Null
Copy-Item -LiteralPath 'reports/candidates/twelve_month_horizon_20261020/protocol.json' -Destination $reproRun
Copy-Item -LiteralPath 'reports/candidates/twelve_month_horizon_20261020/protocol_implementation_addendum.json' -Destination $reproRun
Copy-Item -LiteralPath 'reports/candidates/twelve_month_horizon_20261020/preserve.py' -Destination $reproRun
Copy-Item -LiteralPath 'reports/candidates/twelve_month_horizon_20261020/verify_results.py' -Destination $reproRun
.\venv\Scripts\python.exe -B "$reproRun/preserve.py" before
.\venv\Scripts\python.exe -B scripts/backtest_twelve_month.py --stage prepare --protocol "$reproRun/protocol.json"
.\venv\Scripts\python.exe -B scripts/backtest_twelve_month.py --stage run --protocol "$reproRun/protocol.json" --output-dir "$reproRun/evaluation"
.\venv\Scripts\python.exe -B "$reproRun/verify_results.py"
.\venv\Scripts\python.exe -B "$reproRun/preserve.py" after
```

Model serialization bytes may differ with software versions; the protocol records this run's Python/numpy/pandas/sklearn/XGBoost versions and exact input hashes. The cohort lock pins the source implementation used. Preserve any failed attempt under its original name rather than overwriting it. Refreshing sources, changing settings/cohorts, training production models or issuing forecasts is outside these reproduction commands.
