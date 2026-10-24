# History hover and continuous visual trend

24 October 2026. Local branch `codex/next-12-months-ux`; no commit or push.

Fixed two causes of incorrect or missing history tooltips: decorative lines shared the observed series' tooltip key, allowing a hidden entry to displace an observation; short per-line datasets could also clamp pointer indexes intended for the full monthly calendar. Earlier keyboard-only checks did not catch the later-year pointer case.

All chart lines now use the full original monthly dataset. Decorative guides use distinct functional selectors rather than short datasets. The custom hover tooltip resolves the month directly from that calendar and shows the original value and observed/filled status. `filterNull={false}` allows explicit unavailable content for missing months. Hover is axis-based, so the user can point within the plot rather than target a small dot; keyboard and tap interaction remain available.

The user's latest request for visual continuity is implemented with dashed bridges over missing periods. Solid portions remain observation guides within available history. Each dashed bridge joins two adjacent original observed endpoints; it adds no monthly values or dots and does not extend beyond the first or last observation. Hovering the missing portion reports **No recorded value**, never an interpolated depth. This intentionally updates the previous request to leave the line visually broken, while retaining the original null data and making missing periods explicit.

Changed implementation files:

- `dashboard/src/components/recordedHistory.js`: full-calendar endpoint selectors and dashed-gap endpoint pairs.
- `dashboard/src/pages/DistrictDetail.jsx`: full-month hover tooltip, root-data-only guides, dashed continuity and concise interpretation.
- `dashboard/tests/recordedHistory.test.js`: original-value/zero/status tooltips, missing-month messages, later-year lookup, no short guide datasets, no synthetic gap values, and no extrapolated endpoints.

Verification:

- Targeted history tests: **14/14 passed**.
- Configured frontend suite: **106/106 passed**, exit 0 (`frontend-tests.txt`).
- Configured lint and build: passed, exit 0 (`lint.txt`, `build.txt`). Build output is isolated in this report directory; the original `dashboard/dist` is preserved. The existing >500 kB bundle advisory remains.
- `git diff --check`: passed.
- Actual pointer-driven browser interactions in Kaithal: latest observed dot showed **January 2026 / Source-marked observation / 24.28 m below ground**; first filled dot showed **February 2002 / Forward-filled value / 8.58 m below ground / Not a new measurement**; the long dashed bridge showed **July 2023 / No recorded value for this month / Visual guide only**. Pointer movement during locator clicks exercised hover handling, not just keyboard navigation.
- Desktop 1366 × 900 and mobile 390 × 844 checked. On mobile, tooltip bounds were approximately x=115–319 within a 382-pixel document viewport, and page width also measured 382. Viewport override was reset afterwards.
- Screenshots: `observed-hover.jpg`, `missing-month.jpg`, `mobile-hover.jpg`. Browser focus outlines from pointer selection may be visible.
- **1,467 protected files unchanged** (`preservation.json`). Model/data/backend/configuration and older audit files match their original hashes. Previous reports/results were not rewritten. Normal preview serving appends to its existing log.

Reproduction from the repository root:

```powershell
node --test dashboard/tests/recordedHistory.test.js
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build -- --outDir ../reports/history_hover_REPRO_NEW/build
git diff --check
```

No backend contract, dependency, training, model, dataset or database contents were changed. The visually continuous guide does not establish measurements in missing periods or any new forecasting accuracy.
