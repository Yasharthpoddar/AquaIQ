[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath,
    [ValidatePattern('^(auto|\d{4}-(0[1-9]|1[0-2]))$')][string]$StartMonth = 'auto',
    [ValidateRange(1,168)][int]$EveryHours = 24,
    [ValidateRange(1,366)][int]$MaxDays = 10,
    [string]$TaskName = 'AquaIQ-Rainfall-Staging',
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedProject 'config.yaml'))) { throw 'Invalid AquaIQ project root.' }
if (-not $PythonPath) { $PythonPath = Join-Path $resolvedProject 'venv\Scripts\python.exe' }
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
$runner = Join-Path $resolvedProject 'scripts\run_refresh_task.ps1'
if (-not (Test-Path -LiteralPath $runner)) { throw 'Missing run_refresh_task.ps1.' }
# Task Scheduler arguments are literal Windows command-line arguments, not commands.
foreach ($value in @($resolvedProject, $resolvedPython, $runner)) {
    if ($value.Contains('"') -or $value.Contains("`r") -or $value.Contains("`n")) { throw 'Unsupported quotation or newline in task path.' }
}
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" -ProjectRoot "{1}" -PythonPath "{2}" -StartMonth "{3}" -MaxDays {4}' -f $runner, $resolvedProject, $resolvedPython, $StartMonth, $MaxDays
$shellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$preview = [ordered]@{
    TaskName = $TaskName; Executable = $shellPath; Arguments = $arguments
    WorkingDirectory = $resolvedProject; EveryHours = $EveryHours
    Scope = 'Staging only; no database, model, or score publication'
    Logon = 'Current user must be logged in; no stored password'
    Installed = $false
}
if ($Install) {
    $action = New-ScheduledTaskAction -Execute $shellPath -Argument $arguments -WorkingDirectory $resolvedProject
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours $EveryHours) -RepetitionDuration (New-TimeSpan -Days 3650)
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    # Refuse accidental replacement; review/remove an existing task explicitly.
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description $preview.Scope | Out-Null
    $preview.Installed = $true
}
$preview | ConvertTo-Json
