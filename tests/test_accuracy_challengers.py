import json

import numpy as np
import pandas as pd
import pytest

from models import accuracy_challengers as c
from models.climate_forecast_12m import FEATURES
from scripts.run_accuracy_experiments import rank, trees_for


def training_pairs():
    rng=np.random.default_rng(42);n=6000
    f=pd.DataFrame(rng.normal(size=(n,len(FEATURES))),columns=FEATURES)
    f['horizon_months']=np.tile(np.arange(1,13),500)
    f['district_id']=np.tile([f'AA-{i}' for i in range(60)],100)
    # Each individual horizon must see >=50 distinct districts.
    f['district_id']=[f'AA-{(i//12)%60}' for i in range(n)]
    f['origin_date']=[pd.Timestamp(2005+(i//12)%6,1,1) for i in range(n)]
    f['target_date']=[d+pd.DateOffset(months=int(h)) for d,h in zip(f.origin_date,f.horizon_months)]
    f['origin_gwl']=10.+rng.random(n)
    f['target_delta']=.1*f.origin_gwl_lag_3mo
    f['actual_gwl']=f.origin_gwl+f.target_delta
    return f


@pytest.mark.parametrize('structure',['shared','individual','grouped'])
def test_horizon_structure_reload_schema_and_repeatability(tmp_path,structure):
    pairs=training_pairs()
    recipe={'name':'fixture','structure':structure,'parameters':{'n_estimators':2,'n_jobs':1}}
    first=c.fit(recipe,pairs);second=c.fit(recipe,pairs)
    np.testing.assert_array_equal(first.depth(pairs),second.depth(pairs))
    _,card=c.save(first,tmp_path/'artifact',{'training_dataset_fingerprint':'fixture'})
    loaded,_=c.load(tmp_path/'artifact/checkpoint.json')
    np.testing.assert_array_equal(first.depth(pairs),loaded.depth(pairs))
    assert card['ordered_input_features']==FEATURES
    with pytest.raises(ValueError,match='ordered'):
        loaded.predict(pairs[list(reversed(FEATURES))])
    changed=pairs[FEATURES].iloc[:1].copy();changed['horizon_months']=13
    with pytest.raises(ValueError,match='Unsupported'):
        loaded.predict(changed)


def test_sparse_horizon_fails_explicitly_instead_of_shifting_population():
    pairs=training_pairs();pairs=pairs.loc[pairs.horizon_months.ne(11)]
    with pytest.raises(ValueError,match='Unsupported horizon'):
        c.fit({'name':'individual','structure':'individual','parameters':{'n_estimators':2}},pairs)


def test_ridge_transforms_fit_only_training_and_reload_without_pickle(tmp_path):
    pairs=training_pairs();pairs.loc[pairs.index%3==0,'origin_gwl_lag_3mo']=np.nan
    recipe={'name':'ridge','kind':'ridge','alpha':100.}
    model=c.fit(recipe,pairs)
    medians=model.members[0][1].steps[0][1].statistics_.copy()
    validation=pairs.copy();validation['origin_gwl_lag_3mo']=999999.
    c.fit(recipe,pairs,validation=validation)
    np.testing.assert_array_equal(medians,model.members[0][1].steps[0][1].statistics_)
    c.save(model,tmp_path/'ridge',{})
    loaded,_=c.load(tmp_path/'ridge/checkpoint.json')
    np.testing.assert_allclose(loaded.predict(pairs[FEATURES]),model.predict(pairs[FEATURES]),rtol=0,atol=1e-12)


def test_checksum_and_path_integrity_fail_closed(tmp_path):
    model=c.fit({'name':'fixture','parameters':{'n_estimators':2}},training_pairs())
    c.save(model,tmp_path/'artifact',{})
    path=tmp_path/'artifact/model_00.json';path.write_text(path.read_text()+' ')
    with pytest.raises(ValueError,match='checksum'):c.load(tmp_path/'artifact/checkpoint.json')
    with pytest.raises(FileExistsError):c.save(model,tmp_path/'artifact',{})


def test_trend_uses_only_origin_history_and_sparse_history_persists():
    pairs=training_pairs().iloc[:12].copy();pairs['district_id']='AA-One'
    pairs['origin_date']=pd.Timestamp('2019-01-01')
    frame=pd.DataFrame({'district_id':['AA-One']*4,'date':pd.to_datetime(['2017-01-01','2018-01-01','2019-01-01','2020-01-01']),
                        'gwl_current':[8.,9.,10.,999.],'is_observed':True,'is_imputed':False})
    recipe={'name':'trend','kind':'trend','window_months':36,'damping_months':6.}
    first=c.trend_deltas(pairs,frame,recipe)
    frame.loc[frame.date.gt('2019-01-01'),'gwl_current']=100000.
    np.testing.assert_array_equal(first,c.trend_deltas(pairs,frame,recipe))
    assert (first>0).all() and first[-1]<1.
    np.testing.assert_array_equal(c.trend_deltas(pairs,frame.iloc[2:],recipe),np.zeros(12))


def test_selection_cannot_use_outer_records_or_contaminated_artifact():
    def record(year,phase='inner'):
        return {'year':year,'phase':phase,'scores':{'joint':{'methods':{
            'a':{'supported':True,'district_macro_mae_m':2.,'rmse_m':3.},
            'b':{'supported':True,'district_macro_mae_m':1.,'rmse_m':2.}}}},
            'fits':{'a':[{'trees':10}],'b':[{'trees':20}]}}
    inner=[record(2018),record(2019)]
    assert rank(inner,[2018,2019],['a','b'])[0]=='b'
    assert trees_for(inner,[2018,2019],'b')==[20]
    with pytest.raises(ValueError,match='same supported'):
        rank([record(2021,'outer')],[2021],['a','b'])


def test_january_2026_training_labels_rejected():
    pairs=training_pairs();pairs['target_date']=pd.Timestamp('2026-01-01')
    with pytest.raises(ValueError,match='January 2026'):c.fit({'name':'fixture'},pairs)
