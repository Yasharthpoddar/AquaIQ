# Future monthly prediction graph — 13 October 2026

**Later update:** the seasonal-only future graph described in this report has been superseded by a monthly XGBoost model using rainfall, temperature, and evapotranspiration assumptions. The seasonal fit now estimates the current groundwater baseline. See [AquaIQ_Weather_Prediction_Update.md](AquaIQ_Weather_Prediction_Update.md) for the current implementation and verification. The results below document the earlier implementation.

The district prediction graph now shows the next six full calendar months after today's month. On 13 October 2026, the plotted months are November 2026 through April 2027. This window moves automatically with the API's current date.

## Behavior

- The graph requests `/api/predict/<district_id>?window=next_six_months`.
- A separate statistical regression fits actual groundwater observations. It learns an annual seasonal cycle where coverage supports one, weights recent history, and damps the trend across the entire unobserved gap before projecting the future months.
- The source observation date stays unchanged. The estimated current depth is explicitly an estimate. Quarterly measurements do not become invented monthly training observations.
- The new graph is separate from the recorded history and historical XGBoost endpoint. Existing crisis scores and simulation baselines retain their evidence and model identities.
- Missing district and zone evidence returns an empty graph with a reason. Unsupported/stale API responses cannot be displayed under the future graph's title.
- Forecast units are metres below ground level. Values are finite and nonnegative; real groundwater depths above 100 metres remain valid.

## Verification

- Complete test suite: **169 passed**, including integration tests.
- Dashboard lint and production build: passed.
- Read-only checks across **725 districts**: **721 six-month projections**, four explicitly unavailable, zero errors. Sources comprise 427 district estimates and 294 labelled zone estimates.
- Live API checks covered Gandhinagar, Jaipur, Mumbai Suburban, and a zone fallback, plus invalid horizons, unknown districts, and unsupported cutoffs.
- Browser verification confirmed all six future dates and the estimated/source distinction on Gandhinagar. Screenshot: `monthly_prediction_graph.jpg`.
- Default historical XGBoost prediction for Gandhinagar remains the July 2021 endpoint from the January 2021 observation; it is not relabelled as a current forecast.

Details are in [monthly_projection_live_verification.json](monthly_projection_live_verification.json). Historical evaluation is reproducible with `python -m scripts.evaluate_monthly_projection`, which writes [monthly_projection_evaluation.json](monthly_projection_evaluation.json) without changing production features, scores, or checkpoints.

## Evidence limits

The historical evaluation recreated 7,421 fits at 16 completed calendar cutoffs. Short one-to-six-month targets included 11,769 observed values; aggregate RMSE was 2.428 m versus 3.201 m for persistence. Long-gap comparisons are mixed: at the 69-month requested horizon, projection RMSE was 3.769 m versus 3.677 m for persistence. Quarterly observation coverage leaves some individual monthly horizons sparsely tested.

Historical comparisons do not establish accuracy for today's conditions. Most district observations end in January 2021, and the latest observations in the supplied data are from March 2023. The method estimates the missing years and excludes unknown future rainfall, extraction, and weather. The API and graph therefore label the output as a statistical projection; operational readiness remains false. Fresh measurements are required to validate a current outlook.
