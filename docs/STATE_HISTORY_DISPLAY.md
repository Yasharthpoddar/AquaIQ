# State coverage, full historical timeline and graph display

Local correction, 2026-10-30. No release publication, active-pointer switch,
model retraining or deployment is part of this change. Existing r1/r2 model
and release bytes remain immutable.

## Why the count showed 17/36

The existing published **r1** test generation contains 17 complete XGBoost
paths and 204 monthly predictions. It contains no persistence forecasts.
The separate **r2** generation has 17 XGBoost and 17 persistence paths, 408
monthly predictions and two no-observation states, but remains **staged**.
Changing a frontend filter cannot turn that staged generation into an active
publication. The normal API must not expose it as published.

The existing r2 frontend already accepts persistence and the explicitly marked
local r2 preview on port 5108 returned **34/36**, not 17. Its AP reference was
3.19175 m, consistent with the displayed 3.19 m example. The former published
r1 API evidence and the current source show why release identity matters.
No screenshot file or remote runtime endpoint accompanied this request; the
reproduction uses actual local HTTP responses and source/persisted data.

The corrected summary derives availability and monthly counts from validated
stored forecast arrays, requires a complete twelve-month path, and reports
XGBoost, persistence and unavailable counts separately. A historical observation
alone does not count as a forecast. Release/vintage labels explain which policy
the page is actually displaying. It continues to show 17/36 for r1 and 34/36 for
a verified r2 fixture; neither number is hardcoded into the display.

## Why state history began in 2021

`models/state_median_forecast.py` builds a complete genuine state history, but
its immutable `forecast_state` response serializes only `state.tail(60)`.
At the October 2026 vintage, all 36 stored r1/r2 histories therefore start at
**2021-10-01**, even when earlier genuine and coverage-qualified medians exist.
The r2 persistence wrapper extends the window only when needed to retain an
older reference; it does not recover the entire source history. The district
history endpoint independently defaults to 2002 and retains its own genuine/
imputed provenance, so the two views had different serialization windows.

The correction supplies a separate full-history read pinned to the published
forecast generation, vintage and source. It does not rewrite the old snapshot,
change model inputs or create a new forecast. The approved source manifest,
actual CSV bytes, feature/data/registry identities and coverage rule must match
the selected publication. A configured source override is strict; otherwise
only exact manifest matches in the approved processed-data locations qualify.
Missing/mismatched sources fail explicitly, leaving the forecast available with
its original short history clearly identified as incomplete.

For each state, the full series starts at its first genuine district-based
median and retains every following missing calendar month through the release's
completed input month, **September 2026**. It does not prepend fictitious 2002
measurements. The first coverage-qualified month is separately disclosed.

## Historical coverage before and after

The independent source audit found:

| Metric | Original forecast snapshot | Full source-supported history |
|---|---:|---:|
| Calendar rows across all states | 2,160 | 8,446 |
| Genuine state-month medians | 386 | 2,776 |
| Coverage-qualified state-month medians | 282 | 1,819 |
| States with genuine data | 34 | 34 |
| States with at least one qualified median | 30 | 30 |

The added timeline recovers **2,390 genuine medians**, including **1,537
coverage-qualified medians**. Eighteen states have qualified observations in
2002; twenty-three have at least some genuine data in 2002. AR, MN, MZ and SK
have genuine low-coverage observations but no qualified blue points. LA and LD
have no genuine state history.

Andhra Pradesh expands from 60 rows to 297, beginning January 2002; its genuine
medians increase from 18 visible months to 101, and qualified medians from ten
to 85. Sikkim begins January 2025, has one genuine low-coverage observation,
and never receives an invented qualified historical point. A long calendar does
not imply a measurement exists in every month.

| State / UT | First genuine median | First coverage-qualified median | Full calendar rows |
|---|---|---|---:|
| AN — Andaman and Nicobar Islands | 2013-11-01 | 2013-11-01 | 155 |
| AP — Andhra Pradesh | 2002-01-01 | 2002-01-01 | 297 |
| AR — Arunachal Pradesh | 2002-01-01 | None | 297 |
| AS — Assam | 2013-01-01 | 2013-01-01 | 165 |
| BR — Bihar | 2002-01-01 | 2002-01-01 | 297 |
| CH — Chandigarh | 2013-01-01 | 2013-01-01 | 165 |
| CG — Chhattisgarh | 2002-01-01 | 2002-01-01 | 297 |
| DD — Dadra and Nagar Haveli and Daman and Diu | 2013-01-01 | 2013-01-01 | 165 |
| DL — Delhi | 2013-01-01 | 2013-01-01 | 165 |
| GA — Goa | 2013-01-01 | 2013-01-01 | 165 |
| GJ — Gujarat | 2002-01-01 | 2002-01-01 | 297 |
| HR — Haryana | 2002-01-01 | 2002-01-01 | 297 |
| HP — Himachal Pradesh | 2002-01-01 | 2002-05-01 | 297 |
| JK — Jammu and Kashmir | 2002-01-01 | 2021-08-01 | 297 |
| JH — Jharkhand | 2002-01-01 | 2002-01-01 | 297 |
| KA — Karnataka | 2002-01-01 | 2002-01-01 | 297 |
| KL — Kerala | 2002-01-01 | 2002-01-01 | 297 |
| LA — Ladakh | None | None | 0 |
| LD — Lakshadweep | None | None | 0 |
| MP — Madhya Pradesh | 2002-01-01 | 2002-01-01 | 297 |
| MH — Maharashtra | 2002-01-01 | 2002-01-01 | 297 |
| MN — Manipur | 2004-11-01 | None | 263 |
| ML — Meghalaya | 2002-01-01 | 2002-01-01 | 297 |
| MZ — Mizoram | 2025-01-01 | None | 21 |
| NL — Nagaland | 2002-01-01 | 2023-01-01 | 297 |
| OD — Odisha | 2002-01-01 | 2002-01-01 | 297 |
| PB — Punjab | 2002-01-01 | 2002-01-01 | 297 |
| PY — Puducherry | 2013-01-01 | 2013-01-01 | 165 |
| RJ — Rajasthan | 2002-01-01 | 2002-01-01 | 297 |
| SK — Sikkim | 2025-01-01 | None | 21 |
| TN — Tamil Nadu | 2002-01-01 | 2002-01-01 | 297 |
| TS — Telangana | 2002-01-01 | 2021-01-01 | 297 |
| TR — Tripura | 2002-01-01 | 2002-01-01 | 297 |
| UP — Uttar Pradesh | 2002-01-01 | 2002-05-01 | 297 |
| UK — Uttarakhand | 2013-01-01 | 2023-01-01 | 165 |
| WB — West Bengal | 2002-01-01 | 2013-01-01 | 297 |

Source evidence is
`scratch/state_history_ui_20261030/diagnostics/history_by_state.{csv,json}`.
Counts refer to state-month medians or calendar rows as labelled. The underlying
43,384 genuine district-month observations are not original well counts.

## Graph and evidence semantics

The actual district history reference is `recordedHistoryPlot` in
`dashboard/src/pages/DistrictDetail.jsx`. The state chart adopts its blue
qualified observations, visible markers, axis/tooltip typography and responsive
layout while preserving explicit gaps. District history and model behavior are
not edited.

- Blue markers/line show genuine coverage-qualified medians only, in date order.
  Missing and ineligible months remain null; lines do not connect across them.
- Grey points identify genuine low-coverage medians and have no connecting line.
  They remain ineligible training targets. They are not forward fills.
- Teal dashed markers/line show the actual twelve forecast months, with the
  method explicitly named as XGBoost or persistence. A dashed vertical marker
  identifies the forecast origin.
- Tooltips distinguish historical medians, low coverage and future estimates,
  show state/month/depth and actual historical contributor counts/coverage, and
  label forecast reference coverage as historical reference information. Future
  district coverage is never invented. No forward-filled state values are
  generated or labelled as observations.
- Selected reference depth, date, age, coverage and method update with the
  selected state and the same generation/vintage. Failed full-history reads do
  not silently substitute another state, source or model.

Higher depth in metres below ground means a deeper water table. It does not
measure a proportional change in total groundwater volume. Sparse/stale
references remain disclosed; persistence has no evaluated accuracy and frozen
historical XGBoost backtests do not guarantee future accuracy.

## Implementation and verification

- Python test suite: **1,936 passed, 47 skipped, 70 warnings** (`pytest -q --tb=short`).
- Focused history and API tests: **28 passed in 2.78s** (`tests/test_state_median_history*.py`).
- Frontend test suite: **191 passed in 2.23s** (`npm test --prefix dashboard`).
- Frontend lint: **0 warnings, 0 errors** (`oxlint` across 65 files).
- Production build: built in **320ms** (`vite build`).
- Release verification CLI: both `2026.10.29-r1` and `2026.10.29-r2` verify clean.
- Protected files: no modifications to immutable model files, `models/state_median_forecast.py`, `models/state_median_policy.py`, or release artifacts.

The active-publication boundary is intentional. r2 activation still requires a
separately authorized publication procedure; this task does not change pointers
or deploy to Render, Vercel or any other host.
