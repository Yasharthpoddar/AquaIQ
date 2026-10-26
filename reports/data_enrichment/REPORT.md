# Official-data enrichment and verified local release - 26 October 2026

The selected candidate recovers **5,952 genuine district months** across **639 districts**, including **11 previously unobserved districts**. Coverage remains **725/725 districts, 8,700/8,700 monthly values and 36/36 states/UTs**. Evidence tiers change from 547/104/73/1 to **551 A / 111 B / 62 C / 1 D** without lowering eligibility rules or refitting the model. Training-period and weather feature values are preserved exactly.

## Acquired sources and measurement counts

The [82-entry catalog](../../data_sources/catalog.yaml) and [source inventory](source_inventory.md) distinguish discovered, accessible, downloaded, parsed, integrated and validated resources. Acquisitions include 62 NWDP manual CSVs, four separate telemetry CSVs, two IMD products, CGWB assessment PDFs, scientific sample/index files and metadata. Merely advertised products, metadata-only access, old downloads and actual observation downloads remain distinct. Raw datasets and station-level rows are ignored by Git; per-resource licenses, attribution, exact URLs, dates, sizes and SHA-256 values are committed.

Manual input contains **171,107 rows**: **156,176 accepted timestamps** and **14,931 quarantined rows**. Eight exact old-raw matches, four exact duplicate timestamps and 62 conflicting station timestamps are recorded among the rejection reasons; reasons overlap. There are also invalid depths, colocated labels, ambiguous boundaries, source-state disagreements and old-source conflicts. The full breakdown is in [groundwater evidence](groundwater_sources.json).

Accepted rows form **6,513 candidate district-months** across 641 districts. The overlay retains **561 existing measured means** and inserts **5,952 missing genuine months**. **142,844 accepted source readings** contribute to the newly added months. The feature grid contains **36,890 -> 42,842** genuine district months. [District coverage](source_coverage.csv) records before/after counts and earliest/latest months for all 725 IDs. Comparable old/new raw unions contain **52,304 -> 58,527 conservative station fingerprints** and **1,470,970 -> 1,627,123 distinct station-days**; these are not certified physical well counts.

Quarterly manual dates actually span 2021-01-01 to 2025-01-30. The 2026-2030 manual files are header-only. The protected baseline already includes a separate January 2026 refresh; recovering earlier missing years does not establish uniformly fresh current measurements. Exact station labels/coordinates are matching aids, source district names do not override ambiguous coordinates, and changing well panels still limit comparisons. No imputed value becomes an observation.

## Model and validation results

The candidate keeps the identical XGBoost SHA-256 `4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`. All **156,600 training-period feature rows** are compared exactly through the frozen 2019 target cutoff, and all weather values/definitions remain identical. Candidate feature generation is `physical-v3-official-a891508e320439f9` with CSV SHA-256 `e83990a7fc66e58bd74829f5523dd021dd9cff87894271a99c6202d2a1872115`. Its separate card records the protected parent card/generation and compatibility proof; the deployed model pointer is unchanged.

The [protocol](evaluation_protocol.json) was fixed before metrics. Calibration uses January/July 2021 origins, ending at the July 2022 target. Development origins are October 2022, January 2023 and July 2023. Final origins are July 2024 and January 2025. Both input versions use identical genuine targets, exact calendar horizons and frozen model/tier rules. The development-MAE decision is sealed before final evaluation; protocol, data, cards, model and normalized source-code hashes must match. No final labels change model weights, thresholds, features, intervals or selection.

| Split | Candidate tier at origin | Cases | Old-input MAE (m) | Added-data MAE (m) | Old-input RMSE (m) | Added-data RMSE (m) |
|---|---|---:|---:|---:|---:|---:|
| Development | All | 4,323 | 2.422 | 1.930 | 4.821 | 3.789 |
| Development | A | 3,759 | 2.114 | 1.780 | 4.006 | 3.355 |
| Development | B | 530 | 4.076 | 2.442 | 7.433 | 4.095 |
| Development | C | 34 | 10.628 | 10.568 | 17.885 | 17.876 |
| Development | D | 0 | - | - | - | - |
| Final temporal holdout | All | 843 | 2.451 | 2.247 | 4.583 | 4.067 |
| Final temporal holdout | A | 731 | 2.244 | 2.069 | 4.446 | 3.887 |
| Final temporal holdout | B | 97 | 3.387 | 2.949 | 4.403 | 4.260 |
| Final temporal holdout | C | 15 | 6.452 | 6.352 | 9.581 | 8.700 |
| Final temporal holdout | D | 0 | - | - | - | - |

The retained change is the added measured history with unchanged forecasting methods. Persistence and exact previous-year observed-month baselines use the same origin-available candidate history on their paired available subsets; see [development](final_evaluation/development.json) and [final results](final_evaluation/final.json) for metrics, denominators, districts, horizons, origins and observation-age groups. Tier B/D remain persistence, rather than a newly claimed learned sparse model. Seasonal naive can outperform sparse persistence; no post-test switching was performed.

In the final persistence-paired subset (**828 cases**), candidate MAE is **2.172 m** versus **2.762 m** for the last genuine local depth. In the seasonal-paired subset (**215 cases**), candidate MAE is **1.693 m** versus **1.686 m** for exact previous-year observations; candidate RMSE is **2.507 m** versus **2.618 m**. These subsets have different denominators and must not be compared as one common sample. The data improvement does not establish uniform superiority to seasonal naive.

Natural sparse evaluation increases from the earlier seven-case report to **530 development cases across 91 districts**. Cases share districts/targets and are not independent measurements. The final sample has **843 cases across 640 districts**, with uneven monitoring phases/horizons. It does not validate every monthly trajectory.

Pseudo-cold references exclude all target-district history and never invoke XGBoost trained on that hidden history. Final regional/global/state-blocked reference MAEs are **3.095 / 3.553 / 3.601 m** on identical targets. Out-of-state sensitivity illustrates transfer risk; it does not confer spatial independence on the pretrained XGBoost model.

Intervals use only pre-evaluation calibration, by actual serving tier/horizon. Unsupported horizons remain unavailable. Empirical candidate coverage is **A: 88.4% (3759 cases); B: 75.3% (442 cases); C: 31.2% (16 cases)** in development and **A: 81.8% (731 cases); B: 61.9% (97 cases); C: 20.0% (15 cases)** in the final period. A nominal 90th-percentile residual is not a calibrated local probability; undercoverage and small panels remain explicit. Historical measurement dates do not certify historical publication/availability times. This is a protected temporal split within this experiment, with previously inspected source distributions/model, not blind prospective operational validation.

## Rejected or deferred integrations and corrected defects

* Telemetry: 274,930 records include 264,278 negatives; per-well sign/datum and manual overlap are unresolved. No sign flip or manual pooling.
* IMD 2025 rainfall NetCDF: all 1,811,860 valid values/masks exactly mirror existing annual GRD. Zero new weather values.
* IMD daily maximum temperature: 129,552 valid values, but a different variable/grid from model monthly mean temperature and no evaporation. Direct substitution rejected.
* Newer ERA5: official catalogue advertises September 2026; authenticated observation retrieval and account terms were not verified. It is not classified unavailable. Existing ZIP extraction is fixed with bounded in-memory split-field parsing, matching calendar/spatial axes, explicit 00/06 UTC monthly labels and no-clobber publication. All source arrays equal the existing clean file exactly; weather predictors are unchanged.
* GSDA: metadata producer mismatch and large resource bodies not checked. Mumbai Suburban: no independently verified georeferenced weather attribution; its labelled D fallback remains.
* Resource assessment, soil, land cover and GRACE: context/sample/index/availability evidence acquired as documented, without complete historically available district predictors and a validated transfer model. They do not replace measured depths. No unsupported pooled or hydrogeological model was fitted.
* Candidate publication now verifies all six private base tables and removes public/temp fallback before reads/writes. Overlong PostgreSQL schema names are rejected. Explicit feature snapshots fail closed without their verified CSV.
* Evaluation binds code/cards as well as model/data/protocol. Only LF/CRLF source representation is normalized. Metadata-only performance changes reproduced development predictions exactly.
* Production JavaScript is split into app/map/runtime/chart chunks. Largest chunk is **365.50 kB**, down from 876.52 kB; the 500 kB threshold is unchanged and the bundle-size warning is gone.

## Executed engineering checks and preservation

[Engineering evidence](engineering_validation.json): **1,422 Python tests passed**, 37 explicit integration skips; **38 storage/scoring/isolation integration tests passed** and **39 final overlay/seal/guard tests passed**. Frontend: **155 tests passed**, lint and production build passed. [Nine browser flows](browser.json) exercise real candidate tiers A-D, state navigation, desktop/tablet/mobile layouts and retry states; no page errors. Additional real-score/map/alerts production flows are recorded in auxiliary evidence.

[Release verification](release_verification.json) reads all **761 district/state APIs** with twelve-month inference forbidden, checks 8,700 normalized horizon records and registry/state means, verifies missing-generation/default-vintage behavior and both legacy six-month products. No twelve-month inference occurs during normal reads. The complete generation **`600edc35-506d-501d-82c2-5cc2ebcfe699`** is published only in **`aquaiq_test_enrichment_20261026`**. The original publication remains available.

All **14 public tables** retain identical before/after counts and sorted row-content fingerprints. [Protected inputs](protected_inputs.json) retain baseline raw/features/boundary/model hashes. The risk index is unchanged, historical and uncalibrated. Source/history and six-month endpoints retain the original inputs while twelve-month candidate reads use the new publication; their dates/evidence must be distinguished.

Initial attempts hit disk exhaustion and are not counted as successful tests or publication. The failed run's disposable output and two inspected assistant-created fixture directories were removed after a broader cleanup was rejected; user work/source assets were preserved. A too-long test-schema fixture and a nonportable byte-only code seal were corrected and verified. Earlier development reports under `evaluation/` are superseded by the final code-sealed `final_evaluation/` evidence, without rewriting their historical results.

## Reproduction, remaining limitations and Git

Use the [release guide](../../docs/OFFICIAL_DATA_ENRICHMENT.md) for exact acquisition, preprocessing, phased evaluation, migration, local serving and publication commands. A clean clone requires ignored baseline/runtime/source assets and a restored test database. No private data, credentials, raw acquisitions or generated forecasts are committed. No hosted deployment or fresh-machine restoration is claimed.

Uneven recency, changing wells, conditional historical availability, incomplete monthly holdout coverage, interval undercoverage, uncertified mixed-vintage/Telangana attribution, remaining 62 zero-history districts and Mumbai Suburban weather attribution remain limitations. The 725-district inventory is internal. Auxiliary data and larger model complexity cannot resolve these without further evidence.

During the pause, the repository advanced to user commit `5ef30c346b71d75b2918e71cdcadc13a9e69d06b` on main. This work preserves that commit and finishes on `feature/official-data-enrichment-final`. Only the remaining release-related files are staged; the user's untracked fuzzy tests are preserved. The final commit and verified remote branch SHA are reported after the staged scan and non-force push.
