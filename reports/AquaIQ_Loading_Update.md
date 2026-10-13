# Loading performance update — 13 October 2026

The local dashboard's score response median fell from **5,727 ms to 421 ms** across three sequential samples before and after the change, about **93% less time**. These are local measurements of the `/api/scores` response, not a guarantee for complete page loading on other machines.

## Changes

- Configuration is parsed once per score response, rather than separately for all 725 districts. Alerts use the same formatter and benefit from the correction. Configuration changes still apply on each request.
- District detail makes three distinct requests: district/score, history, and future monthly projection. The district response already contains the historical model endpoint, so the duplicate prediction request is removed.
- Concurrent identical GETs share a pending request. React's development effects now produce three actual district requests instead of up to eight. Completed and failed requests leave no persistent response cache; later visits and retries obtain fresh data.
- The district heading and score render when their response arrives. History and future projection load independently, with separate failure and retry controls.
- Chart data renders immediately without the initial line animations. Tooltips remain interactive.

Historical score dates, future projection dates, unavailable evidence, model verification, and scoring formulas are preserved. No feature data, model checkpoint, risk weights, or scoring batch was changed.

## Verification

- Full Python suite including integration: **172 passed**.
- Frontend request sharing/freshness/error regression checks: **6 passed**.
- Dashboard lint and production build: passed.
- Live API still returned 725 districts, Gandhinagar score 87, and its six future projection points.
- Browser confirmed the district score and both charts. The API log showed one district request, one history request, and one monthly projection request for the browser load, without the duplicate historical prediction request.
- Frontend request tests are wired into `npm test` and the dashboard CI job. Remote CI has not been run.

Raw measurements: [loading_before.json](loading_before.json), [loading_after.json](loading_after.json), and [loading_comparison.json](loading_comparison.json). The first request after an API restart can take longer while model/fuzzy dependencies initialize; the change does not claim to eliminate cold startup cost. Existing JavaScript bundle size advisory remains.
