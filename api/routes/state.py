"""AquaIQ — State-Wise Groundwater Forecasting API Routes.

Endpoints:
- GET /api/states: List of all 36 verified Indian States and Union Territories.
- GET /api/states/summary: Comparative summary with 12m forecasts and rankings.
- GET /api/predict/state/<state_id>: Full 12-month forecast and historical time series.
"""

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
from api.contracts import response, failure, parse_as_of

state_bp = Blueprint("state", __name__)


@state_bp.route("/states")
def get_states():
    """Return list of all 36 Indian States and Union Territories with basic coverage metadata."""
    try:
        states = list_states()
        results = []
        for s in states:
            districts = get_state_districts(s["state_id"])
            results.append({
                "state_id": s["state_id"],
                "state_name": s["name"],
                "state_type": s["type"],
                "st_code": s["st_code"],
                "total_districts": len(districts),
                "districts": districts,
            })
        return response({"total": len(results), "states": results})
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

        cutoff = parse_as_of()
        data = get_all_states_summary(horizon=horizon, as_of=cutoff)
        return response(data)
    except Exception as error:
        return failure(error)


@state_bp.route("/predict/state/<state_id>")
def get_state_prediction(state_id):
    """Return 12-month state-wise groundwater depth forecast, history, baselines and metrics."""
    try:
        # Validate parameters
        horizon_arg = request.args.get("horizon", "12")
        try:
            horizon = int(horizon_arg)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid horizon '{horizon_arg}'; horizon must be an integer equal to 12.")

        if horizon != 12:
            raise ValueError(f"Only a twelve-month prediction horizon is supported; horizon must equal 12.")

        cutoff = parse_as_of()
        canonical_state_id = resolve_state_id(state_id)

        data = forecast_state_twelve_months(canonical_state_id, as_of=cutoff)
        data["requested_state_id"] = state_id
        data["resolved_state_id"] = canonical_state_id
        data["districts"] = get_state_districts(canonical_state_id)

        if data.get("status") == "insufficient_data":
            # Return 200 with structured insufficient_data status so UI can gracefully display reason
            return response(data)

        return response(data)
    except Exception as error:
        return failure(error)
