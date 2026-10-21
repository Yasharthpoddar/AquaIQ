"""Synthetic bundle/API checks: no fitting, real model loading, DB or network.

Fixtures are deliberately tiny and carry no real observations. The estimator
loader is replaced by a recording fake; model bytes are inert synthetic text.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from api.app import create_app
from models import research_forecast as service


@pytest.fixture(autouse=True)
def forbid_runtime_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Synthetic research API tests must not connect to a database or fit models")
    import db.connection
    from api import district_resolver
    from models import xgboost_model
    monkeypatch.setattr(db.connection, "get_connection", forbidden)
    monkeypatch.setattr(district_resolver, "get_connection", forbidden)
    monkeypatch.setattr(xgboost_model, "get_connection", forbidden)
    import xgboost
    monkeypatch.setattr(xgboost.XGBRegressor, "fit", forbidden)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(service.research, "ROOT", tmp_path)
    monkeypatch.setattr(service.research, "RESEARCH_ROOT", tmp_path / "reports" / "candidates")
    directory = tmp_path / "reports" / "candidates" / "twelve_month_horizon_fixture" / "artifact"
    directory.mkdir(parents=True)
    contract = {"schema_version": 1, "product": service.PRODUCT, "horizon_months": 12,
                "embargo_months": 12, "features": service.FEATURES.copy(), "feature_units": service.FEATURE_UNITS.copy(),
                "units": "m_bgl", "feature_generation_id": service.GENERATION,
                "supported_district_ids": service.SUPPORTED.copy(), "allowed_use": "historical_research_only",
                "protocol_sha256": service.PROTOCOL_SHA256, "train_target_cutoff": "2021-12-31",
                "first_allowed_origin": "2023-01", "max_weather_carry_months": 2, "max_gwl_carry_months": 3}
    config_hash = service._canonical_hash(contract)
    (directory / "model.json").write_text("SYNTHETIC INERT TEST MODEL", encoding="utf-8")
    card = {"research_schema_version": 1, "research_only": True, "allowed_use": "historical_research_only",
            "horizon_months": 12, "embargo_months": 12, "family": "xgboost", "features": service.FEATURES.copy(),
            "feature_schema_sha256": service.research.schema_hash(service.FEATURES), "units": "m_bgl",
            "protocol_sha256": service.PROTOCOL_SHA256, "train_target_cutoff": "2021-12-31",
            "max_train_target_date": "2021-12-01", "max_train_origin": "2020-12-01",
            "configuration_sha256": config_hash, "feature_generation_id": service.GENERATION,
            "supported_district_ids": service.SUPPORTED.copy(), "feature_units": service.FEATURE_UNITS.copy(),
            "shadow_artifact_approved": False, "model_path": "model.json",
            "settings": {"parameters": service.XGB_PARAMETERS.copy()},
            "model_sha256": service.research.sha256_file(directory / "model.json")}
    write_json(directory / "card.json", card)
    rows, provenance_rows = [], []
    for index, month in enumerate(("2022-01", "2023-01", "2023-02", "2024-01", "2024-02", "2026-05")):
        values = {feature: float(index + 1) for feature in service.FEATURES}
        values.update(district_id="TS-Adilabad", date=month + "-01", is_observed=month != "2023-02",
                      is_imputed=month == "2023-02", units="m_bgl", feature_generation=service.GENERATION,
                      first_reported_date=month + "-01", last_reported_date=month + "-01",
                      well_count=2, panel_sha256="synthetic-panel")
        if month == "2026-05":
            values["temperature"] = np.nan
        rows.append(values)
        flags = []
        origin = service.parse_month(month)
        for feature in service.FEATURES:
            lag = 3 if feature == "gwl_lag_3mo" else 6 if feature == "gwl_lag_6mo" else 0
            source = (origin - pd.DateOffset(months=lag)).strftime("%Y-%m")
            flags.append({"feature": feature, "status": "calendar" if feature.startswith("season_") else "observed",
                          "required_month": source, "source_month": source, "age_months": 0})
        provenance_rows.append({"district_id": "TS-Adilabad", "date": month + "-01", "inputs": flags})
    pd.DataFrame(rows).to_csv(directory / "features.csv", index=False)
    write_json(directory / "inputs.json", {"schema_version": 1, "feature_generation_id": service.GENERATION,
                                            "rows": provenance_rows})
    write_json(directory / "provenance.json", {"synthetic_test_fixture": True, "availability_verified": False})
    manifest = {"schema_version": 1, "contract_sha256": config_hash, "card_path": "card.json",
                "snapshot_path": "features.csv", "input_provenance_path": "inputs.json", "provenance_path": "provenance.json"}
    config_path = tmp_path / "research" / "twelve_month_app.json"
    config_path.parent.mkdir()
    config = {"contract": contract, "contract_sha256": config_hash,
              "manifest_path": str((directory / "manifest.json").relative_to(tmp_path)).replace("\\", "/")}
    calls = []

    def refresh():
        for prefix in ("card", "snapshot", "input_provenance", "provenance"):
            manifest[prefix + "_sha256"] = service.research.sha256_file(directory / manifest[prefix + "_path"])
        write_json(directory / "manifest.json", manifest)
        config["manifest_sha256"] = service.research.sha256_file(directory / "manifest.json")
        write_json(config_path, config)

    class FakeModel:
        def predict(self, frame):
            calls.append(frame.copy())
            return np.array([4.75])

    def load(card_path, expected_horizon, protocol_sha256, feature_columns):
        assert expected_horizon == 12
        assert protocol_sha256 == service.PROTOCOL_SHA256
        assert feature_columns == service.FEATURES
        return FakeModel(), card

    monkeypatch.setattr(service.research, "load_research_model", load)
    refresh()
    client = create_app({"TESTING": True, "RESEARCH_FORECAST_CONFIG_PATH": str(config_path)}).test_client()
    return {"client": client, "directory": directory, "config": config, "config_path": config_path,
            "card": card, "manifest": manifest, "calls": calls, "refresh": refresh, "inputs": provenance_rows}


def test_calendar_target_and_annual_baseline_are_one_effective_method(bundle):
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01&months=12")
    assert result.status_code == 200
    value = result.json
    assert value["product"] == "direct_12month_research" and value["horizon_months"] == 12
    assert value["origin_month"] == "2023-01" and value["target_month"] == "2024-01"
    assert value["status"] == "available" and value["output_kind"] == "historical_research"
    assert value["ml_estimate_m"] == 4.75 and value["annual_baseline_m"] == 2.0
    assert value["observed_target_m"] == 4.0 and value["units"] == "m_bgl"
    assert value["forecast_issued_at"] is None
    assert pd.Timestamp(value["computed_at"]).tzinfo is not None
    assert value["source"]["availability_verified"] is False
    assert value["source"]["datum_continuity_verified"] is False
    assert value["scope"]["metadata_agreement_only"] is True
    assert list(bundle["calls"][0].columns) == service.FEATURES
    assert "target_value" not in bundle["calls"][0]
    assert len(bundle["calls"]) == 1


@pytest.mark.parametrize("month,target", [("2023-02", "2024-02"), ("2023-12", "2024-12"), ("2024-02", "2025-02")])
def test_exact_calendar_target_without_row_shift(month, target):
    assert service.target_month(month) == target


def test_catalog_has_supported_scope_and_latest_observed_origin(bundle):
    result = bundle["client"].get("/api/research/forecast")
    assert result.status_code == 200
    data = result.json
    assert data["horizon_months"] == 12
    assert data["districts"][0]["latest_observed_month"] == "2026-05"
    assert data["districts"][0]["origin_months"][-1] == "2026-05"
    assert data["scope"]["supported_district_ids"] == ["TS-Adilabad"]
    assert not bundle["calls"]


def test_default_never_falls_back_from_latest_observation_to_complete_old_row(bundle):
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad")
    assert result.status_code == 200
    value = result.json
    assert value["origin_month"] == "2026-05" and value["target_month"] == "2027-05"
    assert value["status"] == "unavailable" and value["ml_estimate_m"] is None
    assert value["annual_baseline_m"] == 6.0
    assert any("temperature" in reason for reason in value["unavailable_reasons"])
    assert any("historical research only" in reason for reason in value["unavailable_reasons"])
    assert not bundle["calls"]


def test_unobserved_origin_cannot_supply_baseline_or_ml(bundle):
    value = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-02").json
    assert value["annual_baseline_m"] is None and value["ml_estimate_m"] is None
    assert value["source"]["origin_is_imputed"] is True
    assert not bundle["calls"]


def test_imputed_target_is_not_an_observed_evaluation_label(bundle):
    path = bundle["directory"] / "features.csv"
    frame = pd.read_csv(path)
    frame.loc[frame.date.eq("2024-01-01"), ["is_observed", "is_imputed"]] = [False, True]
    frame.to_csv(path, index=False)
    bundle["refresh"]()
    value = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01").json
    assert value["ml_estimate_m"] is None and "observed_target_m" not in value
    assert not bundle["calls"]


def test_changing_target_label_does_not_change_model_inputs(bundle):
    client = bundle["client"]
    first = client.get("/api/research/forecast/TS-Adilabad?origin_month=2023-01").json
    path = bundle["directory"] / "features.csv"
    frame = pd.read_csv(path)
    frame.loc[frame.date.eq("2024-01-01"), "gwl_current"] = 98765.0
    frame.to_csv(path, index=False)
    bundle["refresh"]()
    second = client.get("/api/research/forecast/TS-Adilabad?origin_month=2023-01").json
    assert first["ml_estimate_m"] == second["ml_estimate_m"]
    assert second["observed_target_m"] == 98765.0
    pd.testing.assert_frame_equal(*bundle["calls"])


@pytest.mark.parametrize("district", ["GJ-Gandhinagar", "TS-Hyderabad", "legacy-adilabad", "unknown"])
def test_unsupported_districts_never_borrow_another_population(bundle, district):
    result = bundle["client"].get("/api/research/forecast/" + district)
    assert result.status_code == 200
    value = result.json
    assert value["status"] == "unavailable" and value["origin_month"] is None
    assert value["ml_estimate_m"] is None and value["annual_baseline_m"] is None
    assert any("scope" in reason for reason in value["unavailable_reasons"])
    assert not bundle["calls"]


@pytest.mark.parametrize("query", ["months=6", "months=12.0", "origin_month=2023-13", "origin_month=2023-01-01",
                                  "origin_month=", "as_of=2023-01-01", "origin_month=2023-01&origin_month=2024-01",
                                  "months=12&months=12", "window=observed_endpoint"])
def test_invalid_queries_fail_before_bundle_access(bundle, monkeypatch, query):
    monkeypatch.setattr(service, "_load_bundle", lambda *args: pytest.fail("Invalid query accessed artifacts"))
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?" + query)
    assert result.status_code == 400


@pytest.mark.parametrize("field,value", [("horizon_months", 6), ("features", list(reversed(service.FEATURES))),
                                       ("units", "feet"), ("feature_generation_id", "other"),
                                       ("configuration_sha256", "0" * 64), ("supported_district_ids", ["TS-Hyderabad"]),
                                       ("train_target_cutoff", "2022-12-31"), ("family", "hist_gradient_boosting")])
def test_incompatible_cards_fail_before_estimator_loading(bundle, field, value):
    bundle["card"][field] = value
    write_json(bundle["directory"] / "card.json", bundle["card"])
    bundle["refresh"]()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.status_code == 503
    assert result.json["ml_estimate_m"] is None
    assert not bundle["calls"]


@pytest.mark.parametrize("filename", ["model.json", "card.json", "features.csv", "inputs.json", "provenance.json", "manifest.json"])
def test_revised_bundle_bytes_fail_immutable_checks(bundle, filename):
    path = bundle["directory"] / filename
    path.write_bytes(path.read_bytes() + b"\nrevised")
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.status_code == 503 and result.json["ml_estimate_m"] is None
    assert not bundle["calls"]


@pytest.mark.parametrize("defect", ["stale", "future", "unknown", "wrong_lag"])
def test_invalid_input_provenance_prevents_prediction(bundle, defect):
    entry = bundle["inputs"][1]["inputs"]
    flag = next(flag for flag in entry if flag["feature"] == ("gwl_lag_6mo" if defect == "wrong_lag" else "temperature"))
    if defect == "stale":
        flag.update(status="carried_forward", age_months=3, source_month="2022-10")
    elif defect == "future":
        flag["source_month"] = "2024-01"
    elif defect == "wrong_lag":
        flag["source_month"] = "2022-08"
    else:
        flag["status"] = "unknown"
    write_json(bundle["directory"] / "inputs.json", {"schema_version": 1, "feature_generation_id": service.GENERATION,
                                                      "rows": bundle["inputs"]})
    bundle["refresh"]()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.status_code == 200
    assert result.json["ml_estimate_m"] is None and result.json["unavailable_reasons"]
    assert not bundle["calls"]


def test_carried_weather_within_locked_limit_is_explicit(bundle):
    flag = next(flag for flag in bundle["inputs"][1]["inputs"] if flag["feature"] == "temperature")
    flag.update(status="carried_forward", source_month="2022-11", age_months=2)
    write_json(bundle["directory"] / "inputs.json", {"schema_version": 1, "feature_generation_id": service.GENERATION,
                                                      "rows": bundle["inputs"]})
    bundle["refresh"]()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.json["status"] == "available"
    assert next(flag for flag in result.json["source"]["input_flags"] if flag["feature"] == "temperature")["status"] == "carried_forward"


@pytest.mark.parametrize("defect", ["future", "stale", "unknown"])
def test_derived_features_cannot_hide_ineligible_dependencies(bundle, defect):
    flag = next(flag for flag in bundle["inputs"][1]["inputs"] if flag["feature"] == "water_balance_proxy")
    dependency = {"feature": "temperature", "status": "observed", "required_month": "2023-01",
                  "source_month": "2023-01", "age_months": 0}
    if defect == "future":
        dependency["source_month"] = "2024-01"
    elif defect == "stale":
        dependency.update(status="carried_forward", source_month="2022-10", age_months=3)
    else:
        dependency["status"] = "unknown"
    flag.update(status="derived_with_carried_input", dependencies=[dependency])
    write_json(bundle["directory"] / "inputs.json", {"schema_version": 1, "feature_generation_id": service.GENERATION,
                                                      "rows": bundle["inputs"]})
    bundle["refresh"]()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.json["ml_estimate_m"] is None
    assert any("dependencies" in reason for reason in result.json["unavailable_reasons"])
    assert not bundle["calls"]


@pytest.mark.parametrize("field,value", [("units", "feet"), ("feature_generation", "other-generation"),
                                       ("district_id", "TS-Hyderabad")])
def test_snapshot_units_generation_and_scope_are_checked(bundle, field, value):
    path = bundle["directory"] / "features.csv"
    frame = pd.read_csv(path)
    frame.loc[0, field] = value
    frame.to_csv(path, index=False)
    bundle["refresh"]()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.status_code == 503
    assert not bundle["calls"]


def test_unobserved_calendar_padding_may_omit_measurement_units(bundle):
    path = bundle["directory"] / "features.csv"
    frame = pd.read_csv(path)
    frame.loc[frame.date.eq("2023-02-01"), "units"] = None
    frame.to_csv(path, index=False)
    bundle["refresh"]()
    assert bundle["client"].get("/api/research/forecast").status_code == 200
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-02").json
    assert result["ml_estimate_m"] is None and result["annual_baseline_m"] is None
    assert not bundle["calls"]


def test_observed_measurement_cannot_omit_its_units(bundle):
    path = bundle["directory"] / "features.csv"
    frame = pd.read_csv(path)
    frame.loc[frame.date.eq("2023-01-01"), "units"] = None
    frame.to_csv(path, index=False)
    bundle["refresh"]()
    assert bundle["client"].get("/api/research/forecast").status_code == 503
    assert not bundle["calls"]


def test_model_path_cannot_escape_dedicated_bundle(bundle):
    bundle["card"]["model_path"] = "../model.json"
    write_json(bundle["directory"] / "card.json", bundle["card"])
    bundle["refresh"]()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.status_code == 503
    assert not bundle["calls"]


def test_locked_hyperparameters_are_not_changed_by_card(bundle):
    bundle["card"]["settings"]["parameters"]["n_estimators"] = 501
    write_json(bundle["directory"] / "card.json", bundle["card"])
    bundle["refresh"]()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.status_code == 503
    assert not bundle["calls"]


def test_security_sensitive_metadata_is_blocked_and_never_echoed(bundle):
    value = "SYNTHETIC_TEST_ONLY_DO_NOT_ECHO"
    write_json(bundle["directory"] / "provenance.json", {"headers": {"Set-Cookie": value}})
    bundle["refresh"]()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.status_code == 503
    assert value not in result.get_data(as_text=True)
    assert not bundle["calls"]


def test_missing_artifact_errors_do_not_echo_local_paths(bundle):
    (bundle["directory"] / "features.csv").unlink()
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2023-01")
    assert result.status_code == 503
    assert str(bundle["directory"]) not in result.get_data(as_text=True)


def test_old_origins_are_blocked_by_cutoff_and_complete_embargo(bundle):
    result = bundle["client"].get("/api/research/forecast/TS-Adilabad?origin_month=2022-01")
    assert result.json["status"] == "unavailable"
    assert any("embargo" in reason for reason in result.json["unavailable_reasons"])
    assert not bundle["calls"]


def test_legacy_six_month_dispatch_remains_separate(bundle, monkeypatch):
    from api.routes import predict
    calls = []
    monkeypatch.setattr(predict, "resolve_district_id", lambda value: "GJ-Gandhinagar")
    monkeypatch.setattr(predict, "forecast_result", lambda *args: calls.append(args) or {"status": "historical_forecast", "forecast": []})
    result = bundle["client"].get("/api/predict/legacy-id?months=6")
    assert result.status_code == 200 and len(calls) == 1
    assert not bundle["calls"]


def test_primary_metadata_does_not_relabel_legacy_products(bundle):
    root = bundle["client"].get("/").json
    metadata = bundle["client"].get("/api/config").json
    assert root["primary_research_horizon_months"] == 12
    assert root["prospective_skill_verified"] is False
    assert metadata["primary_forecast"]["horizon_months"] == 12
    assert metadata["primary_forecast"]["product"] == service.PRODUCT
    assert metadata["primary_forecast"]["prospective_skill_verified"] is False
    legacy = metadata["secondary_forecasts"]
    assert legacy[0]["horizon_months"] == 6
    assert legacy[1]["horizons_months"] == [1, 2, 3, 4, 5, 6]
    assert "not_recalibrated" in metadata["risk_index_forecast_basis"]
    assert not bundle["calls"]


def test_legacy_default_and_monthly_dispatch_keep_their_own_contract(bundle, monkeypatch):
    from api.routes import predict
    calls = []
    monkeypatch.setattr(predict, "resolve_district_id", lambda value: "GJ-Gandhinagar")
    monkeypatch.setattr(predict, "forecast_result", lambda *args: calls.append("six-month") or {"forecast": []})
    monkeypatch.setattr(predict, "forecast_next_six_months", lambda *args: calls.append("monthly-1-to-6") or {"forecast": []})
    assert bundle["client"].get("/api/predict/legacy-id").status_code == 200
    assert bundle["client"].get("/api/predict/legacy-id?window=next_six_months").status_code == 200
    assert bundle["client"].get("/api/predict/legacy-id?months=12").status_code == 400
    assert calls == ["six-month", "monthly-1-to-6"]
    assert not bundle["calls"]
