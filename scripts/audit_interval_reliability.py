"""Audit unchanged historical bands; never refit radii or optimize on holdout.

Report coverage jointly with width and the negatively oriented interval score
of Gneiting & Raftery (2007), equation 43. Samples are dependent retrospective
district-month cases, so fractions are descriptive and not local probabilities.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from models.district_registry import get_registry
from models.interval_evidence import POLICY_VERSION, MIN_CALIBRATION_DISTRICTS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALUATION = ROOT/'reports/data_enrichment/final_evaluation'
SCORE_SOURCE = 'https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def interval_score(actual, lower, upper, *, alpha=.1):
    actual, lower, upper = map(lambda value:np.asarray(value,dtype=float), (actual,lower,upper))
    if (actual.shape != lower.shape or lower.shape != upper.shape or not 0<alpha<1
            or not np.isfinite(actual).all() or not np.isfinite(lower).all() or not np.isfinite(upper).all()
            or (lower>upper).any()):
        raise ValueError('Interval score needs aligned finite observations and ordered bounds.')
    return upper-lower + 2/alpha*np.maximum(lower-actual,0) + 2/alpha*np.maximum(actual-upper,0)


def validate_cases(table):
    required = {'district_id','origin','target_date','horizon','actual','candidate','baseline',
        'tier_candidate','tier_baseline','age_candidate','observations_candidate'}
    if required-set(table) or table.empty or table.duplicated(['district_id','origin','horizon']).any():
        raise ValueError('Evaluation cases need nonempty unique provenance and method keys.')
    table = table.copy()
    for col in ('origin','target_date'):
        table[col] = pd.to_datetime(table[col],format='%Y-%m-%d',errors='raise')
    expected = [origin.to_period('M').to_timestamp()+pd.DateOffset(months=int(h)) for origin,h in zip(table.origin,table.horizon)]
    if (not table.target_date.dt.is_month_start.all() or not table.target_date.eq(expected).all()
            or not table.horizon.between(1,12).all() or table.horizon.mod(1).ne(0).any()
            or not np.isfinite(table[['actual','candidate','baseline']]).all().all()
            or table[['actual','candidate','baseline']].lt(0).any().any()
            or not table.tier_candidate.isin(['A','B','C','D']).all()):
        raise ValueError('Invalid units, finite targets or calendar horizon alignment.')
    registry={r['district_id']:r['state_id'] for r in get_registry()}
    if set(table.district_id)-set(registry):
        raise ValueError('Evaluation contains an unregistered district.')
    table['state_id'] = table.district_id.map(registry)
    table['age_group'] = pd.cut(table.age_candidate,[-1,3,12,36,np.inf],labels=['0-3','4-12','13-36','37+']).astype('string').fillna('no_local_history')
    return table


def attach_original_bands(table, calibration, *, version='candidate'):
    table=table.copy()
    if version=='candidate':
        radius_by_tier=calibration['radii_m']
    else:
        radius_by_tier=calibration
    radii=[radius_by_tier.get(tier,{}).get(str(h),np.nan) for tier,h in zip(table['tier_'+version],table.horizon)]
    table[version+'_radius']=radii
    radius=pd.to_numeric(table[version+'_radius'],errors='coerce')
    if np.isinf(radius).any() or radius.dropna().lt(0).any():
        raise ValueError('Invalid historical radius; audit cannot repair it.')
    table[version+'_lower']=np.maximum(0,table[version]-radius)
    table[version+'_upper']=table[version]+radius
    if version=='candidate':
        counts=calibration.get('sample_counts',{})
        table['calibration_districts']=[counts.get(tier,{}).get(str(h),{}).get('districts',0) for tier,h in zip(table.tier_candidate,table.horizon)]
        table['tail_support'] = table.calibration_districts.ge(MIN_CALIBRATION_DISTRICTS)
    return table


def panel_dates(table):
    return {'cases':len(table),'distinct_districts':table.district_id.nunique(),
        'distinct_states':table.state_id.nunique(), 'distinct_origins':table.origin.nunique(),
        'distinct_target_dates':table.target_date.nunique(),
        'origin_start':str(table.origin.min().date()),'origin_end':str(table.origin.max().date()),
        'target_start':str(table.target_date.min().date()),'target_end':str(table.target_date.max().date())}


def band_summary(table, *, version='candidate'):
    result=panel_dates(table)
    error=table[version]-table.actual
    result.update(mae_m=float(np.abs(error).mean()),rmse_m=float(np.sqrt(np.mean(error**2))))
    bands=table.loc[table[version+'_radius'].notna()]
    result['band_cases']=len(bands)
    result['unavailable_band_cases']=len(table)-len(bands)
    result['local_coverage_claim']=False
    if bands.empty:
        return result
    lower,upper=bands[version+'_lower'],bands[version+'_upper']
    covered=bands.actual.between(lower,upper)
    result.update(covered_cases=int(covered.sum()),case_fraction_covered=float(covered.mean()),
        band_districts=bands.district_id.nunique(),mean_width_m=float((upper-lower).mean()),
        mean_interval_score_m=float(interval_score(bands.actual,lower,upper).mean()),
        mean_miss_distance_m=float((np.maximum(lower-bands.actual,0)+np.maximum(bands.actual-upper,0)).mean()),
        target_coverage=.9,
        status='empirical_undercovered' if covered.mean()<.9 else 'historical_reference_only',
        band_panel_dates=panel_dates(bands))
    return result


def grouped(table, column):
    return {str(key):band_summary(group) for key,group in table.groupby(column,sort=True)}


def audit(evaluation_dir, output, *, evidence_output=None, report_date=None):
    evaluation_dir,output=Path(evaluation_dir),Path(output)
    card_path=evaluation_dir/'calibration.json'
    card=json.loads(card_path.read_text(encoding='utf-8'))
    calibration=validate_cases(pd.read_csv(evaluation_dir/'calibration_cases.csv'))
    reports={}
    hashes={'calibration':sha(card_path),'calibration_cases':sha(evaluation_dir/'calibration_cases.csv')}
    for phase in ('development','final'):
        path=evaluation_dir/(phase+'_cases.csv')
        original_report=json.loads((evaluation_dir/(phase+'.json')).read_text(encoding='utf-8'))
        if sha(path)!=original_report['cases_sha256']:
            raise ValueError('Evaluation case checksum differs from saved report.')
        hashes[phase+'_cases']=sha(path)
        table=validate_cases(pd.read_csv(path))
        if calibration.target_date.max()>=table.origin.min().to_period('M').to_timestamp():
            raise ValueError('Calibration targets overlap evaluation origin months.')
        raw_radius=table.candidate_radius.copy()
        table=attach_original_bands(table,card)
        if not np.allclose(raw_radius,table.candidate_radius,equal_nan=True,rtol=0,atol=1e-12):
            raise ValueError('Saved radii differ from the frozen calibration; no recalibration permitted.')
        baseline_card=json.loads((evaluation_dir/'baseline_radii.json').read_text(encoding='utf-8'))
        baseline_radii={}
        for key,radius in baseline_card.items():
            tier,h=key.split(':');baseline_radii.setdefault(tier,{})[h]=radius
        table=attach_original_bands(table,baseline_radii,version='baseline')
        supported=table.loc[table.tail_support & table.candidate_radius.notna()]
        reports[phase]={'original_bands':band_summary(table),'unchanged_input_bands':band_summary(table,version='baseline'),
            'by_tier':grouped(table,'tier_candidate'),'by_horizon':grouped(table,'horizon'),
            'by_tier_horizon':{tier:grouped(group,'horizon') for tier,group in table.groupby('tier_candidate')},
            'by_state':grouped(table,'state_id'),'by_origin':grouped(table,'origin'),
            'by_observation_age':grouped(table,'age_group'),
            'tail_supported_display_subset':band_summary(supported) if len(supported) else None,
            'withheld_band_cases':int((table.candidate_radius.notna() & ~table.tail_support).sum()),
            'display_subset_note':'Withholding does not recalibrate or widen any radius. Its coverage is a changed subset, not an improved accuracy claim.'}
    final=pd.read_csv(evaluation_dir/'final_cases.csv')
    cfinal=final[final.tier_candidate.eq('C')]
    ccal=calibration[calibration.tier_candidate.eq('C')]
    tier_evidence={}
    for tier,values in reports['final']['by_tier'].items():
        tier_evidence[tier]={**values,'by_horizon':reports['final']['by_tier_horizon'][tier]}
    report={'schema_version':1,'report_date':report_date or date.today().isoformat(),
        'policy_version':POLICY_VERSION,'source_hashes':hashes,
        'point_predictions_changed':False,'calibration_radii_changed':False,'final_labels_used_to_tune':False,
        'minimum_distinct_calibration_districts':MIN_CALIBRATION_DISTRICTS,
        'display_policy':'At least ten distinct calibration districts for a 90th-percentile band: one expected tail case at best; not a coverage guarantee. Fixed from calibration tail resolution, not final errors.',
        'interval_score':{'formula':'(U-L) + (2/alpha)*max(L-y,0) + (2/alpha)*max(y-U,0)',
            'alpha':.1,'direction':'lower_is_better','units':'metres','source':SCORE_SOURCE,
            'interpretation':'Proper central-interval diagnostic of width and misses; reporting it does not establish calibration.'},
        'calibration_panel':panel_dates(calibration),'calibration_counts':card['sample_counts'],
        'phases':reports,
        'zero_history_diagnosis':{'final_cases':len(cfinal),'final_districts':cfinal.district_id.nunique(),
            'final_horizons':sorted(cfinal.horizon.unique().tolist()),
            'calibration_districts_by_horizon':{str(h):g.district_id.nunique() for h,g in ccal.groupby('horizon')},
            'm12_calibration_districts':ccal.loc[ccal.horizon.eq(12),'district_id'].unique().tolist(),
            'final_actual_depth_range_m':[float(cfinal.actual.min()),float(cfinal.actual.max())],
            'reason':'All final C cases are M+12; its radius comes from one calibration district/target. Other C horizons have 1-6 districts. This tiny, geographically different calibration panel is consistent with poor transfer and cannot support local probability claims; the audit does not establish a unique causal mechanism.',
            'corrective_action':'Withhold unsupported numerical bands; keep all twelve labelled regional/global point references unchanged. Acquire new independent local evidence, not post-holdout band widening.'},
        'limitations':['Dependent and overlapping historical cases; fractions are descriptive, not independent binomial coverage estimates.',
            'Small state/horizon panels are reported with denominators and dates, never as district-specific calibrated probabilities.',
            'No wider radius, new quantile, model, threshold or method was selected using final residuals.',
            'The original previously inspected holdout cannot establish new prospective reliability.']}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    if evidence_output:
        evidence={'schema_version':1,'policy_version':POLICY_VERSION,'report_date':report['report_date'],
            'feature_generation_id':card['feature_generation_id'],'xgboost_sha256':card['xgboost_sha256'],
            'calibration_id':card['calibration_id'],
            'max_evaluation_target':reports['final']['original_bands']['target_end'],
            'audit_sha256':sha(output),'source_hashes':hashes,'tiers':tier_evidence,
            'scope':'Descriptive retrospective evaluation of pooled cases; no local or present-period coverage guarantee.'}
        evidence_path=Path(evidence_output)
        evidence_path.parent.mkdir(parents=True,exist_ok=True)
        evidence_path.write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'original_final':reports['final']['original_bands'],
        'zero_history':report['zero_history_diagnosis'],'point_predictions_changed':False,'radii_changed':False},indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation-dir',type=Path,default=DEFAULT_EVALUATION)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--evidence-output',type=Path)
    p.add_argument('--report-date');args=p.parse_args()
    audit(args.evaluation_dir,args.output,evidence_output=args.evidence_output,report_date=args.report_date)
