# AquaIQ API contract

The default dashboard reads persistent twelve-month district forecasts and equal-district state summaries. The [serving guide](docs/NATIONWIDE_FORECASTS.md) defines tiered methods, immutable generations, evidence fields and namespace operations. Historical research, the seasonal/trend scenario and legacy six-month risk products have separate contracts below. HTTP success, model loading and coverage do not establish forecasting accuracy.

## Published twelve-month products

`GET /api/districts` returns the canonical district registry independently of optional score publications. `GET /api/states` lists the state/UT registry. `GET /api/states/summary?horizon=12`, `GET /api/predict/state/<state_id>?horizon=12` and `GET /api/predict/climate-12m/<district_id>?months=12` read published generations. Optional `as_of=YYYY-MM-DD` selects that date exactly; omission selects the latest published vintage no later than today and retains its actual dates. Missing generations return HTTP 503 rather than triggering nationwide inference. Explicit dates/horizons are validated.

Each district returns twelve month-start absolute depths in `m_bgl`, with separate changes from estimated current depth, method/evidence tier, observation counts/dates, uncertainty availability and generation/model/data identities. Reference tiers never manufacture local observations or weather. States use equal weights across registered districts, with evidence proportions and constituent methods; this is neither area/well weighting nor groundwater volume. Source/history and risk evidence can have different dates from the published outlook.

## Historical direct twelve-calendar-month research

`GET /api/research/forecast` describes the historical research product, supported canonical district IDs, source-backed origin months, artifact scope and limitations. `GET /api/research/forecast/<district_id>` defaults to the **latest observed source month**; `origin_month=YYYY-MM` selects an explicit origin. The optional `months` parameter must equal `12`. Unknown, repeated or incompatible query parameters are rejected. This route is separate from the preserved legacy endpoint below and does not connect to the database.

The target is exactly **origin M + 12 calendar months**. The response includes `product: direct_12month_research`, `horizon_months: 12`, `units: m_bgl`, `origin_month`, `target_month`, nullable `ml_estimate_m`, one nullable `annual_baseline_m`, `status`, `output_kind`, `source`, `model`, `scope`, `unavailable_reasons` and `limitations`. `computed_at` is timezone-aware UTC and `forecast_issued_at` stays null: these are retrospective/current-vintage research calculations, not an archive of issued prospective forecasts. A source month is not a certified acquisition day.

The **annual baseline is persistence = standard annual seasonal naive** because target−12 is the observed origin. It is eligible only for a finite, explicitly observed origin; imputed/estimated origins cannot become measurements. Baseline eligibility is independent of ML availability and is not a second independent method. When historical labels are available, `observed_target_m` is shown separately; it is not a model input.

The new fixed-cutoff XGBoost artifact is restricted to the **TS-Adilabad metadata-agreement population**. All other districts return unsupported-scope unavailability; neither national registry coverage nor zone fallback expands this research scope. Before model loading, the adapter checks the research-only twelve-month contract, feature order/hash, physical units, source generation, geographic scope, configuration, manifest/card/model bytes and frozen input/provenance snapshots. A six-month checkpoint is never substituted.

ML calculation additionally requires an observed origin and historical observed target, the full embargo after the training cutoff, finite inputs with compatible provenance and permitted carry ages. The artifact is **historical-only**. Current/future targets, missing/stale inputs, imputed origins, absent/incompatible artifacts and unsupported scope return a null ML estimate with reasons. A historical request can use old source months as historical evidence; their age today is disclosed without relabelling them current. No silent backoff to an older complete origin is allowed.

For the retained source, a default Adilabad request has origin `2026-05`, target `2027-05`, and unavailable ML; an explicit `origin_month=2024-01` targets `2025-01` for historical research. `source` distinguishes latest observed month from selected origin, reported dates from unknown acquisition/availability times, observed versus imputed values and per-input carry/derived/missing status. Scope agreement does not certify geographic truth, a stable physical well panel or datum continuity. No twelve-full-month operational lead or prospective skill is claimed.

Previously inspected historical checks did not establish robust model superiority; the annual baseline performed better on the fixed application artifact's checks. Historical study metrics cannot validate the current/future application. Artifact failures return HTTP 503 with null estimates and public-safe research reasons; invalid queries return HTTP 400. No risk-index or extraction-simulation recalibration follows from this integration.

### Historical graph mode: twelve calendar positions

`GET /api/research/graph/<district_id>?months=12[&origin_month=YYYY-MM]` adapts the validated direct research endpoint for the existing chart. Its twelve rows use exact calendar months M+1 through M+12, with `horizon_months` 1–12. The retained artifact supports only M+12: rows 1–11 have explicit null `predicted_gwl` and `annual_baseline_m` values and unavailable reasons. Row 12 retains the direct endpoint's ML and annual reference where eligible. No interpolation, six-month fallback or repeated annual baseline supplies a monthly trajectory. Unknown origins have null month labels rather than invented dates. The response retains origin/target, units, model/source identity, scope, limitations and `forecast_issued_at=null`. Existing `/api/predict` six-month behavior and monthly horizons 1–6 are unchanged.

## Secondary and legacy products

This API serves an academic research prototype. HTTP success or model loading does not establish predictive skill, nationwide accuracy or validated real-time forecasting. The 0–100 score is a project-defined, uncalibrated risk index, not a probability; its tiers are not official groundwater classifications. Simulation is sensitivity analysis, including a heuristic extraction adjustment, not a proven causal estimate.

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

`estimate_type` is `district_level`, `zone_fallback`, or `insufficient_data`. Zone estimates name `source_zone` and carry `zone_fallback_reason`. The fallback aggregates source-marked district observations from that zone; the resulting estimate is not a district measurement.

## Legacy `GET /api/predict/<district_id>`

Selects one of two distinct prediction windows. The default preserves the **six-calendar-month XGBoost endpoint** and score based on the last source-marked groundwater month admitted by the calendar cutoff. `window=next_six_months` returns **monthly XGBoost projections for six consecutive month buckets beginning next month**, using rainfall and weather assumptions. This window is not a guarantee of six full months of acquisition lead from issuance.

| Query parameter | Accepted value |
| --- | --- |
| `months` | Omitted or exactly `6` |
| `as_of` | Omitted, `today`, `last_observed`, or an ISO `YYYY-MM-DD` date no later than today |
| `window` | Omitted, `observed_endpoint`, or `next_six_months` |

The aliases `today` and `last_observed` both apply today's calendar cutoff. With the default `observed_endpoint` window, the model forecast still originates at the latest source-marked observation month. With `next_six_months`, the projection window starts after today's month. Invalid windows and `target_year`, `year`, `start`, and `start_month` return 400.

Monthly feature dates label the first day of a month, not a certified acquisition day. The calendar-cutoff heuristic admits a month on its last calendar day: `as_of=2021-01-15` can use December 2020 and earlier, while `as_of=2021-01-31` can use January 2021. It does not verify intraday completion, provider publication, receipt or revision availability. Nominal origin+6 bucket spacing is not proof of six full months from actual issuance to target acquisition.

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

The method fits a statistical seasonal/trend projection to source-marked groundwater history to estimate the level at the cutoff. It requires at least 24 source-marked monthly observations spanning 36 months and uses annual seasonality only when observation coverage supports it. The trend damps over the entire unobserved gap. One shared monthly XGBoost model predicts changes at exact one-through-six-month horizons from that estimated baseline, using the horizon and monthly rainfall, temperature, and evapotranspiration assumptions. This method does not relabel the historical six-month XGBoost endpoint as a present-day forecast.

The response has `status: projection`, `projection_method: climate_conditioned_xgboost_monthly`, `estimated_current_gwl`, `last_observed_date`, `data_age_months`, `forecast_start`, `forecast_end`, `units: m_bgl`, and six `forecast` entries containing `month`, `date`, and `predicted_gwl`. Each entry also contains `weather` with finite `rainfall_mm`, `temperature_c`, and `evapotranspiration_mm` inputs. Rainfall and evapotranspiration are monthly totals. `weather_basis.method` is `historical_monthly_climatology`; `weather_basis.last_observed_weather_date` and the history range report the available weather evidence. The monthly assumptions use up to ten recent usable same-calendar-month reference years per weather field, with at least three prior years required. They are assumed future conditions, not live weather forecasts. `fit_details` describes the historical groundwater fit used to estimate the present baseline. `validation` and `limitations` report evaluation limits; current-period accuracy remains unvalidated. Missing usable district/zone groundwater or weather evidence produces `insufficient_data` with an empty forecast.

Old observations remain old in `last_observed_date` and `data_age_months`, even when the graph contains future months. The projected current level and future months are estimates, not new measurements. Rainfall and weather affect the monthly XGBoost projections through the disclosed historical-average assumptions; measured future pumping is excluded. These projections have not established present-day forecast accuracy and do not replace the existing uncalibrated project risk index or simulation baseline.

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

Checks a real PostgreSQL query and validates the historical, monthly climate and twelve-month serving bundles, including their checksums, feature schemas, units, supported horizons, and matching feature generation. Returns `status`, `database`, `model_loaded`, `monthly_climate_model_loaded`, `climate_12m_model_loaded`, and project `version`.

- HTTP 200: `status: healthy`, `database: connected`, `model_loaded: true`, `monthly_climate_model_loaded: true`.
- HTTP 503: `status: degraded`; the other fields identify failed readiness.

File existence alone does not establish model health. Health does not claim that the historical dataset supports a present-day forecast.

## `GET /api/research/scenario/<district_id>?months=12[&as_of=YYYY-MM-DD]`

Separate experimental scenario approved for local demonstration; defaults to today's **Asia/Kolkata** calendar date. All 725 canonical district IDs are accepted. `TS-Adilabad` retains its frozen research source; other districts use their own observed-marked history from the pinned national feature export and canonical crosswalk in `research/experimental_scenario_sources.json`. The `experimental_12month_scenario` product returns `status: scenario` with twelve next full calendar months and `projected_gwl` in metres below ground, or `status: unavailable` with no values and explicit reasons. Current history requirements support 548 districts; 177 abstain. Invalid/future dates, duplicate parameters and horizons other than 12 return 400; incompatible/revised source bytes return 503 until separately reviewed and versioned. Unknown IDs and insufficient/no-history districts abstain with HTTP 200 and never use another district's or zone's evidence. No aliases are guessed or resolved through the DB.

The calculation reuses the existing robust damped seasonal/trend fit in memory from explicitly source-marked observed history strictly before the scenario month. It loads no estimator, trains no active ML, accesses no DB and saves no parameters or prediction ledger. It estimates the observation gap, omits weather and extraction effects, and is unvalidated. Responses separate `as_of`, timezone-aware `computed_at`, null `forecast_issued_at`, last observed depth/date, estimated scenario-month depth, age, fit history/phase coverage, source/method/configuration hashes, assumptions and limitations. Availability remains unverified. Past `as_of` requests use the retained current source vintage and are not causal historical backtests. Existing `/research/forecast`, `/research/graph` and six-month endpoints retain their contracts.

National source units follow the repository's `m_bgl` convention; certified per-well datum/continuity are unknown. National well counts, panels, acquisition and availability timestamps are absent and remain null. `source.scope` is `district_own_observed_history`, with source-specific `name`, `units_qualification`, district metadata, generation and byte hashes. Observation age and sparse phase coverage do not establish current forecasting skill. Cached parsing never skips verifying the pinned bytes on a subsequent request.


The retained robust scenario requires at least 24 source-marked observations spanning 36 months. Where enough recent data exist it uses a 120-month window; otherwise full history, with 60-month age half-life, four robust fitting iterations, a penalized linear/annual-seasonal fit, recent-residual adjustment and 36-month trend damping. It estimates the gap from the last observation and evaluates each future month directly; depths are floored at zero. Calendar phases without observations are inferred from assumptions, not measurements. Weather, pumping, extraction and policy interventions are excluded. The method is an in-memory NumPy fit, not an extrapolated six-month estimator or interpolated M+12 point. Sparse sampling, old anchors and uncertain panel continuity limit credibility.

The explicit UI scenario view uses `/district/<district_id>?view=scenario#forecast-graph`; historical `origin_month` links retain their research scope. Scenario and historical risk are independent products. Future labels, verified source availability and stable well/datum evidence plus preregistered baseline comparisons would be necessary to establish skill. No scenario result is recorded as prospective issuance or promoted to an active model.
