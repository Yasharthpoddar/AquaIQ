"""Create/verify a byte-preservation inventory for the scoped F6/F10 repairs.

No model, database, data-ingestion or forecasting module is imported.
Creation is exclusive; --check-only verification never writes output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ALLOWED_EDITS = {'README.md', 'models/ann_classifier.py', 'models/linear_regression.py'}
ALLOWED_NEW_TESTS = {'tests/test_post_audit_reporting.py', 'tests/test_post_audit_metadata.py'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(name, value):
    with (HERE/name).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def files():
    paths = {ROOT/name for name in git('ls-files').splitlines()}
    for name in ['data', 'models/checkpoints', 'reports']:
        paths.update(p for p in (ROOT/name).rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in sorted(paths) if p.is_file() and HERE not in p.parents
            and '__pycache__' not in p.parts and p.name != '.env'}


def active_artifacts():
    result = {}
    for pointer_name in ['aquaiq_xgb.json', 'aquaiq_monthly_climate.json']:
        pointer_path = ROOT/'models/checkpoints'/pointer_name
        pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
        for path, expected in [(pointer_path, None),
                               (pointer_path.parent/pointer['model_path'], pointer['model_sha256']),
                               (pointer_path.parent/pointer['card_path'], pointer['card_sha256'])]:
            actual = sha(path)
            assert expected is None or actual == expected, str(path)
            result[path.relative_to(ROOT).as_posix()] = actual
    return result


def snapshot():
    write('before.json', {'audit_date': '2026-10-19', 'branch': git('branch','--show-current'),
        'commit': git('rev-parse','HEAD'),
        'git_status_at_snapshot': git('status','--short','--untracked-files=all'),
        'existing_files': files(), 'active_artifacts': active_artifacts(),
        'allowed_existing_source_edits': sorted(ALLOWED_EDITS),
        'note': 'Existing October 18 audit is untracked user evidence and is protected. Snapshot status includes this new helper.'})


def verify(check_only):
    before = json.loads((HERE/'before.json').read_text(encoding='utf-8'))
    assert git('rev-parse','HEAD') == before['commit'], 'Commit changed during this task'
    assert git('branch','--show-current') == before['branch'], 'Branch changed during this task'
    unchanged, changed = [], {}
    for name, original in before['existing_files'].items():
        path = ROOT/name
        assert path.is_file(), f'Missing pre-existing file: {name}'
        after = sha(path)
        if after == original['sha256']:
            unchanged.append(name)
        else:
            assert name in ALLOWED_EDITS, f'Unexpected pre-existing change: {name}'
            changed[name] = {'before_sha256': original['sha256'], 'after_sha256': after}
    active_after = active_artifacts()
    assert before['active_artifacts'] == active_after
    for base in ['data', 'models/checkpoints', 'reports']:
        for path in (ROOT/base).rglob('*'):
            if path.is_file() and HERE not in path.parents and '__pycache__' not in path.parts:
                name = path.relative_to(ROOT).as_posix()
                assert name in before['existing_files'], f'Unexpected protected-directory addition: {name}'
    tracked_changes = set(git('diff','--name-only').splitlines())
    assert tracked_changes <= ALLOWED_EDITS, tracked_changes
    untracked = git('ls-files','--others','--exclude-standard').splitlines()
    for name in untracked:
        assert name in before['existing_files'] or name in ALLOWED_NEW_TESTS or HERE in (ROOT/name).parents, name
    result = {'audit_date':'2026-10-19', 'existing_files_checked':len(before['existing_files']),
        'unchanged_existing_files':len(unchanged), 'allowed_source_changes':changed,
        'protected_datasets_checkpoints_and_previous_reports_unchanged':True,
        'active_artifacts_before':before['active_artifacts'], 'active_artifacts_after':active_after,
        'git_status':git('status','--short','--untracked-files=all'),
        'scope':'Byte integrity only. No fitting/forecasting/DB operations are invoked by this helper.'}
    if not check_only:
        write('after.json', result)
    print(json.dumps({'existing_files_checked':len(before['existing_files']),
        'unchanged_existing_files':len(unchanged), 'allowed_changes':sorted(changed),
        'active_artifacts_unchanged':True}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot','verify'])
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.action == 'snapshot':
        if args.check_only:
            parser.error('snapshot is create-only; use verify --check-only')
        snapshot()
    else:
        verify(args.check_only)
