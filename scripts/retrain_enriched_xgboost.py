"""Fit an isolated enriched 12-month candidate; never replace deployed pointers.

Earlier chronological folds select settings. Previously inspected final labels
never enter fitting/selection. The saved candidate remains experimental when
there is no genuinely untouched post-refit test period.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import xgboost as xgb

from models import climate_forecast_12m as climate
from models.xgboost_model import load_feature_matrix, observed_mask, sha256_file, _json_hash, _write_json

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'reports/retraining_20261027/protocol.json'


def code_identity():
    names = ['scripts/retrain_enriched_xgboost.py', 'models/enriched_training_data.py',
             'models/climate_forecast_12m.py', 'models/climate_forecast.py',
             'models/climate_inputs.py', 'models/monthly_projection.py', 'models/xgboost_model.py']
    return _json_hash({name: hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode()).hexdigest()
                       for name in names})


def partition(pairs, fold):
    cutoff = pd.Timestamp(fold['train_target_cutoff'])
    first = pd.Timestamp(fold['validation_origin_start'])
    if first < (cutoff.to_period('M')+13).to_timestamp():
        raise ValueError('Rolling folds require the existing twelve-month origin embargo.')
    train = pairs.loc[pairs.target_date.le(cutoff)].copy()
    validation = pairs.loc[pairs.origin_date.between(first, pd.Timestamp(fold['validation_origin_end']))
                           & pairs.target_date.le(pd.Timestamp(fold['validation_target_end']))].copy()
    if train.empty or validation.empty or train.target_date.max() >= validation.origin_date.min():
        raise ValueError('Empty or overlapping chronological training/validation split.')
    if set(train.horizon_months.astype(int)) != set(range(1, 13)):
        raise ValueError('Training must contain actual observed pairs for every horizon.')
    return train, validation


def metric(part, prediction):
    if part.empty:
        return {'n': 0, 'districts': 0, 'mae_m': None, 'rmse_m': None, 'district_macro_mae_m': None}
    error = part[prediction].to_numpy(float)-part.actual.to_numpy(float)
    if not np.isfinite(error).all():
        raise ValueError('Nonfinite prediction/target in validation comparison.')
    absolute = pd.Series(np.abs(error), index=part.index)
    return {'n': len(part), 'districts': int(part.district_id.nunique()),
            'mae_m': float(absolute.mean()), 'rmse_m': float(np.sqrt(np.mean(error**2))),
            'district_macro_mae_m': float(absolute.groupby(part.district_id).mean().mean())}


def predict_deltas(model, values):
    predicted = np.asarray(model.predict(values),dtype=float)
    if predicted.shape != (len(values),) or not np.isfinite(predicted).all():
        raise ValueError('Model must return exactly one finite depth change per input row.')
    return predicted


def compare_pairs(pairs, models, frame):
    cases = pairs[['district_id', 'origin_date', 'target_date', 'horizon_months', 'actual_gwl', 'origin_gwl']].copy()
    cases = cases.rename(columns={'actual_gwl': 'actual', 'horizon_months': 'horizon'})
    for name, model in models.items():
        cases[name] = np.maximum(0., cases.origin_gwl.to_numpy()+predict_deltas(model,pairs[climate.FEATURES]))
    cases['persistence'] = cases.origin_gwl
    labels = frame.loc[observed_mask(frame) & ~frame.is_imputed].set_index(['district_id','date']).gwl_current
    previous = cases.target_date-pd.DateOffset(years=1)
    keys = pd.MultiIndex.from_arrays([cases.district_id, previous])
    seasonal = labels.reindex(keys).to_numpy(float)
    cases['seasonal'] = np.where(previous.le(cases.origin_date), seasonal, np.nan)
    return cases


def summarize_cases(cases):
    names = ['frozen', 'retrained', 'persistence']
    result = {name: metric(cases, name) for name in names}
    paired = cases.loc[cases.seasonal.notna()]
    result['seasonal_paired'] = {name: metric(paired,name) for name in names+['seasonal']}
    result['dates'] = {name: [cases[name].min().date().isoformat(), cases[name].max().date().isoformat()]
                       for name in ['origin_date', 'target_date']}
    result['by_horizon'] = {str(h): {name: metric(cases.loc[cases.horizon.eq(h)],name) for name in names}
                            for h in range(1,13)}
    result['by_history_group'] = {group: {name: metric(cases.loc[cases[group]],name) for name in names}
        for group in ['gained_accepted_history','newly_local_history','substantial_original_history'] if group in cases}
    return result


def select_candidate(results):
    if not results or any(item.get('phase') != 'earlier_validation' for item in results):
        raise ValueError('Selection accepts earlier validation records only.')
    scores = {}
    for name in sorted({item['candidate'] for item in results}):
        folds = [item for item in results if item['candidate'] == name]
        scores[name] = {'folds': len(folds),
            'district_macro_mae_m': float(np.mean([f['metrics']['retrained']['district_macro_mae_m'] for f in folds])),
            'mean_fold_rmse_m': float(np.mean([f['metrics']['retrained']['rmse_m'] for f in folds])),
            'final_trees': max(1,int(np.rint(np.median([f['best_iteration']+1 for f in folds]))))}
    counts = {item['folds'] for item in scores.values()}
    if len(counts) != 1:
        raise ValueError('All candidates must share the same validation folds.')
    winner = min(scores, key=lambda name: (scores[name]['district_macro_mae_m'],scores[name]['mean_fold_rmse_m'],name))
    return winner, scores


def preservation(checkpoint, protocol_path=PROTOCOL):
    pointer = json.loads(Path(checkpoint).read_text(encoding='utf-8'))
    paths = [Path(checkpoint), *[(Path(checkpoint).parent/pointer[key]).resolve() for key in ['model_path','card_path']]]
    paths += [climate.ARTIFACT_PATH, Path(protocol_path)]
    return {str(p.resolve()): sha256_file(p) for p in paths}


def fit_final(training, parameters):
    if training.empty or set(training.horizon_months.astype(int)) != set(range(1,13)):
        raise ValueError('Final fit needs genuine observed pairs at all twelve horizons.')
    model = xgb.XGBRegressor(**parameters)
    model.fit(training[climate.FEATURES],training.target_delta,verbose=False)
    return model


def validate_destinations(output, checkpoint):
    output,checkpoint = Path(output).resolve(),Path(checkpoint).resolve()
    artifact_root = (ROOT/'models/artifacts').resolve()
    if output.exists() or checkpoint.exists():
        raise FileExistsError('Choose new immutable training report and candidate checkpoint paths.')
    if (checkpoint.parent.parent != artifact_root
            or not checkpoint.parent.name.startswith('enriched_retraining_')
            or checkpoint.name != 'checkpoint.json'):
        raise ValueError('Candidate needs a fresh models/artifacts/enriched_retraining_*/checkpoint.json directory.')
    if checkpoint.parent.exists() and any(checkpoint.parent.iterdir()):
        raise FileExistsError('Candidate artifact directory is not empty; refusing overwrite.')
    if output.is_relative_to(checkpoint.parent) or checkpoint.parent.is_relative_to(output):
        raise ValueError('Report and model directories must be separate and cannot contain each other.')
    if not any(output.is_relative_to(ROOT/name) for name in ['reports','scratch']):
        raise ValueError('Training reports require a separate reports/ or scratch/ directory.')
    return output,checkpoint


def run(feature_directory, frozen_checkpoint, output, checkpoint, protocol_path=PROTOCOL):
    from models.enriched_training_data import prepare_pairs
    output,checkpoint = validate_destinations(output,checkpoint)
    protocol = json.loads(Path(protocol_path).read_text(encoding='utf-8'))
    frame = load_feature_matrix(feature_directory)
    if (frame.attrs['feature_generation_id'] != protocol['feature_generation'] or
        frame.attrs['feature_manifest']['feature_csv_sha256'] != protocol['feature_csv_sha256']):
        raise ValueError('Feature snapshot differs from the prespecified retraining protocol.')
    frozen_bundle = climate.load_bundle(frozen_checkpoint,expected_generation=frame.attrs['feature_generation_id'])
    if frozen_bundle[1]['model_sha256'] != protocol['frozen_model_sha256']:
        raise ValueError('Frozen reference model differs from the locked protocol.')
    before = preservation(frozen_checkpoint,protocol_path)
    before_code = code_identity()
    output.mkdir(parents=True)
    backup = ROOT/'scratch/retraining_20261027/rollback'
    backup.mkdir(parents=True,exist_ok=True)
    pointer = json.loads(Path(frozen_checkpoint).read_text(encoding='utf-8'))
    for key in ['model_path','card_path']:
        source = Path(frozen_checkpoint).parent/pointer[key]
        target = backup/pointer[key]
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and sha256_file(target) != sha256_file(source):
            raise ValueError('Existing rollback copy differs; refusing overwrite.')
        if not target.exists(): shutil.copyfile(source,target)
    rollback_pointer = backup/'checkpoint.json'
    if rollback_pointer.exists() and rollback_pointer.read_bytes() != Path(frozen_checkpoint).read_bytes():
        raise ValueError('Existing rollback pointer differs.')
    if not rollback_pointer.exists(): shutil.copyfile(frozen_checkpoint,rollback_pointer)
    print('Building serving-encoded, observed-only training pairs...',flush=True)
    base = load_feature_matrix()
    old_labels = base.loc[observed_mask(base)].set_index(['district_id','date']).gwl_current
    new_keys = set(frame.loc[observed_mask(frame)].set_index(['district_id','date']).index)-set(old_labels.index)
    gained = {key[0] for key in new_keys}
    newly_local = set(frame.loc[observed_mask(frame),'district_id'])-set(base.loc[observed_mask(base),'district_id'])
    old_counts = base.loc[observed_mask(base)].groupby('district_id').size()
    substantial = set(old_counts.loc[old_counts.ge(24)].index)
    pairs = prepare_pairs(frame)
    pair_audit = dict(pairs.attrs.get('pair_audit', {}))
    pairs.attrs = {}
    pairs.to_csv(output/'training_pairs.csv',index=False,lineterminator='\n')
    print(f'Prepared {len(pairs):,} exact calendar origin/target pairs.',flush=True)
    results = []
    for fold in protocol['folds']:
        training,validation = partition(pairs,fold)
        for candidate in protocol['selection']['candidates']:
            settings = {**climate.PARAMETERS,**{k:v for k,v in candidate.items() if k!='name'},
                'n_estimators':protocol['selection']['maximum_trees'],
                'early_stopping_rounds':protocol['selection']['early_stopping_rounds']}
            print(f"Fitting {candidate['name']} / {fold['name']}: {len(training):,} train, {len(validation):,} validation",flush=True)
            model = xgb.XGBRegressor(**settings)
            model.fit(training[climate.FEATURES],training.target_delta,
                eval_set=[(validation[climate.FEATURES],validation.target_delta)],verbose=False)
            cases = compare_pairs(validation,{'frozen':frozen_bundle[0],'retrained':model},frame)
            for group,members in [('gained_accepted_history',gained),('newly_local_history',newly_local),
                                  ('substantial_original_history',substantial)]:
                cases[group] = cases.district_id.isin(members)
            case_path = output/f"validation_{fold['name']}_{candidate['name']}.csv"
            cases.to_csv(case_path,index=False,lineterminator='\n')
            results.append({'phase':'earlier_validation','candidate':candidate['name'],'fold':fold,
                'parameters':settings,'best_iteration':int(model.best_iteration),
                'train_pairs':len(training),'train_districts':int(training.district_id.nunique()),
                'validation_cases_file':case_path.name,'validation_cases_sha256':sha256_file(case_path),
                'max_train_target':training.target_date.max().date().isoformat(),
                'metrics':summarize_cases(cases)})
            _write_json(output/'validation_progress.json',results)
    winner,scores = select_candidate(results)
    chosen = next(c for c in protocol['selection']['candidates'] if c['name']==winner)
    parameters = {**climate.PARAMETERS,**{k:v for k,v in chosen.items() if k!='name'},'n_estimators':scores[winner]['final_trees']}
    cutoff = pd.Timestamp(protocol['final_fit_target_cutoff'])
    training = pairs.loc[pairs.target_date.le(cutoff)].copy()
    assert not training.target_date.ge(pd.Timestamp('2026-01-01')).any()
    selection = {'phase':'locked_before_retrospective_final_diagnostic','selected':winner,'scores':scores,
        'parameters':parameters,'fold_results':results,'protocol_sha256':sha256_file(protocol_path),
        'training_code_sha256':before_code,'final_target_cutoff':cutoff.date().isoformat(),
        'selection_uses_january2026_labels':False}
    _write_json(output/'selection.json',selection)
    print(f'Locked {winner}; final fit {len(training):,} pairs / {parameters["n_estimators"]} trees.',flush=True)
    model = fit_final(training,parameters)
    repeated = fit_final(training,parameters)
    raw = model.get_booster().save_raw(raw_format='ubj')
    repeated_raw = repeated.get_booster().save_raw(raw_format='ubj')
    if raw != repeated_raw or not np.array_equal(predict_deltas(model,training[climate.FEATURES]),predict_deltas(repeated,training[climate.FEATURES])):
        raise RuntimeError('Same-seed final training did not reproduce exactly.')
    target_keys = list(zip(training.district_id,training.target_date))
    origin_keys = list(zip(training.district_id,training.origin_date))
    new_target = np.array([key in new_keys for key in target_keys])
    new_origin = np.array([key in new_keys for key in origin_keys])
    if not new_target.any() or not training.loc[new_target,'target_date'].eq(pd.Timestamp('2025-01-01')).any():
        raise ValueError('Accepted enrichment/January2025 labels did not enter final fitting.')
    inclusion = {'pairs_with_new_target':int(new_target.sum()),'pairs_with_new_origin':int(new_origin.sum()),
        'new_months_used_as_target':len(set(k for k in target_keys if k in new_keys)),
        'new_months_used_in_either_role':len({k for k in target_keys+origin_keys if k in new_keys}),
        'january2025_pairs_with_new_target':int((new_target & training.target_date.eq(pd.Timestamp('2025-01-01')).to_numpy()).sum()),
        'latest_training_target':training.target_date.max().date().isoformat()}
    card = {'version':climate.MODEL_VERSION,'candidate_version':'2.0-enriched-retraining-experimental',
        'features':climate.FEATURES,'feature_schema_sha256':_json_hash(climate.FEATURES),
        'units':climate.UNITS,'target':'gwl_change_from_origin','horizons_months':climate.HORIZONS_MONTHS,
        'created_at':datetime.now(timezone.utc).isoformat(),'parameters':parameters,
        'feature_generation_id':frame.attrs['feature_generation_id'],'data_source':frame.attrs['data_source'],
        'data_sha256':frame.attrs['data_sha256'],'feature_csv_sha256':protocol['feature_csv_sha256'],
        'train_target_cutoff':cutoff.date().isoformat(),'max_train_target_date':training.target_date.max().date().isoformat(),
        'max_train_origin':training.origin_date.max().date().isoformat(),'n_train_observed_pairs':len(training),
        'training_districts':int(training.district_id.nunique()),
        'training_counts_by_horizon':{str(int(h)):int(n) for h,n in training.groupby('horizon_months').size().items()},
        'protocol_sha256':sha256_file(protocol_path),'training_code_sha256':before_code,'inclusion':inclusion,
        'evaluation_protocol':protocol,'validation_assessment':{'status':'experimental_not_promoted',
          'sufficient_for_operational_use':False,'untouched_test_available':False},
        'uncertainty':{'status':'unavailable','reason':'Retrained weights have no independently validated matching calibration.'},
        'reference_model_sha256':protocol['frozen_model_sha256']}
    saved_card = climate.publish_bundle(model,card,checkpoint)
    loaded,loaded_card = climate.load_bundle(checkpoint,expected_generation=protocol['feature_generation'])
    if not np.array_equal(predict_deltas(model,training[climate.FEATURES]),predict_deltas(loaded,training[climate.FEATURES])):
        raise ValueError('Saved candidate predictions differ after reload.')
    restored = climate.load_bundle(rollback_pointer,expected_generation=protocol['feature_generation'])
    if restored[1]['model_sha256'] != protocol['frozen_model_sha256']:
        raise ValueError('Rollback bundle failed immutable model verification.')
    if before != preservation(frozen_checkpoint,protocol_path) or before_code != code_identity():
        raise RuntimeError('Frozen inputs or training implementation changed during the run.')
    report = {'selected':winner,'parameters':parameters,'candidate_checkpoint':str(checkpoint.relative_to(ROOT)),
        'candidate_model_sha256':saved_card['model_sha256'],'reference_model_sha256':protocol['frozen_model_sha256'],
        'train_pairs':len(training),'train_districts':int(training.district_id.nunique()),
        'train_origin_start':training.origin_date.min().date().isoformat(),'train_origin_end':training.origin_date.max().date().isoformat(),
        'train_target_start':training.target_date.min().date().isoformat(),'train_target_end':training.target_date.max().date().isoformat(),
        'inclusion':inclusion,'pair_audit':pair_audit,'model_bytes_reproducible':True,
        'reloaded_predictions_exact':True,'rollback_verified':True,'frozen_assets_unchanged':True,
        'training_code_sha256':before_code,'training_pairs_sha256':sha256_file(output/'training_pairs.csv'),
        'promoted':False,'promotion_blocker':'No genuinely untouched post-refit test observations exist.',
        'environment':{'python':__import__('sys').version.split()[0],**{name:importlib.metadata.version(name) for name in ['xgboost','numpy','pandas','scikit-learn','scipy']}}}
    _write_json(output/'training_summary.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='pair_audit'},indent=2))
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['feature-directory','frozen-checkpoint','output','checkpoint']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--protocol',type=Path,default=PROTOCOL)
    args = parser.parse_args()
    run(args.feature_directory,args.frozen_checkpoint,args.output,args.checkpoint,args.protocol)
