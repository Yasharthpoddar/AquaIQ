"""Serving evidence, forecast origin and atomic publication regressions."""
import json
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
from models import ensemble,score_all,xgboost_model

def evidence(origin='2021-01-01'):
    row={key:10. for key in ensemble.NUMERIC_FEATURES}
    row.update(date=pd.Timestamp(origin),crop_season_flag='Rabi',is_observed=True)
    frame=pd.DataFrame([row])
    return {'district_id':'RJ-Jaipur','origin':pd.Timestamp(origin),'as_of':pd.Timestamp('2026-10-13'),
        'generation':'generation','estimate_type':'district_level','zone':None,'reason':None,
        'frame':frame,'history':frame,'readiness':{}}

def test_trend_uses_elapsed_calendar_time():
    dates=pd.to_datetime(['2002-01-01','2002-02-01','2003-01-01','2004-01-01','2005-01-01','2006-01-01'])
    months=np.array([d.year*12+d.month for d in dates])
    series=pd.Series(8.+(months-months[0])*.01,index=dates)
    assert ensemble.lr_trend_score(series)==pytest.approx(56.)

def test_components_ignore_filled_measurements():
    frame=pd.DataFrame({'date':pd.date_range('2020-01-01',periods=24,freq='MS'),
        'gwl_current':np.linspace(8,9,24),'is_observed':True,'monsoon_deficit_pct':-10.})
    artificial=pd.DataFrame({'date':[pd.Timestamp('2022-01-01')],'gwl_current':[999.],
        'is_observed':['False'],'monsoon_deficit_pct':[-100.]})
    assert ensemble.components_from_history(pd.concat([frame,artificial]),10.)==ensemble.components_from_history(frame,10.)

def test_missing_components_stay_missing_and_zero_is_valid():
    weights={'xgboost_risk':.8,'linear_regression_trend':.2,'drought_frequency':0.,'fuzzy_logic':0.}
    assert ensemble.blend_components({'xgb_risk':None,'lr_trend':0.},weights)==(0,{'linear_regression_trend':1.})
    assert ensemble.blend_components({'xgb_risk':None,'lr_trend':None},weights)==(None,{})

def test_forecast_is_one_calendar_endpoint_and_named_features(monkeypatch):
    model=Mock()
    model.predict.return_value=[12.3456]
    card={'version':'test','train_target_cutoff':'2019-12-31','features':xgboost_model.CANONICAL_FEATURE_COLS,
        'validation_assessment':{'status':'limited_evidence'}}
    monkeypatch.setattr(ensemble,'_load_bundle',lambda:(model,card))
    result=ensemble.forecast_from_evidence(evidence())
    assert result['forecast']==[{'month':'2021-07','predicted_gwl':12.3456}]
    assert result['status']=='historical_forecast' and result['last_observed_date']=='2021-01-01'
    assert result['model_validation']['status']=='limited_evidence'
    assert list(model.predict.call_args.args[0].columns)==xgboost_model.CANONICAL_FEATURE_COLS

def test_checkpoint_cannot_predict_from_an_origin_before_training(monkeypatch):
    model=Mock()
    monkeypatch.setattr(ensemble,'_load_bundle',lambda:(model,{'version':'test','train_target_cutoff':'2019-12-31'}))
    result=ensemble.forecast_from_evidence(evidence('2015-01-01'))
    assert result['status']=='unavailable' and result['forecast']==[]
    model.predict.assert_not_called()

def test_future_as_of_is_rejected():
    with pytest.raises(ValueError,match='future'):
        ensemble._as_of('2099-01-01')

@pytest.mark.parametrize('cutoff,available',[('2021-01-15','2020-12-01'),('2021-01-31','2021-01-01'),
    ('2024-02-28','2024-01-01'),('2024-02-29','2024-02-01')])
def test_partial_month_cannot_supply_completed_weather(cutoff,available):
    assert ensemble._completed_feature_month(pd.Timestamp(cutoff))==pd.Timestamp(available)

def test_cached_bundle_revalidates_changed_assets(monkeypatch,tmp_path):
    checkpoint=tmp_path/'models/checkpoints/aquaiq_xgb.json'
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(json.dumps({'model_path':'model.json','card_path':'card.json'}))
    (checkpoint.parent/'model.json').write_text('model')
    card_path=checkpoint.parent/'card.json'
    card_path.write_text('good')
    loader=Mock(return_value=('model',{}))
    monkeypatch.setattr(ensemble,'ROOT',tmp_path)
    monkeypatch.setattr(ensemble,'feature_generation',lambda:'generation')
    monkeypatch.setattr(xgboost_model,'load_model_bundle',loader)
    ensemble._BUNDLE_CACHE.clear()
    assert ensemble._load_bundle()[0]=='model'
    ensemble._load_bundle()
    assert loader.call_count==1
    card_path.write_text('tampered-card')
    loader.side_effect=ValueError('checksum')
    with pytest.raises(RuntimeError,match='incompatible'):
        ensemble._load_bundle()
    assert loader.call_count==2
    ensemble._BUNDLE_CACHE.clear()

def test_scoring_exception_does_not_publish_partial_run(monkeypatch):
    connection=Mock()
    monkeypatch.setattr(score_all,'get_connection',lambda:connection)
    monkeypatch.setattr(score_all,'read_frame',lambda *args:pd.DataFrame({'district_id':['RJ-Jaipur','PY-Mahe']}))
    monkeypatch.setattr(score_all,'feature_generation',lambda:'generation')
    monkeypatch.setattr(score_all,'_load_bundle',lambda:(Mock(),{'version':'test','model_sha256':'sha'}))
    monkeypatch.setattr(score_all,'compute_crisis_score',Mock(side_effect=RuntimeError('Database unavailable')))
    with pytest.raises(RuntimeError):
        score_all.score_all_districts('2026-10-13')
    connection.cursor.assert_not_called()
    connection.close.assert_called_once()
