from flask import Blueprint
from db.connection import get_connection
from api.contracts import response
from models.ensemble import feature_generation,ROOT,CONFIG
from models.xgboost_model import load_model_bundle
from models.climate_forecast import load_bundle as load_climate_bundle
from models.climate_forecast_12m import load_bundle as load_climate_12m_bundle

health_bp=Blueprint('health',__name__)

@health_bp.route('/health')
def health_check():
    database=False
    model=False
    climate_model=False
    climate_12m_model=False
    connection=None
    try:
        connection=get_connection()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        database=True
        load_model_bundle(ROOT/CONFIG['paths']['xgboost_checkpoint'],expected_generation=feature_generation())
        model=True
        load_climate_bundle(expected_generation=feature_generation())
        climate_model=True
        load_climate_12m_bundle(expected_generation=feature_generation())
        climate_12m_model=True
    except Exception:
        pass
    finally:
        if connection is not None:
            connection.close()
    healthy=database and model and climate_model and climate_12m_model
    return response({'status':'healthy' if healthy else 'degraded','database':'connected' if database else 'disconnected',
        'model_loaded':model,'monthly_climate_model_loaded':climate_model,
        'climate_12m_model_loaded':climate_12m_model,
        'version':CONFIG['project']['version']},200 if healthy else 503)
