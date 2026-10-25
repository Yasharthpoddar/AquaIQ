"""Rolling-origin, paired serving-path and pseudo-cold-start validation.

Fallback calibration: 2017/18-01/07. Fallback evaluation starts 2019-07,
then 2020/21/22/23-01/07 and 2025-01. A calibration: 2021-01/07 (after the
frozen artifact's twelve-month embargo); A evaluation starts 2022-07,
then 2023 and 2025-01. Origins before all calibration targets are purged.
No tuning uses evaluation labels. Cold starts exclude ALL target district rows
from the donor fit. Sparse experiments expose only the last 1/3/9/23 genuine
observations and never use the frozen XGBoost artifact (which saw those districts
historically). All labels are genuine district-month measurements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from db.connection import finite_json
from models import climate_forecast_12m as climate
from models.state_forecast import get_feature_matrix
from models.tiered_forecast import RegionalReference, observations, forecast_district, VERSION, CALIBRATION_PATH
from models.monthly_projection import fit_projection
from models.district_registry import get_registry


def metrics(actual, predicted):
    err=np.asarray(actual,float)-np.asarray(predicted,float)
    return {'n':len(err),'mae_m':float(np.abs(err).mean()),'rmse_m':float(np.sqrt(np.mean(err**2)))}


def write_validation_report(path, report):
    """Keep per-district aggregates on single lines for a manageable Git diff."""
    report=finite_json(report)
    districts=report.pop('by_district')
    prefix=json.dumps(report,indent=2,allow_nan=False).rstrip()[:-1].rstrip()
    rows=',\n'.join('    '+json.dumps(did)+': '+json.dumps(value,separators=(',',':'),allow_nan=False)
        for did,value in districts.items())
    Path(path).write_text(prefix+',\n  "by_district": {\n'+rows+'\n  }\n}\n',encoding='utf-8')


def summarize(part):
    result={'n':len(part),'districts':part.district_id.nunique(),
        'method':metrics(part.actual,part.predicted), 'regional_transfer_candidate':metrics(part.actual,part.transfer),
        'global_reference':metrics(part.actual,part.global_reference)}
    if 'state_blocked_reference' in part:
        result['state_blocked_reference']=metrics(part.actual,part.state_blocked_reference)
    paired=part[part.persistence.notna()]
    if len(paired):
        result['persistence_paired']={'method':metrics(paired.actual,paired.predicted), 'baseline':metrics(paired.actual,paired.persistence)}
    paired=part[part.seasonal.notna()]
    if len(paired):
        result['seasonal_paired']={'method':metrics(paired.actual,paired.predicted), 'baseline':metrics(paired.actual,paired.seasonal)}
    if 'covered' in part:
        tested=part[part.covered.notna()]
        if len(tested): result['interval_coverage']={'n':len(tested),'fraction':float(tested.covered.mean()),'mean_width_m':float(tested.interval_width.mean())}
    return finite_json(result)


def run(output, origins=None, write_calibration=False, cases_path=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    frame=get_feature_matrix();bundle=climate.load_bundle(expected_generation=frame.attrs['feature_generation_id'])
    registry=get_registry();ids=[r['district_id'] for r in registry]
    origins=origins or [f'{year}-{month}-31' for year in range(2017,2024) for month in ['01','07']]+['2025-01-31']
    records=pd.read_csv(cases_path).to_dict('records') if cases_path else [];errors=[]
    for cutoff in ([] if cases_path else origins):
        cutoff=pd.Timestamp(cutoff);origin=cutoff.replace(day=1)
        ref=RegionalReference(frame,cutoff)
        groups={d:g for d,g in frame.groupby('district_id')}
        future_months=pd.date_range(origin+pd.offsets.MonthBegin(1),periods=12,freq='MS')
        for idx,did in enumerate(ids):
            district=groups.get(did,frame.iloc[:0])
            local=observations(district,cutoff)
            target=observations(district,origin+pd.DateOffset(months=13)).set_index('date').gwl_current
            labels={h:float(target.loc[month]) for h,month in enumerate(future_months,1) if month in target.index}
            if not labels: continue
            # Dropping target rows, not just setting their values to NaN, gives
            # a donor model invariant to any hidden target history.
            full,donors=ref.predict(did,future_months,local.iloc[:0])
            global_pred=[float(np.median(ref.distribution(did,m.month,global_only=True)[0])) for m in future_months]
            # Sparse cap is deterministic and fixed before inspecting labels.
            cap=[1,3,9,23][int(hashlib.sha256(did.encode()).hexdigest()[:8],16)%4]
            sparse=local.tail(cap)
            experiments=[('C','pseudo_cold',local.iloc[:0],full,full)]
            if len(sparse):
                transfer,_=ref.predict(did,future_months,sparse)
                experiments.append(('B','pseudo_sparse',sparse,np.repeat(sparse.iloc[-1].gwl_current,12),transfer))
            if fit_projection(local, cutoff) is not None:
                experiments.append(('D','masked_environment',local,np.repeat(local.iloc[-1].gwl_current,12),ref.predict(did,future_months,local)[0]))
            try:
                result=(forecast_district(did,district,cutoff,frame.attrs['feature_generation_id'],bundle,ref)
                        if cutoff.year>=2021 else None)
                if result and result['evidence_tier']=='A':
                    prediction=np.array([r['predicted_gwl'] for r in result['forecast']])
                    experiments.append(('A','natural_supported',local,prediction,prediction))
                elif result and result['evidence_tier']=='B':
                    prediction=np.array([r['predicted_gwl'] for r in result['forecast']])
                    experiments.append(('B','natural_sparse',local,prediction,ref.predict(did,future_months,local)[0]))
            except Exception as exc:
                errors.append({'district_id':did,'origin':cutoff.date().isoformat(),'error':type(exc).__name__})
                raise
            for tier,experiment,history,prediction,transfer in experiments:
                pers=float(history.iloc[-1].gwl_current) if len(history) else None
                for h,actual in labels.items():
                    seasonal=history.loc[history.date.dt.month==future_months[h-1].month]
                    seasonal=float(seasonal.iloc[-1].gwl_current) if len(seasonal) else None
                    records.append(dict(district_id=did,origin=cutoff.date().isoformat(),target_date=future_months[h-1].date().isoformat(),
                        horizon=h,tier=tier,experiment=experiment,actual=actual,predicted=float(prediction[h-1]),
                        transfer=float(transfer[h-1]),global_reference=global_pred[h-1],persistence=pers,seasonal=seasonal,
                        local_observations=len(history),donor_scope=donors[h-1]['scope'],
                        split=('calibration' if cutoff.year==2021 else 'evaluation') if tier=='A' else ('calibration' if cutoff.year<=2018 else 'evaluation')))
        print(f'Validated origin {cutoff.date()}: cumulative {len(records)} paired cases',flush=True)
    table=pd.DataFrame(records)
    # Geographic sensitivity: exclude every district in the target state from
    # the global reference. This withholds neighboring in-state histories as
    # well as the target. It evaluates reference transfer, not XGBoost skill.
    blocked={}
    for origin,part in table.groupby('origin'):
        reference=RegionalReference(frame,pd.Timestamp(origin))
        for state in part.district_id.str[:2].unique():
            ids=reference.annual.index[~reference.annual.index.str.startswith(state+'-')]
            for month in range(1,13):
                values=reference.monthly.reindex(ids).get(month,pd.Series(np.nan,index=ids)).fillna(reference.annual.reindex(ids))
                if values.empty:raise ValueError('No out-of-state donors for geographic sensitivity.')
                blocked[(origin,state,month)]=float(values.median())
    table['state_blocked_reference']=[blocked[(r.origin,r.district_id[:2],pd.Timestamp(r.target_date).month)] for r in table.itertuples()]
    # A full twelve-month calibration path can end after an origin in the
    # following year. Purge those early evaluation origins before reporting
    # either point metrics or interval coverage. No evaluated target constructs
    # predictors or determines a calibration radius available at its origin.
    a=table.tier.eq('A')
    years=table.origin.str[:4].astype(int)
    table['split']=np.select([a & years.eq(2021),~a & years.le(2018),
        (a & table.origin.eq('2022-01-31')) | (~a & table.origin.eq('2019-01-31'))],
        ['calibration','calibration','purged'],default='evaluation')
    for tier,part in table.groupby('tier'):
        cal_part=part[part.split=='calibration'];eval_part=part[part.split=='evaluation']
        if len(cal_part) and len(eval_part) and cal_part.target_date.max()>eval_part.origin.min():
            raise ValueError('Calibration target occurs after an evaluation origin.')
    table.to_csv(output/'cases.csv',index=False)
    cal=table[table.split=='calibration']
    # Calibration restricted to origins separated from XGBoost training by 12 months.
    radii={tier:{str(int(h)):float(np.quantile(np.abs(g.actual-g.predicted),.9,method='higher'))
            for h,g in part.groupby('horizon')} for tier,part in cal.groupby('tier')}
    counts={tier:{str(int(h)):{'n':len(g),'districts':g.district_id.nunique()}
            for h,g in part.groupby('horizon')} for tier,part in cal.groupby('tier')}
    calibration={'pipeline_version':VERSION,'calibration_id':hashlib.sha256(cal[['district_id','origin','horizon','tier','experiment','actual','predicted']].to_csv(index=False).encode()).hexdigest(),
        'max_calibration_target':cal.target_date.max(),'nominal_coverage':.9,'radii_m':radii,'sample_counts':counts,
        'feature_generation_id':frame.attrs['feature_generation_id'],'feature_data_sha256':frame.attrs['feature_manifest']['feature_csv_sha256'],
        'xgboost_sha256':bundle[1]['model_sha256'],
        'policy':'90th percentile absolute residual, higher quantile, by tier and horizon. No evaluation labels used.'}
    evaluation=table[table.split=='evaluation'].copy()
    evaluation['radius']=evaluation.apply(lambda r:radii.get(r.tier,{}).get(str(r.horizon),np.nan),axis=1)
    evaluation['covered']=np.abs(evaluation.actual-evaluation.predicted)<=evaluation.radius
    evaluation['interval_width']=evaluation.predicted+evaluation.radius-np.maximum(0,evaluation.predicted-evaluation.radius)
    report={'pipeline_version':VERSION,'protocol':__doc__,'model_sha256':bundle[1]['model_sha256'],
        'feature_generation':frame.attrs['feature_generation_id'],'origins':origins,'calibration_cases':len(cal),'evaluation_cases':len(evaluation),
        'calibration':calibration,'errors':errors,
        'by_tier':{tier:summarize(part) for tier,part in evaluation.groupby('tier')},
        'by_experiment':{exp:summarize(part) for exp,part in evaluation.groupby('experiment')},
        'by_observation_count':{str(int(count)):summarize(part) for count,part in evaluation[evaluation.tier=='B'].groupby('local_observations')},
        'by_origin':{origin:{tier:summarize(g) for tier,g in part.groupby('tier')} for origin,part in evaluation.groupby('origin')},
        'purged_cases':int(table.split.eq('purged').sum()),
        'cases_sha256':hashlib.sha256((output/'cases.csv').read_bytes()).hexdigest(),
        'by_horizon':{tier:{str(h):summarize(g) for h,g in part.groupby('horizon')} for tier,part in evaluation.groupby('tier')},
        'by_district':{did:{tier:summarize(g) for tier,g in part.groupby('tier')} for did,part in evaluation.groupby('district_id')},
        'limitations':[
            'Conditional on observation month; provider publication times and well-panel stability are unknown.',
            'Pseudo-cold starts leave out all target history from reference fitting, including past years. No XGBoost model is used for cold/sparse transfer.',
            'Nearby donor districts may share aquifers/errors; leave-one-district-out is not a spatial-block holdout.',
            'The state-blocked reference sensitivity excludes all target-state groundwater histories; this does not turn within-state reference metrics or XGBoost evaluation into geographically independent validation.',
            'State membership lacks hydrogeological similarity guarantees; global references cover states without two other observed donors.',
            'No observations exist to validate genuinely unmonitored districts; pseudo-cold results may not transport to them.',
            'Most labels sample seasonal monitoring phases, not every calendar month or horizon equally.',
            'The model and historical holdouts were previously inspected; no blind or prospective accuracy claim.',
            'A uses the actual serving anchor across historical gaps. B/D persistence intentionally sacrifices monthly shape; transfer is a comparison candidate only.',
            'Interval calibration is marginal and dependent; nominal coverage is not a district-level guarantee.']}
    write_validation_report(output/'validation.json',report)
    if write_calibration:
        CALIBRATION_PATH.write_text(json.dumps(finite_json(calibration),indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['calibration_cases','evaluation_cases','by_tier']},indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path('reports/nationwide_20261025'))
    parser.add_argument('--write-calibration',action='store_true')
    parser.add_argument('--summarize-existing',type=Path,help='Recompute metrics from saved local prediction cases without refitting/inference')
    args=parser.parse_args();run(args.output_dir,write_calibration=args.write_calibration,cases_path=args.summarize_existing)
