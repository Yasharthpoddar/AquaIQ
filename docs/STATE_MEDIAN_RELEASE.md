# Primary States median release

The subsequent [r2 coverage policy](STATE_MEDIAN_COVERAGE.md) adds explicit
persistence forecasts for every state with genuine observations while retaining
the XGBoost safeguards. It is generated/staged/validated locally, not published.
The r1 artifact and publication described below remain immutable. Do not run the
publication/deployment commands below as part of the coverage-fix task.

## Product selection and compatibility

The main States page selects `state_median_xgboost` by default. It has one
primary median chart and uses the same median generation for cards, map and
comparison table. Historical reference depths are explicitly dated, not
relabeled as current estimates. The forecast line is dashed, history and
forecast remain separate, low-coverage observations are grey, missing months
remain gaps, and unavailable states retain history and district navigation.
There is no implicit fallback to an old state mean.

`/api/v2/states`, `/api/v2/states/summary` and
`/api/v2/predict/state/<state_id>` serve published median releases. Unknown
states, malformed/repeated parameters and unsupported horizons follow existing
404/400 conventions. Missing/corrupt/mismatched releases return explicit 503
availability responses. Registry navigation remains available without a
publication. Summary and detail are pinned by exact generation UUID plus
vintage. Published reads validate stored identities and never load model files,
train or infer. There is no active-pointer response cache that can mix releases.

Existing `/api/states/summary` and `/api/predict/state/*` remain compatible;
`model=current` explicitly selects their legacy method. Home continues using
that summary. District routes, source features, model bytes, configurations,
predictions and dashboard behavior are untouched.

Depth is in `m_bgl`; larger values indicate a deeper water table. Medians
describe reporting districts, not groundwater volume, total availability,
arithmetic mean or the most depleted district. Reporting/well composition can
change between months. Software publication does not establish scientific
validation: evidence remains **limited/experimental**.

## Artifact and chronological procedure

The release artifact is `2026.10.29-r1`, separate from the earlier frozen
experimental artifacts; the model algorithm remains `1.0-state-median-xgboost`.
The latest verified supplied snapshot is
`data/processed/enrichment/final_release_20261026_v3`, generation
`physical-v3-official-c9ade81d95720f91`, CSV SHA-256
`3a4a560667d732b50c6a1712f4d9ceb13b411d4ae2c7a984e08ffc2aada21042`.
It has 43,384 genuine district-month observations, with a completed source
calendar through September 2026. This is richer than the original 36,890-row
observation snapshot; its evidence is kept separate.

Fixed existing parameters, eligibility rules and causal feature engineering
are reused. Development fitting ends in 2016; later chronological origins are
diagnosed without tuning. A separate frozen state artifact refits through
December 2019 for retrospective tests. Its matching district baseline uses
unchanged frozen model bytes with the V3-bound checkpoint. Tests use December
2020–December 2021 monthly origins plus December 2022/2023/2024/2025: 17
predeclared origins covering all horizons and later observation rounds. This
schedule was chosen for horizon/year coverage and bounded runtime, before
inspecting the new scores. Three independent processes replay disjoint origins
and merge only matching source/artifact identities; exact serial/partitioned
reproducibility is tested.

The serving artifact then refits fixed parameters to all eligible targets
available by September 2026. No test-outcome hyperparameter selection occurs.
Its latest actual qualified labels are January 2026; both the allowed cutoff
and each state's last actual training label are recorded. Historical test
metrics describe **frozen 2019 weights**, not held-out evaluation of the latest
refitted weights. The UI shows evaluated horizons, dates, per-state cases and
distinct targets, with separate comparison-wide sample fields. Repeated
state-month targets at different origins are dependent. Source month labels do
not prove publication/acquisition times; climate/reanalysis timing remains a
retrospective assumption. No future climate is supplied.

The immutable release contains only model files/cards, an evaluation report and
a manifest; raw observations and source exports are not bundled. The manifest
records source/registry hashes, feature schema, fixed parameters, training
cutoff, exact Python/package versions, algorithm/model/card/report hashes and
artifact version. Missing/corrupt/incompatible assets fail closed. A changed
source, runtime, algorithm or feature schema requires a new artifact directory.
Exact Python patch versions are currently checked; match the recorded runtime
when building the serving image (this prepared refit uses Python 3.13.15).
The state model implementation and artifact tree have byte-preserving Git
attributes, so checkout line-ending conversion cannot invalidate their hashes.

## Prepared release and executed results (2026-10-29)

The prepared immutable directory is
`models/artifacts/state_median_releases/20261029-r1/` (17 models, model card,
historical evaluation and release manifest). Manifest SHA-256 is
`4f49c06c40fe96983219c611c483dbcfc87d40937a513fb03023d0fc8851e512`;
model-card SHA-256 is
`2ab75da0eeb8dbd8c98a61a275d24e7b76a87582fd8161cfd91b2995d48f0be8`.
The allowed training cutoff is `2026-09-01` (month label), with last actual
qualified training targets on `2026-01-01`. Runtime versions are Python
3.13.15, NumPy 2.5.4, pandas 3.0.6, scikit-learn 1.9.1 and XGBoost 3.4.1.

The **local test** publication is
`eaabeba7-a554-59a6-9110-726221e63cb2` in
`aquaiq_test_state_median_primary_20261029`, vintage October 29, 2026. It has
17 forecasts for November 2026–October 2027 and 19 explicit insufficient-data
states. No median tables were created in `public`; the previous public district
generation count and identity remained unchanged. An independent actual-data
regeneration reproduced all 36 forecast paths exactly. Publishing that second
snapshot and rolling back restored the first UUID; the final active test
publication is the UUID above. Neither publication touched production records.

The V3 historical run attempted **7,344 cases** (36 states × 17 origins × 12
horizons). There were 1,362 coverage-qualified cases across 30 states,
representing 334 distinct state-month targets. The exact matched panel has
**892 forecast cases across 17 states, 208 distinct state-month targets and 23
observation dates**:

| Method | MAE (m) | RMSE (m) |
|---|---:|---:|
| Unchanged production tiered district mean | 1.738870 | 2.544091 |
| Frozen state median XGBoost | 1.126714 | 1.595665 |
| Qualified state-median persistence | 1.382641 | 1.832331 |

Candidate error changed by -0.612156 m MAE (-35.20%) and -0.948426 m RMSE
(-37.28%) against production on identical cases. All horizons 1–12 have
observations, but their evidence is uneven: M+12 has only 68 cases across six
observation dates in January–November 2022. Repeated forecasts reuse 208 targets
892 times, with at most 12 forecasts per target. The candidate was worse than
the production baseline by state MAE in JH, KA, MH, MP and TN. The global error
reduction does not establish universal or current forecasting skill.

Production could score all 1,362 eligible cases; the candidate could score
892. Its other 470 cases include 461 insufficient-history and nine stale
reference failures. Persistence has 1,343 available cases. These unmatched
panels cannot be directly compared to infer improvement. Matched target
coverage bins contain 76 cases at 50–<75%, 143 at 75–<90%, and 673 at 90–100%.
The complete state/horizon/origin/coverage results and failure cases are in
`scratch/state_median_primary_20261029/backtest/{evaluation.json,cases.csv,comparison.md}`.
The evaluation JSON is also bundled with the release. Independent serial
December 2020 replay exactly reproduced all 432 attempted rows and all origin
metrics; its evidence is in `backtest_repro_dec2020/reproducibility.json` under
the same scratch run. These results describe the **frozen December 2019 model**;
they do not validate the latest refitted weights. The primary selection is a
product decision with explicit limited evidence, not promotion of an accuracy
claim.

Executed verification:

- Full Python regression: **1,860 passed, 46 skipped**. Two subsequently added
  release guard/status checks passed in the focused release run.
- Focused median/model/evaluation/storage/API/release/deployment selection:
  **123 passed with `--integration`**, including complete PostgreSQL snapshots,
  actual transaction-failure atomicity, source/artifact corruption, missing
  vintages and exact publication/rollback behavior.
- A fresh legacy persisted summary/state/district API regression plus new
  release tests: **30 passed**, using a newly computed real district fixture
  and clearing the local legacy namespace override only in that test process.
  The local `.env` was preserved.
- Frontend: **179 passed**, lint and final production build passed; the legacy
  rollback build was also executed successfully.
- All **36 actual v2 persisted API responses** passed the real frontend
  contracts and rendering checks, including 2,160 history rows, 204 forecast
  rows and all 36 comparison rows. Runtime median startup readiness passed
  against the exact local artifact and published manifest.
- Real browser inspection at desktop 1280×900 and mobile 390×844 verified the
  single chart, history/forecast boundary, dashed forecast, 12 monthly values,
  state selection and an insufficient-data Telangana view with history and no
  forecast table. Mobile page width was 389 px in a 390 px viewport. Screenshots
  and validation JSON are in the local scratch run. The viewport was restored.
- Compose and CI YAML parsed; `git diff --check` passed. Docker/target-host and
  remote CI runs were not executed.

The original district model remains SHA-256
`4b22e2165664e1c1dd21c81ccf95d894655f0a0d589017a9ab87df0588a73a03`.
No district methodology/configuration/artifact/dashboard file was changed.
Existing uncommitted experimental work was preserved and extended. No commit,
push, merge, production database change or deployment occurred.

## Reproduce preparation and local release validation

Use the existing project Python environment, restored V3 verified snapshot,
matching frozen bundle and private PostgreSQL configuration. Use new paths on
every run. No command below downloads inputs, changes district artifacts or
writes production records.

```powershell
$medianPython = '.\venv\Scripts\python.exe'
$source = 'data/processed/enrichment/final_release_20261026_v3'
& $medianPython -B -m scripts.state_median_forecasts train --artifacts scratch/median_new/frozen --train-cutoff 2019-12-31 --processed-dir $source
$origins = @('2020-12-01') + (1..12 | ForEach-Object { '2021-{0:00}-01' -f $_ }) + @('2022-12-01','2023-12-01','2024-12-01','2025-12-01')
& $medianPython -B -m scripts.backtest_state_median --artifacts scratch/median_new/frozen --processed-dir $source --checkpoint "$source/frozen_bundle/checkpoint.json" --origins $origins --workers 3 --output scratch/median_new/backtest
& $medianPython -B -m scripts.release_state_median prepare --release-dir models/artifacts/state_median_releases/NEW_RELEASE --artifact-release NEW_RELEASE --processed-dir $source --as-of 2026-10-29 --evaluation scratch/median_new/backtest/evaluation.json --evaluation-artifacts scratch/median_new/frozen
& $medianPython -B -m scripts.release_state_median verify --release-dir models/artifacts/state_median_releases/NEW_RELEASE --expected-release NEW_RELEASE
& $medianPython -B -m scripts.release_state_median generate --release-dir models/artifacts/state_median_releases/NEW_RELEASE --processed-dir $source --as-of 2026-10-29 --output scratch/median_new/generation.json --test-schema aquaiq_test_median_new
# Substitute the exact staged UUID returned by generate:
& $medianPython -B -m scripts.release_state_median publish --release-id STAGED_UUID --expected-active none --reason 'Validated isolated release' --test-schema aquaiq_test_median_new
& $medianPython -B -m scripts.release_state_median status --test-schema aquaiq_test_median_new
$env:AQUAIQ_STATE_MEDIAN_SCHEMA='aquaiq_test_median_new'
$env:AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE='NEW_RELEASE'
& $medianPython -B -m api.app
```

`--trained-artifacts` can reuse a separately trained latest refit only after
checking its exact source, cutoff, configuration, registry, schema and model
hashes. It cannot reuse the frozen historical artifact as the latest refit.

Validation commands executed with the project environment:

```powershell
& $medianPython -B -m pytest -q
& $medianPython -B -m pytest tests/test_state_median_forecast.py tests/test_state_median_evaluation.py tests/test_state_median_storage.py tests/test_state_median_api.py tests/test_state_median_release.py tests/test_state_median_release_storage.py tests/test_state_median_v2_api.py tests/test_deployment_readiness.py -q --integration
npm test --prefix dashboard
npm run lint --prefix dashboard
npm run build --prefix dashboard
node scratch/state_median_primary_20261029/validate_frontend.mjs scratch/state_median_primary_20261029/api_bundle.json
```

The legacy DB regression requires the test process to clear the unrelated local
`AQUAIQ_FORECAST_SCHEMA` override before pytest; `.env` is not edited. The new
median storage uses its dedicated namespace independently. CI now includes
private median publication/migration tests and a legacy States rollback build;
remote CI execution remains outstanding.

## Publication, production deployment and rollback

Migrations 006 and 007 are additive and independent of legacy source/district
tables. The median migration command applies only these migrations in the
dedicated `AQUAIQ_STATE_MEDIAN_SCHEMA`. Existing `db.init_db` remains compatible
with its original 003–005 migration history. Test schemas auto-migrate when
explicitly selected; production stage/read paths do not auto-migrate.

Staging validates all 36 responses, their source/model/report identities,
monthly dates, units, coverage, history, statuses and finite values inside one
transaction. A stage is invisible to primary reads. Publication revalidates
stored content, records an immutable publication event and switches one active
pointer transactionally under an advisory lock. Failure preserves the old
pointer and event history. `--expected-active` provides compare-and-swap safety.
Rollback can select only a previously published immutable release. All these
operations preserve district and legacy state tables.

**Production was not deployed or published by this work.** The target host,
its credentials/search paths, restored assets, Linux container runtime, serving
role permissions, HTTPS and recoverable backup must be verified by the release
operator. Local schemas are not production schemas. Docker was not available
in the inspected local shell, so container deployment is not claimed.

After explicit authorization, use the separate schema-write role and the
target database configuration. First take and **test restore** a full database
backup plus current image/config/artifact hashes. For example, with the target
PG connection variables configured privately and `pg_dump`/`pg_restore` on PATH:

```powershell
pg_dump --format=custom --file=backups/before_state_median.dump
pg_restore --list backups/before_state_median.dump
# Restore into a separate empty recovery database and verify it before proceeding.
pg_restore --exit-on-error --dbname=RECOVERY_DATABASE backups/before_state_median.dump
```

The CLI checks only backup existence/custom-format header/size; it cannot prove
a restore was tested. Set `AQUAIQ_STATE_MEDIAN_SCHEMA` to the reviewed production
schema (normally `public`), never `aquaiq_test_*`. Then:

```powershell
& $medianPython -B -m scripts.release_state_median migrate --allow-production-write --backup backups/before_state_median.dump
& $medianPython -B -m scripts.release_state_median stage --release-dir models/artifacts/state_median_releases/20261029-r1 --input APPROVED_GENERATION.json --allow-production-write --backup backups/before_state_median.dump
& $medianPython -B -m scripts.release_state_median publish --release-id STAGED_UUID --expected-active PREVIOUS_UUID_OR_none --reason 'Authorized primary States release' --allow-production-write --backup backups/before_state_median.dump
```

Configure `deploy/.env` privately with read-only serving credentials and:

- `AQUAIQ_STATE_MEDIAN_SCHEMA`: reviewed production schema.
- `AQUAIQ_STATE_MEDIAN_ARTIFACT_DIR`: exact image path to the release.
- `AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE`: exact artifact version.
- `AQUAIQ_STATE_MEDIAN_MANIFEST_SHA256`: verified file checksum.
- `AQUAIQ_REQUIRE_STATE_MEDIAN_RELEASE=true`.

The API image includes `models/artifacts`; `.dockerignore` excludes scratch and
private data. Ensure the exact release directory is in the build context and
the image Python/package versions match the manifest. Startup independently
verifies the local manifest against the actual published manifest and all 36
pinned API responses, in addition to unchanged district release readiness.
The serving role needs schema USAGE and SELECT on the five median tables;
it does not need migration, stage or publication permissions.
Set `AQUAIQ_PYTHON_IMAGE` to a target-verified image/digest with the recorded
Python version; Compose forwards it as the API build argument. The existing
default is `python:3.13-slim`, whose resolved runtime must still be verified.
No specific image digest or target container build was verified locally.

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d
docker compose --env-file deploy/.env -f deploy/compose.yaml ps
```

Verify health, all v2 states, exact generation/version, unavailable states,
desktop/mobile navigation and unchanged district/Home pages on the target.
Do not call local validation a deployment. Preserve previous publication UUID,
image and configuration to recover:

```powershell
# Median artifact rollback; update expected artifact/version/hash to the prior release too.
& $medianPython -B -m scripts.release_state_median rollback --release-id PREVIOUS_UUID --expected-active CURRENT_UUID --reason 'Authorized rollback' --allow-production-write --backup backups/before_state_median.dump
# Restore prior mean-based States UI if the product selection must be reversed:
docker compose --env-file deploy/.env -f deploy/compose.yaml build --build-arg VITE_STATE_FORECAST_MODE=legacy web
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d web
```

The legacy UI continues using compatible legacy APIs; it does not change
district predictions or delete median records. For the first median release,
where no earlier median UUID exists, restoring the legacy web image/build is
the product rollback. Set `AQUAIQ_REQUIRE_STATE_MEDIAN_RELEASE=false` only if
restoring a deployment without any median artifact, and preserve its other
district readiness requirements. No destructive database restoration is needed
for an ordinary median pointer/UI rollback.
