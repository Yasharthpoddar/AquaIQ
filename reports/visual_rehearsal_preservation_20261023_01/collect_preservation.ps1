$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\Users\Yasharth\Downloads\AquaIQ'
$taskEvidence = Join-Path $taskRoot 'reports\visual_rehearsal_preservation_20261023_01'
$priorAudit = Join-Path $taskRoot 'reports\end_to_end_verification_20261022'

function Write-NewJson([string]$Name, $Value) {
    $target = Join-Path $taskEvidence $Name
    $json = $Value | ConvertTo-Json -Depth 12
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json + "`n")
    $stream = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}

function Read-FileMetadata([string]$Relative) {
    $absolute = [IO.Path]::GetFullPath((Join-Path $taskRoot $Relative))
    if (-not $absolute.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path outside task workspace.' }
    if (-not (Test-Path -LiteralPath $absolute -PathType Leaf)) {
        return [pscustomobject]@{path=$Relative;exists=$false}
    }
    $item = Get-Item -LiteralPath $absolute
    [pscustomobject]@{
        path=$Relative
        exists=$true
        bytes=$item.Length
        sha256=(Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash.ToLowerInvariant()
        creation_time_utc=$item.CreationTimeUtc.ToString('o')
        last_write_time_utc=$item.LastWriteTimeUtc.ToString('o')
    }
}

$started = [DateTime]::UtcNow.ToString('o')
$before = Get-Content -LiteralPath (Join-Path $priorAudit 'before.json') -Raw | ConvertFrom-Json
$final = Get-Content -LiteralPath (Join-Path $priorAudit 'final_preservation_20261023.json') -Raw | ConvertFrom-Json
$exceptionRows = @(
    foreach ($prior in $final.outside_audit_new_file_metadata) {
        $current = Read-FileMetadata $prior.path
        [pscustomobject]@{
            path=$current.path
            exists=$current.exists
            bytes=$current.bytes
            sha256=$current.sha256
            creation_time_utc=$current.creation_time_utc
            last_write_time_utc=$current.last_write_time_utc
            prior_final_bytes=$prior.bytes
            prior_final_sha256=$prior.sha256
            matches_prior_final=($current.exists -and $current.bytes -eq $prior.bytes -and $current.sha256 -eq $prior.sha256)
            before_sha256=if ($before.files.PSObject.Properties.Name -contains $prior.path) {$before.files.($prior.path).sha256} else {$null}
            before_bytes=if ($before.files.PSObject.Properties.Name -contains $prior.path) {$before.files.($prior.path).bytes} else {$null}
        }
    }
)
Write-NewJson 'exception_files_current.json' ([pscustomobject]@{captured_at_utc=$started;database_access='Metadata and SHA-256 only; no SQLite connection or DB content parsing.';files=$exceptionRows})

$matrix = @(
    foreach ($property in $before.files.PSObject.Properties) {
        $current = Read-FileMetadata $property.Name
        [pscustomobject]@{
            path=$property.Name
            exists=$current.exists
            before_bytes=$property.Value.bytes
            before_sha256=$property.Value.sha256
            current_bytes=$current.bytes
            current_sha256=$current.sha256
            creation_time_utc=$current.creation_time_utc
            last_write_time_utc=$current.last_write_time_utc
            unchanged=($current.exists -and $current.bytes -eq $property.Value.bytes -and $current.sha256 -eq $property.Value.sha256)
        }
    }
)
$matrixSummary = [pscustomobject]@{
    started_at_utc=$started
    completed_at_utc=[DateTime]::UtcNow.ToString('o')
    reference='reports/end_to_end_verification_20261022/before.json'
    checked=$matrix.Count
    unchanged=@($matrix | Where-Object unchanged).Count
    changed_or_missing=@($matrix | Where-Object {-not $_.unchanged} | Select-Object path,exists,before_bytes,before_sha256,current_bytes,current_sha256)
    files=$matrix
}
Write-NewJson 'protected_matrix_current.json' $matrixSummary

$reportRows = @(
    foreach ($item in Get-ChildItem -LiteralPath $priorAudit -File -Recurse | Sort-Object FullName) {
        $relative = $item.FullName.Substring($taskRoot.Length + 1).Replace('\','/')
        Read-FileMetadata $relative
    }
)
Write-NewJson 'prior_audit_report_matrix_start.json' ([pscustomobject]@{captured_at_utc=[DateTime]::UtcNow.ToString('o');note='Current baseline of the 479 prior end-to-end audit files. Rehash against this receipt at the end of the rehearsal; no prior audit file is modified.';count=$reportRows.Count;files=$reportRows})
[pscustomobject]@{checked=$matrix.Count;unchanged=$matrixSummary.unchanged;exceptions_match_prior_final=@($exceptionRows | Where-Object matches_prior_final).Count;exception_count=$exceptionRows.Count;prior_audit_report_count=$reportRows.Count;changed=$matrixSummary.changed_or_missing} | ConvertTo-Json -Depth 5
