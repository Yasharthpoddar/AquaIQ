"""Coverage and scientific invariants with intentionally small, labelled fixtures."""
from copy import deepcopy
from datetime import date
import numpy as np
import pandas as pd
import pytest
from models import tiered_forecast as tf
from models.district_registry import get_registry, validate_registry, reconcile_features


def fixture_frame():
    dates=pd.date_range('2015-01-01','2025-12-01',freq='MS')
    frames=[]
    for did,depth in [('HR-A',10.),('HR-B',20.),('TN-C',30.)]:
        f=pd.DataFrame({'district_id':did,'date':dates,'gwl_current':depth+np.sin(dates.month*np.pi/6),
            'is_observed':True,'is_imputed':False,'rainfall_current':60.,'temperature':25.,'evapotranspiration':30.})
        f['gwl_lag_3mo']=f.gwl_current.shift(3);f['gwl_lag_6mo']=f.gwl_current.shift(6)
        frames.append(f)
    return pd.concat(frames,ignore_index=True)


def test_registry_is_unique_state_qualified_and_feature_ids_reconcile():
    rows=get_registry();ids=[r['district_id'] for r in rows]
    assert len(ids)==len(set(ids)) and len({r['state_id'] for r in rows})==36
    assert all(r['district_id'].startswith(r['state_id']+'-') for r in rows)
    with pytest.raises(ValueError,match='absent'):
        reconcile_features(pd.DataFrame({'district_id':['ZZ-Unknown'],'date':[pd.Timestamp('2020-01-01')]}))


def test_registry_rejects_duplicate_conflicting_metadata_and_wrong_state():
    f=pd.DataFrame({'canonical_district_id':['HR-A','HR-A'],'canonical_name':['A','Different'],'canonical_state':['Haryana','Haryana']})
    with pytest.raises(ValueError,match='Conflicting'):validate_registry(f)
    f=f.iloc[:1].assign(canonical_state='Telangana')
    with pytest.raises(ValueError,match='state'):validate_registry(f)


def test_genuine_flags_completed_month_and_monitoring_denominator():
    f=fixture_frame().query("district_id=='HR-A'").copy()
    f.loc[f.date<'2020-01-01','is_observed']=False
    f.loc[f.date=='2020-01-01','is_imputed']=True
    obs=tf.observations(f,pd.Timestamp('2020-05-15'))
    assert obs.date.tolist()==list(pd.date_range('2020-02-01','2020-04-01',freq='MS'))
    ready=tf.readiness(f,pd.Timestamp('2020-05-15'))
    assert ready['monitoring_start']=='2020-02-01' and ready['expected_monitoring_rounds']==1
    assert ready['data_age_months']==1 and not ready['eligible']


def test_cold_reference_invariant_to_hidden_target_history_and_future():
    f=fixture_frame();cutoff=pd.Timestamp('2021-01-31')
    first=tf.RegionalReference(f,cutoff)
    tampered=f.copy();tampered.loc[(f.district_id=='HR-A') | (f.date>cutoff),'gwl_current']=90000.
    second=tf.RegionalReference(tampered,cutoff)
    months=pd.date_range('2021-02-01',periods=12,freq='MS')
    a,meta=first.predict('HR-A',months,f.iloc[:0])
    b,_=second.predict('HR-A',months,f.iloc[:0])
    np.testing.assert_array_equal(a,b)
    assert all(m['target_district_excluded'] for m in meta)
    assert meta[0]['scope']=='global'  # one other same-state donor cannot define regional variation


@pytest.mark.parametrize('count',[0,1,3,9,23])
def test_all_sparse_counts_have_twelve_horizons_without_imputation(count):
    f=fixture_frame();cutoff=pd.Timestamp('2025-12-31');ref=tf.RegionalReference(f,cutoff)
    local=f[f.district_id=='HR-A'].copy()
    local['is_observed']=False
    if count:local.loc[local.tail(count).index,'is_observed']=True
    result=tf.forecast_district('HR-A',local,cutoff,'fixture',None,ref)
    assert result['observation_count']==count
    assert result['evidence_tier']==('C' if count==0 else 'B')
    assert len(result['forecast'])==12 and result['forecast'][0]['date']=='2026-01-01'
    assert result['forecast'][-1]['date']=='2026-12-01'
    assert all(np.isfinite(r['predicted_gwl']) and r['predicted_gwl']>=0 for r in result['forecast'])
    assert all(r['weather']['rainfall_mm'] is None for r in result['forecast'])
    assert (result['last_observed_date'] is None)==(count==0)


def test_missing_weather_uses_distinct_tier_and_invalid_model_fails(monkeypatch):
    f=fixture_frame();cutoff=pd.Timestamp('2025-12-31');ref=tf.RegionalReference(f,cutoff)
    local=f[f.district_id=='HR-A'].copy();local[tf.WEATHER]=np.nan
    monkeypatch.setattr(tf.climate,'forecast_from_evidence',lambda *a,**k:{'status':'insufficient_data','message':'Missing weather'})
    result=tf.forecast_district('HR-A',local,cutoff,'fixture',(None,{'train_target_cutoff':'2019-12-31'}),ref)
    assert result['evidence_tier']=='D' and all(result['input_missingness'].values())
    monkeypatch.setattr(tf.climate,'forecast_from_evidence',lambda *a,**k:{'status':'model_unavailable'})
    with pytest.raises(RuntimeError):tf.forecast_district('HR-A',local,cutoff,'fixture',(None,{'train_target_cutoff':'2019-12-31'}),ref)


def test_publication_rejects_missing_district_dates_nan_and_bad_ranges():
    f=fixture_frame();cutoff=pd.Timestamp('2025-12-31');ref=tf.RegionalReference(f,cutoff)
    res=tf.forecast_district('HR-Z',f.iloc[:0],cutoff,'fixture',None,ref)
    res['generation_id']='fixture'
    identity={'districts':['HR-Z'],'as_of':date(2025,12,31),'forecast_origin':date(2025,12,1),'generation_id':'fixture'}
    assert tf.validate_complete_generation(identity,{'HR-Z':res})['horizons']==12
    with pytest.raises(ValueError):tf.validate_complete_generation(identity,{})
    for field,value in [('date','2026-02-01'),('predicted_gwl',float('nan')),('lower_gwl',900.)]:
        broken=deepcopy(res);broken['forecast'][0][field]=value
        if field=='lower_gwl':broken['forecast'][0]['upper_gwl']=901.
        with pytest.raises(ValueError):tf.validate_complete_generation(identity,{'HR-Z':broken})


def test_no_donors_never_invents_output():
    f=fixture_frame().iloc[:0]
    with pytest.raises(ValueError,match='No genuine'):tf.RegionalReference(f,pd.Timestamp('2021-01-31'))


def test_persisted_state_membership_is_not_replaced_by_a_new_live_registry(monkeypatch):
    from api.app import create_app
    from api.routes import state
    stored={'state_id':'HR','generation_id':'published','districts':['HR-Old'],
        'contributing_district_ids':['HR-Old'],'status':'forecast'}
    monkeypatch.setattr(state.forecast_storage,'get_state_forecast',lambda *a,**kw:stored)
    monkeypatch.setattr(state,'get_state_districts',lambda *a:['HR-New','HR-Another'])
    res=create_app({'TESTING':True}).test_client().get('/api/predict/state/HR?as_of=2026-10-25')
    assert res.status_code==200 and res.json['districts']==['HR-Old']
    assert stored['districts']==['HR-Old']
