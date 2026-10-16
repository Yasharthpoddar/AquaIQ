"""Immutable prospective forecast evidence and later measured-label evaluation.

No label is synthesized, no database is written and no model is published.
Source provenance is supplied by the evaluator; its authenticity and comparable
monitoring-well coverage still require independent review.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from zoneinfo import ZoneInfo

import pandas as pd

VERSION = "aquaiq-prospective-v1"
INDIA = ZoneInfo("Asia/Kolkata")
HASHES = ("model_sha256", "model_card_file_sha256", "feature_csv_sha256",
          "feature_manifest_sha256", "config_sha256", "geography_sha256")


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _time(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tz is None:
        raise ValueError("Issue, observation and publication timestamps require an explicit timezone.")
    return stamp.tz_convert("UTC")


def _depth(value):
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError("Groundwater depths must be finite nonnegative metres below ground.") from error
    if isinstance(value, bool) or not math.isfinite(result) or result < 0:
        raise ValueError("Groundwater depths must be finite nonnegative metres below ground.")
    return result


def _hash_valid(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def create_record(forecast, model_card, provenance, *, issued_at=None):
    """Create evidence now; CLI supplies a real clock and offers no backdating."""
    issued = _time(issued_at or datetime.now(timezone.utc))
    record = {"schema_version": VERSION, "issued_at_utc": issued.isoformat(),
              "forecast": forecast, "model_card": model_card, "provenance": provenance,
              "model_card_content_sha256": checksum(model_card),
              "limitations": ["Archived estimates are not observations or validated confidence intervals.",
                  "Future evaluation requires independently obtained observed district-month depths.",
                  "Changing monitoring wells or aquifers can impair comparability."]}
    record["record_sha256"] = checksum(record)
    validate_record(record, now=issued)
    return record


def validate_record(record, *, now=None):
    now = _time(now or datetime.now(timezone.utc))
    supplied = {key: value for key, value in record.items() if key != "record_sha256"}
    if record.get("schema_version") != VERSION or checksum(supplied) != record.get("record_sha256"):
        raise ValueError("Prospective record schema/checksum mismatch.")
    issued = _time(record["issued_at_utc"])
    if issued > now:
        raise ValueError("Forecast issue timestamp is in the future.")
    forecast, provenance, card = record["forecast"], record["provenance"], record["model_card"]
    as_of = pd.Timestamp(forecast["as_of"])
    if as_of.tz is not None or as_of != as_of.normalize() or as_of.date() != issued.tz_convert(INDIA).date():
        raise ValueError("Forecast as_of must be its actual issue date in India; backdating is forbidden.")
    if forecast.get("status") != "projection" or forecast.get("units") != "m_bgl":
        raise ValueError("Only full monthly groundwater projections in m_bgl may be archived.")
    district = forecast.get("district_id")
    if not isinstance(district, str) or not district.strip() or district != provenance.get("district_id"):
        raise ValueError("An explicitly verified canonical district identity is required.")
    if any(not _hash_valid(provenance.get(key)) for key in HASHES):
        raise ValueError("Model/card/data/config/geography provenance requires SHA256 identities.")
    if (forecast.get("model_sha256") != provenance["model_sha256"] or card.get("model_sha256") != provenance["model_sha256"]
            or checksum(card) != record["model_card_content_sha256"]
            or not provenance.get("feature_generation_id")
            or forecast.get("feature_generation") != provenance["feature_generation_id"]
            or card.get("feature_generation_id") != provenance["feature_generation_id"]):
        raise ValueError("Forecast, model card and feature generation identities differ.")
    cutoff = pd.Timestamp(card.get("train_target_cutoff"))
    if pd.isna(cutoff) or cutoff.tz is not None or cutoff > as_of:
        raise ValueError("Model training cutoff must precede the forecast issue date.")
    if forecast.get("estimate_type") not in ("district_level", "zone_fallback") or not isinstance(forecast.get("weather_basis"), dict):
        raise ValueError("Evidence source and full weather assumptions are required.")
    if forecast["estimate_type"] == "zone_fallback" and not forecast.get("source_zone"):
        raise ValueError("Fallback forecasts must identify their source zone.")
    origin = as_of.to_period("M").to_timestamp()
    last = pd.Timestamp(forecast["last_observed_date"])
    if pd.isna(last) or last.tz is not None or last.day != 1 or last != last.normalize() or last > origin:
        raise ValueError("Last observation must be a real, nonfuture calendar month.")
    age = (origin.year-last.year)*12+origin.month-last.month
    if forecast.get("data_age_months") != age:
        raise ValueError("Archived observation age is inconsistent.")
    points = forecast.get("forecast", [])
    expected = [origin+pd.DateOffset(months=h) for h in range(1, 7)]
    dates = [pd.Timestamp(point["date"]) for point in points]
    if dates != expected or any(issued >= target.tz_localize(INDIA).tz_convert("UTC") for target in dates):
        raise ValueError("Six monthly targets must follow issuance and match the next calendar months.")
    for point in points:
        _depth(point["predicted_gwl"])
    if forecast.get("last_observed_gwl") is not None:
        _depth(forecast["last_observed_gwl"])
    return record


def evaluate_records(records, labels, *, now=None):
    """Join independent observed district-month labels to previously issued targets.

    labels may be a DataFrame or records. Publication must follow measurement
    and be available by now; labels for unrelated forecast keys are rejected.
    Shared targets may evaluate multiple distinct earlier issued forecasts.
    """
    now = _time(now or datetime.now(timezone.utc))
    if isinstance(labels, pd.DataFrame):
        labels = labels.to_dict("records")
    records = [validate_record(record, now=now) for record in records]
    identities = {(record["forecast"]["district_id"], record["forecast"]["as_of"],
                   record["provenance"]["model_sha256"], record["provenance"]["feature_generation_id"]) for record in records}
    if len({record["record_sha256"] for record in records}) != len(records) or len(identities) != len(records):
        raise ValueError("Duplicate forecast archives cannot inflate evidence.")
    expected = {(record["forecast"]["district_id"], point["date"][:7])
                for record in records for point in record["forecast"]["forecast"]}
    truth = {}
    required = {"district_id", "month", "depth_m_bgl", "is_observed", "is_imputed", "units", "observed_at",
                "available_at", "source", "source_record_id", "source_sha256", "geography_sha256", "evidence_origin"}
    for supplied in labels:
        if required-set(supplied):
            raise ValueError("Actual labels require observation, publication, units and source provenance.")
        row = dict(supplied)
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(row["month"])):
            raise ValueError("Label month must be YYYY-MM.")
        key = (row["district_id"], row["month"])
        if key in truth or key not in expected:
            raise ValueError("Duplicate or misaligned observed district-month labels.")
        if (str(row["is_observed"]).lower() not in ("true", "1") or str(row["is_imputed"]).lower() not in ("false", "0")
                or row["units"] != "m_bgl" or row["evidence_origin"] != "independent_measurement"):
            raise ValueError("Only independent explicitly observed, non-imputed m_bgl labels are eligible.")
        observed, available = _time(row["observed_at"]), _time(row["available_at"])
        if observed > available or available > now or observed.tz_convert(INDIA).strftime("%Y-%m") != row["month"]:
            raise ValueError("Label observation/publication dates are future or inconsistent with its month.")
        if not str(row["source"]).strip() or not str(row["source_record_id"]).strip() or not _hash_valid(row["source_sha256"]) or not _hash_valid(row["geography_sha256"]):
            raise ValueError("Actual-label source and geography provenance is missing.")
        row["depth_m_bgl"] = _depth(row["depth_m_bgl"])
        truth[key] = row
    cases, pending = [], []
    for record in records:
        forecast = record["forecast"]
        for horizon, point in enumerate(forecast["forecast"], start=1):
            key = (forecast["district_id"], point["date"][:7])
            identity = {"record_sha256": record["record_sha256"], "district_id": key[0], "month": key[1],
                        "horizon_months": horizon, "estimate_type": forecast["estimate_type"],
                        "source_zone": forecast.get("source_zone"), "data_age_months": forecast["data_age_months"]}
            if key not in truth:
                pending.append({**identity, "status": "pending_independent_observation"})
                continue
            label = truth[key]
            if label["geography_sha256"] != record["provenance"]["geography_sha256"]:
                raise ValueError("Actual-label geography differs from the archived canonical boundary version.")
            actual, prediction = label["depth_m_bgl"], _depth(point["predicted_gwl"])
            baseline = forecast.get("last_observed_gwl")
            cases.append({**identity, "actual_m_bgl": actual, "predicted_m_bgl": prediction, "error_m": actual-prediction,
                          "persistence_error_m": actual-float(baseline) if baseline is not None else None,
                          "label_source": label["source"], "label_available_at": label["available_at"]})
    def summary(part):
        errors = [row["error_m"] for row in part]
        paired = [row for row in part if row["persistence_error_m"] is not None]
        return {"n": len(part), "mae_m": sum(map(abs, errors))/len(errors) if errors else None,
            "rmse_m": math.sqrt(sum(value*value for value in errors)/len(errors)) if errors else None,
            "persistence_paired_n": len(paired),
            "paired_forecast_rmse_m": math.sqrt(sum(row["error_m"]**2 for row in paired)/len(paired)) if paired else None,
            "persistence_rmse_m": math.sqrt(sum(row["persistence_error_m"]**2 for row in paired)/len(paired)) if paired else None}
    group = lambda row: f"h{row['horizon_months']}|{row['estimate_type']}|zone_{json.dumps(row['source_zone'])}|gap_{row['data_age_months']}"
    return {"schema_version": VERSION, "status": "prospective_labels_matched" if cases else "awaiting_independent_labels",
        "evaluated_at_utc": now.isoformat(), "forecasts": len(records), "targets": len(cases)+len(pending),
        "matched_targets": len(cases), "pending_targets": len(pending),
        "matched_fraction": len(cases)/(len(cases)+len(pending)) if cases or pending else None,
        "errors": summary(cases), "groups": {key: summary([row for row in cases if group(row) == key]) for key in sorted({group(row) for row in cases})},
        "cases": cases, "pending": pending, "sufficient_for_operational_use": False,
        "limitations": ["Observed-source authenticity and comparable monitoring-station coverage require independent review.",
            "Small or dependent matched samples do not establish nationwide/current operational accuracy.",
            "This report does not calibrate prediction intervals or crisis-score thresholds."]}
