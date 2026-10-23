"""Frozen-submission checks: metadata, offline frontend tests and isolated build only.

No estimator, database, ingestion, refresh or deployment entry point is invoked.
Evidence files are created exclusively; existing evidence is never replaced.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def write_new(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def digest(path):
    with path.open('rb') as handle:
        checksum = hashlib.file_digest(handle, 'sha256').hexdigest()
    return {'sha256': checksum, 'bytes': path.stat().st_size}


def state():
    paths = set()
    incident = json.loads((ROOT / 'reports/preservation_incident_20261019/snapshot_before.json').read_text())
    paths.update(incident['files'])
    study = ROOT / 'reports/actual_forecast_validation_20261019'
    inventory = json.loads((study / 'INVENTORY.json').read_text())
    paths.update((study.relative_to(ROOT) / name).as_posix() for name in inventory['files'])
    # Include all completed report files, including their inventories themselves.
    for folder in ('scientific_validation_audit_20261018', 'post_audit_safe_fixes_20261019',
                   'provenance_issuance_20261019', 'submission_finalization_20261019',
                   'actual_forecast_validation_20261019', 'preservation_incident_20261019'):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'reports' / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    for folder in ('data', 'models/checkpoints', 'dashboard/dist'):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    files = {name: digest(ROOT / name) if (ROOT / name).is_file() else {'missing': True}
             for name in sorted(paths)}
    git = {}
    for label, command in [('status', ['git', 'status', '--short']),
                           ('branch', ['git', 'branch', '--show-current']),
                           ('head', ['git', 'rev-parse', 'HEAD']),
                           ('remote', ['git', 'remote', '-v']),
                           ('staged', ['git', 'diff', '--cached', '--name-only'])]:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        git[label] = {'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    return {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
            'client_date': '2026-10-20', 'git': git, 'files': files,
            'database_contents': 'Not accessed; file/configuration hashes do not verify database contents.'}


def checks():
    build = ROOT / 'scratch/final-stabilization-build-20261020'
    junit = HERE / 'metadata-tests.xml'
    if build.exists() or junit.exists() or (HERE / 'checks.json').exists():
        raise SystemExit('Output already exists; refusing to repeat or overwrite evidence.')
    commands = [
        ['npm.cmd', '--prefix', 'dashboard', 'test'],
        [str(ROOT / 'venv/Scripts/python.exe'), '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
         'tests/test_post_audit_metadata.py', '--junitxml=' + str(junit)],
        ['npm.cmd', '--prefix', 'dashboard', 'run', 'lint'],
        ['npm.cmd', '--prefix', 'dashboard', 'run', 'build', '--', '--outDir', str(build)],
        ['git', 'diff', '--check'],
    ]
    results = []
    for index, command in enumerate(commands, 1):
        start = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        entry = {'command': command, 'started_at_utc': start,
                 'ended_at_utc': datetime.now(timezone.utc).isoformat(),
                 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        write_new(f'check-{index}.json', entry)
        results.append(entry)
        print(f'Check {index}/{len(commands)}: exit {result.returncode}', flush=True)
    write_new('checks.json', {'scope': '14 unique safe finalization tests; lint; isolated build; whitespace',
                              'build_was_absent': True, 'deployed': False, 'results': results})
    if any(item['exit_code'] for item in results):
        raise SystemExit(1)


if __name__ == '__main__':
    if sys.argv[1:] == ['before']:
        write_new('before.json', state())
    elif sys.argv[1:] == ['checks']:
        checks()
    elif sys.argv[1:] == ['after']:
        after = state()
        before = json.loads((HERE / 'before.json').read_text())
        changes = [name for name, metadata in before['files'].items()
                   if after['files'].get(name) != metadata]
        write_new('after.json', after)
        write_new('preservation.json', {'checked': len(before['files']), 'changed': changes,
                                       'unchanged': len(before['files']) - len(changes),
                                       'database_contents': 'Not accessed or independently verified.'})
        print(json.dumps({'checked': len(before['files']), 'changed': changes}))
    else:
        raise SystemExit('Use before, checks, or after.')
