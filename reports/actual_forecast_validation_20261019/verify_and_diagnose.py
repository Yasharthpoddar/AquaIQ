"""Independent arithmetic, lineage and time checks; no training or inference."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(ROOT))
from models import xgboost_model as direct


def write_json(path, value):
    with path.open('x',encoding='utf-8') as handle:
        json.dump(value,handle,indent=2,allow_nan=False)


def write_csv(path, frame):
    with path.open('x',encoding='utf-8',newline='') as handle:
        frame.to_csv(handle,index=False)


def run(normalized,evaluation,output):
    normalized,evaluation,output=map(lambda p:Path(p).resolve(),[normalized,evaluation,output])
    if not all(p.is_relative_to(RUN) for p in [normalized,evaluation,output]) or output.exists():
        raise ValueError('Use research-only inputs and a new output directory')
    output.mkdir(exist_ok=False)
    frame=pd.read_csv(normalized/'research_features.csv',parse_dates=['date'])
    monthly=pd.read_csv(normalized/'district_monthly_observed.csv',parse_dates=['date'])
    observed=pd.read_csv(normalized/'normalized_well_observations.csv',parse_dates=['date','reported_observation_date'],dtype={'provider_well_id':str})
    table=pd.read_csv(evaluation/'case_inventory.csv',parse_dates=['date','target_date','seasonal_date'])
    summary=json.loads((evaluation/'metrics.json').read_text())
    checks=json.loads((evaluation/'leakage_and_eligibility.json').read_text())
    protocol=json.loads((RUN/'protocol.json').read_text())
    before=json.loads((RUN/'before.json').read_text())
    assert np.isfinite(observed.gwl_m_bgl).all() and observed.gwl_m_bgl.ge(0).all()
    # Independently recompute reported district means and equal weights.
    recomputed=observed.groupby(['district_id','date']).gwl_m_bgl.agg(['mean','size']).reset_index()
    joined=monthly.merge(recomputed,on=['district_id','date'],validate='one_to_one')
    assert len(joined)==len(monthly)
    assert np.allclose(joined.gwl,joined['mean'],rtol=1e-12,atol=1e-12)
    assert (joined.well_count==joined['size']).all()
    assert (table.target_date==table.date+pd.DateOffset(months=6)).all()
    assert (table.seasonal_date==table.target_date-pd.DateOffset(months=12)).all()
    indexed=monthly.set_index(['district_id','date']).gwl
    for reference,column in [('date','persistence'),('seasonal_date','seasonal_naive'),('target_date','actual')]:
        part=table.loc[table.reference_eligible]
        actual=indexed.reindex(pd.MultiIndex.from_arrays([part.district_id,part[reference]])).to_numpy()
        assert np.allclose(actual,part[column],rtol=1e-12,atol=1e-12)
    # Weather remains a copy of the existing verified causal feature generation.
    weather_path=ROOT/'data/processed/features_matrix.csv'
    assert direct.sha256_file(weather_path)==protocol['weather_source']['sha256']
    weather=direct.encode_crop_season(pd.read_csv(weather_path,parse_dates=['date']))
    w=[c for c in direct.CANONICAL_FEATURE_COLS if not c.startswith('gwl_')]
    paired=frame[['district_id','date',*w]].merge(weather[['district_id','date',*w]],on=['district_id','date'],suffixes=('_new','_old'),validate='one_to_one')
    assert len(paired)==len(frame)
    for c in w:
        assert np.allclose(paired[c+'_new'],paired[c+'_old'],equal_nan=True,rtol=1e-12,atol=1e-12)
    # Rebuild actual truncated histories; later GWL/weather cannot enter these prefixes.
    spec=importlib.util.spec_from_file_location('prepare_check',RUN/'prepare_research.py')
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    prefix_checks=[]
    for cutoff in ['2018-12-01','2023-07-01','2024-12-01']:
        rebuilt=adapter.build_research_features(monthly.loc[monthly.date<=cutoff],weather.loc[weather.date<=cutoff],end=cutoff)
        expected=frame.loc[frame.date<=cutoff].sort_values(['district_id','date'])
        assert len(rebuilt)==len(expected)
        for c in direct.CANONICAL_FEATURE_COLS:
            assert np.allclose(rebuilt[c],expected[c],equal_nan=True,rtol=1e-12,atol=1e-12), (cutoff,c)
        prefix_checks.append({'cutoff':cutoff,'rows':len(rebuilt),'all_12_features_match_full_generation':True})
    model_metrics=[];weighting=[]
    for cohort,report in summary.items():
        if not report['n']:continue
        part=table.loc[table[cohort]].copy()
        assert len(part)==report['n']
        names=list(report['models'])
        assert np.isfinite(part[['actual',*names]]).all().all()
        for name in names:
            error=part[name].to_numpy()-part.actual.to_numpy()
            mae=float(np.abs(error).mean());rmse=float(np.sqrt(np.square(error).mean()))
            assert abs(mae-report['models'][name]['mae_m'])<1e-10
            assert abs(rmse-report['models'][name]['rmse_m'])<1e-10
            model_metrics.append({'cohort':cohort,'model':name,'n':len(part),'districts':part.district_id.nunique(),
                **report['models'][name], 'rmse_minus_persistence_m':rmse-report['models']['persistence']['rmse_m'],
                'rmse_minus_seasonal_m':rmse-report['models']['seasonal_naive']['rmse_m'],
                'mae_minus_persistence_m':mae-report['models']['persistence']['mae_m'],
                'mae_minus_seasonal_m':mae-report['models']['seasonal_naive']['mae_m']})
            weighting.append({'cohort':cohort,'model':name,'weighting':'pooled','mae_m':mae,'rmse_m':rmse})
        for key,by in [('district_id','district_macro'),('calendar_month','calendar_month_macro'),('target_period','target_period_macro')]:
            groups=pd.read_csv(evaluation/f'{cohort}_{key}_metrics.csv')
            for name,values in groups.groupby('model'):
                weighting.append({'cohort':cohort,'model':name,'weighting':by,
                    'mae_m':float(values.mae_m.mean()),'rmse_m':float(values.rmse_m.mean())})
    write_csv(output/'comparison.csv',pd.DataFrame(model_metrics))
    write_csv(output/'weighting_comparison.csv',pd.DataFrame(weighting))
    observed['source_name_unresolved']=observed.source_name_district_id.isna()
    observed['depth_exceeds_well_depth']=observed.gwl_m_bgl.gt(observed.well_depth_m)
    grouped=observed.groupby(['district_id','date']).agg(wells=('provider_well_id','size'),
        name_disagreement_share=('source_name_differs_from_fixed_boundary','mean'),
        name_unresolved_share=('source_name_unresolved','mean'),
        depth_exceeds_well_share=('depth_exceeds_well_depth','mean'))
    case_qc=table[['case_id','district_id','date','target_date','seasonal_date','primary_common','primary_native','secondary_native']].copy()
    for tag,column in [('origin','date'),('target','target_date'),('seasonal','seasonal_date')]:
        part=grouped.reset_index().rename(columns={'date':column,**{c:tag+'_'+c for c in grouped.columns}})
        case_qc=case_qc.merge(part,on=['district_id',column],how='left',validate='many_to_one')
    write_csv(output/'case_mapping_and_depth_qc.csv',case_qc)
    qc_summary={}
    for cohort in ['primary_common','primary_native','secondary_native']:
        part=table.loc[table[cohort]]
        mapped=case_qc.loc[case_qc[cohort]]
        qc_summary[cohort]={'n':len(part),'identical_origin_target_panels':int(part.identical_origin_target_panels.sum()),
            'identical_all_three_panels':int(part.identical_all_three_panels.sum()),
            'median_origin_target_jaccard':float(part.origin_target_jaccard.median()),
            'min_origin_target_jaccard':float(part.origin_target_jaccard.min()),
            'targets_equal_persistence':int(part.actual.eq(part.persistence).sum()),
            'targets_equal_seasonal':int(part.actual.eq(part.seasonal_naive).sum()),
            'cases_with_name_coordinate_disagreement_in_origin_or_target':int((mapped.origin_name_disagreement_share.gt(0)|mapped.target_name_disagreement_share.gt(0)).sum()),
            'mean_target_disagreement_well_share':float(mapped.target_name_disagreement_share.mean()),
            'mean_target_unresolved_name_well_share':float(mapped.target_name_unresolved_share.mean()),
            'cases_with_depth_exceeds_well_metadata_in_target':int(mapped.target_depth_exceeds_well_share.gt(0).sum())}
    write_json(output/'panel_and_mapping_summary.json',qc_summary)
    # Earliest post-month-close issue is only a conditional lower bound; not an actual issue.
    timeline=table.loc[table.reference_eligible,['case_id','date','target_date','target_first_reported_date','target_last_reported_date']].copy()
    timeline['earliest_if_complete_origin_weather_no_latency']=timeline.date+pd.offsets.MonthBegin(1)
    timeline['reported_target_minus_earliest_issue_days']=(pd.to_datetime(timeline.target_first_reported_date)-timeline.earliest_if_complete_origin_weather_no_latency).dt.days
    timeline['actual_issue_time']=None;timeline['actual_target_acquisition_time']=None
    timeline['interpretation']='Conditional calendar bound only; reported dates are not certified acquisition times, and provider latency is unknown.'
    write_csv(output/'conditional_timing.csv',timeline)
    # QC correction should never be concealed or mistaken for tuning.
    old=RUN/'evaluation'
    if old.exists() and old!=evaluation:
        previous=pd.read_csv(old/'case_inventory.csv')
        numeric_same={}
        for name in ['actual','persistence','seasonal_naive','xgb_expanding','linear_expanding','xgb_active_frozen','hgb_locked_historical']:
            numeric_same[name]=bool(np.allclose(previous[name],table[name],equal_nan=True,rtol=0,atol=0))
        write_json(output/'qc_run_comparison.json',{'first_run_preserved':'evaluation/','corrected_run':evaluation.name,
            'reason':'Nullable numeric missing values were not rejected in first adapter; corrected before final evidence, without changing settings or selecting on results.',
            'identical_case_order':previous.case_id.tolist()==table.case_id.tolist(),'prediction_and_target_values_bitwise_equal':numeric_same})
    unchanged=[];changes=[]
    for relative,metadata in before['files'].items():
        path=ROOT/relative
        current=direct.sha256_file(path) if path.is_file() else None
        if current==metadata['sha256']:
            unchanged.append(relative)
        else:
            changes.append({'path':relative,'before_sha256':metadata['sha256'],'after_sha256':current})
    write_json(output/'verification.json',{'pre_existing_files_checked':len(before['files']),
        'pre_existing_files_unchanged':len(unchanged),'preservation_status':'pass' if not changes else 'FAILED: unexpected pre-existing file changes',
        'unexpected_pre_existing_changes':changes,'attribution':'No restoration attempted; writer is not established by this evidence.',
        'observed_targets_and_exact_both_baselines_recomputed':True,'district_means_recomputed':True,
        'weather_numeric_values_and_missingness_unchanged':True,'real_history_prefix_rebuilds':prefix_checks,
        'all_saved_metrics_independently_recomputed':True,'calendar_causal_checks':'pass',
        'historical_vintage_and_actual_issuance_checks':'unresolved; no historical release/receipt/revision archive or authenticated acquisition times',
        'prospective_performance':'unmeasured','nationwide_generalization':'unestablished',
        'geographic_source_quality':'Serious unresolved named-location/coordinate conflicts; conditional district results cannot establish trustworthy location-specific skill.'})
    print(json.dumps({'metrics':'independently reproduced','protected_files_unchanged':len(unchanged),
        'unexpected_pre_existing_changes':changes,'panel_and_mapping_summary':qc_summary},indent=2))
    return 2 if changes else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized',required=True,type=Path)
    parser.add_argument('--evaluation',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args();raise SystemExit(run(args.normalized,args.evaluation,args.output_dir))
