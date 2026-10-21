"""Read-only adapter for the isolated, twelve-calendar-month research product.

This adapter never fits, writes, accesses a database, or issues a forecast.  It
checks a frozen local bundle before loading its XGBoost artifact, and permits
only historical current-vintage estimates with observed origin/target months.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from models import research_horizon as research

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "direct_12month_research"
FEATURES = ["gwl_current", "gwl_lag_3mo", "gwl_lag_6mo", "rainfall_current",
            "rainfall_3mo_avg", "monsoon_deficit_pct", "temperature",
            "evapotranspiration", "water_balance_proxy", "season_Kharif",
            "season_Rabi", "season_Zaid"]
FEATURE_UNITS = {"gwl": "m_bgl", "rainfall": "mm/month",
                 "evapotranspiration": "mm/month", "temperature": "degC"}
GENERATION = "research-telangana-exact-name-coordinate-h12-app-v1"
PROTOCOL_SHA256 = "1a93abf0a52eb44263d05090137df2c7000f83c3d0cf2c3e2843c56ac1ec57c2"
SUPPORTED = ["TS-Adilabad"]
XGB_PARAMETERS = {"n_estimators": 500, "max_depth": 6, "learning_rate": 0.01,
                  "subsample": 0.8, "random_state": 42, "objective": "reg:squarederror",
                  "n_jobs": 4, "verbosity": 0}
LIMITATIONS = [
    "Research prototype: no prospective forecasting skill or nationwide generalization is established.",
    "Name/coordinate agreement is metadata agreement, not certified geography or stable well/datum continuity.",
    "Publication, acquisition and model-availability times are unknown; M+12 does not establish twelve full months of operational lead.",
    "The annual baseline is persistence and annual seasonal naive as one effective method; ML superiority is unverified.",
    "This fixed-cutoff artifact differs from the expanding historical comparison and cannot inherit its pooled accuracy.",
]


class ResearchContractError(ValueError):
    """A public-safe contract failure without local paths or source contents."""


def _fail(message):
    raise ResearchContractError(message)


def _canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _reject_constant(value):
    _fail("Research JSON contains a nonfinite value.")


def _read_json(path):
    try:
        result = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("A required research artifact is missing or unreadable.")
    if not isinstance(result, dict):
        _fail("Research metadata must be a JSON object.")
    return result


def _sensitive_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if any(word in normalized for word in ("cookie", "authorization", "password", "secret", "token", "credential")):
                return True
            if _sensitive_keys(item):
                return True
    elif isinstance(value, list):
        return any(_sensitive_keys(item) for item in value)
    return False


def parse_month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("origin_month must be YYYY-MM.")
    try:
        return pd.Timestamp(value + "-01")
    except (ValueError, OverflowError):
        raise ValueError("origin_month must be a valid YYYY-MM calendar month.") from None


def target_month(origin_month):
    return (parse_month(origin_month) + pd.DateOffset(months=12)).strftime("%Y-%m")


def _artifact_path(relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        _fail("Research artifact paths must remain in their dedicated namespace.")
    resolved = (ROOT / relative).resolve()
    base = (ROOT / "reports" / "candidates").resolve()
    try:
        parts = resolved.relative_to(base).parts
    except ValueError:
        _fail("Research artifact paths must remain in their dedicated namespace.")
    if not parts or not parts[0].startswith("twelve_month_horizon_") or parts[0] == "twelve_month_horizon_":
        _fail("Research artifact paths must remain in their dedicated namespace.")
    return resolved


def _child(parent, basename):
    if (not isinstance(basename, str) or not basename or "/" in basename or "\\" in basename
            or Path(basename).name != basename or basename in (".", "..")):
        _fail("Research bundle members require confined filenames.")
    path = (parent / basename).resolve()
    if path.parent != parent.resolve():
        _fail("Research bundle member escapes its directory.")
    return _artifact_path(str(path.relative_to(ROOT.resolve())))


def _verify_hash(path, expected):
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        _fail("Research artifact checksum metadata is invalid.")
    try:
        actual = research.sha256_file(path)
    except OSError:
        _fail("A required research artifact is missing or unreadable.")
    if actual != expected:
        _fail("Research artifact checksum mismatch; estimates are blocked.")


def _observed(frame):
    def flag(series):
        return series.astype("string").str.strip().str.lower().map({"true": True, "false": False, "1": True, "0": False})
    return (flag(frame.is_observed).eq(True) & flag(frame.is_imputed).eq(False)
            & np.isfinite(pd.to_numeric(frame.gwl_current, errors="coerce")))


def _load_bundle(config_path=None):
    """Validate identities and all bytes before estimator deserialization."""
    config_path = Path(config_path) if config_path else ROOT / "research" / "twelve_month_app.json"
    config = _read_json(config_path)
    contract = config.get("contract")
    if not isinstance(contract, dict) or config.get("contract_sha256") != _canonical_hash(contract):
        _fail("Research configuration checksum is incompatible.")
    required = {"schema_version": 1, "product": PRODUCT, "horizon_months": 12,
                "embargo_months": 12, "features": FEATURES, "feature_units": FEATURE_UNITS,
                "units": "m_bgl", "feature_generation_id": GENERATION,
                "supported_district_ids": SUPPORTED, "allowed_use": "historical_research_only",
                "train_target_cutoff": "2021-12-31", "first_allowed_origin": "2023-01",
                "max_weather_carry_months": 2, "max_gwl_carry_months": 3}
    if any(contract.get(key) != value or (isinstance(value, int) and type(contract.get(key)) is not int)
           for key, value in required.items()):
        _fail("Research horizon, feature, units, scope or training-cutoff contract is incompatible.")
    protocol = contract.get("protocol_sha256")
    if protocol != PROTOCOL_SHA256:
        _fail("Research protocol identity is invalid.")
    manifest_path = _artifact_path(config.get("manifest_path"))
    _verify_hash(manifest_path, config.get("manifest_sha256"))
    manifest = _read_json(manifest_path)
    if (type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1
            or manifest.get("contract_sha256") != config["contract_sha256"]):
        _fail("Research manifest contract is incompatible.")
    paths = {}
    for prefix in ("card", "snapshot", "input_provenance", "provenance"):
        paths[prefix] = _child(manifest_path.parent, manifest.get(prefix + "_path"))
        _verify_hash(paths[prefix], manifest.get(prefix + "_sha256"))
    card = _read_json(paths["card"])
    try:
        research.validate_card(card, 12, protocol, FEATURES)
    except (ValueError, TypeError, KeyError):
        _fail("Research model card horizon, schema, units or protocol is incompatible.")
    if (card.get("family") != "xgboost" or card.get("shadow_artifact_approved") is not False
            or card.get("configuration_sha256") != config["contract_sha256"]
            or card.get("feature_generation_id") != GENERATION
            or card.get("supported_district_ids") != SUPPORTED
            or card.get("feature_units") != FEATURE_UNITS
            or card.get("train_target_cutoff") != contract["train_target_cutoff"]):
        _fail("Research model generation, scope, configuration or cutoff is incompatible.")
    settings = card.get("settings", {})
    if not isinstance(settings, dict) or settings.get("parameters") != XGB_PARAMETERS:
        _fail("Research estimator settings differ from the locked fixed-settings protocol.")
    _verify_hash(_child(paths["card"].parent, card.get("model_path")), card.get("model_sha256"))
    provenance = _read_json(paths["provenance"])
    inputs = _read_json(paths["input_provenance"])
    if any(_sensitive_keys(value) for value in (config, manifest, card, provenance, inputs)):
        _fail("Research metadata contains security-sensitive fields; loading is blocked.")
    if (type(inputs.get("schema_version")) is not int or inputs.get("schema_version") != 1
            or inputs.get("feature_generation_id") != GENERATION or not isinstance(inputs.get("rows"), list)):
        _fail("Research input-provenance schema or generation is incompatible.")
    input_mapping = {}
    for entry in inputs["rows"]:
        if not isinstance(entry, dict) or entry.get("district_id") not in SUPPORTED:
            _fail("Research input-provenance scope is incompatible.")
        try:
            input_date = pd.Timestamp(entry.get("date"))
        except (ValueError, TypeError):
            _fail("Research input-provenance month is invalid.")
        if pd.isna(input_date) or input_date.tzinfo is not None or input_date.day != 1 or input_date != input_date.normalize():
            _fail("Research input-provenance month is invalid.")
        key = input_date.strftime("%Y-%m")
        flags = entry.get("inputs")
        if key in input_mapping or not isinstance(flags, list) or any(not isinstance(flag, dict) for flag in flags):
            _fail("Research input-provenance rows are ambiguous or incomplete.")
        names = [flag.get("feature") for flag in flags]
        if names != FEATURES:
            _fail("Research input-provenance feature order is incompatible.")
        input_mapping[key] = {flag["feature"]: flag for flag in flags}
    try:
        frame = pd.read_csv(paths["snapshot"], dtype={"district_id": str})
        required_columns = {"district_id", "date", "is_observed", "is_imputed", "units", "feature_generation",
                            "first_reported_date", "last_reported_date", "well_count", "panel_sha256", *FEATURES}
        if required_columns - set(frame) or frame.empty:
            _fail("Research feature snapshot schema is incomplete.")
        frame["date"] = pd.to_datetime(frame.date, errors="raise")
        # The frozen calendar grid omits measurement units on padded months
        # that contain no observation. These rows cannot supply a baseline or
        # target label; every observed row must explicitly declare m_bgl.
        unit_ok = frame.units.eq("m_bgl") | (frame.units.isna() & ~_observed(frame))
        if (frame.date.isna().any() or (frame.date.dt.day != 1).any()
                or (frame.date != frame.date.dt.normalize()).any()
                or frame.duplicated(["district_id", "date"]).any()
                or not frame.district_id.isin(SUPPORTED).all()
                or not unit_ok.all() or not frame.feature_generation.eq(GENERATION).all()):
            _fail("Research feature dates, scope, units or source generation are incompatible.")
        for feature in FEATURES:
            frame[feature] = pd.to_numeric(frame[feature], errors="raise")
        frame["_observed"] = _observed(frame)
    except ResearchContractError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        _fail("Research feature snapshot is unreadable or incompatible.")
    return {"contract": contract, "config_sha256": config["contract_sha256"], "manifest": manifest,
            "card": card, "card_path": paths["card"], "frame": frame, "inputs": input_mapping}


def _scope():
    return {"supported_district_ids": SUPPORTED.copy(), "metadata_agreement_only": True,
            "description": "Adilabad strict source-name/coordinate-agreement reaggregation only; geographic verification and generalization remain unestablished."}


def _model_metadata(bundle):
    card = bundle["card"]
    return {"family": card["family"], "train_target_cutoff": card["train_target_cutoff"],
            "model_sha256": card["model_sha256"], "card_sha256": bundle["manifest"]["card_sha256"],
            "configuration_sha256": bundle["config_sha256"], "protocol_sha256": card["protocol_sha256"],
            "feature_generation_id": card["feature_generation_id"],
            "supported_district_ids": card["supported_district_ids"]}


def _base(district_id=None, origin=None):
    return {"product": PRODUCT, "horizon_months": 12, "units": "m_bgl", "status": "unavailable",
            "district_id": district_id, "output_kind": "current_vintage_research",
            "origin_month": origin, "target_month": target_month(origin) if origin else None,
            "ml_estimate_m": None, "annual_baseline_m": None,
            "source": {"name": "Retained SGWD-Telangana monthly research data with existing IMD/ERA5 weather",
                       "latest_observed_month": None, "origin_is_observed": False, "origin_is_imputed": False,
                       "input_flags": [], "reported_date_start": None, "reported_date_end": None,
                       "well_count": None, "panel_sha256": None, "availability_verified": False,
                       "datum_continuity_verified": False, "actual_acquisition_at": None},
            "model": None, "scope": _scope(), "unavailable_reasons": [], "limitations": LIMITATIONS.copy(),
            "forecast_issued_at": None, "computed_at": datetime.now(timezone.utc).isoformat()}


def unavailable_response(reason, district_id=None, origin=None):
    result = _base(district_id, origin)
    result["unavailable_reasons"] = [reason]
    return result


def forecast_catalog(config_path=None):
    bundle = _load_bundle(config_path)
    observed = bundle["frame"].loc[bundle["frame"]._observed]
    districts = []
    for district in SUPPORTED:
        selected = observed.loc[observed.district_id.eq(district)]
        districts.append({"district_id": district, "name": "Adilabad", "state": "Telangana",
                          "latest_observed_month": selected.date.max().strftime("%Y-%m") if len(selected) else None,
                          "origin_months": selected.loc[selected.date.ge(parse_month(bundle["contract"]["first_allowed_origin"])),
                                                        "date"].dt.strftime("%Y-%m").sort_values().tolist()})
    return {"product": PRODUCT, "horizon_months": 12, "units": "m_bgl", "status": "available",
            "districts": districts, "model": _model_metadata(bundle), "scope": _scope(),
            "limitations": LIMITATIONS.copy(), "forecast_issued_at": None,
            "computed_at": datetime.now(timezone.utc).isoformat()}


def _input_flags(bundle, row, origin):
    mapping = bundle["inputs"].get(origin.strftime("%Y-%m"), {})
    if not isinstance(mapping, dict):
        mapping = {}
    flags, reasons = [], []
    valid_status = {"observed", "derived_from_observed", "derived_with_carried_input", "carried_forward", "calendar"}
    for feature in FEATURES:
        saved = mapping.get(feature, {})
        if not isinstance(saved, dict):
            saved = {}
        flag = {"feature": feature, "status": saved.get("status", "unknown"),
                "source_month": saved.get("source_month"), "age_months": saved.get("age_months"),
                "required_month": saved.get("required_month")}
        flags.append(flag)
        if not np.isfinite(row[feature]):
            flag["status"] = "missing"
            reasons.append("Required input is missing: " + feature + ".")
            continue
        if flag["status"] not in valid_status:
            reasons.append("Input provenance is unknown or unavailable: " + feature + ".")
            continue
        try:
            source = parse_month(flag["source_month"])
            required = parse_month(flag["required_month"])
        except ValueError:
            reasons.append("Input source month is unknown: " + feature + ".")
            continue
        if source > required or required > origin:
            reasons.append("Future source month is forbidden: " + feature + ".")
        age = flag["age_months"]
        maximum = bundle["contract"]["max_gwl_carry_months"] if feature.startswith("gwl_") else bundle["contract"]["max_weather_carry_months"]
        if type(age) is not int or age < 0 or age > maximum:
            reasons.append("Input is stale or its carry age is unknown: " + feature + ".")
        elif flag["status"] in {"observed", "calendar"} and age != 0:
            reasons.append("Observed/calendar input has inconsistent carry provenance: " + feature + ".")
        if feature.startswith("gwl_"):
            lag = 3 if feature == "gwl_lag_3mo" else 6 if feature == "gwl_lag_6mo" else 0
            if (required != origin - pd.DateOffset(months=lag)
                    or type(age) is int and age >= 0 and source != required - pd.DateOffset(months=age)):
                reasons.append("Groundwater lag source month is incompatible: " + feature + ".")
        elif feature in {"rainfall_current", "temperature", "evapotranspiration"} or feature.startswith("season_"):
            if (required != origin or type(age) is int and age >= 0
                    and source != required - pd.DateOffset(months=age)):
                reasons.append("Input source month and carry age are incompatible: " + feature + ".")
        if flag["status"].startswith("derived_"):
            dependencies = saved.get("dependencies")
            if not isinstance(dependencies, list) or not dependencies:
                reasons.append("Derived input dependencies are unknown: " + feature + ".")
            elif not _dependencies_valid(dependencies, origin, maximum):
                reasons.append("Derived input contains future, stale or unknown dependencies: " + feature + ".")
    return flags, reasons


def _dependencies_valid(dependencies, origin, maximum):
    for item in dependencies:
        if not isinstance(item, dict):
            return False
        status, age = item.get("status"), item.get("age_months")
        if status not in {"observed", "derived_from_observed", "derived_with_carried_input", "carried_forward", "calendar"}:
            return False
        try:
            source, required = parse_month(item.get("source_month")), parse_month(item.get("required_month"))
        except ValueError:
            return False
        if (source > required or required > origin or type(age) is not int or not 0 <= age <= maximum
                or status in {"observed", "calendar"} and age != 0):
            return False
        if status in {"observed", "carried_forward", "calendar"} and source != required - pd.DateOffset(months=age):
            return False
        if status.startswith("derived_"):
            nested = item.get("dependencies")
            if not isinstance(nested, list) or not nested or not _dependencies_valid(nested, origin, maximum):
                return False
    return True


def research_forecast(district_id, origin_month=None, config_path=None):
    if origin_month is not None:
        parse_month(origin_month)
    result = _base(district_id, origin_month)
    bundle = _load_bundle(config_path)
    result["model"] = _model_metadata(bundle)
    if district_id not in SUPPORTED:
        result["unavailable_reasons"].append("District is outside the isolated research artifact's supported Adilabad scope.")
        return result
    frame = bundle["frame"].loc[bundle["frame"].district_id.eq(district_id)]
    observed = frame.loc[frame._observed]
    if observed.empty:
        result["unavailable_reasons"].append("No explicitly observed source groundwater month is available.")
        return result
    latest = observed.date.max()
    result["source"]["latest_observed_month"] = latest.strftime("%Y-%m")
    origin = parse_month(origin_month) if origin_month else latest
    result["origin_month"] = origin.strftime("%Y-%m")
    result["target_month"] = target_month(result["origin_month"])
    selected = frame.loc[frame.date.eq(origin)]
    if len(selected) != 1:
        result["unavailable_reasons"].append("The exact requested origin month is absent; no fallback origin was used.")
        return result
    row = selected.iloc[0]
    source = result["source"]
    source["origin_is_observed"] = bool(row._observed)
    source["origin_is_imputed"] = str(row.is_imputed).lower() in ("true", "1")
    for source_key, column in (("reported_date_start", "first_reported_date"), ("reported_date_end", "last_reported_date"),
                               ("well_count", "well_count"), ("panel_sha256", "panel_sha256")):
        source[source_key] = row[column] if pd.notna(row[column]) else None
    if row._observed:
        result["annual_baseline_m"] = float(row.gwl_current)
    else:
        result["unavailable_reasons"].append("An explicitly observed origin is required; imputed or missing origins cannot supply the annual baseline.")
    flags, input_reasons = _input_flags(bundle, row, origin)
    source["input_flags"] = flags
    result["unavailable_reasons"].extend(input_reasons)
    if origin < parse_month(bundle["contract"]["first_allowed_origin"]):
        result["unavailable_reasons"].append("Origin precedes the frozen training-cutoff and twelve-month embargo boundary.")
    target = parse_month(result["target_month"])
    target_rows = frame.loc[frame.date.eq(target) & frame._observed]
    if target_rows.empty:
        result["unavailable_reasons"].append("This artifact permits historical research only; no observed exact M+12 target is archived for this origin.")
    else:
        result["output_kind"] = "historical_research"
        result["observed_target_m"] = float(target_rows.iloc[0].gwl_current)
    if result["unavailable_reasons"]:
        return result
    # Only origin features enter prediction.  Target labels above classify the
    # retrospective product and are never included in the estimator inputs.
    try:
        model, _ = research.load_research_model(bundle["card_path"], 12,
                                                bundle["contract"]["protocol_sha256"], FEATURES)
        prediction = np.asarray(model.predict(pd.DataFrame([row[FEATURES].to_dict()], columns=FEATURES)), dtype=float)
    except Exception:
        _fail("The compatible research estimator could not produce an estimate.")
    if prediction.shape != (1,) or not np.isfinite(prediction).all():
        _fail("The research estimator returned a nonfinite or incompatible estimate.")
    result["ml_estimate_m"] = float(prediction[0])
    result["status"] = "available"
    return result
