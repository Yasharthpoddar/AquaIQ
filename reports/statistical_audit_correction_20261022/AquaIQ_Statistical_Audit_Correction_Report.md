# AquaIQ — Statistical Audit Correction and Final Evidence Review

**Audit Correction Date:** October 22, 2026  
**Auditor:** Senior Software Engineer, ML Auditor & Research Reviewer  
**Repository:** [https://github.com/Yasharthpoddar/AquaIQ](https://github.com/Yasharthpoddar/AquaIQ)  
**Target Branches:** `main` and `experiment/12-month-horizon`  
**Verified Commit Hash:** `090626df28ad6414b355e2b1a4e24a4163693de5`  
**Correction Directory:** `reports/statistical_audit_correction_20261022/`  

---

## 1. Executive Summary & Audit Revisions

This audit report formally supersedes and corrects specific statistical, historical, and methodological claims presented in the earlier audit (`AquaIQ_End_to_End_Audit_Report.md`). While the engineering implementation, test suites (1,164 Python tests passing, 57 Vitest frontend tests passing), and protected cryptographic artifact digests remain pristine and fully validated, three critical areas required substantial statistical and evidence corrections:

1. **Correction of the District-Block Bootstrap**: The previous reported bootstrap interval of $\Delta \text{RMSE} \in [-0.2203, +0.1409]\text{ m}$ was calculated using **independent (unpaired)** cluster draws for XGBoost and the annual persistence baseline. This violated the statistical requirement of paired evaluation, artificially inflating standard error by ~2× ($\text{SE} \approx 0.0918\text{ m}$). The corrected **paired cluster bootstrap** reduces standard error to **$0.0454\text{ m}$** and establishes the true 95% Confidence Interval as **$[-0.1209, +0.0555]\text{ m}$**.
2. **Scientific Conclusion Unchanged**: Despite narrowing the confidence interval by half, the upper bound remains strictly positive ($+0.0555\text{ m} > 0$), and in **20.47%** of bootstrap replicates the simple annual baseline equals or outperforms the ML model. With a two-sided empirical p-value of **$p = 0.4094$**, **XGBoost does NOT demonstrate statistically significant predictive superiority over annual persistence.**
3. **Correction of District-Count Discrepancy**: The earlier audit dismissed the historical 807 figure as an "arithmetic typo in Safe count (380 vs 300) where $380 + 365 + 50 + 6 + 4 = 805 \approx 807$." This was erroneous. The historical report displayed Safe=380, Watch=365, Warning=56, Crisis=6, which sums **exactly** to $380 + 365 + 56 + 6 = 807$. The historical figure differed across three distinct tiers (+80 Safe, +6 Warning, -4 Unknown; net difference +82) and originated from an uncurated pre-deduplication snapshot before migration `001_canonical_districts.sql` mapped 1,291 legacy rows to the 725 canonical Census/GeoJSON boundaries.
4. **Scoping of Target Leakage Findings**: The previous audit's sweeping conclusion of "zero pipeline leakage" was unsupported by its narrow test of 24 TS-Adilabad rows. We have now rigorously defined the exact verified boundaries: feature lag alignment ($\tau-3$, $\tau-6$, 3-month trailing rainfall) and temporal training separation buffers (12–24 months) are verified leak-free, whereas upstream raw NetCDF grid spatial extractions and multi-decade climatology baselines remain outside the certified scope.

---

## 2. Paired District-Cluster Bootstrap: Flaw Diagnosis & Correction

### 2.1 Diagnosis of the Flawed Bootstrap (`task-165` / Step 164)
The earlier audit report documented:
$$\Delta \text{RMSE} = -0.0378\text{ m}, \quad 95\% \text{ CI} = [-0.2203, +0.1409]\text{ m}$$
Inspection of the execution log in `transcript_full.jsonl` (step 164) reveals the exact command that was executed:

```python
# FLAWED IMPLEMENTATION (Step 164):
diffs = [
    np.sqrt(np.mean(sq_xgb[np.concatenate([np.where(districts == d)[0] for d in rng.choice(unique_d, size=len(unique_d), replace=True)])]))
    - np.sqrt(np.mean(sq_base[np.concatenate([np.where(districts == d)[0] for d in rng.choice(unique_d, size=len(unique_d), replace=True)])]))
    for _ in range(10000)
]
```

**The Flaw**:
Inside each iteration of the list comprehension, `rng.choice(unique_d, size=len(unique_d), replace=True)` was invoked **twice independently**: once for `sq_xgb` and once for `sq_base`. 
- In replicate $b$, XGBoost was evaluated on one random combination of districts (e.g. Adilabad, Nizamabad, Karimnagar...), while the annual baseline was evaluated on an entirely different combination of districts (e.g. Warangal, Khammam, Nalgonda...).
- Because hydrologic depth and variance vary significantly across districts, this independent resampling injected massive artificial inter-cluster noise into the paired difference.
- This resulted in an artificially inflated standard error of **$0.0918\text{ m}$**, yielding the excessively wide interval $[-0.2203, +0.1409]\text{ m}$.

### 2.2 Corrected Paired Cluster Implementation
In a valid paired cluster bootstrap, both candidate models must be evaluated on the **exact same resampled clusters** in every replicate $b$:
1. Draw a single bootstrap sample of district clusters: $D^{*(b)} = (d_1^*, \dots, d_K^*)$ with replacement from the $K=33$ unique districts.
2. If district $d$ is selected $m$ times in $D^{*(b)}$, include all 24 eligible monthly observations for district $d$ exactly $m$ times in both the XGBoost evaluation set and the baseline evaluation set.
3. Compute the replicate metrics on this identical resampled panel:
   $$\text{RMSE}_{\text{XGB}}^{*(b)} = \sqrt{\frac{1}{N} \sum_{i \in \text{resample}} (\hat{y}_{\text{xgb}, i} - y_i)^2}, \quad \text{RMSE}_{\text{base}}^{*(b)} = \sqrt{\frac{1}{N} \sum_{i \in \text{resample}} (\hat{y}_{\text{base}, i} - y_i)^2}$$
   $$\Delta \text{RMSE}^{*(b)} = \text{RMSE}_{\text{XGB}}^{*(b)} - \text{RMSE}_{\text{base}}^{*(b)}$$
4. Similarly compute $\Delta \text{MAE}^{*(b)} = \text{MAE}_{\text{XGB}}^{*(b)} - \text{MAE}_{\text{base}}^{*(b)}$.

### 2.3 Reproducible Verification Command
The standalone script is located at `reports/statistical_audit_correction_20261022/audit_correction_analysis.py`.
Execution command:
```powershell
.\venv\Scripts\python.exe reports\statistical_audit_correction_20261022\audit_correction_analysis.py
```

---

## 3. Empirical Results: 792-Case Primary Evaluation (33 Districts)

### 3.1 Dataset Verification
- **Source File**: `reports/candidates/twelve_month_horizon_20261020/evaluation/full_coordinate_predictions.csv`
- **Subset**: `period == 'primary'`
- **Rows**: Exactly 792 rows across 33 Telangana districts.
- **Balance**: Exactly 24 origin months per district (2023-01-01 to 2024-12-01 targeting 2024-01-01 to 2025-12-01).
- **Data Integrity**: Zero duplicate tuples on `[district_id, date, target_date]`, zero duplicate `case_id`, zero missing values in `actual`, `xgb_expanding`, or `annual_seasonal_naive`.

### 3.2 Point Estimates and Metric Reproduction
The primary period evaluations reproduce with 100% precision:

| Model / Approach | MAE (m) | RMSE (m) | $R^2$ | Mean Bias (m) |
|---|---|---|---|---|
| **Annual Seasonal Naive (Persistence)** | **1.1911** | **1.4577** | **0.7215** | **-0.2424** |
| **XGBoost (expanding window)** | **1.1591** | **1.4199** | **0.7357** | **+0.4566** |
| **Linear Regression (expanding)** | 1.9280 | 2.4556 | 0.2096 | +1.5121 |
| **HistGradientBoosting (fixed 12m)** | 1.2222 | 1.5055 | 0.7029 | +0.4938 |

**Point Differences ($\Delta = \text{Model} - \text{Baseline}$)**:
- **$\Delta \text{RMSE}$ Point Estimate**: $1.419908 - 1.457723 = \mathbf{-0.037815\text{ m}}$ ($-3.78\text{ cm}$)
- **$\Delta \text{MAE}$ Point Estimate**: $1.159119 - 1.191079 = \mathbf{-0.031960\text{ m}}$ ($-3.20\text{ cm}$)
*(Direction: Negative favors XGBoost; Positive favors Annual Baseline)*

### 3.3 Bootstrap Uncertainty & Hypothesis Testing (10,000 Iterations)

```
+----------------------------------------------------------------------------------------------------------+
|                                  BOOTSTRAP COMPARISON: UNPAIRED VS PAIRED                                 |
+--------------------------+------------------------------+------------------------------+-----------------+
| Statistic                | Flawed Unpaired Bootstrap    | Corrected Paired Bootstrap   | Change          |
+--------------------------+------------------------------+------------------------------+-----------------+
| Resampling Method        | Independent District Draws   | Paired Identical Clusters    | Validated       |
| Point Estimate           | -0.0378 m                    | -0.0378 m                    | Exact Match     |
| Bootstrap Mean           | -0.0381 m                    | -0.0371 m                    | Minimal Bias    |
| Standard Error (SE)      | 0.0918 m                     | 0.0454 m                     | 50.5% Reduction |
| 95% CI (Percentile)      | [-0.2203, +0.1409] m         | [-0.1209, +0.0555] m         | Much Tighter    |
| 95% CI (Normal Approx)   | [-0.2178, +0.1421] m         | [-0.1269, +0.0513] m         | Consistent      |
| Fraction Replicates >= 0 | 0.3392                       | 0.2047                       | 20.5% >= 0      |
| Two-Sided p-value        | 0.6784                       | 0.4094                       | p >> 0.05       |
| Reject H0 (Delta = 0)?   | NO                           | NO                           | NO              |
+--------------------------+------------------------------+------------------------------+-----------------+
```

**Corresponding MAE Bootstrap Statistics**:
- **Bootstrap Mean $\Delta \text{MAE}$**: $-0.0317\text{ m}$
- **Standard Error**: $0.0452\text{ m}$
- **Corrected 95% CI (Percentile)**: **$[-0.1147, +0.0613]\text{ m}$**
- **Fraction $\ge 0$**: $0.2368$
- **Two-Sided p-value**: $p = 0.4736$

### 3.4 Seed Sensitivity Analysis (10,000 Iterations Each)
- **Seed 42**: $95\% \text{ CI} = [-0.1209, +0.0555]\text{ m}$, Mean = $-0.0371\text{ m}$, Fraction $\ge 0 = 0.2047$
- **Seed 2026**: $95\% \text{ CI} = [-0.1221, +0.0548]\text{ m}$, Mean = $-0.0363\text{ m}$, Fraction $\ge 0 = 0.2094$
- **Seed 12345**: $95\% \text{ CI} = [-0.1213, +0.0560]\text{ m}$, Mean = $-0.0369\text{ m}$, Fraction $\ge 0 = 0.2017$
- **Seed 99999**: $95\% \text{ CI} = [-0.1227, +0.0543]\text{ m}$, Mean = $-0.0374\text{ m}$, Fraction $\ge 0 = 0.2014$

### 3.5 District-Level Paired Parametric & Non-Parametric Tests
To corroborate the cluster bootstrap without distribution assumptions:
- XGBoost achieved lower RMSE in **20 of 33 districts** (60.6%).
- The annual baseline achieved lower RMSE in **13 of 33 districts** (39.4%).
- District-level mean $\Delta \text{RMSE}$: $-0.0206\text{ m}$; median: $-0.0282\text{ m}$.
- **Paired Student's t-test**: $t(32) = -0.4235, \quad p = \mathbf{0.6747}$
- **Wilcoxon Signed-Rank Test**: $W = 218.0, \quad p = \mathbf{0.2719}$

### 3.6 Definitive Statistical Interpretation
**Does XGBoost provide a statistically significant improvement over annual persistence under cluster-aware resampling?**

**CONCLUSION: NO.**
While correcting the cluster bootstrap eliminates artificial inter-district variance and contracts the confidence interval from $0.361\text{ m}$ to $0.176\text{ m}$ wide, **the interval $[-0.1209, +0.0555]\text{ m}$ still decisively crosses zero**. 
In more than one out of every five resamples ($20.47\%$), the simple annual seasonal persistence baseline performs equal to or better than the expanding gradient-boosted tree model. With $p = 0.4094$, the empirical null hypothesis cannot be rejected. AquaIQ's 12-month direct ML model cannot be claimed to outperform a naive seasonal persistence baseline.

---

## 4. Re-examination of District-Count Discrepancy

### 4.1 Historical vs Current District Count Breakdown

```
+-----------------------------------------------------------------------------------------------+
|                               DISTRICT CLASSIFICATION RECONCILIATION                          |
+---------------+------------------------+-----------------------+-------------+----------------+
| Risk Tier     | Historical Displayed   | Current Operational   | Difference  | Verification   |
+---------------+------------------------+-----------------------+-------------+----------------+
| Safe          | 380                    | 300                   | +80         | Reconciled     |
| Watch         | 365                    | 365                   | 0           | Exact Match    |
| Warning       | 56                     | 50                    | +6          | Reconciled     |
| Crisis        | 6                      | 6                     | 0           | Exact Match    |
| Unknown       | 0 (not tracked)        | 4                     | -4          | Reconciled     |
+---------------+------------------------+-----------------------+-------------+----------------+
| TOTAL         | 807                    | 725                   | +82         | 100% Accounted |
+---------------+------------------------+-----------------------+-------------+----------------+
```

### 4.2 Rebuttal of the "Single Typo" Hypothesis
The previous audit report stated:
> *"The historical document had an arithmetic typo listing Safe as 380 instead of 300 (380 + 365 + 50 + 6 + 4 = 805 ≈ 807)."*

This explanation was mathematically false:
1. $380 + 365 + 50 + 6 + 4$ equals **805**, not 807.
2. In the historical documentation, the categories were Safe=380, Watch=365, Warning=56, and Crisis=6.
3. The sum is **exact**:
   $$380 + 365 + 56 + 6 = \mathbf{807}$$
4. The discrepancy was not a simple clerical addition error on a single tier; it was an entirely different classification distribution:
   - Safe had 80 additional districts (380 vs 300)
   - Warning had 6 additional districts (56 vs 50)
   - Unknown (insufficient data) was omitted (0 vs 4)
   - Algebraic net difference: $+80 + 6 - 4 = \mathbf{+82}$ ($807 - 725 = 82$).

### 4.3 Provenance and Ground Truth
The 807 count reflects an early, pre-deduplication prototype snapshot when raw station-level district strings from CGWB PDFs were aggregated prior to geographic standardization. 

In migration `001_canonical_districts.sql` (commit `626f21d`), AquaIQ formally crosswalked 1,291 raw district aliases in `data_ingestion/district_crosswalk.csv` to exactly **725 canonical Census/GeoJSON districts**. 

The live database and API endpoint (`http://localhost:5000/api/scores`) reconcile with 100% precision:
- **Total Registered Districts**: 725
- **Tier Breakdown**: $\text{Safe}(300) + \text{Watch}(365) + \text{Warning}(50) + \text{Crisis}(6) + \text{Unknown}(4) = \mathbf{725}$
- **Estimate Methodology**: $\text{district\_level}(427) + \text{zone\_fallback}(294) + \text{insufficient\_data}(4) = \mathbf{725}$

---

## 5. Precisely Scoped Data Leakage Audit

The earlier audit's claim of "zero target leakage across the entire pipeline" was over-broad and ungrounded. We have re-audited the feature generation and model evaluation pipelines to explicitly delineate what has been proven versus what remains unverified.

```
+--------------------------------------------------------------------------------------------------------------+
|                                      DATA LEAKAGE AUDIT BOUNDARY MATRIX                                      |
+------------------------------------+--------------------------+-----------------------+----------------------+
| Pipeline Layer                     | Audit Mechanism          | Evidence Status       | Certified Scope      |
+------------------------------------+--------------------------+-----------------------+----------------------+
| Evaluation Feature Alignment       | Vector match across 792  | Zero overlap (0/792)  | Confirmed Leak-Free  |
| 3-Month GWL Lag (gwl_lag_3mo)      | Time-shift comparison    | Exactly y(t-3)        | Confirmed Causal     |
| 6-Month GWL Lag (gwl_lag_6mo)      | Time-shift comparison    | Exactly y(t-6)        | Confirmed Causal     |
| 3-Month Trailing Rainfall          | Rolling mean shift check | Exactly mean(t-2..t)  | Confirmed Causal     |
| Expanding Train/Test Separation    | Cutoff dates vs targets  | 12-24 mo buffer       | Confirmed Separated  |
| Raw NetCDF Spatial Polygon Masking | Code/Raster extraction   | Not audited           | OUT OF SCOPE         |
| Panel-Wide Climatology Baselines   | 2002-2025 norm formulas  | Multi-decade pooled   | QUALIFIED / LIMIT    |
| Imputation Lookahead               | Forward-fill bounded <=3m| Intra-district causal | Qualified Causal     |
+------------------------------------+--------------------------+-----------------------+----------------------+
```

### 5.1 Certified Leak-Free Components
1. **Target Contamination**: In all 792 primary cases and 24 TS-Adilabad prototype cases, `gwl_current` strictly reflects the ground-truth water table depth at forecast origin $t$. The correlation between `gwl_current` and evaluation target $y_{t+12}$ is zero contemporaneous overlap ($0 / 792$).
2. **Lag Construction**: Ground-truth water table depth lags `gwl_lag_3mo` and `gwl_lag_6mo` match exact historical observations at $t-3$ and $t-6$ months. The feature `rainfall_3mo_avg` is strictly a trailing backward rolling mean over $[t-2, t-1, t]$.
3. **Temporal Partitioning**: In the expanding evaluation, models targeting 2024 were restricted to `train_target_cutoff = 2021-12-31` (12-month pre-origin buffer; 24-month pre-target buffer). Models targeting 2025 used `train_target_cutoff = 2022-12-31`.

### 5.2 Methodological Qualifications and Exclusions
1. **Climatology Baseline Normalization**: Features such as `monsoon_deficit_pct` and evapotranspiration anomalies compute seasonal norms across the full multi-decade historical record (2002–2025). While common in hydrogeology, this constitutes mild transductive leakage of long-term climate statistics into early training folds.
2. **Upstream Gridded Aggregations**: The spatial raster extraction from raw IMD NetCDF grids (`data_ingestion/imd_district_climatology.py`) was not audited with pixel-level coordinate geometry checks.
3. **Forward-Fill Imputation**: Missing GWL values are carried forward up to 3 months (`is_imputed=True`). While forward-fill is strictly causal and cannot leak future measurements, it induces artificial autocorrelation during extended well observation blackouts.

---

## 6. Synthesis: Confirmed, Corrected, and Unresolved Audit Findings

```
+--------------------------------------------------------------------------------------------------------------+
|                                          COMPREHENSIVE AUDIT STATUS TABLE                                    |
+---------------------+-------------------+---------------------+-----------------------+----------------------+
| Finding Item        | Earlier Audit     | Corrected Status    | Empirical Evidence    | Audit Verdict        |
+---------------------+-------------------+---------------------+-----------------------+----------------------+
| 12m Bootstrap CI    | [-0.220, +0.141]  | [-0.121, +0.055] m  | Paired cluster sample | CORRECTED (Flaw fix) |
| Statistical Skill   | Insignificant     | Insignificant       | p=0.4094; 20.5% >= 0  | RECONFIRMED (No Sig) |
| 792-Case Metrics    | MAE 1.159 / 1.191 | MAE 1.159 / 1.191   | 100% exact match      | RECONFIRMED          |
| 24-Case Adilabad    | ML 3x worse       | ML 3x worse         | RMSE 2.664 vs 0.877 m | RECONFIRMED          |
| District Counts     | "Safe typo (805)" | Multi-tier (+82 net)| 380+365+56+6 = 807    | CORRECTED            |
| Live System Total   | 725 Districts     | 725 Districts       | DB/API match 100%     | RECONFIRMED          |
| Target Leakage      | "Zero in pipeline"| Scoped feature lags | Lags causal; raw NetCDF| CORRECTED & SCOPED  |
| Python Test Suite   | 1164 pass / 14 skp| 1164 pass / 14 skp  | Exit code 0           | RECONFIRMED          |
| Frontend Vitest     | 57 pass / 0 fail  | 57 pass / 0 fail    | Exit code 0           | RECONFIRMED          |
| Artifact Hashes     | 5/5 SHA256 match  | 5/5 SHA256 match    | Exact digest equality | RECONFIRMED          |
| Git Branch Parity   | main == experiment| main == experiment  | Zero git diff         | RECONFIRMED          |
| Ensemble Weights    | Uncalibrated      | Uncalibrated        | Flag in config.yaml   | RECONFIRMED          |
+---------------------+-------------------+---------------------+-----------------------+----------------------+
```

---

## 7. Remaining Research & Operational Limitations

1. **Hydrogeological Domain Challenge (The "Persistence Barrier")**: In monsoonal hydrologic systems, groundwater exhibits strong annual periodicity driven by seasonal recharge. At a 12-month forecast horizon ($M+12$), the target month falls in the exact same calendar season as origin month $M$. As a result, the naive persistence baseline $\hat{y}_{t+12} = y_t$ accounts for the seasonal cycle with zero estimated parameters. Machine learning models attempting to predict absolute groundwater depth directly must learn both the seasonal baseline and climate anomalies simultaneously, frequently introducing variance that cancels out any theoretical modeling gain.
2. **Spatial Feature Generalization**: The research artifact `xgb_fixed_2021.json` deployed to the prototype UI fails severely on `TS-Adilabad` (RMSE 2.664 m vs 0.877 m for baseline) because local hydrogeology (e.g. Deccan basalt vs alluvial aquifers) cannot be captured by simple regional models without localized calibration.
3. **Operational Readiness**: The operational crisis scoring ensemble remains explicitly marked `initial_uncalibrated` in `config.yaml`. The system cannot be used for agricultural or municipal drought allocations until prospective out-of-sample ground validation is conducted.

---

## 8. Final Audit Sign-Off

- **Previous Confidence Interval**: Formally designated **INVALID** due to unpaired cluster resampling.
- **Corrected Confidence Interval**: Certified as **$[-0.1209, +0.0555]\text{ m}$** under 10,000 paired cluster replicates ($p = 0.4094$).
- **Core ML Verdict**: **RECONFIRMED**. The 12-month XGBoost model does not provide statistically significant predictive skill over simple annual persistence.
- **Code & Test Integrity**: **CONFIRMED EXCELLENT**. Zero broken tests, zero regressions, full cryptographic preservation.
