"""Create-only verification of retained research assets; no fitting, DB or HTTP.

Calls use Flask's in-process test client and never create prospective records.
Run from the repository root with the existing environment and Python -B.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))


def forbidden(*args, **kwargs):
    raise AssertionError("Verification must not fit models or access the database")


def main():
    destination = HERE / "local-demo-verification.json"
    if destination.exists():
        raise FileExistsError("Use a fresh evidence destination; never overwrite results")
    from api.app import create_app
    from models import research_forecast as service

    with ExitStack() as guards:
        for name in ("psycopg2.connect", "db.connection.get_connection",
                     "api.district_resolver.get_connection", "models.xgboost_model.get_connection",
                     "xgboost.XGBRegressor.fit"):
            guards.enter_context(patch(name, forbidden))
        client = create_app({"TESTING": True}).test_client()
        catalog = client.get("/api/research/forecast")
        assert catalog.status_code == 200
        assert catalog.json["scope"]["supported_district_ids"] == ["TS-Adilabad"]
        latest = client.get("/api/research/forecast/TS-Adilabad")
        assert latest.status_code == 200
        current = latest.json
        assert (current["origin_month"], current["target_month"]) == ("2026-05", "2027-05")
        assert current["status"] == "unavailable" and current["ml_estimate_m"] is None
        assert np.isclose(current["annual_baseline_m"], 6.553333333333333)
        assert any("missing" in reason for reason in current["unavailable_reasons"])
        assert current["forecast_issued_at"] is None
        historical = client.get("/api/research/forecast/TS-Adilabad?origin_month=2024-01").json
        assert historical["status"] == "available"
        assert historical["target_month"] == "2025-01"
        assert historical["output_kind"] == "historical_research"
        assert historical["forecast_issued_at"] is None
        assert historical["source"]["availability_verified"] is False
        fixed = pd.read_csv(HERE / "artifact/historical_checks.csv")
        differences = []
        for row in fixed.itertuples():
            origin = str(row.date)[:7]
            response = client.get("/api/research/forecast/TS-Adilabad?origin_month=" + origin)
            assert response.status_code == 200
            value = response.json
            assert value["status"] == "available", value["unavailable_reasons"]
            assert value["target_month"] == str(row.target_date)[:7]
            assert np.isclose(value["observed_target_m"], row.target_value)
            assert np.isclose(value["annual_baseline_m"], row.annual_baseline)
            differences.append(abs(value["ml_estimate_m"] - row.fixed_xgb_2021))
        assert len(differences) == 24 and max(differences) < 1e-8
        carry = {}
        for origin in ("2025-01", "2025-02"):
            value = client.get("/api/research/forecast/TS-Adilabad?origin_month=" + origin).json
            assert value["status"] == "available", value["unavailable_reasons"]
            carry[origin] = [flag for flag in value["source"]["input_flags"]
                             if flag["feature"] in {"temperature", "evapotranspiration"}]
            assert all(flag["status"] == "carried_forward" and flag["source_month"] == "2024-12"
                       for flag in carry[origin])
        outside = client.get("/api/research/forecast/GJ-Gandhinagar").json
        assert outside["status"] == "unavailable"
        assert outside["ml_estimate_m"] is None and outside["annual_baseline_m"] is None
        assert client.get("/api/research/forecast/TS-Adilabad?months=6").status_code == 400
        assert client.get("/").json["primary_research_horizon_months"] == 12
        metadata = client.get("/api/config").json
        assert metadata["primary_forecast"]["horizon_months"] == 12
        assert metadata["secondary_forecasts"][0]["horizon_months"] == 6
        bundle = service._load_bundle()
        identified_files = {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (HERE / "artifact").iterdir() if path.is_file()
        }
    result = {"verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "in_process_file_only_historical_research_not_forecast_issuance",
              "database_and_fit_guards": True, "database_accessed": False,
              "network_requests": 0, "prospective_records_created": 0,
              "catalog": catalog.json, "default_result": current,
              "historical_january_2024": historical, "unsupported_district": outside,
              "archived_fixed_case_count": len(differences),
              "maximum_api_vs_archived_prediction_difference_m": max(differences),
              "explicit_weather_carry": carry, "contract_sha256": bundle["config_sha256"],
              "artifact_sha256": identified_files}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps({"passed": True, "checked_fixed_cases": len(differences),
                      "historical_ml_m": historical["ml_estimate_m"],
                      "historical_annual_baseline_m": historical["annual_baseline_m"],
                      "default_ml": current["ml_estimate_m"], "database_accessed": False}))


if __name__ == "__main__":
    main()
