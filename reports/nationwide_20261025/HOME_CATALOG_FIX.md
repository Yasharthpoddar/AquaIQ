# Home navigation repair — 2026-10-26

The Home screenshot showed `awaiting_complete_scoring_run` from `/api/scores`, four empty risk cards and a disabled district search. The twelve-month generation was available, but Home and Simulate incorrectly used completed risk-score records as their district catalog. Risk scoring has a separate model/configuration/code signature; the absence of a matching risk run is not evidence that district forecasts are unavailable.

Added `/api/districts`, backed only by the validated canonical registry. It returns all registered identities without querying scores, loading forecasting artifacts or running inference. Home and Simulate load this catalog independently and merge optional scores by canonical ID, preserving names/state membership and legitimate zero scores. Unrelated score IDs cannot enter the catalog.

Home now shows the actual published evidence mix (547 A, 104 B, 73 C, 1 D; 725 complete outputs) with a compact explanation when the separate risk index is absent. Actual available risk cards/rankings are retained. Search and registered map polygons remain navigable without risk scores. Grey map shading explicitly means no published risk index; it does not label groundwater forecasts unavailable. Map polygons also support keyboard navigation. Registry errors have their own retry state and do not hide independently loaded forecast coverage.

Verification executed:

- `python -B -m pytest -q tests/test_district_catalog_api.py tests/test_api.py --basetemp=scratch/pytest-home-catalog`: **22 passed**.
- `npm --prefix dashboard test`: **155 passed**, zero failures.
- `npm --prefix dashboard run lint`: passed without warnings.
- `npm --prefix dashboard run build -- --outDir ../scratch/home-catalog-build`: passed; the existing large JavaScript chunk warning remains.
- `node dashboard/tests/homeCatalogBrowser.cjs`, using the existing Playwright and Chrome installation against the running local app: **six browser scenarios passed**, zero page errors. Tests reproduce empty, failed and delayed score responses; navigate via map/search to a real supported forecast; open a real zero-history reference; select a district in Simulate; and exercise an actual registry failure/retry. Layout inspected at 1440, 768 and 390 pixels without horizontal overflow.

The source data, model weights, calibration, generation identity and production database are unchanged. No risk score is fabricated and no scoring job is launched by a normal API request. The validated local forecast namespace remains in use. The frontend and backend remain running on ports 5173 and 5000.
