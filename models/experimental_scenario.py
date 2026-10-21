"""User-approved, file-only seasonal/trend scenarios; never active ML forecasts.

The existing robust seasonal fit is calculated in memory. No checkpoint is
trained/loaded, no database is accessed and no prospective record is archived.
Calendar filtering does not establish historical input availability.
"""
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re

import numpy as np
import pandas as pd

from models import research_forecast as source
from models import monthly_projection as seasonal
from models import scenario_sources

PRODUCT = "experimental_12month_scenario"
INDIA = timezone(timedelta(hours=5, minutes=30))
METHOD = {
    "name": "damped_seasonal_trend", "version": "experimental-12-month-v2-own-district-sources",
    "horizon_months": 12, "minimum_observations": seasonal.MIN_OBSERVATIONS,
    "minimum_span_months": seasonal.MIN_SPAN_MONTHS,
    "lookback_months": seasonal.LOOKBACK_MONTHS,
    "trend_damping_months": seasonal.TREND_DAMPING_MONTHS,
    "source": "explicit_own_district_history_source", "weather_included": False,
    "extraction_included": False, "current_month_input_policy": "exclude",
}
ASSUMPTIONS = [
    "Historical depth trend continues with damping and, when estimable, a repeating annual seasonal cycle.",
    "The gap since the last source-marked observation and the current depth are estimated; they are not new measurements.",
    "Rainfall, temperature, evapotranspiration and pumping/extraction are not inputs to this scenario.",
    "No future weather forecast, intervention effect or uncertainty interval is supplied.",
]
LIMITATIONS = [
    "Unvalidated experimental scenario: no accuracy, prospective forecasting skill or production readiness is established.",
    "These twelve monthly estimates come from a separate seasonal/trend calculation, not from extending an active six-month ML model or the historical M+12 artifact.",
    "Source dates are reported month labels. Actual acquisition and input-availability times are unverified; past as_of requests are current-vintage scenarios, not point-in-time backtests.",
    "Well-panel composition and datum continuity are unverified; district means can change when contributing wells change.",
    "No superiority to persistence or seasonal naive has been demonstrated for this scenario.",
]


def parse_as_of(value=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("The scenario clock must be timezone-aware.")
    today = now.astimezone(INDIA).date()
    if value is None:
        return today
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("as_of must be YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("as_of must be a valid YYYY-MM-DD date.") from None
    if parsed > today:
        raise ValueError("as_of cannot be in the future.")
    return parsed


def unavailable(district_id, as_of, reason, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = parse_as_of(as_of, now)
    return {
        "product": PRODUCT, "status": "unavailable", "output_kind": "assumption_based_scenario",
        "district_id": district_id, "horizon_months": 12, "units": "m_bgl",
        "as_of": cutoff.isoformat(), "as_of_timezone": "Asia/Kolkata",
        "computed_at": now.astimezone(timezone.utc).isoformat(), "forecast_issued_at": None,
        "forecast": [], "estimated_current_gwl": None,
        "source": {"availability_verified": False}, "method": METHOD.copy(),
        "validation": {"status": "unvalidated_scenario", "prospective_skill_verified": False,
                       "sufficient_for_operational_use": False},
        "assumptions": ASSUMPTIONS.copy(), "limitations": LIMITATIONS.copy(),
        "unavailable_reasons": [reason] if reason else [],
    }


def scenario(district_id, as_of=None, config_path=None, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = parse_as_of(as_of, now)
    result = unavailable(district_id, cutoff.isoformat(), None, now)
    if district_id in source.SUPPORTED:
        # Preserve the already approved source precedence and exact numeric
        # scenario for Adilabad. Its direct historical ML contract is unchanged.
        bundle = source._load_bundle(config_path)
        metadata = {"name":"Frozen Adilabad source-marked district monthly means",
                    "scope":"district_own_observed_history", "source_kind":"frozen_adilabad_research_snapshot",
                    "district_known":True, "district_name":"Adilabad", "state_name":"Telangana",
                    "units_qualification":"Source dataset reports m_bgl; per-well datum and continuity are unverified."}
    else:
        bundle = scenario_sources.load_district(district_id)
        metadata = bundle["source_metadata"]
    result["source"].update(metadata)
    if not metadata["district_known"]:
        result["unavailable_reasons"] = ["Unknown canonical district ID in the pinned local registry. No district or zone has been substituted."]
        return result
    frame = bundle["frame"]
    current_month = pd.Timestamp(cutoff).to_period("M").to_timestamp()
    # Strictly exclude the current month, even on its last day. Availability
    # cannot be inferred from a source month/date label alone.
    history = frame.loc[frame.district_id.eq(district_id) & frame._observed
                        & frame.date.lt(current_month) & frame.gwl_current.ge(0)].copy()
    result["source"].update({"feature_generation":bundle["contract"]["feature_generation_id"],
                            "source_snapshot_sha256":bundle["manifest"]["snapshot_sha256"],
                            "observed_months_available":len(history)})
    fit = seasonal.fit_projection(history, pd.Timestamp(cutoff))
    if fit is None:
        if history.empty:
            result["unavailable_reasons"] = ["No source-marked observed groundwater history is available for this district before the scenario month; filled values cannot replace observations."]
        else:
            result["source"]["last_observed_month"] = history.date.max().strftime("%Y-%m")
            result["unavailable_reasons"] = [f"Only {len(history)} source-marked observed months are available; at least 24 spanning 36 months are required. Filled, future and current-month rows are excluded; no district or zone has been substituted."]
        return result
    origin = pd.Timestamp(fit["origin"])
    last = history.loc[history.date.eq(origin)].iloc[0]
    used = history.loc[history.date.ge(pd.Timestamp(fit["history_start"])) & history.date.le(origin)]
    months = pd.period_range(pd.Period(cutoff, freq="M") + 1, periods=12, freq="M").to_timestamp()
    depths = seasonal.predict_depth(fit, months)
    current = float(seasonal.predict_depth(fit, [current_month])[0])
    if len(depths) != 12 or not np.isfinite(depths).all() or not np.isfinite(current):
        raise source.ResearchContractError("The scenario calculation did not produce twelve finite monthly estimates.")
    observed_phases = sorted(int(m) for m in used.date.dt.month.unique())
    result.update(status="scenario", estimated_current_gwl=current,
                  forecast_start=months[0].strftime("%Y-%m"), forecast_end=months[-1].strftime("%Y-%m"),
                  forecast=[{"month": month.strftime("%Y-%m"), "date": month.date().isoformat(),
                             "horizon_months": i + 1, "projected_gwl": float(value)}
                            for i, (month, value) in enumerate(zip(months, depths))])
    def optional(field):
        value = last.get(field)
        return None if value is None or pd.isna(value) else value.item() if isinstance(value, np.generic) else value
    result["source"].update({
        "feature_generation": bundle["contract"]["feature_generation_id"],
        "last_observed_month": origin.strftime("%Y-%m"), "last_observed_gwl": float(last.gwl_current),
        "data_age_months": int((current_month.year-origin.year)*12 + current_month.month-origin.month),
        "reported_date_start": optional("first_reported_date"), "reported_date_end": optional("last_reported_date"),
        "well_count": optional("well_count"), "panel_sha256": optional("panel_sha256"),
        "actual_acquisition_at": None, "input_available_at": None,
        "source_snapshot_sha256": bundle["manifest"]["snapshot_sha256"],
    })
    result["method"].update({
        "configuration_sha256": source._canonical_hash(METHOD),
        "history_sha256": fit["history_sha256"],
        "method_sha256": hashlib.sha256(Path(seasonal.__file__).read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_snapshot_sha256": bundle["manifest"]["snapshot_sha256"],
        "source_configuration_sha256": bundle["config_sha256"],
        "history_start": fit["history_start"], "history_end": origin.date().isoformat(),
        "observed_month_count": fit["observation_count"], "observed_calendar_months": observed_phases,
        "unobserved_calendar_months": sorted(set(range(1,13))-set(observed_phases)),
        "annual_seasonality": bool(fit["seasonal"]), "seasonal_cycle_assumed": bool(fit["seasonal"]),
        "parameters_saved": False,
    })
    return result
