"""Isolated research routes; canonical frozen IDs never use the database resolver."""
from flask import Blueprint, current_app, request

from api.contracts import failure, response
from models import research_forecast as service
from models import research_graph as graph_service
from models import experimental_scenario as scenario_service

research_bp = Blueprint("research", __name__)


def _configuration():
    return current_app.config.get("RESEARCH_FORECAST_CONFIG_PATH")


def _validate_query(allowed):
    if set(request.args) - set(allowed):
        raise ValueError("Unsupported research query parameter; use origin_month and optional months=12.")
    if any(len(request.args.getlist(key)) != 1 for key in request.args):
        raise ValueError("Research query parameters must not be repeated.")
    if "months" in request.args and request.args["months"] != "12":
        raise ValueError("The primary research product requires months=12.")


@research_bp.route("/research/forecast")
def catalog():
    try:
        _validate_query(())
        return response(service.forecast_catalog(_configuration()))
    except service.ResearchContractError as error:
        return response(service.unavailable_response(str(error)), 503)
    except (ValueError, LookupError) as error:
        return failure(error)
    except Exception:
        return response(service.unavailable_response("Research artifacts are unavailable; no estimate was produced."), 503)


@research_bp.route("/research/forecast/<district_id>")
def forecast(district_id):
    origin = None
    try:
        _validate_query(("origin_month", "months"))
        origin = request.args.get("origin_month")
        if origin is not None:
            service.parse_month(origin)
        return response(service.research_forecast(district_id, origin, _configuration()))
    except service.ResearchContractError as error:
        return response(service.unavailable_response(str(error), district_id, origin), 503)
    except (ValueError, LookupError) as error:
        return failure(error)
    except Exception:
        return response(service.unavailable_response("Research artifacts are unavailable; no estimate was produced.", district_id, origin), 503)


@research_bp.route("/research/graph/<district_id>")
def graph(district_id):
    origin = None
    try:
        _validate_query(("origin_month", "months"))
        origin = request.args.get("origin_month")
        if origin is not None:
            service.parse_month(origin)
        return response(graph_service.research_graph(district_id, origin, _configuration()))
    except service.ResearchContractError as error:
        return response(graph_service.unavailable_graph(str(error), district_id, origin), 503)
    except (ValueError, LookupError) as error:
        return failure(error)
    except Exception:
        return response(graph_service.unavailable_graph("Research graph artifacts are unavailable; no estimate was produced.", district_id, origin), 503)


@research_bp.route("/research/scenario/<district_id>")
def scenario(district_id):
    as_of = None
    try:
        _validate_query(("as_of", "months"))
        as_of = request.args.get("as_of")
        scenario_service.parse_as_of(as_of)
        return response(scenario_service.scenario(district_id, as_of, _configuration()))
    except service.ResearchContractError as error:
        return response(scenario_service.unavailable(district_id, as_of, str(error)), 503)
    except (ValueError, LookupError) as error:
        return failure(error)
    except Exception:
        return response(scenario_service.unavailable(district_id, as_of, "Scenario source or calculation is unavailable; no estimate was produced."), 503)
