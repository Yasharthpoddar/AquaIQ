> Historical XGBoost-only product notes. The default serving product is now the [complete tiered generation](NATIONWIDE_FORECASTS.md). The old 50% state panel rule, XGBoost-only labels, default-as-of behavior and quoted performance below do not describe the current product. Timing figures are earlier local measurements, not current guarantees. The legacy direct inference utilities remain available for comparison.

# State XGBoost outlook: method and contracts

This experimental product uses the existing twelve-month district XGBoost bundle. It trains no new state model. The previous harmonic state projection and its historical report must not be described as XGBoost evaluation evidence.

## Inputs and aggregation

1. Resolve the state through `models/state_mapping.py`; enumerate registered canonical district IDs from `data_ingestion/district_crosswalk.csv`. Join the local state boundaries by `state_id`, never by a similar name.
2. Verify the feature CSV and manifest using the existing feature loader. Reject duplicate district/month keys. Restrict all district inputs to completed months at the requested `as_of` date. This calendar convention does **not** verify provider publication or acquisition times.
3. Require existing individual-district readiness and sufficient groundwater/weather inputs. Use only unambiguous observed history for the current-depth anchor. District zone fallback evidence never enters a state panel.
4. Call the existing `climate_forecast_12m.forecast_from_evidence` for each eligible district. Future weather is origin-limited historical climatology; current depths and lags may be estimated across gaps by the existing district implementation. There is no alternate forecast when XGBoost fails.
5. Keep the eligible district panel fixed for all twelve horizons. Require at least 50% of registered districts and at least two contributors (one for a single-district state). These are coverage safeguards, not statistically validated representativeness thresholds. Average their returned XGBoost depths with equal weights; retain panel IDs, exclusions and coverage. Do not substitute one arbitrary district for a multi-district state.
6. Label the output as a **covered-district mean depth in m bgl**. It is neither a well-weighted nor an area-weighted state estimate, and does not measure groundwater volume. Historical observed means use that month's reporting districts and may have different composition. Missing months remain gaps.

## API and rendering

- `/api/states` retains the canonical 36-state/territory registry.
- `/api/states/summary?horizon=12` returns counts and the last XGBoost horizon. Missing state predictions remain null.
- `/api/predict/state/TN?horizon=12&as_of=2026-10-25` returns November 2026–October 2027. Omitting `as_of` uses today, not an old observation month. Other horizons are rejected; district six-month APIs are unchanged.
- Successful state responses use `model_version=2.0-state-district-xgboost`, `model_name=district_xgboost_equal_weight`, exact target dates, UTC `computed_at`, model hash, feature generation, fixed panel and separately labelled observed history.
- State and district 12-month predictions are precomputed ahead-of-time and served from persistent PostgreSQL storage (migration 004: `forecast_generations`, `district_forecast_records`, `state_forecast_records`, `nationwide_summary_records`) with process-local L1 caching. Caller mutation cannot alter cached values. Normal API reads never trigger synchronous model inference. If precomputation has not been run, endpoints return HTTP 503 `model_unavailable` with actionable diagnostics.

## Historical evaluation and release limits

`python -m scripts.evaluate_state_xgboost --output reports/<new-unused-directory>` evaluates the frozen existing model with Jan/May/Aug/Nov origins in 2021–2025. Training labels stop at 2019-12-31; 2020 is embargoed. The output path must not exist. It records panel membership, exact case joins, exclusions and matched comparisons with observed persistence and annual seasonal naive. A target is eligible only if every district in the origin-selected panel has an exact source-marked observation at the target month. No target-driven panel shrinking, imputation, training, tuning or selection is allowed.

This diagnostic reuses previously inspected historical data. It is not a new untouched test, independent state survey or prospective campaign. Monthly source flags, unknown well composition and old weather coverage constrain interpretation. Forecast availability does not establish accuracy; the UI preference for XGBoost does not change prior comparisons favoring baselines. HGB stays abstained. Current source observations, availability timestamps and stable well panels are still required before any operational or prospective-skill claim.

## Runtime and checks

The existing tracked `models/artifacts/aquaiq_climate_12m.json` pointer and referenced bundle are used unchanged. The feature CSV and matching manifest remain external deployment prerequisites; a code-only clone cannot generate these state outputs. The existing Docker image includes `models/artifacts/` and mounts data read-only. Forecast precomputation is executed ahead-of-time via `python -m scripts.precompute_forecasts --horizon 12`. Stored forecasts are served in ~12ms for nationwide summaries and ~25ms for states. Normal API startup does not run model inference.

Run `python -m pytest`, `npm --prefix dashboard test`, `npm --prefix dashboard run lint`, and `npm --prefix dashboard run build`. Database integration tests remain opt-in against an isolated test database. Optional browser regression: build with `npm --prefix dashboard run build -- --outDir ../scratch/xgb-states-build`, then run `node dashboard/tests/stateBrowser.cjs` with an existing Playwright installation resolvable through `NODE_PATH` and, if needed, `PLAYWRIGHT_CHROMIUM_EXECUTABLE` pointing to an existing Chromium binary. This browser harness uses labelled synthetic API fixtures, blocks external requests and saves screenshots under `scratch/`; it does not access the application database or establish model accuracy.
