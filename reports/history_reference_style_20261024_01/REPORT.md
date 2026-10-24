# History chart reference styling

24 October 2026. Local branch `codex/next-12-months-ux`; uncommitted and unpublished.

Matched the user's requested visual style with a thin blue observation trend, white-centred observed dots, grey forward-filled history, light grid, depth-axis label, observed-first legend and a taller 360-pixel chart. Retained concise interpretation: higher depth means a lower water level.

The blue lines are visual guides between original observed endpoints within each contiguous available monthly block. They may span intervening forward-filled buckets. Explicit or inserted missing months split the blocks, so no guide crosses a genuinely unavailable interval. Filled-only blocks and isolated observations cannot create an observed trend line. No interpolated measurement rows are generated. All original points, flags and values remain unchanged.

Implementation files changed:

- `dashboard/src/components/recordedHistory.js`: splits observation guides at genuine calendar gaps; reuses original row objects.
- `dashboard/src/pages/DistrictDetail.jsx`: reference styling, guide lines, compact explanation and safe tooltip formatter preserving provenance names and units. Full monthly data remains on the chart; categorical month alignment is explicit.
- `dashboard/tests/recordedHistory.test.js`: regression coverage for blue guides, exact endpoint values, finite zero, explicit/absent gaps, unchanged rows and filled-only/isolated cases. Updated the previous dashed-connector expectation for the newly requested presentation.

Verification:

- Targeted history tests: **9/9 passed**.
- Configured frontend suite: **101/101 passed**, exit 0 (`frontend-tests.txt`).
- Configured lint and production build: passed, exit 0 (`lint.txt`, `build.txt`). Build output is isolated under this new report directory; the existing `dashboard/dist` was preserved. The existing >500 kB bundle-size advisory remains.
- `git diff --check`: passed.
- Browser, actual Kaithal data: **77 observed dots** retained. Four guide blocks contain **76 original observed endpoints**; every rendered guide vertex aligns with an observed dot within 0.02 pixels. The remaining isolated observation retains its dot. Only the two intended legend entries appear.
- Keyboard tooltips distinguish `2002-01 / Source-marked observation / 8.58 m` from `2002-02 / Forward-filled history / 8.58 m`, without duplicate guide entries.
- Checked desktop 1366 × 900 and mobile 390 × 844. Mobile document width equalled viewport width (382 CSS pixels after scrollbar exclusion), with no page overflow. Reset viewport override after checking. Screenshots: `history-desktop.jpg`, `history-mobile.jpg`.
- **1,467 protected files unchanged**, including datasets, models, backend/configuration and older audit reports (`preservation.json`). Earlier completed report text/results remain intact; normal preview serving appends to its existing log.

Reproduction from the repository root:

```powershell
node --test dashboard/tests/recordedHistory.test.js
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../reports/history_reference_style_REPRO_NEW/build
git diff --check
```

No backend changes, new dependencies, training, backtests, data updates or database mutations were needed. The reference image's unrelated forecast/model wording was not copied. This work changes chart presentation and makes no new scientific accuracy claim.
