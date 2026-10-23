"""Create-only subprocess receipt for supplementary read-only data audit."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
helper = OUT / 'supplemental_data_20261023.py'
command = [sys.executable, '-B', str(helper)]
names = ['supplement_execution_20261023.json', 'supplement_stdout_20261023.log', 'supplement_stderr_20261023.log']
for name in names:
    if (OUT / name).exists():
        raise FileExistsError(name)
started = datetime.now(timezone.utc).isoformat()
result = subprocess.run(command, cwd=ROOT, capture_output=True)
for name, content in zip(names[1:], (result.stdout, result.stderr)):
    with (OUT / name).open('xb') as stream:
        stream.write(content)
receipt = {'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
           'cwd': str(ROOT), 'command': command, 'script_sha256': hashlib.sha256(helper.read_bytes()).hexdigest(),
           'exit_status': result.returncode, 'stdout_file': names[1], 'stderr_file': names[2],
           'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(result.stderr).hexdigest()}
with (OUT / names[0]).open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(receipt, indent=2))
print(result.stdout.decode('utf-8', errors='replace'))
if result.stderr:
    print(result.stderr.decode('utf-8', errors='replace'), file=sys.stderr)
sys.exit(result.returncode)
