"""AquaIQ — State-Wise Groundwater Forecasting API Routes.

Endpoints:
- GET /api/states: List of all 36 verified Indian States and Union Territories.
- GET /api/states/summary: Comparative summary with 12m forecasts and rankings.
- GET /api/predict/state/<state_id>: Full 12-month forecast and historical time series.
"""

import os
import re
from copy import deepcopy
from datetime import date, datetime, timezone
from flask import Blueprint, request

from models.state_mapping import list_states, resolve_state_id, get_state_metadata
from models.state_forecast import (
    forecast_state_twelve_months,
    get_all_states_summary,
    get_state_districts,
    aggregate_state_observations,
    PRODUCT_NAME,
    MODEL_VERSION,
)
from models import forecast_storage, state_median_storage
from models.district_registry import get_registry
from api.contracts import response, failure, parse_forecast_as_of, parse_as_of_value

state_bp = Blueprint("state", __name__)


def _median_state_prediction(state_id):
    """Read the independent experimental candidate; never launch inference."""
    canonical = resolve_state_id(state_id)
    requested_as_of = request.args.get('as_of')
    if requested_as_of is not None:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', requested_as_of):
            raise ValueError('Median candidate as_of must be YYYY-MM-DD.')
        requested_as_of = parse_as_of_value(requested_as_of)
    unavailable_reason = 'candidate_generation_missing'
    try:
        stored = state_median_storage.get_state_forecast(canonical, requested_as_of)
    except (ValueError, LookupError):
        raise
    except Exception:
        stored = None
        unavailable_reason = 'candidate_storage_unavailable'
    if stored is None:
        unavailable_as_of = requested_as_of or date.today()
        registered = sum(row['state_id'] == canonical for row in get_registry())
        stored = {
            'product': state_median_storage.PRODUCT_NAME,
            'model_version': state_median_storage.MODEL_VERSION,
            'model_name': state_median_storage.MODEL_NAME,
            'state_id': canonical,
            'state_name': get_state_metadata(canonical)['name'],
            'status': 'model_unavailable',
            'promotion_status': 'experimental',
            'evaluation_status': 'experimental',
            'units': 'm_bgl', 'horizon_months': 12,
            'as_of': unavailable_as_of.isoformat(),
            'forecast_origin': unavailable_as_of.replace(day=1).isoformat(),
            'computed_at': datetime.now(timezone.utc).isoformat(),
            'training_cutoff': None, 'model_sha256': None,
            'contributing_districts_count': 0,
            'total_districts_in_state': registered,
            'district_coverage_pct': 0.,
            'evaluation': {'status': 'not_evaluated', 'n': 0, 'mae_m': None,
                           'rmse_m': None, 'period_start': None, 'period_end': None,
                           'description': 'No persisted candidate or independent held-out evaluation is available.'},
            'history': [], 'forecast': [],
            'unavailable_reason': unavailable_reason,
            'message': 'No persisted experimental median forecast is available for this state and vintage. '
                       'Run python -m scripts.state_median_forecasts generate with candidate artifacts in an isolated test namespace.',
        }
    data = deepcopy(stored)
    data.update(requested_state_id=state_id, resolved_state_id=canonical)
    return response(data, 503 if data.get('status') == 'model_unavailable' else 200)


@state_bp.route("/states")
def get_states():
    """Return list of all 36 Indian States and Union Territories with basic coverage metadata."""
    try:
        states = list_states()
        registry = get_registry()
        results = []
        for s in states:
            districts = [r["district_id"] for r in registry if r["state_id"]==s["state_id"]]
            results.append({
                "state_id": s["state_id"],
                "state_name": s["name"],
                "state_type": s["type"],
                "st_code": s["st_code"],
                "total_districts": len(districts),
                "districts": districts,
            })
        return response({"total": len(results), "states": results,
                         "as_of": parse_forecast_as_of().isoformat(), "horizon_months": 12})
    except Exception as error:
        return failure(error)


@state_bp.route("/states/summary")
def get_states_summary():
    """Return comparative nationwide summary of all 36 states with 12-month projections."""
    try:
        horizon_arg = request.args.get("horizon", "12")
        try:
            horizon = int(horizon_arg)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid horizon '{horizon_arg}'; horizon must be an integer equal to 12.")

        if horizon != 12:
            raise ValueError(f"Only horizon=12 is supported; received horizon={horizon}.")

        cutoff = parse_forecast_as_of()
        stored = forecast_storage.get_nationwide_summary(cutoff)
        if stored is not None:
            return response(stored)

        sync_enabled = os.getenv("AQUAIQ_ENABLE_SYNC_FORECAST_FALLBACK", "false").lower() in ("true", "1")
        if not sync_enabled:
            diag = forecast_storage.get_generation_diagnostics(cutoff)
            raise RuntimeError(diag.get("message") or
                "No active persisted XGBoost forecast generation is available for this origin/model version. "
                "Run 'python -m scripts.precompute_forecasts --horizon 12' to precompute and publish forecasts.")

        data = get_all_states_summary(horizon=horizon, as_of=cutoff)
        return response(data)
    except Exception as error:
        return failure(error)


@state_bp.route("/predict/state/<state_id>")
def get_state_prediction(state_id):
    """Return the fixed-panel state XGBoost outlook and separately labelled history."""
    try:
        # Validate parameters
        horizon_arg = request.args.get("horizon", "12")
        try:
            horizon = int(horizon_arg)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid horizon '{horizon_arg}'; horizon must be an integer equal to 12.")

        if horizon != 12:
            raise ValueError(f"Only a twelve-month prediction horizon is supported; horizon must equal 12.")

        model = request.args.get('model', 'current')
        if model == 'median_xgboost':
            return _median_state_prediction(state_id)
        if model != 'current':
            raise ValueError('model must be current or median_xgboost.')

        cutoff = parse_forecast_as_of()
        canonical_state_id = resolve_state_id(state_id)

        stored = forecast_storage.get_state_forecast(canonical_state_id, cutoff)
        if stored is not None:
            data = deepcopy(stored)
            data["requested_state_id"] = state_id
            data["resolved_state_id"] = canonical_state_id
            return response(data)

        sync_enabled = os.getenv("AQUAIQ_ENABLE_SYNC_FORECAST_FALLBACK", "false").lower() in ("true", "1")
        if not sync_enabled:
            diag = forecast_storage.get_generation_diagnostics(cutoff)
            err_payload = {
                "product": PRODUCT_NAME,
                "model_version": MODEL_VERSION,
                "status": "model_unavailable",
                "state_id": canonical_state_id,
                "requested_state_id": state_id,
                "resolved_state_id": canonical_state_id,
                "forecast": [],
                "districts": get_state_districts(canonical_state_id),
                "message": diag.get("message") or f"Persistent 12-month XGBoost forecast for state '{state_id}' is not available. Run 'python -m scripts.precompute_forecasts --horizon 12' to precompute.",
                "unavailable_reason": diag.get("reason", "forecast_generation_missing"),
                "diagnostics": diag,
            }
            return response(err_payload, 503)

        data = forecast_state_twelve_months(canonical_state_id, as_of=cutoff)
        data["requested_state_id"] = state_id
        data["resolved_state_id"] = canonical_state_id
        data["districts"] = get_state_districts(canonical_state_id)

        if data.get("status") == "model_unavailable":
            return response(data, 503)
        if data.get("status") == "insufficient_data":
            # Return 200 with structured insufficient_data status so UI can gracefully display reason
            return response(data)

        return response(data)
    except Exception as error:
        return failure(error)
