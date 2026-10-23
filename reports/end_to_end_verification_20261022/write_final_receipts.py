"""Create final audit receipts; preserve sources and all earlier evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
names=['browser_limit_20261023.json','commands_20261023.json','final_preservation_20261023.json']
if any((HERE/n).exists() for n in names):
    raise SystemExit('Refusing to replace final evidence')


def write(name,value):
    with (HERE/name).open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2,allow_nan=False)
        f.write('\n')


write(names[0],{
 'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
 'live_visual_verdict':'NOT VERIFIED',
 'earlier_in_app_url':'http://127.0.0.1:5182/district/HR-Kurukshetra',
 'earlier_observation':'Cached rendered content was readable on 22 October; reload returned ERR_CONNECTION_REFUSED. This is not a fresh successful live page check.',
 'new_audit_url':'http://127.0.0.1:5183/',
 'in_app_attempt':'Temporary browser tab was requested; its initial state output was truncated. No fresh chart screenshot retained.',
 'windows_browser_attempt':'Existing Edge selected, separate New tab window opened, local URL entered in address bar. Return/navigation produced the error below.',
 'exact_stop_message':'Computer Use has been stopped for this turn because it could not determine the current browser URL on Windows with enough confidence to enforce policy. Stop your work and send a final message noting why Computer Use ended.',
 'subsequent_ui_interaction':False,
 'not_verified':['Fresh rendered charts','Map interactions','Four-card layout','Responsive/mobile layout','Page navigation by clicks','Live loading/error/retry states'],
 'independent_evidence':'HTTP receipts and mocked contract tests do not substitute for visual verification.'})

commands=[
 {'command':'git -c gc.auto=0 fetch --no-tags --no-write-fetch-head --no-auto-maintenance origin refs/heads/main:refs/remotes/origin/main refs/heads/experiment/12-month-horizon:refs/remotes/origin/experiment/12-month-horizon','exit_code':0,'receipt':'remote_verification_20261023.json'},
 {'command':'git ls-remote --heads origin refs/heads/main refs/heads/experiment/12-month-horizon','exit_code':0,'receipt':'remote_verification_20261023.json'},
 {'command':'.\\venv\\Scripts\\python.exe -B reports/end_to_end_verification_20261022/run_safe_tests.py tests/test_research_forecast_api.py tests/test_research_graph_api.py tests/test_research_graph_demo.py tests/test_api_audit_regressions.py tests/test_cors_configuration.py tests/test_deployment_readiness.py tests/test_tiers.py -q -p no:cacheprovider --basetemp=reports/end_to_end_verification_20261022/checks_20261023/pytest_tmp --junitxml=reports/end_to_end_verification_20261022/checks_20261023/python-tests-01.xml','exit_code':0,'result':'161 passed','receipt':'checks_20261023/python-tests-01.txt'},
 {'command':'npm.cmd --prefix dashboard test','exit_code':0,'result':'57 passed','receipt':'frontend-tests-20261023.txt'},
 {'command':'npm.cmd --prefix dashboard run lint','exit_code':0,'receipt':'frontend-lint-20261023.txt'},
 {'command':'npm.cmd --prefix dashboard run build -- --outDir ../reports/end_to_end_verification_20261022/frontend_build_20261023','exit_code':0,'result':'Build succeeded; existing dashboard/dist not used by this command. Nonfatal outDir/bundle-size warnings.','receipt':'frontend-build-20261023.txt'},
 {'command':'.\\venv\\Scripts\\python.exe -B reports/end_to_end_verification_20261022/check_repository.py','exit_code':1,'result':'166 Python syntax passes;205/206 strict tracked JSON passes, historical reports/data_audit.json contains8NaN.1114/1115 existing file hashes match;dashboard/dist/index.html changed.','receipt':'quality_20261023.json;preservation_20261023.json'},
 {'command':'git diff --check','exit_code':0,'receipt':'quality_20261023.json'},
 {'command':'.\\venv\\Scripts\\python.exe -B reports/end_to_end_verification_20261022/api_source/live_http_20261023.py','exit_code':1,'result':'First sandbox attempt all63socketfailures WinError10013; authorized elevated retry has61/63expectedstatus and176/179contractpasses. Vite root404 and default5000proxy502 remain preserved in receipt.','receipt':'api_source/live_http_20261023.json'},
 {'command':'.\\venv\\Scripts\\python.exe -B reports/end_to_end_verification_20261022/final_live_checks.py','exit_code':0,'result':'Correct dashboard working directory launch;31/31additionalchecks. Frontendroot/deeplinks/module/boundary HTTP200.','receipt':'final_live_checks_20261023.json'},
 {'command':"From dashboard: $env:VITE_API_URL='http://127.0.0.1:5053'; & 'C:\\Program Files\\nodejs\\node.exe' '.\\node_modules\\vite\\bin\\vite.js' --host127.0.0.1 --port5183 --strictPort",'result':'Running session62619; actual arguments used separate --host/127.0.0.1 and --port/5183; startup succeeded.','exit_code':None},
 {'command':'.\\venv\\Scripts\\python.exe -B reports/end_to_end_verification_20261022/audit_server.py','result':'Running session70044; localhost5053, enforced DBread-only and saved ML.fitblocked.','exit_code':None},
 {'command':'.\\venv\\Scripts\\python.exe -B reports/candidates/twelve_month_graph_only_20261021/demo_server.py','result':'Running session76358; localhost5051 intentional original read-only routeguard.','exit_code':None},
]
for c in commands:
    receipt=c.get('receipt','')
    if ';' not in receipt and (HERE/receipt).is_file():
        c['receipt_sha256']=hashlib.sha256((HERE/receipt).read_bytes()).hexdigest()
write(names[1],{'at_utc':datetime.now(timezone.utc).isoformat(),'commands':commands,
                'additional_data_commands':'data/DATA.md and *_execution_20261023.json',
                'additional_metrics_commands':'metrics/COMMANDS.md and run receipts',
                'no_unrestricted_suite':True,'no_source_fixes':True})

before=json.loads((HERE/'before.json').read_text())
earlier=json.loads((HERE/'preservation_20261023.json').read_text())
rows=[]
for name,old in before['files'].items():
    p=ROOT/name
    if p.is_file():
        with p.open('rb') as f:
            h=hashlib.file_digest(f,'sha256').hexdigest()
    else:
        h=None
    rows.append({'path':name,'before_sha256':old['sha256'],'after_sha256':h,'unchanged':h==old['sha256']})
git=lambda *args:subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
head=git('rev-parse','HEAD')
metadata=[]
for name in ['dashboard/dist/index.html']+earlier['new_untracked_outside_audit']:
    p=ROOT/name
    s=p.stat()
    metadata.append({'path':name,'bytes':s.st_size,
                     'creation_time_utc':datetime.fromtimestamp(s.st_ctime,timezone.utc).isoformat(),
                     'last_write_time_utc':datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat(),
                     'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
write(names[2],{'at_utc':datetime.now(timezone.utc).isoformat(),'files':rows,
               'checked':len(rows),'unchanged':sum(r['unchanged'] for r in rows),
               'head':head,'head_unchanged':head==before['head'],
               'tracked_status':git('status','--porcelain=v1','--untracked-files=no'),
               'staged':git('diff','--cached','--name-status'),
               'outside_audit_new_file_metadata':metadata,
               'database_note':'No production DB content hash; audit-serving connections enforce read-only. Newly discovered aquaiq.db is0bytes; only metadata/hash read, no SQLite connection.',
               'attribution':'Writer/launcher not established by filesystem metadata. Preserve all discrepancies; no deletion or restoration performed.'})
print(json.dumps({'final_checked':len(rows),'unchanged':sum(r['unchanged'] for r in rows),'head_unchanged':head==before['head']}))
