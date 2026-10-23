"""Read-only localhost provisioning probe; does not substitute for visual evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
OUT=HERE/'local_http_provisioning.json'
if OUT.exists():
    raise SystemExit('Refusing to replace evidence')
results=[]
cases=[('frontend_home',5183,'/'),('frontend_district_shell',5183,'/district/HR-Kurukshetra'),
       ('frontend_client',5183,'/src/api.js'),('normal_config',5053,'/api/config'),
       ('normal_health',5053,'/api/health'),('normal_scores',5053,'/api/scores')]
for name,port,path in cases:
    item={'name':name,'url':f'http://127.0.0.1:{port}{path}'}
    try:
        request=Request(item['url'],headers={'Origin':'http://127.0.0.1:5183'})
        try:
            reply=urlopen(request,timeout=30)
        except HTTPError as e:
            reply=e
        with reply:
            raw=reply.read()
            item.update(status=reply.status,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                        content_type=reply.headers.get('Content-Type'),
                        access_control_allow_origin=reply.headers.get('Access-Control-Allow-Origin'))
            text=raw.decode('utf-8',errors='replace')
            if name=='frontend_client':
                item['client_explicit_api_5053']='http://127.0.0.1:5053' in text
            elif port==5183:
                item['spa_shell_present']='/src/main.jsx' in text and '<div id="root"></div>' in text
            else:
                body=json.loads(text)
                # Only public-safe diagnostic fields, never full source/credentials/logs.
                item['public_fields']={k:body[k] for k in ['status','total','tier_counts','estimate_counts','primary_forecast'] if k in body}
    except Exception as e:
        item['error']=type(e).__name__+': '+str(e)
    results.append(item)
record={'at_utc':datetime.now(timezone.utc).isoformat(),'requests':results,
        'visual_evidence':False,'writes_to_application_or_database':False,
        'scope':'GET public-safe health/config/published score metadata and frontend assets only. No scenarios, model training, scoring publication, downloads, builds, database mutation or browser automation.'}
with OUT.open('x',encoding='utf-8') as f:
    json.dump(record,f,indent=2,allow_nan=False)
    f.write('\n')
print(json.dumps({'requests':len(results),'http_200':sum(r.get('status')==200 for r in results),'failures':[r for r in results if r.get('status')!=200]}))
raise SystemExit(0 if all(r.get('status')==200 for r in results) else 1)
