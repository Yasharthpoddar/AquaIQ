"""Create an immutable baseline of non-frontend research/runtime assets."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=HERE/'before.json'
if OUT.exists():
    raise SystemExit('Refusing to replace baseline')
folders=['api','db','data','models','preprocessing','research','reports','dashboard/dist']
paths=set()
for name in folders:
    folder=ROOT/name
    for p in folder.rglob('*'):
        if p.is_file() and HERE not in p.parents and '__pycache__' not in p.parts:
            paths.add(p)
for name in ['.env','.env.example','config.yaml','requirements.txt','requirements-download.txt',
             'requirements-tracking.txt','dashboard/package.json','dashboard/package-lock.json']:
    p=ROOT/name
    if p.is_file():
        paths.add(p)
files={}
for p in sorted(paths):
    with p.open('rb') as f:
        digest=hashlib.file_digest(f,'sha256').hexdigest()
    files[p.relative_to(ROOT).as_posix()]={'bytes':p.stat().st_size,'sha256':digest}
def git(*args):
    return subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
with OUT.open('x',encoding='utf-8') as f:
    json.dump({'at_utc':datetime.now(timezone.utc).isoformat(),'head':git('rev-parse','HEAD'),
               'branch':git('branch','--show-current'),'files':files,
               'scope':'Preserved non-frontend source, datasets, checkpoints, existing reports, config/env hashes and prior dashboard/dist. No private file contents copied.'},f,indent=2)
print(json.dumps({'protected_files':len(files),'head':git('rev-parse','HEAD'),'branch':git('branch','--show-current')}))
