# Run from C:\Users\Yasharth\Downloads\AquaIQ. The saved experiment is never replaced.
$ErrorActionPreference = 'Stop'
$python = '.\venv\Scripts\python.exe'
$saved = 'reports/candidates/six_month_selection_20261017'
$newRun = 'reports/candidates/six_month_selection_reproduction_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
if (Test-Path -LiteralPath $newRun) { throw 'Choose a new output directory.' }
New-Item -ItemType Directory -Path "$newRun/coverage" | Out-Null

# Reproduce the previous saved checkpoint comparison, before candidate fitting.
& $python -u -m models.audit_evaluation --output-dir "$newRun/reproduction"
if ($LASTEXITCODE -ne 0) { throw 'Previous evaluation reproduction failed.' }

# All helper writes go to the new sibling directory. Active data is read only.
Copy-Item -LiteralPath "$saved/coverage/run_coverage.py" -Destination "$newRun/coverage/run_coverage.py"
Copy-Item -LiteralPath "$saved/coverage/run_source_holdout_audit.py" -Destination "$newRun/coverage/run_source_holdout_audit.py"
& $python "$newRun/coverage/run_coverage.py"
if ($LASTEXITCODE -ne 0) { throw 'Coverage inventory failed.' }
& $python "$newRun/coverage/run_source_holdout_audit.py"
if ($LASTEXITCODE -ne 0) { throw 'Optional source inventory failed.' }

# Stage one constructs validation labels only through2018 and freezes settings.
& $python -u -m models.six_month_selection --stage validation --output-dir "$newRun/experiment_v2" --external-features "$newRun/coverage/source_manual_optional_features.csv"
if ($LASTEXITCODE -ne 0) { throw 'Validation failed.' }

# Stage two uses the saved selection lock; no further tuning is permitted.
& $python -u -m models.six_month_selection --stage test --output-dir "$newRun/experiment_v2" --external-features "$newRun/coverage/source_manual_optional_features.csv"
if ($LASTEXITCODE -ne 0) { throw 'Final evaluation failed.' }

& $python -m pytest -q -m 'not requires_db' --basetemp="$newRun/pytest-temp" --junitxml="$newRun/pytest-final-results.xml"
if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed.' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed.' }

# The renderer only reads saved predictions; no fitting or selection occurs.
Copy-Item -LiteralPath "$saved/build_report.py" -Destination "$newRun/build_report.py"
& $python "$newRun/build_report.py"
if ($LASTEXITCODE -ne 0) { throw 'Report rendering failed.' }
Write-Output "Saved independent reproduction to $newRun"
