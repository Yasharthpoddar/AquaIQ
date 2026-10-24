"""Compare protected files with the original baseline; never modify protected paths."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
baseline = json.loads((HERE / 'before.json').read_text(encoding='utf-8'))
out = HERE / 'preservation.json'
if out.exists():
    raise SystemExit('Refusing to replace preservation evidence')

current = {}
missing = []
changed = []
for name, before in baseline['files'].items():
    path = ROOT / name
    if not path.is_file():
        missing.append(name)
        continue
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    current[name] = {'bytes': path.stat().st_size, 'sha256': digest}
    if current[name] != before:
        changed.append(name)

protected = set()
for folder in ['api', 'db', 'data', 'models', 'preprocessing', 'research', 'reports', 'dashboard/dist']:
    for path in (ROOT / folder).rglob('*'):
        if path.is_file() and HERE not in path.parents and '__pycache__' not in path.parts:
            protected.add(path.relative_to(ROOT).as_posix())
new = sorted(protected - set(baseline['files']))

def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()

result = {
    'at_utc': datetime.now(timezone.utc).isoformat(),
    'head': git('rev-parse', 'HEAD'),
    'branch': git('branch', '--show-current'),
    'baseline_files': len(baseline['files']),
    'unchanged_files': len(current) - len(changed),
    'changed': changed,
    'missing': missing,
    'new_in_protected_folders': new,
    'files': current,
    'scope': 'Byte hashes cover existing local files, not a database content snapshot. '
             'Live preview used the existing audit server with DB sessions forced read-only and active ML fit blocked. '
             'Test wrapper forbids live DB connections and fitting, including transient monthly projection fitting.',
}
with out.open('x', encoding='utf-8') as handle:
    json.dump(result, handle, indent=2)
print(json.dumps({key: value for key, value in result.items() if key != 'files'}))
raise SystemExit(1 if changed or missing or new else 0)
