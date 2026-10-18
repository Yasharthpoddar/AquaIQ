# AquaIQ prospective shadow infrastructure — implementation

The isolated direct-six-month ledger is implemented. No estimator was fitted or loaded, no real forecast was issued, no migration ran, and production checkpoints, predictions, datasets and completed experiments were preserved. The selected HGB configuration and training-label cutoff (2018-12-31) remain fixed.

Inspection reused canonical hashing and aware timestamp conventions from `models/prospective_validation.py`, create-only/path-confinement patterns from `scripts/record_live_forecasts.py`, and the locked direct-model contract from `experiment_v2`. The existing monthly production forecast path remains untouched.

| New file | Purpose |
|---|---|
| `models/shadow_ledger.py` | Versioned file ledger, immutable snapshots, timestamp/source/panel validation, duplicate issuance reservations, label revision chains and separate evaluation cohorts. |
| `scripts/shadow_evaluation.py` | Offline-first commands; explicit isolated writes; synthetic-only demonstration. |
| `tests/test_shadow_ledger.py` | Availability/leakage, immutability, concurrency, revisions, missing baselines, timezones, panels and lead classification tests. |
| `tests/test_shadow_evaluation_cli.py` | CLI default isolation, no backdating interface, synthetic scope and create-only output checks. |
| `docs/prospective_shadow.md` | Schema, operational commands, migration requirements and real-deployment prerequisites. |

Every forecast stores its runtime issuance/commit times, source versions and hashes, per-input acquisition/period/publication/receipt/availability evidence, district, registered well-panel membership/weights and fingerprint, frozen configuration identity, feature values, and three prediction slots with explicit abstention reasons. Complete-month weather cannot be accepted before month-end. Caller-supplied real predictions or issuance backdates are rejected.

Real HGB is deliberately blocked with `shadow_artifact_not_approved`; no fitted binary exists in this phase. Persistence and exact seasonal-naive use only their explicitly observed inputs. Missing baselines remain archived abstentions and exclude the case from all three-way paired scores. The synthetic HGB number is a clearly labelled untrained placeholder, not inference from the selected estimator.

Exclusive campaign/district/origin/target slots prevent reissuance after source revisions. Label revisions form a locked linear chain; default evaluation retains its root vintage, with latest-vintage evaluation stored separately. Reports distinguish retrospective/backfilled, synthetic, prospective nominal-month and actual six-full-month evidence. Local hashes detect inconsistent edits; trusted timestamping, source authenticity and write-once retention remain external prerequisites.

The final synthetic-only demonstration is `reports/candidates/shadow_demo_20261018_final/`: **3 forecasts, 1 label, 1 evaluation**. It verifies duplicate and late-input rejection, missing-baseline abstention, revised-source protection, independent later issuance and immutable snapshots. Every fixture is invented and stored outside all real-data directories. Its summary explicitly reports no prospective skill.

Validation results are recorded in `pytest-results.xml` and `verification.json`. `protected_inputs_verified.json` confirms **198 distinct existing input/result files** unchanged (204 digest comparisons before path-alias normalization). No commit or push was performed.

```powershell
# From the repository root: offline plan and read-only final demo verification.
.\venv\Scripts\python.exe scripts/shadow_evaluation.py plan
.\venv\Scripts\python.exe scripts/shadow_evaluation.py verify --run --ledger reports/candidates/shadow_demo_20261018_final/ledger

# A new synthetic demonstration: choose an unused output path.
.\venv\Scripts\python.exe scripts/shadow_evaluation.py demo --run --ledger reports/candidates/shadow_synthetic_reproduction

# Non-fitting regression suite; use a fresh test-output directory.
.\venv\Scripts\python.exe -m pytest -q tests/test_shadow_ledger.py tests/test_shadow_evaluation_cli.py tests/test_prospective_validation.py --basetemp=scratch/pytest-shadow-reproduction
```

Real deployment still requires explicit approval of the separate deterministic HGB artifact build, source/dependency availability provenance, stable well identifiers and datum verification, preregistration, trusted archive/clock controls, and a feasible genuine six-month lead. No database schema change is necessary for this file-ledger phase; any database integration needs separate approval and new append-only shadow tables. Infrastructure tests and synthetic scores establish no forecasting skill.
