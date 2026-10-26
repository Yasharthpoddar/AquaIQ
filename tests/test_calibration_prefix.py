import pandas as pd
import pytest

from scripts.prepare_final_calibration import prove_calibration_prefix


def panel():
    return pd.DataFrame({'district_id':['AA-Test']*3,'date':pd.to_datetime(['2021-01-01','2022-01-01','2025-01-01']),
        'gwl_current':[1.,2.,None],'is_observed':[True,True,False],'feature_generation':['parent']*3})


def test_only_future_measurements_can_reuse_pre_origin_radii():
    parent=panel();candidate=parent.copy();candidate['feature_generation']='candidate'
    candidate.loc[2,['gwl_current','is_observed']]=[3.,True]
    assert prove_calibration_prefix(parent,candidate,'2022-07-01')==2


@pytest.mark.parametrize('change',['depth','date','flag','schema'])
def test_changed_calibration_inputs_fail_closed(change):
    parent=panel();candidate=parent.copy()
    if change=='depth':candidate.loc[0,'gwl_current']=9.
    elif change=='date':candidate.loc[0,'date']=pd.Timestamp('2021-02-01')
    elif change=='flag':candidate.loc[0,'is_observed']=False
    else:candidate['new_predictor']=1.
    with pytest.raises(ValueError):prove_calibration_prefix(parent,candidate,'2022-07-01')
