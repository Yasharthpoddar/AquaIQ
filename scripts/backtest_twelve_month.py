"""Create-only, offline twelve-month historical research; never production serving.

Prepare cohorts before inspecting errors, then fit the protocol's fixed models.
All inputs are retained local files; no download or database path is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from threadpoolctl import threadpool_limits
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from models import research_horizon as horizon
from models import xgboost_model as six

F = six.CANONICAL_FEATURE_COLS
HF = [*F, 'origin_month_sin', 'origin_month_cos']
MODELS = ['persistence', 'xgb_expanding', 'linear_expanding', 'hgb_12month_fixed']
STUDY = ROOT/'reports/actual_forecast_validation_20261019'
IDENTITY = ['latitude', 'longitude', 'well_depth_m', 'aquifer', 'well_type']


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def write_csv(path, frame):
    with Path(path).open('x', encoding='utf-8', newline='') as handle:
        frame.to_csv(handle, index=False)


def namespace(path):
    path = Path(path).resolve()
    base = (ROOT/'reports/candidates').resolve()
    if (not path.is_relative_to(base) or path == base
            or not path.relative_to(base).parts[0].startswith('twelve_month_horizon_')):
        raise ValueError('Use a dedicated reports/candidates/twelve_month_horizon_* directory')
    return path


def protocol_at(path):
    path = Path(path).resolve()
    namespace(path.parent)
    protocol = json.loads(path.read_text(encoding='utf-8'))
    if protocol['horizon_months'] != 12 or protocol['embargo_months'] != 12 or not protocol['no_tuning_or_model_selection']:
        raise ValueError('Frozen twelve-month protocol required')
    for name, checksum in protocol['inputs_sha256'].items():
        if horizon.sha256_file(ROOT/name) != checksum:
            raise ValueError(f'Frozen input changed: {name}')
    return protocol, horizon.sha256_file(path)


def import_adapter():
    spec = importlib.util.spec_from_file_location('retained_telangana_adapter', STUDY/'prepare_research.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_frames():
    full = pd.read_csv(STUDY/'normalized_v2/research_features.csv', parse_dates=['date'])
    normalized = pd.read_csv(STUDY/'normalized_v2/normalized_well_observations.csv',
        dtype={'provider_well_id':str}, parse_dates=['date', 'reported_observation_date'])
    # Filter metadata before any prediction errors; never repair guessed locations.
    agreement = normalized.source_name_district_id.notna() & normalized.source_name_district_id.eq(normalized.district_id)
    adapter = import_adapter()
    monthly, _ = adapter.aggregate_monthly(normalized.loc[agreement].copy())
    strict = adapter.build_research_features(monthly, full, end='2026-09-01')
    return full, strict, normalized


def decorate_cases(frame, protocol):
    cases = horizon.build_cases(frame, 12)
    meta = frame[['district_id','date','panel_sha256','well_count','first_reported_date','last_reported_date']]
    meta = meta.rename(columns={'date':'target_date', **{c:'target_'+c for c in meta if c not in ('date','district_id')}})
    cases = cases.merge(meta, on=['district_id','target_date'], how='left', validate='many_to_one')
    cases['identical_origin_target_panel'] = cases.panel_sha256.notna() & cases.panel_sha256.eq(cases.target_panel_sha256)
    selected = cases.target_date.between(protocol['primary_target_range'][0], protocol['secondary_target_range'][1])
    inventory = cases.loc[selected].copy()
    inventory['period'] = np.where(inventory.target_date.le(protocol['primary_target_range'][1]), 'primary', 'secondary')
    inventory['complete_inputs'] = np.isfinite(inventory[HF]).all(axis=1)
    inventory['complete_ols_training_n'] = 0
    for fold in protocol['annual_folds']:
        train, _, metadata = horizon.split_fold(cases, fold['target_year'], 12)
        if metadata['cutoff'] != fold['train_target_cutoff'] or metadata['first_permitted_origin'] != fold['first_permitted_origin']:
            raise ValueError('Fold differs from frozen protocol')
        counts = train.loc[np.isfinite(train[F]).all(axis=1)].groupby('district_id').size()
        index = inventory.index[inventory.target_date.dt.year.eq(fold['target_year'])]
        inventory.loc[index,'complete_ols_training_n'] = inventory.loc[index,'district_id'].map(counts).fillna(0).astype(int)
        inventory.loc[index,'train_target_cutoff'] = metadata['cutoff']
    inventory['common_eligible'] = inventory.reference_eligible & inventory.complete_inputs & inventory.complete_ols_training_n.ge(12)
    inventory['exclusion_reasons'] = ''
    for flag, reason in [('reference_eligible','missing_observed_origin_or_target'),
                         ('complete_inputs','missing_common_model_inputs')]:
        inventory.loc[~inventory[flag],'exclusion_reasons'] += reason+';'
    inventory.loc[inventory.complete_ols_training_n.lt(12),'exclusion_reasons'] += 'fewer_than_12_complete_district_training_pairs;'
    if not inventory.loc[inventory.reference_eligible,'seasonal_naive'].eq(inventory.loc[inventory.reference_eligible,'gwl_current']).all():
        raise ValueError('Annual seasonal naive must equal persistence at twelve months')
    return cases, inventory


def well_pairs(normalized, protocol):
    origin = normalized[['agency','provider_well_id','date','gwl_m_bgl','source_name_district_id','district_id',*IDENTITY]].copy()
    origin = origin.rename(columns={c:'origin_'+c for c in origin if c not in ('agency','provider_well_id')})
    target = normalized.loc[normalized.date.between(protocol['primary_target_range'][0],protocol['secondary_target_range'][1])].copy()
    target['origin_date'] = target.date-pd.DateOffset(months=12)
    paired = target.merge(origin,on=['agency','provider_well_id','origin_date'],how='left',validate='one_to_one')
    valid = np.isfinite(paired[['gwl_m_bgl','origin_gwl_m_bgl']]).all(axis=1)
    for column in IDENTITY:
        valid &= paired[column].notna() & paired['origin_'+column].notna() & paired[column].eq(paired['origin_'+column])
    paired = paired.loc[valid].copy()
    paired['strict_name_coordinate_agreement_both'] = (paired.source_name_district_id.notna()
        & paired.source_name_district_id.eq(paired.district_id)
        & paired.origin_source_name_district_id.notna()
        & paired.origin_source_name_district_id.eq(paired.origin_district_id))
    paired['period'] = np.where(paired.date.le(protocol['primary_target_range'][1]),'primary','secondary')
    return paired[['agency','provider_well_id','district_id','origin_date','date','origin_gwl_m_bgl',
        'gwl_m_bgl','strict_name_coordinate_agreement_both','period']]


def prepare(protocol_path):
    protocol, checksum = protocol_at(protocol_path)
    directory = namespace(Path(protocol_path).parent/'cohorts')
    if directory.exists():
        raise FileExistsError('Cohort archive already exists; never overwrite')
    full, strict, normalized = load_frames()
    # Rebuild a historical prefix from source rows, not from future-filled values.
    # Weather is exact-key copied from the retained causal generation.
    adapter = import_adapter()
    prefix_checks = {}
    for label, frame, rows in [('full_coordinate',full,normalized),
            ('exact_name_coordinate',strict,normalized.loc[normalized.source_name_district_id.notna()
                & normalized.source_name_district_id.eq(normalized.district_id)])]:
        monthly,_ = adapter.aggregate_monthly(rows.loc[rows.date.le('2022-12-01')])
        prefix = adapter.build_research_features(monthly,full.loc[full.date.le('2022-12-01')],end='2022-12-01')
        paired = prefix.merge(frame,on=['district_id','date'],suffixes=('_prefix','_all'),validate='one_to_one')
        for feature in HF:
            if not np.allclose(paired[feature+'_prefix'],paired[feature+'_all'],rtol=0,atol=1e-10,equal_nan=True):
                raise ValueError('Future source rows changed historical features: '+feature)
        for flag in ('is_observed','is_imputed'):
            if not paired[flag+'_prefix'].equals(paired[flag+'_all']):
                raise ValueError('Future source rows changed historical observation flags')
        prefix_checks[label]={'prefix_end':'2022-12-01','compared_rows':len(paired),
            'features_unchanged':True,'observation_flags_unchanged':True,'comparison_atol':1e-10}
    directory.mkdir(exist_ok=False)
    counts = []
    for name, frame in [('full_coordinate',full),('exact_name_coordinate',strict)]:
        _, inventory = decorate_cases(frame, protocol)
        write_csv(directory/(name+'_inventory.csv'),inventory)
        if name == 'exact_name_coordinate':
            write_csv(directory/'strict_features.csv',frame)
        for period, table in inventory.groupby('period'):
            eligible = table.loc[table.common_eligible]
            counts.append({'dataset':name,'period':period,'registered':len(table),
                'observed_origin_target':int(table.reference_eligible.sum()),'common_eligible':len(eligible),
                'districts':int(eligible.district_id.nunique()),
                'same_origin_target_panel':int(eligible.identical_origin_target_panel.sum()),
                'target_start':str(eligible.target_date.min().date()) if len(eligible) else None,
                'target_end':str(eligible.target_date.max().date()) if len(eligible) else None})
    pairs = well_pairs(normalized,protocol)
    write_csv(directory/'well_pairs.csv',pairs)
    write_csv(directory/'cohort_counts.csv',pd.DataFrame(counts))
    named = normalized.source_name_district_id.notna()
    mismatch = named & normalized.source_name_district_id.ne(normalized.district_id)
    quality = {'accepted_rows':len(normalized),'provider_ids':int(normalized.provider_well_id.nunique()),
        'exact_name_coordinate_rows':int((named & ~mismatch).sum()),'name_coordinate_conflict_rows':int(mismatch.sum()),
        'unknown_name_rows':int((~named).sum()),
        'availability_populated':{c:int(normalized[c].notna().sum()) for c in
            ('actual_acquisition_at','first_publication_at','first_received_at','available_at')},
        'mapping_policy':'No guessed correction. Full coordinate aggregation conditional; exact-agreement reaggregation separate.',
        'well_pairs_by_period':pairs.groupby('period').size().to_dict(),
        'well_pairs_strict_by_period':pairs.loc[pairs.strict_name_coordinate_agreement_both].groupby('period').size().to_dict(),
        'no_forecast_errors_examined':True,'no_model_fitting_in_preparation':True}
    quality['causal_prefix_checks']=prefix_checks
    write_json(directory/'data_quality.json',quality)
    implementation = {name:horizon.sha256_file(ROOT/name) for name in ('models/research_horizon.py','scripts/backtest_twelve_month.py')}
    write_json(directory/'lock.json',{'frozen_at_utc':now(),'protocol_sha256':checksum,
        'implementation_sha256':implementation,
        'files':{p.name:horizon.sha256_file(p) for p in directory.iterdir() if p.is_file()}})
    print(json.dumps({'prepared_at_utc':now(),'counts':counts,'quality':quality},indent=2),flush=True)


def measure(actual,prediction):
    y,p = np.asarray(actual,float),np.asarray(prediction,float)
    if not len(y):
        return {'n':0,'status':'no_eligible_cases'}
    result = six.metrics(y,p)
    error = p-y
    absolute = np.abs(error)
    result.update(bias_m=float(error.mean()),negative_predictions=int((p<0).sum()),
        ae_over_5m=int((absolute>5).sum()),ae_over_10m=int((absolute>10).sum()),ae_max_m=float(absolute.max()))
    result.update({f'ae_p{q}_m':float(np.percentile(absolute,q)) for q in (50,75,90,95,99)})
    return result


def bootstrap(table,model,baseline='persistence',repeats=2000):
    """Paired descriptive district bootstrap and circular twelve-month blocks."""
    if table.empty:
        return {'model':model,'baseline':baseline,'n':0,'districts':0,'target_months':0,'status':'no_eligible_cases'}
    districts = sorted(table.district_id.unique())
    months = pd.date_range(table.target_date.min(),table.target_date.max(),freq='MS')
    di,mi = {k:i for i,k in enumerate(districts)},{k:i for i,k in enumerate(months)}
    totals = np.zeros((len(districts),len(months),7))
    for row in table.itertuples():
        a,b = getattr(row,model)-row.actual,getattr(row,baseline)-row.actual
        totals[di[row.district_id],mi[row.target_date]] += [1,abs(a),a*a,a,abs(b),b*b,b]
    rng = np.random.default_rng(42)
    values = {'district':[],'district_x_12month_blocks':[]}
    for _ in range(repeats):
        dw = np.bincount(rng.integers(len(districts),size=len(districts)),minlength=len(districts))
        starts = rng.integers(len(months),size=int(np.ceil(len(months)/12)))
        chosen = np.concatenate([(np.arange(12)+s)%len(months) for s in starts])[:len(months)]
        tw = np.bincount(chosen,minlength=len(months))
        for method,weights in [('district',np.ones(len(months))),('district_x_12month_blocks',tw)]:
            n,aa,sa,ba,ab,sb,bb = np.einsum('i,j,ijk->k',dw,weights,totals)
            if n:
                values[method].append([aa/n,np.sqrt(sa/n),ba/n,(aa-ab)/n,np.sqrt(sa/n)-np.sqrt(sb/n),(ba-bb)/n])
    names = ['model_mae_m','model_rmse_m','model_bias_m','mae_difference_m','rmse_difference_m','bias_difference_m']
    intervals = {method:{name:np.quantile(data,[.025,.975],axis=0)[:,i].tolist() for i,name in enumerate(names)}
                 for method,data in values.items()}
    return {'model':model,'baseline':baseline,'districts':len(districts),'target_months':len(months),
        'resamples':repeats,'seed':42,'negative_mae_rmse_difference_favors_model':True,
        'bias_difference_interpretation':'Signed bias differences have no universally favorable direction.',
        'interval_95_percentile':intervals,
        'limitations':'Descriptive dependent regional current-vintage sample; few annual blocks. Not prospective or confirmatory.'}


def summarize(table,names):
    if table.empty:
        return {'n':0,'status':'no_eligible_cases'}
    if not np.isfinite(table[['actual',*names]]).all().all():
        raise ValueError('Nonfinite prediction on frozen common cohort; never drop a model-specific case')
    result = {'n':len(table),'districts':int(table.district_id.nunique()),
        'origin_start':str(table.date.min().date()),'origin_end':str(table.date.max().date()),
        'target_start':str(table.target_date.min().date()),'target_end':str(table.target_date.max().date()),
        'target_months':int(table.target_date.nunique()),'models':{name:measure(table.actual,table[name]) for name in names}}
    for label,groups in [('district_macro',table.district_id),('calendar_month_macro',table.target_date.dt.month)]:
        result[label] = {}
        for name in names:
            scores=[measure(part.actual,part[name]) for _,part in table.groupby(groups)]
            result[label][name]={key:float(np.mean([score[key] for score in scores])) for key in ('mae_m','rmse_m','bias_m')}
    return result


def model_card(protocol,checksum,train,metadata,family,features,model_name):
    return {'research_schema_version':1,'research_only':True,'allowed_use':'historical_research_only',
        'horizon_months':12,'embargo_months':12,'family':family,'features':features,
        'feature_schema_sha256':horizon.schema_hash(features),'units':'m_bgl','protocol_sha256':checksum,
        'train_target_cutoff':metadata['cutoff'],'max_train_target_date':str(train.target_date.max().date()),
        'max_train_origin':str(train.date.max().date()),'train_n':len(train),'created_at_utc':now(),
        'model_name':model_name,'settings':protocol['models'][model_name],
        'input_sha256':protocol['inputs_sha256'],'training_case_ids_sha256':hashlib.sha256('\n'.join(sorted(train.case_id)).encode()).hexdigest(),
        'configuration_sha256':protocol['inputs_sha256']['config.yaml'],
        'feature_units':six.FEATURE_UNITS,
        'implementation_sha256':{name:horizon.sha256_file(ROOT/name) for name in
            ('models/research_horizon.py','scripts/backtest_twelve_month.py')},
        'shadow_artifact_approved':False,'forecast_issued_at':None,'historical_availability_verified':False,
        'no_model_selection_or_tuning':True}


def breakdown(table,names,cohort):
    result=[]
    for dimension,groups in [('district',table.district_id),('calendar_month',table.target_date.dt.month),
                             ('target_year',table.target_date.dt.year),('target_period',table.target_date.dt.strftime('%Y-%m'))]:
        for group,part in table.groupby(groups):
            for name in names:
                result.append({'cohort':cohort,'dimension':dimension,'group':str(group),'model':name,**measure(part.actual,part[name])})
    return result


def compare_six(full,output,protocol):
    previous = pd.read_csv(STUDY/'evaluation_v2/historical_predictions_vs_observations.csv',parse_dates=['date','target_date'])
    previous = previous.loc[previous.primary_common.astype(str).str.lower().eq('true')].copy()
    current = full.loc[full.common_eligible & full.period.eq('primary')].copy()
    result,intervals = {},[]
    for join in ('target_date','date'):
        old = previous[['district_id',join,'actual','persistence','seasonal_naive','xgb_expanding','linear_expanding',
                        'date' if join=='target_date' else 'target_date','expanding_train_label_cutoff']]
        merged = current.merge(old,on=['district_id',join],suffixes=('_12','_6'),validate='one_to_one')
        write_csv(output/('six_vs_twelve_same_'+('target' if join=='target_date' else 'origin')+'.csv'),merged)
        summary={'n':len(merged),'same_outcomes':join=='target_date','controlled_horizon_effect':False,
                 'caveat':'Different origins/cutoffs on matched targets; different targets on matched origins. Existing6models were not refitted.'}
        for h in (6,12):
            summary[str(h)]={name:measure(merged['actual_'+str(h)],merged[name+'_'+str(h)]) for name in ('persistence','xgb_expanding','linear_expanding')}
        summary['six_month_seasonal_naive'] = measure(merged.actual_6,merged.seasonal_naive_6)
        if join=='target_date':
            if not np.allclose(merged.actual_12,merged.actual_6,rtol=0,atol=1e-10):
                raise ValueError('Matched targets differ from preserved six-month observations')
            for name in ('persistence','xgb_expanding','linear_expanding'):
                table=merged[['district_id','target_date','actual_12',name+'_12',name+'_6']].rename(columns={'actual_12':'actual'})
                intervals.append(bootstrap(table,name+'_12',name+'_6',protocol['uncertainty']['resamples']))
        result['same_'+join] = summary
    write_json(output/'six_vs_twelve_context.json',result)
    write_json(output/'six_vs_twelve_uncertainty.json',intervals)


def run(protocol_path,output):
    protocol, checksum = protocol_at(protocol_path)
    base = Path(protocol_path).resolve().parent
    output = namespace(output)
    if not output.is_relative_to(base) or output.exists():
        raise ValueError('Output must be a new child directory of this frozen experiment')
    lock=json.loads((base/'cohorts/lock.json').read_text())
    if checksum != lock['protocol_sha256']:
        raise ValueError('Frozen protocol changed')
    for name,expected in lock['implementation_sha256'].items():
        if horizon.sha256_file(ROOT/name)!=expected:
            raise ValueError('Implementation changed since cohort freeze; preserve and investigate')
    for name,expected in lock['files'].items():
        if horizon.sha256_file(base/'cohorts'/name)!=expected:
            raise ValueError('Frozen cohort/input changed')
    # Guard against accidental fallback to the database in reused modules.
    def forbidden(*args,**kwargs):
        raise RuntimeError('Database access forbidden in twelve-month research')
    six.get_connection=forbidden
    import db.connection as connection
    connection.get_connection=forbidden
    output.mkdir(exist_ok=False)
    metrics, intervals, groups, fit_log, predictions = {},[],[],[],{}
    computed_at = now()
    for dataset in ('full_coordinate','exact_name_coordinate'):
        frame_path = STUDY/'normalized_v2/research_features.csv' if dataset=='full_coordinate' else base/'cohorts/strict_features.csv'
        frame=pd.read_csv(frame_path,parse_dates=['date'])
        cases,inventory=decorate_cases(frame,protocol)
        frozen=pd.read_csv(base/'cohorts'/(dataset+'_inventory.csv'))
        if inventory.case_id.tolist()!=frozen.case_id.tolist() or inventory.common_eligible.tolist()!=frozen.common_eligible.tolist():
            raise ValueError('Common cohort membership changed before fitting')
        inventory['actual']=inventory.target_value
        inventory['persistence']=inventory.gwl_current.where(inventory.common_eligible)
        inventory['annual_seasonal_naive']=inventory.seasonal_naive.where(inventory.common_eligible)
        for name in MODELS[1:]: inventory[name]=np.nan
        for fold in protocol['annual_folds']:
            year=fold['target_year']
            train,_,metadata=horizon.split_fold(cases,year,12)
            index=inventory.index[inventory.common_eligible & inventory.target_date.dt.year.eq(year)]
            if not len(index): continue
            complete=train.loc[np.isfinite(train[F]).all(axis=1)]
            support=complete.groupby('district_id').size()
            ols_used=complete.loc[complete.district_id.map(support).ge(12)]
            linear={}
            with threadpool_limits(limits=1):
                xgb=XGBRegressor(**protocol['models']['xgb_expanding']['parameters'])
                xgb.fit(train[F],train.target_value)
                inventory.loc[index,'xgb_expanding']=xgb.predict(inventory.loc[index,F])
                for district,part in complete.groupby('district_id'):
                    if len(part)<12: continue
                    estimator=LinearRegression(fit_intercept=True).fit(part[F],part.target_value)
                    linear[district]=estimator
                    selected=index[inventory.loc[index,'district_id'].eq(district)]
                    if len(selected): inventory.loc[selected,'linear_expanding']=estimator.predict(inventory.loc[selected,F])
                hgb=HistGradientBoostingRegressor(**protocol['models']['hgb_12month_fixed']['parameters'])
                hgb.fit(train[HF],train.target_value-train.gwl_current)
                inventory.loc[index,'hgb_12month_fixed']=np.maximum(0,inventory.loc[index,'gwl_current'].to_numpy()+hgb.predict(inventory.loc[index,HF]))
            if not np.isfinite(inventory.loc[index,MODELS]).all().all():
                raise ValueError('A model abstained on a frozen common case; do not change comparison membership')
            directory=output/'models'/dataset
            cards={}
            for name,estimator,family,features,fitted in [
                ('xgb_expanding',xgb,'xgboost',F,train),
                ('linear_expanding',linear,'linear_regression',F,ols_used),
                ('hgb_12month_fixed',hgb,'hist_gradient_boosting',HF,train)]:
                card=model_card(protocol,checksum,fitted,metadata,family,features,name)
                card_path=horizon.save_research_model(estimator,card,directory,f'{name}_{year}')
                saved=json.loads(card_path.read_text())
                cards[name]=saved['model_sha256']
                inventory.loc[index,name+'_model_sha256']=saved['model_sha256']
            fit_log.append({'dataset':dataset,**metadata,'evaluated_common_n':len(index),
                'max_train_origin':str(train.date.max().date()),'complete_ols_train_n':len(complete),
                'ols_used_train_n':len(ols_used),
                'ols_district_counts':{str(k):int(v) for k,v in complete.groupby('district_id').size().items()},
                'model_sha256':cards,'no_learned_preprocessing':True})
            print(json.dumps({'dataset':dataset,'year':year,'train_n':len(train),'evaluation_n':len(index)}),flush=True)
        inventory['computed_at_utc']=computed_at
        inventory['forecast_issued_at']=None
        inventory['evidence_class']='retrospective_current_vintage_nominal_12month_not_issuance_verified'
        inventory['protocol_sha256']=checksum
        inventory['issuance_availability_verified']=False
        write_csv(output/(dataset+'_predictions.csv'),inventory)
        predictions[dataset]=inventory
        for period in ('primary','secondary'):
            table=inventory.loc[inventory.common_eligible & inventory.period.eq(period)].copy()
            cohort=dataset+'_'+period
            metrics[cohort]=summarize(table,MODELS)
            if table.empty: continue
            groups.extend(breakdown(table,MODELS,cohort))
            if not table.persistence.eq(table.annual_seasonal_naive).all():
                raise ValueError('Persistence and annual seasonal differ unexpectedly')
            for name in MODELS:
                item=bootstrap(table,name,repeats=protocol['uncertainty']['resamples'])
                intervals.append({'cohort':cohort,**item})
            if dataset=='full_coordinate':
                stable=table.loc[table.identical_origin_target_panel]
                label=cohort+'_identical_panel'
                metrics[label]=summarize(stable,MODELS)
                groups.extend(breakdown(stable,MODELS,label))
                for name in MODELS[1:]:
                    intervals.append({'cohort':label,**bootstrap(stable,name,repeats=protocol['uncertainty']['resamples'])})
    compare_six(predictions['full_coordinate'],output,protocol)
    pairs=pd.read_csv(base/'cohorts/well_pairs.csv',parse_dates=['date','origin_date'])
    well_results=[]
    for period,part in pairs.groupby('period'):
        for label,table in [('all_metadata_matched',part),('exact_name_coordinate_both',part.loc[part.strict_name_coordinate_agreement_both])]:
            well_results.append({'period':period,'stratum':label,'provider_ids':int(table.provider_well_id.nunique()),
                'baseline':'persistence_equals_annual_seasonal_naive',**measure(table.gwl_m_bgl,table.origin_gwl_m_bgl)})
    write_json(output/'metrics.json',metrics)
    write_json(output/'uncertainty.json',intervals)
    write_csv(output/'group_metrics.csv',pd.DataFrame(groups))
    write_csv(output/'well_baseline_metrics.csv',pd.DataFrame(well_results))
    write_json(output/'execution.json',{'started_at_utc':computed_at,'completed_at_utc':now(),'protocol_sha256':checksum,
        'fit_log':fit_log,'horizon_months':12,'embargo_months':12,'baseline_identity_verified':True,
        'training_or_evaluation_used_imputed_targets':False,'common_cases_frozen_before_fitting':True,
        'tuned_or_selected':False,'production_or_database_writes':False,'shadow_artifact_approved':False,
        'prospective_forecasts_issued':0,'historical_issuance_availability_verified':False})
    print(json.dumps({'metrics':{cohort:{'n':value['n'],'models':value.get('models')} for cohort,value in metrics.items()}},indent=2),flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--stage',choices=['prepare','run'],required=True)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args(argv)
    if args.stage=='prepare': prepare(args.protocol)
    elif args.output_dir is None: parser.error('--output-dir required for run')
    else: run(args.protocol,args.output_dir)


if __name__=='__main__':
    main()
