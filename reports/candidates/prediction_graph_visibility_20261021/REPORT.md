# Prediction graph visibility correction

The graph was on district pages with no direct Home link. Adilabad's default origin (May 2026) supplies no eligible ML estimate, while the historical January 2024 origin supplies one M+12 estimate. Other districts can be outside the saved artifact's scope. The graph card could also disappear behind legacy district loading/error returns or lack dated axes when the origin is unknown. These are distinct conditions; absent ML values have not been manufactured.

## Changes

Home now links to an explicitly labelled Adilabad historical graph example. District pages retain a graph card during legacy loading/errors and provide explicit origin-month, Apply, Latest observed origin and Retry controls. The selected historical origin must match the response; failures never automatically select an older origin. Missing or undated results show an explanatory graph-sized frame. A separate blue M+12 reference marker displays the observed-origin annual baseline. The red ML series retains gaps for months 1-11; neither series becomes a fabricated monthly curve. Map, summary cards, risk calculation and recorded history remain as before this correction.

Open `http://127.0.0.1:5182/district/TS-Adilabad?origin_month=2024-01#forecast-graph`. The existing normal app uses read-only API port 5052; the separate protected demo on 5051/5181 is unchanged. Browser-tab opening was queued by Codex.

## Evidence and limits

Read-only running API checks returned HTTP 200. January 2024 has twelve calendar slots (February 2024-January 2025), exactly one finite ML value at M+12 (7.57110071182251 m below ground) and annual baseline 6.836666666666668 m. The default May 2026 origin has no ML values and a single annual reference of 6.553333333333334 m at May 2027. The new component, district URL and Home also return HTTP 200. See `api_diagnostic.json` and `runtime_http-v2.json`.

This is a historical research estimate, not a prospective forecast or a validated twelve-month monthly path. The saved direct artifact is limited to its existing Adilabad research scope; current inputs and provenance constraints still cause abstention. No additional monthly models were introduced. HGB remains abstained; the artifact has not established superiority to the annual baseline.

43 frontend tests passed, with no failures or skips. Tests cover explicit origin requests, rejection of mismatched origins, unavailable frames, origin controls, discoverability, a separate baseline and unchanged null monthly ML values. Lint, whitespace checks and an isolated production build passed. Build output is under `scratch/prediction-graph-visibility-build-20261021-01`; existing dashboard build files were not overwritten. The build retains a bundle-size advisory. Python tests were not repeated for this frontend-only correction.

Rendered browser pixels were not verified: the browser tool failed before tab access with a local kernel-assets/path error. Server-rendered component tests and Vite/API checks do not replace browser interaction verification. The first HTTP receipt used a reserved PowerShell variable for the Home response; the app was unaffected. The corrected separate receipt confirms Home HTTP 200 and retains the original receipt unchanged.

## Files changed in this correction

- `dashboard/src/pages/DistrictDetail.jsx`
- `dashboard/src/pages/Home.jsx`
- `dashboard/tests/forecastGraph.test.js`
- `dashboard/tests/researchForecast.test.js`
- `dashboard/src/components/ForecastGraphPanel.jsx`
- `dashboard/src/components/forecastGraphPresentation.js`
- `dashboard/tests/forecastGraphPresentation.test.js`

## Preservation

Of 1043 inventoried pre-existing files, 1039 remain byte-identical. The only 4 changed existing files are the four intended frontend/test files above; the other three listed source files are new. No inventoried data, model code/artifacts, API files, previous reports or dashboard/dist files changed. Existing user changes remain present. HEAD is unchanged at `3a4936b6950b76dc7413ccfbabace30b67e5891e` and the index is empty. No model training/tuning, pipeline execution, data download, database writes, forecast issuance, checkpoint promotion, commit or push occurred. Preservation is a file-hash check and a record of actions; database contents were not independently compared. See `preservation.json`.

## Reproduce safe checks

```powershell
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
# Choose a new absent output directory for each build.
npm.cmd --prefix dashboard run build -- --outDir ../scratch/prediction-graph-visibility-build-NEW
```

The remaining demonstration check is to visit the link in the running app, confirm the red M+12 point and separate blue baseline, then select Latest observed origin and confirm the explicit ML-unavailable message. A continuous monthly curve requires an explicitly approved method and scientifically supported artifacts; it is not a presentation fix.
