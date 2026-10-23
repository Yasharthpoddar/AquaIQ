# AquaIQ pushed twelve-month version: end-to-end verification

Audit started **22 October 2026**, completed **23 October 2026** (India calendar). This is an audit of retained source, assets, historical predictions and local serving, not a new experiment or release. No source fixes, training/tuning, model selection/promotion, ingestion, migrations, rainfall staging, shadow issuance, commit, push or deployment were performed.

**Result: PARTIAL for a locally provisioned academic demonstration; not production-ready.** The normal API serves the three distinct forecast products and the saved arithmetic reproduces. Fresh visual/browser verification is incomplete. GitHub alone omits required runtime assets, the default container omits the frozen research bundle, and source geography/availability prevent prospective-skill claims. A preservation exception also remains: one pre-existing built HTML file changed during the interrupted audit interval; ten new untracked files appeared outside this audit directory. They were preserved, not repaired or removed.

## Verified version and scope

| Reference | Exact SHA after successful fetch and `ls-remote`, 23 October |
|---|---|
| Remote `main` | `090626df28ad6414b355e2b1a4e24a4163693de5` |
| Remote `experiment/12-month-horizon` | `090626df28ad6414b355e2b1a4e24a4163693de5` |
| Local `main` / HEAD | `090626df28ad6414b355e2b1a4e24a4163693de5` |

This is the commit titled `feat: add twelve-month graph and experimental scenario for 725 districts`. Its predecessor `3a4936b` introduced the primary twelve-month research flow; `98c7056` is the preceding academic/six-month UI reference. Both pushed branches contain the final changes. The tracked working tree and index were empty at the beginning and end. Fifty audited serving/frontend source files match HEAD after accounting for CRLF checkout bytes. Existing untracked/private/ignored research assets were inventoried and retained; a clean tracked tree does not mean these assets are published.

The latest all-district, twelve-month finalization/backtest, scientific-validation, safe-fixes, provenance/issuance and preservation-incident reports were read. Current source and fetched SHA take precedence over older descriptions. Evidence: [remote receipt](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/remote_verification_20261023.json), [source/assets audit](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/api_source/API_SOURCE.md), [initial inventory](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/before.json).

## Application and graph contracts

These products are distinct. The district-page default is the monthly scenario, while API root/config metadata still calls direct M+12 research the primary product. That naming inconsistency is confirmed; it was not changed.

| Product | Calculation and verified dates | Qualification |
|---|---|---|
| Historical direct M+12 | Fixed Adilabad XGBoost; origin January 2024 → target January 2025. Twelve calendar slots, M+1…M+11 null, only M+12 has ML/baseline. | One endpoint, not twelve monthly ML predictions. Exact fixed artifact, historical only. |
| Experimental monthly scenario, default district view | Separate own-district seasonal/trend calculation. On 23 October 2026, twelve explicit values cover November 2026–October 2027. | Unvalidated assumption-based path, including estimated present depth across an observation gap. No weather/extraction inputs or prospective skill. |
| Legacy default prediction and climate projection | Default `/api/predict` is one M+6 endpoint from its observed origin; `window=next_six_months` is a separate six-point climate-conditioned XGBoost product. | Neither supplies the historical M+12 graph or the default twelve-month scenario. Risk scores retain these legacy components. |

The direct January example returned **7.571100711822510 m** ML, **6.836666666666668 m** annual baseline and **6.831333333333332 m** separately labelled observed target. These match the exact retained fixed-artifact row. Baseline is the source-backed origin observation. The estimator receives only ordered feature columns; the target is not an input. Source, API and graph tests confirm eleven null intermediate ML/baseline slots, retained M+12 value, explicit unsupported-horizon reasons and no six-month/other-district fallback. The chart component uses the returned series; no synthetic intermediate ML values are inserted. Actual browser rendering remains unverified.

The default/latest fixed snapshot origin is **May 2026**, nominal target **May 2027**, baseline **6.553333333333334 m**. ML correctly remains null: rainfall current/three-month mean/anomaly, temperature, ET and water balance are missing, and no observed exact target exists for this historical-only artifact. It does not silently retreat to January 2024. Unsupported Kaithal direct research returns unavailable, while its separate scenario succeeds.

Live scenario examples all supplied twelve finite nonnegative explicit monthly values and null issuance timestamps:

| District | Source-marked latest month | Gap in October | Estimated current depth, not measured |
|---|---|---:|---:|
| Kaithal | January 2026 | 9 months | 26.337015 m |
| Kurukshetra | January 2026 | 9 months | 38.275227 m |
| Adilabad, separate frozen source | May 2026 | 5 months | 1.642629 m |

The national source has 77 available Kaithal observations and 92 Kurukshetra observations; the recency rule can use a smaller fit window (37 Kurukshetra observations in the retained scenario evidence). Adilabad has 229 available observed months, with a 121-observation recent fit window in retained evidence. These counts must not be confused with independent wells or current observations. Nicobars and an unknown ID abstain with no borrowed path. The archived all-district coverage is 548 eligible / 104 insufficient / 73 no observed history, not 725 validated predictions; this audit did not regenerate all 725 fits. Eligible histories comprise 538 latest-January-2026, nine latest-January-2021 and the separate May-2026 Adilabad source.

Source comparison to `98c7056` preserves the CSS, map component, tier-card structure, alerts and simulator components. Home wording/links, district graph panel, view controls and related loading/error mounting changed. This is source continuity, not a pixel-level comparison. The default graph's methodology changed from the older six-month climate panel to the separately disclosed approved scenario; it is not merely a longer invocation of the same estimator.

## Local HTTP verification and the 403

The isolated normal API uses localhost **5053**, enforced PostgreSQL read-only sessions and guards against saved ML fitting. The original restricted demo helper uses **5051** with DB access forbidden. The frontend is **5183**, explicitly pointed at 5053 without editing environment/configuration files. Normal scenario and next-six serving execute their existing transient NumPy seasonal/trend fit in memory; this is not a new trained/saved checkpoint. These calculations were exercised only as existing application requests. Saved response evidence is an audit receipt, not a prospective forecast ledger; `forecast_issued_at` remains null.

The first socket attempt was blocked with **WinError 10013**. The authorized localhost retry produced **61/63 expected statuses and 176/179 contract checks**. Its two failed requests were Vite root 404 and `/api/config` proxy 502. The frontend launch was repeated from the explicit dashboard working directory, leaving the first receipt intact. A separate create-only verification passed **31/31** checks: frontend root, district deep link, alerts, simulation, client module and map boundary return 200; the transformed client includes the explicit 5053 API URL. Vite's unchanged relative `/api` proxy targets port 5000, which is absent in this audit; the configured client uses 5053 directly. The initial root 404 is consistent with a launch-directory/root problem, not evidence that the production build failed.

| Route family, normal 5053 API | Actual evidence |
|---|---|
| `/`, `/api/config`, `/api/health` | 200; health reports healthy legacy DB/bundles. Config reports the distinct 12-month direct and six-month products. Health does not certify research artifacts or predictive skill. |
| `/api/scores` | 200, 725 canonical records; Safe 300, Watch 365, Warning 50, Crisis 6, Unknown 4. Estimate types: 427 district, 294 real zone fallback, four insufficient. No scoring run was triggered. |
| Research catalog | 200, frozen bundle verified, Adilabad-only direct scope. Extra query rejected 400. Catalog availability is not ML availability for every origin. |
| Direct forecast/graph | Historical/default/latest and unsupported-district contracts behaved as above. Wrong/repeated horizon, malformed origin and legacy-window query rejected 400. |
| Scenario | Kaithal, Kurukshetra, Adilabad 200/scenario; Nicobars/unknown 200/unavailable. Wrong horizon, repeated/future date and historical-origin query rejected 400. |
| Legacy predict/district | 200, separate horizon six; Kaithal score 79/Warning, January-2026 origin → historical July-2026 target. Adilabad legacy source remains January 2026, distinct from its frozen May-2026 research source. Unsupported parameters rejected 400; unknown legacy ID 404. |
| Next-six climate | 200, explicit `climate_conditioned_xgboost_monthly`, six consecutive future buckets; unavailable evidence stays unavailable. |
| Recorded history | 200, equal `data`/`history` aliases, mutually exclusive observed/imputed flags and retained missing rows. Range/count errors rejected 400. |
| Alerts | Default 100 of 725 with `has_more`; limit 1000 returns all 725; tier filter and invalid-limit/tier handling checked. |
| Simulation | Zero-change Kaithal 79→79, delta 0, no changed XGB inference. +10% extraction 79→81, delta 2, explicitly heuristic metadata; Boolean numeric input rejected 400. No result written to the database. |
| CORS | Allowed audit origin receives its header; other origin does not. This is independent of the deliberate demo 403. |

**Confirmed local 403 mechanism:** the original demo helper's `before_request` allowlist rejects `/api/scores`, district/predict/health and the subsequently added scenario route. Live request `http://127.0.0.1:5051/api/scores` returns 403 with exactly:

```json
{"status":"unavailable","error":"Legacy routes are excluded from this read-only demonstration."}
```

The same helper serves the historical research catalog/graph with 200; normal 5053 `/api/scores` returns 200. This establishes the helper mechanism, not the launcher/URL of every historical screenshot. Normal factory routes have no authentication guard producing that response. No authentication or access control was weakened. No public deployment URL was established, so public hosting/proxy behavior is **NOT VERIFIED**.

Full safe response bodies/statuses are in [HTTP evidence](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/api_source/live_http_20261023.json), with [additional frontend/value checks](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/final_live_checks_20261023.json).

## Browser limitation

The earlier in-app Kurukshetra page exposed cached scenario/disclosure text, but a reload failed with **ERR_CONNECTION_REFUSED** after the old servers stopped. It is not fresh visual proof. A later in-app tab request did not yield retained usable chart evidence. Windows browser automation subsequently ended with:

> Computer Use has been stopped for this turn because it could not determine the current browser URL on Windows with enough confidence to enforce policy.

UI interaction stopped; no barrier was bypassed. Fresh rendered charts, responsive/mobile layout, map clicks, card appearance, navigation and live loading/error/retry interactions are **NOT VERIFIED**. Source review and mocked tests cover their contract/state logic, but neither those tests, HTTP shell responses nor a build is visual verification. [Exact attempt record](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/browser_limit_20261023.json).

## Source-to-feature lineage and data quality

| Source → transformation → use | Retained evidence and limits |
|---|---|
| Telangana NWIC CSV → frozen adapter exclusions → coordinate district / equal provider-month means → causal research features | 188,877 raw rows, 1,769 provider IDs, May 2007–May 2026. 188,458 accepted / 419 excluded; 1,764 accepted IDs, 33 coordinate districts, 7,555 district-month means. Every mean/count/panel hash reproduces. Provider IDs are not certified persistent physical wells. |
| Strict exact-name/coordinate subset → frozen Adilabad snapshot → fixed M+12 app and special Adilabad scenario | 2,817 source rows / 15 provider IDs; 233 months: 229 observed, three bounded fills, one missing. This is a different panel/target population from the 792-case broad study. |
| Legacy national CSV plus retained January-2026 station/PDF update → canonical feature export → national own-district scenarios and legacy DB features | Legacy raw 1,514,984 rows; usable mapped/dated/finite 1,366,656 across 559 districts. Retained update: 16,952 extraction rows, 16,605 accepted, 639 candidate district means; means reproduce without re-extracting PDF. National matrix: 725×297=215,325 unique rows, 36,890 observed, 72,110 filled, 106,325 missing GWL. |
| IMD daily grids → complete-calendar-month sum → district-cell mean / recorded nearest-cell fallback → rainfall and causal anomaly/rolling inputs | Export Jan 1992–Dec 2025; 295,392 rows/724 district-state pairs. All 34 annual grid hashes and CSV hash match. 8,978 rows use nearest-cell fallback; Nicobars maximum distance is approximately 1,604 km. Finite coverage does not establish local island measurement. |
| ERA5 monthly NetCDF → spatial extraction → temperature/ET → water balance | Jan 2002–Dec 2024, 199,824 rows/724 pairs. Bytes/metadata and declared conversions checked, not full extraction rerun. K−273.15 gives °C; signed metre evaporation conversion gives mm/month once. Eighteen nearest-cell districts recorded. |

Telangana raw data contain 27 missing/nonnumeric depths, five negative values, 218 zeros and 1,077 above-listed-well-depth readings. Twenty-one duplicated agency/ID/month keys involve 42 rows; there are no exact full-record duplicates. The frozen exclusions are 345 state/boundary disagreements, 42 conflicting well-month records, 27 nonfinite and five negative depths. Flags are reported without inventing corrections; negative mbgl can require domain interpretation, and above-depth values are QC concerns rather than automatically proven errors.

Independent geometry/crosswalk checks reproduce **125,400 name/coordinate conflicts (66.5400% accepted), 58,034 unresolved names (30.7941%), and 5,024 agreements (2.6658%)**. All 792 broad primary target panels contain conflicts, with mean conflict share 65.8031%. Agreement is stricter QC, not authoritative location verification. Mixed aquifers, changing memberships, shared coordinates and unknown datum/replacements remain. No coordinates or IDs were corrected.

**National freshness, source-marked only:** 639 districts latest January 2026; nine January 2021; two November 2019; one November 2018; one May 2013; 73 no observed groundwater. All September-2026 current groundwater entries are missing. The scenario's separate Adilabad override has May-2026 observations. This inventory measures retained source flags, not confirmed fresh field acquisition. [Per-district CSV](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/data/district_freshness.csv).

Groundwater uses source/repository **m below ground** conventions; datum continuity is uncertified. Rain/ET are mm/month; temperature °C. Current-vintage feature relationships reproduce bounded causal GWL carry (three months), weather carry (two), exact calendar lags and rainfall−ET water balance. Jan/Feb-2025 temperature/ET repeat Dec-2024, and Jan/Feb-2026 rainfall repeats Dec-2025: these are carries, not fresh weather. The reported export tail cannot be treated as current observations.

All eight acquisition response files match retained manifests and receipts; 72 additional hash comparisons across 47 distinct paths match. Telangana CSV SHA-256 is `f8222245721c421bc2f82b6afbd387ee5cd0e263790515ac7d3ffcce0c521302`, recorded receipt 19 October 2026 08:58:44 UTC. This receipt is not historic publication/acquisition proof. Private request headers/cookies were not copied or displayed; generated transport metadata is allowlisted/redacted. Full details, exclusion counts, units and lineage checks: [DATA.md](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/data/DATA.md).

## Independently recomputed historical performance

Errors are prediction minus observation. MAE is mean absolute error; RMSE is square root of mean squared error; R² is `1−SSE/SST` when target variation exists. R² is not an accuracy percentage. These current-vintage, previously inspected historical cohorts are not a newly untouched prospective test.

**Broad 12-month primary:** identical 792 observed-origin/observed-target cases, 33 districts ×24 months. Origins January 2023–December 2024; exact M+12 targets January 2024–December 2025. At M+12, persistence and annual seasonal naive are the **same effective baseline**, not two independent comparisons.

| Method | MAE m | RMSE m | Pooled R² | Bias m | Absolute-error p95 m |
|---|---:|---:|---:|---:|---:|
| Persistence / annual seasonal naive | 1.191079 | 1.457723 | 0.721470 | −0.242431 | 2.699686 |
| Expanding XGBoost | 1.159119 | 1.419908 | 0.735733 | +0.456614 | 2.499216 |
| Expanding linear regression | 1.927979 | 2.455646 | 0.209587 | +1.512082 | 4.913861 |
| Separate 12-month HGB | 1.222151 | 1.505470 | 0.702924 | +0.493834 | 2.808784 |

XGB's point RMSE advantage is **0.037815 m (2.59%)**. Paired method-minus-baseline ΔRMSE 95% intervals are **[−0.123913,+0.055974] m** for district resampling and **[−0.317330,+0.264465] m** for district×circular-12-month resampling. Both cross zero. The retained 2,000-replicate seed-42 procedure was independently reconstructed from sampled row indices; all **228 interval pairs /456 endpoints** across 19 archived comparisons agree within 1e−10. This is descriptive uncertainty under the specified dependence assumptions, not a validated future-error interval. Only two annual target blocks exist.

| Weighting of primary RMSE | Annual baseline | XGB | Linear | HGB |
|---|---:|---:|---:|---:|
| Pooled rows | 1.457723 | 1.419908 | 2.455646 | 1.505470 |
| Mean of 33 district RMSEs | 1.407106 | 1.386473 | 2.198170 | 1.478994 |
| Mean of 12 calendar-month RMSEs | 1.439376 | 1.398452 | 2.423136 | 1.478018 |

MAE is unchanged by these macro weights because this primary panel is balanced; averaging group RMSE is a different estimand from pooled RMSE. XGB wins 20/33 district and 8/12 month RMSE comparisons; it loses September–December. Loss districts include Adilabad, Kamareddy, Karimnagar, Mancherial, Medak and Siddipet; the complete list and every district/month/year/period statistic are saved. In target 2024, XGB/baseline RMSE is **1.335399/1.628014 m**; in 2025 it reverses to **1.499662/1.264706 m**, each n=396. On identical origin/target well-panel membership (380 cases/32 districts), XGB also loses: **1.437134 vs1.382523 m**. Geographic strictness reduces the primary cohort to 24 cases/one district, where annual expanding XGB RMSE2.517817 exceeds baseline0.876996. These sensitivity results prevent a reliable-superiority claim.

**Exact fixed application artifact:** separate 24 Adilabad cases, origins January 2023–December 2024, targets January 2024–December 2025. Model SHA-256 `f94911f5e1a6c3e8b4bbbb82d6a4c6ec87b5d601abbfd774801afc046aa5455f`.

| Method, fixed-artifact cohort | MAE m | RMSE m | R² | Bias m |
|---|---:|---:|---:|---:|
| Annual baseline | 0.645164 | 0.876996 | 0.880638 | +0.066662 |
| Fixed 2021-cutoff XGBoost | 2.144770 | 2.664045 | −0.101423 | +2.052587 |

The fixed artifact loses substantially. Paired circular-block ΔRMSE interval is **[+1.534353,+2.103300] m**; district-only uncertainty degenerates with one district. The 792-case expanding-model score must never be assigned to this artifact. Bundle/card/schema/provenance hashes and its 158 complete-feature training pairs, maximum training target December 2021, 2021-12-31 cutoff and first permitted origin January 2023 reproduce.

**Original six-month test:** 209 cases/32 districts/eight states, origins July 2019–September 2022 and targets January 2020–March 2023; different geography, horizon and period.

| Method | MAE m | RMSE m | R² |
|---|---:|---:|---:|
| Persistence | 1.233873 | 3.698362 | 0.809025 |
| Seasonal naive | 1.048686 | 2.131714 | 0.936552 |
| Ridge | 1.380663 | 2.573416 | 0.907535 |
| Random forest | 1.289730 | 2.558294 | 0.908618 |
| XGBoost | 1.432185 | 3.224709 | 0.854809 |
| Validation-selected HGB | 1.327448 | 3.060216 | 0.869244 |

Seasonal naive beats all tested ML methods on primary MAE/RMSE. HGB remains abstained; no test-driven replacement was selected. Its largest error, Faridabad 37.329406 m, contributes 71.195% of SSE. The separate retained Telangana six-month n=594 comparison also favors seasonal naive (RMSE1.440454 vs expanding XGB1.472179). Same-target/same-origin cross-horizon joins change conclusions and do not isolate a controlled horizon effect. The 66-case January–February-2026 twelve-month secondary cohort supplies only two target months, not another full annual validation period.

Full precision, bias/percentiles, group metrics, fingerprints, uncertainty, six-month comparisons and raw audit-failure resolutions: [METRICS.md](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/metrics/METRICS.md). No estimator was loaded by the arithmetic audit. Live fixed-example inference agrees with its archive, but this does not independently regenerate every archived prediction.

## Leakage, timestamps and issuance feasibility

**Confirmed calendar safeguards:** exact horizon joins and observed-only evaluation labels; training-target cutoffs and twelve-month embargo; bounded past-only fills/lags; derived-input month checks; training feature order; bundle/model/config/schema/source hash guards; different loaders for incompatible six/twelve-month artifacts; explicit unavailable results. The fixed artifact has a locked 2021-12-31 label cutoff; annual expanding cards use December-2021/2022/2023 cutoffs before first origins January-2023/2024/2025. No current audit retraining occurred. Source/code and saved membership checks found no target-as-feature or calendar-future input in these paths.

**Not established:** historic publication, actual field acquisition, first receipt, revision vintages, station changes and availability to the model at issue time. Telangana `actual_acquisition_at`, `first_publication_at`, `first_received_at`, `available_at` are empty; monthly reported dates, October download receipts and file timestamps cannot fill them. National datum/stable well IDs/panel identities are incomplete. Calendar-causal retrospective features do not prove issue-time feasibility. Future-source integrity tests verify rejection logic, not missing real metadata.

January-2024 → January-2025 is a nominal calendar horizon using data acquired in a later export. No contemporaneous archived issuance exists. If the latest May-2026 origin were examined in October2026, May2027 is only seven calendar-month steps after October, not twelve months from actual issuance; actual acquisition-to-issuance lead cannot be certified. The scenario instead labels November2026–October2027 as the next twelve full buckets, but these are statistical assumptions, not observed acquisition dates or validated direct-model horizons. No horizon was changed in this audit.

**Real shadow campaign remains NO-GO.** Minimum dependencies are provider-certified observation/acquisition/publication/revision semantics, auditable input availability receipts, stable well/panel and datum/change metadata, sufficiently current complete origin inputs, and a human-approved operational protocol defining issue time versus target acquisition and frozen-artifact authorization. These cannot be invented from existing files. The highest-priority dependency is **an auditable provider-to-model availability timeline for the intended forecast origin**, so that a real issuance with the required inputs and effective lead can be defined before any shadow prediction is archived.

## Claims and portability

README and shared UI explicitly describe an academic prototype, unverified nationwide/real-time skill, and the project-defined uncalibrated0–100 index. Tiers are project categories, not official classifications. ANN/MLP agreement imitates fuzzy-generated labels, not independently observed crisis outcomes. The simulator labels extraction as a heuristic sensitivity; the verified +10%→+2index example is implementation behavior, not evidence of a causal effect. The scenario discloses its separate seasonal/trend method, excluded weather/extraction and unvalidated status. Observed/fill history traces and current estimates are separately named in source. Visibility/readability across actual viewport sizes remains unverified.

A clean clone cannot reproduce the locally provisioned numerical app. Fifteen of seventeen audited runtime assets are untracked, including the frozen direct bundle, national feature CSV/manifest and legacy/climate pointers/models/cards. A matching populated PostgreSQL DB is also required. The default Docker context excludes all reports and Compose lacks a mount for the frozen research bundle; data/checkpoint mounts alone do not repair that omission. No container/deployment was run or changed. Local API health is not proof of reproducible deployment or nationwide skill.

## Executed safe checks and preservation

| Check | Actual outcome |
|---|---|
| Fetch and exact remote metadata | Exit0 for fetch and `ls-remote`; both branch SHAs equal local HEAD. |
| Reviewed guarded Python subset | Exit0, **161 passed**, 5.96s; live DB connections and estimator fitting/load fitting paths blocked in the test helper. Synthetic/mock inference contracts, not accuracy tests. |
| Frontend Node tests | Exit0, **57 passed**. |
| Frontend lint | Exit0. |
| Fresh isolated production build | Exit0,615modules,9.84s; new `frontend_build_20261023`, not the existing dist. Nonfatal large-bundle/outDir warnings. |
| Tracked Python AST syntax | **166/166 pass** without importing code. |
| Strict tracked JSON | **205/206 pass**; pre-existing `reports/data_audit.json` contains eight `NaN` literals. Not repaired. Live API JSON checks pass independently. |
| `git diff --check` | Exit0. |
| Data checks | Exit0;16/16 base,14/14 supplement,72/72 hash comparisons; national v2 and nested `--verify-only` exit0. First national helper exit1 (join suffix assumption), retained. |
| Metrics arithmetic | First helper exit1 solely two CRLF raw hashes; supplement exit1 solely two documented ID/hash encoding assumptions; final resolution46/46,exit0. Earlier failures retained, all metric/interval arithmetic reconciled. |
| Live HTTP |63requests;61expectedstatuses,176/179checks; initial transport failures and frontend404/proxy502 retained. Original helper does not signal failed checks in its process exit, so do not interpret an exit alone as success. |
| Additional frontend/archive checks | Exit0,31/31checks after explicit dashboard-directory launch. |
| Browser, responsive and interactive walkthrough | **NOT VERIFIED**, exact policy stop recorded. |
| Complete protected-file comparison | **1114/1115 unchanged**, same at final recheck; tracked source/index/HEAD unchanged. Combined repository-check exit1 reflects strict-JSON and preservation exceptions, not a hidden pass. |

Two raw frozen implementation hash differences are exactly CRLF→LF checkout normalization in memory; no source was normalized. The metrics supplement's two failed assertions used the wrong retained six-month ID format and training-membership hash encoding; separate receipts establish the actual builder formats. Neither correction changed a dataset, model, archived result or earlier failed record.

The one protected-file exception is `dashboard/dist/index.html`: before682bytes/SHA`273c2d6eec27ffa15c1daa1fed8e5100376cd3e63b583a3f94a87c869904c9ad`; after696bytes/SHA`f21af1b46c1ed4d5ed506773dac8784e54d471b25288301e3464926d6129a336`. Current creation/write metadata is22October16:49:41UTC, before this continuation's isolated23Octoberbuild. The other five inventoried dist assets still match. Original HTML bytes were not snapshotted, so an exact before/after text diff and writer attribution are unavailable. Rebuilding is plausible from the file timestamps, but no command receipt directly establishes its launcher.

Ten additional untracked files appeared outside this audit directory: an empty `aquaiq.db` (creation22October16:47:38UTC) and nine files in `final_research_readiness_20261022_audit`, `statistical_audit_correction_20261022`, `statistical_inference_review_20261022`. They were not in the initial untracked inventory. Filesystem metadata does not establish who created them. No SQLite connection was made to the empty file; no files were deleted, reverted, overwritten or regenerated to conceal this discrepancy. Full paths, times/hashes and all protected before/after values: [final preservation receipt](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/final_preservation_20261023.json).

All110inventorieddatafiles,46modelsfiles and757priorreportfiles match, including Telangana acquisition, normalized research data, saved row predictions, checkpoints, prior audits, both previously affected rainfall progress files and the two private cookie-bearing originals. Config and `.env` hashes match; no secret contents were emitted. This is file preservation evidence, not a production database contents checksum. Audit API connections enforce read-only, but the audit cannot certify absence of unrelated external DB activity. Fetch changed Git remote metadata intentionally. Dependency/runtime caches were not included in the protected inventory. New audit evidence resides only under this dated directory; all earlier outputs were retained.

Containment recommendation: retain the HTML and outside-audit file evidence, coordinate other workspace jobs, and obtain the missing command/session history before attributing these changes. Do not auto-clean, restore or publish private evidence. No claim of perfect whole-workspace preservation is made.

## Commands and reproduction

Repository root is `C:\Users\Yasharth\Downloads\AquaIQ`. The following are the actual safe check commands; use **fresh audit output names** for a later run. Evidence writers intentionally refuse replacement. Do not rerun builders, training, ingestion or full pytest for this audit.

```powershell
git -c gc.auto=0 fetch --no-tags --no-write-fetch-head --no-auto-maintenance origin refs/heads/main:refs/remotes/origin/main refs/heads/experiment/12-month-horizon:refs/remotes/origin/experiment/12-month-horizon
git ls-remote --heads origin refs/heads/main refs/heads/experiment/12-month-horizon
.\venv\Scripts\python.exe -B reports/end_to_end_verification_20261022/run_safe_tests.py tests/test_research_forecast_api.py tests/test_research_graph_api.py tests/test_research_graph_demo.py tests/test_api_audit_regressions.py tests/test_cors_configuration.py tests/test_deployment_readiness.py tests/test_tiers.py -q -p no:cacheprovider --basetemp=reports/end_to_end_verification_20261022/checks_20261023/pytest_tmp --junitxml=reports/end_to_end_verification_20261022/checks_20261023/python-tests-01.xml
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../reports/end_to_end_verification_20261022/frontend_build_20261023
.\venv\Scripts\python.exe -B reports/end_to_end_verification_20261022/check_repository.py
.\venv\Scripts\python.exe -B reports/end_to_end_verification_20261022/final_live_checks.py
git diff --check
```

Exact arithmetic/data commands and observed exits: [metrics command receipt](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/metrics/COMMANDS.md), [data command receipts](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/data/DATA.md), [verified parent command receipt](C:/Users/Yasharth/Downloads/AquaIQ/reports/end_to_end_verification_20261022/commands_verified_20261023.json). The latter corrects two manually transcribed fields while preserving the initial receipt: the parent did not retain the HTTP helper's process exit, and the exact Vite argument spacing is recorded. An initial command-receipt correction attempt failed shell parsing before writing output; the standalone correction helper then exited0. Test stdout/JUnit, lint/build output and quality JSON are retained in this directory. The unrestricted training-capable suite, all-district fit regeneration, model backtests, Docker/public deployment and full source-weather extraction were not run.

Audit serving commands (separate existing-runtime processes, no source changes):

```powershell
# Repository root, separate API process
.\venv\Scripts\python.exe -B reports/end_to_end_verification_20261022/audit_server.py
# Repository root, separate original guarded demonstration process
.\venv\Scripts\python.exe -B reports/candidates/twelve_month_graph_only_20261021/demo_server.py
# From C:\Users\Yasharth\Downloads\AquaIQ\dashboard
$env:VITE_API_URL='http://127.0.0.1:5053'
& 'C:\Program Files\nodejs\node.exe' '.\node_modules\vite\bin\vite.js' --host 127.0.0.1 --port 5183 --strictPort
```

These are development/audit servers, not production deployment. The initial Start-Process PID receipt is historical; the continuation started new tool sessions62619(Vite),70044(API),76358(guard). Their exit codes were not final while serving; no existing unrelated service was stopped. This report does not promise they remain alive after the audit session ends.

## Final verdicts and submission checklist

| Area / explicit conclusion | Verdict |
|---|---|
| Do local numerical APIs and frontend assets run? | **PARTIAL:** normal provisioned API and corrected frontend asset checks pass; full live visual walkthrough incomplete. |
| Does the graph represent its twelve-month contract? | **PASS for API/source/tests; PARTIAL overall:** direct graph is eleven nulls plus one M+12 endpoint; default scenario has twelve explicitly different monthly estimates. Render not verified. |
| Are saved historical metrics arithmetically correct? | **PASS**, including dependent paired intervals and separate artifact identities. |
| Does ML outperform annual baseline? | **FAIL for a reliable-superiority claim:** broad XGB small point gain is uncertain/reverses by year/panel; fixed app loses strongly. Six-month seasonal naive beats HGB. |
| Historical input availability certified? | **NOT VERIFIED.** |
| Prospective forecasting skill established? | **NOT VERIFIED.** No prospective campaign started. |
| Data/location reliability sufficient for operational district claims? | **FAIL:** major name/coordinate conflicts, unknown stable wells/datum/vintages. |
| Pushed source alone/default container reproduces this local app? | **FAIL:** ignored assets/external DB and missing research-bundle container mount. |
| Whole protected workspace perfectly unchanged? | **PARTIAL:**1114/1115 byte hashes match; one dist HTML exception and ten extra external untracked files disclosed. |
| Ready for academic demonstration? | **PARTIAL/conditional:** suitable as a disclosed local research prototype after a human visual rehearsal and confirmation of retained runtime assets. Not certified end-to-end visually by this audit. |
| Ready for production? | **FAIL / NO-GO.** |

- [x] Freeze the presentation at the verified SHA and distinguish the792-case expanding study,24-case fixed artifact,209-case old benchmark and unvalidated scenario.
- [x] Preserve active models, HGB abstention, datasets and prior experiments; report the separate built-HTML preservation exception.
- [x] Present observed/fill/estimated/scenario values and the uncalibrated index/heuristic simulator accurately.
- [ ] Complete a human desktop/mobile walkthrough of map/cards, Kaithal/Kurukshetra scenario, Adilabad January2024 direct graph, latest unavailable case, history, alerts, simulation, navigation and retry states.
- [ ] Verify artifact/database provisioning on the exact demonstration machine; use the normal API, not the restricted5051helper, for the complete dashboard.
- [ ] Resolve attribution/containment for the unexpected dist/external files before any further release action; do not publish private cookie originals.
- [ ] Obtain real availability/measurement metadata and approve an operational protocol before any shadow issuance. No current result establishes production readiness.

**Demonstrated:** reproducible retained historical error arithmetic, nominal-calendar contracts, observed-only target membership, frozen-artifact/source checks, explicit abstention and local API separation of research products. **Unverified:** trustworthy physical-well geography/datum continuity, historical input availability, effective prospective lead, nationwide/current forecast accuracy, causal simulation effects, reliable ML superiority, fresh visual completeness and portable production deployment.
