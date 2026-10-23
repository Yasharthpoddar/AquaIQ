"""Audit-only syntax, tracked diff, and complete before-hash checks; no imports of app."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def git(*args):
    p = subprocess.run(['git', *args], cwd=ROOT, capture_output=True)
    return p.returncode, p.stdout.decode('utf-8', errors='replace'), p.stderr.decode('utf-8', errors='replace')


def exclusive(name, obj):
    with (HERE/name).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write('\n')


if __name__ == '__main__':
    outputs = ['quality_20261023.json', 'preservation_20261023.json']
    if any((HERE/name).exists() for name in outputs):
        raise SystemExit('Audit output already exists; refusing overwrite')
    code, names, _ = git('ls-files', '-z')
    assert code == 0
    tracked = names.split('\0')
    syntax = []
    strict_json = []
    for name in tracked:
        if name.endswith('.py'):
            try:
                ast.parse((ROOT/name).read_text(encoding='utf-8-sig'), filename=name)
                syntax.append({'path': name, 'pass': True})
            except Exception as e:
                syntax.append({'path': name, 'pass': False, 'exception_type': type(e).__name__})
        if name.endswith('.json'):
            try:
                def reject(value):
                    raise ValueError('Nonfinite JSON constant')
                json.loads((ROOT/name).read_text(encoding='utf-8-sig'), parse_constant=reject)
                strict_json.append({'path': name, 'pass': True})
            except Exception as e:
                strict_json.append({'path': name, 'pass': False, 'exception_type': type(e).__name__})
    diff_code, diff_out, diff_err = git('diff', '--check')
    quality = {'at_utc': datetime.now(timezone.utc).isoformat(), 'syntax': syntax,
               'strict_tracked_json': strict_json, 'git_diff_check':
               {'exit_code': diff_code, 'stdout': diff_out, 'stderr': diff_err}}
    exclusive(outputs[0], quality)
    before = json.loads((HERE/'before.json').read_text(encoding='utf-8'))
    checked = []
    for name, old in before['files'].items():
        p = ROOT/name
        digest = hashlib.file_digest(p.open('rb'), 'sha256').hexdigest() if p.is_file() else None
        checked.append({'path': name, 'before_sha256': old['sha256'], 'after_sha256': digest,
                        'unchanged': digest == old['sha256']})
    head = git('rev-parse', 'HEAD')[1].strip()
    tracked_state = git('status', '--porcelain=v1', '--untracked-files=no')[1]
    staged = git('diff', '--cached', '--name-status')[1]
    status = git('status', '--porcelain=v1', '--untracked-files=all')[1]
    original_untracked = {line[3:] for line in before['full_status'].splitlines() if line.startswith('?? ')}
    current_untracked = {line[3:] for line in status.splitlines() if line.startswith('?? ')}
    new_external = sorted(name for name in current_untracked-original_untracked
                          if not name.startswith(HERE.relative_to(ROOT).as_posix()+'/'))
    preservation = {'at_utc': datetime.now(timezone.utc).isoformat(),
                    'before_at_utc': before['captured_at_utc'], 'checked_count': len(checked),
                    'unchanged_count': sum(row['unchanged'] for row in checked), 'files': checked,
                    'head_unchanged': head == before['head'], 'head': head,
                    'tracked_status': tracked_state, 'staged': staged,
                    'new_untracked_outside_audit': new_external,
                    'database_contents_hash': 'Not taken; API connections enforced read-only.',
                    'scope_exclusions': ['.git fetched refs and runtime metadata', 'venv/node_modules',
                                         'bytecode/cache/scratch not inventoried in before.json']}
    exclusive(outputs[1], preservation)
    summary = {'syntax_files': len(syntax), 'syntax_failures': sum(not x['pass'] for x in syntax),
               'json_files': len(strict_json), 'json_failures': sum(not x['pass'] for x in strict_json),
               'diff_check_exit': diff_code, 'preserved': preservation['unchanged_count'],
               'inventoried': len(checked), 'head_unchanged': preservation['head_unchanged'],
               'new_untracked_outside_audit_count': len(new_external)}
    print(json.dumps(summary))
    raise SystemExit(0 if all(x['pass'] for x in syntax+strict_json) and diff_code == 0 and
                     all(x['unchanged'] for x in checked) and head == before['head'] and
                     not tracked_state and not staged else 1)
