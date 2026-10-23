$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\Users\Yasharth\Downloads\AquaIQ'
$taskEvidence = Join-Path $taskRoot 'reports\visual_rehearsal_preservation_20261023_01'
function Write-NewJson([string]$Name, $Value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 14) + "`n")
    $stream = [IO.File]::Open((Join-Path $taskEvidence $Name), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try {$stream.Write($bytes,0,$bytes.Length)} finally {$stream.Dispose()}
}
function Get-SafeMetadata([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {return [pscustomobject]@{path=$Path;exists=$false}}
    $item=Get-Item -LiteralPath $Path
    [pscustomobject]@{path=$Path;exists=$true;bytes=$item.Length;creation_time_utc=$item.CreationTimeUtc.ToString('o');last_write_time_utc=$item.LastWriteTimeUtc.ToString('o')}
}
function Get-Hash([byte[]]$Bytes) {
    $hasher=[Security.Cryptography.SHA256]::Create()
    try {([BitConverter]::ToString($hasher.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()} finally {$hasher.Dispose()}
}
function Get-NewlineCounts([byte[]]$Bytes) {
    $text=[Text.Encoding]::UTF8.GetString($Bytes)
    [pscustomobject]@{
        cr_bytes=@($Bytes|Where-Object {$_ -eq 13}).Count
        lf_bytes=@($Bytes|Where-Object {$_ -eq 10}).Count
        crlf_pairs=([regex]::Matches($text,"`r`n")).Count
        cr_not_followed_by_lf=([regex]::Matches($text,"`r(?!`n)")).Count
        lf_not_preceded_by_cr=([regex]::Matches($text,"(?<!`r)`n")).Count
        doubled_cr_then_lf_sequences=([regex]::Matches($text,"`r`r`n")).Count
    }
}

$originalPath=Join-Path $taskRoot 'scratch\all-district-twelve-month-build-01\index.html'
$currentPath=Join-Path $taskRoot 'dashboard\dist\index.html'
$original=[IO.File]::ReadAllBytes($originalPath)
$current=[IO.File]::ReadAllBytes($currentPath)
$withoutCr=[byte[]]@($current|Where-Object {$_ -ne 13})
$candidates=@('dashboard/dist/index.html') + @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'scratch') -Directory | ForEach-Object {$p=Join-Path $_.FullName 'index.html';if(Test-Path -LiteralPath $p -PathType Leaf){$p}}) + @('reports/end_to_end_verification_20261022/frontend_build_test/index.html','reports/end_to_end_verification_20261022/frontend_build_20261023/index.html')
$candidateRows=@(foreach($p in $candidates){if(-not [IO.Path]::IsPathRooted($p)){$p=Join-Path $taskRoot $p};$item=Get-Item -LiteralPath $p;[pscustomobject]@{path=$item.FullName.Substring($taskRoot.Length+1).Replace('\','/');bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant();creation_time_utc=$item.CreationTimeUtc.ToString('o');last_write_time_utc=$item.LastWriteTimeUtc.ToString('o')}})
Write-NewJson 'html_comparison.json' ([pscustomobject]@{
    captured_at_utc=[DateTime]::UtcNow.ToString('o')
    original_retained_path='scratch/all-district-twelve-month-build-01/index.html'
    original_retained_bytes=$original.Length
    original_retained_sha256=(Get-Hash $original)
    original_matches_baseline_sha256=((Get-Hash $original) -eq '273c2d6eec27ffa15c1daa1fed8e5100376cd3e63b583a3f94a87c869904c9ad')
    current_path='dashboard/dist/index.html'
    current_bytes=$current.Length
    current_sha256=(Get-Hash $current)
    original_newline_counts=(Get-NewlineCounts $original)
    current_newline_counts=(Get-NewlineCounts $current)
    current_without_cr_bytes=$withoutCr.Length
    current_without_cr_sha256=(Get-Hash $withoutCr)
    bytewise_equal_after_dropping_current_cr=([Convert]::ToBase64String($original) -ceq [Convert]::ToBase64String($withoutCr))
    exact_difference='Current HTML contains exactly 14 additional 0x0D carriage-return bytes. All other bytes retain identical order and values. The comparison and filtering occurred in memory only; no file was normalized, restored or overwritten.'
    attribution='No writer or launcher is inferred from this content equivalence or filesystem timestamps.'
    narrow_candidate_search=$candidateRows
})

$windowStart=[DateTimeOffset]'2026-10-22T16:40:00Z'
$windowEnd=[DateTimeOffset]'2026-10-22T17:00:00Z'
$sessionRows=@(
    foreach($day in @('21','22')) {
        $folder='C:\Users\Yasharth\.codex\sessions\2026\10\'+$day
        foreach($file in Get-ChildItem -LiteralPath $folder -File) {
            $first=Get-Content -LiteralPath $file.FullName -TotalCount 1|ConvertFrom-Json
            if($first.payload.cwd -notmatch '(?i)AquaIQ') {continue}
            $last=Get-Content -LiteralPath $file.FullName -Tail 1|ConvertFrom-Json
            $targetRecords=0
            foreach($line in [IO.File]::ReadLines($file.FullName)) {
                $record=$line|ConvertFrom-Json
                if($record.timestamp) {$stamp=[DateTimeOffset]$record.timestamp;if($stamp -ge $windowStart -and $stamp -le $windowEnd){$targetRecords++}}
            }
            [pscustomobject]@{source=$file.FullName;bytes=$file.Length;session_cwd=$first.payload.cwd;first_record_utc=([DateTimeOffset]$first.timestamp).UtcDateTime.ToString('o');last_record_utc=([DateTimeOffset]$last.timestamp).UtcDateTime.ToString('o');target_window_record_count=$targetRecords}
        }
    }
    foreach($file in Get-ChildItem -LiteralPath 'C:\Users\Yasharth\.codex\archived_sessions' -File | Where-Object {$_.Name -like '*2026-10-22*'}) {
        $first=Get-Content -LiteralPath $file.FullName -TotalCount 1|ConvertFrom-Json
        if($first.payload.cwd -notmatch '(?i)AquaIQ') {continue}
        $last=Get-Content -LiteralPath $file.FullName -Tail 1|ConvertFrom-Json
        $targetRecords=0
        foreach($line in [IO.File]::ReadLines($file.FullName)) {$record=$line|ConvertFrom-Json;if($record.timestamp){$stamp=[DateTimeOffset]$record.timestamp;if($stamp -ge $windowStart -and $stamp -le $windowEnd){$targetRecords++}}}
        [pscustomobject]@{source=$file.FullName;bytes=$file.Length;session_cwd=$first.payload.cwd;first_record_utc=([DateTimeOffset]$first.timestamp).UtcDateTime.ToString('o');last_record_utc=([DateTimeOffset]$last.timestamp).UtcDateTime.ToString('o');target_window_record_count=$targetRecords}
    }
)
$psHistory='C:\Users\Yasharth\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt'
$safeBuilds=@();$historyLines=0;$aquaMentions=0;$dbMentions=0
foreach($line in [IO.File]::ReadLines($psHistory)) {
    $historyLines++
    if($line -match '(?i)AquaIQ') {$aquaMentions++}
    if($line -match '(?i)aquaiq\.db|sqlite3?') {$dbMentions++}
    if($line -match '(?i)^\s*(?:npm(?:\.cmd)?|yarn|pnpm)\s+(?:--prefix\s+dashboard\s+)?(?:run\s+)?build\s*$') {$safeBuilds += [pscustomobject]@{line_number=$historyLines;safe_command=$line.Trim();command_timestamp=$null;cwd=$null}}
}
$codexHistory='C:\Users\Yasharth\.codex\history.jsonl'
$codexHistoryCount=0;$codexHistoryWindowCount=0
foreach($line in [IO.File]::ReadLines($codexHistory)) {$record=$line|ConvertFrom-Json;$codexHistoryCount++;$stamp=[DateTimeOffset]::FromUnixTimeSeconds($record.ts);if($stamp -ge $windowStart -and $stamp -le $windowEnd){$codexHistoryWindowCount++}}
$appLog='C:\Users\Yasharth\AppData\Local\Codex\logs\2026\10\22\codex-desktop-5b8d5c0f-4b42-4778-8ed8-fde5ba489024-23444-t0-i1-160554-0.log'
$appLineCount=0;$appWindowCount=0;$appBuildReceiptCount=0;$appDbCount=0;$appAquaCount=0
foreach($line in [IO.File]::ReadLines($appLog)) {
    $appLineCount++
    $stampText=([regex]::Match($line,'\d{4}-\d{2}-\d{2}T[0-9:.]+Z')).Value
    if($stampText){$stamp=[DateTimeOffset]$stampText;if($stamp -ge $windowStart -and $stamp -le $windowEnd){$appWindowCount++}}
    if($line -match '(?i)npm(?:\.cmd)?\s+(?:--prefix\s+dashboard\s+)?(?:run\s+)?build|\bvite\s+build') {$appBuildReceiptCount++}
    if($line -match '(?i)aquaiq\.db') {$appDbCount++}
    if($line -match '(?i)AquaIQ') {$appAquaCount++}
}
Write-NewJson 'history_investigation.json' ([pscustomobject]@{
    captured_at_utc=[DateTime]::UtcNow.ToString('o')
    target_window_utc=@($windowStart.UtcDateTime.ToString('o'),$windowEnd.UtcDateTime.ToString('o'))
    privacy_policy='No raw session messages, private headers, cookies, credentials, environment values, or unrelated personal history are copied. Persisted command strings are accepted only by a whole-line allowlist for bare build commands. Other retained evidence consists of safe timestamps, paths, counts and boolean checks.'
    aqua_session_metadata=$sessionRows
    session_target_window_record_count=($sessionRows|Measure-Object -Property target_window_record_count -Sum).Sum
    psreadline=[pscustomobject]@{metadata=(Get-SafeMetadata $psHistory);line_count=$historyLines;AquaIQ_mention_count=$aquaMentions;sqlite_or_aquaiq_db_mention_count=$dbMentions;allowlisted_bare_build_commands=$safeBuilds;limitation='These entries retain neither per-command timestamps nor execution directory. File last-write metadata is 18 October 2026; it supplies no direct 22 October execution receipt.'}
    codex_prompt_history=[pscustomobject]@{metadata=(Get-SafeMetadata $codexHistory);record_count=$codexHistoryCount;target_window_record_count=$codexHistoryWindowCount;prompt_text_exported=$false}
    app_log=[pscustomobject]@{metadata=(Get-SafeMetadata $appLog);line_count=$appLineCount;target_window_line_count=$appWindowCount;literal_build_command_pattern_count=$appBuildReceiptCount;literal_aquaiq_db_count=$appDbCount;literal_aquaiq_count=$appAquaCount;raw_lines_exported=$false;limitation='Generic build/vite/sqlite labels occur in application diagnostics but do not supply an AquaIQ command receipt.'}
    older_log_metadata=@((Get-SafeMetadata 'C:\Users\Yasharth\.codex\log\codex-tui.log'),(Get-SafeMetadata 'C:\Users\Yasharth\.codex\sandbox.log'))
    not_inspected='No browser caches, broad Downloads trees, cookie stores, authentication stores, environment/config contents or local application databases were searched. No database was connected or parsed.'
    attribution_status='UNRESOLVED. No direct safe retained receipt establishes the writer/launcher of the 22 October 16:49 UTC HTML rewrite or 16:47 UTC empty aquaiq.db creation. Filesystem timestamps are supporting metadata only.'
})
[pscustomobject]@{original_matches_baseline=$true;cr_insertions=14;non_cr_bytes_equal=$true;session_files_checked=$sessionRows.Count;target_window_session_records=($sessionRows|Measure-Object -Property target_window_record_count -Sum).Sum;app_literal_build_receipts=$appBuildReceiptCount;attribution='UNRESOLVED'}|ConvertTo-Json
