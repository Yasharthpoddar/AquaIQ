"""Synthetic source fixtures verify coverage policy, not forecasting skill."""
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from models import state_median_forecast as core, state_median_policy as policy
from tests.test_state_median_forecast import history  # noqa: F401 - registered fixture


REGISTRY = [dict(district_id=f'TN-{name}',state_id='TN') for name in ('A','B','C','D')]


def sparse_history(rows, as_of='2026-10-29'):
    frame = pd.DataFrame(rows,columns=['district_id','date','gwl_current','is_observed','is_imputed'])
    frame.attrs.update(feature_generation_id='synthetic-policy',data_sha256='a'*64)
    return core.build_state_history(frame,REGISTRY,as_of=as_of)


def card_for(hist):
    return dict(training_cutoff='2019-12-01',min_coverage=.5,states={},
        feature_generation_id=hist.attrs['feature_generation_id'],data_sha256=hist.attrs['data_sha256'],
        registry_sha256=hist.attrs['registry_sha256'])


def test_exactly_one_genuine_low_coverage_observation_supports_twelve_month_persistence():
    h=sparse_history([('TN-A','2025-01-01',7.,True,False)])
    result=policy.forecast_state('TN',h,{},card_for(h),'2026-10-29')
    assert result['status']=='forecast' and result['forecast_method']=='persistence_fallback'
    assert [r['predicted_gwl'] for r in result['forecast']]==[7.]*12
    assert result['genuine_observation_count']==result['genuine_observed_months']==1
    assert result['historical_reference_date']=='2025-01-01' and result['reference_age_months']==21
    assert result['reference_is_stale'] and not result['reference_training_eligible']
    assert result['district_coverage_pct']==25.
    assert result['training_cutoff'] is None and result['model_sha256'] is None
    assert result['evaluation']['n']==0 and result['evaluation']['status']=='not_evaluated_for_fallback'
    assert result['forecast'][0]['target_date']=='2026-11-01'
    assert result['forecast'][-1]['target_date']=='2027-10-01'


def test_few_observations_use_latest_state_median_not_whole_history_average():
    h=sparse_history([('TN-A','2024-01-01',20.,True,False),('TN-B','2025-01-01',2.,True,False),
                      ('TN-C','2025-01-01',10.,True,False)])
    result=policy.forecast_state('TN',h,{},card_for(h),'2026-10-29')
    assert result['genuine_observed_months']==2 and result['genuine_observation_count']==3
    assert result['last_observed_gwl_m_bgl']==6.
    assert all(row['predicted_gwl']==6. for row in result['forecast'])


def test_invalid_missing_imputed_unknown_values_do_not_create_observations():
    h=sparse_history([('TN-A','2025-01-01',np.nan,True,False),('TN-B','2025-01-01',np.inf,True,False),
        ('TN-C','2025-01-01',-4.,True,False),('TN-D','2025-01-01',5.,False,True)])
    result=policy.forecast_state('TN',h,{},card_for(h),'2026-10-29')
    assert result['genuine_observation_count']==0 and not result['forecast']
    assert result['status']=='insufficient_data' and result['forecast_method']=='no_observations'
    assert result['latest_observation_date'] is None and result['reference_observation'] is None


def test_genuine_zero_is_a_measurement_and_does_not_represent_missing_data():
    h=sparse_history([('TN-A','2025-01-01',0.,True,False)])
    result=policy.forecast_state('TN',h,{},card_for(h),'2026-10-29')
    assert result['genuine_observation_count']==1 and result['status']=='forecast'
    assert all(row['predicted_gwl']==0. for row in result['forecast'])


def test_old_reference_is_preserved_outside_normal_chart_window():
    h=sparse_history([('TN-A','2002-01-01',4.,True,False)])
    result=policy.forecast_state('TN',h,{},card_for(h),'2026-10-29')
    assert result['historical_reference_date']=='2002-01-01'
    assert result['reference_age_months']==297 and result['reference_is_stale']
    assert result['history'][0]['date']=='2002-01-01'
    assert result['history'][1]['gwl_m_bgl'] is None
    assert result['history'][-1]['date']=='2026-09-01'
    assert result['reference_observation']['gwl_m_bgl']==4.


def test_future_observations_cannot_change_past_fallback():
    h=sparse_history([('TN-A','2025-01-01',4.,True,False),('TN-A','2026-10-31',99.,True,False)])
    result=policy.forecast_state('TN',h,{},card_for(h),'2026-10-29')
    assert result['genuine_observed_months']==1 and result['last_observed_gwl_m_bgl']==4.


def test_missing_or_mismatched_assets_never_trigger_persistence():
    h=sparse_history([('TN-A','2025-01-01',4.,True,False)])
    bad=card_for(h);bad['states']={'TN':{'status':'trained'}}
    with pytest.raises(ValueError,match='artifact is missing'):
        policy.forecast_state('TN',h,{},bad,'2026-10-29')
    bad=card_for(h);bad['data_sha256']='b'*64
    with pytest.raises(ValueError,match='assets/source'):
        policy.forecast_state('TN',h,{},bad,'2026-10-29')


def test_eligible_state_retains_identical_xgboost_predictions_and_quality_gates(history,tmp_path):
    models,card=core.train_state_models(history,tmp_path/'models','2019-12-31')
    before=core.forecast_state('TN',history,models,card,'2021-10-29')
    after=policy.forecast_state('TN',history,models,card,'2021-10-29')
    assert after['forecast_method']=='state_median_xgboost'
    assert after['forecast']==before['forecast'] and after['model_sha256']==before['model_sha256']
    assert after['reference_training_eligible'] and after['reference_age_months']<=12
    assert card['min_history']==core.MIN_HISTORY==36
    assert card['min_span_months']==core.MIN_SPAN_MONTHS==60


def test_stale_xgboost_reference_uses_named_persistence_without_weakening_training(history,tmp_path):
    models,card=core.train_state_models(history,tmp_path/'models','2019-12-31')
    result=policy.forecast_state('TN',history,models,card,'2026-10-29')
    assert result['forecast_method']=='persistence_fallback' and result['reference_is_stale']
    assert result['model_sha256'] is None and result['training_cutoff'] is None
    assert 'last 12 months' in result['fallback_reason']
