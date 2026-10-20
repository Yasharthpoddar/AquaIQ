param([string]$RunName = ("replay_" + (Get-Date -Format "yyyyMMdd_HHmmss_ffff")))
$ErrorActionPreference = "Stop"
if ($RunName -notmatch '^[a-zA-Z0-9_-]+$') { throw "RunName must be a simple directory name." }
$studyRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $studyRoot "../.."))
$replayRoot = [IO.Path]::GetFullPath((Join-Path $studyRoot $RunName))
if (-not $replayRoot.StartsWith($studyRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Replay must remain inside this research directory." }
if (Test-Path -LiteralPath $replayRoot) { throw "Choose a new RunName; existing artifacts are immutable." }
$protocolPath = Join-Path $studyRoot "protocol.json"
if ((Get-FileHash -LiteralPath $protocolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne "06af4e6aab2e7d71ab573ecc6196fad7c5cbc9b825243c9d1aa624ce4193ce45") { throw "Frozen protocol changed." }
$protocol = Get-Content -LiteralPath $protocolPath -Raw | ConvertFrom-Json
$sourcePath = Join-Path $studyRoot $protocol.source.file
$weatherPath = Join-Path $repositoryRoot $protocol.weather_source.path
if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $protocol.source.sha256) { throw "Raw source changed." }
if ((Get-FileHash -LiteralPath $weatherPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $protocol.weather_source.sha256) { throw "Weather features changed." }
$pythonPath = Join-Path $repositoryRoot "venv/Scripts/python.exe"
$normalizedPath = Join-Path $replayRoot "normalized"
$evaluationPath = Join-Path $replayRoot "evaluation"
$diagnosticsPath = Join-Path $replayRoot "diagnostics"
New-Item -ItemType Directory -Path $replayRoot | Out-Null
Push-Location -LiteralPath $repositoryRoot
try {
    & $pythonPath -B (Join-Path $studyRoot "prepare_research.py") --source $sourcePath --output-dir $normalizedPath
    if ($LASTEXITCODE -ne 0) { throw "Research preparation failed: $LASTEXITCODE" }
    & $pythonPath -B (Join-Path $studyRoot "evaluate_research.py") --normalized $normalizedPath --output-dir $evaluationPath
    if ($LASTEXITCODE -ne 0) { throw "Historical evaluation failed: $LASTEXITCODE" }
    & $pythonPath -B (Join-Path $studyRoot "well_baselines.py") --normalized-dir $normalizedPath --output-dir (Join-Path $replayRoot "well_baselines")
    if ($LASTEXITCODE -ne 0) { throw "Well-baseline verification failed: $LASTEXITCODE" }
    & $pythonPath -B (Join-Path $studyRoot "verify_and_diagnose.py") --normalized $normalizedPath --evaluation $evaluationPath --output-dir $diagnosticsPath
    $diagnosticExit = $LASTEXITCODE
    Write-Output "New research evidence: $replayRoot"
    if ($diagnosticExit -eq 2) {
        Write-Warning "Historical arithmetic completed; pre-existing preservation discrepancy remains. Read verification.json. No preservation pass is claimed."
    } elseif ($diagnosticExit -ne 0) {
        throw "Diagnostics failed: $diagnosticExit"
    }
} finally {
    Pop-Location
}
exit $diagnosticExit
