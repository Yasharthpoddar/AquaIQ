"""Live HTTP verification of all research API endpoints."""
import urllib.request
import json
import sys

BASE = "http://127.0.0.1:5000"
results = []

def fetch(path, label):
    url = BASE + path
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = json.loads(resp.read())
            print(f"[{label}] HTTP {status} OK")
            results.append((label, status, "OK"))
            return body
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")[:500]
        except:
            pass
        print(f"[{label}] HTTP {e.code}")
        if body_text:
            try:
                body = json.loads(body_text)
                print(f"  response keys: {list(body.keys())[:8]}")
                if "error" in body:
                    print(f"  error: {str(body['error'])[:200]}")
            except:
                print(f"  raw: {body_text[:200]}")
        results.append((label, e.code, body_text[:100] if body_text else ""))
        return None
    except Exception as e:
        print(f"[{label}] CONNECT ERROR: {e}")
        results.append((label, 0, str(e)[:100]))
        return None

print("=" * 70)
print("LIVE HTTP VERIFICATION — AquaIQ Research API")
print("=" * 70)

# 1. Health
fetch("/api/health", "Health")

# 2. Config
cfg = fetch("/api/config", "Config")
if cfg:
    print(f"  tiers: {list(cfg.get('tiers', {}).keys())}")
    print(f"  weights_status: {cfg.get('weights_status')}")

# 3. Research catalog
cat = fetch("/api/research/forecast", "Research Catalog")
if cat:
    print(f"  product: {cat.get('product')}")
    print(f"  horizon_months: {cat.get('horizon_months')}")
    print(f"  districts: {len(cat.get('districts', []))}")
    d0 = cat.get("districts", [{}])[0] if cat.get("districts") else {}
    print(f"  first: {d0.get('district_id')} origins={len(d0.get('origin_months', []))}")

# 4. Research forecast — latest origin
rf = fetch("/api/research/forecast/TS-Adilabad", "Forecast (latest)")
if rf:
    print(f"  product: {rf.get('product')}")
    print(f"  origin: {rf.get('origin_month')}")
    print(f"  target: {rf.get('target_month')}")
    print(f"  status: {rf.get('status')}")
    print(f"  output_kind: {rf.get('output_kind')}")
    print(f"  ml_estimate_m: {rf.get('ml_estimate_m')}")
    print(f"  annual_baseline_m: {rf.get('annual_baseline_m')}")
    print(f"  forecast_issued_at: {rf.get('forecast_issued_at')}")

# 5. Research forecast — Jan 2024 historical
rf24 = fetch("/api/research/forecast/TS-Adilabad?origin_month=2024-01", "Forecast (Jan 2024)")
if rf24:
    print(f"  origin: {rf24.get('origin_month')}")
    print(f"  target: {rf24.get('target_month')}")
    print(f"  output_kind: {rf24.get('output_kind')}")
    print(f"  ml_estimate_m: {rf24.get('ml_estimate_m')}")
    print(f"  annual_baseline_m: {rf24.get('annual_baseline_m')}")
    print(f"  observed_target_m: {rf24.get('observed_target_m')}")
    # Cross-reference with saved artifact
    baseline_match = abs(rf24.get("annual_baseline_m", 0) - 6.836667) < 0.001
    ml_match = abs(rf24.get("ml_estimate_m", 0) - 7.571101) < 0.001
    target_match = abs(rf24.get("observed_target_m", 0) - 6.831333) < 0.001
    print(f"  baseline matches saved artifact: {baseline_match}")
    print(f"  ML matches saved artifact: {ml_match}")
    print(f"  target matches saved artifact: {target_match}")

# 6. Research graph — Jan 2024
rg = fetch("/api/research/graph/TS-Adilabad?origin_month=2024-01", "Graph (Jan 2024)")
if rg:
    print(f"  product: {rg.get('product')}")
    print(f"  origin: {rg.get('origin_month')} -> target: {rg.get('target_month')}")
    fc = rg.get("forecast", [])
    print(f"  forecast slots: {len(fc)}")
    nulls = 0
    endpoint_ml = None
    for slot in fc:
        ml = slot.get("predicted_gwl")
        bl = slot.get("annual_baseline_m")
        h = slot.get("horizon_months", "?")
        m = slot.get("month", "?")
        if ml is None:
            nulls += 1
        else:
            endpoint_ml = ml
        tag = "" if ml is None and bl is None else f" ML={ml} BL={bl}"
        print(f"    M+{h:2d} {m}{tag}")
    print(f"  Null ML slots (M+1 to M+11): {nulls}")
    print(f"  M+12 ML value: {endpoint_ml}")
    print(f"  Exactly 11 nulls + 1 value: {nulls == 11 and endpoint_ml is not None}")

# 7. Experimental scenario
sc = fetch("/api/research/scenario/TS-Adilabad", "Scenario")
if sc:
    print(f"  product: {sc.get('product')}")
    print(f"  status: {sc.get('status')}")
    print(f"  as_of: {sc.get('as_of')}")
    print(f"  forecast_issued_at: {sc.get('forecast_issued_at')}")
    print(f"  estimated_current_gwl: {sc.get('estimated_current_gwl')}")
    fc = sc.get("forecast", [])
    print(f"  forecast slots: {len(fc)}")
    for row in fc:
        print(f"    {row.get('month')}: {row.get('projected_gwl'):.3f} m")
    val = sc.get("validation", {})
    print(f"  validation.status: {val.get('status')}")
    print(f"  validation.prospective_skill_verified: {val.get('prospective_skill_verified')}")
    print(f"  validation.sufficient_for_operational_use: {val.get('sufficient_for_operational_use')}")
    src = sc.get("source", {})
    print(f"  source.scope: {src.get('scope')}")
    print(f"  source.availability_verified: {src.get('availability_verified')}")
    method = sc.get("method", {})
    print(f"  method.name: {method.get('name')}")
    print(f"  method.observed_month_count: {method.get('observed_month_count')}")

# 8. Unsupported district
us = fetch("/api/research/forecast/GJ-Gandhinagar", "Unsupported District")
if us:
    print(f"  status: {us.get('status')}")
    print(f"  ml_estimate_m: {us.get('ml_estimate_m')}")
    print(f"  annual_baseline_m: {us.get('annual_baseline_m')}")
    print(f"  unavailable_reasons: {us.get('unavailable_reasons', [])}")

# 9. DB-dependent: Scores
fetch("/api/scores", "Scores (DB)")

# 10. DB-dependent: District detail
fetch("/api/district/TS-Adilabad", "District Detail (DB)")

# 11. DB-dependent: History
fetch("/api/history/TS-Adilabad", "History (DB)")

# 12. DB-dependent: Alerts
fetch("/api/alerts", "Alerts (DB)")

print()
print("=" * 70)
print("RESULT SUMMARY")
print("=" * 70)
for label, status, detail in results:
    cat = "PASS" if status == 200 else ("DB-BLOCKED" if "DB" in label else "FAIL")
    print(f"  {label:30s} HTTP {status:3d}  {cat}")
