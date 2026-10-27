"""Prespecify then execute nested rolling-origin development, never promotion."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import pandas as pd

from models import accuracy_experiments as a, accuracy_challengers as learners
from models import climate_forecast_12m as climate
from models.xgboost_model import sha256_file, _write_json, _json_hash
from scripts.audit_accuracy_baselines import ROOT, FEATURES, FROZEN, CURRENT, load_inputs, protected_files


def code_identity():
    names=['scripts/run_accuracy_experiments.py','models/accuracy_experiments.py',
           'models/accuracy_challengers.py','models/enriched_training_data.py',
           'models/climate_forecast_12m.py','models/climate_forecast.py',
           'models/climate_inputs.py','models/monthly_projection.py']
    return {name:hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode()).hexdigest() for name in names}


def environment():
    return {'python':platform.python_version(),**{p:importlib.metadata.version(p)
        for p in ['xgboost','numpy','pandas','scikit-learn','scipy']}}


def fingerprint(frame):
    return hashlib.sha256(pd.util.hash_pandas_object(frame,index=False).to_numpy().tobytes()).hexdigest()


def prepare(audit, destination):
    audit,destination=Path(audit),Path(destination)
    if destination.exists():raise FileExistsError('Use a new immutable protocol path.')
    receipt=json.loads((audit/'baseline_audit.json').read_text())
    if receipt['status']!='reproduced':raise ValueError('Baseline audit must pass before experiments.')
    pairs=pd.read_csv(audit/'development_pairs.csv',parse_dates=['origin_date','target_date'])
    folds=a.choose_folds(pairs)
    recipes=learners.candidates()
    for recipe in recipes:
        failures=[]
        if recipe.get('kind')!='trend':
            for fold in folds['inner']+folds['outer']:
                train,_=a.partition(pairs,fold)
                for horizons in learners.horizon_groups(recipe):
                    part=train.loc[train.horizon_months.isin(horizons)]
                    support={'cases':len(part),'districts':int(part.district_id.nunique()),
                             'target_years':int(part.target_date.dt.year.nunique())}
                    if support['cases']<500 or support['districts']<50 or support['target_years']<5:
                        failures.append({'fold':fold['name'],'horizons':horizons,'support':support})
        recipe['status']='unsupported' if failures else 'eligible'
        recipe['eligibility_failures']=failures
    protocol={'version':'aquaiq-accuracy-nested-development-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'starting_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'audit_directory':audit.as_posix(),'audit_sha256':sha256_file(audit/'baseline_audit.json'),
        'pairs_sha256':receipt['development_pairs_sha256'],'folds':folds,
        'primary_metric':'Equal mean of inner-fold district-macro MAE on identical seasonal-eligible cases across ALL candidates and baselines; every district with >=1 eligible case has equal weight within a fold.',
        'secondary_metrics':['case-weighted MAE','RMSE','signed error','median absolute error','coverage','full-population district-macro MAE'],
        'minimum_subgroup_support':{'cases':30,'districts':10},
        'horizon_model_training_support':{'cases':500,'districts':50,'target_years':5},
        'fold_rule':'Last two eligible origin years whose full twelve-horizon target window ends strictly before 2023; training labels through December y-2, validation origins January-December y, validation targets through December y+1. At least 20,000 train rows, 250 train districts, five train target years; 1,000 validation rows and 100 districts. Each outer uses the last two eligible inner validation years with their entire target window ending by its training-label cutoff. Target windows overlap; dependent cases are acknowledged.',
        'selection_rule':'Per outer: rank candidates and both baselines on its two inner folds only, tie by mean RMSE then name. Outer labels never select features, trees or candidate. Final development recipe uses the union of inner years only. Keep the existing candidate if the final winner is a baseline/reference or no new recipe beats current_recipe.',
        'early_stopping':'Only early_stopping/slower_learning candidates use up to 480 trees and 40 rounds on inner folds. Outer/final tree counts are rounded medians of selected inner best counts. Early stopping monitors delta MAE; selection scores reconstructed floored depth rounded to four decimals.',
        'candidates':recipes,'base_parameters':learners.BASE,'feature_groups':learners.GROUPS,
        'unsupported_candidate_rule':'Support is checked before fitting on every inner/outer training partition. A recipe failing a predeclared horizon support threshold is excluded from all folds, with exact reasons retained. No validation cases are removed to rescue it.',
        'horizon_groups':[[1,2,3,4],[5,6,7,8],[9,10,11,12]],
        'horizon_group_rationale':'Three contiguous four-month product segments provide short/middle/long horizon sharing; specified independently of residuals.',
        'baselines':['persistence','seasonal'],'final_label_cutoff':'2025-01-31',
        'fixed_artifact_policy':'Frozen artifact valid only where its 2019-12-31 training cutoff precedes origins. Current 2025-fit artifact is contaminated on all development folds and appears in a separate diagnostic only. Reference recipes are refitted on each chronological training partition.',
        'target':'observed_target_depth_minus_observed_origin_depth_m_bgl',
        'forecast_reconstruction':'round(max(0, observed_origin_gwl + predicted_delta),4)',
        'scope':'Controlled observed-origin depth prediction experiment; not a full serving-tier replay or a prospective test. Genuine observed endpoints only; origin-available causal features. Source publication dates remain unverified.',
        'january2026_for_tuning':False,'old_2023_2024_for_tuning':False,'production_promotion_prohibited':True,
        'old_promotion_requirements':json.loads((ROOT/'reports/retraining_20261027/protocol.json').read_text())['promotion_requirements'],
        'bounded_compute':{'recipe_count':17,'inner_folds':3,'outer_folds':2,'maximum_cell_fits':85,
                           'xgb_workers':4,'maximum_trees_per_member':480,'maximum_wall_seconds':7200},
        'training_code':code_identity(),'environment':environment()}
    _write_json(destination,protocol)
    print(f'Locked protocol: {destination}; SHA-256 {sha256_file(destination)}',flush=True)


def score(cases, names):
    return {'joint':a.matched(cases,names),'full':{m:a.metric(cases.loc[np.isfinite(cases[m])],m) for m in names},
            'coverage':{m:{'available':int(np.isfinite(cases[m]).sum()),'missing':int((~np.isfinite(cases[m])).sum())} for m in names}}


def rank(records, years, names):
    values={}
    for name in names:
        parts=[r['scores']['joint']['methods'][name] for r in records if r['year'] in years and r['phase']=='inner']
        if len(parts)!=len(years) or any(not x['supported'] for x in parts):
            raise ValueError('Every ranked candidate needs the same supported inner folds.')
        values[name]={'mean_fold_district_macro_mae_m':float(np.mean([x['district_macro_mae_m'] for x in parts])),
                      'mean_fold_rmse_m':float(np.mean([x['rmse_m'] for x in parts]))}
    winner=min(values,key=lambda n:(values[n]['mean_fold_district_macro_mae_m'],values[n]['mean_fold_rmse_m'],n))
    return winner,values


def trees_for(records, years, name):
    details=[r['fits'][name] for r in records if r['year'] in years]
    if not details or not details[0]:return None
    if details[0][0]['trees'] is None:return None
    return [max(1,int(np.rint(np.median([d[i]['trees'] for d in details])))) for i in range(len(details[0]))]


def gate_table(cases, candidate, reference):
    rows=[]
    for field in ['horizon','history_group','gained_history','newly_local_history','substantial_original_history']:
        for value,g in cases.groupby(field,dropna=False):
            panel=a.matched(g,[candidate,reference]);c,b=panel['methods'][candidate],panel['methods'][reference]
            supported=c['supported']
            rows.append({'group':field,'value':str(value),'candidate':c,'reference':b,
                'relative_mae_regression':(c['mae_m']/b['mae_m']-1) if supported and b['mae_m'] else None,
                'status':'unsupported' if not supported else 'pass' if c['mae_m']<=b['mae_m']*1.10 else 'fail'})
    return rows


def run(protocol_path,output):
    protocol_path,output=Path(protocol_path),Path(output)
    protocol=json.loads(protocol_path.read_text())
    if output.exists():raise FileExistsError('Use a new immutable experiment run directory.')
    if protocol['training_code']!=code_identity():raise ValueError('Code changed after prespecification; lock a new protocol.')
    audit=Path(protocol['audit_directory'])
    if sha256_file(audit/'baseline_audit.json')!=protocol['audit_sha256']:raise ValueError('Audit checksum mismatch.')
    if sha256_file(audit/'development_pairs.csv')!=protocol['pairs_sha256']:raise ValueError('Pair checksum mismatch.')
    before=protected_files();output.mkdir(parents=True)
    _write_json(output/'protected_before.json',before)
    pairs=pd.read_csv(audit/'development_pairs.csv',parse_dates=['origin_date','target_date'])
    assert not pairs.target_date.gt(protocol['final_label_cutoff']).any()
    frame,original,identity=load_inputs()
    # Remove inspected January 2026 labels even from history supplied to trend.
    frame=frame.loc[frame.date.le(protocol['final_label_cutoff'])].copy();frame.attrs={}
    recipes=[r for r in protocol['candidates'] if r['status']=='eligible']
    names=[r['name'] for r in recipes]+['persistence','seasonal']
    records=[];outer_cases=[];started=time.monotonic()
    fold_inputs={}
    for phase,folds in [('inner',protocol['folds']['inner']),('outer',protocol['folds']['outer'])]:
        for fold in folds:
            if time.monotonic()-started>protocol['bounded_compute']['maximum_wall_seconds']:
                raise TimeoutError('Prespecified compute budget exceeded; no partial selection.')
            year=fold['year'];train,valid=a.partition(pairs,fold)
            train_hash=fingerprint(train)
            cases=valid[['district_id','origin_date','target_date','horizon_months','actual_gwl','origin_gwl']].rename(
                columns={'horizon_months':'horizon','actual_gwl':'actual'}).copy()
            cases=a.baseline_cases(cases,frame)
            np.testing.assert_allclose(cases.persistence,cases.origin_gwl,rtol=0,atol=1e-12)
            cases=a.metadata(cases,frame,original)
            cases['tier']=np.where(cases.projection_fit_eligible,'observed_origin_fit_eligible','sparse_observed_origin')
            fold_inputs[f'{phase}_{year}']={'training':a.describe_pairs(train),'validation':a.describe_pairs(valid),
                'training_fingerprint':train_hash,'case_keys_sha256':a.key_hash(cases),
                'train_pairs_per_district':{str(q):float(train.groupby('district_id').size().quantile(q)) for q in [0,.1,.5,.9,1]},
                'top_ten_district_training_pair_fraction':float(train.groupby('district_id').size().nlargest(10).sum()/len(train)),
                'balanced_district_total_weight':float(len(train)/train.district_id.nunique())}
            fits={}
            if phase=='outer':
                winner,ranks=rank(records,fold['inner_years'],names)
                # This lock is written before producing any outer predictions.
                _write_json(output/f'outer_{year}_selection_lock.json',{'winner':winner,'inner_years':fold['inner_years'],'ranks':ranks})
            for recipe in recipes:
                name=recipe['name']
                print(f'{phase} {year}: {name} ({len(train):,} train / {len(valid):,} validation)',flush=True)
                counts=trees_for(records,fold['inner_years'],name) if phase=='outer' else None
                model=learners.fit(recipe,train,validation=valid if phase=='inner' else None,
                                   tree_counts=counts,frame=frame)
                cases[name]=model.depth(valid)
                fits[name]=model.fit_details
                artifact=output/'fold_artifacts'/f'{phase}_{year}'/name
                card={'candidate_version':f'accuracy-v1-{phase}-{year}-{name}',
                      'units':'m_bgl','target':protocol['target'],'fold':fold,'phase':phase,
                      'training_dataset_fingerprint':train_hash,'train_target_cutoff':fold['train_target_cutoff'],
                      'training_code':protocol['training_code'],'protocol_sha256':sha256_file(protocol_path),
                      'feature_generation':identity['feature_generation_id'],'feature_csv_sha256':identity['feature_manifest']['feature_csv_sha256'],
                      'environment':protocol['environment'],'promoted':False,'validation_counts':a.describe_pairs(valid)}
                learners.save(model,artifact,card)
                loaded,_=learners.load(artifact/'checkpoint.json',frame=frame)
                np.testing.assert_allclose(loaded.depth(valid),cases[name],rtol=0,atol=1e-4)
            record={'phase':phase,'year':year,'fold':fold,'fits':fits,'scores':score(cases,names)}
            if phase=='outer':
                cases['nested_selected']=cases[winner]
                cases['nested_selected_name']=winner
                record['selected_from_inner']=winner
                record['nested_scores']=score(cases,['nested_selected','current_recipe','production_recipe','persistence','seasonal'])
                # Only frozen predictions respect these outer origins. The
                # current artifact is explicitly labelled contaminated diagnostic.
                for name,path in [('frozen_fixed_reference',FROZEN),('current_fixed_CONTAMINATED',CURRENT)]:
                    model,card=climate.load_bundle(path,expected_generation=identity['feature_generation_id'])
                    cases[name]=np.round(np.maximum(0.,valid.origin_gwl.to_numpy()+model.predict(valid[climate.FEATURES])),4)
                record['fixed_artifact_diagnostic']=score(cases,['frozen_fixed_reference','current_fixed_CONTAMINATED','current_recipe','persistence','seasonal'])
                record['subgroup_gates_vs_current']=gate_table(cases,'nested_selected','current_recipe')
                record['subgroup_gates_vs_frozen']=gate_table(cases,'nested_selected','frozen_fixed_reference')
                record['paired_uncertainty']={b:a.paired_district_bootstrap(cases,'nested_selected',b)
                                              for b in ['current_recipe','frozen_fixed_reference','persistence','seasonal']}
                outer_cases.append(cases)
            case_path=output/f'{phase}_{year}_cases.csv'
            cases.to_csv(case_path,index=False,lineterminator='\n')
            record['cases_sha256']=sha256_file(case_path)
            records.append(record)
            _write_json(output/'progress.json',records)
            print(f'{phase} {year} complete.',flush=True)
    _write_json(output/'fold_inputs.json',fold_inputs)
    _write_json(output/'results.json',records)
    pooled=pd.concat(outer_cases,ignore_index=True)
    pooled.to_csv(output/'outer_pooled_cases.csv',index=False,lineterminator='\n')
    outer_methods=names+['nested_selected','frozen_fixed_reference','current_fixed_CONTAMINATED']
    _write_json(output/'outer_diagnostics.json',a.diagnostics(pooled,outer_methods))
    final_years=[f['year'] for f in protocol['folds']['inner']]
    final_winner,ranks=rank(records,final_years,names)
    final={'selected':final_winner,'inner_years_only':final_years,'ranks':ranks,
           'production_changed':False,'promotion_eligible':False,
           'promotion_blocker':'No untouched post-refit test; no full new serving/API/rollback gate assessment.',
           'old_candidate_retained':True,'new_candidate_checkpoint':None}
    _write_json(output/'final_selection_lock.json',final)
    if final_winner not in ['production_recipe','current_recipe','persistence','seasonal']:
        recipe=next(r for r in recipes if r['name']==final_winner)
        counts=trees_for(records,final_years,final_winner)
        training=pairs.loc[pairs.target_date.le(protocol['final_label_cutoff'])]
        print(f'Final isolated candidate: {final_winner}; {len(training):,} genuine pairs.',flush=True)
        model=learners.fit(recipe,training,tree_counts=counts,frame=frame)
        repeated=learners.fit(recipe,training,tree_counts=counts,frame=frame)
        np.testing.assert_array_equal(model.depth(training),repeated.depth(training))
        if recipe.get('kind') not in ['ridge','trend']:
            assert all(x.get_booster().save_raw(raw_format='ubj')==y.get_booster().save_raw(raw_format='ubj')
                       for (_,x),(_,y) in zip(model.members,repeated.members))
        artifact=ROOT/'models/artifacts'/f'accuracy_experiments_20261027_{output.name}_{final_winner}'
        card={'candidate_version':f'3.0-accuracy-experimental-{final_winner}',
              'units':'m_bgl','target':protocol['target'],'train_target_cutoff':protocol['final_label_cutoff'],
              'training_pairs':a.describe_pairs(training),'training_dataset_fingerprint':fingerprint(training),
              'source_pairs_csv_sha256':protocol['pairs_sha256'],'feature_generation':identity['feature_generation_id'],
              'feature_csv_sha256':identity['feature_manifest']['feature_csv_sha256'],
              'training_code':protocol['training_code'],'protocol_sha256':sha256_file(protocol_path),
              'environment':protocol['environment'],'selection':final,'validation_folds':fold_inputs,
              'uncertainty':'unavailable','promoted':False,'repeat_training_predictions_exact':True,
              'note':'Isolated adapter format, not a production model pointer; no production dispatch changed.'}
        _,saved_card=learners.save(model,artifact,card)
        restored,_=learners.load(artifact/'checkpoint.json',frame=frame)
        np.testing.assert_allclose(restored.depth(training),model.depth(training),rtol=0,atol=1e-4)
        final.update(new_candidate_checkpoint=str((artifact/'checkpoint.json').relative_to(ROOT)).replace('\\','/'),
                     new_candidate_card_sha256=sha256_file(artifact/'model_card.json'),
                     new_candidate_model_hashes=[m['sha256'] for m in saved_card['members']],
                     repeat_training_predictions_exact=True,reloaded_depth_max_difference_m=float(np.max(abs(restored.depth(training)-model.depth(training)))))
    final['wall_seconds']=time.monotonic()-started
    final['outer_pooled_scores']=score(pooled,['nested_selected','current_recipe','production_recipe','frozen_fixed_reference','persistence','seasonal'])
    final['outer_selected_models']={str(r['year']):r['selected_from_inner'] for r in records if r['phase']=='outer'}
    assert before==protected_files()
    assert protocol['training_code']==code_identity()
    _write_json(output/'decision.json',final)
    _write_json(output/'protected_after.json',protected_files())
    print(json.dumps(final,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--audit',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True)
    p=sub.add_parser('run');p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='prepare':prepare(args.audit,args.protocol)
    else:run(args.protocol,args.output)
