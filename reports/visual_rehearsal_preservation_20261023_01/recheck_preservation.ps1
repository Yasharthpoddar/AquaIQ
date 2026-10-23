param([string]$OutputName='preservation_final_recheck.json')
$ErrorActionPreference='Stop'
if($OutputName -notmatch '^[A-Za-z0-9_-]+\.json$'){throw 'OutputName must be a simple JSON basename.'}
$taskRoot='C:\Users\Yasharth\Downloads\AquaIQ'
$taskEvidence=Join-Path $taskRoot 'reports\visual_rehearsal_preservation_20261023_01'
$start=Get-Content -LiteralPath (Join-Path $taskEvidence 'protected_matrix_current.json') -Raw|ConvertFrom-Json
$priorReports=Get-Content -LiteralPath (Join-Path $taskEvidence 'prior_audit_report_matrix_start.json') -Raw|ConvertFrom-Json
$exceptions=Get-Content -LiteralPath (Join-Path $taskEvidence 'exception_files_current.json') -Raw|ConvertFrom-Json
$began=[DateTime]::UtcNow.ToString('o')
function Get-Current([string]$Relative){
    $absolute=[IO.Path]::GetFullPath((Join-Path $taskRoot $Relative))
    if(-not $absolute.StartsWith($taskRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Protected path outside workspace.'}
    $exists=Test-Path -LiteralPath $absolute -PathType Leaf
    $item=if($exists){Get-Item -LiteralPath $absolute}else{$null}
    [pscustomobject]@{path=$Relative;exists=$exists;bytes=$item.Length;sha256=if($exists){(Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null};creation_time_utc=if($exists){$item.CreationTimeUtc.ToString('o')}else{$null};last_write_time_utc=if($exists){$item.LastWriteTimeUtc.ToString('o')}else{$null}}
}
$protected=@(foreach($entry in $start.files){$current=Get-Current $entry.path;[pscustomobject]@{path=$entry.path;exists=$current.exists;baseline_bytes=$entry.before_bytes;baseline_sha256=$entry.before_sha256;start_bytes=$entry.current_bytes;start_sha256=$entry.current_sha256;final_bytes=$current.bytes;final_sha256=$current.sha256;matches_rehearsal_start=($current.exists -and $current.bytes -eq $entry.current_bytes -and $current.sha256 -eq $entry.current_sha256);matches_original_baseline=($current.exists -and $current.bytes -eq $entry.before_bytes -and $current.sha256 -eq $entry.before_sha256)}})
$reports=@(foreach($entry in $priorReports.files){$current=Get-Current $entry.path;[pscustomobject]@{path=$entry.path;exists=$current.exists;start_bytes=$entry.bytes;start_sha256=$entry.sha256;final_bytes=$current.bytes;final_sha256=$current.sha256;unchanged=($current.exists -and $current.bytes -eq $entry.bytes -and $current.sha256 -eq $entry.sha256)}})
$exceptionRows=@(foreach($entry in $exceptions.files){$current=Get-Current $entry.path;[pscustomobject]@{path=$entry.path;exists=$current.exists;bytes=$current.bytes;sha256=$current.sha256;creation_time_utc=$current.creation_time_utc;last_write_time_utc=$current.last_write_time_utc;matches_start=($current.exists -and $current.bytes -eq $entry.bytes -and $current.sha256 -eq $entry.sha256);matches_prior_final=($current.exists -and $current.bytes -eq $entry.prior_final_bytes -and $current.sha256 -eq $entry.prior_final_sha256)}})
$result=[pscustomobject]@{started_at_utc=$began;completed_at_utc=[DateTime]::UtcNow.ToString('o');protected_checked=$protected.Count;protected_matches_rehearsal_start=@($protected|Where-Object matches_rehearsal_start).Count;protected_matches_original_baseline=@($protected|Where-Object matches_original_baseline).Count;protected_new_discrepancies=@($protected|Where-Object {-not $_.matches_rehearsal_start});prior_report_checked=$reports.Count;prior_report_unchanged=@($reports|Where-Object unchanged).Count;prior_report_discrepancies=@($reports|Where-Object {-not $_.unchanged});exception_checked=$exceptionRows.Count;exception_matches_start=@($exceptionRows|Where-Object matches_start).Count;exception_matches_prior_final=@($exceptionRows|Where-Object matches_prior_final).Count;protected_files=$protected;prior_report_files=$reports;exception_files=$exceptionRows;note='All operations hash/read existing protected files. Only this create-only JSON receipt is written, under the new rehearsal directory. Empty aquaiq.db is hashed as a file only; no DB connection or parser is used.'}
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($result|ConvertTo-Json -Depth 13)+"`n")
$stream=[IO.File]::Open((Join-Path $taskEvidence $OutputName),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try{$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
[pscustomobject]@{output=$OutputName;protected_checked=$protected.Count;protected_matches_start=$result.protected_matches_rehearsal_start;protected_matches_original_baseline=$result.protected_matches_original_baseline;prior_report_checked=$reports.Count;prior_report_unchanged=$result.prior_report_unchanged;exceptions_match_prior_final=$result.exception_matches_prior_final;completed_at_utc=$result.completed_at_utc}|ConvertTo-Json
