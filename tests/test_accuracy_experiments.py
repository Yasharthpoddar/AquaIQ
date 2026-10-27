"""Scientific invariants of the isolated accuracy experiment."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models import accuracy_experiments as a


def source():
    return pd.DataFrame({'district_id':['AA-One']*5,
        'date':pd.to_datetime(['2018-01-01','2018-04-01','2019-01-01','2019-02-01','2020-01-01']),
        'gwl_current':[10.,8.,11.,999.,25.], 'is_observed':[True,True,True,False,True],
        'is_imputed':[False,False,False,True,False]})


def cases():
    return pd.DataFrame({'district_id':['AA-One']*3,
        'origin_date':pd.to_datetime(['2019-02-01']*3),
        'target_date':pd.to_datetime(['2019-03-01','2019-04-01','2020-01-01']),
        'horizon':[1,2,11],'actual':[12.,13.,25.]})


def test_baselines_resolve_observed_values_and_keep_missing_seasonal():
    values=a.baseline_cases(cases(),source())
    assert values.persistence.tolist()==[11.,11.,11.]
    assert values.persistence_date.eq(pd.Timestamp('2019-01-01')).all()
    assert np.isnan(values.seasonal.iloc[0])
    assert values.seasonal.iloc[1:].tolist()==[8.,11.]
    assert values.seasonal_date.iloc[2]==pd.Timestamp('2019-01-01')


def test_future_perturbations_cannot_change_either_baseline():
    before=a.baseline_cases(cases(),source())
    changed=source(); changed.loc[changed.date.gt('2019-02-01'),'gwl_current']=100000.
    after=a.baseline_cases(cases(),changed)
    pd.testing.assert_frame_equal(before,after)


def test_zero_history_has_no_fabricated_baseline():
    values=cases();values['district_id']='BB-New'
    out=a.baseline_cases(values,source())
    assert out[['persistence','seasonal']].isna().all().all()
    assert out.observation_count.eq(0).all()


def test_m_plus_twelve_can_use_origin_observation_for_seasonal():
    values=cases().iloc[:1].copy();values['origin_date']=pd.Timestamp('2019-01-01')
    values['target_date']=pd.Timestamp('2020-01-01');values['horizon']=12
    out=a.baseline_cases(values,source())
    assert out.seasonal.iloc[0]==out.persistence.iloc[0]==11.


def test_matched_metrics_use_identical_keys_and_explicit_exclusions():
    values=cases();values['a']=[10.,20.,30.];values['b']=[np.nan,20.,30.]
    result=a.matched(values,['a','b'])
    assert result['excluded']==1
    assert result['methods']['a']['n']==result['methods']['b']['n']==2
    assert result['case_keys_sha256']==a.key_hash(values.iloc[1:])
    with pytest.raises(ValueError,match='Duplicate'):
        a.matched(pd.concat([values,values.iloc[:1]]),['a','b'])


def test_case_and_district_macro_metrics_are_distinct():
    values=pd.DataFrame({'district_id':['a','a','a','b'],'actual':[0.]*4,'prediction':[0.,0.,0.,8.]})
    metrics=a.metric(values,'prediction')
    assert metrics['mae_m']==2. and metrics['district_macro_mae_m']==4.
    assert metrics['mean_signed_error_m']==2.
    assert metrics['overestimate_fraction']==.25
    assert not metrics['supported']


def test_district_weights_equalize_training_mass_without_reading_labels():
    train=pd.DataFrame({'district_id':['a']*9+['b'],'target_delta':range(10)})
    weights=a.district_weights(train)
    assert weights.mean()==pytest.approx(1.)
    assert weights[:9].sum()==pytest.approx(weights[-1])
    changed=train.copy();changed['target_delta']=np.nan
    np.testing.assert_array_equal(weights,a.district_weights(changed))
    with pytest.raises(ValueError):a.district_weights(train.iloc[:0])


def test_partition_enforces_target_cutoff_origin_embargo_and_pre2023_labels():
    pairs=pd.DataFrame({'origin_date':pd.to_datetime(['2017-01-01','2019-01-01','2020-01-01']),
                        'target_date':pd.to_datetime(['2017-04-01','2019-04-01','2020-04-01'])})
    train,valid=a.partition(pairs,a.fold_for_year(2019))
    assert len(train)==len(valid)==1
    assert train.target_date.max()<valid.origin_date.min()
    with pytest.raises(ValueError,match='embargo'):
        a.partition(pairs,{**a.fold_for_year(2019),'train_target_cutoff':'2018-12-31'})
    with pytest.raises(ValueError,match='2023'):
        a.partition(pairs,a.fold_for_year(2023))


def test_district_cluster_resampling_is_deterministic():
    values=pd.DataFrame({'district_id':np.repeat([str(i) for i in range(12)],3),
                         'actual':0.,'candidate':1.,'baseline':2.})
    first=a.paired_district_bootstrap(values,'candidate','baseline',100)
    assert first==a.paired_district_bootstrap(values,'candidate','baseline',100)
    assert first['percentile_95_interval_m']==[-1.,-1.]
    assert first['districts']==12


def test_pure_experiment_module_has_no_database_or_production_writes():
    text=Path(a.__file__).read_text()
    assert 'get_connection(' not in text and 'publish_bundle(' not in text
    assert '.to_sql(' not in text


def test_mechanical_nested_folds_depend_on_availability_only():
    rows=[]
    for year in range(2005,2023):
        for district in range(500):
            for month in [1,4,7,10]:
                rows.append({'district_id':str(district),'origin_date':pd.Timestamp(year,month,1),
                             'target_date':pd.Timestamp(year,month+1,1),'horizon_months':1.,'actual_gwl':1.})
    pairs=pd.DataFrame(rows)
    folds=a.choose_folds(pairs)
    assert [f['year'] for f in folds['outer']]==[2020,2021]
    assert [f['inner_years'] for f in folds['outer']]==[[2016,2017],[2017,2018]]
    pairs['actual_gwl']=99999.
    assert a.choose_folds(pairs)==folds
    for outer in folds['outer']:
        for year in outer['inner_years']:
            assert pd.Timestamp(a.fold_for_year(year)['validation_target_end'])<=pd.Timestamp(outer['train_target_cutoff'])
