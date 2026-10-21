"""Exact calendar-horizon helpers for isolated historical research.

Production forecasting retains its six-month contract.  This module never loads
production features, reads a database, publishes a pointer, or fits an estimator.
Research artifacts are confined to the twelve-month candidate namespace.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ROOT = ROOT / "reports" / "candidates"
FAMILIES = {"xgboost", "linear_regression", "hist_gradient_boosting"}


def _horizon(value):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value not in (6, 12):
        raise ValueError("Research horizon must be exactly 6 or 12 calendar months")
    return int(value)


def _flags(values):
    return values.astype("string").str.strip().str.lower().map(
        {"true": True, "1": True, "false": False, "0": False}
    ).astype("boolean")


def schema_hash(feature_columns):
    return hashlib.sha256(json.dumps(
        list(feature_columns), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_cases(frame, horizon_months=6):
    """Retain origin inventory; only exact, explicitly observed labels count.

    Annual seasonal naive uses target minus twelve months.  At horizon twelve
    that is the origin observation itself, so it equals persistence exactly.
    Finite imputed origin values may enter training only with an explicit age of
    one through three months.  Evaluation always requires observed references.
    """
    horizon = _horizon(horizon_months)
    required = {"district_id", "date", "gwl_current", "is_observed", "is_imputed"}
    absent = required - set(frame)
    if absent:
        raise ValueError(f"Explicit research fields required: {sorted(absent)}")
    attrs = frame.attrs.copy()
    rows = frame.copy()
    rows["date"] = pd.to_datetime(rows.date, errors="raise")
    if (rows.date.isna().any() or (rows.date.dt.day != 1).any()
            or (rows.date != rows.date.dt.normalize()).any()):
        raise ValueError("Calendar month starts are required")
    if rows.district_id.isna().any() or rows.district_id.astype(str).str.strip().eq("").any():
        raise ValueError("District identity is required")
    if rows.duplicated(["district_id", "date"]).any():
        raise ValueError("Duplicate district-month keys cannot form unique targets")
    observed, imputed = _flags(rows.is_observed), _flags(rows.is_imputed)
    if (observed.eq(True) & imputed.eq(True)).fillna(False).any():
        raise ValueError("Observed and imputed provenance flags conflict")
    explicit_observed = (observed.eq(True) & imputed.eq(False)).fillna(False).astype(bool)
    explicit_imputed = (observed.eq(False) & imputed.eq(True)).fillna(False).astype(bool)
    depth = pd.to_numeric(rows.gwl_current, errors="coerce")
    finite = np.isfinite(depth.to_numpy(dtype=float))
    rows["origin_is_observed"] = explicit_observed & finite
    rows["origin_is_imputed"] = explicit_imputed & finite
    age = pd.to_numeric(rows.get("months_since_observation", pd.Series(np.nan, index=rows.index)), errors="coerce")
    rows["training_origin_eligible"] = rows.origin_is_observed | (rows.origin_is_imputed & age.between(1, 3))
    reference = rows[["district_id", "date"]].copy()
    reference["reference_value"] = depth.where(explicit_observed & finite).to_numpy()
    reference["reference_observed"] = (explicit_observed & finite).to_numpy()
    rows["target_date"] = rows.date + pd.DateOffset(months=horizon)
    rows["seasonal_date"] = rows.target_date - pd.DateOffset(months=12)
    for prefix, key, value_name, observed_name in [
        ("target", "target_date", "target_value", "target_is_observed"),
        ("seasonal", "seasonal_date", "seasonal_naive", "seasonal_is_observed"),
    ]:
        lookup = reference.rename(columns={"date": key, "reference_value": value_name,
                                            "reference_observed": observed_name})
        # Refuse accidental reuse of a previously prepared table as raw inputs.
        if value_name in rows or observed_name in rows:
            raise ValueError(f"Input already contains prepared {prefix} labels")
        rows = rows.merge(lookup, on=["district_id", key], how="left", validate="many_to_one")
        rows[observed_name] = rows[observed_name].fillna(False).astype(bool)
    rows["reference_eligible"] = (
        rows.origin_is_observed & rows.target_is_observed & rows.seasonal_is_observed
        & np.isfinite(rows[["gwl_current", "target_value", "seasonal_naive"]].apply(pd.to_numeric, errors="coerce")).all(axis=1)
    )
    rows["horizon_months"] = horizon
    rows["case_id"] = (rows.district_id.astype(str) + "|" + rows.date.dt.strftime("%Y-%m-%d")
                       + "|" + rows.target_date.dt.strftime("%Y-%m-%d") + "|" + str(horizon))
    if not rows.case_id.is_unique:
        raise ValueError("Duplicate research case identities")
    rows = rows.sort_values(["district_id", "date"]).reset_index(drop=True)
    rows.attrs.update(attrs)
    return rows


def split_fold(cases, target_year, horizon_months=6):
    """Expand training chronologically with H complete embargo months.

    For twelve-month targets in 2024, origins start January 2023 and training
    labels end December 2021.  Calendar year 2022 is entirely embargoed.
    """
    horizon = _horizon(horizon_months)
    if isinstance(target_year, bool) or not isinstance(target_year, (int, np.integer)):
        raise ValueError("Target year must be an integer")
    required = {"date", "target_date", "target_value", "target_is_observed",
                "training_origin_eligible", "reference_eligible", "horizon_months"}
    if required - set(cases):
        raise ValueError("Prepared research cases are required")
    if not cases.horizon_months.eq(horizon).all():
        raise ValueError("Case horizon differs from the requested fold")
    dates = pd.to_datetime(cases.date)
    targets = pd.to_datetime(cases.target_date)
    if not targets.eq(dates + pd.DateOffset(months=horizon)).all():
        raise ValueError("Target dates violate the exact calendar horizon")
    earliest = pd.Timestamp(int(target_year), 1, 1) - pd.DateOffset(months=horizon)
    cutoff = earliest - pd.DateOffset(months=horizon) - pd.Timedelta(days=1)
    valid_target = cases.target_is_observed.eq(True) & np.isfinite(pd.to_numeric(cases.target_value, errors="coerce"))
    train = cases.loc[valid_target & cases.training_origin_eligible.eq(True) & targets.le(cutoff)].copy()
    evaluated = cases.loc[cases.reference_eligible.eq(True) & targets.dt.year.eq(int(target_year))].copy()
    if len(evaluated) and pd.to_datetime(evaluated.date).min() < earliest:
        raise ValueError("Evaluation origins violate the complete-month embargo")
    if len(train) and len(evaluated) and pd.to_datetime(train.target_date).max() >= pd.to_datetime(evaluated.date).min():
        raise ValueError("Training labels overlap evaluated origins")
    metadata = {"target_year": int(target_year), "horizon_months": horizon, "embargo_months": horizon,
                "cutoff": str(cutoff.date()), "train_target_cutoff": str(cutoff.date()),
                "first_permitted_origin": str(earliest.date()), "train_n": len(train),
                "max_train_target": str(train.target_date.max().date()) if len(train) else None,
                "evaluation_n": len(evaluated)}
    return train, evaluated, metadata


def _calendar_date(value, name):
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid research card date: {name}") from error
    if pd.isna(result) or result.tzinfo is not None or result != result.normalize():
        raise ValueError(f"Invalid research card date: {name}")
    return result


def validate_card(card, expected_horizon, protocol_sha256, feature_columns):
    """Validate the research contract before any estimator deserialization."""
    horizon = _horizon(expected_horizon)
    if not isinstance(card, dict):
        raise ValueError("Research model card must be a JSON object")
    if (type(card.get("research_schema_version")) is not int or card.get("research_schema_version") != 1
            or card.get("research_only") is not True
            or card.get("allowed_use") != "historical_research_only"):
        raise ValueError("Model card is not an isolated historical research artifact")
    if (type(card.get("horizon_months")) is not int or card.get("horizon_months") != horizon
            or type(card.get("embargo_months")) is not int or card.get("embargo_months") != horizon):
        raise ValueError("Research model horizon or embargo is incompatible")
    try:
        features = list(feature_columns)
    except TypeError as error:
        raise ValueError("Research feature schema/order is incompatible") from error
    if (not features or any(not isinstance(name, str) or not name for name in features)
            or len(features) != len(set(features))
            or card.get("features") != features
            or card.get("feature_schema_sha256") != schema_hash(features)):
        raise ValueError("Research feature schema/order is incompatible")
    if card.get("units") != "m_bgl":
        raise ValueError("Research target units must be m_bgl")
    if not protocol_sha256 or card.get("protocol_sha256") != protocol_sha256:
        raise ValueError("Research protocol hash is incompatible")
    if card.get("family") not in FAMILIES:
        raise ValueError("Unknown research estimator family")
    cutoff = _calendar_date(card.get("train_target_cutoff"), "train_target_cutoff")
    target = _calendar_date(card.get("max_train_target_date"), "max_train_target_date")
    origin = _calendar_date(card.get("max_train_origin"), "max_train_origin")
    if (target.day != 1 or origin.day != 1 or target > cutoff
            or origin + pd.DateOffset(months=horizon) > target):
        raise ValueError("Research training dates violate the cutoff or calendar horizon")
    return card


def _research_path(path):
    resolved = Path(path).resolve()
    try:
        relative = resolved.relative_to(RESEARCH_ROOT.resolve())
    except ValueError as error:
        raise ValueError("Research artifacts require the dedicated twelve-month candidate namespace") from error
    if (not relative.parts or not relative.parts[0].startswith("twelve_month_horizon_")
            or relative.parts[0] == "twelve_month_horizon_"):
        raise ValueError("Research artifacts require a twelve_month_horizon_* directory")
    return resolved


def load_research_model(card_path, expected_horizon, protocol_sha256, feature_columns):
    card_path = _research_path(card_path)
    card = json.loads(card_path.read_text(encoding="utf-8"))
    validate_card(card, expected_horizon, protocol_sha256, feature_columns)
    name = card.get("model_path")
    if (not isinstance(name, str) or not name or "/" in name or "\\" in name
            or Path(name).is_absolute() or Path(name).name != name):
        raise ValueError("Research model path must be a confined basename")
    model_path = (card_path.parent / name).resolve()
    if model_path.parent != card_path.parent.resolve():
        raise ValueError("Research model path escapes its card directory")
    _research_path(model_path)
    expected_sha = card.get("model_sha256")
    if (not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
            or sha256_file(model_path) != expected_sha):
        raise ValueError("Research model checksum differs from its card")
    if card["family"] == "xgboost":
        if model_path.suffix != ".json":
            raise ValueError("Research XGBoost artifacts require JSON")
        from xgboost import XGBRegressor
        model = XGBRegressor()
        model.load_model(model_path)
    else:
        if model_path.suffix != ".joblib":
            raise ValueError("Research sklearn artifacts require joblib")
        import joblib
        model = joblib.load(model_path)
    return model, card


def save_research_model(model, card, directory, stem):
    """Write a new immutable model/card pair; never publish a serving pointer."""
    directory = _research_path(directory)
    if not isinstance(stem, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", stem):
        raise ValueError("Research model stem must be a simple filename")
    if not isinstance(card, dict):
        raise ValueError("Research model card must be a JSON object")
    validate_card(card, card.get("horizon_months"), card.get("protocol_sha256"), card.get("features", []))
    extension = ".json" if card["family"] == "xgboost" else ".joblib"
    model_path, card_path = directory / (stem + extension), directory / (stem + "_card.json")
    if model_path.exists() or card_path.exists():
        raise FileExistsError("Research model/card already exists; historical artifacts are immutable")
    directory.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents concurrent writers from replacing history.
    with card_path.open("x", encoding="utf-8") as card_handle:
        with model_path.open("xb") as model_handle:
            if card["family"] != "xgboost":
                import joblib
                joblib.dump(model, model_handle)
        if card["family"] == "xgboost":
            model.save_model(model_path)
        complete = {**card, "model_path": model_path.name, "model_sha256": sha256_file(model_path)}
        json.dump(complete, card_handle, indent=2, allow_nan=False)
    return card_path
