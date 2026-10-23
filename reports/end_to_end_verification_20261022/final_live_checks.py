"""Loopback GETs and saved-response arithmetic, with fresh create-only outputs."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE/'final_live_checks_20261023.json'
if OUT.exists():
    raise SystemExit('Refusing to replace evidence')

requests = []
for path in ['/', '/district/HR-Kurukshetra', '/alerts', '/simulate', '/src/api.js', '/india_districts.geojson']:
    try:
        try:
            response = urlopen('http://127.0.0.1:5183'+path, timeout=20)
        except HTTPError as e:
            response = e
        with response:
            raw = response.read()
            text = raw.decode('utf-8', errors='replace')
            item = {'path': path, 'status': response.status, 'bytes': len(raw),
                    'sha256': hashlib.sha256(raw).hexdigest()}
            if path == '/src/api.js':
                item['explicit_audit_api_url_present'] = 'http://127.0.0.1:5053' in text
            elif path == '/india_districts.geojson':
                obj = json.loads(text)
                item['geojson_type'] = obj.get('type')
                item['features'] = len(obj.get('features', []))
            else:
                item['spa_entry_present'] = '/src/main.jsx' in text and '<div id="root"></div>' in text
            requests.append(item)
    except Exception as e:
        requests.append({'path': path, 'error': type(e).__name__+': '+str(e)})

saved = json.loads((HERE/'api_source/live_http_20261023.json').read_text())
by_name = {r['name']: r for r in saved['requests']}
checks = []


def check(name, ok, detail=None):
    checks.append({'name': name, 'pass': bool(ok), 'detail': detail})


for item in requests:
    check('frontend_get_'+item['path'], item.get('status') == 200, item.get('error', item.get('status')))
check('frontend_module_uses_explicit_api_5053',
      next((r for r in requests if r['path'] == '/src/api.js'), {}).get('explicit_audit_api_url_present') is True)
html = [r for r in requests if r['path'] in ['/', '/district/HR-Kurukshetra', '/alerts', '/simulate']]
check('routes_serve_spa_shell_not_render_verification', len(html) == 4 and all(r.get('spa_entry_present') for r in html))
direct = by_name['direct_adilabad_2024-01']['body']
rows = list(csv.DictReader((ROOT/'reports/candidates/twelve_month_horizon_finalization_20261020/artifact/historical_checks.csv').open(newline='', encoding='utf-8')))
check('historical_saved_rows_count', len(rows) == 24)
# The archive has explicit case origins/targets; only read their declared columns.
matches = [r for r in rows if r['date'] == '2024-01-01' and r['target_date'] == '2025-01-01']
check('historical_row_unique', len(matches) == 1)
check('exact_historical_calendar', direct['origin_month'] == '2024-01' and direct['target_month'] == '2025-01')
if len(matches) == 1:
    row = matches[0]
    numeric = {k: float(row[k]) for k in ['fixed_xgb_2021','annual_baseline','target_value']}
    check('api_prediction_matches_saved_row', math.isclose(numeric['fixed_xgb_2021'],direct['ml_estimate_m'],abs_tol=1e-12), {'numeric_columns': numeric})
    check('api_baseline_matches_saved_row', math.isclose(numeric['annual_baseline'],direct['annual_baseline_m'],abs_tol=1e-12))
    check('api_target_matches_saved_row', math.isclose(numeric['target_value'],direct['observed_target_m'],abs_tol=1e-12))
check('historical_prediction_exact_reference', math.isclose(direct['ml_estimate_m'],7.57110071182251,abs_tol=1e-12))
check('historical_baseline_exact_reference', math.isclose(direct['annual_baseline_m'],6.836666666666668,abs_tol=1e-12))
check('historical_target_separate', math.isclose(direct['observed_target_m'],6.831333333333332,abs_tol=1e-12))
check('no_prospective_issuance_direct', direct.get('forecast_issued_at') is None)
for name in ['scenario_HR-Kaithal','scenario_HR-Kurukshetra','scenario_TS-Adilabad']:
    body=by_name[name]['body']
    forecast=body['forecast']
    check(name+'_finite_monthly_points', len(forecast)==12 and all(isinstance(r.get('projected_gwl'),(float,int)) and math.isfinite(r['projected_gwl']) and r['projected_gwl']>=0 for r in forecast))
    check(name+'_november_october', forecast[0]['month']=='2026-11' and forecast[-1]['month']=='2027-10')
scores=by_name['scores']['body']
check('score_tiers_sum_to_725', sum(scores['tier_counts'].values())==725 and scores['total']==725)
for name in ['history_kaithal','history_adilabad']:
    body=by_name[name]['body']
    history=body.get('history',body.get('data',[]))
    check(name+'_separate_flags', all(not (r.get('is_observed') and r.get('is_imputed')) for r in history))
    check(name+'_equal_aliases', body.get('history')==body.get('data'))
guard=by_name['old_guard_scores']
check('403_is_old_helper_guard', guard['status']==403 and guard['body'].get('error')=='Legacy routes are excluded from this read-only demonstration.')
check('same_api_scores_works', by_name['scores']['status']==200)
record={'at_utc':datetime.now(timezone.utc).isoformat(),'frontend_requests':requests,
        'source_http_receipt_sha256':hashlib.sha256((HERE/'api_source/live_http_20261023.json').read_bytes()).hexdigest(),
        'checks':checks,'passed':sum(c['pass'] for c in checks),'total':len(checks),
        'scope':'No browser automation. GETs only for frontend assets; other checks use saved API responses and archived CSV. No estimator fitting, pipelines or database connections in this helper.'}
with OUT.open('x',encoding='utf-8') as f:
    json.dump(record,f,indent=2,allow_nan=False)
print(json.dumps({'passed':record['passed'],'total':len(checks),'failed':[c for c in checks if not c['pass']]}))
raise SystemExit(0 if all(c['pass'] for c in checks) else 1)
