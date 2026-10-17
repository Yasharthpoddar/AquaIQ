# AquaIQ API contract

All routes below use the `/api` prefix. Values are physical: groundwater depth is metres below ground level, rainfall and evapotranspiration are millimetres per month, and temperature is degrees Celsius. Responses use strict JSON: missing and non-finite numeric values are `null`, never `NaN` or an invented fallback score.

District path identifiers resolve to the canonical district master or a recorded legacy crosswalk. The response's canonical `district_id` may differ from a legacy identifier supplied by the caller. Similar district names in different states do not share data.

## Errors and evidence statuses

| HTTP code | `status` | Meaning |
| --- | --- | --- |
| 200 | Route-specific | The request succeeded, including an explicit missing-evidence result |
| 400 | `invalid_request` | Invalid dates, horizons, ranges, or simulation inputs |
| 404 | `not_found` | District identity is unknown or ambiguous |
| 503 | `unavailable` | PostgreSQL or the verified model/data service failed |

Error responses contain `status` and `error`. A service failure does not become a score of 50, 0, or Watch. The health route has its own degraded response described below.

Forecast and district responses distinguish `success`, `historical_forecast`, `projection`, `insufficient_data`, and `unavailable`. These are evidence statuses, separate from the risk tier. A `historical_forecast` means the target month precedes the requested cutoff. A `projection` is the monthly climate-conditioned estimate described below, including an estimated present level when observations are old. `insufficient_data` returns an empty `forecast`; risk responses also return `crisis_score: null` and `tier: null`. A causally incompatible model/origin may return `unavailable` with an explanatory `message` and empty forecast.

`estimate_type` is `district_level`, `zone_fallback`, or `insufficient_data`. Zone estimates name `source_zone` and carry `zone_fallback_reason`. The fallback uses actual observations aggregated from that zone.

## `GET /api/predict/<district_id>`

Selects one of two distinct prediction windows. The default preserves the **six-calendar-month XGBoost endpoint** and score based on the last observed groundwater month available through the cutoff. `window=next_six_months` returns a **monthly XGBoost projection with rainfall and weather inputs for the six full calendar months after the cutoff**, for the dashboard's future prediction graph.

| Query parameter | Accepted value |
| --- | --- |
| `months` | Omitted or exactly `6` |
| `as_of` | Omitted, `today`, `last_observed`, or an ISO `YYYY-MM-DD` date no later than today |
| `window` | Omitted, `observed_endpoint`, or `next_six_months` |

The aliases `today` and `last_observed` both select evidence available through today. With the default `observed_endpoint` window, the model forecast still originates at the latest true observation. With `next_six_months`, the projection window starts after today's month. Invalid windows and `target_year`, `year`, `start`, and `start_month` return 400.

Monthly feature dates label the first day of their observation month. A monthly aggregate is eligible only after that month ends: `as_of=2021-01-15` can use December 2020 and earlier, while `as_of=2021-01-31` can use January 2021. Source publication delays are not recorded, so these are calendar availability checks on retrospective data.

The following illustrates the default endpoint's response shape; its example score and depth are not measured project results:

```json
{
  "district_id": "MH-Pune",
  "requested_id": "MH-Pune",
  "resolved_id": "MH-Pune",
  "status": "historical_forecast",
  "as_of": "2026-10-13",
  "forecast_origin": "2023-03-01",
  "last_observed_date": "2023-03-01",
  "feature_cutoff": "2023-03-01",
  "forecast_start": "2023-09",
  "horizon_months": 6,
  "forecast_horizon": "6-month ahead endpoint",
  "projection_method": "direct_xgboost_6_month_endpoint",
  "forecast": [{"month": "2023-09", "predicted_gwl": 8.2}],
  "crisis_score": 42,
  "tier": "Watch",
  "estimate_type": "district_level",
  "source_zone": null,
  "zone_fallback_reason": null,
  "data_age_months": 43,
  "model_version": "3.0-calendar-observed"
}
```

Additional fields include `feature_generation`, `model_sha256`, `model_validation`, component scores, effective ensemble weights, `weights_status`, and `data_readiness`. Forward-filled feature months do not advance `last_observed_date`. An old observation plus six months can remain a historical endpoint even when `as_of` is today.

### Future monthly projection window

`GET /api/predict/GJ-Gandhinagar?window=next_six_months&as_of=today` selects the future graph. With a cutoff of `2026-10-13`, `forecast` contains monthly estimates for `2026-11`, `2026-12`, `2027-01`, `2027-02`, `2027-03`, and `2027-04`. A historical cutoff projects the next six months relative to that cutoff and only uses observations eligible then.

The method fits a statistical seasonal/trend projection to observed groundwater history to estimate the level at the cutoff. It requires at least 24 actual observations spanning 36 months and uses annual seasonality only when observation coverage supports it. The trend damps over the entire unobserved gap. One shared monthly XGBoost model predicts changes at exact one-through-six-month horizons from that estimated baseline, using the horizon and monthly rainfall, temperature, and evapotranspiration assumptions. This method does not relabel the historical six-month XGBoost endpoint as a present-day forecast.

The response has `status: projection`, `projection_method: climate_conditioned_xgboost_monthly`, `estimated_current_gwl`, `last_observed_date`, `data_age_months`, `forecast_start`, `forecast_end`, `units: m_bgl`, and six `forecast` entries containing `month`, `date`, and `predicted_gwl`. Each entry also contains `weather` with finite `rainfall_mm`, `temperature_c`, and `evapotranspiration_mm` inputs. Rainfall and evapotranspiration are monthly totals. `weather_basis.method` is `historical_monthly_climatology`; `weather_basis.last_observed_weather_date` and the history range report the available weather evidence. The monthly assumptions use up to ten recent usable same-calendar-month reference years per weather field, with at least three prior years required. They are assumed future conditions, not live weather forecasts. `fit_details` describes the historical groundwater fit used to estimate the present baseline. `validation` and `limitations` report evaluation limits; current-period accuracy remains unvalidated. Missing usable district/zone groundwater or weather evidence produces `insufficient_data` with an empty forecast.

Old observations remain old in `last_observed_date` and `data_age_months`, even when the graph contains future months. The projected current level and future months are estimates, not new measurements. Rainfall and weather affect the monthly XGBoost projections through the disclosed historical-average assumptions; measured future pumping is excluded. These projections have not established present-day forecast accuracy and do not replace the existing evidence-based crisis score or simulation baseline.

## `GET /api/district/<district_id>`

Accepts the same `as_of` cutoff as `/predict`. Returns the same scoring and evidence fields plus `metadata` from the district master, `resolved_id`, and `ensemble_components` (an alias of `components`). Metadata includes the district name, state, agro-climatic zone, and GeoJSON name where available. Component values may be null; blending uses only available components and reports the effective weights.

`data_readiness` reports observed monitoring-round coverage using the configured observation interval, counts, eligibility, and zone readiness where relevant. It does not treat imputed months as observations.

## `GET /api/history/<district_id>`

Returns physical feature history for the current generation, including observed/imputed provenance.

| Query parameter | Meaning |
| --- | --- |
| `start` | `YYYY-MM` or `YYYY-MM-DD`; defaults to `2002-01` |
| `end` | `YYYY-MM` or `YYYY-MM-DD`; defaults to the current month |
| `months` | Optional integer from 1 to 1200; retains the final N rows of the selected range |

`start` must precede or equal `end`. A `YYYY-MM` cutoff selects the first day of that month. Results are sorted by month. The response contains canonical `district_id`, `requested_id`, `start`, `end`, and equal `data`/`history` arrays. Each row has:

```json
{
  "month": "2023-04",
  "date": "2023-04",
  "gwl": 8.2,
  "rainfall": 12.4,
  "is_observed": false,
  "is_imputed": true,
  "months_since_observation": 1,
  "feature_generation": "physical-v3-causal-monthly-example"
}
```

Values and dates in this example illustrate the shape. Missing history is an empty array; missing groundwater within the monthly grid is `gwl: null`.

## `GET /api/config`

Returns project name and version, tier definitions and colors, feature names, and the configured ensemble weights. Score responses separately expose `weights_status`; current initial weights are uncalibrated. Risk tiers are project-defined bands, not official groundwater classifications.

| Tier | Rounded score range |
| --- | --- |
| Safe | 0–30 |
| Watch | 31–60 |
| Warning | 61–80 |
| Crisis | 81–100 |

## `GET /api/scores`

Returns `total`, `districts`, `tier_counts`, `estimate_counts`, and `status`. Records come from one completed scoring run that matches the current feature generation and verified model checksum/version. The route does not combine rows from partial or mismatched runs.

District records include `district_id`, `name`, `state`, `score`, `tier`, `estimate_type`, `zone_fallback_reason`, `top_factors`, `forecast_date`, `last_observed_date`, `model_version`, `feature_generation`, and `run_id`. In persisted score records, `forecast_date` is the batch's as-of scoring date; the actual six-month target is exposed by `/predict`.

Unavailable scores and tiers are null; `tier_counts.Unknown` counts null scores. Until a matching complete run is published, `districts` is empty and `status` is `awaiting_complete_scoring_run`.

## `GET /api/alerts`

Reads the same completed run as `/scores`, orders available scores descending, then unavailable evidence, and returns `alerts`, `count`, `total`, `has_more`, and `status`. `total` is the number of districts matching the tier before the limit; `has_more` explicitly reports truncation. The dashboard requests up to 1000 rows so the current 725-district master remains visible.

| Query parameter | Meaning |
| --- | --- |
| `tier` | Case-insensitive `All`, `Safe`, `Watch`, `Warning`, or `Crisis`; defaults to `All` |
| `limit` | Integer from 1 to 1000; defaults to 100 |

The default includes all tiers and unavailable districts; use `tier` for a specific band. Each row carries the score-record fields plus `crisis_score`/`risk_tier` aliases and a recommendation to review historical evidence. Empty publication state uses `awaiting_complete_scoring_run`.

## `POST /api/simulate`

Accepts a JSON object with required non-empty string `district_id`, optional `rainfall_change_pct` and `extraction_change_pct` (both default to 0), and optional `as_of` date (`YYYY-MM-DD`, `today`, or `last_observed`). Percentage changes must be finite JSON numbers in [-100, 100]; booleans and numeric strings are invalid. Invalid dates, JSON objects, or numeric inputs return 400 before district lookup.

```json
{
  "district_id": "MH-Pune",
  "rainfall_change_pct": -10,
  "extraction_change_pct": 5,
  "as_of": "2023-03-31"
}
```

The response contains `baseline_score`/`baseline_crisis_score`, `baseline_tier`, `simulated_score`/`simulated_crisis_score`, `simulated_tier`, `delta`, evidence `status`, `estimate_type`, `zone_fallback_reason`, `last_observed_date`, `extraction_heuristic_applied`, and `simulation_details`.

Rainfall sensitivity changes the same origin's rainfall, rainfall average, anomaly, and water-balance features, then uses the same verified model and scoring components. Extraction adds the configured project heuristic; `simulation_details.extraction_method` explicitly identifies it as a sensitivity heuristic rather than a learned causal effect. `simulation_details.xgb_inference_used` reports whether a changed scenario was inferred.

Zero-change inputs preserve the exact available baseline. If the baseline is unavailable, both scores, both tiers, and the delta remain null. The route does not invent a valid baseline to compute a scenario.

## `GET /api/health`

Checks a real PostgreSQL query and validates both the historical endpoint and monthly climate serving bundles, including their checksums, feature schemas, units, supported horizons, and matching feature generation. Returns `status`, `database`, `model_loaded`, `monthly_climate_model_loaded`, and project `version`.

- HTTP 200: `status: healthy`, `database: connected`, `model_loaded: true`, `monthly_climate_model_loaded: true`.
- HTTP 503: `status: degraded`; the other fields identify failed readiness.

File existence alone does not establish model health. Health does not claim that the historical dataset supports a present-day forecast.
