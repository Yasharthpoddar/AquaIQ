# AquaIQ — Flask API Specification

Defines the request/response contract for all 5 endpoints, agreed before backend implementation begins. Field names match the `predictions`, `crisis_scores`, `raw_data`, and `districts` PostgreSQL tables.

---

## 1. `GET /predict/{district_id}`
Returns the forecasted Crisis Score for a district.

**Request**
- Path param: `district_id` (string) — e.g. `/predict/MH-Pune`

**Response — 200 OK**
```json
{
  "district_id": "MH-Pune",
  "crisis_score": 62,
  "risk_tier": "Warning",
  "forecast_horizon_months": 6,
  "estimate_type": "district_level",
  "forecast_date": "2027-02-01"
}
```

**Errors**
- `404 Not Found` — district_id does not exist
- `500 Internal Server Error` — model failed to produce a score

---

## 2. `GET /district/{district_id}`
Returns static metadata for a district.

**Request**
- Path param: `district_id` (string)

**Response — 200 OK**
```json
{
  "district_id": "MH-Pune",
  "state": "Maharashtra",
  "agro_climatic_zone": "Western Maharashtra Scarcity Zone",
  "data_coverage_pct": 87
}
```

**Errors**
- `404 Not Found` — district_id does not exist

---

## 3. `GET /history/{district_id}`
Returns historical GWL readings, used to render the Recharts timeline.

**Request**
- Path param: `district_id` (string)
- Query param (optional): `months` (integer) — limit range, e.g. `?months=24`

**Response — 200 OK**
```json
{
  "district_id": "MH-Pune",
  "history": [
    { "date": "2024-01-01", "gwl": 8.2 },
    { "date": "2024-02-01", "gwl": 8.5 }
  ]
}
```

**Errors**
- `404 Not Found` — district_id does not exist
- `400 Bad Request` — `months` is not a valid positive integer

---

## 4. `GET /alerts`
Returns all districts currently in Warning or Crisis tier.

**Request**
- Query param (optional): `tier` (string) — filter to one tier, e.g. `?tier=Crisis`

**Response — 200 OK**
```json
{
  "alerts": [
    { "district_id": "MH-Pune", "crisis_score": 84, "risk_tier": "Crisis" }
  ]
}
```

**Errors**
- `400 Bad Request` — `tier` is not one of Safe/Watch/Warning/Crisis

---

## 5. `POST /simulate`
Runs a policy "what-if" simulation and returns an adjusted Crisis Score.

**Request — JSON body**
```json
{
  "district_id": "MH-Pune",
  "rainfall_change_pct": -10,
  "extraction_change_pct": 5
}
```

**Response — 200 OK**
```json
{
  "district_id": "MH-Pune",
  "simulated_crisis_score": 71,
  "baseline_crisis_score": 62
}
```

**Errors**
- `400 Bad Request` — missing or invalid fields in body
- `404 Not Found` — district_id does not exist

---

## Risk tier reference (used across all endpoints)
| Tier | Score range |
|---|---|
| Safe | 0–30 |
| Watch | 31–60 |
| Warning | 61–80 |
| Crisis | 81–100 |
