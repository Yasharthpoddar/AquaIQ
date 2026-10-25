"""Configuration and scores from a completely published, matching model/data run."""
from flask import Blueprint
from pathlib import Path
import yaml
import pandas as pd
from db.connection import read_frame,finite_json
from db.scoring_storage import get_scoring_connection as get_connection
from models.ensemble import _load_ensemble_weights,feature_generation,_load_bundle,scoring_signature
from api.contracts import response,failure

scores_bp=Blueprint('scores',__name__)
ROOT=Path(__file__).resolve().parents[2]

@scores_bp.route('/config')
def get_config():
    config=yaml.safe_load((ROOT/'config.yaml').read_text(encoding='utf-8'))
    colors={'Safe':'#22c55e','Watch':'#eab308','Warning':'#f97316','Crisis':'#ef4444'}
    tiers={name:{'min':config['crisis_score']['tiers'][name.lower()][0],
        'max':config['crisis_score']['tiers'][name.lower()][1],'color':color} for name,color in colors.items()}
    return response({'project':config['project']['name'],'version':config['project']['version'],'tiers':tiers,
        'ensemble_weights':_load_ensemble_weights(),'features':config['features'],
        'weights_status':'validated' if config['model_hyperparameters']['ensemble'].get('validated_weights') else 'initial_uncalibrated',
        'primary_forecast':{'horizon_months':12,'product':'direct_12month_research',
            'endpoint':'/api/research/forecast/<district_id>',
            'scope_endpoint':'/api/research/forecast','prospective_skill_verified':False},
        'secondary_forecasts':[
            {'product':'legacy_observed_endpoint','horizon_months':6,'endpoint':'/api/predict/<district_id>'},
            {'product':'monthly_climate_projection','horizons_months':[1,2,3,4,5,6],
             'endpoint':'/api/predict/<district_id>?window=next_six_months'}],
        'risk_index_forecast_basis':'legacy_six_month_components_not_recalibrated_for_twelve_months'})

def latest_scores(connection):
    _,card=_load_bundle()
    generation=feature_generation()
    return read_frame('''SELECT c.district_id,d.district_name AS name,d.state,c.aquaiq_score AS score,c.tier,
        c.estimate_type,c.zone_fallback_reason,c.top_factor_1,c.top_factor_2,c.top_factor_3,c.forecast_date,
        c.last_observed_date,c.model_version,c.feature_generation,c.run_id
        FROM crisis_scores c JOIN districts d ON d.district_id=c.district_id
        WHERE c.run_id=(SELECT run_id FROM scoring_runs WHERE status='completed'
            AND feature_generation=%s AND model_version=%s AND model_sha256=%s AND scoring_signature=%s
            ORDER BY completed_at DESC LIMIT 1) ORDER BY c.district_id''',
        connection,(generation,card['version'],card.get('model_sha256',''),scoring_signature()))

def score_records(frame):
    records=frame.to_dict('records')
    if records:
        settings=yaml.safe_load((ROOT/'config.yaml').read_text(encoding='utf-8'))
        weights_status='validated' if settings['model_hyperparameters']['ensemble'].get('validated_weights') else 'initial_uncalibrated'
    for record in records:
        record['top_factors']=[record.pop(key) for key in ('top_factor_1','top_factor_2','top_factor_3') if record.get(key)]
        origin=pd.Timestamp(record.get('last_observed_date'))
        cutoff=pd.Timestamp(record.get('forecast_date'))
        record['as_of']=record.get('forecast_date')
        record['forecast_origin']=origin.date().isoformat() if not pd.isna(origin) else None
        record['forecast_target']=(origin+pd.DateOffset(months=6)).date().isoformat() if not pd.isna(origin) else None
        record['status']='unavailable' if pd.isna(record.get('score')) else 'historical_forecast' if origin+pd.DateOffset(months=6)<cutoff else 'success'
        record['weights_status']=weights_status
    return finite_json(records)

@scores_bp.route('/scores')
def get_scores():
    connection=None
    try:
        connection=get_connection()
        records=score_records(latest_scores(connection))
        tiers={name:sum(record['tier']==name for record in records) for name in ('Safe','Watch','Warning','Crisis')}
        tiers['Unknown']=sum(record['score'] is None for record in records)
        estimates={name:sum(record['estimate_type']==name for record in records) for name in ('district_level','zone_fallback','insufficient_data')}
        return response({'total':len(records),'districts':records,'tier_counts':tiers,'estimate_counts':estimates,
            'status':'success' if records else 'awaiting_complete_scoring_run'})
    except Exception as error:
        return failure(error)
    finally:
        if connection is not None:
            connection.close()
