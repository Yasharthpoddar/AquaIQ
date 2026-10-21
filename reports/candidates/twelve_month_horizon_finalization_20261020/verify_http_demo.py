"""Read the guarded localhost demo only; never fetch external sources or legacy APIs."""
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def main():
    destination = HERE / "http-demo-verification.json"
    if destination.exists():
        raise FileExistsError("Never replace verification evidence")
    results = []
    for address in ("http://127.0.0.1:5181/research", "http://127.0.0.1:5051/api/research/forecast",
                    "http://127.0.0.1:5051/api/research/forecast/TS-Adilabad",
                    "http://127.0.0.1:5051/api/research/forecast/TS-Adilabad?origin_month=2024-01"):
        with urlopen(Request(address, headers={"Origin": "http://127.0.0.1:5181"}), timeout=15) as reply:
            body = reply.read().decode()
            item = {"url": address, "http_status": reply.status,
                    "content_type": reply.headers.get("Content-Type"),
                    "cors_origin": reply.headers.get("Access-Control-Allow-Origin")}
            if "/api/" in address:
                item["response"] = json.loads(body)
            else:
                assert "12-Month Groundwater Research" in body and "/src/main.jsx" in body
                item["html_title_and_spa_entry_verified"] = True
            results.append(item)
    assert results[1]["response"]["horizon_months"] == 12
    assert results[2]["response"]["ml_estimate_m"] is None
    assert results[3]["response"]["status"] == "available"
    assert results[3]["response"]["ml_estimate_m"] == 7.57110071182251
    assert all(item["cors_origin"] == "http://127.0.0.1:5181" for item in results[1:])
    result = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "local_http_checks": results,
              "database_access_blocked_by_demo_server": True, "public_deployment": False,
              "browser_visual_check": "Not verified: browser automation failed twice before opening a tab: failed to write kernel assets; system cannot find the path specified (os error 3).",
              "browser_retry_after_kernel_reset": True, "database_backed_page_loaded": False}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps({"passed": True, "local_http_cases": len(results),
                      "browser_visual_check": False, "database_accessed": False}))


if __name__ == "__main__":
    main()
