"""Audit all own-district scenarios; writes new candidate evidence only.

This is a functional scenario check, not accuracy evaluation, model training,
production batch scoring or prospective issuance. Requires a new output path.
"""
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from models import experimental_scenario as service


def main():
    output = Path(sys.argv[1]).resolve()
    if not output.is_relative_to((ROOT/'reports/candidates').resolve()):
        raise SystemExit('Output must be a new candidate directory')
    output.mkdir(exist_ok=False)
    now = datetime.now(timezone.utc)
    as_of = service.parse_as_of(now=now)
    months = [(pd.Period(as_of,freq='M')+n).strftime('%Y-%m') for n in range(1,13)]
    registry = pd.read_csv(ROOT/'data_ingestion/district_crosswalk.csv',dtype=str)
    districts = sorted(registry.canonical_district_id.unique())
    def forbidden(*args,**kwargs):
        raise RuntimeError('Scope verification forbids DB and active estimator fitting/loading')
    rows=[]; examples={}
    with ExitStack() as guards:
        guards.enter_context(patch('psycopg2.connect',forbidden))
        for target in ('xgboost.XGBRegressor.fit','xgboost.XGBRegressor.load_model',
                       'sklearn.ensemble.HistGradientBoostingRegressor.fit','sklearn.ensemble.RandomForestRegressor.fit',
                       'sklearn.linear_model.LinearRegression.fit','sklearn.linear_model.Ridge.fit'):
            guards.enter_context(patch(target,forbidden))
        for index,district in enumerate(districts,1):
            value=service.scenario(district,now=now)
            assert value['district_id']==district and value['horizon_months']==12
            assert value['forecast_issued_at'] is None and value['source']['availability_verified'] is False
            assert value['source']['scope']=='district_own_observed_history'
            points=value['forecast']
            if value['status']=='scenario':
                assert [r['month'] for r in points]==months
                assert [r['horizon_months'] for r in points]==list(range(1,13))
                assert all(np.isfinite(r['projected_gwl']) and r['projected_gwl']>=0 for r in points)
                assert value['source']['last_observed_month']<as_of.strftime('%Y-%m')
            else:
                assert value['status']=='unavailable' and points==[] and value['estimated_current_gwl'] is None
            rows.append({'district_id':district,'status':value['status'],'source_kind':value['source'].get('source_kind'),
                         'latest_observed_month':value['source'].get('last_observed_month'),
                         'age_months':value['source'].get('data_age_months'),
                         'observed_months_available':value['source'].get('observed_months_available'),
                         'used_observations':value['method'].get('observed_month_count'),
                         'fit_start':value['method'].get('history_start'),'fit_end':value['method'].get('history_end'),
                         'phase_count':len(value['method'].get('observed_calendar_months',[])),
                         'point_count':len(points),'first_month':months[0] if points else None,'last_month':months[-1] if points else None,
                         'unavailable_reason':' '.join(value['unavailable_reasons'])})
            if district in {'HR-Kaithal','GJ-Gandhinagar','AN-Nicobars','TS-Adilabad','AR-Lohit'}:
                examples[district]=value
            if index%100==0 or index==len(districts):
                print(json.dumps({'checked':index,'of':len(districts),'statuses':dict(Counter(r['status'] for r in rows))}),flush=True)
    with (output/'district_coverage.csv').open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'scenario_as_of':as_of.isoformat(),
             'first_month':months[0],'last_month':months[-1],'districts':len(rows),'statuses':dict(Counter(r['status'] for r in rows)),
             'available_latest_month_counts':dict(Counter(r['latest_observed_month'] for r in rows if r['status']=='scenario')),
             'available_phase_counts':dict(Counter(r['phase_count'] for r in rows if r['status']=='scenario')),
             'no_observed_history':sum(r['status']=='unavailable' and r['observed_months_available']==0 for r in rows),
             'insufficient_observed_history':sum(r['status']=='unavailable' and r['observed_months_available']>0 for r in rows),
             'accuracy_evaluated':False,'active_ml_fitted_or_loaded':False,'database_accessed':False,
             'prospective_records_created':False,'output_kind':'experimental_scenario_functional_verification_only'}
    with (output/'summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2);f.write('\n')
    for district,value in examples.items():
        with (output/(district+'_scenario_example.json')).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
