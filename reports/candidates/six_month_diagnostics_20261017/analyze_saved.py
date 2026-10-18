"""Read-only diagnostics of frozen predictions. No estimator is fitted.

python reports/candidates/six_month_diagnostics_20261017/analyze_saved.py
python reports/candidates/six_month_diagnostics_20261017/analyze_saved.py --verify-only
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT/'reports/candidates/six_month_selection_20261017'
EXP = OLD/'experiment_v2'
NAMES = ['persistence','seasonal_naive','ridge','random_forest','xgboost','hist_gradient_boosting']
ML = NAMES[2:]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def snapshot():
    files = [p for base in (OLD,ROOT/'data/processed',ROOT/'models/checkpoints')
             for p in base.rglob('*') if p.is_file()]
    files += [ROOT/'models/six_month_selection.py',ROOT/'models/xgboost_model.py',
              ROOT/'preprocessing/features.py',ROOT/'config.yaml',
              ROOT/'data/raw/updates/20261013/gwl_manual_quarterly_cgwb_gj_2021_2025.csv']
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(set(files))}


def metrics(actual,predicted):
    actual,predicted = np.asarray(actual,float),np.asarray(predicted,float)
    residual = predicted-actual
    sse = float(np.square(residual).sum())
    resolved = len(actual)>1 and np.ptp(actual)>8*np.finfo(float).eps*max(1.,float(np.abs(actual).max()))
    return {'n':len(actual),'mae_m':float(np.abs(residual).mean()),
            'rmse_m':float(np.sqrt(sse/len(actual))),
            'r2':float(1-sse/np.square(actual-actual.mean()).sum()) if resolved else None}


def check_group_csv(frames,filename,key,derive):
    stored = pd.read_csv(OLD/filename)
    expected = 0
    for cohort,data in frames.items():
        for group,part in data.groupby(derive(data),sort=True):
            for name in NAMES:
                found = stored.loc[(stored.cohort==cohort)&(stored[key].astype(str)==str(group))&(stored.model==name)]
                assert len(found)==1,(filename,cohort,group,name)
                row = found.iloc[0]
                for metric,value in metrics(part.actual,part[name]).items():
                    assert (value is None and pd.isna(row[metric])) or np.isclose(value,row[metric],rtol=1e-10,atol=1e-10),(filename,cohort,group,name,metric)
                expected+=1
    assert len(stored)==expected,(filename,len(stored),expected)
    return expected


def load_frames():
    lock = read(EXP/'selection_lock.json')
    validation = None
    for family,item in lock['selected_by_family'].items():
        path = EXP/'validation'/f'{item["candidate_id"]}.csv'
        cached = read(path.with_suffix('.json'))
        assert sha(path)==cached['case_csv_sha256']
        frame = pd.read_csv(path,parse_dates=['date','target_date'])
        if validation is None:
            validation = frame.drop(columns='prediction').copy()
        else:
            assert validation.case_id.tolist()==frame.case_id.tolist()
            np.testing.assert_array_equal(validation.actual,frame.actual)
        validation[family]=frame.prediction.to_numpy()
    result = {'validation':validation}
    result.update({key:pd.read_csv(EXP/f'{key}_predictions.csv',parse_dates=['date','target_date'])
                   for key in read(EXP/'test_results.json')['cohorts']})
    for data in result.values():
        assert data.case_id.is_unique
        assert np.isfinite(data[['actual',*NAMES]].to_numpy(float)).all()
        assert (data.target_date==data.date+pd.DateOffset(months=6)).all()
        assert (data.date.dt.day==1).all() and (data.target_date.dt.day==1).all()
    return result


def labels_and_features(frames):
    manifest = read(ROOT/'data/processed/feature_manifest.json')
    path = ROOT/'data/processed/features_matrix.csv'
    assert sha(path)==manifest['feature_csv_sha256']==read(EXP/'protocol.json')['feature_csv_sha256']
    active = pd.read_csv(path,parse_dates=['date'])
    external_path = OLD/'coverage/source_manual_optional_features.csv'
    assert sha(external_path)==read(EXP/'protocol.json')['external_source_sha256']
    external = pd.read_csv(external_path,parse_dates=['date'])
    checks = {}
    weather = ['rainfall_current','rainfall_3mo_avg','monsoon_deficit_pct','temperature','evapotranspiration','water_balance_proxy']
    for cohort,data in frames.items():
        source = external if cohort=='external_source_conditional' else active
        lookup = source.set_index(['district_id','date'])
        def at(dates):
            return lookup.reindex(pd.MultiIndex.from_arrays([data.district_id,dates])).reset_index(drop=True)
        origins,targets,seasonal = at(data.date),at(data.target_date),at(data.target_date-pd.DateOffset(months=12))
        for part,col in [(origins,'persistence'),(targets,'actual'),(seasonal,'seasonal_naive')]:
            np.testing.assert_allclose(part.gwl_current,data[col],rtol=0,atol=1e-10)
        assert targets.is_observed.eq(True).all() and seasonal.is_observed.eq(True).all()
        if cohort!='secondary_causal_origin':
            assert origins.is_observed.eq(True).all()
        checks[cohort]={'n':len(data),'observed_targets':int(targets.is_observed.sum()),
                       'observed_seasonal_references':int(seasonal.is_observed.sum()),
                       'observed_origins':int(origins.is_observed.sum()),
                       'origins_missing_any_weather_feature':int(origins[weather].isna().any(axis=1).sum()),
                       'origins_missing_any_gwl_lag':int(origins[['gwl_lag_3mo','gwl_lag_6mo']].isna().any(axis=1).sum()),
                       'actual_issue_timestamp_in_prediction_csv':'issued_at' in data,
                       'observation_date_resolution':'monthly bucket, not actual measurement timestamp'}
    return checks


def analyze(frames):
    weightings,months,districts,patterns,cases = [],[],[],[],[]
    summary = {}
    for cohort,data in frames.items():
        data = data.copy()
        data['month']=data.target_date.dt.month
        exact_p = np.isclose(data.actual,data.persistence,atol=1e-9,rtol=0)
        exact_s = np.isclose(data.actual,data.seasonal_naive,atol=1e-9,rtol=0)
        data['pattern']=np.select([exact_p&exact_s,exact_s,exact_p],
                                 ['both_exact','seasonal_only_exact','persistence_only_exact'],default='neither_exact')
        parts = {'district_macro':list(data.groupby('district_id')),
                 'calendar_macro':list(data.groupby('month'))}
        for name in NAMES:
            pooled = metrics(data.actual,data[name])
            weightings.append({'cohort':cohort,'model':name,'weighting':'pooled',**pooled})
            for weighting,groups in parts.items():
                grouped = [metrics(part.actual,part[name]) for _,part in groups]
                weightings.append({'cohort':cohort,'model':name,'weighting':weighting,'n':len(data),
                                   'groups':len(groups),'mae_m':float(np.mean([x['mae_m'] for x in grouped])),
                                   'rmse_m':float(np.mean([x['rmse_m'] for x in grouped])), 'r2':None})
        for dimension,out in [('month',months),('district_id',districts),('pattern',patterns)]:
            for value,part in data.groupby(dimension,sort=True):
                base = metrics(part.actual,part.seasonal_naive)
                for name in ML:
                    measured = metrics(part.actual,part[name])
                    out.append({'cohort':cohort,dimension:value,'model':name,'n':len(part),
                                'districts':int(part.district_id.nunique()),
                                'seasonal_mae_m':base['mae_m'],'seasonal_rmse_m':base['rmse_m'],
                                'ml_mae_m':measured['mae_m'],'ml_rmse_m':measured['rmse_m'],
                                'ml_minus_seasonal_sae_m':float(((part[name]-part.actual).abs()-(part.seasonal_naive-part.actual).abs()).sum()),
                                'ml_minus_seasonal_sse_m2':float((((part[name]-part.actual)**2)-((part.seasonal_naive-part.actual)**2)).sum()),
                                'seasonal_lower_absolute_error_cases':int(((part.seasonal_naive-part.actual).abs()<(part[name]-part.actual).abs()-1e-9).sum())})
        for name in ML:
            copied = data[['case_id','district_id','date','target_date','pattern','actual','persistence','seasonal_naive',name]].copy()
            copied = copied.rename(columns={name:'ml_prediction'})
            copied['cohort'],copied['model']=cohort,name
            copied['ml_minus_seasonal_ae_m']=(data[name]-data.actual).abs()-(data.seasonal_naive-data.actual).abs()
            copied['ml_minus_seasonal_se_m2']=(data[name]-data.actual)**2-(data.seasonal_naive-data.actual)**2
            cases.append(copied)
        summary[cohort]={'n':len(data),'districts':int(data.district_id.nunique()),
                         'calendar_counts':{str(k):int(v) for k,v in data.month.value_counts().sort_index().items()},
                         'pattern_counts':{str(k):int(v) for k,v in data.pattern.value_counts().items()},
                         'both_exact_by_year':{str(year):int((part.pattern=='both_exact').sum()) for year,part in data.groupby(data.target_date.dt.year)},
                         'seasonal_better_cases':{name:int(((data.seasonal_naive-data.actual).abs()<(data[name]-data.actual).abs()-1e-9).sum()) for name in ML},
                         'constant_source_target_pairs_are_not_proof_of_same_wells':True}
    return summary,{'weighting_metrics':pd.DataFrame(weightings),'calendar_comparisons':pd.DataFrame(months),
                    'district_contributions':pd.DataFrame(districts),'measurement_pattern_metrics':pd.DataFrame(patterns),
                    'case_diagnostics':pd.concat(cases,ignore_index=True)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    before=snapshot()
    frames=load_frames()
    reconciled={filename:check_group_csv(frames,filename,key,derive) for filename,key,derive in
                [('calendar_metrics.csv','target_calendar_month',lambda x:x.target_date.dt.month),
                 ('district_metrics.csv','district_id',lambda x:x.district_id),
                 ('period_metrics.csv','target_year',lambda x:x.target_date.dt.year)]}
    provenance=labels_and_features(frames)
    summary,tables=analyze(frames)
    result={'mode':'saved predictions only; no fitting, tuning or reselection',
            'reconciled_metric_rows':reconciled,'provenance_checks':provenance,'cohorts':summary,
            'macro_definition':'Unweighted arithmetic mean of group MAEs and group RMSEs; not sqrt(mean(group MSE)); no average group R2.',
            'calendar_evaluation':'Target calendar month; paired six-calendar-month predictions. Calendar macro equally weights present months; absent months never filled.',
            'exact_equality_tolerance_m':1e-9,'descriptive_only':True}
    assert snapshot()==before,'Protected input or completed result changed'
    if args.verify_only:
        assert read(HERE/'preserved_inputs.json')==before
        assert read(HERE/'diagnostics.json')==result
        print(json.dumps({'preserved_files':len(before),'reconciled_metric_rows':reconciled,'verified':True},indent=2))
        return
    for name,value in [('preserved_inputs',before),('diagnostics',result)]:
        with (HERE/f'{name}.json').open('x',encoding='utf-8') as handle:
            json.dump(value,handle,indent=2,allow_nan=False)
    for name,value in tables.items():
        with (HERE/f'{name}.csv').open('x',encoding='utf-8',newline='') as handle:
            value.to_csv(handle,index=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
