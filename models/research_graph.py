"""Twelve calendar graph slots backed only by the existing direct M+12 product.

The retained artifact estimates one endpoint, not a monthly trajectory. Slots
M+1 through M+11 deliberately contain nulls. This adapter neither interpolates
values nor loads a six-month model, trains, writes, or accesses a database.
"""
from __future__ import annotations

import math

import pandas as pd

from models import research_forecast as direct

PRODUCT = "direct_12month_research_graph"
INTERMEDIATE_REASON = (
    "No compatible artifact supplies this intermediate monthly horizon; "
    "the retained research model estimates only the direct M+12 endpoint."
)
GRAPH_LIMITATION = (
    "Twelve calendar slots are shown, not twelve supported monthly estimates. "
    "Missing intermediate values are neither interpolated nor supplied by the six-month model."
)


def _number_or_null(value):
    return value is None or type(value) in (int, float) and math.isfinite(value)


def graph_from_endpoint(endpoint):
    """Retain validated endpoint provenance and expose the honest chart shape."""
    if (not isinstance(endpoint, dict) or endpoint.get("product") != direct.PRODUCT
            or type(endpoint.get("horizon_months")) is not int or endpoint["horizon_months"] != 12
            or endpoint.get("units") != "m_bgl" or endpoint.get("status") not in ("available", "unavailable")
            or endpoint.get("output_kind") not in ("historical_research", "current_vintage_research")
            or "forecast_issued_at" not in endpoint or endpoint["forecast_issued_at"] is not None):
        raise direct.ResearchContractError("The graph requires a compatible twelve-month research endpoint.")
    origin = endpoint.get("origin_month")
    target = endpoint.get("target_month")
    if origin is not None:
        try:
            origin_date = direct.parse_month(origin)
        except ValueError:
            raise direct.ResearchContractError("Research graph origin month is incompatible.") from None
        if target != direct.target_month(origin):
            raise direct.ResearchContractError("Research graph target must equal origin plus twelve calendar months.")
    elif target is not None:
        raise direct.ResearchContractError("Research graph target requires an observed origin month.")
    for field in ("ml_estimate_m", "annual_baseline_m"):
        if field not in endpoint or not _number_or_null(endpoint[field]):
            raise direct.ResearchContractError("Research graph estimates must be finite numbers or explicit nulls.")
        if endpoint[field] is not None and (origin is None
                or endpoint.get("source", {}).get("origin_is_observed") is not True
                or endpoint.get("source", {}).get("origin_is_imputed") is not False):
            raise direct.ResearchContractError("Research graph estimates require an explicitly observed origin.")
    if endpoint["status"] == "unavailable" and endpoint["ml_estimate_m"] is not None:
        raise direct.ResearchContractError("Unavailable research ML must remain null.")
    if endpoint["status"] == "available" and endpoint["ml_estimate_m"] is None:
        raise direct.ResearchContractError("An available research ML endpoint requires its validated estimate.")
    if not isinstance(endpoint.get("unavailable_reasons"), list) or not isinstance(endpoint.get("limitations"), list):
        raise direct.ResearchContractError("Research graph limitations and unavailable reasons are required.")
    rows = []
    for horizon in range(1, 13):
        final = horizon == 12
        month = (origin_date + pd.DateOffset(months=horizon)).strftime("%Y-%m") if origin else None
        reasons = endpoint["unavailable_reasons"].copy() if final else [INTERMEDIATE_REASON]
        if final and endpoint["ml_estimate_m"] is None and not reasons:
            reasons = ["The direct M+12 ML estimate is unavailable."]
        if month is None:
            reasons.append("No source-backed origin month is available; target month labels cannot be assigned.")
        row = {"month": month, "horizon_months": horizon,
               "predicted_gwl": endpoint["ml_estimate_m"] if final else None,
               "annual_baseline_m": endpoint["annual_baseline_m"] if final else None,
               "unavailable_reasons": reasons}
        rows.append(row)
    result = {**endpoint, "product": PRODUCT, "endpoint_product": direct.PRODUCT,
              "projection_method": "direct_twelve_month_endpoint_with_explicit_monthly_gaps",
              "forecast": rows,
              "origin_observed_gwl": endpoint["annual_baseline_m"],
              "supported_ml_horizons": [12], "supported_annual_baseline_horizons": [12],
              "limitations": [*endpoint["limitations"], GRAPH_LIMITATION]}
    # Labels can be shown at the endpoint, but are never copied into predicted
    # values or used to fill the eleven unsupported intermediate horizons.
    if "observed_target_m" in endpoint and not _number_or_null(endpoint["observed_target_m"]):
        raise direct.ResearchContractError("Observed graph target is incompatible.")
    return result


def research_graph(district_id, origin_month=None, config_path=None):
    return graph_from_endpoint(direct.research_forecast(district_id, origin_month, config_path))


def unavailable_graph(reason, district_id=None, origin_month=None):
    return graph_from_endpoint(direct.unavailable_response(reason, district_id, origin_month))
