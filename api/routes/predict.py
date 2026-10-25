import os
from copy import deepcopy
import math
from flask import Blueprint, request
from models.ensemble import forecast_result
from models.monthly_projection import forecast_next_six_months
from models.climate_forecast_12m import forecast_next_twelve_months, MODEL_VERSION as MODEL_VERSION_12M, PRODUCT_NAME as PRODUCT_NAME_12M
from models import forecast_storage
from api.district_resolver import resolve_district_id
from api.contracts import response, parse_as_of, parse_forecast_as_of, failure

predict_bp = Blueprint('predict', __name__)


@predict_bp.route('/predict/<district_id>')
def get_prediction(district_id):
    try:
        window = request.args.get('window', 'observed_endpoint')
        if window not in ('observed_endpoint', 'next_six_months'):
            raise ValueError('window must be observed_endpoint or next_six_months.')
        if any(key in request.args for key in ('target_year', 'year', 'start', 'start_month')):
            raise ValueError('year, target_year, start, and start_month are unsupported. Use as_of and window to select the prediction window.')
        if request.args.get('months', '6') != '6':
            raise ValueError('Only a six-month prediction horizon is supported; months must equal 6.')
        cutoff = parse_as_of()
        canonical = resolve_district_id(district_id)
        data = (forecast_next_six_months(canonical, cutoff) if window == 'next_six_months'
                else forecast_result(canonical, cutoff))
        data['requested_id'] = district_id
        data['resolved_id'] = canonical
        return response(data)
    except Exception as error:
        return failure(error)


def _validate_12m_forecast(data):
    if not isinstance(data, dict):
        raise ValueError('12-month forecast payload must be a dictionary.')
    if data.get('product') != PRODUCT_NAME_12M:
        raise ValueError('Product must be ' + PRODUCT_NAME_12M)
    if data.get('model_version') != MODEL_VERSION_12M:
        raise ValueError('Model version mismatch for 12-month climate model.')
    if data.get('horizon_months') != 12:
        raise ValueError('horizon_months must equal 12.')
    if data.get('units') != 'm_bgl':
        raise ValueError('Units must be m_bgl.')
    if data.get('status') == 'forecast':
        forecast = data.get('forecast')
        if not isinstance(forecast, list) or len(forecast) != 12:
            raise ValueError('Forecast must contain exactly 12 monthly records.')
        for idx, item in enumerate(forecast, start=1):
            if item.get('horizon') != idx:
                raise ValueError(f'Forecast item {idx} has invalid horizon.')
            gwl = item.get('predicted_gwl')
            if not isinstance(gwl, (int, float)) or not math.isfinite(gwl) or gwl < 0:
                raise ValueError(f'Forecast item {idx} has invalid predicted_gwl.')
            weather = item.get('weather')
            if not isinstance(weather, dict):
                raise ValueError(f'Forecast item {idx} missing weather object.')
            for wfield in ('rainfall_mm', 'temperature_c', 'evapotranspiration_mm'):
                val = weather.get(wfield)
                if not isinstance(val, (int, float)) or not math.isfinite(val):
                    raise ValueError(f'Forecast item {idx} weather {wfield} must be finite.')


@predict_bp.route('/predict/climate-12m/<district_id>')
def get_climate_12m_prediction(district_id):
    try:
        if any(key in request.args for key in ('target_year', 'year', 'start', 'start_month', 'window')):
            raise ValueError('Unsupported parameter for 12-month climate prediction; use as_of.')
        if request.args.get('months', '12') != '12':
            raise ValueError('Only a twelve-month prediction horizon is supported; months must equal 12.')
        cutoff = parse_forecast_as_of()
        canonical = resolve_district_id(district_id)

        stored = forecast_storage.get_district_forecast(canonical, cutoff)
        if stored is not None:
            data = deepcopy(stored)
            data['requested_id'] = district_id
            data['resolved_id'] = canonical
            return response(data)

        sync_enabled = os.getenv("AQUAIQ_ENABLE_SYNC_FORECAST_FALLBACK", "false").lower() in ("true", "1")
        if not sync_enabled:
            diag = forecast_storage.get_generation_diagnostics(cutoff)
            err_payload = {
                "product": PRODUCT_NAME_12M,
                "model_version": MODEL_VERSION_12M,
                "status": "model_unavailable",
                "district_id": canonical,
                "requested_id": district_id,
                "resolved_id": canonical,
                "forecast": [],
                "horizon_months": 12,
                "units": "m_bgl",
                "as_of": cutoff.isoformat(),
                "forecast_origin": cutoff.replace(day=1).isoformat(),
                "timezone": "Asia/Kolkata",
                "projection_method": "climate_conditioned_xgboost_12m",
                "estimated_current_gwl": None,
                "message": diag.get("message") or f"Persistent 12-month XGBoost forecast for district '{district_id}' is not available. Run 'python -m scripts.precompute_forecasts --horizon 12' to precompute.",
                "unavailable_reason": diag.get("reason", "forecast_generation_missing"),
                "diagnostics": diag,
            }
            return response(err_payload, 503)

        data = forecast_next_twelve_months(canonical, cutoff)
        _validate_12m_forecast(data)
        data['requested_id'] = district_id
        data['resolved_id'] = canonical
        if data.get('status') == 'model_unavailable':
            return response(data, 503)
        return response(data)
    except Exception as error:
        return failure(error)
