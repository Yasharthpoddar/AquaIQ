# Commands and retained execution evidence

Commands ran from the repository root using the existing pinned `venv`, in separate research processes. Isolation is by sandbox, create-only research paths, independent estimators and explicit prohibition of DB/production writes; no separate container or new virtual environment was claimed. No dependency installation occurred. See `checks.json` for outcomes and `source_manifest.json` for every actual acquisition URL/time/hash.

## Acquisitions

Each acquisition used this helper with a new output name:

```powershell
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/fetch_official.py 'https://nwdp.nwic.gov.in/api/3/action/package_show?id=ground-water-level-telemetry-daily-upgw' reports/actual_forecast_validation_20261019/acquired/upgw_package.json --max-bytes 1000000
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/fetch_official.py 'https://nwdp.nwic.gov.in/api/3/action/package_show?id=ground-water-level-telemetry-daily-cgwb-as-assam' reports/actual_forecast_validation_20261019/acquired/cgwb_telemetry_package.json --max-bytes 2000000
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/fetch_official.py 'https://nwdp.nwic.gov.in/api/3/action/package_show?id=gwl-manual-quarterly-central-ground-water-board-department' reports/actual_forecast_validation_20261019/acquired/cgwb_manual_package.json --max-bytes 2000000
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/fetch_official.py 'https://nwdp.nwic.gov.in/api/3/action/datastore_search?resource_id=84bfda45-8ead-436d-9c8e-f7a93ee57522&limit=5' reports/actual_forecast_validation_20261019/acquired/upgw_sample.json --max-bytes 100000
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/fetch_official.py 'https://nwdp.nwic.gov.in/api/3/action/package_show?id=ground-water-level-manual-monthly-telangana-ground-water-department' reports/actual_forecast_validation_20261019/acquired/telangana_package.json --max-bytes 1000000
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/fetch_official.py 'https://nwdp.nwic.gov.in/api/3/action/datastore_search?resource_id=b5706a43-1319-44b4-9739-afd9115e1312&limit=10' reports/actual_forecast_validation_20261019/acquired/telangana_sample.json --max-bytes 200000
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/fetch_official.py 'https://nwdp.nwic.gov.in/footer/copyrightPolicy' reports/actual_forecast_validation_20261019/acquired/nwic_copyright.html --max-bytes 1000000
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/fetch_official.py 'https://nwdp.nwic.gov.in/dataset/0000396f-0381-4154-923e-86c8e23c5f5f/resource/b5706a43-1319-44b4-9739-afd9115e1312/download/ground_water_level_manual_monthly_telangna_2007_2026.csv' reports/actual_forecast_validation_20261019/acquired/telangana_monthly_2007_2026.csv --max-bytes 30000000
```

The full CSV succeeded after metadata/sample suitability checks. The first ten-row sample request was automatically rejected under the prior task's no-download instruction. The current attached mission, lines9 and72–77, was checked; review then approved the same request. No alternative path bypassed that rejection. Re-running these commands against existing filenames deliberately fails to preserve raw snapshots; use retained bytes or distinct names.

## Preparation, historical fitting and arithmetic checks

```powershell
# First attempt, preserved; later superseded by the nullable-depth QC correction.
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/prepare_research.py --source reports/actual_forecast_validation_20261019/acquired/telangana_monthly_2007_2026.csv --output-dir reports/actual_forecast_validation_20261019/normalized > reports/actual_forecast_validation_20261019/prepare.log 2>&1
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/evaluate_research.py --normalized reports/actual_forecast_validation_20261019/normalized --output-dir reports/actual_forecast_validation_20261019/evaluation > reports/actual_forecast_validation_20261019/evaluation.log 2>&1

# Corrected final evidence. Same frozen targets, settings, cutoffs and models.
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/prepare_research.py --source reports/actual_forecast_validation_20261019/acquired/telangana_monthly_2007_2026.csv --output-dir reports/actual_forecast_validation_20261019/normalized_v2 > reports/actual_forecast_validation_20261019/prepare-v2.log 2>&1
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/evaluate_research.py --normalized reports/actual_forecast_validation_20261019/normalized_v2 --output-dir reports/actual_forecast_validation_20261019/evaluation_v2 > reports/actual_forecast_validation_20261019/evaluation-v2.log 2>&1
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/verify_and_diagnose.py --normalized reports/actual_forecast_validation_20261019/normalized_v2 --evaluation reports/actual_forecast_validation_20261019/evaluation_v2 --output-dir reports/actual_forecast_validation_20261019/diagnostics > reports/actual_forecast_validation_20261019/diagnostics.log 2>&1
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/verify_and_diagnose.py --normalized reports/actual_forecast_validation_20261019/normalized_v2 --evaluation reports/actual_forecast_validation_20261019/evaluation_v2 --output-dir reports/actual_forecast_validation_20261019/diagnostics_v2 > reports/actual_forecast_validation_20261019/diagnostics-v2.log 2>&1
.\venv\Scripts\python.exe -B reports/actual_forecast_validation_20261019/well_baselines.py
```

Preparation/fitting/baseline commands succeeded. The first diagnostics run stopped with a preservation assertion: two pre-existing rainfall-progress files changed. Its partial numeric diagnostics remain. The corrected diagnostic reporter records every discrepancy and returns **2**, not a pass, when preservation fails. Scientific arithmetic/prefix checks are recorded separately in `diagnostics_v2/verification.json`. The final broader directory inventory additionally found two new rainfall task logs outside this research run; their staging activity is recorded in `preservation.json`, with launcher unestablished. No source/model settings were changed to improve outcomes.

Original adapter code is retained in `code_snapshots/prepare_research_v1.py`. The first-run commands above describe actual execution with that version; executing them with the current corrected script is not a recreation of the original bug. No old output should be overwritten.

## Tests

```powershell
.\venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider reports/actual_forecast_validation_20261019/test_prepare_research.py reports/actual_forecast_validation_20261019/test_evaluate_research.py --junitxml=reports/actual_forecast_validation_20261019/final-tests.xml
```

Final outcome: **24 passed in7.05s**, [XML](final-tests.xml). Coverage includes nullable depths/coordinates, conflicts/duplicates, unknown availability, preserving past rows despite later metadata changes, causal fills and lags, exact observed target/seasonal references, future perturbations, immutable output paths, metric semantics and paired-resampling equality. The broad application suite was not run.

Earlier create-only test evidence: `adapter-tests.xml` (8pass), `adapter-final-tests.xml` (8pass), `evaluator-tests.xml` (5pass), `research-final-tests.xml` (13pass), `adapter-v2-tests.xml` (19pass). These are repeated subsets, not additional independent tests. The very first adapter test invocation without `--junitxml` had7pass/1setup-error because an unnecessary `tmp_path` fixture attempted a sandbox-forbidden AppData directory. No failure XML was generated; the error is recorded in the task transcript and this execution record. Removing that unused fixture resolved it. Well-baseline code also passed eight in-memory assertion groups; no synthetic forecast/ledger records were created.

Read-only inspection also found two guessed paths absent (`models/forecast_data.py`, `data_ingestion/cgwb_history.py`); existing modules were located instead. Process attribution via `Get-CimInstance Win32_Process` failed with an unavailable-CIM-resource error. A process-session poll after continuation found an expired session ID; completed files/logs, not that poll, provide execution evidence. No failed check is counted as passing.

## Safe repeat

Use [REPRODUCE.ps1](REPRODUCE.ps1), which creates a fresh child directory, verifies frozen input hashes and reuses retained raw bytes. It does not download, overwrite, train production models or issue real forecasts. The original broad preservation discrepancy remains recorded and causes its diagnostic status2; investigate that separately rather than replacing the baseline.
