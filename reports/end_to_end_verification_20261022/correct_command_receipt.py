"""Correct two transcription fields without replacing earlier audit evidence."""
import json
from pathlib import Path

p=Path(__file__).resolve().parent
d=json.loads((p/'commands_20261023.json').read_text())
d['correction']='Supersedes two manually transcribed fields; original retained. Parent did not retain the live-helper process exit. Its source has no failed-check exit. Vite argument spacing is corrected below.'
for item in d['commands']:
    if 'api_source/live_http_20261023.py' in item['command']:
        item['exit_code']=None
        item['exit_status_note']='Not retained by parent. Helper does not signal failed checks through exit status; inspect individual results.'
    if 'From dashboard:' in item['command']:
        item['command']="From dashboard: $env:VITE_API_URL='http://127.0.0.1:5053'\n& 'C:\\Program Files\\nodejs\\node.exe' '.\\node_modules\\vite\\bin\\vite.js' --host 127.0.0.1 --port 5183 --strictPort"
with (p/'commands_verified_20261023.json').open('x',encoding='utf-8') as f:
    json.dump(d,f,indent=2)
    f.write('\n')
print('Created corrected receipt; original unchanged.')
