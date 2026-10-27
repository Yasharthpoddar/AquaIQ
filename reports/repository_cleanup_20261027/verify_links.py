"""Validate retained reports, reproduction entrypoints and source syntax."""
import ast
import gzip
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
protected=json.loads((HERE/'preservation/protected_hashes.json').read_text(encoding='utf-8'))
documents=[ROOT/'README.md',ROOT/'docs/ACCURACY_EXPERIMENTS.md',
           ROOT/'docs/ENRICHED_XGBOOST_RETRAINING.md',ROOT/'docs/FINAL_RELEASE_REPRODUCTION.md']
for folder in ['final_release_20261026','retraining_20261027']:
    documents.extend(sorted((ROOT/'reports'/folder).glob('*.md')))
documents.append(ROOT/'reports/accuracy_experiments_20261027/REPORT.md')
links=[];modules=set();missing=[];newly_broken=[]
for source in documents:
    text=source.read_text(encoding='utf-8')
    modules.update(re.findall(r'python(?:\.exe)?\s+(?:-[Bu]\s+)*-m\s+([a-zA-Z_][\w.]*)',text))
    for value in re.findall(r'\]\(([^)]+)\)',text):
        value=unquote(value.strip('<>')).split('#',1)[0]
        if not value or value.startswith(('http:','https:','mailto:','codex:')):continue
        path=(source.parent/value).resolve()
        if not path.is_relative_to(ROOT):continue
        relative=path.relative_to(ROOT).as_posix()
        result={'source':source.relative_to(ROOT).as_posix(),'target':relative,'exists':path.exists()}
        links.append(result)
        if not path.exists():
            missing.append(result)
            if relative in protected or any(k.startswith(relative+'/') for k in protected):newly_broken.append(result)
entrypoints={}
for module in sorted(modules):
    path=ROOT/Path(*module.split('.'))
    present=path.with_suffix('.py').is_file() or (path/'__main__.py').is_file()
    # pytest/pip are installed external tools, never source/data cleanup targets.
    if module in {'pytest','pip'}:present=True
    entrypoints[module]=present
syntax=[]
for folder in ['api','db','data_ingestion','models','preprocessing','scripts','tests']:
    for path in sorted((ROOT/folder).rglob('*.py')):
        if '__pycache__' in path.parts:continue
        ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
        syntax.append(path.relative_to(ROOT).as_posix())
for path in HERE.glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'),filename=str(path));syntax.append(path.relative_to(ROOT).as_posix())
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
large=[{'path':name,'bytes':(ROOT/name).stat().st_size} for name in tracked if name and (ROOT/name).is_file() and (ROOT/name).stat().st_size>5_000_000]
report={'documents_checked':[p.relative_to(ROOT).as_posix() for p in documents],
        'local_links_checked':len(links),'missing_links':missing,'newly_broken_links':newly_broken,
        'entrypoints':entrypoints,'python_sources_parsed':len(syntax),
        'preexisting_large_tracked_files':large,
        'large_file_policy':'Retained historical observation/panel evidence. No source data deleted, no Git history rewrite, no new large file staged.',
        'private_configuration_tracked':'.env' in tracked,
        'passed':not newly_broken and all(entrypoints.values()) and '.env' not in tracked}
(HERE/'links_syntax_large_files.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
if not report['passed']:raise SystemExit(1)
