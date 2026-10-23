# AquaIQ — Final Research Readiness, Statistical Robustness, and Publication Audit Report

**Audit Date:** October 22, 2026  
**Auditor Profile:** Senior Machine-Learning Researcher, Applied Statistician, Groundwater Domain Reviewer, and Software Quality Auditor  
**Repository:** [https://github.com/Yasharthpoddar/AquaIQ](https://github.com/Yasharthpoddar/AquaIQ)  
**Target Commit Hash:** `090626df28ad6414b355e2b1a4e24a4163693de5`  
**Audit Directory:** `reports/final_research_readiness_20261022_audit/`  
**Associated Artifacts:**
- Execution Script: [`reproducible_checks.py`](file:///c:/Users/Yasharth/Downloads/AquaIQ/reports/final_research_readiness_20261022_audit/reproducible_checks.py)
- Numerical Manifest: [`results.json`](file:///c:/Users/Yasharth/Downloads/AquaIQ/reports/final_research_readiness_20261022_audit/results.json)
- Execution Log: [`execution.log`](file:///c:/Users/Yasharth/Downloads/AquaIQ/reports/final_research_readiness_20261022_audit/execution.log)

---

## Executive Verdict

### **Verdict: A. Suitable for academic benchmarking with qualifications**
*(With the strict caveat that the operational software and risk-scoring subsystem remain **B. Suitable only as an engineering prototype pending prospective ground validation**).*

### Summary of Verdict Rationale:
1. **Academic Benchmarking Value (PASS with Qualifications):** The 792-case retrospective 12-month expanding evaluation panel across 33 Telangana districts provides a reproducible, leak-free empirical comparison between direct gradient-boosted trees and annual seasonal persistence. The code, test suites (1,164 Python tests passing, 57 frontend tests passing, 0 linter errors), data schemas, and cryptographic artifact digests are preserved with pristine engineering rigor.
2. **Predictive Superiority (FAIL):** The headline point estimate of $\Delta\text{RMSE} = -0.0378\text{ m}$ ($-3.78\text{ cm}$, a $2.59\%$ nominal reduction in error) is **not statistically significant** under any defensible inferential procedure. The 95% paired district-cluster bootstrap confidence interval is $[-0.1209, +0.0555]\text{ m}$, straddling zero.
3. **Severe Temporal Dependence (WARNING):** The 792 evaluation rows span only 24 consecutive calendar months (target years 2024 and 2025). The evaluation exhibits massive annual regime reversal: in 2024, XGBoost outperformed the baseline by $29.3\text{ cm}$ ($\Delta\text{RMSE} = -0.2926\text{ m}$), whereas in 2025, the annual persistence baseline outperformed XGBoost by $23.5\text{ cm}$ ($\Delta\text{RMSE} = +0.2350\text{ m}$). Under temporal block resampling that accounts for shared annual monsoonal shocks, standard error triples from $0.0454\text{ m}$ to $0.1520\text{ m}$, widening the 95% uncertainty interval to $[-0.3289, +0.2520]\text{ m}$. The effective temporal degrees of freedom are $T_{\text{years}} \approx 2$.
4. **Operational Readiness (NO-GO / Prototype Only):** The operational crisis risk scores rely on `initial_uncalibrated` component weights built on a legacy 6-month horizon basis, the fixed 24-case Adilabad research artifact underperforms the annual baseline by over 3× (RMSE 2.664 m vs 0.877 m), and the experimental monthly scenario is an unvalidated dampened seasonal-trend extrapolation lacking weather inputs.

---

## 1. Dataset Integrity and Exact Evaluation Population

The evaluation dataset was audited directly at row level against [`reports/candidates/twelve_month_horizon_20261020/evaluation/full_coordinate_predictions.csv`](file:///c:/Users/Yasharth/Downloads/AquaIQ/reports/candidates/twelve_month_horizon_20261020/evaluation/full_coordinate_predictions.csv).

### 1.1 Dataset Composition & Balance
- **Total Records:** 957 rows.
- **Primary Research Subset (`period == 'primary'`):** Exactly **792 rows**.
- **Secondary Subset (`period == 'secondary'`):** 165 rows (origins Jan–May 2025 targeting Jan–May 2026). 66 rows have complete carried weather inputs; 99 rows (March–May 2025) lack weather inputs and are excluded from the common primary benchmark.
- **Geographic Coverage:** Exactly 33 unique Telangana districts.
- **Panel Balance:** Perfectly balanced panel. Exactly 24 observations per district (24 origin months $\times$ 33 districts = 792 rows).
- **Origin Date Range:** `2023-01-01` to `2024-12-01` (24 contiguous monthly issues).
- **Target Date Range:** `2024-01-01` to `2025-12-01` (24 contiguous target months).
- **Forecast Horizon:** Exactly 12 calendar months for every single row (`horizon_months == 12`).
- **Identifier Uniqueness:** 
  - `case_id` is unique across all 792 rows (0 duplicates).
  - Tuples `[district_id, date, target_date]` are unique (0 duplicates).
- **Evaluation Commonality:** All competing methods (Annual Persistence, Expanding XGBoost, Expanding Linear Regression, Fixed 12m HistGradientBoosting) are evaluated on the exact same 792 cases with identical ground truth observations (`actual == target_value`).

### 1.2 Training Partitions and Model Provenance
- **Model Refits:** The expanding models (`xgb_expanding`, `linear_expanding`, `hgb_12month_fixed`) were refitted annually using temporal embargo buffers:
  - **Target Year 2024** (origins 2023-01-01 to 2023-12-01): `train_target_cutoff = 2021-12-31`. Model SHA-256: `faee0ff0c2b6baa59acb1c0b68618b605b1b68d66f23ccd49bdc53f0cd71175c`. Embargo buffer: 12 months between training cutoff and earliest origin; 24 months between cutoff and earliest target.
  - **Target Year 2025** (origins 2024-01-01 to 2024-12-01): `train_target_cutoff = 2022-12-31`. Model SHA-256: `5b5a4ee629262450fe9eea483ce988d18b743937864ee6bc0c24b422976a6afc`. Embargo buffer: 12 months between training cutoff and earliest origin.
- **Fixed Artifact (Study B):** `xgb_fixed_2021.json` is a separate, single fixed model trained on TS-Adilabad data up to `2021-12-31` and evaluated over 24 historical months without retraining.

### 1.3 Dataset Integrity Verification Table

| Verification Check | Target / Expected Specification | Observed Value | Verification Procedure | Audit Outcome |
|:---|:---|:---|:---|:---:|
| Primary Population Count | Exactly 792 rows | 792 rows | Filter `period == 'primary'` on CSV | **PASS** |
| District Count | 33 Telangana districts | 33 unique `district_id` | `nunique()` aggregation | **PASS** |
| Panel Balance | 24 observations per district | Exactly 24 (min=24, max=24) | `groupby('district_id').size()` | **PASS** |
| Temporal Horizon | Exact calendar M+12 | 12 months (all 792) | Inspect `horizon_months` | **PASS** |
| Origin Temporal Span | 2023-01-01 to 2024-12-01 | 2023-01-01 to 2024-12-01 | `min()`, `max()` on `date` | **PASS** |
| Target Temporal Span | 2024-01-01 to 2025-12-01 | 2024-01-01 to 2025-12-01 | `min()`, `max()` on `target_date` | **PASS** |
| Identifier Uniqueness | Zero duplicate keys | 0 duplicate `case_id`, 0 duplicate tuples | `duplicated().sum()` on key subsets | **PASS** |
| Data Completeness | Zero NaNs in evaluation variables | 0 NaNs across all 5 models & actuals | `isna().sum()` on prediction columns | **PASS** |
| Evaluation Pairing | Identical rows across all methods | 100% paired (792/792) | Column-wise row alignment | **PASS** |
| Baseline Identity | Persistence == Annual Seasonal Naive | Exact equality ($\Delta = 0.000000$) | Vector difference check | **PASS** |
| Geographic Identification | Confirmed administrative boundaries | 100% of target panels contain name/polygon conflicts | Audit of `target_panel_quality.csv` | **WARNING** |

---

## 2. Reproduced Headline Metrics

All metrics were independently calculated using standard definitions:
- $\text{MAE} = \frac{1}{N} \sum_{i=1}^N |y_i - \hat{y}_i|$
- $\text{RMSE} = \sqrt{\frac{1}{N} \sum_{i=1}^N (y_i - \hat{y}_i)^2}$
- $\text{Bias} = \frac{1}{N} \sum_{i=1}^N (\hat{y}_i - y_i)$ (Positive = model overpredicts depth / dry conditions; Negative = model underpredicts depth)
- $R^2 = 1 - \frac{\sum (y_i - \hat{y}_i)^2}{\sum (y_i - \bar{y})^2}$

### 2.1 Study A: 792-Case Expanding Evaluation (33 Districts)

| Model / Baseline | MAE (m) | RMSE (m) | Bias (m) | $R^2$ | Status |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Annual Seasonal Naive (Persistence)** | **1.191079** | **1.457723** | **-0.242431** | **0.721470** | Benchmark |
| **XGBoost (expanding window)** | **1.159119** | **1.419908** | **+0.456614** | **0.735733** | Evaluated |
| **Linear Regression (expanding)** | 1.927979 | 2.455646 | +1.512082 | 0.209587 | Comparator |
| **HistGradientBoosting (fixed 12m)** | 1.222151 | 1.505470 | +0.493834 | 0.702924 | Comparator |

#### Point Differences (XGBoost − Annual Baseline):
- **$\Delta\text{RMSE}$:** $1.419908 - 1.457723 = \mathbf{-0.037815\text{ m}}\quad (-3.78\text{ cm})$
- **$\Delta\text{MAE}$:** $1.159119 - 1.191079 = \mathbf{-0.031960\text{ m}}\quad (-3.20\text{ cm})$
- **Relative RMSE Change:** $\frac{-0.037815}{1.457723} \times 100 = \mathbf{-2.59\%}$
- **Measurement Convention:** All measurements are in metres below ground level ($\text{m bgl}$).
- **Audit Finding:** The reported values reproduce to 6 decimal places. Small differences in earlier summaries are completely explained by rounding to 3 decimal places ($1.420 - 1.458 = -0.038\text{ m}$).
- **Characterization:** The 2.59% relative reduction in RMSE is strictly a sample point-estimate difference, **not an established predictive superiority**.

### 2.2 Study B: 24-Case Fixed TS-Adilabad Artifact

Evaluated on [`reports/candidates/twelve_month_horizon_finalization_20261020/artifact/historical_checks.csv`](file:///c:/Users/Yasharth/Downloads/AquaIQ/reports/candidates/twelve_month_horizon_finalization_20261020/artifact/historical_checks.csv):

| Model / Method | MAE (m) | RMSE (m) | Bias (m) | $R^2$ | Status |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Annual Baseline** | **0.645164** | **0.876996** | **+0.066662** | **0.880638** | Benchmark |
| **Fixed 2021 XGBoost (`xgb_fixed_2021.json`)** | **2.144770** | **2.664045** | **+2.052587** | **-0.101423** | Prototype ML |
| **Point Difference ($\Delta = \text{ML} - \text{Base}$)** | **+1.499606** | **+1.787050** | **+1.985925** | **-0.982061** | **ML Underperforms** |

#### Critical Finding for Study B:
The fixed XGBoost artifact performs **over 3 times worse** than the annual baseline on its own historical checks (RMSE 2.664 m vs 0.877 m, with a massive positive bias of $+2.05\text{ m}$). This failure demonstrates that frozen regional gradient boosting without localized calibration or annual retraining cannot track local hydrogeological shifts in Deccan hard-rock aquifers. This 24-case single-district result must remain completely isolated from Study A.

---

## 3. Annual Persistence Baseline Audit

### 3.1 Mathematical Definition & Alignment
At a forecast horizon of $H = 12$ calendar months, target month $T = M + 12$. The annual seasonal naive baseline is defined as:
$$\hat{y}_{M+12} = y_M$$
Because origin month $M$ and target month $M+12$ share the exact same calendar month (e.g., January 2023 predicting January 2024), **annual seasonal persistence and origin persistence are mathematically identical**. This was verified with 100% precision across all 792 rows ($\max |y_{\text{persistence}} - y_{\text{annual\_seasonal\_naive}}| = 0.000000$).

### 3.2 Why the Annual Baseline is Formidable at 12 Months
In monsoonal hydrogeological regimes like Telangana:
1. **Dominant Seasonality:** Groundwater recharge and extraction follow an annual cycle driven by the Southwest Monsoon (June–September) and post-monsoon Rabi irrigation (October–March).
2. **Zero-Parameter Variance Capture:** The seasonal cycle explains $72.15\%$ of the total groundwater level variance across the 33 districts. A naive model that predicts $\hat{y}_{t+12} = y_t$ captures over $72\%$ of variance **without estimating a single parameter**.
3. **Estimation Variance Penalty:** To beat annual persistence at $M+12$, a machine learning model must estimate both the multi-harmonic seasonal cycle and the climate-driven anomaly. Any variance or bias introduced by the estimator easily exceeds the subtle anomaly signal, leading to higher squared error.

### 3.3 Handling of Missing Data, Imputation, and Timestamps
- **Missing Origin Groundwater:** Missing groundwater depths are carried forward using causal last-observation-carried-forward (LOCF) for up to 3 months (`is_imputed = True`). While LOCF is strictly causal (does not use future data), carried-forward values represent stale observations, not fresh measurements.
- **Contemporaneous Availability at Issue Time:** The baseline assumes $y_M$ is available at the end of month $M$. However, in practice, CGWB water-level measurements are typically taken in piezometer networks during specific observation rounds (January, May, August, November) and published weeks or months later. The dataset lacks populated `actual_acquisition_at` and `available_at` timestamps. Therefore, the baseline must be understood as an *idealized retrospective benchmark*, not a verified operational real-time feed.

---

## 4. Validation of the Paired Cluster Bootstrap

### 4.1 Implementation Diagnosis
The cluster bootstrap procedure was re-audited against [`reports/statistical_audit_correction_20261022/audit_correction_analysis.py`](file:///c:/Users/Yasharth/Downloads/AquaIQ/reports/statistical_audit_correction_20261022/audit_correction_analysis.py).

The audit confirms:
1. **Resampling Unit:** Sampling with replacement from the $K=33$ unique district clusters.
2. **Identical Paired Draws:** In replicate $b$, the exact same vector of resampled districts is evaluated for both XGBoost and the baseline.
3. **Cluster Multiplicity:** All 24 monthly observations for a selected district are repeated in full according to the district's draw multiplicity ($m \in \{0, 1, 2, \dots\}$).
4. **Independent Recomputation:** 10,000 bootstrap replicates were executed across four distinct pseudorandom seeds.

### 4.2 Seed Sensitivity Analysis ($B = 10,000$ Replicates Each)

| Random Seed | Bootstrap Mean $\Delta\text{RMSE}$ (m) | Standard Error (m) | 95% Percentile CI (m) | Fraction $\ge 0$ |
|:---:|:---:|:---:|:---:|:---:|
| **42** | -0.037111 | 0.045446 | **[-0.120860, +0.055450]** | 0.2047 |
| **2026** | -0.036334 | 0.045255 | **[-0.122071, +0.054794]** | 0.2094 |
| **12345** | -0.036862 | 0.045271 | **[-0.121274, +0.056001]** | 0.2017 |
| **99999** | -0.037375 | 0.045402 | **[-0.122735, +0.054284]** | 0.2014 |

- **CI Width:** Consistently $0.176\text{ m}$ to $0.177\text{ m}$ wide across all seeds.
- **Zero Infiltration:** The upper bound remains strictly positive ($+0.054\text{ m}$ to $+0.056\text{ m}$) across all seeds.
- **Bootstrap Sign Proportion:** In **20.1% to 20.9%** of replicates, the annual baseline equals or outperforms XGBoost.
- **Formal Status of $p = 0.4094$:** Confirmed **INVALID as a frequentist $p$-value**. Doubling the uncentered tail probability $\min(q, 1-q) \times 2 = 2 \times 0.2047 = 0.4094$ confounds estimation sampling variability with a hypothesis test under $H_0$. It is permanently withdrawn.

---

## 5. Spatial and Temporal Dependence Investigation (Priority Audit)

The central statistical question is whether the district-cluster bootstrap uncertainty is overly optimistic because districts share common climate shocks and serial autocorrelation.

### 5.1 Empirical Dependence Diagnostics

#### A. Contemporaneous Cross-District Correlation (Spatial Shock Sharing)
Groundwater errors across all $\binom{33}{2} = 528$ district pairs over the 24 evaluation months:
- **Mean Cross-District Correlation of Annual Baseline Errors:** $\mathbf{+0.6898}$
- **Mean Cross-District Correlation of XGBoost Errors:** $\mathbf{+0.4398}$
- **Mean Cross-District Correlation of Squared Error Differences ($\Delta\text{SE}$):** $\mathbf{+0.2279}$

> [!CRITICAL]
> **Interpretation:** There is massive spatial co-movement across Telangana districts ($r \approx 0.69$ for baseline errors). When a monsoon failure or intense rainfall event strikes the state, groundwater depth errors across all 33 districts move in lockstep. The 33 districts are **not independent sampling units**.

#### B. Serial Autocorrelation within Districts (Temporal Persistence)
Lag-1 autocorrelation of monthly errors within each district across the 24 contiguous months:
- **Mean Lag-1 Autocorrelation of Baseline Errors:** $\mathbf{+0.7534}$
- **Mean Lag-1 Autocorrelation of XGBoost Errors:** $\mathbf{+0.4344}$
- **Mean Lag-1 Autocorrelation of Squared Error Differences ($\Delta\text{SE}$):** $\mathbf{+0.3763}$

> [!CRITICAL]
> **Interpretation:** Baseline errors have an average lag-1 serial autocorrelation of $0.75$. Groundwater depth is an aquifer storage stock variable whose errors persist across multiple consecutive quarters. Consecutive forecast origins are heavily dependent.

#### C. Annual Regime Reversal (The Two-Year Cancellation Effect)
When evaluated separately by target calendar year ($N = 396$ each):

| Target Year | Evaluation Period | Baseline RMSE | XGBoost RMSE | $\Delta\text{RMSE}$ (XGB − Base) | Dominant Method |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **2024** | 2024-01 to 2024-12 | 1.6280 m | 1.3354 m | **-0.2926 m** ($-29.3\text{ cm}$) | **XGBoost Superior** |
| **2025** | 2025-01 to 2025-12 | 1.2647 m | 1.4997 m | **+0.2350 m** ($+23.5\text{ cm}$) | **Baseline Superior** |
| **Combined** | **2024-01 to 2025-12** | **1.4577 m** | **1.4199 m** | **-0.0378 m** ($-3.78\text{ cm}$) | **Near-Tie (Cancellation)** |

**Hydrogeological Explanation:**
- In 2024, post-monsoon drought depleted water tables deeper than the 2023 origin baseline. XGBoost utilized rainfall deficit and evapotranspiration signals to correctly anticipate deeper water levels, beating the naive baseline by $29.3\text{ cm}$.
- In 2025, groundwater levels rebounded to near-normal seasonal depths matching 2024 origins. Naive persistence achieved an outstanding RMSE of $1.265\text{ m}$, whereas XGBoost suffered from severe positive bias ($+0.457\text{ m}$ overall), overpredicting depletion and losing to the baseline by $23.5\text{ cm}$.
- The pooled 792-case difference of $-3.78\text{ cm}$ is not a stable steady-state advantage; it is the **net algebraic cancellation of two large opposing climate-regime swings**.

### 5.2 Resampling Scheme Sensitivity Comparison

To assess how unmodeled cross-district and temporal dependence affects uncertainty bounds, four resampling schemes were independently computed ($B = 10,000$ each):

| Resampling Scheme | Preserved Dependence Structure | Standard Error (SE) | 95% Confidence Interval | CI Width |
|:---|:---|:---:|:---:|:---:|
| **1. District-Cluster ($K=33$)** | Within-district serial only; assumes spatial independence | **0.0454 m** | **[-0.1209, +0.0555] m** | 0.176 m |
| **2. Time-Cluster ($T=24$ months)** | Cross-district spatial only; assumes temporal independence | **0.0875 m** | **[-0.2046, +0.1366] m** | 0.341 m |
| **3. Temporal Block ($L=6$ months)** | Cross-district spatial + 6-month serial blocks | **0.1520 m** | **[-0.3289, +0.2520] m** | **0.581 m** |
| **4. Temporal Block ($L=12$ months)** | Cross-district spatial + full annual cycle blocks | **0.1452 m** | **[-0.2705, +0.2436] m** | **0.514 m** |
| **5. Two-Way District $\times$ Block** | Candidate report design (`uncertainty.json`) | — | **[-0.3173, +0.2645] m** | **0.582 m** |

### 5.3 Synthesis on Dependence Limitations
1. **District-Cluster Bootstrap is Deceptively Narrow:** Resampling districts forces every bootstrap replicate to contain equal proportions of the 2024 and 2025 regimes (12 months of 2024 and 12 months of 2025). This artificially neutralizes the between-year regime variance.
2. **True Uncertainty is >3× Wider:** When temporal dependence is preserved via moving block bootstrap, the standard error expands from **$0.045\text{ m}$ to $0.152\text{ m}$**, and the 95% confidence interval spans roughly $[-0.33, +0.25]\text{ m}$.
3. **Effective Sample Size:** Because the evaluation contains only two full annual cycles, the effective temporal degrees of freedom are $T_{\text{years}} \approx 2$. No statistical method can manufacture asymptotic temporal certainty from two observed monsoons.

---

## 6. Review of Reported Inferential Procedures

Four inferential methods were evaluated in `reports/statistical_inference_review_20261022/`:

```
+-------------------------------------------------------------------------------------------------------------------------+
|                                        INFERENTIAL PROCEDURES EVALUATION MATRIX                                         |
+--------------------------+-----------------------+---------------------+-------------------+------------+---------------+
| Inferential Method       | Scientific Estimand   | Null Hypothesis H0  | Test Statistic    | p-Value    | Valid & Robust|
+--------------------------+-----------------------+---------------------+-------------------+------------+---------------+
| Centered Bootstrap Pivot | Pooled Delta_RMSE     | Delta_RMSE = 0      | Dev >= |delta_obs|| p = 0.4061  | Conditional   |
| Cluster-Robust Wald Test | Pooled Delta_RMSE     | Delta_RMSE = 0      | z = -0.8321       | p = 0.4054  | Conditional   |
| District Paired t-Test   | Mean District Delta   | E[Delta_d] = 0      | t(32) = -0.4235   | p = 0.6747  | Qualified     |
| District Wilcoxon Test   | Median District Delta | Median(Delta_d) = 0 | W = 218.0         | p = 0.2719  | Qualified     |
+--------------------------+-----------------------+---------------------+-------------------+------------+---------------+
```

### 6.1 Centered Bootstrap Pivot Test ($p = 0.4061$)
- **Estimand:** Pooled $\Delta\text{RMSE}$ across all 792 observations.
- **Calculation:** Shifts the bootstrap distribution by $\widehat{\Delta\text{RMSE}}_{\text{obs}}$ so it centers at 0: $T_b^* = \Delta\text{RMSE}_b^* - \widehat{\Delta\text{RMSE}}_{\text{obs}}$, then computes $P(|T_b^*| \ge |\widehat{\Delta\text{RMSE}}_{\text{obs}}|)$.
- **Critical Critique:** RMSE difference is a nonlinear function of sample second moments ($\sqrt{\text{MSE}_1} - \sqrt{\text{MSE}_2}$). In non-parametric bootstrap theory, shifting an unstudentized empirical distribution provides only a first-order asymptotic approximation and assumes variance stability under $H_0$. Furthermore, it inherits the spatial-only clustering assumption, ignoring the temporal dependence documented in Section 5.
- **Verdict:** Valid as an exploratory, conditional pivot test, but not an exact finite-sample null distribution.

### 6.2 Cluster-Robust Wald-Style Test ($z = -0.8321, p = 0.4054$)
- **Estimand:** Pooled $\Delta\text{RMSE}$.
- **Calculation:** $z = \frac{-0.037815}{0.045446} = -0.8321 \implies p = 2\Phi(-0.8321) = 0.4054$.
- **Critical Critique:** While the bootstrap distribution exhibits near-zero skewness ($0.202$) and low excess kurtosis ($0.047$), the denominator $\text{SE} = 0.0454\text{ m}$ is based on district-only clustering. If the dependence-aware block standard error ($\text{SE} \approx 0.152\text{ m}$) is used, $z$ becomes $\frac{-0.0378}{0.152} \approx -0.248 \implies p \approx 0.804$.
- **Verdict:** Under normal approximation conditional on district clustering, $p = 0.4054$. Under temporal dependence, $p$ is even larger. In both cases, $H_0$ is decisively not rejected.

### 6.3 District-Level Paired $t$-Test ($t(32) = -0.4235, p = 0.6747$) & Wilcoxon Signed-Rank ($W = 218.0, p = 0.2719$)
- **Crucial Estimand Distinction:** These test the **unweighted arithmetic average of district RMSE differences**:
  $$\bar{\theta} = \frac{1}{33} \sum_{d=1}^{33} \left(\text{RMSE}_{\text{xgb}}(d) - \text{RMSE}_{\text{base}}(d)\right) = -0.020634\text{ m}$$
  This is scientifically distinct from pooled $\Delta\text{RMSE}$ ($-0.0378\text{ m}$), because pooled RMSE implicitly weights districts by their mean squared error magnitude.
- **Assumptions & Violations:** Both tests assume that the 33 district observations are mutually independent. This assumption is violated by regional spatial correlation ($r \approx 0.44–0.69$).
- **Non-Parametric Win Counts:** XGBoost achieved lower RMSE in 20 of 33 districts ($60.6\%$), while the baseline achieved lower RMSE in 13 districts ($39.4\%$). Under a two-tailed binomial test against fair coin flipping ($p_0 = 0.5$), $P(X \ge 20 \text{ or } X \le 13 \mid N=33) = 0.3060$.

### 6.4 Scientific Inference Verdict
None of the four tests yields a statistically significant difference at $\alpha = 0.05$ or $\alpha = 0.10$. However, **failure to reject the null hypothesis must not be reported as proof of equal performance**. The data simply lack the power and temporal depth to distinguish between the two models.

---

## 7. Practical Significance and Equivalence Assessment

### 7.1 Magnitude in Hydrogeological Context
The observed point improvement of XGBoost over annual persistence is:
$$\Delta\text{RMSE} = -0.0378\text{ m} = -3.78\text{ cm}$$
In Telangana groundwater monitoring:
- Hard-rock aquifers exhibit seasonal water table fluctuations of **3.0 to 15.0 metres**.
- CGWB open well and piezometer manual water-level soundings have physical measurement uncertainty of **$\pm 0.05\text{ to } \pm 0.20\text{ m}$**.
- Changes in the composition of contributing wells in a district induce artificial shifts in district mean depth of **$\pm 0.30\text{ to } \pm 0.80\text{ m}$**.
- Therefore, a point difference of **$3.78\text{ cm}$** is an order of magnitude smaller than typical well measurement noise and well-network compositional churn.

### 7.2 Pre-Specified Equivalence Margins
- **Audit Finding:** Neither `config.yaml`, the candidate protocol (`protocol.json`), nor previous reports specify a predefined practical equivalence margin ($\delta$) or decision-linked error tolerance.
- **Methodological Rule:** Without a pre-specified margin established before data inspection, **it is statistically improper to perform a post-hoc equivalence test (e.g. TOST) or claim non-inferiority**. Any selected margin would be arbitrary and subject to confirmation bias.
- **Mandated Reporting Language:** The research claim must be strictly qualified as:
  > *"The 12-month evaluation did not establish statistically significant predictive superiority of expanding XGBoost over annual seasonal persistence."*

---

## 8. Research Evaluation Design and Leakage Audit

### 8.1 Partitioning & Embargo Boundaries
- **Causal Feature Lags (PASS):** Ground-truth depth lags `gwl_lag_3mo` and `gwl_lag_6mo` match exact historical observations at $t-3$ and $t-6$ months. Trailing rainfall `rainfall_3mo_avg` is strictly backward-looking ($\text{mean}(t-2, t-1, t)$).
- **Temporal Buffer (PASS):** Cutoffs are separated from evaluation origins by 12 calendar months and from targets by 24 calendar months.
- **Direct Target Overlap (PASS):** Contemporaneous overlap between features and evaluation target $y_{t+12}$ is zero across all 792 primary rows.

### 8.2 Methodological Qualifications
- **Transductive Climatology Normalization (QUALIFIED):** Multi-decade normals for rainfall deficit and evapotranspiration use the full 2002–2025 record. While standard in hydrogeology, this constitutes mild transductive leakage of long-term climate statistics into early training folds.
- **Repeated Inspection of Test Sets (WARNING):** Target years 2024 and 2025 were repeatedly analyzed during previous project phases and 6-month model selections. The primary evaluation period is a **chronological holdout, not a pristine blind holdout**.
- **Case Re-use across Horizons:** An observation at origin $t$ serves as `gwl_current` at origin $t$, `gwl_lag_3mo` at origin $t+3$, and the baseline reference for target $t+12$.

---

## 9. Data Provenance and Hydrogeological Limitations

Audit of raw records in `reports/actual_forecast_validation_20261019/` and `reports/candidates/twelve_month_horizon_20261020/`:

1. **Source-Name/Polygon Conflicts (CRITICAL LIMITATION):**
   - Out of 188,458 accepted records, **125,400 rows** have resolvable name/polygon conflicts, **58,034 rows** have unresolved district names, and only **5,024 rows** ($2.7\%$) have exact name/polygon agreement.
   - **100% of the 792 primary target panels contain a name/polygon conflict**. The mean conflicting-well share is **65.80%**, with another **29.67%** unresolved.
   - In 106 primary target panels, recorded depths exceed listed well depth.
2. **Well-Panel Composition Churn:** Contributing wells shift month-to-month (e.g. 6 to 15 wells in Adilabad). District averages change when stations drop in or out of the network, confounding physical water table trends with sampling changes.
3. **Lack of Operational Timestamps:** `actual_acquisition_at`, `available_at`, and `forecast_issued_at` are `null`. A target labeled "January 1" does not provide 12 full months of operational lead when whole-month weather is not finalized until February.
4. **Policy Simulation is Non-Causal:** In `api/routes/simulate.py`, extraction impacts are computed as a hardcoded linear heuristic:
   $$\Delta\text{Score} = +0.20 \times \text{extraction\_change\_pct}$$
   This is an arbitrary sensitivity heuristic, not a learned hydrological causal effect.

---

## 10. Separate Inspection of Distinct Components

```
+----------------------------------------------------------------------------------------------------------------------+
|                                          SYSTEM COMPONENT STATUS MATRIX                                              |
+--------------------------+-----------------------+---------------------------------------+---------------------------+
| Component                | Scope                 | Performance / Implementation          | Research Verdict          |
+--------------------------+-----------------------+---------------------------------------+---------------------------+
| Expanding XGBoost (12m)  | 33 Telangana Districts| RMSE 1.4199 m vs Base 1.4577 m        | Comparable to Baseline    |
| Fixed Adilabad Artifact  | 1 District (Adilabad) | RMSE 2.6640 m vs Base 0.8770 m        | Severe Underperformance   |
| Monthly Scenario         | 725 Districts         | Damped seasonal trend; zero weather   | Unvalidated Scenario Only |
| Operational Risk Score   | 725 Districts         | 6-month legacy basis; initial weights | Prototype / Uncalibrated  |
+--------------------------+-----------------------+---------------------------------------+---------------------------+
```

1. **Fixed TS-Adilabad Artifact (`xgb_fixed_2021.json`):**
   - **RMSE:** Fixed XGBoost = $2.6640\text{ m}$; Baseline = $0.8770\text{ m}$.
   - **Finding:** Underperforms baseline by $1.787\text{ m}$ (304% of baseline RMSE). Suitable only as a historical research counter-example showing failure of frozen regional models. Must never be generalized across Telangana.
2. **Experimental Monthly Scenario (`models/experimental_scenario.py`):**
   - **Method:** `damped_seasonal_trend`. Extrapolates in-memory linear trend and 12-month calendar harmonics.
   - **Finding:** Contains zero weather or extraction features. It is **not a machine learning model**. It is explicitly marked `unvalidated_scenario`, `prospective_skill_verified = False`, and `sufficient_for_operational_use = False`.
3. **Operational Risk Tiers (`api/routes/scores.py` & `config.yaml`):**
   - **Weights Status:** Explicitly `'initial_uncalibrated'`.
   - **Forecast Basis:** Explicitly `'legacy_six_month_components_not_recalibrated_for_twelve_months'`.
   - **Distribution:** 725 canonical districts (Safe=300, Watch=365, Warning=50, Crisis=6, Unknown=4).
   - **Finding:** Risk scores are uncalibrated project indices, not official CGWB categories or empirical crisis probabilities.

---

## 11. Product Research Communication Audit

Inspection of dashboard components (`dashboard/src/components/ResearchForecast.jsx`, `dashboard/src/pages/Home.jsx`):
- **PASS:** The UI and API explicitly differentiate:
  1. Measured historical observations (solid points/lines).
  2. Direct M+12 point forecast (single discrete point at month 12).
  3. Intermediate months 1–11 are rendered as empty nulls on the ML forecast line; they are not interpolated into a false continuous curve.
  4. Experimental scenarios are isolated behind `view=scenario` with prominent warnings: *"Unvalidated experimental scenario: no prospective skill or operational readiness is established."*
  5. The UI prominently displays that the 24-case Adilabad check favored the baseline (0.877 m vs 2.664 m) and that the 792-case difference interval crosses zero.
- **Integrity Verdict:** The research communication in the user interface is truthful, cautious, and maintains high scientific integrity.

---

## 12. Confirmed Bugs, Corrected Claims, and Remaining Risks

1. **Previous Flawed Bootstrap (RESOLVED / PASS):** The independent (unpaired) cluster bootstrap in early audits ($\text{SE} \approx 0.0918\text{ m}$, CI $[-0.2203, +0.1409]\text{ m}$) was formally corrected to a paired cluster bootstrap ($\text{SE} = 0.0454\text{ m}$, CI $[-0.1209, +0.0555]\text{ m}$).
2. **Invalid Sign-Proportion $p$-Value (RESOLVED / WITHDRAWN):** The quantity $p = 0.4094$ is formally withdrawn as an invalid frequentist $p$-value.
3. **Historical 807 District Typo Claim (RESOLVED / CORRECTED):** Proven to be a pre-deduplication prototype snapshot ($380 + 365 + 56 + 6 = 807$), not an arithmetic addition typo. The live database correctly reconciles to 725 canonical districts.
4. **Underestimated Bootstrap Uncertainty (CONFIRMED LIMITATION):** District-only clustering ignores the massive cross-district correlation ($r \approx 0.69$) and annual regime reversal (2024 vs 2025). The true sampling uncertainty under temporal block resampling is $\text{SE} \approx 0.152\text{ m}$ ($[-0.3289, +0.2520]\text{ m}$).

---

## 13. Reproducible Audit Commands

All commands can be re-executed in PowerShell within the repository root:

```powershell
# 1. Verify complete Python test suite (1,164 passed, 14 skipped)
.\venv\Scripts\python.exe -m pytest -q

# 2. Verify frontend test suite (57 passed, 0 failed)
cd dashboard; npm test; cd ..

# 3. Verify frontend code linting (0 warnings, 0 errors)
cd dashboard; npm run lint; cd ..

# 4. Re-execute standalone audit script and export results
.\venv\Scripts\python.exe reports\final_research_readiness_20261022_audit\reproducible_checks.py
```

---

## 14. Prioritized Recommendations for Future Research

1. **High Priority (Hydrogeological Panel Curation):** Filter and certify well-level records with stable measuring-point datums and consistent panel membership across years, eliminating the 65.8% name/polygon conflict rate.
2. **High Priority (Multi-Year Prospective Validation):** Archive prospective frozen forecasts at issue time and evaluate over at least 5 to 10 future annual monsoons to achieve sufficient temporal degrees of freedom ($T_{\text{years}} \ge 5$).
3. **Medium Priority (Pre-Specified Equivalence Protocol):** Pre-specify a formal domain tolerance margin (e.g. $\delta = \pm 0.25\text{ m}$) in collaboration with groundwater hydrogeologists before running future evaluations.
4. **Medium Priority (Ensemble Weight Calibration):** Calibrate crisis scoring weights against historical independent declarations of agricultural drought (e.g. state-notified drought mandals) rather than arbitrary initial settings.
5. **Low Priority (Physical Process Integration):** Integrate numerical groundwater flow models (MODFLOW) with ML residual learning to combine physical water-budget conservation with data-driven anomaly detection.
