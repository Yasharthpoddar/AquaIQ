# Recorded-history connecting line fix

24 October 2026 (Asia/Kolkata), local branch `codex/next-12-months-ux`. No commit or push.

The observed and forward-filled series contained alternating nulls. Their separate `connectNulls={false}` lines stopped at each switch, so the graph showed mostly isolated observed dots and short filled segments even when adjacent months had available values.

Added a dashed grey background connector using each month's existing observed or forward-filled value. Existing blue observed points/solid adjacent-observation segments and filled markers remain above it. Explicitly missing and absent calendar months still resolve to null and break all lines. The connector has no extra tooltip entry, legend entry or dots. No values are interpolated, imputed or changed by this fix.

Changed only these implementation files since the previous completed UX work:

- `dashboard/src/components/recordedHistory.js`: accessor for existing available values, preserving finite zero and null gaps.
- `dashboard/src/pages/DistrictDetail.jsx`: connector and compact explanation of its dashed style.
- `dashboard/tests/recordedHistory.test.js`: regression for alternating observed/filled values, finite zero, explicit/absent missing months and actual chart properties.

Verification:

- Targeted history tests: **8/8 passed**.
- Configured frontend suite: **100/100 passed** (`frontend-tests.txt`).
- Configured lint: passed, exit 0.
- Configured build: passed, exit 0 (`build.txt`). Used a new report-local output directory to preserve `dashboard/dist`. The existing >500 kB chunk-size advisory remains.
- `git diff --check`: passed.
- Real browser: Kaithal history now renders a dashed connector with **225 line segments across five separate paths**. All **230 existing data dots** remain; the four genuine breaks are still visible. Observed and filled series retain their original separate data. No duplicate legend item appears.
- `history-chart-screen.jpg` is the final corrected-chart viewport, captured with the documented screen-snapshot API and reopened for verification. `history-connections.jpg` is an earlier incorrect clip of another page region, retained as an unsuccessful capture. `history-trend-verified.jpg` is an intermediate viewport capture; use the final file above.
- Preservation check: all **1,467 protected model, data, backend/configuration and older audit files** match the original baseline (`preservation.json`). Only the three expected frontend files differ from the previous completed frontend manifest. Prior completed report text/results were preserved. Normal preview requests append to the existing server log.

Commands from the repository root:

```powershell
node --test dashboard/tests/recordedHistory.test.js
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../reports/history_trend_fix_20261024_01/build
git diff --check
```

Use a fresh output directory when reproducing the build. Backend/model/data code did not change; no training, backtest or database mutation was run. This is a graph-rendering correction and makes no new accuracy claim.
