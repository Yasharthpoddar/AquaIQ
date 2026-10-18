# AquaIQ — seasonal-naive diagnostics and prospective release plan

**Decision:** keep the already selected `hist_gradient_boosting-2-delta` as the fixed research candidate. No fitting, tuning or reselection occurred. Neither it nor a baseline is declared production-ready. Detailed tables, lineage and protocol qualifications are in `TECHNICAL_NOTES.md` and the adjacent CSV/JSON evidence.

**Audit.** All 228 calendar, 6,522 district and 84 year metric rows reconcile with the saved predictions. Every primary origin, label and seasonal reference matches the verified feature release; all 627 raw-source monthly means reproduce within 0.00001 m. Existing observed flags identify source-backed monthly values, not independently certified fresh acquisitions.

**Weighting changes interpretation.** Primary-test entries are MAE / RMSE in metres, using the same 209 cases. Macro scores are arithmetic means of group scores; no group R² is averaged.

| Model | Pooled | Equal district | Equal target calendar month |
|---|---:|---:|---:|
| Persistence | 1.234 / 3.698 | 3.671 / 3.780 | 1.060 / 2.469 |
| Seasonal naive | 1.049 / 2.132 | 2.071 / 2.186 | 0.971 / 1.883 |
| Ridge | 1.381 / 2.573 | 2.220 / 2.307 | 1.383 / 2.142 |
| Random Forest | 1.290 / 2.558 | 2.236 / 2.329 | 1.280 / 2.031 |
| XGBoost | 1.432 / 3.225 | 2.709 / 2.807 | 1.389 / 2.379 |
| Fixed HGB | 1.327 / 3.060 | 2.548 / 2.655 | 1.298 / 2.237 |

Validation has 3,312/3,522 May/November cases (94%). Its pooled RMSE favors HGB, 2.148 versus seasonal 2.436; equal-month mean RMSE reverses this, 2.551 versus 2.367. Other validation months contain only 18–29 cases each. This diagnoses sampling sensitivity without changing the existing selection.

**Districts, months and measurement patterns.** Seasonal has lower absolute error than HGB on 141/209 cases, Ridge on 149, RF on 137 and XGBoost on 147. Its largest summed HGB-minus-seasonal absolute-error advantages are Faridabad 21.79 m, Kurukshetra 17.41, Sivaganga 14.88, Thoothukkudi 9.23 and Alwar 8.60; Cuddalore offsets 16.28 m. These are sums, not district MAEs.

Seasonal wins primary RMSE in February–May and August, and MAE in nine months. August's 16 cases give HGB/seasonal RMSE 9.383/4.258. Month samples differ geographically and contain 11–45 cases, so this is not an isolated seasonal causal effect.

Of 209 targets, 68 equal the prior-year seasonal value, 90 equal persistence and 64 equal both. The 68 seasonal-exact cases account for 103.2% of HGB's net excess absolute error. All 48 targets in 2022 equal persistence; 43 equal seasonal. Nine of ten in 2023 equal both. Those years cover only Cuddalore, Tiruppur, Sivaganga and Deoria. Flat aggregate means require source-freshness verification; they do not establish unchanged groundwater or independent repeated measurements.

Faridabad's single case accounts for 114.3% of HGB's net excess squared error over seasonal. Its origin and target share no station-location proxy; the seasonal reference shares both target proxies. Across all cases, average proxy Jaccard overlap is 0.638 for origin–target versus 0.820 for seasonal–target. Retain every case: no erroneous observation was established. Proxy names/coordinates are not stable well IDs.

Legacy aggregation weights raw readings, so high-frequency series can dominate district means. Equal proxy-well weighting would change 59/209 target means, by up to 15.93 m; no replacement labels were scored. The broader cohort remains seasonal-favored; the separate Gujarat result favors HGB but is concentrated in four districts and has unresolved datum/composition. It does not resolve generalization.

**Dates, units and issuance.** Raw reported dates follow saved month-start indexes for 208/209 origins and every target; latest source-date separations span 162–204 days. Whole-origin-month rainfall and ERA5 monthly aggregates cannot be known at that month's start. Calendar causality is verified, but publication/receipt/revision timestamps and actual issuance snapshots are absent. Six-month operational lead is therefore unverified.

The manifest declares depth in `m_bgl`; the legacy header does not independently certify datum. Gujarat establishes metres but not below-ground datum. [CGWB's general depth-below-ground convention](https://cgwb.gov.in/en/ground-water-level-monitoring) does not certify these downloaded records.

**Prospective next steps.** Before new outcomes, preregister districts, calendar coverage, panels, aggregation, missingness, issuance dates and one analysis date. The experiment has no serialized final HGB: later create one separate deterministic shadow artifact from the same locked settings and 14,817 pre-2019 training pairs, with no tuning. Freeze weights/binning, learned preprocessing state, feature code/order, clipping and software hashes. No refit was performed here.

Archive each model and both baseline predictions with input snapshots, well membership/weights, `issued_at` and per-value `available_at`; require availability before issuance. Use newly acquired observed targets, complete panels registered at issuance, and observed origin/exact prior-year references. Never recompute a matched-well intersection after target arrival. Historical backfills and partial-panel aggregates remain separate cohorts.

Collect immutable well IDs, replacement/location history, aquifer/screen/depth, ground/measuring-point datum, acquisition timestamps and freshness flags, pumping/method metadata, publication/receipt times and revision IDs. Obtain current origins, 3/6-month lags, prior-year references, point-in-time weather and future target readings. Without historical references, a new seasonal→origin→target chain needs approximately a year. Year-round claims require quality-controlled observations beyond the usual seasonal rounds and a registered geographic/aquifer sample, including new districts.

**Proposed release gates — currently unmet.** Finalize margins and development-only clustered power calculations before prospective issuance; the numerical defaults below are planning proposals, not sufficiency proven by this test.

| Gate | Requirement |
|---|---|
| Artifact, units and lead | Frozen reproducible shadow artifact; verified m_bgl/panels; 100% of eligible forecasts archived before acquisition and inputs available before issuance. A six-full-month claim requires every included target acquisition at least six calendar months after actual issuance. If complete-month inputs prevent that, fail this gate; do not shift labels or silently substitute weather. |
| Coverage | Planning floors: 500 paired cases, 50 districts, two complete annual target cycles. Year-round scope additionally requires 25 cases from 10 districts per month, with both cycles represented. Use the larger sample required by power analysis; daily source rows do not increase forecast-case counts. |
| Skill | Proposed ≥5% lower pooled RMSE point estimate versus each baseline, with simultaneous paired 95% intervals excluding no improvement; the intervals do not have to establish the full 5% benefit. Upper uncertainty bounds for pooled, district-macro and calendar-macro MAE/RMSE ratios versus each baseline must remain within a proposed 1.05 non-inferiority margin. Account for districts and shared contiguous target periods; insufficient temporal replication means no release. |
| Integrity and scope | All exclusions, missing labels and abstentions disclosed; repeated/extreme values adjudicated without outcome-driven deletion. Separate registered new-region/aquifer results; no national claim from a regional pass. |
| Decision discipline | One scheduled confirmatory analysis; no accuracy-driven stopping, tuning or subgroup/family switching. Failed or uncertain gates mean no promotion. Further confirmation needs a preregistered fresh cohort and separate operational review. |

**Preservation and verification.** All 194 fingerprinted existing artifact/input files remain unchanged; the raw audit separately checks its ten source/code inputs. Only this new diagnostics directory was added. No database or production checkpoint was written. Reproduce the read-only checks from the repository root:

```powershell
.\venv\Scripts\python.exe reports/candidates/six_month_diagnostics_20261017/analyze_saved.py --verify-only
.\venv\Scripts\python.exe reports/candidates/six_month_diagnostics_20261017/verify_raw_lineage.py --verify-only
```
