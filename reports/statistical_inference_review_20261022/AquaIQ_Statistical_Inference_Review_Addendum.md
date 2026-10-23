# AquaIQ — Statistical Inference Review Addendum

**Review Target:** `reports/statistical_audit_correction_20261022/AquaIQ_Statistical_Audit_Correction_Report.md`  
**Dataset Analyzed:** `reports/candidates/twelve_month_horizon_20261020/evaluation/full_coordinate_predictions.csv` (`period == 'primary'`)  
**Audit Script:** `reports/statistical_inference_review_20261022/inference_review.py`  
**Machine-Readable Summary:** `reports/statistical_inference_review_20261022/inference_results.json`  
**Date:** 2026-10-22  
**Status:** Completed & Independently Verified  

---

## Executive Summary

This addendum provides a focused review of statistical inference following the district-cluster bootstrap correction in the AquaIQ 12-month groundwater depth forecasting evaluation. 

The review confirms:
1. **The reported $p = 0.4094$ is INVALID as a frequentist $p$-value** and should be withdrawn. It was computed by doubling an uncentered bootstrap tail probability, confounding estimation uncertainty with a hypothesis test under $H_0$.
2. **The point estimates and 95% paired cluster-bootstrap confidence interval are independently reproduced**:
   - $\text{RMSE}(\text{XGBoost}) = 1.4199\text{ m}$, $\text{RMSE}(\text{Annual Baseline}) = 1.4577\text{ m}$
   - Point Estimate: $\Delta\text{RMSE} = -0.0378\text{ m}$ ($-3.78\text{ cm}$)
   - **95% Paired Cluster-Bootstrap CI:** $[-0.1209, +0.0555]\text{ m}$ ($B=10,000$, paired district resampling, seed=42)
3. **Valid inferential procedures yield consistent, non-significant results**:
   - Bootstrap Pivot (null-calibrated) Test: $p = 0.4061$
   - Cluster-Robust Wald Test (normal approximation): $z = -0.8321, p = 0.4054$
   - District-Level Paired $t$-test (unweighted average estimand): $t(32) = -0.4235, p = 0.6747$
   - District-Level Wilcoxon Signed-Rank Test: $W = 218.0, p = 0.2719$
4. **The 20.47% bootstrap sign proportion** describes sampling variability in the estimator across district clusters, not an empirical probability that the baseline will outperform XGBoost in future operational deployments.
5. **Final Scientific Conclusion:** The empirical evidence **fails to reject the null hypothesis of equal forecasting performance at $\alpha = 0.05$**. XGBoost cannot be claimed to be statistically significantly superior to the simple annual seasonal persistence baseline for 12-month groundwater depth forecasts in Telangana.

---

## 1. Review of the Reported $p$-Value ($p = 0.4094$)

### 1.1 Calculation Method
In `reports/statistical_audit_correction_20261022/audit_correction_analysis.py` (lines 184–185), the reported $p$-value was computed as:
```python
p_value = 2 * min(
    np.mean(delta_rmse_list >= 0),
    np.mean(delta_rmse_list <= 0)
)
```
Given that $\hat{P}^*(\Delta\text{RMSE}^* \ge 0) = 0.2047$, the script returned $2 \times 0.2047 = 0.4094$.

### 1.2 Flaw and Statistical Assumptions
In frequentist hypothesis testing, a $p$-value is defined as the probability, **calculated under the null hypothesis $H_0$**, of obtaining a test statistic at least as extreme as the observed value:
$$p = P(T(X^*) \ge T(x_{\text{obs}}) \mid H_0)$$

For the hypothesis of equal accuracy ($H_0: \Delta\text{RMSE} = 0$):
- The non-parametric paired cluster bootstrap draws samples from the empirical distribution $\hat{F}$, which approximates the true data-generating process under the alternative/observed state.
- Consequently, the bootstrap distribution $\Delta\text{RMSE}^*$ is centered near the observed point estimate $\widehat{\Delta\text{RMSE}} = -0.0378\text{ m}$ (bootstrap mean = $-0.0371\text{ m}$), **not at the null value $0.0\text{ m}$**.
- The proportion $\hat{P}^*(\Delta\text{RMSE}^* \ge 0) = 0.2047$ measures the tail mass of the estimator's sampling distribution that happens to cross zero.
- Doubling this tail probability ($\min(q, 1-q) \times 2$) is an ad-hoc heuristic that:
  1. Does not evaluate the statistic under a null-restricted model or centered distribution.
  2. Lacks asymptotic frequentist justification, particularly when the bootstrap distribution is asymmetric or biased.
  3. Mistakenly conflates parameter estimation uncertainty with null-hypothesis rejection probability.

**Verdict:** The figure $0.4094$ is **statistically invalid as a frequentist $p$-value** and must be classified as unsupported.

---

## 2. Independent Verification of Data & Confidence Interval

### 2.1 Dataset Integrity Verification
The evaluation dataset was independently verified against `reports/candidates/twelve_month_horizon_20261020/evaluation/full_coordinate_predictions.csv`:

| Verification Item | Specification Requirement | Verified Value | Status |
|:---|:---|:---|:---:|
| Evaluation Subset | `period == 'primary'` | 792 rows filtered | **PASS** |
| District Coverage | 33 Telangana districts | 33 unique district IDs | **PASS** |
| Panel Balance | 24 paired predictions per district | Exactly 24 rows per district (12 horizons $\times$ 2 cycles) | **PASS** |
| Key Uniqueness | Zero duplicate keys | 0 duplicates on `[district_id, date, target_date]` and `case_id` | **PASS** |
| Missing Data | Zero NaNs in evaluation variables | 0 NaNs in `actual`, `xgb_expanding`, `annual_seasonal_naive` | **PASS** |

### 2.2 Point Estimates
Evaluating across all $N = 792$ primary-period observations:
- **XGBoost Expanding:**
  $$\text{RMSE} = \sqrt{\frac{1}{792}\sum_{i=1}^{792} (y_i - \hat{y}_{i, \text{xgb}})^2} = 1.4199075311\text{ m}$$
  $$\text{MAE} = \frac{1}{792}\sum_{i=1}^{792} |y_i - \hat{y}_{i, \text{xgb}}| = 1.1591189914\text{ m}$$
- **Annual Seasonal Naive Baseline:**
  $$\text{RMSE} = \sqrt{\frac{1}{792}\sum_{i=1}^{792} (y_i - \hat{y}_{i, \text{base}})^2} = 1.4577225786\text{ m}$$
  $$\text{MAE} = \frac{1}{792}\sum_{i=1}^{792} |y_i - \hat{y}_{i, \text{base}}| = 1.1910789108\text{ m}$$
- **Point Differences (XGBoost $-$ Baseline):**
  $$\Delta\text{RMSE} = 1.4199075311 - 1.4577225786 = \mathbf{-0.0378150475\text{ m}}\quad (\approx -3.78\text{ cm})$$
  $$\Delta\text{MAE} = 1.1591189914 - 1.1910789108 = \mathbf{-0.0319599194\text{ m}}\quad (\approx -3.20\text{ cm})$$

### 2.3 Paired District-Cluster Bootstrap Verification
The bootstrap was executed with the following protocol:
- **Resampling Unit:** District clusters ($K = 33$).
- **Paired Evaluation:** In each replication $b \in \{1, \dots, 10000\}$, a single vector of 33 district IDs was drawn with replacement using `np.random.default_rng(42)`. Both XGBoost and the Baseline were evaluated on identical resampled panels.
- **Cluster Multiplicity:** All 24 observations for a sampled district were included, repeating in full whenever a district was drawn multiple times.
- **Number of Replicates:** $B = 10,000$.

#### Recalculated Confidence Intervals
- **$\Delta\text{RMSE}$:**
  - Bootstrap Mean: $-0.037111\text{ m}$
  - Bootstrap Standard Error ($\text{SE}$): $0.045446\text{ m}$
  - **95% Percentile CI:** $\mathbf{[-0.120860, +0.055450]\text{ m}}$ (rounded: $\mathbf{[-0.1209, +0.0555]\text{ m}}$)
- **$\Delta\text{MAE}$:**
  - Bootstrap Mean: $-0.031697\text{ m}$
  - Bootstrap Standard Error ($\text{SE}$): $0.045163\text{ m}$
  - **95% Percentile CI:** $\mathbf{[-0.114678, +0.061328]\text{ m}}$ (rounded: $\mathbf{[-0.1147, +0.0613]\text{ m}}$)

The recalculated interval exactly reproduces $[-0.1209, +0.0555]\text{ m}$. Because the interval straddles zero, the difference is not statistically significant at $\alpha = 0.05$.

---

## 3. Valid Inferential Results and Methodology

To provide mathematically defensible alternatives to the invalid $p$-value, four rigorous inferential procedures were evaluated:

### 3.1 Null-Calibrated Bootstrap Inversion (Pivot Test)
- **Estimand:** Pooled $\Delta\text{RMSE}$ across all 792 observations.
- **Methodology:** We center the empirical bootstrap replicates to represent the null distribution under $H_0: \Delta\text{RMSE} = 0$:
  $$T_b^* = \Delta\text{RMSE}_b^* - \widehat{\Delta\text{RMSE}}_{\text{obs}}$$
  The two-sided pivot $p$-value computes the proportion of centered bootstrap deviations at least as large as the observed difference:
  $$p_{\text{pivot}} = \frac{1}{B}\sum_{b=1}^B \mathbb{I}\left(|T_b^*| \ge |\widehat{\Delta\text{RMSE}}_{\text{obs}}|\right)$$
- **Assumptions:** The centered bootstrap distribution $\Delta\text{RMSE}^* - \hat{\theta}$ adequately approximates the sampling distribution under $H_0$.
- **Result:**
  $$p_{\text{pivot}} = \mathbf{0.4061}$$
  *Interpretation:* With $p = 0.4061 > 0.05$, $H_0$ cannot be rejected.

### 3.2 Cluster-Robust Wald Test
- **Estimand:** Pooled $\Delta\text{RMSE}$.
- **Methodology:** Using the cluster-bootstrap standard error $\text{SE}_{\text{boot}} = 0.045446\text{ m}$:
  $$z = \frac{\widehat{\Delta\text{RMSE}}_{\text{obs}}}{\text{SE}_{\text{boot}}} = \frac{-0.037815}{0.045446} = -0.83208$$
  $$p_{\text{wald}} = 2 \cdot \Phi(-|z|) = \mathbf{0.4054}$$
- **Assumptions:** Asymptotic normality of the clustered estimator. 
  - Diagnostic check: The bootstrap distribution exhibits low skewness ($0.202$) and near-zero excess kurtosis ($0.047$), confirming that normal approximation is well-behaved.
- **Result:**
  $$p_{\text{wald}} = \mathbf{0.4054}$$

### 3.3 District-Level Paired Tests (Important Estimand Distinction)
> [!IMPORTANT]
> **Distinction in Estimand:**  
> The pooled difference $\Delta\text{RMSE}$ weights individual observations equally (effectively weighting districts by their squared prediction errors). In contrast, per-district paired tests evaluate the unweighted mean difference across districts:
> $$\theta_{\text{district}} = \mathbb{E}\left[\text{RMSE}_{\text{xgb}}(d) - \text{RMSE}_{\text{base}}(d)\right]$$
> These answer two different scientific questions and must not be conflated.

For the $N=33$ Telangana districts:
- Mean District $\Delta\text{RMSE}$: $-0.020634\text{ m}$ ($-2.06\text{ cm}$)
- Median District $\Delta\text{RMSE}$: $-0.028249\text{ m}$ ($-2.82\text{ cm}$)
- Standard Deviation: $0.279822\text{ m}$
- Districts Favoring XGBoost ($\Delta < 0$): **20 / 33 (60.6%)**
- Districts Favoring Baseline ($\Delta > 0$): **13 / 33 (39.4%)**

#### Inferential Results:
1. **Paired $t$-Test ($df = 32$):**
   $$t = -0.4235, \quad p = \mathbf{0.6747}$$
   *Assumptions:* District differences are independent and normally distributed.
2. **Wilcoxon Signed-Rank Test:**
   $$W = 218.0, \quad p = \mathbf{0.2719}$$
   *Assumptions:* District differences are continuous, mutually independent, and symmetrically distributed under $H_0$.

Both district-level tests confirm the absence of statistically significant separation between the two models.

---

## 4. Correct Interpretation of the 20.47% Bootstrap Sign Proportion

In the paired cluster bootstrap, **20.47% (2,047 of 10,000)** of resampled panels yielded $\Delta\text{RMSE}^* \ge 0$.

### What It Measures:
- This value is a descriptive property of the **sampling variability of the estimator** $\widehat{\Delta\text{RMSE}}$ when clusters are resampled from the observed empirical dataset.
- It reflects that approximately one in five bootstrap draws of 33 districts produces an aggregate panel where the annual baseline matches or outperforms XGBoost.

### What It Does NOT Measure:
- **It is NOT a frequentist $p$-value:** It was not generated from a null distribution where $H_0: \Delta\text{RMSE} = 0$.
- **It is NOT a population predictive probability:** It cannot be stated as *"there is a 20.47% probability that the baseline will outperform XGBoost in future operational years."* A predictive probability requires an out-of-sample Bayesian posterior predictive distribution or temporal holdout evaluation, not a non-parametric spatial cluster resample of past data.

---

## 5. Final Evidence-Based Conclusion

Based on rigorous data verification, cluster-aware resampling, and proper inferential testing:

1. **Nominal Advantage:** The 12-month expanding XGBoost model demonstrates a minor nominal reduction in pooled RMSE of **$-0.0378\text{ m}$ ($-3.78\text{ cm}$)** relative to the annual seasonal persistence baseline (a 2.6% relative improvement from 1.4577 m to 1.4199 m).
2. **Confidence Bounds:** The 95% paired cluster-bootstrap confidence interval **$[-0.1209, +0.0555]\text{ m}$** straddles zero. The interval cannot rule out that the annual baseline is up to 5.55 cm better, nor that XGBoost is up to 12.09 cm better.
3. **Hypothesis Testing:** All valid significance tests fail to reject the null hypothesis of equal performance at conventional thresholds ($\alpha = 0.05$ or $\alpha = 0.10$):
   - Null-Calibrated Pivot Test: $p = 0.4061$
   - Cluster-Robust Wald Test: $p = 0.4054$
   - District-Level Paired $t$-test: $p = 0.6747$
   - District-Level Wilcoxon Test: $p = 0.2719$
4. **Scientific Claim:** The current evaluation **DOES NOT establish statistically significant superiority** of XGBoost over the annual seasonal persistence baseline for 12-month groundwater depth forecasting across Telangana. In research and technical communications, XGBoost must be described as achieving **comparable performance** to annual seasonal persistence, not demonstrable superiority.
