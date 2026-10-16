"""Candidate-only, chronological replay and empirical forecast intervals.

This module never loads a database, fits/publishes a model, or alters serving.
Replay hides groundwater measurements before calling the complete serving
forecast via an injected callable. Intervals are experimental summaries of
separately reserved calibration errors, not a current-period confidence claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np
import pandas as pd

VERSION = "1.1-gap-source-zone-forecast-replay"
SOURCES = {"district_level", "zone_fallback"}
IDENTITY = ["district_id", "origin_date", "horizon_months", "requested_gap_months"]
WARNINGS = [
    "Experimental historical replay; source publication dates and data revisions are unavailable.",
    "Calendar truncation does not reconstruct the historical data-release vintage.",
    "Residuals are dependent across districts, shared zones, overlapping origins and targets.",
    "Finite-sample residual ranks do not establish exchangeability or guaranteed coverage.",
    "Historical empirical coverage does not validate current projections or new gap/source regimes.",
    "Calibration data must have been reserved independently of model and hyperparameter selection.",
]


def _date(value, name, month_start=False):
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a valid date.") from exc
    if pd.isna(result) or result.tz is not None or result != result.normalize():
        raise ValueError(f"{name} must be a timezone-free calendar date.")
    if month_start and result.day != 1:
        raise ValueError(f"{name} must be a calendar month start.")
    return result


def _month_distance(later, earlier):
    return (later.year-earlier.year)*12 + later.month-earlier.month


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _integer(value, name, minimum=0, maximum=None):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be an integer.")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if not math.isfinite(number) or number != int(number) or number < minimum or (maximum is not None and number > maximum):
        raise ValueError(f"{name} is outside the allowed integer range.")
    return int(number)


@dataclass(frozen=True)
class TemporalProtocol:
    """Starts constrain replay origins; ends constrain both origins and labels.

    Entire forecast paths/labels remain inside their assigned stage. Fit labels
    end at fit_end, development starts after a six-month embargo, calibration
    starts strictly after development labels, and evaluation starts strictly
    after calibration labels. No evaluation residual enters calibration.
    """

    fit_start: str
    fit_end: str
    development_start: str
    development_end: str
    calibration_start: str
    calibration_end: str
    evaluation_start: str
    evaluation_end: str

    def __post_init__(self):
        dates = {name: _date(value, name, month_start=name.endswith("start"))
                 for name, value in asdict(self).items()}
        if dates["fit_start"] > dates["fit_end"]:
            raise ValueError("Fit dates must form a chronological range.")
        for split in ("development", "calibration", "evaluation"):
            if dates[split+"_end"] < dates[split+"_start"] + pd.DateOffset(months=1):
                raise ValueError(f"{split} must allow at least one future monthly target.")
        first_origin = (dates["fit_end"].to_period("M")+7).to_timestamp()
        if dates["development_start"] < first_origin:
            raise ValueError("Development origins must follow a six-month fit-label embargo.")
        if dates["calibration_start"] <= dates["development_end"] or dates["evaluation_start"] <= dates["calibration_end"]:
            raise ValueError("Development, calibration and evaluation ranges must be separate and chronological.")

    @property
    def sha256(self):
        return _hash(asdict(self))

    def window(self, split):
        if split not in ("development", "calibration", "evaluation"):
            raise ValueError("Unknown replay split.")
        return _date(getattr(self, split+"_start"), "start"), _date(getattr(self, split+"_end"), "end")

    def validate_model(self, metadata):
        required = ("model_sha256", "feature_generation_id", "train_target_cutoff")
        if any(not isinstance(metadata.get(key), str) or not metadata[key].strip() for key in required):
            raise ValueError("Verified model hash, feature generation and training cutoff are required.")
        if _date(metadata["train_target_cutoff"], "model cutoff") > _date(self.fit_end, "fit end"):
            raise ValueError("Model training labels extend beyond the reserved fit period.")
        if _date(metadata["train_target_cutoff"], "model cutoff") < _date(self.fit_start, "fit start"):
            raise ValueError("Model training cutoff precedes the declared fit window.")


def age_bin(age):
    age = _integer(age, "data_age_months")
    if age == 0:
        return "0"
    if age <= 3:
        return "1_3"
    if age <= 12:
        return "4_12"
    if age <= 36:
        return "13_36"
    return "37_plus"


def _observed(frame):
    if "is_observed" not in frame:
        raise ValueError("Explicit observation provenance is required.")
    flags = frame.is_observed.astype("string").str.strip().str.lower().map(
        {"true": True, "1": True, "false": False, "0": False})
    if flags.isna().any():
        raise ValueError("Unknown observation provenance is not an observed label.")
    return flags.astype(bool)


def prepare_replay_frame(frame):
    if {"district_id", "date", "gwl_current", "is_observed"} - set(frame):
        raise ValueError("Replay requires district/month groundwater and observation provenance.")
    result = frame.copy()
    result["date"] = pd.to_datetime(result.date, errors="raise")
    if result.empty or result.date.isna().any() or result.date.dt.tz is not None or (result.date.dt.day != 1).any() or (result.date != result.date.dt.normalize()).any():
        raise ValueError("Replay requires nonempty calendar month-start rows.")
    if result.district_id.isna().any() or result.district_id.astype(str).str.strip().eq("").any():
        raise ValueError("Replay district identities cannot be empty.")
    result["district_id"] = result.district_id.astype(str)
    if result.duplicated(["district_id", "date"]).any():
        raise ValueError("Duplicate district-month replay rows.")
    result["is_observed"] = _observed(result)
    result["gwl_current"] = pd.to_numeric(result.gwl_current, errors="coerce")
    observed = result.loc[result.is_observed, "gwl_current"]
    if not np.isfinite(observed).all() or (observed < 0).any():
        raise ValueError("Observed replay labels must be finite nonnegative depths.")
    result = result.sort_values(["district_id", "date"]).reset_index(drop=True)
    result.attrs.update(frame.attrs)
    return result


def groundwater_snapshot(frame, origin, requested_gap_months):
    """Hide all later measurements, including zone peers, and rebuild GWL lags.

    A uniform reporting gap is simulated across the panel. Climate information
    remains available only through the completed origin month. This does not
    simulate asynchronous district reporting delays or historical releases.
    """
    origin = _date(origin, "origin", month_start=True)
    gap = _integer(requested_gap_months, "requested_gap_months", maximum=120)
    visible = origin-pd.DateOffset(months=gap)
    snapshot = frame.loc[frame.date <= origin].copy()
    snapshot["is_observed"] = _observed(snapshot) & (snapshot.date <= visible)
    # Never retain an imputed value or lag derived from a hidden measurement.
    parts = []
    for _, rows in snapshot.groupby("district_id", sort=True):
        rows = rows.sort_values("date").copy()
        # Reindex before LOCF/lagging so missing calendar rows cannot compress time.
        grid = pd.date_range(rows.date.min(), origin, freq="MS")
        district_id = str(rows.district_id.iloc[0])
        rows = rows.set_index("date").reindex(grid).rename_axis("date").reset_index()
        rows["district_id"] = district_id
        rows["is_observed"] = rows.is_observed.fillna(False).astype(bool)
        raw = rows.gwl_current.where(rows.is_observed)
        rows["gwl_current"] = raw.ffill(limit=3)
        rows["is_imputed"] = ~rows.is_observed & rows.gwl_current.notna()
        for lag in (3, 6):
            rows[f"gwl_lag_{lag}mo"] = rows.gwl_current.shift(lag)
        for lower, upper in (("gwl_current", "GWL_current"), ("gwl_lag_3mo", "GWL_lag_3mo"), ("gwl_lag_6mo", "GWL_lag_6mo")):
            if upper in rows:
                rows[upper] = rows[lower]
        since = rows.date.where(rows.is_observed).ffill()
        rows["months_since_observation"] = [float(_month_distance(d, prior)) if pd.notna(prior) else np.nan for d, prior in zip(rows.date, since)]
        parts.append(rows)
    if not parts:
        raise ValueError("Replay origin precedes every feature row.")
    result = pd.concat(parts, ignore_index=True)
    result.attrs.update(frame.attrs)
    return result, visible


def in_memory_evidence_provider(*, generation, zones=None, readiness_start="2002-01-01",
                                minimum_observations=24, minimum_coverage_pct=60., interval_months=3):
    """Return a DB-free counterpart to current district/zone evidence selection.

    zones maps canonical district IDs to existing agro-climatic zone names. Zone
    groundwater is the mean of reporting observed districts in each month,
    exactly as in the serving SQL; these means are not labelled district truth.
    """
    zones = dict(zones or {})
    start = _date(readiness_start, "readiness_start")
    minimum_observations = _integer(minimum_observations, "minimum observations", minimum=1)
    interval_months = _integer(interval_months, "monitoring interval", minimum=1)
    if not math.isfinite(float(minimum_coverage_pct)) or not 0 < float(minimum_coverage_pct) <= 100:
        raise ValueError("Monitoring coverage threshold must be in (0,100].")

    def readiness(frame, origin):
        count = int(frame.loc[_observed(frame) & np.isfinite(frame.gwl_current), "date"].nunique())
        expected = max(1, math.ceil(max(1, _month_distance(origin, start)+1)/interval_months))
        coverage = min(100., 100.*count/expected)
        return {"observed_months": count, "expected_monitoring_rounds": expected,
                "readiness_score": round(coverage, 1),
                "eligible": count >= minimum_observations and coverage >= minimum_coverage_pct}

    def provider(district_id, as_of, panel):
        origin = _date(as_of, "as_of").to_period("M").to_timestamp()
        frame = panel.loc[panel.district_id == district_id].copy()
        if frame.empty:
            raise ValueError("Unknown district in replay panel.")
        ready = readiness(frame, origin)
        source, zone, reason = "district_level", None, None
        if not ready["eligible"]:
            source, zone = "zone_fallback", zones.get(district_id)
            reason = "District monitoring history is insufficient in the replay snapshot."
            if zone:
                peers = panel.loc[panel.district_id.map(zones) == zone].copy()
                peers.loc[~_observed(peers), "gwl_current"] = np.nan
                numeric = [name for name in ("gwl_current", "gwl_lag_3mo", "gwl_lag_6mo",
                    "rainfall_current", "rainfall_3mo_avg", "monsoon_deficit_pct", "temperature",
                    "evapotranspiration", "water_balance_proxy") if name in peers]
                frame = peers.groupby("date", as_index=False)[numeric].mean()
                flags = peers.groupby("date").is_observed.any()
                frame["is_observed"] = frame.date.map(flags).astype(bool)
                original = frame.gwl_current.copy()
                frame["gwl_current"] = original.ffill(limit=3)
                frame["is_imputed"] = original.isna() & frame.gwl_current.notna()
                for lag in (3, 6):
                    frame[f"gwl_lag_{lag}mo"] = frame.gwl_current.shift(lag)
                frame["crop_season_flag"] = frame.date.dt.month.map(
                    lambda month: "Kharif" if 6 <= month <= 10 else "Rabi" if month in (11, 12, 1, 2, 3) else "Zaid")
                ready["zone_readiness"] = readiness(frame, origin)
                if not ready["zone_readiness"]["eligible"]:
                    source = "insufficient_data"
            else:
                source = "insufficient_data"
        history = frame.loc[_observed(frame) & np.isfinite(frame.gwl_current)].copy()
        return {"district_id": district_id, "as_of": _date(as_of, "as_of"),
                "generation": generation, "frame": frame, "history": history,
                "origin": history.date.max() if len(history) else None,
                "estimate_type": source, "zone": zone if source == "zone_fallback" else None,
                "reason": reason, "readiness": ready}
    return provider


def replay_forecasts(frame, protocol, model_metadata, *, evidence_provider, predictor,
                     splits=("calibration", "evaluation"), gaps=(0, 3, 12, 36), district_ids=None):
    """Replay the full predictor; truth is joined only after prediction returns.

    predictor(evidence) must invoke the complete forecasting path, not only the
    XGBoost delta. evidence_provider(district_id, month_end, snapshot) receives
    no rows later than the origin and no observations later than the gap cutoff.
    """
    protocol.validate_model(model_metadata)
    frame = prepare_replay_frame(frame)
    gaps = tuple(_integer(gap, "requested_gap_months", maximum=120) for gap in gaps)
    if not gaps or len(set(gaps)) != len(gaps):
        raise ValueError("Replay gaps must be nonempty and unique.")
    if not splits or len(set(splits)) != len(splits):
        raise ValueError("Replay splits must be nonempty and unique.")
    districts = sorted(frame.district_id.unique()) if district_ids is None else list(district_ids)
    if not districts or len(set(districts)) != len(districts) or set(districts)-set(frame.district_id):
        raise ValueError("Replay districts must be nonempty, unique canonical panel IDs.")
    truth = frame.loc[frame.is_observed].set_index(["district_id", "date"]).gwl_current
    records, skipped = [], []
    for split in splits:
        start, end = protocol.window(split)
        for origin in pd.date_range(start, end-pd.DateOffset(months=1), freq="MS"):
            as_of = origin+pd.offsets.MonthEnd(0)
            for gap in gaps:
                snapshot, visible = groundwater_snapshot(frame, origin, gap)
                for district_id in districts:
                    labels = [(horizon, origin+pd.DateOffset(months=horizon)) for horizon in range(1, 7)
                              if origin+pd.DateOffset(months=horizon) <= end and (district_id, origin+pd.DateOffset(months=horizon)) in truth.index]
                    if not labels:
                        continue
                    evidence = evidence_provider(district_id, as_of, snapshot.copy(deep=True))
                    leaked_observations = _observed(evidence["frame"]) & (evidence["frame"].date > visible)
                    if (evidence["frame"].date > origin).any() or (evidence["history"].date > visible).any() or leaked_observations.any():
                        raise ValueError("Evidence provider leaked future or hidden groundwater observations.")
                    if evidence.get("generation") != model_metadata["feature_generation_id"] or evidence.get("district_id") != district_id:
                        raise ValueError("Evidence provider returned mismatched generation or district.")
                    prediction = predictor(evidence)
                    if prediction.get("status") != "projection":
                        skipped.append({"split": split, "district_id": district_id, "origin_date": origin.date().isoformat(),
                                        "requested_gap_months": gap, "status": prediction.get("status", "unavailable"),
                                        "reason": prediction.get("message", "Insufficient replay evidence.")})
                        continue
                    source = evidence["estimate_type"]
                    if source not in SOURCES:
                        raise ValueError("Projection has an unknown evidence source.")
                    if pd.isna(evidence.get("origin")):
                        raise ValueError("Projection needs a last observed month.")
                    last = _date(evidence["origin"], "last observed", month_start=True)
                    if last > visible:
                        raise ValueError("Projection retained a hidden last observation.")
                    anchor = evidence["history"].loc[evidence["history"].date == last, "gwl_current"]
                    if len(anchor) != 1 or not np.isfinite(float(anchor.iloc[0])) or float(anchor.iloc[0]) < 0:
                        raise ValueError("Replay persistence baseline requires one finite observed anchor depth.")
                    anchor_depth = float(anchor.iloc[0])
                    points = prediction.get("forecast", [])
                    expected = [origin+pd.DateOffset(months=h) for h in range(1, 7)]
                    dates = [_date(point["date"], "forecast target", month_start=True) for point in points]
                    values = np.array([point["predicted_gwl"] for point in points], dtype=float)
                    if dates != expected or len(values) != 6 or not np.isfinite(values).all() or (values < 0).any():
                        raise ValueError("Full replay predictor must return six finite nonnegative calendar forecasts.")
                    if prediction.get("model_sha256", model_metadata["model_sha256"]) != model_metadata["model_sha256"]:
                        raise ValueError("Predictor used another model hash.")
                    if prediction.get("model_train_target_cutoff", model_metadata["train_target_cutoff"]) != model_metadata["train_target_cutoff"]:
                        raise ValueError("Predictor used another training-label cutoff.")
                    for horizon, target in labels:
                        record = {"split": split, "district_id": district_id,
                            "origin_date": origin.date().isoformat(), "as_of": as_of.date().isoformat(),
                            "target_date": target.date().isoformat(), "horizon_months": horizon,
                            "requested_gap_months": gap, "groundwater_visible_through": visible.date().isoformat(),
                            "last_observed_date": last.date().isoformat(), "data_age_months": _month_distance(origin, last),
                            "estimate_type": source, "source_zone": evidence.get("zone"),
                            "target_basis": "observed_district_depth", "target_is_observed": True,
                            "last_observed_gwl_m_bgl": anchor_depth,
                            "actual_gwl_m_bgl": float(truth.loc[(district_id, target)]),
                            "predicted_gwl_m_bgl": float(values[horizon-1]),
                            "model_sha256": model_metadata["model_sha256"],
                            "feature_generation_id": model_metadata["feature_generation_id"],
                            "protocol_sha256": protocol.sha256}
                        record["age_bin"] = age_bin(record["data_age_months"])
                        record["case_id"] = _hash({key: record[key] for key in IDENTITY})
                        records.append(record)
    return {"version": VERSION, "mode": "candidate_full_path_replay", "protocol": asdict(protocol),
            "model": dict(model_metadata), "cases": records, "skipped": skipped,
            "summary": summarize_errors(records), "production_changes_made": False,
            "current_period_accuracy_established": False, "limitations": list(WARNINGS)}


def _group_key(row):
    zone_key = ""
    if row["estimate_type"] == "zone_fallback":
        zone = row.get("source_zone")
        if not isinstance(zone, str) or not zone.strip():
            raise ValueError("Zone fallback uncertainty requires an explicit canonical source zone.")
        zone_key = "|zone="+json.dumps(zone, ensure_ascii=True)
    return f"h{int(row['horizon_months'])}|{row['estimate_type']}{zone_key}|age_{age_bin(row['data_age_months'])}"


def validated_cases(cases, protocol, split, model_metadata):
    protocol.validate_model(model_metadata)
    if isinstance(cases, pd.DataFrame):
        cases = cases.to_dict("records")
    records = []
    start, end = protocol.window(split)
    required = set(IDENTITY + ["target_date", "last_observed_date", "data_age_months", "estimate_type",
        "actual_gwl_m_bgl", "predicted_gwl_m_bgl", "model_sha256", "feature_generation_id",
        "protocol_sha256", "split", "target_is_observed", "target_basis", "groundwater_visible_through"])
    for supplied in cases:
        if required-set(supplied):
            raise ValueError(f"Replay case lacks required fields: {sorted(required-set(supplied))}")
        row = dict(supplied)
        if row["split"] != split:
            raise ValueError("Only the requested reserved split may enter this operation.")
        origin, target, last, visible = [_date(row[key], key, month_start=True) for key in
                                        ("origin_date", "target_date", "last_observed_date", "groundwater_visible_through")]
        horizon = _integer(row["horizon_months"], "horizon", minimum=1, maximum=6)
        gap = _integer(row["requested_gap_months"], "gap", maximum=120)
        age = _integer(row["data_age_months"], "data age")
        if origin < start or target > end or target != origin+pd.DateOffset(months=horizon):
            raise ValueError("Replay label/origin crosses its reserved calendar split or horizon.")
        if visible != origin-pd.DateOffset(months=gap) or last > visible or age != _month_distance(origin, last):
            raise ValueError("Replay groundwater visibility or age is inconsistent.")
        if (row["estimate_type"] not in SOURCES or row["target_basis"] != "observed_district_depth"
                or str(row["target_is_observed"]).lower() not in ("true", "1")):
            raise ValueError("Intervals require explicit district-observed targets and known evidence sources.")
        if row["estimate_type"] == "zone_fallback":
            _group_key(row)
        for key in ("model_sha256", "feature_generation_id"):
            if row[key] != model_metadata[key]:
                raise ValueError("Replay case model or feature generation differs from calibration.")
        if row["protocol_sha256"] != protocol.sha256:
            raise ValueError("Replay cases use another temporal protocol.")
        if not isinstance(row["district_id"], str) or not row["district_id"].strip():
            raise ValueError("Replay case district identity is empty.")
        for key in ("actual_gwl_m_bgl", "predicted_gwl_m_bgl"):
            if isinstance(row[key], bool):
                raise ValueError("Depth cannot be boolean.")
            row[key] = float(row[key])
            if not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError("Replay depths must be finite and nonnegative.")
        if row.get("last_observed_gwl_m_bgl") is not None:
            baseline = row["last_observed_gwl_m_bgl"]
            if isinstance(baseline, bool) or not math.isfinite(float(baseline)) or float(baseline) < 0:
                raise ValueError("Replay persistence depths must be finite and nonnegative.")
            row["last_observed_gwl_m_bgl"] = float(baseline)
        row.update(horizon_months=horizon, requested_gap_months=gap, data_age_months=age, age_bin=age_bin(age))
        records.append(row)
    identities = [tuple(row[key] for key in IDENTITY) for row in records]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate replay case identities cannot increase calibration support.")
    return records


def summarize_errors(cases):
    if not cases:
        return {"n": 0, "status": "no_observed_labels", "groups": {}}
    def summary(part):
        errors = np.array([row["actual_gwl_m_bgl"]-row["predicted_gwl_m_bgl"] for row in part], dtype=float)
        paired = [row for row in part if row.get("last_observed_gwl_m_bgl") is not None]
        for row in paired:
            value = row["last_observed_gwl_m_bgl"]
            if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError("Replay persistence depths must be finite and nonnegative.")
        return {"n": len(part), "districts": len({row["district_id"] for row in part}),
                "origins": len({row["origin_date"] for row in part}),
                "mae_m": float(np.abs(errors).mean()), "rmse_m": float(np.sqrt(np.square(errors).mean())),
                "mean_error_m": float(errors.mean()), "persistence_paired_n": len(paired),
                "forecast_paired_rmse_m": float(np.sqrt(np.mean([(row["actual_gwl_m_bgl"]-row["predicted_gwl_m_bgl"])**2 for row in paired]))) if paired else None,
                "persistence_paired_rmse_m": float(np.sqrt(np.mean([(row["actual_gwl_m_bgl"]-float(row["last_observed_gwl_m_bgl"]))**2 for row in paired]))) if paired else None}
    keys = sorted({_group_key(row) for row in cases})
    return {"status": "historical_replay_only", **summary(cases),
            "groups": {key: summary([row for row in cases if _group_key(row) == key]) for key in keys}}


def fit_intervals(cases, protocol, model_metadata, *, alpha=.1, min_cases=30, min_origins=6, min_districts=3):
    """Fit absolute-error rank intervals using calibration cases only.

    Sparse strata have no interval; a wider population is never substituted.
    Rank ceil((n+1)*(1-alpha)) is used without clipping an unattainable rank.
    """
    if isinstance(alpha, bool) or not math.isfinite(float(alpha)) or not 0 < float(alpha) < 1:
        raise ValueError("alpha must be in (0,1).")
    alpha = float(alpha)
    minimums = {"n": _integer(min_cases, "min_cases", minimum=1),
                "origins": _integer(min_origins, "min_origins", minimum=1),
                "districts": _integer(min_districts, "min_districts", minimum=1)}
    records = validated_cases(cases, protocol, "calibration", model_metadata)
    groups = {}
    for key in sorted({_group_key(row) for row in records}):
        part = [row for row in records if _group_key(row) == key]
        counts = {"n": len(part), "origins": len({row["origin_date"] for row in part}),
                  "districts": len({row["district_id"] for row in part})}
        rank = math.ceil((len(part)+1)*(1-alpha))
        reasons = [f"insufficient_{name}" for name in minimums if counts[name] < minimums[name]]
        if rank > len(part):
            reasons.append("finite_sample_rank_unavailable")
        radius = None if reasons else float(np.sort([abs(row["actual_gwl_m_bgl"]-row["predicted_gwl_m_bgl"]) for row in part])[rank-1])
        groups[key] = {"status": "uncertainty_not_established" if reasons else "candidate_empirical_interval",
                       **counts, "rank": rank, "radius_m": radius, "reasons": reasons}
    canonical = sorted(records, key=lambda row: tuple(str(row[key]) for key in IDENTITY))
    return {"version": VERSION, "mode": "candidate_empirical_intervals", "protocol": asdict(protocol),
            "protocol_sha256": protocol.sha256, "model": dict(model_metadata), "alpha": alpha,
            "nominal_coverage": 1-alpha, "minimum_support": minimums, "calibration_cases": len(records),
            "calibration_cases_sha256": _hash(canonical), "groups": groups,
            "sufficient_for_operational_use": False, "current_period_uncertainty_established": False,
            "limitations": list(WARNINGS)}


def evaluate_intervals(cases, calibration, protocol, model_metadata):
    """Evaluate later cases; evaluation values never change stored radii."""
    if (calibration.get("version") != VERSION or calibration.get("protocol_sha256") != protocol.sha256
            or calibration.get("model") != model_metadata):
        raise ValueError("Interval artifact model/protocol identity differs from evaluation.")
    records = validated_cases(cases, protocol, "evaluation", model_metadata)
    details = []
    for row in records:
        group = calibration.get("groups", {}).get(_group_key(row), {})
        radius = group.get("radius_m")
        eligible = group.get("status") == "candidate_empirical_interval" and radius is not None
        if eligible and (not math.isfinite(float(radius)) or float(radius) < 0):
            raise ValueError("Interval artifact contains an invalid radius.")
        if eligible:
            low = max(0., row["predicted_gwl_m_bgl"]-float(radius))
            high = row["predicted_gwl_m_bgl"]+float(radius)
            details.append({**row, "interval_status": "candidate_empirical_interval", "lower_m_bgl": low,
                "upper_m_bgl": high, "covered": low <= row["actual_gwl_m_bgl"] <= high, "width_m": high-low})
        else:
            details.append({**row, "interval_status": "uncertainty_not_established", "lower_m_bgl": None,
                            "upper_m_bgl": None, "covered": None, "width_m": None})
    def summary(part):
        supported = [row for row in part if row["covered"] is not None]
        return {"n": len(part), "supported_n": len(supported), "unsupported_n": len(part)-len(supported),
                "empirical_coverage": sum(row["covered"] for row in supported)/len(supported) if supported else None,
                "mean_width_m": float(np.mean([row["width_m"] for row in supported])) if supported else None,
                "districts": len({row["district_id"] for row in supported}),
                "origins": len({row["origin_date"] for row in supported})}
    keys = sorted({_group_key(row) for row in details})
    return {"version": VERSION, "mode": "historical_heldout_interval_evaluation", **summary(details),
            "groups": {key: summary([row for row in details if _group_key(row) == key]) for key in keys},
            "cases": details, "current_period_uncertainty_established": False,
            "sufficient_for_operational_use": False, "limitations": list(WARNINGS)}
