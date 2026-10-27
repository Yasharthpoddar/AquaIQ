"""Recover archived report payloads from retained Git history, without overwrite."""
import argparse
import hashlib
import json
import ntpath
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'reports/repository_simplification_20261027/archives.json'


def safe_path(name):
    path=PurePosixPath(name)
    if (not name or '\\' in name or '\n' in name or ':' in name or path.is_absolute() or '..' in path.parts
            or not path.parts or path.parts[0]!='reports' or '.git' in path.parts
            or any(ntpath.isreserved(part) for part in path.parts)
            or path.name.startswith('.env') or path.suffix.lower() in {'.key','.pem','.db','.sqlite','.sqlite3','.dump'}):
        raise ValueError('Archive targets must be safe report-relative paths.')
    return Path(*path.parts)


def materialize(entry, fetch=None):
    path=safe_path(entry['path'])
    if not re.fullmatch(r'[0-9a-f]{40}',entry['commit']):raise ValueError('Expected an exact Git commit.')
    fetch=fetch or (lambda ref:subprocess.check_output(['git','show',ref],cwd=ROOT))
    data=fetch(entry['commit']+':'+path.as_posix())
    if hashlib.sha256(data).hexdigest()!=entry['git_sha256']:raise ValueError('Git object checksum mismatch.')
    if entry['transform']=='crlf':data=data.replace(b'\n',b'\r\n')
    elif entry['transform']!='raw':raise ValueError('Unknown checkout representation.')
    if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Recovered file checksum mismatch.')
    return data


def restore(manifest, destination, prefix='', *, in_place=False, fetch=None):
    destination=Path(destination).resolve()
    if not destination.is_relative_to(ROOT):raise ValueError('Choose a destination inside the checkout.')
    if not in_place and destination.exists():raise FileExistsError('Choose a new destination.')
    obj=json.loads(Path(manifest).read_text(encoding='utf-8'))
    entries=[e for e in obj['files'] if not prefix or e['path'].startswith(prefix.rstrip('/')+'/') or e['path']==prefix]
    if not entries:raise ValueError('No archived paths matched the prefix.')
    ready=[];seen=set()
    for e in entries:
        relative=safe_path(e['path'])
        if relative in seen:raise ValueError('Duplicate archive target.')
        seen.add(relative);target=destination/relative
        if not target.resolve().is_relative_to(destination):raise ValueError('Target escapes the destination.')
        if target.exists() or target.is_symlink():raise FileExistsError('An archive target already exists; refusing overwrite.')
        for parent in target.parents:
            if parent==destination.parent:break
            if parent.is_symlink() or parent.is_junction():raise ValueError('Reparse-point target refused.')
        ready.append((target,materialize(e,fetch)))
    # All objects and paths pass preflight before creating the first file.
    for target,data in ready:
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as handle:handle.write(data)
    return len(ready)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',type=Path,default=DEFAULT)
    p.add_argument('--prefix',default='')
    location=p.add_mutually_exclusive_group(required=True)
    location.add_argument('--destination',type=Path)
    location.add_argument('--in-place',action='store_true')
    args=p.parse_args()
    count=restore(args.inventory,ROOT if args.in_place else args.destination,args.prefix,in_place=args.in_place)
    print(f'Restored {count} checksum-verified historical report files.')
