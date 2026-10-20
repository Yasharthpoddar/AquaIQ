# Prospective shadow-evaluation infrastructure

**Submission status: real shadow issuance remains NO-GO.** The [latest issuance investigation](../reports/provenance_issuance_20261019/REPORT.md) identifies unresolved source timing, well-panel, observation and effective-lead requirements. Commands below describe an interface, not authorization to start a campaign or build an artifact. Numerical release proposals in earlier design notes are not approved sufficiency criteria. HGB remains abstained; no prospective skill or production readiness is claimed.

This is an isolated file ledger for direct six-month forecasts. It does not fit or load a model, connect to the database, publish production predictions, or establish forecasting skill. The existing production checkpoint and completed experiments remain unchanged.

The research candidate remains **`hist_gradient_boosting-2-delta`** from `reports/candidates/six_month_selection_20261017/experiment_v2/selection_lock.json`. Its training-label cutoff remains **2018-12-31**, with the same 14,817 eligible training pairs specified by the completed experiment. The locked settings are `max_iter=250`, `learning_rate=0.05`, `max_leaf_nodes=31`, `min_samples_leaf=50`, `l2_regularization=20.0`, `early_stopping=False`, `random_state=42`; the response is change from the observed origin depth, added back to that depth and clipped at zero. No setting is selected again here.

No serialized final HGB shadow artifact exists or is approved. Every real HGB record therefore contains `status="abstained"`, a null prediction, and `shadow_artifact_not_approved`. Its model artifact hash is absent, rather than falsely identifying a fitted model. Persistence and seasonal naive can be archived independently when their required observed inputs exist. Only the synthetic lane accepts an explicitly supplied, **untrained placeholder** HGB number.

## Reused components and isolation

Inspection covered `models/six_month_selection.py`, its locked `experiment_v2` protocol/settings, `models/prospective_validation.py`, `scripts/record_live_forecasts.py`, and `preprocessing/features.py`, alongside the diagnostics reports. The existing research pipeline supplies the canonical feature order, direct six-month target, settings and cutoff. Its historical calendar joins do not supply publication or receipt timestamps. The older prospective utility supplies useful conventions for timezone-aware evidence and create-only archives, but serves a different production projection and is not a direct-six-month adapter.

`models/shadow_ledger.py` implements the new contract without importing the production serving pipeline, training libraries or database connectors. `scripts/shadow_evaluation.py` is its offline-first command interface. No existing scheduler or production route invokes either component. Real inputs must be exported through a separately reviewed point-in-time adapter; this implementation does not infer missing timestamps from month indexes or file modification times.

## Evidence lanes and timestamps

Each new ledger has one immutable campaign ID and one lane:

| Lane | Meaning |
|---|---|
| `prospective` | Actual runtime issuance; callers cannot supply `issued_at`. Eligible labels must subsequently be newly acquired observations. |
| `retrospective` | Historical replay, explicitly separate from prospective evidence. Historical issuance supplied here cannot establish archived-in-advance skill. |
| `synthetic` | Invented demonstration/test evidence. Sources, wells, districts and evidence are explicitly marked synthetic; no scientific skill claim is permitted. |

All acquisition, period-end, publication, receipt, availability, registration and issuance timestamps require explicit timezone offsets. The prospective CLI has no issuance timestamp or clock override. The core uses its runtime UTC clock; the private fake clock in `demo` is restricted to synthetic examples.

For every present input, the source revision must be identifiable and the validated chain is:

```text
observed_at <= period_end <= published_at <= received_at <= available_at <= issued_at
```

Input calendar months must match the registered origin and exact lags. A complete monthly weather aggregate cannot claim availability before its month has ended. Any future, late, inconsistent or unversioned present input rejects the entire forecast transaction; it does not silently substitute another vintage. A genuinely absent input is explicit (`value: null`, `missing_reason`), which permits an archived abstention. Missing or unobserved origin/seasonal values do not become baseline predictions.

The nominal target remains `origin_month + 6`; the exact seasonal reference is `target_month - 12`, hence `origin_month - 6`. Evaluation separately checks actual lead between runtime issuance and the earliest target acquisition. Complete origin-month inputs will generally prevent a six-full-month claim for that nominal target. The ledger does not move targets or shorten the claim to conceal that incompatibility.

## Schema v1

The JSON schema is validated by code. Forecast inputs are one object; caller-supplied predictions are not accepted for real evidence.

| Forecast snapshot field | Required content |
|---|---|
| `district_id`, `origin_month` | Canonical district ID and exact `YYYY-MM` origin bucket. |
| `evidence_kind` | `real_observation`, or `synthetic_fixture` in the synthetic lane. |
| `panel` | `panel_id`, `version_id`, `geography_sha256`, timezone-aware `registered_at`, `units="m_bgl"`, `datum="below_ground_level"`, and unique `wells=[{well_id, weight}]`. Weights are fixed and sum to one. |
| `sources` | Unique `{source_id, version_id, sha256, published_at, received_at}` identities for the supplied inputs. Hashes identify exact source bytes; upstream authenticity still needs independent verification. |
| `inputs` | Per-value evidence envelopes for the ten fields below. |
| `synthetic_hgb_prediction` | Optional synthetic-only untrained placeholder; forbidden for real forecasts. |

Each present input envelope is `{value, units, month, source_id, version_id, observed_at, period_end, available_at, is_observed}`. A missing envelope is `{value: null, missing_reason: "..."}`. Values must be finite. Verified signed source depths are retained in metres below ground; a negative artesian reading is not silently removed or clipped. Persistence, seasonal naive and observed labels retain those signed values. Only HGB's eventual prediction has the zero clipping already fixed by the locked research contract.

| Input | Calendar month | Units |
|---|---|---|
| `gwl_current` | Origin | `m_bgl` |
| `gwl_lag_3mo` | Origin − 3 | `m_bgl` |
| `gwl_lag_6mo` | Origin − 6 | `m_bgl` |
| `seasonal_reference` | Origin − 6 | `m_bgl` |
| `rainfall_current`, `rainfall_3mo_avg` | Origin release | `mm/month` |
| `monsoon_deficit_pct` | Origin release | `percent` |
| `temperature` | Origin release | `degC` |
| `evapotranspiration`, `water_balance_proxy` | Origin release | `mm/month` |

An eventual approved artifact must retain the exact fourteen-feature order: the nine numerical model inputs above excluding `seasonal_reference`, three encoded crop-season indicators, and origin-month sine/cosine. The `seasonal_reference` is a baseline input, not an additional HGB feature. Its transformer/encoding, any fitted state, native missing-value behavior, clipping, model binaries, configuration, source code and software versions must be frozen. This phase records and hashes the locked contract; it does not create those fitted weights or preprocessing state.

A committed forecast envelope contains a content-hashed immutable `record`, ledger commit linkage, campaign/lane identity, runtime issuance, complete supplied input and panel snapshots, locked configuration identity and three prediction slots. Each slot has `status`, `prediction_m_bgl` and `reason_codes`. An unapproved real HGB artifact is always an abstention. Panel identity is a canonical hash of membership, weights, version, datum and geography, not a post-outcome matched-well intersection.

An observed-label input contains:

```text
district_id, month, depth_m_bgl, units="m_bgl", datum_verified=true,
panel_sha256, observed_start_at, observed_end_at, available_at,
source={source_id, version_id, sha256, published_at, received_at},
label_id, revision_id, is_observed=true, is_imputed=false, evidence_kind
```

`supersedes_sha256` must identify the current tip of the same label series when appending a revision. Revisions form one linear immutable chain; branches, unknown parents and duplicate revision IDs are rejected. New revisions never mutate prior labels or predictions. Evaluation's default `first` policy selects the chain's original root, and explicit `latest` selects its current tip, including when availability timestamps tie. It writes a separate sensitivity snapshot. Unrelated label series for the same forecast cannot be chosen opportunistically. A matching panel fingerprint asserts complete membership and frozen aggregation: actual per-well records and datum/freshness certificates still need upstream retention and validation. A boolean assertion alone is not independent certification.

## Append-only storage and evaluation

Ledger paths are confined to new `reports/candidates/shadow_*` directories. Creation is exclusive. Forecast uniqueness is tied to the campaign/district/origin schedule slot; a changed source version does not authorize a second prediction in that slot. Later scheduled origins can use newly available source revisions without changing old input or prediction bytes. Labels and evaluation outputs are also append-only. Exclusive per-series directory locks serialize label revisions so competing writers cannot branch a chain. A busy lock rejects a competing write; an interrupted writer can leave a visible lock or incomplete reserved record. Verification fails closed in that state. There is no force-unlock or overwrite command: an operator must review the interrupted transaction and retained evidence before a separately authorized recovery. Do not delete locks or reservations merely to make a test pass.

The ledger verifies record hashes and each record's commit binding on reading and before evaluation. Records also bind to the immutable ledger header. It refuses inconsistent or tampered evidence and fails closed on incomplete transaction state. These are local integrity controls, not a global hash chain, trusted external timestamp, or protection against an administrator replacing/deleting history. Real deployment needs a protected source-byte archive, reliable clock synchronization, restricted writers, durable backups, and externally anchored or write-once ledger retention.

Evaluation distinguishes prospective six-full-month, prospective nominal-six-month, retrospective/backfilled, synthetic and pending cases. Panel incompatibility and missing/abstained predictions remain explicit exclusion reasons within those classifications; paired comparisons require the complete registered panel and all three model slots. While real HGB is blocked, three-way real skill evaluation remains unavailable. Evaluation reports explicitly deny operational sufficiency. They do not apply the proposed release gates, approve a model, perform inference with a fitted artifact, or rerun tuning.

## Commands

Run from `C:\Users\Yasharth\Downloads\AquaIQ`. Every action without `--run` prints a read-only offline plan and writes nothing.

```powershell
# Inspect the locked contract and unresolved prerequisites.
.\venv\Scripts\python.exe scripts/shadow_evaluation.py plan

# Synthetic-only dry run. Use a fresh directory name on every invocation.
.\venv\Scripts\python.exe scripts/shadow_evaluation.py demo --run --ledger reports/candidates/shadow_synthetic_demo_example

# Check the completed demonstration without changing it.
.\venv\Scripts\python.exe scripts/shadow_evaluation.py verify --run --ledger reports/candidates/shadow_synthetic_demo_example/ledger

# Regression tests: entirely synthetic; no database, model or dataset loading.
.\venv\Scripts\python.exe -m pytest -q tests/test_shadow_ledger.py --basetemp=scratch/pytest-shadow-example
```

The demo writes clearly named `SYNTHETIC_*` fixtures and a summary beside a synthetic-only ledger. It exercises late-input rejection, duplicate issuance, missing seasonal reference, source revision protection, independent next-slot issuance, caller-mutation protection and later synthetic-label evaluation. Its HGB value is an invented placeholder, never an estimate from the selected estimator. Reusing the demo directory fails rather than replacing files.

The following commands show the isolated operational interface. They are not scheduled or executed automatically. Construct independently verified JSON inputs first; never use the demo fixtures as real evidence.

```powershell
.\venv\Scripts\python.exe scripts/shadow_evaluation.py init --run --ledger reports/candidates/shadow_campaign_example --lane prospective --campaign preregistered-campaign-id
.\venv\Scripts\python.exe scripts/shadow_evaluation.py record --run --ledger reports/candidates/shadow_campaign_example --input path/to/verified_snapshot.json
.\venv\Scripts\python.exe scripts/shadow_evaluation.py label --run --ledger reports/candidates/shadow_campaign_example --input path/to/new_observed_label.json
.\venv\Scripts\python.exe scripts/shadow_evaluation.py evaluate --run --ledger reports/candidates/shadow_campaign_example --label-policy first
.\venv\Scripts\python.exe scripts/shadow_evaluation.py evaluate --run --ledger reports/candidates/shadow_campaign_example --label-policy latest
.\venv\Scripts\python.exe scripts/shadow_evaluation.py verify --run --ledger reports/candidates/shadow_campaign_example
```

`record` timestamps the archive with the actual clock. Prospective snapshot JSON containing `issued_at` is rejected. Existing historical predictions must use a different retrospective ledger. Importing a past forecast today cannot turn it into prospective evidence.

## Migration requirements and deployment prerequisites

No database migration is needed or applied for these files. Database integration requires separate explicit approval. A future migration must use new shadow-only campaign, panel/version, source/version, forecast/input/prediction, observed-label/revision and evaluation-snapshot tables; preserve full envelopes and hashes; enforce immutable append-only records, unique campaign/district/origin slots and unique label revision IDs; atomically commit prediction sets; and provide read-only evaluation views. Retain receipt timestamps, source bytes, prior revisions, exclusions and all abstentions. Versioned migration and rollback plans must not rewrite production prediction tables. A ledger schema change requires a new version and explicit migration preserving original bytes and external audit anchors; do not reinterpret old records in place.

Real operation remains blocked on:

1. Explicit approval for an isolated deterministic artifact build from the original locked settings, cutoff and eligible pairs. Freeze artifact/transformer/code/software hashes and independently reproduce its outputs before wiring inference into a separately reviewed adapter. No refitting, new tuning or production promotion is authorized here.
2. Stable provider well IDs and relocation/replacement history; fixed pre-issuance panels/weights; per-well acquisition and freshness provenance; verified measuring-point/ground datum and m_bgl units; retained source record IDs and revision history. Names/coordinates alone do not establish identical wells.
3. Genuine publication, receipt and input-availability evidence, including monthly-weather dependencies and any rainfall-normal development histories. An adapter must verify dependency availability, not merely accept a finite aggregate. Missing evidence must produce a rejection/abstention.
4. A feasible lead definition. For the existing origin+6 target, full origin-month weather arriving later cannot establish six-full-month operational lead. Resolve this through a separately developed and preregistered issuance/feature/target protocol, not silent label shifts or test-driven retuning.
5. Registered geography/aquifer/month coverage, panel completeness and missingness policies, one analysis date, practical margins and development-only clustered power calculations. The diagnostics' proposed floors are 500 paired cases, 50 districts, two annual cycles, with additional per-month coverage for year-round claims; use larger requirements if power/precision demands them.
6. Newly acquired future observed labels archived after predictions, across stable panels and registered regions. Preserve partial-panel, historical backfill and revised-label evidence as separate cohorts. Do not claim generalization or promote any model from synthetic results, retrospective reports or infrastructure tests.

Release decisions retain the preregistered gates in `reports/candidates/six_month_diagnostics_20261017/FOLLOWUP.md`: artifact/time integrity, coverage, uncertainty-aware improvement versus both baselines, macro non-inferiority and measurement/scope review. No model is declared production-ready, and prospective forecasting skill cannot be claimed until real predictions were archived before genuinely new targets arrived.
