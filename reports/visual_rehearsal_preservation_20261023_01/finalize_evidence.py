"""Create-only completion receipt and manifest; no application execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
if any((HERE/name).exists() for name in ['COMPLETION.json','EVIDENCE_MANIFEST.json']):
    raise SystemExit('Refusing to replace evidence')


def git(*args):
    return subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()


links=[]
for name in ['REPORT.md','MANUAL_REHEARSAL.md']:
    text=(HERE/name).read_text(encoding='utf-8')
    links.extend(re.findall(r'\]\((C:/[^)]+)\)',text))
missing=[link for link in links if not Path(re.sub(r':\d+$','',link)).is_file()]
preservation=json.loads((HERE/'preservation_final_recheck.json').read_text(encoding='utf-8-sig'))
expected='090626df28ad6414b355e2b1a4e24a4163693de5'
head=git('rev-parse','HEAD')
status=git('status','--porcelain=v1','--untracked-files=no')
staged=git('diff','--cached','--name-status')
completion={
 'at_utc':datetime.now(timezone.utc).isoformat(),'head':head,
 'expected_head_unchanged':head==expected,'tracked_status':status,'staged':staged,
 'missing_local_report_links':missing,
 'verdicts':{'academic_demonstration':'CONDITIONALLY READY','production':'NO-GO',
             'visual_verification':'NOT VERIFIED','historical_preservation':'PARTIAL',
             'current_rehearsal_file_preservation':'CONFIRMED within inventoried scope',
             'historical_writer_attribution':'UNRESOLVED'},
 'preservation_summary':{key:preservation[key] for key in [
   'protected_checked','protected_matches_rehearsal_start','protected_matches_original_baseline',
   'prior_report_checked','prior_report_unchanged','exception_checked','exception_matches_prior_final']},
 'browser_runtime_error':'failed to write kernel assets: The system cannot find the path specified. (os error 3)',
 'browser_visual_actions':0,'screenshots_created':0,
 'services_started':0,'services_stopped':0,'production_builds':0,'model_training_or_backtests':0,
 'http_provisioning_check_exit_code':0,'browser_receipt_writer_exit_code':0,
 'preservation_script_exit_codes':{
   'collect_preservation.ps1':0,'collect_history_and_html.ps1':0,
   'validate_prior_manifest.ps1':0,'recheck_preservation.ps1':0},
 'scope':'New reports/evidence only. No source/config/environment/data/checkpoint/prior-report edits; no commit/push, migration, data acquisition, restoration or shadow campaign.'}
with (HERE/'COMPLETION.json').open('x',encoding='utf-8') as f:
    json.dump(completion,f,indent=2,allow_nan=False)
    f.write('\n')
files=[]
for p in sorted(HERE.rglob('*')):
    if p.is_file() and p.name!='EVIDENCE_MANIFEST.json':
        files.append({'path':p.relative_to(HERE).as_posix(),'bytes':p.stat().st_size,
                      'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
with (HERE/'EVIDENCE_MANIFEST.json').open('x',encoding='utf-8') as f:
    json.dump({'at_utc':datetime.now(timezone.utc).isoformat(),'scope':'New rehearsal evidence, excluding this manifest itself','files':files},f,indent=2)
    f.write('\n')
print(json.dumps({'head_unchanged':head==expected,'tracked_clean':not status,'index_empty':not staged,
                  'missing_links':missing,'evidence_payloads':len(files),
                  'rehearsal_protected_matches':completion['preservation_summary']['protected_matches_rehearsal_start']}))
raise SystemExit(0 if head==expected and not status and not staged and not missing else 1)
