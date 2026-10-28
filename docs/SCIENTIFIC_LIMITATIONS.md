# Scientific conclusions and limitations

AquaIQ is an academic forecasting application. Complete geographic output, reproducible model loading and passing software tests do not establish forecasting accuracy or deployment readiness. The frozen production model remains active. The enriched refit remains experimental, and the grouped-horizon experiment was rejected as a replacement.

## Data and source provenance

The accepted final feature generation is `physical-v3-official-c9ade81d95720f91`; this retained snapshot does not automatically replace the service's configured publication. Its 725-district calendar grid contains **43,384 observed district-months**; a populated calendar row is not necessarily a measurement. Official manual enrichment added 5,952 previously missing measured months, and the verified January archive added 542, for 6,494 gains across 653 districts. Sixteen districts gained their first local history; **57 still have none**. Existing measured values took precedence and were not overwritten. See the [data audit](../reports/retraining_20261027/data_audit.json).

The January source contains 15,892 rows: 15,075 accepted and 817 quarantined. Quarantine reasons overlap and cannot be summed as independent rejected records. Its 571 district-months overlap 29 existing months; 14,213 readings support the remaining 542 additions. Locations are averaged within the source before district aggregation. Source-location fingerprints do not certify physical well identity, stable panels, aquifer construction or datum continuity. Targets are measured depth in metres below ground (`m_bgl`), never generated, imputed or predicted labels. The [groundwater evidence](../reports/final_release_20261026/groundwater_sources.json) records acceptance and source precedence.

The 274,930 telemetry rows remain quarantined because sign/reference conventions are unresolved; 41 station fingerprints contain both signs. No blanket sign flip or elevation subtraction is justified. Observation dates also do not establish when values were published or available to a historical forecaster.

Attribution and permissions remain source-specific: CGWB, NWIC/NWDP and SGWD Telangana observations; IMD/ERA5 weather; and DataMeet/Survey of India boundaries. NWDP's `Other (Open)` label supplies no specific license URL, and CGWB/Survey of India copyright must not be treated as a general redistribution grant. The [catalogue](../data_sources/catalog.yaml) and retained source records preserve these qualifications.

The [weather/boundary investigation](../reports/final_release_20261026/weather_boundary_sources.json) acquired zero new weather arrays. A bounded ERA5 request returned HTTP 403 requiring manual terms acceptance; newer values remain unassessed, not absent. Contemporary SoI polygons do not authorize moving historical observations between boundary vintages. Both Mumbai polygons lack usable interior ERA5 centers under the current method and select a shared external cell. Alternative attribution changed 216 pre-2020 rows and failed frozen compatibility; it was not promoted or shown to improve forecasting. [Measured attribution](../reports/final_release_20261026/weather_attribution.json) distinguishes feature differences from prediction errors.

## Evaluation and model status

| Model | Status | SHA-256 |
| --- | --- | --- |
| Frozen twelve-month XGBoost | Active production weights | `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03` |
| Enriched XGBoost refit | Unpromoted research candidate | `e4e57de9f681b2f2702c9b86a00be06b04147123ecea0579f6abcf3cdc586192` |

The enriched fit uses **145,494 observed-origin/observed-target pairs across 641 districts**, labels through January 2025 and 17 ordered horizon-conditioned features. It predicts depth change; serving reconstructs the anchor plus change and floors depth at zero. Calendar joins, lag fallback and weather assumptions use origin-available prefixes. Learned preprocessing uses training partitions only. These causal calculations cannot prove historical publication availability or isolate enrichment from corrected feature alignment.

The [retraining protocol](../reports/retraining_20261027/protocol.json) selects among three prespecified settings on chronological 2023/2024 validation origins, with training labels ending December 2021/2022 and a twelve-month embargo. Mean fold district-macro MAE is **1.913 m**, versus **1.978 m** frozen and **2.517 m** persistence. These earlier selection results are not the final refit's untouched test. The [acceptance decision](../reports/retraining_20261027/acceptance.json) retains frozen production because that required later test is absent.

The twelve-origin 2025 serving diagnostic scores **7,668 cases/639 districts**, all targeting January 2026. On its identical four-way subset of **6,756 cases/563 districts**:

| Method | MAE (m) | RMSE (m) |
| --- | ---: | ---: |
| Frozen | 1.776656 | 2.938660 |
| Enriched | 1.723345 | 2.884739 |
| Persistence | 1.634254 | 2.885459 |
| Seasonal naive | 1.634254 | 2.885459 |

Both baselines correctly use January 2025 on this subset: the latest eligible observation is also the exact prior-year month. Missing seasonal values are excluded from every method in the paired comparison, without persistence substitution. [Baseline reproduction](../reports/accuracy_experiments_20261027/audit_v2/baseline_audit.json) and the [complete diagnostic](../reports/retraining_20261027/retrospective/summary.json) preserve differing populations, missing truth and horizon regressions. Estimated-anchor serving errors differ from observed-origin model errors.

The [nested development protocol](../reports/accuracy_experiments_20261027/protocol_v2.json) evaluates sixteen supported recipes and two baselines. Inner windows select settings before outer 2020/2021 evaluation; complete twelve-horizon target windows end before 2023. Refitted recipes supply chronological controls; fixed artifacts trained on later labels cannot rank earlier folds.

On **9,833 common cases/617 districts**, selected grouped horizons have mean outer-fold district-macro MAE **1.388311 m**, worse than the current recipe's **1.377637 m**; pooled MAE/RMSE is **1.464994/3.262515 m**. Two subgroup checks fail and eight lack support. The two-percent frozen improvement gate also fails. [Corrected comparisons](../reports/accuracy_experiments_20261027/analysis_v2/comparison.json) and the [assessment](../reports/accuracy_experiments_20261027/acceptance_assessment.json) preserve these negative findings. No alternative was selected after inspecting outer rankings. Shared target months, repeated districts, weak subgroup support and inspected holdouts limit inference; ablations do not establish physical causality.

## Nationwide output and uncertainty

The [final isolated generation](../reports/final_release_20261026/generation.json) produces 725 district outputs, 8,700 horizons and 36 state/UT outputs: **551 A / 116 B / 57 C / 1 D**. A uses eligible XGBoost; B/D use explicit local persistence; C uses regional/global references. State summaries weight registered districts equally, not wells, area or groundwater volume. Availability and coverage are not local skill. [Tiered validation](../reports/nationwide_20261025/validation.json) retains sparse/cold-history sensitivities; natural sparse evidence has only seven target cases. Shared donors and changing panels limit transfer claims.

The [interval audit](../reports/final_release_20261026/uncertainty_audit.json) reports **661/843 cases covered (78.41%) across 640 districts**, mean width **5.791 m** and interval score **22.151 m** for older final bands. Tier C covers **3/15 (20%)**; its M+12 radius came from one calibration district and one January 2022 target. These dependent pooled fractions are not local probabilities.

Calibration targets end July 2022 and precede evaluation origins. Numerical bands require ten distinct calibration districts per tier/horizon; this disclosure guard is not a coverage guarantee. Supported old radii stay unchanged; unsupported C/D bands are unavailable. Withholding 19 final-band cases changes the denominator and is not improved calibration. [Identity checks](../reports/final_release_20261026/uncertainty_identity_check.json) prevent attaching older measured coverage to a newer generation. Old calibration is not transferred to new model weights; enriched-candidate intervals remain unavailable.

## Reproducibility and outstanding evidence

Follow [asset restoration](FINAL_RELEASE_REPRODUCTION.md) and [scientific workflows](ACCURACY_EXPERIMENTS.md) for exact inputs and locked procedures. A code-only clone lacks required local observations, features, bundles and populated publications. The [supplied-asset replay](../reports/final_release_20261026/clean_supplied_asset_replay.json) and [export comparison](../reports/final_release_20261026/clean_output_comparison.json) reproduced recorded outputs using cached sources, supplied baseline assets and local credentials; they did not independently reacquire the baseline.

Promotion needs genuinely new observed targets, forecasts archived before those targets arrive, documented source receipt times, stable well/datum checks, realistic stale-anchor and geographic evaluation, and matching independent uncertainty evidence. Software tests, metadata integrity and historical error reductions cannot replace those requirements.
