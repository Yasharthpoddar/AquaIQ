"""Versioned coverage policy layered over the unchanged state XGBoost model.

Any genuine local state median supports persistence, independently of whether
its coverage/history can support learned-model training. Asset failures never
trigger persistence. Historical targets and training eligibility are unchanged.
"""
from copy import deepcopy

import numpy as np
import pandas as pd

from db.connection import finite_json
from models import state_median_forecast as xgb
from models.ensemble import CONFIG, _as_of, _completed_feature_month
from models.state_mapping import resolve_state_id
from models.xgboost_model import sha256_file

MODEL_VERSION = '2.0-state-median-tiered'
MODEL_NAME = 'state_median_tiered'
POLICY_VERSION = '1.0-state-median-coverage'
FALLBACK_FEATURES = ['latest_genuine_state_median']
METHODS = ('state_median_xgboost', 'persistence_fallback', 'no_observations')
POLICY_DETAILS = dict(
    version=POLICY_VERSION,
    priority=list(METHODS),
    xgboost='Unchanged per-state training, coverage, chronological-validation and reference-recency safeguards.',
    persistence='With one or more genuine valid state-month medians, repeat the latest median for all twelve months when XGBoost is ineligible.',
    minimum_genuine_observations=1,
    reference='Latest genuine median of reporting district-month means, even below training coverage or stale; no other-state donors.',
    unavailable='No valid genuine observation; missing/corrupt model or source assets fail explicitly without generating a fallback.',
    normal_reporting_interval_months=int(CONFIG['crisis_score'].get('observation_interval_months', 3)),
    fallback_accuracy='Not evaluated. XGBoost backtest metrics never describe persistence fallback.')
HISTORY_FIELDS = ('date', 'gwl_m_bgl', 'training_eligible', 'contributing_districts_count',
    'total_districts_in_state', 'district_coverage_pct', 'coverage_ratio', 'observation_count', 'observation_quality')


def history_record(row):
    record = {key: row[key] for key in HISTORY_FIELDS}
    record['date'] = pd.Timestamp(record['date']).date().isoformat()
    record.update(is_observed=bool(pd.notna(record['gwl_m_bgl'])), is_forecast=False)
    return finite_json(record)


def genuine_history(state):
    """Aggregated history contains only source-marked observations or null gaps."""
    depth = pd.to_numeric(state.gwl_m_bgl, errors='coerce')
    valid = (np.isfinite(depth) & depth.ge(0) & state.contributing_districts_count.gt(0)
             & state.observation_count.gt(0)
             & state.observation_quality.isin(['coverage_qualified', 'low_coverage']))
    return state.loc[valid].sort_values('date')


def forecast_state(state_id, history, models, card, as_of, evaluation=None):
    code, cutoff = resolve_state_id(state_id), _as_of(as_of)
    if card.get('states', {}).get(code, {}).get('status') == 'trained' and code not in models:
        raise ValueError('A required verified XGBoost artifact is missing; observation-based fallback cannot hide an asset failure.')
    origin, completed = xgb._month(cutoff), _completed_feature_month(cutoff)
    state = history.loc[history.state_id.eq(code) & history.date.le(completed)].sort_values('date')
    genuine = genuine_history(state)
    # This call retains the established XGBoost quality and asset safeguards.
    result = xgb.forecast_state(code, history, models, card, as_of, evaluation)
    result.update(model_name=MODEL_NAME, model_version=MODEL_VERSION, policy_version=POLICY_VERSION,
        policy_sha256=sha256_file(__file__), genuine_observed_months=len(genuine),
        genuine_observation_count=int(genuine.observation_count.sum()),
        latest_observation_date=genuine.iloc[-1].date.date().isoformat() if len(genuine) else None,
        observation_age_months=xgb._distance(origin, genuine.iloc[-1].date) if len(genuine) else None,
        normal_reporting_interval_months=POLICY_DETAILS['normal_reporting_interval_months'],
        forecast_method='no_observations', fallback_reason=None, reference_observation=None,
        reference_training_eligible=False, reference_age_months=None, reference_is_stale=False)
    if result['status'] == 'model_unavailable':
        # Artifact/source failure is not an observation-count fallback decision.
        raise ValueError('State median assets/source are unavailable or mismatched; no persistence fallback was generated.')
    if result['status'] == 'forecast':
        result['forecast_method'] = 'state_median_xgboost'
        result['xgboost_model_version'] = xgb.MODEL_VERSION
        reference = state.loc[state.date.eq(pd.Timestamp(result['historical_reference_date']))].iloc[-1]
        result['evaluation'] = dict(result['evaluation'], forecast_method='state_median_xgboost')
    elif len(genuine):
        reference = genuine.iloc[-1]
        depth = float(reference.gwl_m_bgl)
        result.update(status='forecast', forecast_method='persistence_fallback',
            fallback_reason=result.get('message') or 'Insufficient XGBoost training or reference evidence.',
            training_cutoff=None, model_sha256=None, features=FALLBACK_FEATURES,
            historical_reference_date=reference.date.date().isoformat(), last_observed_gwl_m_bgl=depth,
            contributing_districts_count=int(reference.contributing_districts_count),
            district_coverage_pct=float(reference.district_coverage_pct),
            forecast=[dict(horizon=h, target_date=(origin+pd.DateOffset(months=h)).date().isoformat(),
                predicted_gwl=depth, units='m_bgl', is_observed=False, is_forecast=True) for h in range(1, 13)],
            message='Persistence fallback repeats the latest genuine reporting-district median; no learned trend or validated forecast skill is implied.',
            evaluation=dict(status='not_evaluated_for_fallback', forecast_method='persistence_fallback',
                n=0, mae_m=None, rmse_m=None, period_start=None, period_end=None,
                description='This observation-based persistence fallback has no attached held-out evaluation; XGBoost backtest metrics do not apply.'))
        # If the only real reading is old, retain it and every intervening null
        # month rather than hiding it outside the ordinary 60-month window.
        first = min(pd.Timestamp(result['history'][0]['date']), reference.date) if result['history'] else reference.date
        result['history'] = [history_record(row) for row in state.loc[state.date.ge(first)].to_dict('records')]
        result['limitations'] = deepcopy(xgb.LIMITATIONS) + [
            'Persistence is a constant reference forecast based on genuine local state observations, not an XGBoost prediction.',
            'Low coverage is retained honestly for this reference and does not become an eligible XGBoost training target.',
            'A stale observation keeps its original month and age; it is not a current measurement.']
    else:
        result.update(status='insufficient_data', forecast_method='no_observations',
            training_cutoff=None, model_sha256=None, features=[], forecast=[],
            historical_reference_date=None, last_observed_gwl_m_bgl=None,
            contributing_districts_count=0, district_coverage_pct=0.,
            unavailable_reason='no_genuine_observations',
            message='No valid genuine groundwater observations are available for this state at the completed input cutoff.',
            evaluation=dict(status='not_evaluated_no_observations', forecast_method='no_observations',
                n=0, mae_m=None, rmse_m=None, period_start=None, period_end=None,
                description='No genuine local state median is available; no forecast or accuracy score was invented.'))
        return finite_json(result)
    age = xgb._distance(origin, reference.date)
    result.update(reference_observation=history_record(reference),
                  reference_training_eligible=bool(reference.training_eligible),
                  reference_age_months=age,
                  reference_is_stale=age > POLICY_DETAILS['normal_reporting_interval_months'])
    return finite_json(result)
