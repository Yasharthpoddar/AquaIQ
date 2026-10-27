"""Isolated learners and checksum-bound experimental inference adapters."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from models.climate_forecast_12m import FEATURES
from models.xgboost_model import sha256_file, _write_json, _json_hash

BASE = {'n_estimators':461,'max_depth':4,'learning_rate':.04,'min_child_weight':60,
        'reg_lambda':40.,'reg_alpha':.2,'subsample':.85,'colsample_bytree':.9,
        'random_state':42,'n_jobs':4,'tree_method':'hist','objective':'reg:squarederror',
        'eval_metric':'mae'}
GROUPS = {'ground':['origin_gwl','origin_gwl_lag_3mo','origin_gwl_lag_6mo'],
    'calendar':['horizon_months','origin_month_sin','origin_month_cos','target_month_sin','target_month_cos'],
    'weather':['origin_rainfall','origin_temperature','origin_evapotranspiration',
               'target_rainfall','target_temperature','target_evapotranspiration'],
    'cumulative':['cumulative_rainfall','cumulative_evapotranspiration','mean_temperature']}


def candidates():
    recipes = [
        {'name':'production_recipe','family':'reference','parameters':{'n_estimators':240,'max_depth':3,'min_child_weight':30,'reg_lambda':20.,'reg_alpha':.1}},
        {'name':'current_recipe','family':'reference'},
        {'name':'district_balanced','family':'A','balanced':True},
        {'name':'individual_horizons','family':'B','structure':'individual'},
        {'name':'three_horizon_groups','family':'B','structure':'grouped'},
        {'name':'early_stopping','family':'C','early_stopping':True},
        {'name':'shallow_stronger_regularization','family':'C','parameters':{'max_depth':2,'min_child_weight':120,'reg_lambda':80.,'reg_alpha':.4}},
        {'name':'slower_learning','family':'C','parameters':{'learning_rate':.02},'early_stopping':True},
        {'name':'lower_subsampling','family':'C','parameters':{'subsample':.7,'colsample_bytree':.7}},
        {'name':'absolute_error','family':'D','parameters':{'objective':'reg:absoluteerror'}},
        {'name':'pseudo_huber','family':'D','parameters':{'objective':'reg:pseudohubererror','huber_slope':1.}},
        *[{'name':f'without_{group}','family':'E','drop_group':group} for group in GROUPS],
        {'name':'ridge','family':'F','kind':'ridge','alpha':100.},
        {'name':'damped_local_trend','family':'F','kind':'trend','window_months':36,'damping_months':6.}]
    hypotheses = {
        'reference':('Reference recipe refitted on identical causal data.','Benchmark structural changes.','No incremental benefit.'),
        'A':('Dense districts dominate squared-error fitting.','Improve equal-district generalization.','Noisy sparse districts receive more weight.'),
        'B':('A single horizon function limits temporal specialization.','Fit different horizon responses.','Small horizon samples increase variance.'),
        'C':('Capacity, regularization, learning rate or sampling mismatches generalization.','Reduce out-of-time residuals.','Underfitting or unstable subsampling.'),
        'D':('Large residuals exert too much squared-loss influence.','Improve typical error.','Large-error RMSE or signed bias worsens.'),
        'E':('A feature group adds complexity without out-of-time information.','Reduce unstable splits.','Remove meaningful causal signal.'),
        'F':('A simple regularized or damped trend model generalizes better.','Provide an inexpensive challenger.','Linear assumptions miss seasonal nonlinearities.')}
    for r in recipes:
        r['hypothesis'],r['expected_benefit'],r['failure_mode']=hypotheses[r['family']]
    return recipes


def horizon_groups(recipe):
    structure=recipe.get('structure','shared')
    if structure=='individual':return [[h] for h in range(1,13)]
    if structure=='grouped':return [list(range(1,5)),list(range(5,9)),list(range(9,13))]
    return [list(range(1,13))]


class Challenger:
    def __init__(self, recipe, features, members, *, frame=None, fit_details=None):
        self.recipe,self.features,self.members=recipe,features,members
        self.frame=frame
        self.fit_details=fit_details or []

    def predict(self, inputs):
        if list(inputs.columns)!=FEATURES:
            raise ValueError('Inference requires the exact ordered 17-feature schema.')
        if self.recipe.get('kind')=='trend':
            raise ValueError('Local trend requires explicit origin history, not anonymous feature rows.')
        result=np.full(len(inputs),np.nan)
        for horizons,model in self.members:
            keep=inputs.horizon_months.isin(horizons).to_numpy()
            if keep.any():result[keep]=model.predict(inputs.loc[keep,self.features])
        if not np.isfinite(result).all():raise ValueError('Unsupported or invalid horizon prediction.')
        return result

    def depth(self, pairs):
        if self.recipe.get('kind')=='trend':
            deltas=trend_deltas(pairs,self.frame,self.recipe)
        else:deltas=self.predict(pairs[FEATURES])
        if not np.isfinite(deltas).all():raise ValueError('Nonfinite predicted changes.')
        return np.round(np.maximum(0.,pairs.origin_gwl.to_numpy(float)+deltas),4)


class PortableRidge:
    """Prediction-only JSON representation of the train-fitted sklearn pipeline."""
    def __init__(self, state):self.state=state

    def predict(self, values):
        raw=values.to_numpy(float);missing=np.isnan(raw)
        filled=np.where(missing,np.asarray(self.state['medians']),raw)
        expanded=np.column_stack([filled,missing[:,self.state['indicator_columns']]])
        scaled=(expanded-np.asarray(self.state['means']))/np.asarray(self.state['scales'])
        return scaled@np.asarray(self.state['coefficients'])+self.state['intercept']


def trend_deltas(pairs,frame,recipe):
    from models.accuracy_experiments import observed_history
    observed=observed_history(frame)
    histories={did:g for did,g in observed.groupby('district_id')}
    cache,result={},[]
    for row in pairs.itertuples():
        origin=pd.Timestamp(row.origin_date);key=(row.district_id,origin)
        if key not in cache:
            history=histories.get(row.district_id,observed.iloc[:0])
            history=history.loc[history.date.between(origin-pd.DateOffset(months=recipe['window_months']),origin)]
            if len(history)>=3 and history.date.nunique()>=3:
                t=(history.date.dt.year-origin.year)*12+history.date.dt.month-origin.month
                cache[key]=float(np.polyfit(t.to_numpy(float),history.gwl_current.to_numpy(float),1)[0])
            else:cache[key]=0.
        h=float(row.horizon_months);d=float(recipe['damping_months'])
        result.append(cache[key]*d*(1-np.exp(-h/d)))
    return np.asarray(result)


def fit(recipe, training, *, validation=None, tree_counts=None, frame=None):
    from models.accuracy_experiments import district_weights
    if training.empty or pd.to_datetime(training.target_date).ge('2026-01-01').any():
        raise ValueError('Training must exclude inspected January 2026 targets.')
    features=[f for f in FEATURES if f not in GROUPS.get(recipe.get('drop_group'),[])]
    if recipe.get('kind')=='trend':return Challenger(recipe,features,[],frame=frame)
    members,details=[],[]
    for i,horizons in enumerate(horizon_groups(recipe)):
        part=training.loc[training.horizon_months.isin(horizons)]
        if len(part)<500 or part.district_id.nunique()<50 or part.target_date.dt.year.nunique()<5:
            raise ValueError(f'Unsupported horizon group {horizons}: need 500 rows, 50 districts, five target years.')
        weights=district_weights(part) if recipe.get('balanced') else None
        if recipe.get('kind')=='ridge':
            model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),
                                StandardScaler(),Ridge(alpha=recipe['alpha']))
            model.fit(part[features],part.target_delta)
            trees=None
        else:
            parameters={**BASE,**recipe.get('parameters',{})}
            if tree_counts is not None:parameters['n_estimators']=int(tree_counts[i])
            early=recipe.get('early_stopping') and validation is not None
            if early:
                parameters.update(n_estimators=480,early_stopping_rounds=40)
                v=validation.loc[validation.horizon_months.isin(horizons)]
                if v.empty:raise ValueError('Early stopping needs its own chronological inner partition.')
            model=xgb.XGBRegressor(**parameters)
            kwargs={'sample_weight':weights,'verbose':False}
            if early:kwargs['eval_set']=[(v[features],v.target_delta)]
            model.fit(part[features],part.target_delta,**kwargs)
            trees=int(model.best_iteration+1) if early else parameters['n_estimators']
        members.append((horizons,model))
        details.append({'horizons':horizons,'n':len(part),'districts':int(part.district_id.nunique()),
                        'target_years':int(part.target_date.dt.year.nunique()),'trees':trees})
    return Challenger(recipe,features,members,fit_details=details)


def save(model, directory, card):
    """Portable JSON artifacts; separate loader, never a production pointer."""
    directory=Path(directory)
    if directory.exists():raise FileExistsError('Use a new immutable artifact directory.')
    directory.mkdir(parents=True)
    members=[]
    for i,(horizons,learner) in enumerate(model.members):
        path=directory/f'model_{i:02d}.json'
        kind=model.recipe.get('kind','xgb')
        if kind=='ridge':
            imp,scale,ridge=learner.steps[0][1],learner.steps[1][1],learner.steps[2][1]
            _write_json(path,{'medians':imp.statistics_.tolist(),'indicator_columns':imp.indicator_.features_.tolist(),
                'means':scale.mean_.tolist(),'scales':scale.scale_.tolist(),
                'coefficients':ridge.coef_.tolist(),'intercept':float(ridge.intercept_)})
        else:learner.save_model(path)
        members.append({'horizons':horizons,'path':path.name,'sha256':sha256_file(path),'kind':kind})
    card={**card,'ordered_input_features':FEATURES,'feature_schema_sha256':_json_hash(FEATURES),
          'fitted_features':model.features,'recipe':model.recipe,'fit_details':model.fit_details,
          'members':members,'artifact_format':'aquaiq-isolated-accuracy-v1'}
    _write_json(directory/'model_card.json',card)
    pointer={'format':card['artifact_format'],'card_path':'model_card.json',
             'card_sha256':sha256_file(directory/'model_card.json')}
    _write_json(directory/'checkpoint.json',pointer)
    return pointer,card


def load(checkpoint, *, frame=None):
    checkpoint=Path(checkpoint).resolve()
    pointer=json.loads(checkpoint.read_text())
    card_path=(checkpoint.parent/pointer['card_path']).resolve()
    if not card_path.is_relative_to(checkpoint.parent) or sha256_file(card_path)!=pointer['card_sha256']:
        raise ValueError('Candidate card path or checksum mismatch.')
    card=json.loads(card_path.read_text())
    if (pointer.get('format')!='aquaiq-isolated-accuracy-v1'
            or card['ordered_input_features']!=FEATURES
            or card['feature_schema_sha256']!=_json_hash(FEATURES)):
        raise ValueError('Incompatible experimental feature schema.')
    members=[]
    for member in card['members']:
        path=(checkpoint.parent/member['path']).resolve()
        if not path.is_relative_to(checkpoint.parent) or sha256_file(path)!=member['sha256']:
            raise ValueError('Candidate member path or checksum mismatch.')
        if member['kind']=='ridge':learner=PortableRidge(json.loads(path.read_text()))
        else:
            learner=xgb.XGBRegressor();learner.load_model(path)
            if learner.get_booster().feature_names!=card['fitted_features']:
                raise ValueError('Fitted feature order differs from the card.')
        members.append((member['horizons'],learner))
    covered=[h for horizons,_ in members for h in horizons]
    if card['recipe'].get('kind')!='trend' and sorted(covered)!=list(range(1,13)):
        raise ValueError('Every horizon must be covered exactly once.')
    if card['recipe'].get('kind')=='trend' and frame is None:
        raise ValueError('Trend inference requires the checksum-bound source frame.')
    return Challenger(card['recipe'],card['fitted_features'],members,frame=frame,fit_details=card['fit_details']),card
