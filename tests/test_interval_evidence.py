"""Unchanged residuals, evidence identities, insufficient tails and honest status."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from models import interval_evidence as bands
from scripts import audit_interval_reliability as audit


def result(tier='A'):
    return {'district_id':'HR-A','evidence_tier':tier,'observation_count':0 if tier=='C' else 30,
        'forecast':[{'horizon':h,'predicted_gwl':float(h),'delta_from_current_m':float(h-1)} for h in range(1,13)]}


def calibration(tier='A',districts=30):
    return {'feature_generation_id':'fixture','xgboost_sha256':'model','calibration_id':'calibration',
        'max_calibration_target':'2022-07-01','nominal_coverage':.9,
        'radii_m':{tier:{str(h):2. for h in range(1,13)}},
        'sample_counts':{tier:{str(h):{'n':districts,'districts':districts} for h in range(1,13)}}}


def evidence():
    return {'schema_version':1,'policy_version':bands.POLICY_VERSION,
        'report_date':'2026-10-26','max_evaluation_target':'2026-01-01',
        'feature_generation_id':'fixture','xgboost_sha256':'model','calibration_id':'calibration',
        'tiers':{'A':{'cases':731,'band_cases':731,'band_districts':543,'covered_cases':598,
            'case_fraction_covered':598/731,'by_horizon':{'1':{'band_cases':30,'band_districts':25,'case_fraction_covered':.8}}}}}


@pytest.mark.parametrize('count',[0,1,6,9])
def test_thin_calibration_withholds_all_bounds_but_preserves_every_point(count):
    point=result('C');old=deepcopy(point)
    point['forecast'][0].update(lower_gwl=0.,upper_gwl=9.)  # stale partial band
    card=calibration('C',count);frozen=deepcopy(card)
    revised=bands.attach_error_bands(point,card,'2026-10-26',evidence=evidence())
    assert len(revised['forecast'])==12 and revised['observation_count']==0
    assert revised['uncertainty']['status']=='unavailable'
    assert all(r['interval_status']=='unavailable' and 'lower_gwl' not in r and 'upper_gwl' not in r for r in revised['forecast'])
    assert [r['predicted_gwl'] for r in revised['forecast']]==[r['predicted_gwl'] for r in old['forecast']]
    assert card==frozen


def test_ten_district_boundary_is_explicit_not_floating_quantile_rounding():
    assert bands.MIN_CALIBRATION_DISTRICTS==10
    value=bands.attach_error_bands(result(),calibration(districts=10),'2026-10-26')
    assert value['uncertainty']['available_horizons']==list(range(1,13))
    assert value['forecast'][0]['upper_gwl']==3.


def test_matching_undercoverage_has_denominators_and_never_claims_calibrated():
    value=bands.attach_error_bands(result(),calibration(),'2026-10-26',evidence=evidence())
    assert value['uncertainty']['status']=='empirical_undercovered'
    assert value['uncertainty']['historical_validation']['band_cases']==731
    assert value['uncertainty']['local_coverage_guarantee'] is False
    assert value['forecast'][0]['interval_status']=='empirical_undercovered'
    assert value['forecast'][1]['interval_status']=='historical_reference_only'  # no evaluated second horizon
    assert 'nominal_coverage' not in value['uncertainty']
    assert value['forecast'][0]['lower_gwl']==0.
    bands.validate_disclosure(value)


@pytest.mark.parametrize('key,value',[('feature_generation_id','new'),('xgboost_sha256','other'),
    ('calibration_id','other'),('report_date','2027-01-01'),('max_evaluation_target','2027-01-01')])
def test_mismatched_or_future_evaluation_is_not_applied_to_current_data(key,value):
    ev=evidence();ev[key]=value
    point=bands.attach_error_bands(result(),calibration(),'2026-10-26',evidence=ev)
    assert point['uncertainty']['status']=='historical_reference_only'
    assert 'historical_validation' not in point['uncertainty']
    assert 'lower_gwl' in point['forecast'][0]


def test_future_calibration_never_leaks_even_via_direct_call():
    point=bands.attach_error_bands(result(),calibration(),'2021-01-31',evidence=evidence())
    assert point['uncertainty']['status']=='unavailable'
    assert all('lower_gwl' not in r for r in point['forecast'])


def test_partial_supported_bands_have_true_per_horizon_and_global_status():
    card=calibration();card['radii_m']['A']={'1':2.}
    point=bands.attach_error_bands(result(),card,'2026-10-26')
    assert point['uncertainty']['status']=='historical_reference_only'
    assert point['uncertainty']['available_horizons']==[1]
    assert point['uncertainty']['unavailable_horizons']==list(range(2,13))
    assert point['forecast'][0]['upper_gwl']==3.
    assert point['forecast'][1]['interval_status']=='unavailable'
    bands.validate_disclosure(point)


@pytest.mark.parametrize('bad',[-1,float('inf'),float('nan'),True])
def test_invalid_radii_fail_closed_without_repair(bad):
    card=calibration();card['radii_m']['A']['1']=bad
    with pytest.raises(ValueError,match='invalid radius'):
        bands.attach_error_bands(result(),card,'2026-10-26')


def test_inconsistent_or_truthy_sample_counts_cannot_create_bands():
    for invalid in ({'n':30,'districts':31},{'n':True,'districts':10},{'n':30,'districts':None}):
        card=calibration();card['sample_counts']['A']['1']=invalid
        point=bands.attach_error_bands(result(),card,'2026-10-26')
        assert point['forecast'][0]['interval_status']=='unavailable'


def test_publication_rejects_status_bound_contradiction():
    point=bands.attach_error_bands(result(),calibration(),'2026-10-26')
    point['forecast'][0]['interval_status']='unavailable'
    with pytest.raises(ValueError,match='contradicts'):
        bands.validate_disclosure(point)


def test_evidence_schema_and_artifact_hash_are_verified(tmp_path):
    p=tmp_path/'evidence.json';p.write_text(json.dumps(evidence()))
    value=bands.load_validation_evidence(p)
    assert len(value['artifact_sha256'])==64
    p.write_text('{}')
    with pytest.raises(ValueError,match='version'):
        bands.load_validation_evidence(p)
    assert bands.load_validation_evidence(tmp_path/'absent') is None


def test_interval_score_penalizes_both_tails_and_width():
    score=audit.interval_score([2,-1,5],[1,1,1],[3,3,3])
    np.testing.assert_array_equal(score,[2.,42.,42.])
    with pytest.raises(ValueError):audit.interval_score([1],[2],[0])
    with pytest.raises(ValueError):audit.interval_score([np.nan],[0],[2])


def test_original_band_audit_never_refits_radius_and_reports_actual_dates():
    table=pd.DataFrame({'district_id':['HR-A','HR-B'],'origin':pd.to_datetime(['2024-01-31']*2),
        'target_date':pd.to_datetime(['2024-02-01']*2),'state_id':['HR']*2,
        'horizon':[1,1],'actual':[0.,5.],'candidate':[1.,2.],'tier_candidate':['A']*2})
    card=calibration()
    with_bands=audit.attach_original_bands(table,card)
    summary=audit.band_summary(with_bands)
    assert summary['covered_cases']==1 and summary['case_fraction_covered']==.5
    assert summary['distinct_target_dates']==1 and summary['distinct_districts']==2
    assert summary['mean_width_m']==3.5
    assert summary['local_coverage_claim'] is False
    assert card['radii_m']['A']['1']==2.
