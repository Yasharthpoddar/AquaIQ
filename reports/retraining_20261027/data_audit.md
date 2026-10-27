# Enriched retraining data audit

Verified `physical-v3-official-c9ade81d95720f91`, CSV SHA-256 `3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042`.

The complete matrix has 215,325 rows across 725 districts, 2002-01-01–2026-09-01. It contains 43,384 observed, 85,816 imputed and 86,125 missing groundwater rows. 57 districts have no local observations.

Duplicate identifiers/months, unknown flags, nonfinite or negative observed depths, conflicting observation/imputation flags, causal carry and calendar-lag checks passed. The recursive accepted-source chain and frozen reference model bytes also passed.

Against baseline: +6,494 measured months across 653 districts, 16 newly local districts, zero removed observations and zero changed existing measured values.
Against parent: +542 measured months across 542 districts, 5 newly local districts, zero removed observations and zero changed existing measured values.

## Observation support

| Year | Observed months |
| --- | ---: |
| 2002 | 1,637 |
| 2003 | 1,642 |
| 2004 | 1,557 |
| 2005 | 1,669 |
| 2006 | 1,711 |
| 2007 | 1,707 |
| 2008 | 1,693 |
| 2009 | 1,709 |
| 2010 | 1,699 |
| 2011 | 1,696 |
| 2012 | 1,286 |
| 2013 | 2,334 |
| 2014 | 2,302 |
| 2015 | 2,391 |
| 2016 | 2,291 |
| 2017 | 2,319 |
| 2018 | 2,229 |
| 2019 | 2,265 |
| 2020 | 1,463 |
| 2021 | 1,898 |
| 2022 | 2,505 |
| 2023 | 1,632 |
| 2024 | 539 |
| 2025 | 571 |
| 2026 | 639 |

Only January has accepted measurements in 2025 (571 districts). January 2026 has 639 measurements; those targets were already inspected. There are no accepted later targets or observed-origin/future-target pairs strictly after January 2025. The September 2026 matrix end is not evidence of September 2026 labels.

## Feature and outlier review

| Feature | Missing rows | Missing on observed rows |
| --- | ---: | ---: |
| GWL_current | 86,125 | 0 |
| GWL_lag_3mo | 86,125 | 4,159 |
| GWL_lag_6mo | 86,764 | 5,506 |
| rainfall_current | 5,365 | 70 |
| rainfall_3mo_avg | 3,917 | 70 |
| monsoon_deficit_pct | 5,744 | 70 |
| temperature | 14,053 | 709 |
| evapotranspiration | 14,053 | 709 |
| water_balance_proxy | 14,053 | 709 |
| crop_season_flag | 0 | 0 |

Flag for source review: GJ-Gandhinagar, 2020-11-01, 106.156 m_bgl. It remains unchanged; no clipping is applied.
Flag for source review: GJ-Gandhinagar, 2021-01-01, 102.51 m_bgl. It remains unchanged; no clipping is applied.

## Retraining and evaluation limits

Calendar joins provide an upper bound of 164,323 training pairs through January 2025, including 20,720 pairs with added targets. 6,165 added months enter a pair role, while 329 cannot form such a pair. These counts precede weather eligibility and must not be reported as final fitted sample counts.

The production objective is depth change from origin across horizons 1–12. Both endpoints must be observed. The current encoder uses origin-available climatology, while the frozen card records realized historical conditional weather. All missing predictors must retain their existing semantics; no learned global imputation is licensed by this audit.

Use earlier chronological folds for selection, then an explicitly labelled final fit that actually includes eligible January 2025 labels. The existing train interface requires later independent heldout origins and cannot manufacture these from the matrix. Previously inspected January 2026 errors are retrospective diagnostics, not a new blind test. No model promotion or scientific accuracy result follows from this data audit.

Suggested checks: exact source-value inclusion; observed-only pair joins; training targets before validation origins; origin truncation/future-label perturbation invariance; unchanged feature ordering and units; reproducible fit bytes/predictions; matched baseline case populations; new-model uncertainty unavailable until separately validated.

No database was accessed and no source data, feature export or model artifact was written. The JSON companion contains full month counts, missingness, provenance hashes and pair-count qualifications.
