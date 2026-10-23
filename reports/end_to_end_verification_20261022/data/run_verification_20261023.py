"""Create-only execution receipt for the reviewed retained-data audit helper."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
command = [sys.executable, '-B', str(OUT / 'verify_data.py')]
receipt_path = OUT / 'verification_execution_20261023.json'
stdout_path = OUT / 'verification_stdout_20261023.log'
stderr_path = OUT / 'verification_stderr_20261023.log'
for path in (receipt_path, stdout_path, stderr_path):
    if path.exists():
        raise FileExistsError(path.name)
started = datetime.now(timezone.utc).isoformat()
result = subprocess.run(command, cwd=ROOT, capture_output=True)
with stdout_path.open('xb') as stream:
    stream.write(result.stdout)
with stderr_path.open('xb') as stream:
    stream.write(result.stderr)
receipt = {
    'started_utc': started,
    'completed_utc': datetime.now(timezone.utc).isoformat(),
    'cwd': str(ROOT),
    'command': command,
    'script_sha256': hashlib.sha256((OUT / 'verify_data.py').read_bytes()).hexdigest(),
    'exit_status': result.returncode,
    'stdout_file': stdout_path.name,
    'stderr_file': stderr_path.name,
    'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
    'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
}
with receipt_path.open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(receipt, indent=2))
if result.stdout:
    print(result.stdout.decode('utf-8', errors='replace'))
if result.stderr:
    print(result.stderr.decode('utf-8', errors='replace'), file=sys.stderr)
sys.exit(result.returncode)
