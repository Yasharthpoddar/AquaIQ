"""Create-only offline fixed XGB research artifact; never a serving promotion.

No network, database, ingestion, HGB fitting, tuning, or active pointer writes.
This explicitly authorized step freezes its plan before fitting exactly once.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from models import research_horizon as horizon

RUN = Path(__file__).resolve().parent
OLD = ROOT / "reports/candidates/twelve_month_horizon_20261020"
STUDY = ROOT / "reports/actual_forecast_validation_20261019"
ARTIFACT = RUN / "artifact"
CONFIG = ROOT / "research/twelve_month_app.json"
F = ["gwl_current", "gwl_lag_3mo", "gwl_lag_6mo", "rainfall_current",
     "rainfall_3mo_avg", "monsoon_deficit_pct", "temperature", "evapotranspiration",
     "water_balance_proxy", "season_Kharif", "season_Rabi", "season_Zaid"]
UNITS = {"gwl": "m_bgl", "rainfall": "mm/month", "evapotranspiration": "mm/month", "temperature": "degC"}
GENERATION = "research-telangana-exact-name-coordinate-h12-app-v1"
DISTRICT = "TS-Adilabad"


def now():
    return datetime.now(timezone.utc).isoformat()


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def finite(value):
    return bool(pd.notna(value) and np.isfinite(float(value)))


def month(value):
    return pd.Timestamp(value).strftime("%Y-%m")


def flag(feature, status, required, source_month=None, age=None, **extra):
    return {"feature": feature, "status": status, "required_month": month(required),
            "source_month": month(source_month) if source_month is not None else None,
            "age_months": age, **extra}


def compatible(value, expected):
    return finite(value) and finite(expected) and bool(np.isclose(float(value), float(expected), rtol=1e-6, atol=1e-6))


def weather_history(frame, name):
    series = frame.set_index("date")[name].sort_index()
    if not series.index.is_unique:
        raise ValueError("Duplicate raw weather months")
    return series.reindex(pd.date_range(series.index.min(), "2026-09-01", freq="MS"))


def direct_weather(feature, intended, value, history, source):
    if not finite(value):
        return flag(feature, "missing", intended, source=source)
    raw = history.get(intended, np.nan)
    if compatible(value, raw):
        return flag(feature, "observed", intended, intended, 0, source=source)
    earlier = history.loc[history.index < intended].dropna()
    if len(earlier):
        latest = earlier.index[-1]
        age = (intended.year - latest.year) * 12 + intended.month - latest.month
        if 1 <= age <= 2 and compatible(value, earlier.iloc[-1]):
            return flag(feature, "carried_forward", intended, latest, age, source=source)
    return flag(feature, "unknown", intended, source=source,
                reason="Finite feature cannot be established from retained raw monthly source and bounded carry rule")


def derived(feature, intended, value, expected, dependencies):
    if not finite(value):
        return flag(feature, "missing", intended, dependencies=dependencies)
    if not compatible(value, expected) or not dependencies or any(
            item["status"] in ("unknown", "missing") for item in dependencies):
        return flag(feature, "unknown", intended, dependencies=dependencies,
                    reason="Derived feature provenance or arithmetic not established")
    status = "derived_with_carried_input" if any(
        item["status"] in ("carried_forward", "derived_with_carried_input") for item in dependencies
    ) else "derived_from_observed"
    sources = [item["source_month"] for item in dependencies if item["source_month"]]
    return flag(feature, status, intended, max(sources) if sources else None,
                max(item["age_months"] or 0 for item in dependencies), dependencies=dependencies)


def input_provenance(snapshot):
    era5 = pd.read_csv(ROOT / "data/processed/era5_district_monthly.csv")
    rain = pd.read_csv(ROOT / "data/processed/imd_rainfall_district_monthly.csv")
    era5 = era5.loc[era5.district.eq("Adilabad") & era5.st_nm.eq("Telangana")].copy()
    rain = rain.loc[rain.district.eq("Adilabad") & rain.st_nm.eq("Telangana")].copy()
    for frame in (era5, rain):
        frame["date"] = pd.to_datetime(dict(year=frame.year, month=frame.month, day=1))
    histories = {name: weather_history(era5, name) for name in ("temperature", "evapotranspiration")}
    histories["rainfall_current"] = weather_history(rain, "rainfall_mm")
    rain_filled = histories["rainfall_current"].ffill(limit=2)
    indexed = snapshot.set_index("date")
    rows = []
    for row in snapshot.itertuples():
        date = row.date
        inputs = {}
        for feature, lag in (("gwl_current", 0), ("gwl_lag_3mo", 3), ("gwl_lag_6mo", 6)):
            intended = date - pd.DateOffset(months=lag)
            value = getattr(row, feature)
            source_row = indexed.loc[intended] if intended in indexed.index else None
            if not finite(value):
                item = flag(feature, "missing", intended)
            elif source_row is None or not compatible(value, source_row.gwl_current):
                item = flag(feature, "unknown", intended)
            elif bool(source_row.is_observed) and not bool(source_row.is_imputed):
                item = flag(feature, "observed", intended, intended, 0,
                            panel_sha256=source_row.panel_sha256,
                            well_count=int(source_row.well_count),
                            reported_date=str(source_row.first_reported_date),
                            actual_acquisition_at=None, available_at=None)
            elif bool(source_row.is_imputed) and finite(source_row.months_since_observation):
                age = int(source_row.months_since_observation)
                measurement = intended - pd.DateOffset(months=age)
                item = flag(feature, "carried_forward", intended, measurement, age)
            else:
                item = flag(feature, "unknown", intended)
            inputs[feature] = item
        for feature in ("rainfall_current", "temperature", "evapotranspiration"):
            inputs[feature] = direct_weather(feature, date, getattr(row, feature), histories[feature],
                "IMD district monthly" if feature == "rainfall_current" else "ERA5 district monthly")
        dependencies = []
        rainfall_values = []
        for offset in (2, 1, 0):
            intended = date - pd.DateOffset(months=offset)
            value = rain_filled.get(intended, np.nan)
            dependencies.append(direct_weather("rainfall", intended, value, histories["rainfall_current"], "IMD district monthly"))
            rainfall_values.append(value)
        expected_avg = float(np.nanmean(rainfall_values)) if any(finite(x) for x in rainfall_values) else np.nan
        inputs["rainfall_3mo_avg"] = derived("rainfall_3mo_avg", date, row.rainfall_3mo_avg, expected_avg, dependencies)
        prior = rain_filled.loc[(rain_filled.index < date) & (rain_filled.index.month == date.month)].dropna()
        normal = float(prior.mean()) if len(prior) >= 3 else np.nan
        expected = (row.rainfall_current - normal) / normal * 100 if finite(normal) and normal > 0 else np.nan
        dependencies = [inputs["rainfall_current"], *[
            direct_weather("prior_same_calendar_month_rainfall", stamp, value,
                           histories["rainfall_current"], "IMD district monthly")
            for stamp, value in prior.items()]]
        inputs["monsoon_deficit_pct"] = derived("monsoon_deficit_pct", date, row.monsoon_deficit_pct, expected, dependencies)
        inputs["water_balance_proxy"] = derived("water_balance_proxy", date, row.water_balance_proxy,
            row.rainfall_current - row.evapotranspiration,
            [inputs["rainfall_current"], inputs["evapotranspiration"]])
        for feature in ("season_Kharif", "season_Rabi", "season_Zaid"):
            inputs[feature] = flag(feature, "calendar", date, date, 0,
                                   source="Deterministic origin calendar month")
        rows.append({"district_id": row.district_id, "date": str(date.date()),
                     "inputs": [inputs[feature] for feature in F]})
    return {"schema_version": 1, "feature_generation_id": GENERATION, "rows": rows}


def metrics(actual, predicted):
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    error = predicted - actual
    sst = float(np.square(actual - actual.mean()).sum())
    return {"n": len(actual), "MAE_m": float(np.abs(error).mean()),
            "RMSE_m": float(np.sqrt(np.square(error).mean())), "bias_m": float(error.mean()),
            "R2": float(1 - np.square(error).sum() / sst) if sst > 1e-12 else None}


def main():
    if ARTIFACT.exists() or CONFIG.exists() or (RUN / "build_plan.json").exists():
        raise FileExistsError("Build is create-only; use a separately authorized fresh version for repetition")
    protocol_path = OLD / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol_sha = horizon.sha256_file(protocol_path)
    if protocol_sha != "1a93abf0a52eb44263d05090137df2c7000f83c3d0cf2c3e2843c56ac1ec57c2":
        raise ValueError("Original protocol changed")
    for name, expected in protocol["inputs_sha256"].items():
        if horizon.sha256_file(ROOT / name) != expected:
            raise ValueError("Frozen input changed: " + name)
    lock = json.loads((OLD / "cohorts/lock.json").read_text(encoding="utf-8"))
    for name, expected in lock["files"].items():
        if horizon.sha256_file(OLD / "cohorts" / name) != expected:
            raise ValueError("Frozen cohort changed: " + name)
    for name in ("era5_district_monthly", "imd_rainfall_district_monthly"):
        manifest = json.loads((ROOT / f"data/processed/{name}.manifest.json").read_text(encoding="utf-8"))
        if horizon.sha256_file(ROOT / f"data/processed/{name}.csv") != manifest["csv_sha256"]:
            raise ValueError("Weather source hash changed")
    snapshot = pd.read_csv(OLD / "cohorts/strict_features.csv", parse_dates=["date"])
    snapshot = snapshot.loc[snapshot.district_id.eq(DISTRICT)].copy()
    if len(snapshot) != 233 or not snapshot.date.is_unique:
        raise ValueError("Unexpected fixed district/month snapshot")
    cases = horizon.build_cases(snapshot, 12)
    train, _, split = horizon.split_fold(cases, 2024, 12)
    if len(train) != 164 or split["cutoff"] != "2021-12-31" or not train.district_id.eq(DISTRICT).all():
        raise ValueError("Fixed training population differs from reviewed plan")
    params = protocol["models"]["xgb_expanding"]["parameters"]
    contract = {"schema_version": 1, "product": "direct_12month_research", "horizon_months": 12,
        "embargo_months": 12, "features": F, "feature_units": UNITS, "units": "m_bgl",
        "feature_generation_id": GENERATION, "supported_district_ids": [DISTRICT],
        "allowed_use": "historical_research_only", "protocol_sha256": protocol_sha,
        "train_target_cutoff": "2021-12-31", "first_allowed_origin": "2023-01",
        "max_weather_carry_months": 2, "max_gwl_carry_months": 3}
    contract_sha = json_hash(contract)
    source_paths = [*protocol["inputs_sha256"],
        str((OLD / "cohorts/strict_features.csv").relative_to(ROOT)).replace("\\", "/"),
        "data/processed/era5_district_monthly.csv", "data/processed/era5_district_monthly.manifest.json",
        "data/processed/imd_rainfall_district_monthly.csv", "data/processed/imd_rainfall_district_monthly.manifest.json",
        "reports/github_release_20261020/PUBLIC_SOURCE_PROVENANCE.json"]
    hashes = {name: horizon.sha256_file(ROOT / name) for name in source_paths}
    plan = {"schema_version": 1, "frozen_at_utc": now(), "authorization":
        "Human finalization request authorizes a separate fixed-settings twelve-month research artifact; no HGB refit or promotion",
        "training_cutoff": "2021-12-31", "max_train_target": "2021-12-01",
        "first_allowed_origin": "2023-01", "train_native_n": 164, "train_complete_n": 158,
        "features": F, "target": "Exact observed M+12 absolute groundwater depth, m_bgl",
        "parameters": params, "contract": contract, "contract_sha256": contract_sha,
        "input_sha256": hashes, "builder_sha256": horizon.sha256_file(Path(__file__)),
        "preprocessing": "No learned preprocessing; preserve six native-missing-lag training rows; no new imputation",
        "scientific_limits": ["Not selected for accuracy", "Strict old comparison favors annual baseline",
            "Name-coordinate agreement is not authoritative verification", "Current inference remains blocked",
            "Availability and datum continuity unverified", "Existing 792-case expanding results do not describe this fixed artifact"],
        "no_tuning": True, "historical_research_only": True, "shadow_artifact_approved": False}
    write_json(RUN / "build_plan.json", plan)
    ARTIFACT.mkdir(exist_ok=False)
    snapshot["feature_generation"] = GENERATION
    with (ARTIFACT / "features.csv").open("x", encoding="utf-8", newline="") as handle:
        snapshot.to_csv(handle, index=False)
    provenance = input_provenance(snapshot)
    write_json(ARTIFACT / "input_provenance.json", provenance)
    normalized = pd.read_csv(STUDY / "normalized_v2/normalized_well_observations.csv",
        usecols=["district_id", "source_name_district_id", "agency", "provider_well_id", "aquifer", "units"],
        dtype={"provider_well_id": str})
    accepted = normalized.loc[normalized.district_id.eq(DISTRICT) & normalized.source_name_district_id.eq(DISTRICT)]
    write_json(ARTIFACT / "provenance.json", {"schema_version": 1,
        "source_role": "retrospective_current_vintage_not_issuance_verified", "input_sha256": hashes,
        "feature_generation_id": GENERATION, "units": UNITS, "supported_district_ids": [DISTRICT],
        "accepted_well_months": len(accepted), "provider_well_id_count": int(accepted.provider_well_id.nunique()),
        "agencies": sorted(accepted.agency.unique()), "aquifer_counts": accepted.aquifer.value_counts().to_dict(),
        "panel_hash_semantics": "Agency/provider ID/equal weight membership identity, not verified physical continuity",
        "source_location_policy": "Exact source-name/fixed-polygon agreement; no coordinate correction; metadata agreement is not verified location",
        "datum": "Source explicitly mbgl; measuring-point changes and replacement history unknown",
        "actual_acquisition_at": None, "first_publication_at": None, "available_at": None,
        "forecast_issued_at": None, "historical_availability_verified": False,
        "public_source_companion": "reports/github_release_20261020/PUBLIC_SOURCE_PROVENANCE.json",
        "security_policy": "Only explicit hashes/units/counts/source-role metadata; original HTTP headers and cookie-bearing manifests are never read"})
    from xgboost import XGBRegressor
    started = now()
    model = XGBRegressor(**params)
    model.fit(train[F], train.target_value)
    completed = now()
    card = {"research_schema_version": 1, "research_only": True, "allowed_use": "historical_research_only",
        "horizon_months": 12, "embargo_months": 12, "family": "xgboost", "features": F,
        "feature_schema_sha256": horizon.schema_hash(F), "units": "m_bgl", "feature_units": UNITS,
        "protocol_sha256": protocol_sha, "train_target_cutoff": "2021-12-31",
        "max_train_target_date": str(train.target_date.max().date()),
        "max_train_origin": str(train.date.max().date()), "train_n": len(train),
        "train_complete_n": int(np.isfinite(train[F]).all(axis=1).sum()),
        "parameters": params, "settings": protocol["models"]["xgb_expanding"],
        "created_at_utc": completed, "configuration_sha256": contract_sha,
        "feature_generation_id": GENERATION, "supported_district_ids": [DISTRICT],
        "first_allowed_origin": "2023-01", "training_case_ids_sha256": json_hash(train.case_id.tolist()),
        "input_sha256": hashes, "implementation_sha256": {"builder": horizon.sha256_file(Path(__file__))},
        "shadow_artifact_approved": False, "forecast_issued_at": None,
        "historical_availability_verified": False, "no_model_selection_or_tuning": True,
        "scope_caveats": plan["scientific_limits"]}
    card_path = horizon.save_research_model(model, card, ARTIFACT, "xgb_fixed_2021")
    reloaded, saved_card = horizon.load_research_model(card_path, 12, protocol_sha, F)
    eligible = cases.loc[cases.date.between("2023-01-01", "2024-12-01")
        & cases.reference_eligible & np.isfinite(cases[F]).all(axis=1)].copy()
    prediction = reloaded.predict(eligible[F]).astype(float)
    if len(eligible) != 24 or not np.allclose(prediction, model.predict(eligible[F]), rtol=0, atol=1e-8):
        raise ValueError("Historical reload checks failed")
    eligible["fixed_xgb_2021"] = prediction
    eligible["annual_baseline"] = eligible.gwl_current
    eligible["forecast_issued_at"] = None
    eligible["output_kind"] = "historical_research_current_vintage"
    eligible["model_sha256"] = saved_card["model_sha256"]
    columns = ["case_id", "district_id", "date", "target_date", "target_value", "annual_baseline",
               "fixed_xgb_2021", "forecast_issued_at", "output_kind", "model_sha256"]
    with (ARTIFACT / "historical_checks.csv").open("x", encoding="utf-8", newline="") as handle:
        eligible[columns].to_csv(handle, index=False)
    old = pd.read_csv(OLD / "evaluation/exact_name_coordinate_predictions.csv", parse_dates=["date", "target_date"])
    parity = eligible.loc[eligible.target_date.dt.year.eq(2024)].merge(
        old[["case_id", "xgb_expanding"]], on="case_id", validate="one_to_one")
    delta = float(np.max(np.abs(parity.fixed_xgb_2021 - parity.xgb_expanding)))
    if len(parity) != 12 or delta > 1e-8:
        raise ValueError("Equivalent 2024 fixed-cutoff checkpoint parity failed")
    manifest = {"schema_version": 1, "contract_sha256": contract_sha,
        "card_path": card_path.name, "card_sha256": horizon.sha256_file(card_path),
        "snapshot_path": "features.csv", "snapshot_sha256": horizon.sha256_file(ARTIFACT / "features.csv"),
        "input_provenance_path": "input_provenance.json", "input_provenance_sha256": horizon.sha256_file(ARTIFACT / "input_provenance.json"),
        "provenance_path": "provenance.json", "provenance_sha256": horizon.sha256_file(ARTIFACT / "provenance.json")}
    write_json(ARTIFACT / "manifest.json", manifest)
    CONFIG.parent.mkdir(exist_ok=True)
    write_json(CONFIG, {"contract": contract, "contract_sha256": contract_sha,
        "manifest_path": str((ARTIFACT / "manifest.json").relative_to(ROOT)).replace("\\", "/"),
        "manifest_sha256": horizon.sha256_file(ARTIFACT / "manifest.json")})
    results = {"started_at_utc": started, "completed_at_utc": completed, "fit_count": 1,
        "family": "xgboost", "train_n": len(train), "complete_train_n": 158,
        "training_missing_by_feature": train[F].isna().sum().to_dict(),
        "snapshot_rows": len(snapshot), "input_provenance_rows": len(provenance["rows"]),
        "plan_sha256": horizon.sha256_file(RUN / "build_plan.json"),
        "configuration_sha256": contract_sha, "descriptor_sha256": horizon.sha256_file(CONFIG),
        "model_sha256": saved_card["model_sha256"], "card_sha256": manifest["card_sha256"],
        "manifest_sha256": horizon.sha256_file(ARTIFACT / "manifest.json"),
        "reload_predictions_equal": True, "equivalent_2024_parity_n": len(parity),
        "equivalent_2024_max_abs_difference_m": delta,
        "own_historical_24_case_check": {"fixed_xgb": metrics(eligible.target_value, prediction),
            "annual_baseline": metrics(eligible.target_value, eligible.gwl_current)},
        "interpretation": "Own fixed-cutoff check, not the old expanding comparison; no tuning or model selection",
        "prospective_forecasts_issued": 0, "active_pointer_changes": 0, "database_accessed": False,
        "source_downloads": 0, "hgb_fitted": False, "shadow_artifact_approved": False}
    write_json(RUN / "artifact_build.json", results)
    print(json.dumps(results, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
