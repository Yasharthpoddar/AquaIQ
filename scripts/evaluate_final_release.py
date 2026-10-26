"""Compare added measurements without reselecting models on old holdout labels."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from models import climate_forecast_12m as climate
from models.xgboost_model import load_feature_matrix,sha256_file,_write_json
from scripts.evaluate_official_enrichment import predictions,metric

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'reports/final_release_20261026/diagnostic_protocol.json'


def summarize(rows):
    result={'cases':len(rows),'districts':int(rows.district_id.nunique()),
        'states':int(rows.district_id.str.split('-').str[0].nunique()),
        'origin_dates':sorted(rows.origin.unique()),'target_dates':sorted(rows.target_date.unique()),
        'parent':metric(rows.actual,rows.baseline),'candidate':metric(rows.actual,rows.candidate)}
    for name in ('persistence','seasonal'):
        paired=rows.loc[rows[name].notna()]
        if len(paired):result[name+'_paired']={'candidate':metric(paired.actual,paired.candidate),'baseline':metric(paired.actual,paired[name]),'districts':int(paired.district_id.nunique())}
    return result


def run(parent_directory,candidate_directory,output):
    output=Path(output)
    if output.exists():raise FileExistsError('Diagnostic output must be a new directory.')
    protocol=json.loads(PROTOCOL.read_text(encoding='utf-8'))
    frames=[load_feature_matrix(path) for path in (parent_directory,candidate_directory)]
    bundles=[climate.load_bundle(Path(path)/'frozen_bundle/checkpoint.json',expected_generation=frame.attrs['feature_generation_id']) for path,frame in zip((parent_directory,candidate_directory),frames)]
    if bundles[0][1]['model_sha256']!=bundles[1][1]['model_sha256']:raise ValueError('This diagnostic requires frozen identical model weights.')
    identity={'parent_csv_sha256':frames[0].attrs['feature_manifest']['feature_csv_sha256'],
        'candidate_csv_sha256':frames[1].attrs['feature_manifest']['feature_csv_sha256'],
        'model_sha256':bundles[0][1]['model_sha256'],'protocol_sha256':sha256_file(PROTOCOL)}
    # Keep fingerprints separately, avoiding repeated deep copies of large raw
    # source manifests through pandas operations. Numeric inputs are unchanged.
    for frame in frames:frame.attrs={'feature_generation_id':frame.attrs['feature_generation_id']}
    rows,cold=predictions(*frames,bundles,protocol['origins'])
    rows['age_group']=pd.cut(rows.age_candidate,[-1,3,12,36,np.inf],labels=['0-3','4-12','13-36','37+']).astype('string').fillna('no_local_history')
    output.mkdir(parents=True)
    rows.to_csv(output/'cases.csv',index=False);cold.to_csv(output/'cold_cases.csv',index=False)
    report={'protocol':protocol,'identity':identity,'overall':summarize(rows),
        'by_tier':{tier:summarize(g) for tier,g in rows.groupby('tier_candidate')},
        'by_horizon':{str(h):summarize(g) for h,g in rows.groupby('horizon')},
        'by_state':{state:summarize(g) for state,g in rows.groupby(rows.district_id.str.split('-').str[0])},
        'by_age':{str(age):summarize(g) for age,g in rows.groupby('age_group')},
        'by_origin':{origin:summarize(g) for origin,g in rows.groupby('origin')},
        'pseudo_cold':{name:metric(cold.actual,cold[name]) for name in ('regional_reference','global_reference','state_blocked_reference')},
        'all_target_histories_excluded':bool(cold.target_history_excluded.all()),
        'cases_sha256':sha256_file(output/'cases.csv'),'new_blind_evaluation':False,
        'model_or_interval_selection_performed':False}
    _write_json(output/'summary.json',report)
    print(json.dumps(report['overall'],indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent-directory',type=Path,required=True);p.add_argument('--candidate-directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.parent_directory,a.candidate_directory,a.output)
