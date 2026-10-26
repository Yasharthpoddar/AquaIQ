# Final reliability release — 26 October 2026

This release continues commit `87e40ca2f48e1e1fd2f381f17b8a7b9c236c3f8b` on `feature/final-reliability-release`. It accepts additional attributable measurements, corrects manifest and uncertainty defects, and tests reproducibility in an independent environment. It preserves frozen model weights, weather values, the canonical 725-district registry, historical boundary mappings, six-month contracts and the existing running forecast service. Main remains `5ef30c346b71d75b2918e71cdcadc13a9e69d06b`. Unrelated local `tests/test_fuzzy_crisis_unit.py` is excluded from the commit.

## Accepted data and source decisions

The [groundwater investigation](groundwater_sources.md) and [source catalog](../../data_sources/catalog.yaml) separate discovery, metadata access, download, parsing, integration and validation. Reusing the already verified CGWB January archive avoids a duplicate 38.5 MB download. Its actual January 2025 pages supply 15,892 source rows: 15,075 accepted and 817 quarantined. The resulting 571 district-months overlap 29 existing measured months; existing means take precedence. The remaining **542 measured months across 542 districts**, supported by 14,213 readings, enter the new snapshot. Products are never pooled together to overwrite an existing measured mean.

Five districts gain their first accepted local month: AR-Kamle, AR-Longding, SK-East_Sikkim, UK-Pithoragarh and UK-Rudraprayag. The new total is **43,384 genuine observed months**, compared with 42,842 in the previous enrichment and 36,890 in the original baseline. Across both enrichment stages, 653 districts gain months and 16 previously unobserved districts gain history. Some months in the candidate overlap original measurements and are deliberately retained unchanged.

Quarantine reasons overlap: conflicting location/date depths 174; source-state disagreement 105; near-boundary coordinates 89; ambiguous colocated labels 125; unresolved district 65; exact duplicate location/date/depth 271. These cannot be summed as independent rejected rows. Coordinates/block/village fingerprints remain source locations, not certified physical well identities. Targets retain measured `m_bgl` units; the archive title does not certify every well's aquifer construction or a stable sampling panel.

New downloads supplied CGWB high-frequency measurement guidance (124 pages, February 2026), the WB/Andaman/Sikkim yearbook (197 pages), and official Survey of India boundary geometry and metadata. The first two are documentation, not additional accepted depth tables. Thirty-one refreshed NWDP 2026–2030 manual resources were actually fetched again; all contained headers and zero observations. Exact publishers, URLs, byte counts, checksums, vintage and license/attribution limitations are in the linked source reports and catalog. Raw datasets, extracted station rows, full geometry and generated forecasts remain ignored.

The 274,930 telemetry records remain quarantined. Forty-one station fingerprints contain both signs. `RL_MSL` does not establish sensor/reference datum or export sign convention. There are only 16 same-day manual matches and no exact timestamp matches; disagreement cannot validate a conversion. Release requires provider-certified well IDs, sign/variable/units, measuring-point elevation, sensor/cable/reference details and correction/clock logs, followed by independent overlap validation. No blanket sign flip was applied.

## Weather, boundaries and auxiliary predictors

The [weather/boundary investigation](weather_boundary_report.md) acquired the actual SoI 2025 archive and metadata, then streamed exact Mumbai LGD 519 and Mumbai Suburban LGD 518 records without persisting national geometry. The distinct valid polygons are published in May 2026; their vintage does not authorize migrating historical groundwater records.

Both districts have zero usable ERA5 grid centers inside their polygons under the current training definition. Its nearest usable land-center fallback selects the same external 19° N, 73° E cell. Footprint weighting intersects two/four cells respectively and changes the definition, including offshore-centered cells. Filling Suburban historical temperature/PET changes 216 pre-2020 rows and correctly fails the frozen compatibility guard. No production weather feature or Tier D status changed; no trained held-out improvement is claimed for this rejected alternative.

A bounded request through the existing user-managed Copernicus configuration returned actual **HTTP 403 requiring manual dataset-license acceptance**. Credentials were never printed or committed and no terms were accepted by the agent. This does not independently verify token validity or show that newer ERA5 data are absent. No new arrays were acquired, so newer-date coverage and numerical revisions remain unassessed.

Previously catalogued aquifer, geology, land-cover, resource-assessment, soil-moisture and GRACE sources retain their actual investigated status. None establishes compatible historical district-level depth labels or a validated transfer predictor. No auxiliary feature enters production or substitutes for missing targets. Metadata availability is not predictor validation.

## Frozen model and fair diagnostic

The feature snapshot is `physical-v3-official-c9ade81d95720f91`, CSV SHA-256 `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042`. The accepted source manifest is `pdf_january_2025_v2/manifest.json`, SHA-256 `a6e32fab5b3b9f16aa734b53e96a28bc8cf702dd306a27fd559fb549d93f420e`. The frozen XGBoost SHA remains `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`. All 156,600 training rows through December 2019 are unchanged. No model was refitted or selected from these results.

The [frozen diagnostic protocol](diagnostic_protocol.json) uses origins 28 February and 31 July 2025, allowing January 2025 observations into history. The [final diagnostic](final_diagnostic/summary.json) compares identical available measured targets: **1,278 cases, 639 districts, 31 states**, targeting **January 2026 only**, at horizons 11 and 6. These target labels were previously inspected. This is a retrospective diagnostic, not a blind test, new independent evaluation period or validation of twelve future trajectories. Historical publication availability and changing well panels remain limitations.

| Candidate tier | Cases / districts | Previous MAE / RMSE (m) | Enriched MAE / RMSE (m) |
| --- | ---: | ---: | ---: |
| A | 1,086 / 543 | 2.330 / 4.359 | 1.744 / 2.791 |
| B | 174 / 87 | 3.125 / 4.605 | 1.722 / 2.837 |
| C | 18 / 9 | 6.819 / 9.675 | 6.100 / 10.099 |
| All | 1,278 / 639 | 2.501 / 4.511 | 1.802 / 3.025 |

There are no valid Tier D target cases in this diagnostic. Tier C RMSE worsens despite lower MAE; new measurements do not establish uniformly better transfer performance. Tier A's 1,086 paired persistence cases have baseline MAE/RMSE **1.602/2.791 m**, versus **1.744/2.791 m** for the candidate. Tier B remains local persistence (rounding explains tiny numerical differences), rather than a promoted complex model.

| Identically paired subset | Cases / districts | Candidate MAE / RMSE (m) | Baseline MAE / RMSE (m) |
| --- | ---: | ---: | ---: |
| Persistence | 1,260 / 630 | 1.741 / 2.798 | 1.619 / 2.797 |
| Seasonal naive | 1,126 / 563 | 1.792 / 2.895 | 1.634 / 2.885 |

The machine report includes all horizon, state, observation-age and origin panels with exact counts/dates. At M+6, overall MAE/RMSE is 2.477/4.516 → 1.833/3.022; at M+11, 2.526/4.506 → 1.771/3.028, each with 639 cases. Baselines still matter: enrichment does not prove XGBoost superiority.

Strict pseudo-cold diagnostics exclude all target-district history, including earlier hidden history, and do not use the pretrained model. Across the same 1,278 cases, regional-reference MAE/RMSE is **3.302/6.004 m**, global **3.845/7.376 m**, and state-blocked **3.886/7.405 m**. Spatial blocking worsens the reference. These dependent inspected targets cannot select a new transfer method. The documented regional/global reference remains in place for 57 zero-history districts.

## Uncertainty correction

The [interval audit](uncertainty_report.md) verifies the original sealed cases/radii and reports tier, horizon, state, age and origin panels with counts, distinct districts and dates. The old enrichment's final bands cover **661/843 cases (78.41%) across 640 districts**, with mean width **5.791 m** and mean interval score **22.151 m**. Tier A covers 81.81% of 731 cases; B 61.86% of 97; C only **3/15 (20%)** across 15 districts. C's M+12 radius comes from one calibration district and one January 2022 target; its other horizons contain only 1–6 calibration districts.

The new disclosure policy withholds numerical bounds with fewer than ten distinct calibration districts per tier/horizon. This calibration-only tail-resolution guard is not a coverage guarantee or a threshold chosen from final errors. Supported radii remain unchanged. Statuses are `historical_reference_only`, `empirical_undercovered` or `unavailable`; no output claims newly calibrated 90% coverage. All twelve point values remain. The frontend also suppresses partial legacy bounds labelled unavailable.

Calibration targets end July 2022 and precede evaluation origins. An exact comparison confirms all **179,075 input/label rows through July 2022** match between old/new enriched snapshots, permitting only an identity rebind of unchanged radii/counts in `calibration_v3.json`. Older final coverage is not attached to the new feature generation. New A/B supported bands are historical references; C/D bands are unavailable. Withholding 19 old final-band cases changes the denominator and is not claimed as improved calibration. No widening, refitting or model selection used final residuals.

## Defects fixed and reproducibility

- Frozen model-card fingerprints now bind the persisted CSV as actually reloaded. CSV serialization previously produced a card/dataframe mismatch for newly built candidates. Training-value equality is checked again after persistence.
- Generation identity verifies actual feature bytes before idempotency, covers missing predictive implementation dependencies and interval evidence, and normalizes code newlines/canonical JSON. A stale manifest fails closed; identical LF/CRLF checkouts produce the same identity.
- Setup accepts an explicit isolated schema, validates it before connection, and keeps migrations/sequences inside it with temporary objects last in resolution. Default setup behavior is preserved.
- Clean frontend installation revealed two high-severity dependency advisories. The compatible Vite 8.3.3/source-map-js 1.2.2 lock update reduces the actual npm audit to zero reported vulnerabilities. The working development server's installed modules were not replaced during this test.

An actual separate Git checkout and independent Python 3.13.15 environment installed the documented requirements and passed `pip check`. The [code-only probe](clean_environment_probe.json) actually failed feature loading because ignored baseline assets/credentials were absent; the compact tracked model hash verified. This limitation is retained explicitly.

The [supplied-asset replay](clean_supplied_asset_replay.json) then validated cached source acquisition/checksums, reconstructed the overlay and calibration, ran migrations/publication in `aquaiq_test_clean_final_20261026`, and reproduced feature ID, CSV bytes, calibration values, generation identity, all 725 districts and 8,700 horizons. It used supplied verified baseline/source assets and local credentials, so it does not establish independent reacquisition of the historical baseline. The pre-commit public source patch hash is recorded. Exact acquisition constraints, hashes and commands are in the [reproduction guide](../../docs/FINAL_RELEASE_REPRODUCTION.md).

The final isolated generation is `015b39d9-56c3-57eb-839c-6d62ce26de9e`, with **551 A / 116 B / 57 C / 1 D**, 36 states/UTs and November 2026–October 2027 outputs. It is separate from the working `600edc35-506d-501d-82c2-5cc2ebcfe699` publication. Default requests continue reading their configured namespace. Existing public tables and prior publication are checked separately; the new generation is not automatically substituted into the user's running service.

## Validation and remaining limitations

Executed final validation evidence is recorded below as checks finish. Focused source and uncertainty tests are additional checks, not substitutes for the full run. An initial root publication command used a nonexistent checkpoint filename and failed before inference/publication; the corrected generated `frozen_bundle/checkpoint.json` path succeeded. The old valid generation was preserved.

Remaining limits are substantial: 57 districts lack accepted local observations; one district lacks independently attributable weather; observation dates do not establish historical publication availability; changing stations/datum and uneven recency limit validation; simple baselines remain competitive or better; zero-history errors remain large; historical bands are not calibrated local probabilities; newer ERA5 data remain access-blocked; and code-only clones require externally restored baseline data and a configured database. No operational advisory, current district-specific accuracy or prospective twelve-month skill is established.
