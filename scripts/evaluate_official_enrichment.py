"""Paired, calendar-aligned replay with a sealed final phase and frozen weights."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from db.connection import finite_json
from models import climate_forecast_12m as climate
from models.district_registry import get_registry
from models.tiered_forecast import RegionalReference, forecast_district, observations, VERSION
from models.xgboost_model import load_feature_matrix, sha256_file, _write_json
from preprocessing.official_enrichment import prove_frozen_compatibility

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'reports/data_enrichment/evaluation_protocol.json'
SEALED_CODE = ('scripts/evaluate_official_enrichment.py', 'models/tiered_forecast.py',
    'models/climate_forecast_12m.py', 'models/climate_forecast.py', 'models/climate_inputs.py',
    'models/monthly_projection.py', 'models/ensemble.py', 'models/xgboost_model.py',
    'models/district_registry.py', 'preprocessing/official_enrichment.py',
    'preprocessing/pipeline.py', 'preprocessing/features.py')


def code_identity():
    # Git checkouts can translate LF to CRLF on Windows without changing code.
    # Bind normalized UTF-8 source text so only that representation difference
    # is portable; all tokens, whitespace and comments still participate.
    files = {name:hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode('utf-8')).hexdigest()
             for name in SEALED_CODE}
    return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()


def card_identity(card):
    return hashlib.sha256(json.dumps(card,sort_keys=True,allow_nan=False).encode()).hexdigest()


def metric(actual, predicted):
    error = np.asarray(actual, float) - np.asarray(predicted, float)
    if not len(error) or not np.isfinite(error).all():
        raise ValueError('Paired metrics require nonempty finite actual/predicted values.')
    return {'n': len(error), 'mae_m': float(np.abs(error).mean()), 'rmse_m': float(np.sqrt(np.mean(error**2)))}


def paired_summary(part):
    result = {'cases': len(part), 'districts': part.district_id.nunique(),
        'origins': part.origin.nunique(), 'candidate': metric(part.actual, part.candidate),
        'unchanged_inputs': metric(part.actual, part.baseline)}
    result['paired_mae_change_m'] = result['candidate']['mae_m'] - result['unchanged_inputs']['mae_m']
    for name in ('persistence', 'seasonal'):
        subset = part.loc[part[name].notna()]
        if len(subset):
            result[name + '_paired'] = {'candidate': metric(subset.actual, subset.candidate),
                'baseline': metric(subset.actual, subset[name]), 'districts': subset.district_id.nunique()}
    for name in ('candidate', 'baseline'):
        subset = part.loc[part[name + '_radius'].notna()]
        if len(subset):
            result[name + '_ranges'] = {'n': len(subset), 'districts': subset.district_id.nunique(),
                'empirical_coverage': float((np.abs(subset.actual-subset[name]) <= subset[name+'_radius']).mean()),
                'nominal_calibration_quantile': .9}
    return finite_json(result)


def build_calibration(table, frame, bundle):
    radii, counts = {}, {}
    for (tier, horizon), rows in table.groupby(['tier_candidate', 'horizon']):
        radii.setdefault(tier, {})[str(horizon)] = float(np.quantile(np.abs(rows.actual-rows.candidate), .9, method='higher'))
        counts.setdefault(tier, {})[str(horizon)] = {'n': len(rows), 'districts': rows.district_id.nunique()}
    return {'pipeline_version': VERSION, 'calibration_id': hashlib.sha256(table.to_csv(index=False).encode()).hexdigest(),
        'max_calibration_target': table.target_date.max(), 'nominal_coverage': .9, 'radii_m': radii, 'sample_counts': counts,
        'feature_generation_id': frame.attrs['feature_generation_id'],
        'feature_data_sha256': frame.attrs['feature_manifest']['feature_csv_sha256'],
        'xgboost_sha256': bundle[1]['model_sha256'], 'policy': 'Fixed pre-evaluation origins, 90th empirical absolute residual quantile; unsupported horizons unavailable.'}


def radii_for(table, version):
    return {(tier, int(h)): float(np.quantile(np.abs(rows.actual-rows[version]), .9, method='higher'))
        for (tier,h), rows in table.groupby(['tier_' + version, 'horizon'])}


def predictions(base, candidate, bundles, origins):
    registry = [row['district_id'] for row in get_registry()]
    groups = [{d: g for d,g in frame.groupby('district_id')} for frame in (base, candidate)]
    for group in groups:
        for district in group.values():
            district.attrs = {}
    labels = candidate.loc[candidate.is_observed].set_index(['district_id', 'date']).gwl_current
    records, cold = [], []
    for cutoff in origins:
        cutoff = pd.Timestamp(cutoff)
        origin = cutoff.to_period('M').to_timestamp()
        targets = pd.date_range(origin+pd.offsets.MonthBegin(1), periods=12, freq='MS')
        refs = [RegionalReference(frame, cutoff) for frame in (base, candidate)]
        for index, did in enumerate(registry):
            if index and index % 100 == 0:
                print(f'  {cutoff.date()}: checked {index}/{len(registry)} districts', flush=True)
            available = [(h, month, float(labels.loc[(did, month)])) for h,month in enumerate(targets,1) if (did,month) in labels.index]
            if not available:
                continue
            results = [forecast_district(did, group.get(did, frame.iloc[:0]), cutoff,
                frame.attrs['feature_generation_id'], bundle, ref)
                for frame, group, bundle, ref in zip((base, candidate), groups, bundles, refs)]
            local = observations(groups[1].get(did, candidate.iloc[:0]), cutoff)
            cold_values, donor_meta = refs[1].predict(did, targets, local.iloc[:0])
            # Explicit out-of-state donor panel; no target history or model weights.
            others = refs[1].annual.index[~refs[1].annual.index.str.startswith(did[:3])]
            for h, month, actual in available:
                previous = local.loc[local.date.eq(month-pd.DateOffset(years=1))]
                state_blocked = refs[1].monthly.reindex(others).get(month.month, pd.Series(np.nan, index=others)).fillna(refs[1].annual.reindex(others))
                global_values, _ = refs[1].distribution(did, month.month, global_only=True)
                records.append(dict(district_id=did, origin=cutoff.date().isoformat(), target_date=month.date().isoformat(), horizon=h,
                    actual=actual, baseline=results[0]['forecast'][h-1]['predicted_gwl'], candidate=results[1]['forecast'][h-1]['predicted_gwl'],
                    tier_baseline=results[0]['evidence_tier'], tier_candidate=results[1]['evidence_tier'],
                    observations_candidate=len(local), age_candidate=results[1]['data_age_months'],
                    persistence=float(local.iloc[-1].gwl_current) if len(local) else None,
                    seasonal=float(previous.iloc[0].gwl_current) if len(previous) else None))
                cold.append(dict(district_id=did, origin=cutoff.date().isoformat(), target_date=month.date().isoformat(), horizon=h,
                    actual=actual, regional_reference=float(cold_values[h-1]), global_reference=float(np.median(global_values)),
                    state_blocked_reference=float(state_blocked.median()) if len(state_blocked) else None,
                    target_history_excluded=donor_meta[h-1]['target_district_excluded']))
        print(f'Finished paired replay {cutoff.date()}: {len(records)} cases', flush=True)
    if not records:
        raise ValueError('No genuinely observed paired targets.')
    return pd.DataFrame(records), pd.DataFrame(cold)


def run(candidate_directory, output, *, phase):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    protocol_sha = sha256_file(PROTOCOL)
    base = load_feature_matrix()
    candidate = load_feature_matrix(candidate_directory)
    bundles = [climate.load_bundle(expected_generation=base.attrs['feature_generation_id']),
        climate.load_bundle(Path(candidate_directory)/'frozen_bundle/checkpoint.json', expected_generation=candidate.attrs['feature_generation_id'])]
    proof = prove_frozen_compatibility(base, candidate, bundles[0][1]['train_target_cutoff'])
    if bundles[0][1]['model_sha256'] != bundles[1][1]['model_sha256']:
        raise ValueError('Comparison requires identical frozen weights.')
    identity = {'protocol_sha256': protocol_sha, 'baseline_feature_sha256': base.attrs['feature_manifest']['feature_csv_sha256'],
        'candidate_feature_sha256': candidate.attrs['feature_manifest']['feature_csv_sha256'], 'model_sha256': bundles[0][1]['model_sha256'],
        'predictive_and_evaluation_code_sha256':code_identity(),
        'baseline_card_sha256':card_identity(bundles[0][1]), 'candidate_card_sha256':card_identity(bundles[1][1])}
    selection_path = output/'selection.json'
    if phase == 'development':
        if selection_path.exists():
            raise ValueError('Development decision already sealed; use a new output directory.')
        calibration, _ = predictions(base, candidate, bundles, protocol['calibration_origins'])
        calibration.to_csv(output/'calibration_cases.csv', index=False)
        card = build_calibration(calibration, candidate, bundles[1])
        _write_json(output/'calibration.json', card)
        _write_json(output/'baseline_radii.json', {f'{tier}:{h}': r for (tier,h),r in radii_for(calibration,'baseline').items()})
        origins = protocol['development_origins']
    else:
        decision = json.loads(selection_path.read_text(encoding='utf-8'))
        if decision['identity'] != identity:
            raise ValueError('Final evaluation inputs/protocol differ from the sealed development decision.')
        if decision['calibration_sha256'] != sha256_file(output/'calibration.json'):
            raise ValueError('Calibration changed after selection.')
        calibration = pd.read_csv(output/'calibration_cases.csv')
        if sha256_file(output/'calibration_cases.csv') != decision['calibration_cases_sha256']:
            raise ValueError('Calibration cases changed after selection.')
        origins = protocol['final_origins']
    if pd.Timestamp(calibration.target_date.max()) >= min(pd.Timestamp(o).to_period('M').to_timestamp() for o in origins):
        raise ValueError('Calibration target must precede evaluation origin month.')
    table, cold = predictions(base, candidate, bundles, origins)
    for version in ('candidate', 'baseline'):
        radii = radii_for(calibration, version)
        table[version+'_radius'] = [radii.get((getattr(row,'tier_'+version), int(row.horizon)), np.nan) for row in table.itertuples()]
    table['age_group'] = pd.cut(table.age_candidate, [-1,3,12,36,np.inf], labels=['0-3','4-12','13-36','37+']).astype('string').fillna('no_local_history')
    table.to_csv(output/(phase+'_cases.csv'), index=False)
    cold.to_csv(output/(phase+'_cold_cases.csv'), index=False)
    report = {'phase': phase, 'identity': identity, 'protocol': protocol, 'frozen_compatibility': proof,
        'overall': paired_summary(table), 'by_tier': {tier:paired_summary(g) for tier,g in table.groupby('tier_candidate')},
        'by_horizon': {str(h):paired_summary(g) for h,g in table.groupby('horizon')},
        'by_age': {str(age):paired_summary(g) for age,g in table.groupby('age_group')},
        'by_origin': {str(o):paired_summary(g) for o,g in table.groupby('origin')},
        'by_district': {str(d):paired_summary(g) for d,g in table.groupby('district_id')},
        'natural_sparse': paired_summary(table.loc[table.observations_candidate.between(1,23)]) if table.observations_candidate.between(1,23).any() else None,
        'pseudo_cold': {name: metric(cold.actual, cold[name]) for name in ('regional_reference','global_reference','state_blocked_reference')},
        'all_cold_targets_excluded': bool(cold.target_history_excluded.all()),
        'cases_sha256': sha256_file(output/(phase+'_cases.csv'))}
    if phase == 'development':
        selected = report['overall']['candidate']['mae_m'] <= report['overall']['unchanged_inputs']['mae_m']
        decision = {'identity': identity, 'candidate_selected': bool(selected),
            'selection_basis': 'Predeclared development paired MAE; final labels were not evaluated.',
            'development_metrics': report['overall'], 'calibration_sha256':sha256_file(output/'calibration.json'),
            'calibration_cases_sha256':sha256_file(output/'calibration_cases.csv')}
        _write_json(selection_path, decision)
    else:
        report['sealed_selection'] = decision
    _write_json(output/(phase+'.json'), finite_json(report))
    print(json.dumps(finite_json({k:report[k] for k in ('phase','overall','by_tier','natural_sparse','pseudo_cold')}), indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['development','final'], required=True)
    args = parser.parse_args()
    run(args.candidate_directory, args.output, phase=args.phase)
