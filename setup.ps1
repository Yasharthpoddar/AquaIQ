param([string]$PythonExecutable = 'py')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Copy .env.example to .env and configure an existing PostgreSQL database before setup.'
}

function Invoke-AquaIQPython {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE. Setup stopped."
    }
}

$environmentPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $environmentPython)) {
    $launcherArguments = @()
    if ($PythonExecutable -eq 'py') { $launcherArguments = @('-3.13') }
    Invoke-AquaIQPython $PythonExecutable ($launcherArguments + @('-c', "import sys; assert sys.version_info[:2] == (3, 13), 'AquaIQ requires Python 3.13'"))
    Invoke-AquaIQPython $PythonExecutable ($launcherArguments + @('-m', 'venv', 'venv'))
}
Invoke-AquaIQPython $environmentPython @('-c', "import sys; assert sys.version_info[:2] == (3, 13), 'Existing venv requires Python 3.13; use a separate new environment'")
Invoke-AquaIQPython $environmentPython @('-m', 'pip', 'install', '--upgrade', 'pip')
Invoke-AquaIQPython $environmentPython @('-m', 'pip', 'install', '-r', 'requirements.txt')
Invoke-AquaIQPython $environmentPython @('-m', 'pip', 'check')
foreach ($directory in @('data\raw', 'data\processed', 'models\checkpoints', 'reports')) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
Invoke-AquaIQPython $environmentPython @('-m', 'db.init_db')
Invoke-AquaIQPython $environmentPython @('-c', "from pathlib import Path; import yaml; yaml.safe_load(Path('config.yaml').read_text(encoding='utf-8')); print('config.yaml is valid')")
Write-Host 'Setup complete. Activate with: .\venv\Scripts\Activate.ps1'
Write-Host 'See README.md for climate regeneration, pipeline execution, and dashboard setup.'
