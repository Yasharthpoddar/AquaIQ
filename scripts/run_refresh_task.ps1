[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [ValidatePattern('^(auto|\d{4}-(0[1-9]|1[0-2]))$')][string]$StartMonth = 'auto',
    [ValidateRange(1,366)][int]$MaxDays = 10
)
$ErrorActionPreference = 'Stop'
$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
$logDirectory = Join-Path $resolvedProject 'reports\candidates\rainfall_refresh\task_logs'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$logStem = Join-Path $logDirectory ("refresh-{0}-{1}" -f (Get-Date -Format 'yyyyMMddTHHmmss'), $PID)
$taskArguments = @('-m', 'scripts.stage_rainfall_update', '--run', '--start', $StartMonth, '--max-days', [string]$MaxDays)
$process = Start-Process -FilePath $resolvedPython -ArgumentList $taskArguments -WorkingDirectory $resolvedProject -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput ($logStem + '.stdout.log') -RedirectStandardError ($logStem + '.stderr.log')
exit $process.ExitCode
