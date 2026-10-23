"""Read-only file verification and in-memory diffs; creates incident evidence only.

No AquaIQ imports, source regeneration, refresh, network, DB or model execution.
The reconstructed timestamp candidate is never written as an affected JSON file.
"""
from __future__ import annotations
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
STUDY = ROOT / 'reports/actual_forecast_validation_20261019'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def write(name, value):
    with (OUT/name).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')


def differences(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        result = []
        for key in sorted(set(a)|set(b)):
            if key not in a or key not in b:
                result.append({'field':path+'/'+key,'before':a.get(key),'after':b.get(key)})
            else:
                result.extend(differences(a[key],b[key],path+'/'+key))
        return result
    return [] if a == b else [{'field':path,'before':a,'after':b}]


def stat_record(path):
    s = path.stat()
    return {'path':path.relative_to(ROOT).as_posix(),'bytes':s.st_size,'sha256':sha(path),
        'modified_at_utc':datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat(),
        'created_at_utc':datetime.fromtimestamp(s.st_birthtime,timezone.utc).isoformat() if hasattr(s,'st_birthtime') else None}


def main():
    original = json.loads((STUDY/'before.json').read_text())
    preservation = json.loads((STUDY/'preservation.json').read_text())
    changes = {r['path']:r for r in preservation['changes']}
    candidate_rel = 'reports/candidates/rainfall_refresh/2026-01_2026-09/progress.json'
    download_rel = 'data/raw/updates/rainfall_refresh/overlap/2025/download_progress.json'
    prior_stdout = ROOT/'reports/candidates/rainfall_refresh/task_logs/refresh-20261018T134200-25188.stdout.log'
    stdout = ROOT/'reports/candidates/rainfall_refresh/task_logs/refresh-20261019T143421-15428.stdout.log'
    stderr = stdout.with_name('refresh-20261019T143421-15428.stderr.log')
    candidate_before, candidate_after = prior_stdout.read_bytes(), (ROOT/candidate_rel).read_bytes()
    assert digest(candidate_before) == changes[candidate_rel]['before_sha256']
    assert digest(candidate_after) == changes[candidate_rel]['after_sha256'] == sha(stdout)
    assert candidate_after == (STUDY/'discrepancy_after_bytes/candidate_progress.json').read_bytes()
    before_obj, after_obj = json.loads(candidate_before), json.loads(candidate_after)
    old_time = before_obj['phases']['overlap_download']['updated_at_utc']
    new_time = after_obj['phases']['overlap_download']['updated_at_utc']
    download_after = (ROOT/download_rel).read_bytes()
    assert digest(download_after) == changes[download_rel]['after_sha256']
    assert download_after == (STUDY/'discrepancy_after_bytes/download_progress.json').read_bytes()
    assert download_after.count(new_time.encode()) == 1
    # This lives only in memory, is hash-verified, and is NOT archived as an original file.
    download_before = download_after.replace(new_time.encode(),old_time.encode(),1)
    assert digest(download_before) == changes[download_rel]['before_sha256']
    details = []
    for label, relative, before_bytes, after_bytes, kind in [
        ('candidate_progress',candidate_rel,candidate_before,candidate_after,'Authentic prior stdout exactly matches recorded before SHA-256.'),
        ('download_progress',download_rel,download_before,download_after,'No standalone prior bytes found; one timestamp inverse performed only in memory and exactly matches recorded before SHA-256.')]:
        diffs = differences(json.loads(before_bytes),json.loads(after_bytes))
        assert len(diffs) == (2 if label == 'candidate_progress' else 1)
        assert all(d['field'].endswith('/updated_at_utc') for d in diffs)
        with (OUT/(label+'.diff')).open('x',encoding='utf-8',newline='') as handle:
            handle.writelines(difflib.unified_diff(before_bytes.decode('utf-8').splitlines(True),
                after_bytes.decode('utf-8').splitlines(True),fromfile=relative+' (recorded before)',tofile=relative+' (recorded after)'))
        details.append({'path':relative,'before_sha256':digest(before_bytes),'after_sha256':digest(after_bytes),
            'before_evidence':kind,'before_bytes':len(before_bytes),'after_bytes':len(after_bytes),
            'json_differences':diffs,'different_byte_positions':[i for i,(a,b) in enumerate(zip(before_bytes,after_bytes)) if a!=b],
            'CRLF_count_before':before_bytes.count(b'\r\n'),'CRLF_count_after':after_bytes.count(b'\r\n'),
            'all_other_JSON_fields_equal':True})
    assert after_obj['phases']['overlap_download']['counts']['downloaded']==0
    assert after_obj['phases']['overlap_download']['counts']['already_present']==3
    write('exact_diffs.json',{'collected_at_utc':datetime.now(timezone.utc).isoformat(),'files':details,
        'current_candidate_equals_current_stdout':True,'stderr_empty':stderr.stat().st_size==0,
        'download_before_written_to_disk':False,'originals_or_after_files_modified':False})
    times = [stat_record(ROOT/download_rel),stat_record(ROOT/candidate_rel),stat_record(prior_stdout),stat_record(stdout),stat_record(stderr)]
    write('file_timestamps.json',times)
    old_status = []
    for path,expected in original['files'].items():
        file=ROOT/path;actual=sha(file) if file.is_file() else None
        if actual!=expected['sha256']:
            old_status.append({'path':path,'expected_sha256':expected['sha256'],'actual_sha256':actual})
    assert {r['path'] for r in old_status}=={candidate_rel,download_rel}
    inventory=json.loads((STUDY/'INVENTORY.json').read_text())
    study_results=[]
    for path,expected in inventory['files'].items():
        file=STUDY/path;actual=sha(file) if file.is_file() else None
        study_results.append({'path':path,'matches':actual==expected['sha256'],'expected_sha256':expected['sha256'],'actual_sha256':actual})
    assert all(row['matches'] for row in study_results)
    groups={}
    for prefix in ['acquired/','normalized/','normalized_v2/','evaluation/','evaluation_v2/','well_baselines/']:
        selected=[r for r in study_results if r['path'].startswith(prefix)]
        groups['research/'+prefix]={'verified_files':len(selected),'all_match':all(r['matches'] for r in selected)}
    prior_groups=['models/checkpoints/','reports/scientific_validation_audit_20261018/',
        'reports/post_audit_safe_fixes_20261019/','reports/provenance_issuance_20261019/',
        'reports/submission_finalization_20261019/']
    for prefix in prior_groups:
        paths=[p for p in original['files'] if p.startswith(prefix)]
        assert all(sha(ROOT/p)==original['files'][p]['sha256'] for p in paths)
        groups[prefix]={'verified_files':len(paths),'all_match':True}
    assert sha(ROOT/'data/processed/features_matrix.csv')==original['files']['data/processed/features_matrix.csv']['sha256']
    git_status=subprocess.check_output(['git','--no-optional-locks','status','--short'],cwd=ROOT,text=True).strip()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert head==original['commit']
    write('verification.json',{'collected_at_utc':datetime.now(timezone.utc).isoformat(),
        'research_inventory_files_checked':len(study_results),'all_research_inventory_hashes_match':True,
        'original_before_files_checked':len(original['files']),'original_before_files_unchanged':len(original['files'])-len(old_status),
        'only_original_discrepancies':old_status,'verified_groups':groups,'active_feature_export_unchanged':True,
        'research_file_checks':study_results,'head':head,'git_status':git_status,
        'limits':'Local hashes establish consistency with retained inventories, not an independently signed chain of custody; no database access or model execution.'})
    history=Path(r'C:\Users\Yasharth\.codex\sessions\2026\10\11\rollout-2026-10-11T17-02-41-01a12abc-87e1-7b33-82e0-a7336a83f9ba.jsonl')
    call='call_fcb59b94d9124c738ce7654b74d6bea5'
    selected=[]
    for number,line in enumerate(history.open(encoding='utf-8'),1):
        if call not in line:continue
        row=json.loads(line);p=row.get('payload',{})
        if p.get('call_id')==call:
            selected.append({'record_path':str(history),'line':number,'timestamp':row.get('timestamp'),'payload':p})
    assert len(selected)==2
    write('historical_registration_record.json',{'purpose':'Only exact registration command and its recorded response, not unrelated session content.',
        'call_id':call,'records':selected})
    print(json.dumps({'diffs':'Only three timestamp fields across two files','original_files_unchanged':len(original['files'])-len(old_status),
        'research_files_verified':len(study_results),'groups':groups},indent=2))


if __name__=='__main__':
    main()
