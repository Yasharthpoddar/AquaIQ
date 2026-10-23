$ErrorActionPreference='Stop'
$taskRoot='C:\Users\Yasharth\Downloads\AquaIQ'
$taskPrior=Join-Path $taskRoot 'reports\end_to_end_verification_20261022'
$taskEvidence=Join-Path $taskRoot 'reports\visual_rehearsal_preservation_20261023_01'
$manifestPath=Join-Path $taskPrior 'EVIDENCE_MANIFEST.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
$rows=@(foreach($entry in $manifest.files){$absolute=[IO.Path]::GetFullPath((Join-Path $taskPrior $entry.path));if(-not $absolute.StartsWith($taskPrior+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Manifest path outside prior audit.'};$exists=Test-Path -LiteralPath $absolute -PathType Leaf;$item=if($exists){Get-Item -LiteralPath $absolute}else{$null};$hash=if($exists){(Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash.ToLowerInvariant()}else{$null};[pscustomobject]@{path=$entry.path;exists=$exists;manifest_bytes=$entry.bytes;manifest_sha256=$entry.sha256;current_bytes=$item.Length;current_sha256=$hash;matches_manifest=($exists -and $item.Length -eq $entry.bytes -and $hash -eq $entry.sha256)}})
$result=[pscustomobject]@{captured_at_utc=[DateTime]::UtcNow.ToString('o');manifest_path='reports/end_to_end_verification_20261022/EVIDENCE_MANIFEST.json';manifest_sha256=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant();payload_count=$rows.Count;payload_matches=@($rows|Where-Object matches_manifest).Count;payload_mismatches=@($rows|Where-Object {-not $_.matches_manifest});scope='The prior manifest authenticates 478 payload files. Its own current bytes are also preserved by the separate 479-file prior-audit baseline matrix.';files=$rows}
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($result|ConvertTo-Json -Depth 12)+"`n")
$stream=[IO.File]::Open((Join-Path $taskEvidence 'prior_evidence_manifest_validation.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try{$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
[pscustomobject]@{manifest_payload_count=$rows.Count;manifest_matches=$result.payload_matches;manifest_sha256=$result.manifest_sha256}|ConvertTo-Json
