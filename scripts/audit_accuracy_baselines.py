"""Reproduce historical serving scores before any new model development."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from models import accuracy_experiments as study, climate_forecast_12m as climate, tiered_forecast as tiered
from models.enriched_training_data import prepare_pairs
from models.xgboost_model import load_feature_matrix, sha256_file, _write_json

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT/'data/processed/enrichment/final_release_20261026_v3'
OLD = ROOT/'reports/retraining_20261027'
FROZEN = FEATURES/'frozen_bundle/checkpoint.json'
CURRENT = ROOT/'models/artifacts/enriched_retraining_20261027/checkpoint.json'


def protected_files():
    names = subprocess.check_output(['git','ls-files','models/artifacts','reports/retraining_20261027',
                                     'research','data_sources'],cwd=ROOT,text=True).splitlines()
    names += [str(p.relative_to(ROOT)).replace('\\','/') for p in FEATURES.rglob('*') if p.is_file()]
    names += ['reports/retraining_20261027/training/training_pairs.csv',
              'reports/retraining_20261027/retrospective/cases.csv']
    return {n:sha256_file(ROOT/n) for n in sorted(set(names))}


def load_inputs():
    frame = load_feature_matrix(FEATURES)
    identity = dict(frame.attrs)
    frame.attrs = {}
    original = load_feature_matrix()
    original.attrs = {}
    return frame, original, identity


def run(output):
    output = Path(output)
    if (output/'baseline_audit.json').exists():
        raise FileExistsError('Use a new versioned audit output.')
    output.mkdir(parents=True,exist_ok=True)
    protected = protected_files()
    _write_json(output/'protected_before.json',protected)
    frame, original, identity = load_inputs()
    generation = identity['feature_generation_id']
    bundles = [climate.load_bundle(p,expected_generation=generation) for p in (FROZEN,CURRENT)]
    assert bundles[0][1]['model_sha256']=='4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03'
    assert bundles[1][1]['model_sha256']=='e4e57de9f681b2f2702c9b86a00be06b04147123ecea0579f6abcf3cdc586192'
    print('Verified immutable model identities; independently resolving baseline observations.',flush=True)
    old = pd.read_csv(OLD/'retrospective/cases.csv',parse_dates=['origin','target_date'])
    cases = old.rename(columns={'origin':'origin_date'})
    resolved = study.baseline_cases(cases,frame)
    for name in ['persistence','seasonal']:
        np.testing.assert_allclose(resolved[name],cases[name],rtol=0,atol=1e-12,equal_nan=True)
    labels = study.observed_history(frame).set_index(['district_id','date']).gwl_current
    actual = labels.reindex(pd.MultiIndex.from_arrays([cases.district_id,cases.target_date])).to_numpy(float)
    np.testing.assert_allclose(actual,cases.actual,rtol=0,atol=1e-12)
    summary = json.loads((OLD/'retrospective/summary.json').read_text())
    panels = {'all':study.matched(resolved,['frozen','retrained']),
              'persistence':study.matched(resolved,['frozen','retrained','persistence']),
              'four_way':study.matched(resolved,['frozen','retrained','persistence','seasonal'])}
    for name,old_panel in [('all',summary['overall']),('persistence',summary['overall']['persistence_paired']),
                           ('four_way',summary['overall']['seasonal_paired'])]:
        for method,metrics in panels[name]['methods'].items():
            assert metrics['n']==old_panel[method]['n']
            for field in ['mae_m','rmse_m']:
                assert abs(metrics[field]-old_panel[method][field])<1e-12
    print('Exact historical aggregate scores reproduced from case records.',flush=True)
    # Replay actual public forecast fields for representative A/B/C districts,
    # including a stale December anchor and a large-error district.
    selected = []
    for tier in ['A','B','C']:
        ids = sorted(cases.loc[cases.tier.eq(tier),'district_id'].unique())[:1]
        selected.extend((did,origin) for did in ids for origin in ['2025-01-31','2025-12-31'])
    selected.extend([('GJ-Gandhinagar','2025-01-31'),('GJ-Gandhinagar','2025-12-31')])
    replay = []
    for did,origin in selected:
        cutoff = pd.Timestamp(origin)
        saved = cases.loc[cases.district_id.eq(did)&cases.origin_date.eq(cutoff)]
        if saved.empty:
            continue
        district = frame.loc[frame.district_id.eq(did)]
        reference = tiered.RegionalReference(frame,cutoff) if saved.iloc[0].tier!='A' else None
        row = {'district_id':did,'origin':origin,'tier':saved.iloc[0].tier}
        for name,bundle in zip(['frozen','retrained'],bundles):
            prediction = tiered.forecast_district(did,district,cutoff,generation,bundle,reference,calibration=None)
            h = int(saved.iloc[0].horizon)
            actual_output = prediction['forecast'][h-1]['predicted_gwl']
            assert actual_output==saved.iloc[0][name]
            row[name]={'public_predicted_gwl':actual_output,'anchor':prediction['estimated_current_gwl'],
                       'method':prediction['forecast_method'],'last_observed_date':prediction.get('last_observed_date')}
        replay.append(row)
    _write_json(output/'serving_replay.json',replay)
    same = resolved.loc[resolved.seasonal.notna()]
    assert (same.persistence==same.seasonal).all()
    assert (same.persistence_date==same.seasonal_date).all()
    # Derive diagnostics only from already inspected evaluation records.
    enriched = study.metadata(resolved,frame,original)
    enriched.to_csv(output/'historical_cases_with_traces.csv',index=False,lineterminator='\n')
    diagnostics = study.diagnostics(enriched,['frozen','retrained','persistence','seasonal'])
    _write_json(output/'historical_diagnostics.json',diagnostics)
    old_folds = []
    selection = json.loads((OLD/'training/selection.json').read_text())
    acceptance = json.loads((OLD/'acceptance.json').read_text())
    for fold in selection['fold_results']:
        path = OLD/'training'/fold['validation_cases_file']
        assert sha256_file(path)==fold['validation_cases_sha256']
        v = pd.read_csv(path,parse_dates=['origin_date','target_date'])
        audited = study.baseline_cases(v,frame)
        for name in ['persistence','seasonal']:
            np.testing.assert_allclose(v[name],audited[name],rtol=0,atol=1e-12,equal_nan=True)
        for method in ['frozen','retrained','persistence']:
            for field in ['mae_m','rmse_m','district_macro_mae_m']:
                assert abs(study.metric(v,method)[field]-fold['metrics'][method][field])<1e-12
        old_folds.append({'fold':fold['fold']['name'],'candidate':fold['candidate'],
                          'metrics':study.matched(v,['frozen','retrained','persistence','seasonal'])})
    _write_json(output/'historical_validation_reproduction.json',old_folds)
    print('Rebuilding causal observed pairs without January 2026 labels.',flush=True)
    prefix = frame.loc[frame.date.le('2025-01-31')].copy()
    prefix.attrs = identity
    pairs = prepare_pairs(prefix)
    pair_audit = pairs.attrs['pair_audit']
    pairs.attrs = {}
    old_pairs = pd.read_csv(OLD/'training/training_pairs.csv',parse_dates=['origin_date','target_date'])
    old_pairs = old_pairs.loc[old_pairs.target_date.le('2025-01-31')].reset_index(drop=True)
    pd.testing.assert_frame_equal(pairs.reset_index(drop=True),old_pairs,check_exact=False,rtol=1e-12,atol=1e-12)
    pair_path = output/'development_pairs.csv'
    pairs.to_csv(pair_path,index=False,lineterminator='\n')
    observed = study.observed_history(frame)
    folds = study.choose_folds(pairs)
    _write_json(output/'fold_availability.json',folds)
    audit = {'status':'reproduced','units':'m_bgl','target':'observed_target_minus_observed_origin',
        'old_summary_sha256':sha256_file(OLD/'retrospective/summary.json'),
        'old_cases_sha256':sha256_file(OLD/'retrospective/cases.csv'),
        'models':{n:b[1]['model_sha256'] for n,b in zip(['frozen','current'],bundles)},
        'old_protocol_sha256':sha256_file(OLD/'protocol.json'),
        'old_selection_sha256':sha256_file(OLD/'training/selection.json'),
        'old_acceptance_sha256':sha256_file(OLD/'acceptance.json'),
        'acceptance_location_note':'training/acceptance.json does not exist; acceptance.json is at the report root.',
        'old_acceptance_decision':acceptance['decision'],'panels':panels,
        'coverage':{n:{'available':int(resolved[n].notna().sum()),'missing':int(resolved[n].isna().sum()),
                       'districts':int(resolved.loc[resolved[n].notna(),'district_id'].nunique())} for n in ['persistence','seasonal']},
        'identical_baseline_cases':len(same),'identical_reference_dates':True,
        'reference_date_counts':same.persistence_date.dt.strftime('%Y-%m-%d').value_counts().to_dict(),
        'explanation':'Every scored target is January 2026. Every seasonal-supported district has January 2025 as both its exact previous-year observation and its latest eligible measurement at all twelve 2025 origins. No later 2025 measurements exist. Separate baseline definitions correctly coincide.',
        'serving_replay_cases':len(replay),'public_output_rounding_decimals':4,
        'baseline_semantics_note':'Independent persistence uses latest measured depth, unlike the embedded Tier A API persistence which uses an estimated current anchor across gaps. Existing external comparison correctly uses measured persistence.',
        'causal_pair_rebuild_matches':True,'pair_audit':pair_audit,
        'development_pairs_sha256':sha256_file(pair_path),'training_pairs':study.describe_pairs(pairs),
        'observed_target_counts_by_year':{str(k):int(v) for k,v in observed.groupby(observed.date.dt.year).size().items()},
        'observed_target_counts_by_month':observed.date.dt.strftime('%Y-%m').value_counts().sort_index().to_dict(),
        'production_changed':False,'january2026_used_for_selection':False,
        'command':f'python -B -m scripts.audit_accuracy_baselines --output {output.as_posix()}'}
    assert protected_files()==protected
    _write_json(output/'baseline_audit.json',audit)
    print(json.dumps({'status':'reproduced','four_way':panels['four_way'],'outer_folds':folds['outer']},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
