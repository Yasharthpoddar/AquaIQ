"""Loopback-only audit requests; no retries, writes, downloads, training or cookies."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen

OUT = Path(__file__).resolve().parent / "live_http_20261023.json"
CASES = []
previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None


def case(name, path, port=5053, expected=200, method="GET", body=None, origin=None):
    CASES.append({"name": name, "port": port, "path": path, "expected_status": expected,
                  "method": method, "request_body": body, "origin": origin})


for name, path in (("root", "/"), ("config", "/api/config"), ("health", "/api/health"),
                   ("scores", "/api/scores"), ("catalog", "/api/research/forecast")):
    case(name, path)
case("cors_allowed", "/api/config", origin="http://127.0.0.1:5183")
case("cors_other_origin", "/api/config", origin="http://127.0.0.1:5999")
for origin in (None, "2024-01", "2026-05"):
    query = "?months=12" + ("&origin_month=" + origin if origin else "")
    label = origin or "default"
    case("direct_adilabad_" + label, "/api/research/forecast/TS-Adilabad" + query)
    case("graph_adilabad_" + label, "/api/research/graph/TS-Adilabad" + query)
case("direct_unsupported_kaithal", "/api/research/forecast/HR-Kaithal?months=12")
case("graph_unsupported_kaithal", "/api/research/graph/HR-Kaithal?months=12")
for district in ("HR-Kaithal", "HR-Kurukshetra", "TS-Adilabad", "AN-Nicobars", "XX-Unknown"):
    case("scenario_" + district, "/api/research/scenario/" + district + "?months=12")
for district in ("HR-Kaithal", "TS-Adilabad", "AN-Nicobars"):
    case("predict_" + district, "/api/predict/" + district)
    case("district_" + district, "/api/district/" + district)
case("predict_next_six", "/api/predict/HR-Kaithal?window=next_six_months&months=6")
case("predict_next_six_insufficient", "/api/predict/AN-Nicobars?window=next_six_months&months=6")
case("history_kaithal", "/api/history/HR-Kaithal?start=2025-01&end=2026-10")
case("history_adilabad", "/api/history/TS-Adilabad?start=2025-01&end=2026-10")
case("alerts_default", "/api/alerts")
case("alerts_full", "/api/alerts?limit=1000")
case("alerts_crisis", "/api/alerts?tier=Crisis&limit=1000")
for name, path in (
    ("catalog_extra_query", "/api/research/forecast?months=12"),
    ("direct_wrong_horizon", "/api/research/forecast/TS-Adilabad?months=6"),
    ("graph_repeated_horizon", "/api/research/graph/TS-Adilabad?months=12&months=12"),
    ("graph_bad_origin", "/api/research/graph/TS-Adilabad?origin_month=2024-13"),
    ("graph_legacy_window", "/api/research/graph/TS-Adilabad?window=next_six_months"),
    ("scenario_wrong_horizon", "/api/research/scenario/HR-Kaithal?months=6"),
    ("scenario_future_date", "/api/research/scenario/HR-Kaithal?as_of=2999-01-01"),
    ("scenario_repeated_date", "/api/research/scenario/HR-Kaithal?as_of=2026-10-01&as_of=2026-10-01"),
    ("scenario_origin_query", "/api/research/scenario/HR-Kaithal?origin_month=2024-01"),
    ("predict_wrong_horizon", "/api/predict/HR-Kaithal?months=12"),
    ("predict_bad_window", "/api/predict/HR-Kaithal?window=bad"),
    ("predict_unsupported_year", "/api/predict/HR-Kaithal?target_year=2027"),
    ("predict_future_date", "/api/predict/HR-Kaithal?as_of=2999-01-01"),
    ("history_bad_range", "/api/history/HR-Kaithal?start=2026-10&end=2025-01"),
    ("history_bad_count", "/api/history/HR-Kaithal?months=0"),
    ("alerts_bad_tier", "/api/alerts?tier=unknown"),
    ("alerts_bad_limit", "/api/alerts?limit=1001")):
    case(name, path, expected=400)
case("predict_unknown", "/api/predict/XX-Unknown", expected=404)
case("simulate_zero", "/api/simulate", method="POST", body={"district_id": "HR-Kaithal"})
case("simulate_extraction_sensitivity", "/api/simulate", method="POST",
     body={"district_id": "HR-Kaithal", "rainfall_change_pct": 0, "extraction_change_pct": 10})
case("simulate_invalid_boolean", "/api/simulate", expected=400, method="POST",
     body={"district_id": "HR-Kaithal", "rainfall_change_pct": True})
for name, path in (("scores", "/api/scores"), ("district", "/api/district/TS-Adilabad"),
                   ("predict", "/api/predict/TS-Adilabad"), ("scenario", "/api/research/scenario/TS-Adilabad?months=12"),
                   ("health", "/api/health")):
    case("old_guard_" + name, path, port=5051, expected=403, origin="http://127.0.0.1:5181")
case("old_guard_working_graph", "/api/research/graph/TS-Adilabad?months=12&origin_month=2024-01", port=5051)
case("old_guard_working_catalog", "/api/research/forecast", port=5051)
case("vite_html", "/", port=5183)
case("vite_config_proxy", "/api/config", port=5183)


def safe(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.search(r"cookie|authorization|password|secret|credential|token", k, re.I)
                else safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe(v) for v in value]
    return value


def fetch(item):
    started = perf_counter()
    url = "http://127.0.0.1:" + str(item["port"]) + item["path"]
    headers = {"Accept": "application/json"}
    if item["origin"]:
        headers["Origin"] = item["origin"]
    raw_body = None
    if item["request_body"] is not None:
        raw_body = json.dumps(item["request_body"], allow_nan=False).encode()
        headers["Content-Type"] = "application/json"
    req = Request(url, data=raw_body, headers=headers, method=item["method"])
    result = dict(item)
    result["url"] = url
    try:
        try:
            response = urlopen(req, timeout=120)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            result["status"] = response.status
            result["headers"] = {k: response.headers[k] for k in
                                 ("Content-Type", "Access-Control-Allow-Origin", "Vary") if k in response.headers}
            try:
                result["body"] = safe(json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))))
                result["strict_json"] = True
            except (ValueError, UnicodeError):
                result["strict_json"] = False
                result["body_metadata"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                                           "html_title": re.search(r"<title>(.*?)</title>", raw.decode("utf-8", errors="replace"), re.S).group(1)
                                           if b"<title>" in raw else None}
        result["status_matches_expected"] = result["status"] == result["expected_status"]
    except Exception as error:
        result["transport_error"] = type(error).__name__ + ": " + str(error)
        result["status_matches_expected"] = False
    result["elapsed_ms"] = round((perf_counter() - started) * 1000, 2)
    return result


def following(month, count=12):
    year, number = map(int, month.split("-"))
    absolute = year * 12 + number - 1
    return [f"{(absolute+i)//12:04d}-{(absolute+i)%12+1:02d}" for i in range(1, count+1)]


with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(fetch, CASES))
by_name = {r["name"]: r for r in results}
checks = []


def check(name, condition, detail=None):
    checks.append({"name": name, "passed": bool(condition), "detail": detail})


for item in results:
    if item["name"] != "vite_html":
        check(item["name"] + "_strict_json", item.get("strict_json") is True)
    check(item["name"] + "_http_status", item["status_matches_expected"], item.get("status", item.get("transport_error")))
for item in results:
    name, value = item["name"], item.get("body", {})
    if name.startswith("graph_") and item.get("status") == 200:
        rows = value.get("forecast", [])
        check(name + "_twelve_slots", len(rows) == 12)
        check(name + "_eleven_nulls", len(rows) == 12 and all(r.get("predicted_gwl") is None and r.get("annual_baseline_m") is None for r in rows[:11]))
        check(name + "_endpoint_retained", len(rows) == 12 and rows[-1].get("predicted_gwl") == value.get("ml_estimate_m") and rows[-1].get("annual_baseline_m") == value.get("annual_baseline_m"))
        check(name + "_identity", value.get("product") == "direct_12month_research_graph" and value.get("horizon_months") == 12)
        if value.get("origin_month"):
            check(name + "_exact_calendar", [r.get("month") for r in rows] == following(value["origin_month"]))
    if name.startswith("scenario_") and item.get("status") == 200:
        check(name + "_unvalidated", value.get("validation") == {"status": "unvalidated_scenario", "prospective_skill_verified": False, "sufficient_for_operational_use": False})
        check(name + "_no_issuance", value.get("forecast_issued_at") is None and value.get("source", {}).get("availability_verified") is False)
        if value.get("status") == "scenario":
            rows = value.get("forecast", [])
            check(name + "_twelve_months", [r.get("month") for r in rows] == following(value["as_of"][:7]))
            check(name + "_date_horizons", len(rows) == 12 and all(r.get("date") == r["month"] + "-01" and r.get("horizon_months") == i+1 for i, r in enumerate(rows)))
            check(name + "_own_district", value.get("district_id") == name[len("scenario_"):] and value.get("source", {}).get("scope") == "district_own_observed_history")
        else:
            check(name + "_abstains", value.get("status") == "unavailable" and value.get("forecast") == [] and value.get("estimated_current_gwl") is None)
    if name.startswith("old_guard_") and item["expected_status"] == 403:
        check(name + "_exact_body", value == {"status": "unavailable", "error": "Legacy routes are excluded from this read-only demonstration."})
check("config_metadata_direct_primary", by_name["config"].get("body", {}).get("primary_forecast", {}).get("product") == "direct_12month_research")
check("cors_allowed_origin", by_name["cors_allowed"].get("headers", {}).get("Access-Control-Allow-Origin") == "http://127.0.0.1:5183")
check("cors_other_origin_header_absent", "Access-Control-Allow-Origin" not in by_name["cors_other_origin"].get("headers", {}))
check("latest_direct_ml_unavailable", by_name["direct_adilabad_default"].get("body", {}).get("ml_estimate_m") is None and by_name["direct_adilabad_default"].get("body", {}).get("origin_month") == "2026-05")
check("historical_direct_ml_available", by_name["direct_adilabad_2024-01"].get("body", {}).get("status") == "available" and by_name["direct_adilabad_2024-01"].get("body", {}).get("target_month") == "2025-01")
zero = by_name["simulate_zero"].get("body", {})
check("simulation_zero_parity", zero.get("baseline_score") == zero.get("simulated_score") and zero.get("delta") == 0)
six = by_name["predict_next_six"].get("body", {})
check("next_six_distinct_method", six.get("projection_method") == "climate_conditioned_xgboost_monthly" and six.get("horizon_months") == 6)
check("next_six_calendar", [r.get("month") for r in six.get("forecast", [])] == following(six.get("as_of", "0000-01")[:7], 6))
alerts = by_name["alerts_default"].get("body", {})
full = by_name["alerts_full"].get("body", {})
check("alerts_pagination", alerts.get("count") == 100 and alerts.get("has_more") is True and full.get("count") == full.get("total") and full.get("has_more") is False)
summary = {"requests": len(results), "status_mismatches": [r["name"] for r in results if not r["status_matches_expected"]],
           "contract_checks": len(checks), "failed_contract_checks": [c for c in checks if not c["passed"]]}
OUT.write_text(json.dumps({"collected_at_utc": datetime.now(timezone.utc).isoformat(),
                         "scope": "Existing routes served on loopback under parent audit-only read-only DB and no-active-ML-fit guards; normal transient NumPy scenario calculation permitted.",
                         "cookie_or_secret_headers_recorded": False,
                         "previous_attempt_summaries": ([{"collected_at_utc": previous.get("collected_at_utc"),
                                                          "requests": previous.get("summary", {}).get("requests"),
                                                          "status_mismatch_count": len(previous.get("summary", {}).get("status_mismatches", [])),
                                                          "transport_errors": sorted(set(r.get("transport_error", "") for r in previous.get("requests", []) if r.get("transport_error")))}]
                                                        if previous else []),
                         "summary": summary,
                         "checks": checks, "requests": results}, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({"requests": summary["requests"], "status_mismatches": summary["status_mismatches"],
                  "contract_checks": summary["contract_checks"], "failed_contract_check_count": len(summary["failed_contract_checks"]),
                  "failed_contract_check_names": [c["name"] for c in summary["failed_contract_checks"]]}, indent=2))
