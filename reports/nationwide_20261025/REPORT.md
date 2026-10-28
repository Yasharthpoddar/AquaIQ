# AquaIQ nationwide completion and validation — 2026-10-25

## Coverage and generated output

The registry, feature export and source database were recalculated for this dated generation, not assumed from the old report. Before: **426/725** district forecasts and **299** empty district results; 16/36 states met the old eligible-panel rule. After: **725/725** district results, **8,700/8,700** finite monthly predictions, no missing districts/horizons, and 36/36 state outputs.

| Evidence | Districts | Method |
|---|---:|---|
| A | 547 | Existing climate-conditioned XGBoost |
| B | 104 | Limited-history local persistence |
| C | 73 | Zero-local-history regional/global seasonal reference |
| D | 1 | Missing-environment local persistence (Mumbai Suburban) |

Origin: October 2026; targets **2026-11-01 through 2027-10-01**. Units: absolute depth in metres below ground (`m_bgl`), with changes in separate fields. The generation is published **only in the local test schema `aquaiq_test_nationwide_20261025`**. Public source and production forecast tables were not overwritten. See [generation metadata](generation.json).

## Serving methodology

Readiness denominators begin at the first genuine measurement, retain monitoring gaps through the completed cutoff, and report recency separately. Forecast eligibility follows the existing anchor's actual 24-observation/36-month requirements, not the old 2002-based coverage gate.

Sparse histories do not pass an unsupported anchor fit; persistence and zero-history references are separate methods and versions with honest evidence metadata. All outputs retain genuine observed-month counts, input missingness, dates, fallback reasons, provenance and historical ranges. XGBoost weights and suitable district behavior are unchanged.

Normal API reads use immutable published generations. State summaries aggregate all registered districts with equal weights, tier counts/proportions and per-district methods. No area, well-weighting, volume or representative-state accuracy claim is made. See [methodology and reproducible commands](../../docs/NATIONWIDE_FORECASTS.md).

## Historical backtests

The saved [validation JSON](validation.json) contains results by evidence tier, district, horizon, origin, experiment and genuine observation count. All methods/baselines compare on identical observed targets in their paired sets. Calibration uses 25,356 rows. Evaluation uses **16,705 rows** after purging **6,890** rows whose origins preceded the last calibration target for that tier. Rows across experiments are repeated uses of observed targets, not 16,705 independent measurements.

Fallback calibration origins: January/July 2017–2018; evaluation starts July 2019 and rolls through 2020–2023 plus January 2025. XGBoost calibration origins: January/July 2021, after the frozen 2019 training-label cutoff and twelve-month embargo; evaluation starts July 2022. Every calibration target precedes its tier's first evaluation origin. The evaluation includes actual serving anchors across observation gaps, not only observed origins. Previously computed point predictions were reused to correct the temporal purge and add geographic sensitivity; no prediction refit or test-driven model selection was performed.

| Tier | Cases | Method MAE (m) | Method RMSE (m) | Paired baseline | Baseline MAE (m) | Baseline RMSE (m) | Historical range coverage |
|---|---:|---:|---:|---|---:|---:|---:|
| A | 576 | 2.215 | 4.713 | Persistence | 2.181 | 4.547 | 76.56% |
| B | 5,376 | 2.093 | 3.501 | Persistence | 2.093 | 3.501 | 86.68% |
| C | 5,462 | 3.966 | 7.712 | Global reference | 4.607 | 9.062 | 88.15% |
| D | 5,291 | 2.094 | 3.498 | Persistence | 2.094 | 3.498 | 87.05% |

XGBoost does not beat persistence overall here. B/D are deliberately persistence estimates. Seasonal naive is evaluated on its available paired subset; regional seasonal transfer is a separately reported candidate, not selected on evaluation outcomes. For C, local persistence/seasonal baselines are undefined without local history; global reference is the valid comparison. With the entire target state's histories excluded, the C reference sensitivity has **MAE 4.665 m, RMSE 9.109 m** on the same 5,462 cases. This illustrates transfer risk; it does not confer spatial independence on ordinary within-state or XGBoost results.

Pseudo-sparse experiments retain only the last 1/3/9/23 actual measurements. Pseudo-cold references exclude all target district history, including earlier years, and never use the XGBoost artifact trained on those districts. Tests verify invariance to hidden target/future data. Natural sparse validation has only **seven target cases**; most sparse districts have a lone January 2026 refresh. January 2026 expands horizon-12 evidence but does not establish monthly path accuracy.

Ranges are nominal 90th-percentile historical absolute-error bands, not guaranteed present-day intervals. The table's observed undercoverage is explicit. XGBoost calibration has only 4–7 districts per horizon. Target-region data sparsity, shared donors, changing well panels, unavailable publication times, prior inspection of holdouts and observation gaps limit all results. No superiority or operational readiness claim is made.

## Spatial and environmental findings

The [reproducible spatial audit](spatial_audit.json) found 56,679 Telangana source readings and 2,223 unique named coordinates. The existing strict coordinate/duplicate auditor produced 55,595 accepted candidate readings and 3,222 candidate district-months across 33 districts; 106 negative-depth and 979 unmatched-coordinate rejections can overlap. It does not silently snap ambiguous points. **40,845** accepted readings disagree with the historical parent crosswalk. Boundary dating is mixed, and station identity/coordinate provenance is not independently certified. Candidates remain local and un-ingested; current XGBoost source attribution is not retroactively certified.

The current refresh already gives 23 newer Telangana districts a small amount of genuine history; they are tier B, not zero-history claims copied from old notes. Mumbai Suburban has no distinct supplied polygon. Sixteen of its 18 source coordinates fall within the combined-looking Mumbai polygon, which is insufficient to certify all district attribution. Raw IMD and cleaned ERA5 source-grid probes select the 19°N, 73°E nearest usable cell, about 15.1 km from the polygon's representative point. No unvalidated alias, zero weather or guessed nearest-district assignment is used. Tier D supplies its explicit local reference instead.

## Reproduction and remaining limitations

Source data, verified bundles and a populated feature/database publication remain external prerequisites. Software verification and complete labelled output coverage do not establish forecasting skill or production deployment readiness. A fully updated administrative registry, independently verified station/boundary provenance, hydrogeological transfer features, better calibration and new prospective observations remain scientific limitations.
