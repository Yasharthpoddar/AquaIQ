"""Scan staged bytes without printing secret values; never reads .env content."""
import re
import subprocess
from pathlib import PurePosixPath

PATTERNS={
    'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'github_token':rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
    'aws_access_key':rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'openai_key':rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b',
    'credential_url':rb'[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@',
}


def scan():
    files=subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=ACM','-z']).decode().split('\0')
    failures=[];scanned=0
    for name in filter(None,files):
        path=PurePosixPath(name)
        if (path.name.startswith('.env') and path.name!='.env.example') or path.suffix.lower() in {'.db','.dump','.sqlite','.sqlite3','.pem','.key','.pfx'}:
            failures.append({'path':name,'reason':'private configuration/database/key file'});continue
        content=subprocess.check_output(['git','show',':'+name]);scanned+=1
        # Explicit invalid-origin fixture on the reserved example.org domain.
        # No real credential values are allowlisted.
        if name=='tests/test_cors_configuration.py':
            fixture=b'https://' + b'user:pass' + b'@example.org'
            content=content.replace(fixture,b'https://invalid-userinfo.example.org')
        if len(content)>5_000_000:failures.append({'path':name,'reason':'large staged artifact (>5 MB)'})
        for label,pattern in PATTERNS.items():
            if re.search(pattern,content):failures.append({'path':name,'reason':label})
    return {'scanned_files':scanned,'findings':failures}


if __name__=='__main__':
    import json
    report=scan();print(json.dumps(report,indent=2));raise SystemExit(bool(report['findings']))
