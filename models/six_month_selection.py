"""Locked, paired six-month candidate selection; never publishes a model.

python -m models.six_month_selection --stage validation --output-dir reports/candidates/six_month_selection_20261017/experiment_v2
python -m models.six_month_selection --stage test --output-dir reports/candidates/six_month_selection_20261017/experiment_v2

Validation never constructs labels from the final period. The selected settings
are locked before test predictions are computed. All outputs are candidate-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from models import xgboost_model as source

ROOT = source.ROOT
FEATURES = [*source.CANONICAL_FEATURE_COLS, 'origin_month_sin', 'origin_month_cos']
FAMILIES = ('ridge', 'random_forest', 'xgboost', 'hist_gradient_boosting')
BASELINES = ('persistence', 'seasonal_naive')
FOLDS = tuple({
    'fold': f'validation-{year}',
    'train_target_cutoff': f'{cutoff}-12-31',
    'evaluation_origin_start': f'{year-1}-07-01',
    'evaluation_target_start': f'{year}-01-01',
    'evaluation_target_end': f'{year}-12-31',
} for year, cutoff in ((2010, 2008), (2013, 2011), (2016, 2014), (2018, 2016)))
FINAL = {'fold': 'chronological-test', 'train_target_cutoff': '2018-12-31',
         'evaluation_origin_start': '2019-07-01', 'evaluation_target_start': '2020-01-01',
         'evaluation_target_end': '2026-09-30'}


def candidate_output(path):
    path = Path(path).resolve()
    parent = (ROOT / 'reports/candidates').resolve()
    if not path.is_relative_to(parent) or path == parent:
        raise ValueError('Use a dedicated reports/candidates/six_month_selection_* directory')
    if not path.relative_to(parent).parts[0].startswith('six_month_selection_'):
        raise ValueError('Use a dedicated reports/candidates/six_month_selection_* directory')
    return path


def build_cases(frame, origin_policy='observed'):
    if origin_policy not in ('observed', 'causal'):
        raise ValueError('Origin policy must be observed or causal')
    if not {'is_observed', 'is_imputed'}.issubset(frame):
        raise ValueError('Explicit observed and imputed provenance is required')
    frame = frame.copy()
    frame['date'] = pd.to_datetime(frame.date, errors='raise')
    if (frame.date.dt.day != 1).any() or frame.date.isna().any():
        raise ValueError('Calendar month starts required')
    if (source.observed_mask(frame) & source._parse_bool(frame.is_imputed).fillna(False)).any():
        raise ValueError('Observed and imputed flags conflict')
    prepared = source.create_target(source.encode_crop_season(frame))
    valid = prepared.target_is_observed & np.isfinite(prepared.target_gwl_6mo)
    if origin_policy == 'observed':
        valid &= source.observed_mask(prepared)
    else:
        known = source.observed_mask(prepared) | source._parse_bool(prepared.is_imputed).fillna(False)
        valid &= known
        if 'months_since_observation' in prepared:
            age = pd.to_numeric(prepared.months_since_observation, errors='coerce')
            valid &= source.observed_mask(prepared) | age.between(1, 3)
    prepared = prepared.loc[valid].copy()
    prepared['origin_month_sin'] = np.sin(2*np.pi*prepared.date.dt.month/12)
    prepared['origin_month_cos'] = np.cos(2*np.pi*prepared.date.dt.month/12)
    prepared['case_id'] = (prepared.district_id.astype(str) + '|' + prepared.date.dt.strftime('%Y-%m-%d')
                           + '|' + prepared.target_date.dt.strftime('%Y-%m-%d') + '|6')
    if prepared.case_id.duplicated().any():
        raise ValueError('Duplicate evaluation cases')
    return prepared.sort_values(['district_id', 'date']).reset_index(drop=True)


def window_split(cases, specification):
    cutoff = pd.Timestamp(specification['train_target_cutoff'])
    start = pd.Timestamp(specification['evaluation_origin_start'])
    lower = pd.Timestamp(specification['evaluation_target_start'])
    upper = pd.Timestamp(specification['evaluation_target_end'])
    if start < (cutoff.to_period('M')+7).to_timestamp() or lower < start + pd.DateOffset(months=6):
        raise ValueError('Six full embargo months must separate training labels and evaluation origins')
    if upper < lower:
        raise ValueError('Invalid evaluation interval')
    train = cases.loc[cases.target_date <= cutoff].copy()
    evaluated = cases.loc[(cases.date >= start) & cases.target_date.between(lower, upper)
                          & np.isfinite(cases.seasonal_naive_6mo)].copy()
    if len(train) and len(evaluated) and train.target_date.max() >= evaluated.date.min():
        raise ValueError('Training labels overlap evaluated origins')
    return train, evaluated


def candidate_grid():
    grids = {
        'ridge': [{'alpha': value} for value in (0.1, 10., 100.)],
        'random_forest': [
            {'n_estimators': 150, 'max_depth': 12, 'min_samples_leaf': 5, 'max_features': .85},
            {'n_estimators': 150, 'max_depth': None, 'min_samples_leaf': 15, 'max_features': 1.},
            {'n_estimators': 150, 'max_depth': 8, 'min_samples_leaf': 30, 'max_features': 1.}],
        'xgboost': [
            {'n_estimators': 500, 'max_depth': 6, 'learning_rate': .01, 'subsample': .8,
             'min_child_weight': 1, 'reg_lambda': 1.},
            {'n_estimators': 240, 'max_depth': 3, 'learning_rate': .04, 'subsample': .85,
             'min_child_weight': 30, 'reg_lambda': 20.},
            {'n_estimators': 240, 'max_depth': 2, 'learning_rate': .03, 'subsample': .9,
             'min_child_weight': 50, 'reg_lambda': 50.}],
        'hist_gradient_boosting': [
            {'max_iter': 250, 'learning_rate': .05, 'max_leaf_nodes': 15,
             'min_samples_leaf': 30, 'l2_regularization': 10.},
            {'max_iter': 250, 'learning_rate': .05, 'max_leaf_nodes': 31,
             'min_samples_leaf': 50, 'l2_regularization': 20.},
            {'max_iter': 150, 'learning_rate': .05, 'max_leaf_nodes': 7,
             'min_samples_leaf': 100, 'l2_regularization': 50.}],
    }
    return [{'candidate_id': f'{family}-{number}-{form}', 'family': family,
             'parameters': settings, 'target_form': form}
            for family, values in grids.items() for number, settings in enumerate(values, 1)
            for form in ('absolute', 'delta')]


def make_estimator(family, parameters):
    if family == 'ridge':
        return make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                             StandardScaler(), Ridge(**parameters))
    if family == 'random_forest':
        return make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                             RandomForestRegressor(**{**parameters, 'random_state':42, 'n_jobs':1}))
    if family == 'hist_gradient_boosting':
        return HistGradientBoostingRegressor(**{**parameters, 'early_stopping':False, 'random_state':42})
    if family == 'xgboost':
        from xgboost import XGBRegressor
        return XGBRegressor(**parameters, objective='reg:squarederror', tree_method='hist',
                            random_state=42, n_jobs=1, verbosity=0)
    raise ValueError('Unknown candidate family')


def fit_candidate(train, specification):
    estimator = make_estimator(specification['family'], specification['parameters'])
    target = train.target_gwl_6mo.to_numpy()
    if specification['target_form'] == 'delta':
        target = target - train.gwl_current.to_numpy()
    elif specification['target_form'] != 'absolute':
        raise ValueError('Target form must be absolute or delta')
    with threadpool_limits(limits=1):
        estimator.fit(train[FEATURES], target)
    return estimator


def predict_candidate(estimator, rows, specification):
    with threadpool_limits(limits=1):
        values = estimator.predict(rows[FEATURES])
    if specification['target_form'] == 'delta':
        values = values + rows.gwl_current.to_numpy()
    return np.maximum(0., values)


def case_table(rows):
    frame = rows[['case_id', 'district_id', 'date', 'target_date']].copy()
    frame['horizon_months'] = 6
    frame['actual'] = rows.target_gwl_6mo.to_numpy()
    frame['persistence'] = rows.gwl_current.to_numpy()
    frame['seasonal_naive'] = rows.seasonal_naive_6mo.to_numpy()
    frame['origin_observed'] = source.observed_mask(rows).to_numpy()
    return frame.reset_index(drop=True)


def summarize_cases(table, names):
    if table.empty:
        return {'n': 0, 'models': {}, 'status': 'no_eligible_cases'}
    if not np.isfinite(table[['actual', *names]].to_numpy(dtype=float)).all():
        raise ValueError('Every model must predict the identical finite evaluation cases')
    def measured(part):
        return {name: source.metrics(part.actual, part[name]) for name in names}
    by_district = {str(key): {'n': len(part), 'models': measured(part)}
                   for key, part in table.groupby('district_id', sort=True)}
    return {'n': len(table), 'districts': int(table.district_id.nunique()), 'models': measured(table),
            'origin_start': str(pd.to_datetime(table.date).min().date()),
            'origin_end': str(pd.to_datetime(table.date).max().date()),
            'target_start': str(pd.to_datetime(table.target_date).min().date()),
            'target_end': str(pd.to_datetime(table.target_date).max().date()),
            'case_ids_sha256': hashlib.sha256('\n'.join(sorted(table.case_id)).encode()).hexdigest(),
            'by_district': by_district,
            'district_macro': {name: {metric: float(np.mean([d['models'][name][metric] for d in by_district.values()]))
                                      for metric in ('mae_m', 'rmse_m')} for name in names},
            'by_target_year': {str(year): {'n': len(part), 'models': measured(part)} for year, part
                               in table.groupby(pd.to_datetime(table.target_date).dt.year, sort=True)},
            'by_horizon_months': {'6': {'n': len(table), 'models': measured(table)}}}


def paired_bootstrap(table, model_name, baseline, repeats=2000):
    """Paired district blocks, retaining every period/horizon of each district."""
    errors = table.assign(model_ae=(table[model_name]-table.actual).abs(),
                          baseline_ae=(table[baseline]-table.actual).abs(),
                          model_se=(table[model_name]-table.actual)**2,
                          baseline_se=(table[baseline]-table.actual)**2)
    totals = errors.groupby('district_id').agg(n=('actual', 'size'),
        model_ae=('model_ae', 'sum'), baseline_ae=('baseline_ae', 'sum'),
        model_se=('model_se', 'sum'), baseline_se=('baseline_se', 'sum')).to_numpy()
    generator = np.random.default_rng(42)
    selected = generator.integers(0, len(totals), size=(repeats, len(totals)))
    sums = totals[selected].sum(axis=1)
    differences = {'mae_difference_m': (sums[:,1]-sums[:,2])/sums[:,0],
                   'rmse_difference_m': np.sqrt(sums[:,3]/sums[:,0])-np.sqrt(sums[:,4]/sums[:,0])}
    return {'baseline': baseline, 'districts': len(totals), 'repeats': repeats, 'seed': 42,
            'negative_favors_model': True,
            'interval_95_percentile': {key: np.quantile(value, [.025,.975]).tolist() for key, value in differences.items()},
            'limitations': 'District bootstrap does not resolve spatial dependence, few time periods, source changes or prior historical exposure.'}


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def csv_once(path, frame):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='') as handle:
        frame.to_csv(handle, index=False)


def protected_snapshot(output_root):
    files = [p for base in (ROOT/'data/processed', ROOT/'models/checkpoints')
             for p in base.rglob('*') if p.is_file()]
    files += [ROOT/'config.yaml', ROOT/'data/raw/updates/20261013/gwl_manual_quarterly_cgwb_gj_2021_2025.csv']
    files += [p for p in (ROOT/'reports').rglob('*') if p.is_file() and not p.is_relative_to(output_root)]
    return {str(p.relative_to(ROOT)): source.sha256_file(p) for p in sorted(files)}


def protocol(frame, external_features=None):
    import sklearn, xgboost
    return {'version': '1.1-six-month-paired-selection', 'seed': 42,
            'feature_csv_sha256': source.sha256_file(ROOT/'data/processed/features_matrix.csv'),
            'generation': frame.attrs['feature_generation_id'], 'features': FEATURES,
            'source_code_sha256': source.sha256_file(Path(__file__)),
            'shared_target_metrics_code_sha256': source.sha256_file(Path(source.__file__)),
            'r2_policy': 'Undefined when observed targets are constant within floating-point resolution; no measurement-precision threshold.',
            'target': 'Exact six-calendar-month observed depth in m_bgl',
            'primary_origin_policy': 'observed', 'secondary_origin_policy': 'causal_bounded_fill_up_to_three_months',
            'comparison_cohort': 'All candidates and both baselines share finite observed exact seasonal target-minus-12 cases.',
            'validation_folds': FOLDS, 'final': FINAL, 'candidates': candidate_grid(),
            'selection': 'Lowest pooled out-of-fold validation RMSE, deterministic candidate_id tiebreak; best settings per family, then best ML family.',
            'target_transform_selection': 'Absolute level versus depth change from origin; chosen only on validation folds.',
            'prediction_policy': 'All ML physical-depth point predictions truncated at zero; no upper clipping.',
            'preprocessing': 'Training-only median imputation/indicators for Ridge/RF and Ridge standardization; native missing handling for boosting.',
            'calendar_features': 'Origin month sine/cosine known at forecast issuance; no future weather.',
            'cpu_thread_limit':1,
            'external_source_features': str(external_features) if external_features else None,
            'external_source_sha256': source.sha256_file(external_features) if external_features else None,
            'external_policy': 'Never used for tuning or refitting; only targets absent from active observed district-months, conditional on unverified vertical datum.',
            'software': {'python': platform.python_version(), 'scikit_learn': sklearn.__version__, 'xgboost': xgboost.__version__},
            'test_exposure': 'No test performance consulted for this run selection. Historical periods were inspected in earlier audits; this is not a pristine prospective trial.'}


def validate(frame, output, plan):
    development = frame.loc[pd.to_datetime(frame.date) <= pd.Timestamp('2018-12-31')].copy()
    cases = build_cases(development)
    results = []
    for candidate in plan['candidates']:
        candidate_id = candidate['candidate_id']
        cache = output/'validation'/f'{candidate_id}.json'
        case_path = cache.with_suffix('.csv')
        if cache.exists() and case_path.exists():
            cached=json.loads(cache.read_text(encoding='utf-8'))
            if (cached.get('case_csv_sha256')!=source.sha256_file(case_path)
                    or any(cached.get(key)!=candidate[key] for key in candidate)):
                raise ValueError('Validation cache integrity differs from the locked candidate')
            results.append(cached)
            print(f'Reused validation cache {candidate_id}', flush=True)
            continue
        predictions = []
        for fold in FOLDS:
            train, rows = window_split(cases, fold)
            if train.empty or rows.empty:
                raise ValueError('Validation folds require real observed training and evaluation cases')
            estimator = fit_candidate(train, candidate)
            table = case_table(rows)
            table['prediction'] = predict_candidate(estimator, rows, candidate)
            table['fold'] = fold['fold']
            table['training_n'] = len(train)
            table['max_training_target'] = str(train.target_date.max().date())
            predictions.append(table)
            print(candidate_id, fold['fold'], f'train={len(train)}, paired={len(rows)}, RMSE={source.metrics(table.actual,table.prediction)["rmse_m"]:.6f}', flush=True)
        combined = pd.concat(predictions, ignore_index=True)
        if combined.case_id.duplicated().any():
            raise ValueError('Overlapping validation evaluation cases')
        result = {**candidate, 'summary': summarize_cases(combined, ['prediction', *BASELINES]),
                  'by_fold': {str(key): summarize_cases(part, ['prediction', *BASELINES])
                              for key, part in combined.groupby('fold', sort=True)}}
        csv_once(case_path, combined)
        result['case_csv_sha256']=source.sha256_file(case_path)
        write_once(cache, result)
        results.append(result)
    identities = {r['summary']['case_ids_sha256'] for r in results}
    if len(identities) != 1:
        raise ValueError('Candidates did not use identical validation cases')
    ranking = sorted(results, key=lambda r: (r['summary']['models']['prediction']['rmse_m'], r['candidate_id']))
    by_family = {family: next(r for r in ranking if r['family']==family) for family in FAMILIES}
    winner = ranking[0]
    baseline_metrics = winner['summary']['models']
    lock = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'protocol_sha256': source.sha256_file(output/'protocol.json'),
            'selected_ml': {k:winner[k] for k in ('candidate_id','family','parameters','target_form')},
            'selected_by_family': {family:{k:item[k] for k in ('candidate_id','family','parameters','target_form')}
                                   for family, item in by_family.items()},
            'validation_best_including_baselines': min(['prediction', *BASELINES],key=lambda n:baseline_metrics[n]['rmse_m']),
            'ranking': [{k:r[k] for k in ('candidate_id','family','parameters','target_form')} | {'metrics':r['summary']['models']['prediction']} for r in ranking],
            'test_predictions_created': False}
    if not (output/'selection_lock.json').exists():
        write_once(output/'selection_lock.json', lock)
    else:
        old=json.loads((output/'selection_lock.json').read_text())
        if old['selected_ml'] != lock['selected_ml']:
            raise ValueError('Locked selection differs; use a new experiment directory')
    return lock


def evaluate_final(frame, output, plan, lock, external_features=None):
    if lock['protocol_sha256'] != source.sha256_file(output/'protocol.json'):
        raise ValueError('Selection lock and protocol do not match')
    if (output/'test_results.json').exists():
        raise ValueError('Final test has already been evaluated; use saved results rather than retuning')
    primary = build_cases(frame)
    training, test = window_split(primary, FINAL)
    _, secondary = window_split(build_cases(frame, 'causal'), FINAL)
    cohorts = {'primary_observed_origin': test, 'secondary_causal_origin': secondary}
    if external_features:
        external = pd.read_csv(external_features, parse_dates=['date'])
        external_cases = build_cases(external)
        observed_keys = set(zip(frame.loc[source.observed_mask(frame),'district_id'],
                                pd.to_datetime(frame.loc[source.observed_mask(frame),'date'])))
        new_targets = [(row.district_id, row.target_date) not in observed_keys for row in external_cases.itertuples()]
        _, external_cases = window_split(external_cases.loc[new_targets], FINAL)
        cohorts['external_source_conditional'] = external_cases
    if not len(training) or not len(test):
        raise ValueError('Independent observed training and final cases are required')
    predictions = {key:case_table(rows) for key, rows in cohorts.items()}
    for family, settings in lock['selected_by_family'].items():
        estimator = fit_candidate(training, settings)
        for key, rows in cohorts.items():
            if len(rows):
                predictions[key][family] = predict_candidate(estimator, rows, settings)
        print(f'Final predictions: {family}, training labels={len(training)}', flush=True)
    results = {'selection_lock_sha256':source.sha256_file(output/'selection_lock.json'),
               'selected_ml':lock['selected_ml'], 'training_n':len(training),
               'max_training_target':str(training.target_date.max().date()), 'cohorts':{}}
    for key, table in predictions.items():
        if table.empty:
            results['cohorts'][key]={'n':0}
            continue
        names=[*BASELINES,*FAMILIES]
        report=summarize_cases(table,names)
        report['paired_district_bootstrap']={family:{baseline:paired_bootstrap(table,family,baseline)
                                                   for baseline in BASELINES} for family in FAMILIES}
        csv_once(output/f'{key}_predictions.csv',table)
        results['cohorts'][key]=report
    write_once(output/'test_results.json',results)
    return results


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['plan','validation','test','all'],default='plan')
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--external-features',type=Path)
    args=parser.parse_args(argv)
    output=candidate_output(args.output_dir)
    # CSV-only: a missing source cannot trigger a database fallback.
    if not (ROOT/'data/processed/features_matrix.csv').is_file():
        parser.error('Verified local feature CSV required; database access is disabled')
    frame=source.load_feature_matrix()
    plan=protocol(frame,args.external_features)
    if args.stage=='plan':
        print(json.dumps(plan,indent=2,allow_nan=False))
        return plan
    owned=ROOT/'reports/candidates'/output.relative_to(ROOT/'reports/candidates').parts[0]
    if output.exists() and not (output/'protocol.json').is_file():
        parser.error('Existing output without a matching protocol is refused')
    before=protected_snapshot(owned)
    if not output.exists():
        output.mkdir(parents=True)
        write_once(output/'protocol.json',plan)
        write_once(output/'protected_inputs.json',before)
    else:
        recorded=json.loads((output/'protocol.json').read_text())
        if source._json_hash(recorded)!=source._json_hash(plan):
            parser.error('Inputs/code/protocol changed; choose a new candidate directory')
        if json.loads((output/'protected_inputs.json').read_text()) != before:
            parser.error('Protected inputs or previous reports changed between stages')
    try:
        if args.stage in ('validation','all'):
            lock=validate(frame,output,plan)
            print('Locked validation winner:',lock['selected_ml'],flush=True)
        if args.stage in ('test','all'):
            path=output/'selection_lock.json'
            if not path.exists():
                parser.error('Run validation and freeze selection before test')
            results=evaluate_final(frame,output,plan,json.loads(path.read_text()),args.external_features)
            print(json.dumps({key:{'n':value['n'],'models':value.get('models')} for key,value in results['cohorts'].items()},indent=2),flush=True)
    finally:
        after=protected_snapshot(owned)
        if before!=after:
            raise RuntimeError('Protected inputs/reports changed during experiment')
        if not (output/'protected_inputs_verified.json').exists():
            write_once(output/'protected_inputs_verified.json',{'unchanged':True,'files':len(before)})


if __name__=='__main__':
    main()
