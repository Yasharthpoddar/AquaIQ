# AquaIQ — saved-result diagnostics and prospective evaluation design

**Decision:** retain the previously locked `hist_gradient_boosting-2-delta` as the sole research ML candidate. This audit fits nothing, changes no selection, and authorizes no release. Seasonal-naive’s advantage reflects sampling weights, repeated aggregate values and a major station-composition break; it does not establish a universally superior physical forecasting process.

**Evidence audited.** Recomputed all 228 calendar, 6,522 district and 84 year metric rows from the four saved prediction cohorts, including validation. All agree within numerical tolerance. Rejoined every primary origin, target and seasonal reference to the verified feature release: all targets/references carry observed flags. All 627 corresponding raw-source monthly means reproduce within 0.00001 m. Those flags establish source-backed monthly values, not independently certified fresh measurements. No production model, dataset, old report or completed experiment was changed.

**Weighting matters.** Entries below are MAE / RMSE in metres on the same 209 primary cases. Macro metrics are arithmetic means of group MAEs and group RMSEs, not square roots of averaged group MSEs. R² is not averaged across groups.

| Model | Pooled | Equal district | Equal target calendar month |
|---|---:|---:|---:|
| Persistence | 1.234 / 3.698 | 3.671 / 3.780 | 1.060 / 2.469 |
| Seasonal naive | 1.049 / 2.132 | 2.071 / 2.186 | 0.971 / 1.883 |
| Ridge | 1.381 / 2.573 | 2.220 / 2.307 | 1.383 / 2.142 |
| Random Forest | 1.290 / 2.558 | 2.236 / 2.329 | 1.280 / 2.031 |
| XGBoost | 1.432 / 3.225 | 2.709 / 2.807 | 1.389 / 2.379 |
| Frozen HGB candidate | 1.327 / 3.060 | 2.548 / 2.655 | 1.298 / 2.237 |

Validation’s **3,312/3,522 May/November cases (94.0%)** favor HGB under pooling: RMSE 2.148 versus seasonal 2.436. Equal-month evaluation reverses that ordering: HGB MAE/RMSE 1.753/2.551 versus seasonal 1.594/2.367. Other validation months contain only 18–29 cases each. This is a descriptive weighting sensitivity, not a new selection rule applied to the old test.

**Where seasonal naive gains.** It has lower absolute error than HGB on 141/209 cases, Ridge on 149, RF on 137 and XGBoost on 147. Against HGB, the largest summed absolute-error advantages are Faridabad 21.79 m, Kurukshetra 17.41, Sivaganga 14.88, Thoothukkudi 9.23 and Alwar 8.60; Cuddalore offsets 16.28 m in HGB’s favor. These are error sums, not district MAEs; all district sizes and scores are in `district_contributions.csv`.

Seasonal wins primary RMSE in February–May and August, and MAE in nine months. August’s 16 cases give HGB/seasonal RMSE **9.383/4.258**; HGB has lower RMSE in the other seven months. Month samples range from 11 to 45 and contain different districts, so month effects are confounded with geography and year. `calendar_comparisons.csv` retains every month and ML family.

**Measurement patterns explain the arithmetic, not the hydrology.** Of 209 targets, 68 equal their exact prior-year seasonal value, 90 equal persistence and 64 equal both (tolerance 1e-9 m). The 68 seasonal-exact cases contribute 103.2% of HGB’s net excess absolute error; on the remaining 141 cases HGB/seasonal MAE is 1.541/1.554. All 48 targets in 2022 equal persistence and 43 equal seasonal; nine of ten in 2023 equal both. HGB/seasonal RMSE is 0.802/0.181 in 2022 and 0.596/0.009 in 2023. These later cases cover only Cuddalore, Tiruppur, Sivaganga and Deoria, not a broad new geographic panel.

Faridabad alone contributes **114.3%** of the net HGB-minus-seasonal squared-error gap. Its February 2020 origin is 65.66 m from one station-location proxy; August’s target is 20.445 m from two different proxies. The prior August reference, 35.9833 m, shares both target proxies. This makes station composition a plausible contributor to seasonal’s advantage; it does not establish an erroneous reading or a causal explanation. Retain the case. Across all primary cases, mean origin–target proxy Jaccard overlap is 0.638 versus seasonal–target 0.820; six origin–target panels share no proxy. Proxies use name and coordinates, not certified well identifiers.

Legacy ingestion averages all readings per district-month. Equal weighting of station-location proxy means would change 59/209 target means by more than 1e-5 m, with a maximum difference of 15.93 m. No alternative labels were substituted or scored. Very flat district means can coexist with multiple different readings at one proxy; the raw file cannot distinguish colocated wells, source carry-forward and fresh acquisitions. Different measurement frequencies also change effective well weights.

The 962-case causal-origin sensitivity remains seasonal-favored but is January/August-heavy (809 cases) and includes the primary cohort. The separate Gujarat cohort reverses the result, yet four districts’ 12 cases supply 98.5% of HGB’s squared-error benefit over seasonal. It covers only May/November, has unresolved datum and panel composition, and cannot certify generalization.

**Dates, units and issuance.** All saved horizons are exactly six calendar-month buckets. Raw reported dates follow the saved month-start bucket for 208/209 origins and all targets; latest source-date separations range 162–204 days. Complete origin-month rainfall totals and ERA5 monthly means/totals cannot be known at the month-start index. Causal calendar joins are verified; actual publication/receipt times, revision vintages and issuance snapshots are absent. Thus actual six-month operational lead is unverified. All primary input weather/lag fields are finite, but finiteness does not establish availability at issuance.

The feature manifest declares target depth in `m_bgl`, not depletion or elevation. The legacy `currentlevel` header does not independently certify datum; Gujarat explicitly states metres but not below-ground datum. [CGWB describes its monitoring convention as depth below ground and its seasonal monitoring rounds](https://cgwb.gov.in/en/ground-water-level-monitoring); that general convention does not certify these particular downloaded records.

**Prospective design — register before new outcomes.**

1. Keep HGB’s locked settings and December 2018 training-label cutoff. No serialized final HGB exists in `experiment_v2`; a separate deterministic refit of the same 14,817 pairs is needed later solely to create a frozen shadow artifact. Do not fit it in this audit. Freeze weights/binning, native missing-value handling, feature order, zero clipping, code, fitted transformation state, software and source hashes. Causal histories may advance only through admissible inputs; never revise previously issued snapshots.
2. Register districts, supported months, fixed well panels/weights, sampling/aggregation, missingness, issuance schedule and analysis date. Archive each HGB, persistence and exact prior-year seasonal prediction with timezone-aware `issued_at`, input values, source-version hashes and `available_at`. Require every input’s availability at or before issuance. No backdating or regeneration after labels arrive. Existing prospective utilities need an explicit adapter for this direct six-month model, both baselines and well-panel provenance; they are not already a complete implementation.
3. Separate nominal origin-month+6 forecasts from genuine six-full-month lead. For the latter require target acquisition at least six calendar months after actual issuance. If complete-month inputs prevent this, that release gate fails; do not move targets or silently substitute estimated weather. Resolving that incompatibility requires a separately developed and preregistered feature/target protocol, not retuning on this test. Evaluation must use information available at the forecast origin, consistent with [rolling-origin forecasting evaluation](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation).
4. Primary labels must be newly acquired after issuance, observed in the registered target month, verified in m_bgl and from the complete panel registered at issuance. Origin and exact seasonal references must also be observed and known by issuance. Do not choose a matched-well intersection after the target arrives. Track missing wells, absent baselines, abstentions and label delays; partial-panel and variable-composition aggregates are separate secondary cohorts. Historical backfills remain retrospective.
5. Obtain immutable provider well IDs and replacement/relocation history; aquifer/screen and well depth; measuring-point/ground datum and changes; actual acquisition timestamp, method, pumping status and fresh/sensor-filled flag; source record ID, first publication, receipt and revision history. Record per-well sampling counts and frozen aggregation weights. Collect current origin readings plus 3/6-month lags, exact prior-year references, point-in-time weather and future targets. Without recoverable history, a full seasonal-reference→origin→target chain takes approximately a year of new observation collection. Quarterly rounds alone cannot support a year-round monthly claim; obtain quality-controlled monthly observations across registered aquifers and regions, including districts not represented in training.

**Proposed release gates; none currently satisfied for production.** These are design defaults, not thresholds estimated from the old final test or demonstrated statistical sufficiency. Domain owners must finalize and preregister practical margins and clustered power/precision calculations before issuance.

| Gate | Required evidence |
|---|---|
| Artifact and time provenance | Frozen shadow model reproduced and hashed; 100% of eligible predictions archived before targets; verified units, availability timestamps and genuine claimed lead. |
| Coverage and independence | Planning floors: ≥500 paired district-month cases, ≥50 districts and two complete annual target cycles. Year-round scope also requires ≥25 cases from ≥10 districts in each month, with both annual cycles represented. Use the larger sample required by development-only power analysis; daily source rows are not extra forecast cases. |
| Skill versus both baselines | Proposed primary margin: ≥5% lower pooled RMSE point estimate versus **each** baseline and simultaneous paired 95% intervals excluding no improvement. This does not claim that the intervals establish a full 5% benefit. Upper uncertainty bounds for pooled, district-macro and calendar-macro MAE/RMSE ratios must each be ≤1.05 versus each baseline. Preregister clustered inference over districts and shared contiguous target periods; insufficient temporal replication means no release. |
| Measurement and scope | Complete registered primary panels; all exclusions disclosed; repeated-value and extreme-case patterns adjudicated without outcome-driven deletion. Separate results for registered new geography/aquifer domains; no nationwide claim from a regional pass. |
| Decision discipline | One scheduled confirmatory analysis, no accuracy-driven early stopping, retuning, subgroup switching or family reselection. Failed/uncertain gates mean no promotion; any further confirmation needs a preregistered fresh cohort. Independent operational review is required even after scientific gates pass. |

**Next steps:** first resolve source freshness/datum and issuance feasibility; then preregister sampling and margins, create the frozen shadow artifact in isolation, and collect timestamped panel observations. Neither ML nor seasonal naive is declared production-ready here.

**Verification and files.** `diagnostics.json`, `weighting_metrics.csv`, calendar/district/pattern/case diagnostics and `raw_lineage.json` contain the detailed evidence. The two scripts below only read inputs and write new diagnostic outputs. Their verification modes reconcile metrics and check hashes; they never train or write to the database. Existing model-selection artifacts and production inputs are preserved.

```powershell
# Repository root; recompute and verify saved diagnostics without replacing files.
.\venv\Scripts\python.exe reports/candidates/six_month_diagnostics_20261017/analyze_saved.py --verify-only
.\venv\Scripts\python.exe reports/candidates/six_month_diagnostics_20261017/verify_raw_lineage.py --verify-only
```
