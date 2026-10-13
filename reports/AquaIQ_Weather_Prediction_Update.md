# AquaIQ rainfall and weather prediction update

Completed locally on 13 October 2026 in `C:\Users\Yasharth\Downloads\AquaIQ`.

The next-six-month graph now uses a monthly XGBoost model that takes rainfall, temperature and evapotranspiration into account. Previously, that graph used only historical groundwater seasonality and trend. The historical crisis score still describes its original observation period; it is separate from this current outlook.

## What changed

- One shared model predicts groundwater depth changes for horizons of one through six calendar months. It uses the forecast horizon, groundwater depth and lags, calendar seasonality, origin weather, target-month weather, cumulative rainfall and evapotranspiration, and mean temperature.
- Old groundwater readings still need a current depth estimate. Historical seasonality and trend provide that estimate; XGBoost then predicts future changes conditional on the weather inputs.
- The API returns six consecutive months after the current month, with the rainfall, temperature and evapotranspiration used for each point. On 13 October 2026, the window is November 2026 through April 2027.
- The district page shows these inputs in a six-row table, explains depth below ground, and labels the age of the groundwater evidence and the weather assumptions.
- The pipeline's training stage trains both the existing historical model and this new monthly model. Health checks verify both model bundles, including the new model's checksum, feature schema, units and data generation.
- Missing groundwater or weather evidence produces an explicit insufficient-data response. It does not substitute zero weather or draw a fabricated prediction.

Implementation: [monthly model](../models/climate_forecast.py), [weather inputs](../models/climate_inputs.py), [district page](../dashboard/src/pages/DistrictDetail.jsx).

## Weather assumptions and data limits

Future rainfall, temperature and evapotranspiration are historical averages for the corresponding calendar month, using up to ten recent usable reference years per field and requiring at least three. Only completed months available at the forecast origin are eligible. The weather history in the current project extends through December 2024. These inputs are assumed future conditions, not live meteorological forecasts.

Weather records may include the feature pipeline's limited causal fills where separate field-level provenance is unavailable. Groundwater observation flags are not treated as weather observation flags. Explicitly flagged weather fills are excluded from the reference averages.

Pumping and extraction are not included. Current groundwater depth is estimated across a long gap for many districts; for example, Gandhinagar and Krishna use actual groundwater observations through January 2021. New weather inputs do not validate that estimated current depth or remove the need for fresh measurements. Some districts use clearly labelled zone evidence when district observations are insufficient.

## Training and evaluation

Training used the verified feature dataset and 60,974 pairs with observed groundwater at both the origin and target. Training target dates end in December 2019. The evaluation starts from July 2020 origins, with a six-month embargo.

Historical realized weather is used to learn the conditional relationship during training. Evaluation reconstructs weather assumptions using only history available at each held-out origin. A review that replaced weather strictly after a held-out origin with extreme values left its evaluation inputs and predictions unchanged.

Across 1,936 held-out labels in 510 districts, the model's RMSE was **2.456 m**, compared with **2.770 m** for persistence. On the 1,893 labels shared with the seasonal baseline, XGBoost's RMSE was **2.473 m** versus **2.398 m** for the seasonal baseline. The seasonal baseline performed better on that comparison. The new model also performed worse than persistence at horizons one, four and six, whose evaluation coverage was limited to nine or ten districts. These results do not establish current-period or nationwide accuracy, especially when the forecast origin itself is estimated across years without measurements. R-squared is not an accuracy percentage.

Weather sensitivity was checked by comparing predicted depths rather than response metadata. For Krishna, increasing future rainfall by 50% changed the six depth predictions by approximately -0.02 to -0.05 m. Increasing temperature by 3 degrees Celsius and evapotranspiration by 20% changed depths by approximately +0.06 to +0.68 m. This confirms the inputs affect model output; it does not establish a causal response or guarantee every small weather change crosses an XGBoost decision threshold.

Details: [evaluation/model card](climate_forecast_evaluation.json), [independent review and scenario checks](climate_forecast_review.json).

## Verification

- **237 Python checks passed**, including integration checks and the new weather/model coverage.
- **6 frontend checks passed**; frontend lint and production build passed.
- The training-stage dry run and dispatch checks passed.
- A live read-only audit checked **all 725 districts**: 720 returned six-month projections; five reported insufficient data; there were no forecast errors.
- Local API checks confirmed healthy database and both verified models, 725 scores, preserved Gandhinagar historical score of 87, and valid climate-conditioned forecasts for sampled districts.
- The browser displayed Gandhinagar's six future months, the graph, weather table and limitations. Existing progressive loading and request deduplication remain in place.

Evidence: [live verification](climate_forecast_live_verification.json), [verified browser view](weather_prediction_graph.jpg).

The trained monthly model is saved locally. As with the existing historical checkpoint, model manifests and bundles are excluded from Git; run `python scripts/run_pipeline.py --step train` after preparing the production feature dataset to rebuild both models on another machine. This report records local verification; deployment was not performed.
