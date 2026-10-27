"""Chronological selection and reproducibility of the isolated fit runner."""
import numpy as np
import pandas as pd
import pytest

from models.climate_forecast_12m import FEATURES
from scripts.retrain_enriched_xgboost import partition, select_candidate, fit_final, compare_pairs


def tiny_pairs():
    random = np.random.default_rng(42)
    values = pd.DataFrame(random.normal(size=(240,len(FEATURES))),columns=FEATURES)
    values['origin_gwl'] = 10.
    values['horizon_months'] = np.tile(np.arange(1,13),20)
    values['district_id'] = np.repeat(['TN-A','TN-B'],120)
    values['origin_date'] = pd.Timestamp('2018-01-01')
    values['target_date'] = [pd.Timestamp('2018-01-01')+pd.DateOffset(months=int(h)) for h in values.horizon_months]
    values['target_delta'] = values.cumulative_rainfall*.1
    values['actual_gwl'] = values.origin_gwl+values.target_delta
    return values


def test_chronological_fold_keeps_all_training_targets_before_validation_origins():
    train = tiny_pairs()
    later = train.copy()
    later['origin_date'] += pd.DateOffset(years=3)
    later['target_date'] += pd.DateOffset(years=3)
    fold = dict(train_target_cutoff='2019-12-31',validation_origin_start='2021-01-01',
                validation_origin_end='2021-12-01',validation_target_end='2022-01-01')
    a,b = partition(pd.concat([train,later],ignore_index=True),fold)
    assert len(a)==len(b)==240
    assert a.target_date.max()<b.origin_date.min()
    with pytest.raises(ValueError,match='embargo'):
        partition(pd.concat([train,later]),{**fold,'validation_origin_start':'2020-01-01'})


def test_final_fit_repeats_exact_bytes_and_predictions_for_same_seed():
    pairs = tiny_pairs()
    settings = dict(n_estimators=8,max_depth=2,n_jobs=1,random_state=42,tree_method='hist')
    a,b = fit_final(pairs,settings),fit_final(pairs,settings)
    assert a.get_booster().save_raw(raw_format='ubj')==b.get_booster().save_raw(raw_format='ubj')
    np.testing.assert_array_equal(a.predict(pairs[FEATURES]),b.predict(pairs[FEATURES]))
    assert a.get_booster().feature_names==FEATURES
    with pytest.raises(ValueError,match='twelve'):
        fit_final(pairs.loc[pairs.horizon_months.ne(12)],settings)


def test_selection_rejects_final_test_records_and_uses_earlier_macro_error_only():
    def result(name,error,iteration=7):
        return dict(phase='earlier_validation',candidate=name,best_iteration=iteration,
            metrics={'retrained':{'district_macro_mae_m':error,'rmse_m':2.}})
    winner,scores = select_candidate([result('a',2.),result('b',1.)])
    assert winner=='b' and scores[winner]['final_trees']==8
    with pytest.raises(ValueError,match='earlier'):
        select_candidate([{**result('a',0.),'phase':'final_diagnostic'}])
    with pytest.raises(ValueError,match='same validation folds'):
        select_candidate([result('a',2.),result('b',1.),result('b',1.)])


def test_seasonal_baseline_never_uses_a_date_after_origin():
    pairs = tiny_pairs().iloc[:12].copy()
    model = fit_final(tiny_pairs(),dict(n_estimators=3,n_jobs=1,random_state=42))
    frame = pd.DataFrame({'district_id':['TN-A','TN-A'],
        'date':pd.to_datetime(['2017-02-01','2018-01-01']),
        'gwl_current':[6.,10.],'is_observed':[True,True],'is_imputed':[False,False]})
    cases = compare_pairs(pairs,{'frozen':model,'retrained':model},frame)
    assert cases.iloc[0].seasonal==6.
    assert cases.iloc[-1].seasonal==10.
    assert cases.iloc[1].seasonal is np.nan or pd.isna(cases.iloc[1].seasonal)


@pytest.mark.parametrize('filename',['training_summary.json','selection.json','checkpoint.json'])
def test_report_and_checkpoint_aliases_are_rejected_before_any_fitting(tmp_path,monkeypatch,filename):
    from scripts import retrain_enriched_xgboost as runner
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    folder=tmp_path/'models/artifacts/enriched_retraining_test'
    with pytest.raises(ValueError):
        runner.validate_destinations(folder,folder/filename)
    with pytest.raises(ValueError):
        runner.validate_destinations(folder/'reports',folder/'checkpoint.json')
    assert not folder.exists()


def test_existing_bundle_and_its_contents_are_never_overwritten(tmp_path,monkeypatch):
    from scripts import retrain_enriched_xgboost as runner
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    folder=tmp_path/'models/artifacts/enriched_retraining_test'
    folder.mkdir(parents=True);(folder/'model.json').write_text('preserved')
    with pytest.raises(FileExistsError,match='not empty'):
        runner.validate_destinations(tmp_path/'reports/new',folder/'checkpoint.json')
    assert (folder/'model.json').read_text()=='preserved'


@pytest.mark.parametrize('prediction', [np.array([-np.inf]*3), np.array([np.nan]*3), np.array([1.]), np.ones((3,1))])
def test_invalid_predictions_cannot_be_hidden_by_clipping_or_broadcast(prediction):
    from scripts.retrain_enriched_xgboost import predict_deltas
    class Broken:
        def predict(self,values):return prediction
    with pytest.raises(ValueError,match='one finite depth change'):
        predict_deltas(Broken(),pd.DataFrame(np.zeros((3,len(FEATURES))),columns=FEATURES))
