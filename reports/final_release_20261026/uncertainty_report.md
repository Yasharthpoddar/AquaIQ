# Historical interval reliability and honest disclosure

This is a retrospective audit and a display-safety correction. No model weights, point predictions, calibration residuals, radii or quantile were refitted. The previously inspected final holdout was not used to widen ranges, select a new model or claim a new independent reliability result.

The [machine audit](uncertainty_audit.json) reports unchanged-band results by evidence tier, horizon, tier/horizon, state, forecast origin and observation age. Every panel contains sample count, distinct districts/states/origins/target dates, exact date spans and missing-band counts. These are dependent district-month cases; their observed fractions are not estimates of a particular district's probability. No independent-binomial confidence intervals are asserted.

| Original final band panel | Cases | Districts | Cases inside band | Mean width (m) | Mean interval score (m) |
|---|---:|---:|---:|---:|---:|
| All | 843 | 640 | 661/843 (78.41%) | 5.791 | 22.151 |
| A | 731 | 543 | 81.81% | 5.922 | 19.741 |
| B | 97 | 83 | 61.86% | 4.917 | 30.618 |
| C | 15 | 15 | 3/15 (20.00%) | 5.048 | 84.842 |

Final targets cover only five distinct calendar dates between August 2024 and January 2026. The observed coverage does not validate every future monthly trajectory. Calibration targets end in July 2022 and precede every evaluation origin month. The audit verifies the saved case hashes, exact calendar horizons and original frozen radii before computing metrics.

The negatively oriented interval score is `(U-L) + (2/alpha)*max(L-y,0) + (2/alpha)*max(y-U,0)`, with alpha=0.1, lower being better. It penalizes width and missed observations jointly; it is not an accuracy percentage. The score definition follows Gneiting and Raftery (2007), equation 43, [author-hosted paper](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf). Reporting this proper diagnostic does not itself establish calibrated central quantiles.

## Why the zero-history result is unsupported

All 15 final C cases are M+12, targeting January 2026. Their common radius of 2.524225 m was derived from **one calibration district and one target: Tenkasi, January 2022**. Other C horizons have only 1-6 distinct calibration districts. The final C targets span multiple different states and depths of 0.405-41.076 m. This tiny, geographically different calibration panel is consistent with poor transfer; it does not establish a unique causal cause of undercoverage. It cannot justify a local 90% probability or a precise error band for an unmonitored district.

## Reporting policy, without post-holdout recalibration

`models/interval_evidence.py` introduces version `2.0-empirical-error-band-disclosure`:

- Numerical bands require **at least ten distinct calibration districts per tier/horizon**. At a 90th-percentile quantile, ten districts provide only one expected tail case at best. This fixed calibration-tail-resolution rule is a minimum reporting guard, not a conformal guarantee, an independence assertion or a threshold optimized against final errors.
- Unsupported horizons have `interval_status=unavailable` and no numerical bounds. C has no supported horizon under this calibration; D has no matching calibration. All twelve point estimates, methods, units, evidence tiers and observation counts remain available.
- Adequately supported historical bands keep their **original radius**. Their statuses are `empirical_undercovered` when matching historical evidence shows undercoverage, otherwise `historical_reference_only`. No output is newly labelled calibrated.
- The evidence artifact must match model, calibration identity and feature generation; its report/evaluation dates must not be in the future of the requested as-of. Historical validation is described as pooled cases, never this district's probability.
- The newer data generation is **not** assigned the older generation's measured coverage. [The identity check](uncertainty_identity_check.json) verifies that the new snapshot receives historical-reference-only/unavailable status while retaining unchanged calibration radii.
- Previously published objects are not rewritten. The frontend suppresses stale partial numerical bounds when legacy metadata says unavailable, visibly distinguishes historical bands from calibrated intervals, and keeps all twelve point values.

The guard withholds 202 previously available development-band cases and 19 final-band cases; the latter include all 15 C cases. Any fraction on the remaining subset is a changed denominator, **not a claimed improvement in calibration**. When no bands remain, coverage is unavailable rather than reported as 0% or 100%.

For the current unchanged calibration, A has supported bands at horizons 1/3/4/6/7/8/9/10/12; B at 1/4/6/7/8/10/12; C/D have none. Adequate count still gives no present-day local coverage guarantee.

## Reproduction and verification

```powershell
.\venv\Scripts\python.exe -B -m scripts.audit_interval_reliability --output reports/final_release_20261026/uncertainty_audit.json --evidence-output models/artifacts/interval_reliability.json --report-date 2026-10-26
.\venv\Scripts\python.exe -B -m pytest tests/test_interval_evidence.py tests/test_tiered_forecast.py -q -p no:cacheprovider
node --test dashboard/tests/intervalDisclosure.test.js dashboard/tests/tieredForecast.test.js
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build
```

Verification completed: **35 Python tests passed**, **9 focused frontend tests passed**, lint passed and production build passed with a largest JavaScript chunk of 365.50 kB. Full release-suite and browser/API checks are recorded separately by the release coordinator. No database or existing publication was modified by this audit.
