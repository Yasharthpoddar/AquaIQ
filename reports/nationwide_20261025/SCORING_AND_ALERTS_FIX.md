# Local scoring, Alerts and national map — 2026-10-26

The screenshot correctly showed that no complete risk-scoring run matched the current model/data/code signature. District forecast coverage was already complete; the separate legacy six-month risk index had not been recomputed after the readiness repair. Generating display-only risk labels or treating twelve-month evidence tiers as risk tiers would have been incorrect.

Reused `models.score_all` to compute the existing risk index from genuine source evidence and the existing model. Added additive output-only migration 005 and `--test-schema` so the run can be published safely to the already configured local test namespace. `AQUAIQ_SCORING_SCHEMA` selects these outputs for `/scores` and `/alerts`, while source district/feature queries remain read-only in public. Private output tables have private sequences. Missing or invalid private configuration fails closed rather than writing to public tables. No model weights, observation data, risk formula or calibration was changed.

Completed local run **6c94defe-f5d4-5d2f-b6bb-a0d4e71365aa**, as of **2026-10-26**, in `aquaiq_test_nationwide_20261025`:

| Result | Districts |
|---|---:|
| Safe | 312 |
| Watch | 357 |
| Warning | 46 |
| Crisis | 6 |
| Risk index unavailable | 4 |
| Total | 725 |

The run contains 721 available historical forecasts/indices and four explicit unavailable results. These are project categories, not official advisories or crisis probabilities. Alerts retain source months, historical target dates, scoring dates and zone-estimate labels. The independent twelve-month generation remains unchanged at **0ee860ab-c064-55e1-a462-bc897b9c9b95**, with all 725 districts and 8,700 monthly values.

Public score tables were fingerprinted before and after computation and test verification. Row counts and ordered-content fingerprints were identical: public `scoring_runs` 6 rows, `crisis_scores` 2,175 rows, `predictions` 4,326 rows. Only the isolated test namespace received the new run. No normal API request performs scoring or nationwide inference.

Strengthened batch publication guards for complete district output, finite integral 0–100 scores, matching configured tiers, null/unavailable consistency and stable input identities. A computation failure or mid-transaction write failure preserves the previous complete snapshot. Migration and rollback tests use disposable test schemas.

The map previously used a fixed centre/zoom. It now fits all supplied district geometries, invalidates/resets bounds when its container size changes, and offers **Show all India** after panning. Risk colours now come from the real completed scoring snapshot; unavailable indices stay grey. There are 724 uniquely matched registered district identities, represented by 726 geometry paths because some districts have fragments. Mumbai Suburban retains its explicit registry/search link without an invented separate polygon.

Executed verification:

- Full non-integration suite: `python -B -m pytest -q --disable-warnings --basetemp=scratch/pytest-scored-complete`: **1,302 passed, 34 explicit integration skips**, 11 existing warnings.
- `python -B -m pytest -q tests/test_scoring_storage.py tests/test_scores_efficiency.py tests/test_api_audit_regressions.py tests/test_serving_integrity.py --basetemp=scratch/pytest-scoring-storage`: **53 passed, 2 integration skips**.
- `python -B -m pytest -q --integration tests/test_scoring_storage.py --basetemp=scratch/pytest-scoring-integration`: **13 passed**. Covers repeated migration, private sequences, source reads, strict namespace selection, invalid score rejection, API retrieval and injected SQL failure/rollback.
- `npm --prefix dashboard test`: **155 passed**; lint passed; production build passed with the existing large-chunk warning.
- `node dashboard/tests/scoredDashboardBrowser.cjs` using existing Playwright/Chrome against the running local app: **five browser flows passed**, zero page errors. Verifies real score counts, coloured district polygons, full-country bounds/reset at 1440/768/390 pixels, district navigation, all 725 Alerts results, all category filters and alert-to-forecast links.

Aggregate run metadata, tier consistency and public-table preservation are recorded in [the scoring snapshot](scoring_snapshot.json). [Browser results](scoring_browser.json) retain the inspected flow results and actual API tier counts.

Frontend and backend remain running on ports 5173 and 5000, with both forecast and scoring reads set to the local test namespace. Refresh Home or Alerts to load the completed snapshot. Reproducible startup commands are in [the current guide](../../docs/NATIONWIDE_FORECASTS.md).
