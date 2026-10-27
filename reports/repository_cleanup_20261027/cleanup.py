"""One-off, inventory-driven cleanup with workspace and preservation guards.

Only reviewed pytest fixture trees, regenerable source bytecode and pytest's
own cache are eligible. No git clean, source pruning, database mutation, or
parent-directory recursive deletion is used. Secrets are never opened.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE_ROOTS = {'api','db','data_ingestion','models','preprocessing','scripts','tests','reports','notebooks'}
SKIP = {'.git','.agents','.codex','.aws','venv','.venv','node_modules'}
PRIVATE_SUFFIXES = {'.db','.sqlite','.sqlite3','.dump','.pem','.key','.pfx'}
_VALIDATED_ANCESTORS = set()


def private(path):
    n=path.name.lower()
    return ((n.startswith('.env') and n!='.env.example') or path.suffix.lower() in PRIVATE_SUFFIXES
            or any(word in n for word in ['credentials','secrets','licence','license']))


def linked(path):return path.is_symlink() or path.is_junction()


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def write(path,value):
    if path.exists():raise FileExistsError(f'Choose a fresh receipt: {path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT).decode('utf-8')


def files_below(directory):
    """Never traverse a junction/symlink or an embedded environment/repository."""
    for current,dirs,files in os.walk(directory,followlinks=False):
        base=Path(current)
        if 'pyvenv.cfg' in files:
            dirs[:]=[]
            continue
        dirs[:]=[n for n in dirs if n not in SKIP and not linked(base/n)]
        for n in files:
            p=base/n
            if not linked(p):yield p


def eligible_file(path,category):
    # Lexical containment plus explicit reparse-point checks avoids resolving
    # every shared ancestor repeatedly for tens of thousands of fixture files.
    absolute=Path(os.path.abspath(path))
    if absolute==ROOT or not absolute.is_relative_to(ROOT):return False
    relative=absolute.relative_to(ROOT)
    if private(path) or linked(path):return False
    checked=[]
    for parent in absolute.parents:
        if parent==ROOT.parent or parent in _VALIDATED_ANCESTORS:break
        if linked(parent):return False
        checked.append(parent)
    _VALIDATED_ANCESTORS.update(checked)
    if category=='pytest_fixture':
        return len(relative.parts)>2 and relative.parts[0]=='scratch' and relative.parts[1].startswith('pytest-')
    if category=='pytest_cache':return relative.parts[0]=='.pytest_cache'
    if category=='validation_build':
        return relative.parts[:3]==('scratch','repository_cleanup_20261027','frontend-dist') and len(relative.parts)>3
    if category=='bytecode':
        if relative.parts[0] not in SOURCE_ROOTS or '__pycache__' not in relative.parts or path.suffix not in {'.pyc','.pyo'}:return False
        source=path.parent.parent/(path.name.split('.cpython-')[0].split('.pypy')[0]+'.py')
        return source.is_file()
    return False


def reference_index():
    """Exact existing-file references in docs and JSON, excluding output commands.

    --basetemp in a historical command is a regenerable destination. Explicit
    manifest/file references remain protected even if the payload is generated.
    """
    references={}
    for start in [ROOT/'reports',ROOT/'docs',ROOT/'research',ROOT/'README.md']:
        for p in ([start] if start.is_file() else files_below(start)):
            if p.is_relative_to(HERE) or '__pycache__' in p.parts or private(p):continue
            if p.suffix.lower() not in {'.md','.json'} or p.stat().st_size>6_000_000:continue
            try:
                if p.suffix=='.json':
                    obj=json.loads(p.read_text(encoding='utf-8'))
                    def strings(value):
                        if isinstance(value,str):yield value
                        elif isinstance(value,list):
                            for x in value:yield from strings(x)
                        elif isinstance(value,dict):
                            for k,v in value.items():
                                yield k
                                yield from strings(v)
                    values=strings(obj)
                else:
                    import re
                    values=re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8'))
                for value in values:
                    if len(value)>500 or '\n' in value or ' --' in value or value.startswith(('http:','https:')):continue
                    if not any(mark in value for mark in ['pytest-','pytest_tmp','__pycache__','.pytest_cache']):continue
                    value=value.replace('\\','/').split('#',1)[0]
                    for path in [Path(value),ROOT/value,p.parent/value]:
                        try:
                            path=path.resolve()
                            if path.is_file() and path.is_relative_to(ROOT):
                                references.setdefault(path.relative_to(ROOT).as_posix(),set()).add(p.relative_to(ROOT).as_posix())
                        except (OSError,ValueError):pass
            except (ValueError,UnicodeError,OSError):continue
    return references


def plan(label):
    destination=HERE/label
    if destination.exists():raise FileExistsError('Use a fresh plan label.')
    destination.mkdir(parents=True)
    tracked=set(git('ls-files','-z').split('\0'))-{''}
    references=reference_index()
    roots=[];kept=[]
    for p in sorted((ROOT/'scratch').iterdir()):
        if not p.is_dir() or not p.name.startswith('pytest-') or linked(p):continue
        children=list(p.iterdir())
        unexpected=[c.name for c in children if not ((c.is_dir() and (c.name.startswith('test_') or c.name.startswith('nationwide')))
                                                   or c.name=='.lock')]
        payload=list(files_below(p))
        blocked=[q for q in payload if q.relative_to(ROOT).as_posix() in tracked
                 or q.relative_to(ROOT).as_posix() in references or private(q)]
        if unexpected or blocked:
            kept.append({'path':p.relative_to(ROOT).as_posix(),'action':'unresolved',
                         'reason':'Unexpected child, protected/private file or explicit evidence reference.',
                         'unexpected_children':unexpected,'protected_files':[q.relative_to(ROOT).as_posix() for q in blocked]})
        else:roots.append((p,'pytest_fixture'))
    cache=ROOT/'.pytest_cache'
    if cache.is_dir() and not linked(cache):roots.append((cache,'pytest_cache'))
    for name in sorted(SOURCE_ROOTS):
        for current,dirs,_ in os.walk(ROOT/name,followlinks=False):
            base=Path(current)
            dirs[:]=[n for n in dirs if n not in SKIP and not linked(base/n)]
            if base.is_relative_to(HERE):dirs[:]=[];continue
            if base.name=='__pycache__':
                payload=list(files_below(base))
                if all(eligible_file(p,'bytecode') and p.relative_to(ROOT).as_posix() not in tracked
                       and p.relative_to(ROOT).as_posix() not in references for p in payload):roots.append((base,'bytecode'))
                else:kept.append({'path':base.relative_to(ROOT).as_posix(),'action':'unresolved','reason':'Not every bytecode file has a corresponding source or is unreferenced.'})
                dirs[:]=[]
    entries=[];groups=[]
    for directory,category in roots:
        payload=list(files_below(directory))
        for p in payload:
            if not eligible_file(p,category):raise ValueError(f'Unsafe candidate: {p}')
            stat=p.stat()
            entries.append({'path':p.relative_to(ROOT).as_posix(),'category':category,
                            'size':stat.st_size,'mtime_ns':stat.st_mtime_ns})
        names=[p.relative_to(ROOT).as_posix() for p in payload]
        assert not (set(names)&tracked)
        groups.append({'path':directory.relative_to(ROOT).as_posix(),'classification':category,
            'tracked_status':'ignored','files':len(payload),'bytes':sum(p.stat().st_size for p in payload),
            'reason':'Regenerable pytest tmp_path/tmp_path_factory payload; original source/data and final receipts retained.' if category=='pytest_fixture'
                     else 'Interpreter bytecode with retained .py source.' if category=='bytecode' else 'Pytest cache only; authoritative results are JUnit/JSON receipts.',
            'dependency_check':'Exact JSON/Markdown evidence references checked; no tracked payload; pytest generators in tests and immutable final reports retained.',
            'recovery':'Rerun documented pytest command with a fresh --basetemp.' if category=='pytest_fixture' else 'Regenerated by Python/pytest.',
            'action':'delete'})
    names=[e['path'] for e in entries]
    assert len(names)==len(set(names))
    with gzip.open(destination/'deletion_files.json.gz','wt',encoding='utf-8') as handle:json.dump(entries,handle,separators=(',',':'))
    body={'created_at_utc':datetime.now(timezone.utc).isoformat(),'root':str(ROOT),
          'branch':git('branch','--show-current').strip(),'head':git('rev-parse','HEAD').strip(),
          'groups':groups,'unresolved':kept,'files':len(entries),'logical_bytes':sum(e['size'] for e in entries),
          'deletion_files_sha256':sha(destination/'deletion_files.json.gz'),
          'tracked_files_to_delete':0,'private_values_read':False,
          'reference_policy':'Historical output-directory arguments are regenerable destinations. Exact existing-file references in Markdown/JSON are retained.',
          'generator_proof':['tests use tmp_path for test_* directories','tests/test_forecast_storage.py:36-40 explicitly generates nationwide* using tmp_path_factory and dry-run inference; no accepted measurements are unique to these exports.']}
    write(destination/'plan.json',body)
    with (destination/'inventory.csv').open('w',newline='',encoding='utf-8') as handle:
        fields=['path','classification','tracked_status','files','bytes','reason','dependency_check','recovery','action']
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(groups)
    print(json.dumps({'plan':str(destination/'plan.json'),'plan_sha256':sha(destination/'plan.json'),
                      'groups':len(groups),'files':body['files'],'logical_bytes':body['logical_bytes'],
                      'unresolved':kept},indent=2),flush=True)


def preservation(label):
    destination=HERE/label
    if destination.exists():raise FileExistsError('Use a fresh preservation label.')
    destination.mkdir()
    with gzip.open(HERE/'initial/deletion_files.json.gz','rt',encoding='utf-8') as handle:
        disposable={e['path'] for e in json.load(handle)}
    hashes={};private_presence=[]
    for p in files_below(ROOT):
        rel=p.relative_to(ROOT).as_posix()
        if p.is_relative_to(HERE) or rel in disposable:continue
        if private(p):
            private_presence.append({'path':rel,'present':True,'tracked':bool(git('ls-files','--',rel).strip())})
            continue
        hashes[rel]=sha(p)
    write(destination/'protected_hashes.json',hashes)
    write(destination/'private_presence.json',private_presence)
    write(destination/'git_start.json',{'starting_branch':'feature/aquaiq-accuracy-experiments-20261027',
        'starting_commit':'d992d396b103a57f04e1ebf433e3591aa626550d',
        'cleanup_branch':git('branch','--show-current').strip(),
        'status':git('status','--short','--branch'),'staged':git('diff','--cached','--name-status'),
        'tracked_files':len(git('ls-files','-z').split('\0'))-1,
        'note':'Pre-existing .gitignore/.gitattributes edits and all local accuracy work are preserved and excluded from the cleanup commit.'})
    print(f'Preservation seal: {len(hashes)} file hashes; {len(private_presence)} private files recorded by presence only.',flush=True)


def plan_validation():
    """Only outputs created by this cleanup's successful verification commands."""
    destination=HERE/'post_validation'
    if destination.exists():raise FileExistsError('Validation cleanup plan already exists.')
    for name in ['python_exit.json','frontend_build_exit.json']:
        if json.loads((HERE/name).read_text(encoding='utf-8-sig'))['exit_code']!=0:
            raise ValueError('Retain failed verification payloads for investigation.')
    before=json.loads((HERE/'preservation/protected_hashes.json').read_text(encoding='utf-8'))
    roots=[(ROOT/'scratch/pytest-repository-cleanup-20261027','pytest_fixture'),
           (ROOT/'scratch/repository_cleanup_20261027/frontend-dist','validation_build')]
    entries=[];groups=[]
    for directory,category in roots:
        relative=directory.relative_to(ROOT).as_posix()
        if any(n==relative or n.startswith(relative+'/') for n in before):
            raise ValueError('Validation output overlaps pre-existing protected work.')
        if not directory.is_dir():continue
        payload=list(files_below(directory))
        for p in payload:
            if not eligible_file(p,category):raise ValueError('Unexpected validation payload; retain for review.')
            stat=p.stat();entries.append({'path':p.relative_to(ROOT).as_posix(),'category':category,
                                         'size':stat.st_size,'mtime_ns':stat.st_mtime_ns})
        groups.append({'path':relative,'classification':category,'tracked_status':'ignored',
            'files':len(payload),'bytes':sum(p.stat().st_size for p in payload),
            'reason':'Created by this cleanup verification; successful receipts and sanitized JUnit retained.',
            'dependency_check':'Absent from the pre-cleanup preservation seal; exact successful generator commands recorded.',
            'recovery':'Rerun the recorded pytest or frontend build command.','action':'delete'})
    destination.mkdir()
    with gzip.open(destination/'deletion_files.json.gz','wt',encoding='utf-8') as handle:json.dump(entries,handle,separators=(',',':'))
    write(destination/'plan.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'root':str(ROOT),
        'groups':groups,'files':len(entries),'logical_bytes':sum(e['size'] for e in entries),
        'deletion_files_sha256':sha(destination/'deletion_files.json.gz'),'tracked_files_to_delete':0})
    print(json.dumps({'plan_sha256':sha(destination/'plan.json'),'groups':groups},indent=2),flush=True)


def apply(plan_path,expected):
    plan_path=Path(plan_path).resolve()
    if not plan_path.is_relative_to(HERE) or sha(plan_path)!=expected:raise ValueError('Unreviewed plan or checksum mismatch.')
    body=json.loads(plan_path.read_text(encoding='utf-8'))
    if body['root']!=str(ROOT):raise ValueError('Workspace mismatch.')
    manifest=plan_path.parent/'deletion_files.json.gz'
    if sha(manifest)!=body['deletion_files_sha256']:raise ValueError('Deletion manifest changed.')
    receipt=plan_path.parent/'applied.json'
    if receipt.exists():raise FileExistsError('This plan has already been applied.')
    with gzip.open(manifest,'rt',encoding='utf-8') as handle:entries=json.load(handle)
    # Complete preflight before removing any file. Never follow reparse points.
    for e in entries:
        p=ROOT/e['path']
        if not eligible_file(p,e['category']):raise ValueError(f'Unsafe changed target: {e["path"]}')
        stat=p.stat()
        if stat.st_size!=e['size'] or stat.st_mtime_ns!=e['mtime_ns']:raise ValueError(f'Changed since dry run: {e["path"]}')
    free_before=shutil.disk_usage(ROOT).free
    removed=0;logical=0;failed=[]
    for e in entries:
        p=ROOT/e['path']
        try:p.unlink()
        except OSError as error:
            failed.append({'path':e['path'],'error_type':type(error).__name__})
            continue
        removed+=1;logical+=e['size']
    removed_dirs=0
    for group in sorted(body['groups'],key=lambda g:len(g['path']),reverse=True):
        directory=ROOT/group['path']
        if not directory.resolve().is_relative_to(ROOT) or linked(directory):raise ValueError('Unsafe directory cleanup target.')
        for current,dirs,_ in os.walk(directory,topdown=False,followlinks=False):
            p=Path(current)
            if linked(p):continue
            try:p.rmdir();removed_dirs+=1
            except OSError:pass
    remaining=[g['path'] for g in body['groups'] if (ROOT/g['path']).exists()]
    write(receipt,{'plan_sha256':expected,'removed_files':removed,'removed_empty_directories':removed_dirs,
        'logical_bytes_removed':logical,'disk_free_before':free_before,'disk_free_after':shutil.disk_usage(ROOT).free,
        'remaining_group_directories':remaining,'failed_files':failed,
        'tracked_files_removed':0,'database_operations':False,'finished_at_utc':datetime.now(timezone.utc).isoformat()})
    print(receipt.read_text(encoding='utf-8'),flush=True)


def verify(label='preservation_after'):
    if not label.replace('_','').replace('-','').isalnum():raise ValueError('Use a simple receipt label.')
    before=json.loads((HERE/'preservation/protected_hashes.json').read_text(encoding='utf-8'))
    failures=[]
    for name,expected in before.items():
        p=ROOT/name
        if not p.is_file() or sha(p)!=expected:failures.append(name)
    private_before=json.loads((HERE/'preservation/private_presence.json').read_text(encoding='utf-8'))
    if any(not (ROOT/e['path']).exists() for e in private_before):raise ValueError('A private configuration file disappeared.')
    write(HERE/(label+'.json'),{'protected_file_count':len(before),'changed_or_missing':failures,
        'private_values_read':False,'private_files_preserved':len(private_before),'passed':not failures})
    if failures:raise ValueError('Protected files changed; inspect preservation_after.json.')
    print(f'All {len(before)} protected file hashes unchanged.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('plan');p.add_argument('--label',required=True)
    p=sub.add_parser('preserve');p.add_argument('--label',default='preservation')
    sub.add_parser('plan-validation')
    p=sub.add_parser('apply');p.add_argument('--plan',type=Path,required=True);p.add_argument('--expected-sha256',required=True)
    p=sub.add_parser('verify');p.add_argument('--label',default='preservation_after')
    args=parser.parse_args()
    if args.action=='plan':plan(args.label)
    elif args.action=='preserve':preservation(args.label)
    elif args.action=='plan-validation':plan_validation()
    elif args.action=='apply':apply(args.plan,args.expected_sha256)
    else:verify(args.label)
