"""Read-only release verification of the isolated published generation and APIs.

Normal API reads are exercised for every district/state with inference forbidden.
Reconcile the registry to source database metadata without modifying source data.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
from unittest.mock import patch
from db.connection import get_connection
from models.district_registry import get_registry
from models.state_mapping import resolve_state_id
from models import forecast_storage as storage, climate_forecast_12m as climate
from api.app import create_app


def run(schema, output, as_of='2026-10-25'):
    os.environ['AQUAIQ_FORECAST_SCHEMA']=schema
    identity=storage.compute_input_identity(as_of)
    active=storage.get_active_generation(as_of)
    if not active or active['generation_id']!=identity['generation_id']:
        raise ValueError('Published generation does not match the final verified implementation.')
    validation=storage.validate_stored_generation(identity)
    registry=get_registry();registered={r['district_id']:r for r in registry}
    conn=get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT district_id,district_name,state FROM districts')
            source=cur.fetchall()
            if set(r[0] for r in source)!=set(registered):raise ValueError('Source DB registry IDs differ from canonical crosswalk.')
            for did,name,state in source:
                if name.strip().casefold()!=registered[did]['district_name'].casefold() or resolve_state_id(state)!=registered[did]['state_id']:
                    raise ValueError('Registry name or state mismatch.')
            cur.execute("SELECT COUNT(*),COUNT(*) FILTER (WHERE status='published') FROM forecast_generations")
            public_generations=cur.fetchone()
    finally:conn.close()
    app=create_app({'TESTING':True});client=app.test_client()
    def forbidden(*a,**kw):raise AssertionError('Normal API read attempted model inference')
    count=0
    with patch.object(climate,'forecast_from_evidence',forbidden):
        state_registry=client.get('/api/states?as_of='+as_of)
        assert state_registry.status_code==200
        state_registry=state_registry.get_json()
        summary=client.get('/api/states/summary?as_of='+as_of).get_json()
        assert summary['generation_id']==identity['generation_id']
        for r in registry:
            res=client.get('/api/predict/climate-12m/'+r['district_id']+'?as_of='+as_of)
            assert res.status_code==200,(r['district_id'],res.status_code)
            payload=res.get_json()
            assert payload['generation_id']==identity['generation_id'] and len(payload['forecast'])==12
            count+=1
        for state in state_registry['states']:
            res=client.get('/api/predict/state/'+state['state_id']+'?as_of='+as_of)
            assert res.status_code==200
            payload=res.get_json()
            assert payload['generation_id']==identity['generation_id'] and len(payload['forecast'])==12
            count+=1
        # Default requests pin the same published vintage without live assets.
        with patch.object(storage,'compute_input_identity',side_effect=FileNotFoundError('test missing live artifact')):
            payload=client.get('/api/predict/climate-12m/AN-Nicobars').get_json()
            assert payload['generation_id']==identity['generation_id']
        for path in ['/api/predict/HR-Kaithal?months=6&as_of='+as_of,
                     '/api/predict/HR-Kaithal?window=next_six_months&months=6&as_of='+as_of]:
            res=client.get(path);assert res.status_code==200,path
    res=client.get('/api/predict/climate-12m/not-registered?as_of='+as_of);assert res.status_code==404
    res=client.get('/api/predict/state/HR?horizon=6');assert res.status_code==400
    res=client.get('/api/predict/climate-12m/HR-Kaithal?as_of=2026-10-24')
    assert res.status_code==503 and res.get_json()['forecast']==[]
    report={'generation_id':identity['generation_id'],'schema':schema,'as_of':as_of,
        'validation':validation,'registry_database_reconciled':len(source),
        'district_and_state_api_reads':count,'inference_calls_during_forecast_reads':0,
        'six_month_endpoints':'passed','default_vintage_and_missing_assets':'passed',
        'missing_generation_and_invalid_requests':'passed',
        'public_forecast_generations_observed':{'total':public_generations[0],'published':public_generations[1]}}
    Path(output).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schema',required=True);p.add_argument('--output',default='reports/nationwide_20261025/release_verification.json')
    p.add_argument('--as-of',default='2026-10-25');a=p.parse_args();run(a.schema,a.output,a.as_of)
