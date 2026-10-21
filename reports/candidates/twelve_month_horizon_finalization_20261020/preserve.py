"""Create-only filesystem preservation receipts; never access the database."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUTHORIZED = {'README.md', 'api_spec.md', 'api/app.py', 'api/routes/scores.py',
    'dashboard/index.html', 'dashboard/src/App.jsx', 'dashboard/src/api.js',
    'dashboard/src/pages/Home.jsx', 'dashboard/src/pages/DistrictDetail.jsx',
    'deploy/README.md'}


def digest(path):
    with path.open('rb') as handle:
        checksum = hashlib.file_digest(handle, 'sha256').hexdigest()
    return {'sha256': checksum, 'bytes': path.stat().st_size}


def write(name, value):
    with (HERE/name).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)


def git_state():
    commands = {'head':['git','rev-parse','HEAD'], 'main':['git','rev-parse','main'],
        'branch':['git','branch','--show-current'], 'status':['git','status','--short'],
        'staged':['git','diff','--cached','--name-only']}
    return {name: subprocess.check_output(command,cwd=ROOT,text=True) for name,command in commands.items()}


if sys.argv[1:] == ['before']:
    paths = set(subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],
                cwd=ROOT,text=True).splitlines())
    for directory in ('data','models/checkpoints','reports'):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/directory).rglob('*') if p.is_file())
    paths = sorted(name for name in paths if not (ROOT/name).is_relative_to(HERE)
                   and '__pycache__' not in Path(name).parts and not name.endswith('.pyc'))
    write('before.json', {'captured_at_utc':datetime.now(timezone.utc).isoformat(),
        'remote_main_verified':'98c7056057b2a0370d377afa831f528f6d408481', 'git':git_state(),
        'files':{name:digest(ROOT/name) for name in paths},
        'database':'Not accessed; no contents verification claimed.'})
elif sys.argv[1:] in (['after'], ['after-final']):
    before = json.loads((HERE/'before.json').read_text())
    changes = []
    authorized_changes = []
    for name, expected in before['files'].items():
        actual = digest(ROOT/name) if (ROOT/name).is_file() else None
        if actual != expected:
            target = authorized_changes if name in AUTHORIZED else changes
            target.append({'path':name, 'before':expected, 'after':actual})
    record = {'verified_at_utc':datetime.now(timezone.utc).isoformat(), 'checked':len(before['files']),
        'unchanged':len(before['files'])-len(changes)-len(authorized_changes), 'changes':changes,
        'authorized_source_documentation_changes':authorized_changes, 'git':git_state(),
        'database':'Not accessed; code review and no DB entry points, not a database checksum.'}
    write('preservation-final.json' if sys.argv[1:] == ['after-final'] else 'preservation.json',record)
    print(json.dumps({'checked':record['checked'],'changes':changes}))
    if changes: raise SystemExit(1)
else:
    raise SystemExit('Use before, after or after-final; existing receipts are never overwritten.')
