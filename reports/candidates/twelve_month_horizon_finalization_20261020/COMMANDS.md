# Execution and local reproduction

Commands below run from `C:\Users\Yasharth\Downloads\AquaIQ` with the existing environment. No package installation, source download, DB setup or production pipeline is needed. Output paths were fresh and create-only. Do not repeat commands against completed receipts/artifacts; select new evidence paths for another verification.

## State and preservation

Read-only inspections included `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, `git rev-parse main`, `git diff --cached --name-only`, `git remote -v`, `git ls-remote origin refs/heads/main refs/heads/experiment/12-month-horizon`, `git ls-files --cached --others --exclude-standard`, report/source reads and local hash comparisons. No branch switch, stage, commit or push was performed in this phase. Remote main and local refs were `98c7056057b2a0370d377afa831f528f6d408481`; the experimental branch remained local.

Executed preservation commands (exit 0; distinct receipts):

```powershell
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_finalization_20261020/preserve.py before
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_finalization_20261020/preserve.py after
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_finalization_20261020/preserve.py after-final
git diff --check
```

Read-only `Get-ScheduledTask -TaskName 'AquaIQ-Rainfall-Staging' -TaskPath '\'` used host access and exported only task name/path/state/enabled plus verification time to fresh JSON receipts. Both checks returned Disabled, false. No disable/enable/refresh command ran.

## Authorized isolated one-fit build

```powershell
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_finalization_20261020/build_application_research.py
# Exit 1 AFTER ONE successful fit/reload: exact-old-2024 parity assumption failed.
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_finalization_20261020/artifact/complete_existing_build.py
# Exit 0: packages the EXISTING model, checks its own reload/rows/settings; zero additional fits.
```

Logs: `artifact-build.log`, `artifact-completion.log`; result: `artifact_build.json`. Original builder, failed evidence, model and original comparison were not overwritten. These helpers intentionally refuse existing destinations. Do not rerun or modify them to seek better errors. Further artifact construction requires a separate unused version and authorized scope; no HGB application/shadow refit is authorized here.

## Final targeted tests/build (all exit 0)

Exact final commands are also stored as argument arrays in `*-final-03.json`:

```powershell
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/test_research_forecast_api.py tests/test_research_horizon.py tests/test_twelve_month_backtest.py tests/test_six_month_selection.py tests/test_forecast_integrity.py tests/test_monthly_candidate_validation.py tests/test_monthly_prediction_api.py tests/test_preprocessing_causal.py tests/test_serving_integrity.py tests/test_post_audit_metadata.py -k 'not imputation_and_scaling_statistics_fit_only_training_rows and not production_bundle_and_eval_use_matching_cutoff' --basetemp=scratch/twelve-month-app-tests-final-03 --junitxml=reports/candidates/twelve_month_horizon_finalization_20261020/python-tests-final-03.xml
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../scratch/twelve-month-app-build-final-03
```

Results: 229 Python passes, 1 Windows symlink-privilege skip, 3 real-fitting deselections; 23 frontend passes; lint/build success. Build warnings concern output outside the dashboard root and bundle size, not test failures. Fresh `scratch/twelve-month-app-build-final-01`, `-02`, `-03` preserve every attempt rather than overwriting `dashboard/dist`.

Earlier checks retained: frontend test/lint `frontend-tests-01.txt`/`frontend-lint-01.txt` (22 passes); root frontend commands with paths `*-final-01` (22 passes), then `*-final-02` (23). Broad Python `python-tests-final-01.json` records the same final command without `tests/test_monthly_prediction_api.py`, with `--basetemp=scratch/twelve-month-app-tests-final-01` and matching XML (205 passes/1 skip/3 deselections). `backend-tests-final-02.json` records `pytest -q -p no:cacheprovider tests/test_research_forecast_api.py --basetemp=scratch/twelve-month-app-backend-final-02 --junitxml=reports/candidates/twelve_month_horizon_finalization_20261020/backend-tests-final-02.xml` under Python `-B` (57 passes). Preliminary agent JUnit files `scratch/twelve-month-backend-tests-20261020-a.xml` and `-b.xml` have 45/149 passes; full original shell invocation was not retained, so no exact extra flags are invented. Their collected modules are respectively the new API tests, then API/horizon/evaluator/monthly-API tests. Repeats are not additional unique coverage.

## Read-only retained-asset verification

```powershell
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_finalization_20261020/verify_local_demo.py
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_finalization_20261020/verify_quality.py
```

Both successful final receipts are create-only. `verify_local_demo.py` first exited 1 because padded unobserved rows omitted measurement units; the new adapter's unit guard was corrected without changing the artifact and the repeat exited 0. Final output matches 24 archived predictions and checks current abstention, carry status, geographic restriction and primary/legacy metadata under DB/fitting guards. Quality checks parse Python AST/strict JSON, check whitespace, compare known sensitive values in memory without emitting them and review only the stated change set. No publication approval is inferred.

For later safe verification, use a fresh receipt name in a new helper copy or reproduce the individual assertions in a separately named check. Do not delete completed evidence to make these helpers run again.

## Safe local demo commands (existing assets required)

The following two commands were executed in separate temporary sessions. Both servers reported startup, then were stopped with Ctrl+C. They did **not** establish a successful browser/HTTP demo in this environment:

```powershell
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_horizon_finalization_20261020/readonly_demo_server.py
```

```powershell
$env:VITE_API_URL = 'http://127.0.0.1:5051'
npm.cmd --prefix dashboard run dev -- --host 127.0.0.1 --port 5181 --strictPort
```

With these running on a host that permits localhost access, open `http://127.0.0.1:5181/research` only. The API helper binds 127.0.0.1:5051, accepts that frontend origin, blocks DB connections/fitting and excludes legacy routes. Inspect the default latest observed origin (ML unavailable), then enter `2024-01` for the historical ML/baseline/observed-target example. No request represents prospective issuance. Restore the terminal's prior `VITE_API_URL` setting afterward; no repository config file is changed.

`verify_http_demo.py` was executed with host network access but exited 1 on timeout. An earlier inline equivalent failed on sandbox WinError 10013. Two direct no-proxy urllib probes also timed out. Browser call `cua.createBrowserTab('iab', 'http://127.0.0.1:5181/research', {visible:true})` failed before tab creation with missing kernel assets; reset-and-retry failed identically. Attempt receipts retain these distinctions. No browser interaction, external data request or DB-backed page load succeeded. Do not claim full end-to-end readiness from server startup.

An alternative normal local launch (documented, **not executed during this phase**) uses the restored matching environment:

```powershell
$env:FLASK_HOST = '127.0.0.1'
$env:FLASK_PORT = '5000'
$env:FLASK_DEBUG = 'false'
.\venv\Scripts\python.exe -B -m api.app
```

In another terminal use Vite port 5173 with `VITE_API_URL` unset so the existing `/api` proxy reaches port 5000. Do not start duplicate services on occupied ports. The dedicated `/research` page only needs the research descriptor/artifact bundle; Home/district/alerts/simulation additionally request legacy DB data and are outside the no-DB demonstration. Existing 5000/5173 services were left untouched and may need a separately controlled restart to load the new backend.

## Reproduce saved historical science

The new application did **not** rerun or overwrite the original 792-case study. Its exact earlier prepare/run/verification commands, immutable protocol and fresh-version reproduction procedure are in [the original COMMANDS.md](../twelve_month_horizon_20261020/COMMANDS.md). Its `verify_results.py` can verify archived rows/models under that report's instructions; it was not rerun during this integration. Refitting that study creates new research artifacts and must use a new unused `reports/candidates/twelve_month_horizon_*` directory; it is never a setup or serving prerequisite.

For this fixed artifact, the saved card, rows, source hashes, training identity check and successful `verify_local_demo.py` receipt provide the actual supported no-fit replay. A clean clone alone omits required ignored assets and cannot reproduce the local demonstration. Neither reproduction path certifies historical input availability, prospective skill or twelve full months of operational lead.
