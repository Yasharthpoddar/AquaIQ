# Maintenance commands

These are explicit maintainer operations, not application startup steps. Preserve a matching database/configuration/data/checkpoint backup before any rebuild. Do not run them as part of repository housekeeping or a frozen demonstration.

## Data acquisition and derived stages

[config.yaml](../config.yaml) and the [source catalogue](../data_sources/catalog.yaml) define expected assets. Acquisition requires the original official archives, source permissions and matching provenance manifests. [Deployment operations](../deploy/README.md) document bounded rainfall staging; staging does not ingest or publish automatically.

```powershell
python -m data_ingestion.era5_to_district
python -m data_ingestion.imd_district_climatology --raw-dir data/raw/imd
python scripts/run_pipeline.py --step all
```

Derived stages can be selected explicitly: `--step preprocess`, `features`, `train`, `backtest` or `score_all`. Feature rebuilding replaces derived database data transactionally. The training stage writes matching bundles; it is not an authorized promotion of an experimental candidate. `--as-of` on the orchestrator applies to batch scoring. Historical input reconstruction uses `python -m preprocessing.pipeline --as-of YYYY-MM-DD`, followed by a matching feature/model build.

Observed labels, physical units, district identifiers and causal feature policies must remain intact. No sample export or filled/predicted groundwater value becomes a genuine target. Source update instructions and exact release identities are in the [release reproduction guide](FINAL_RELEASE_REPRODUCTION.md).

## Isolated sample and CSV-only workflows

```powershell
python -m preprocessing.pipeline --sample 10
python -m preprocessing.features --input-dir reports/samples
python -m preprocessing.features --sample 10
python -m preprocessing.features --csv-only
```

Sample outputs stay under `reports/samples`; CSV-only full outputs are candidates. Production training/loading rejects sample-only manifests. Preserve the active feature CSV, manifest, checkpoints and public source tables.

## Audits and historical comparisons

```powershell
python -m scripts.audit_data_quality --help
python -m scripts.audit_postgres_export
python -m data_ingestion.data_completeness
python -m models.audit_evaluation --output-dir reports/candidates/NEW_AUDIT --include-monthly
```

The comparison can fit test challengers with train-only preprocessing; use a new output directory. Inspected historical holdouts are not pristine tests, and R² is not an accuracy percentage. See the [evidence index](../reports/README.md) for preserved conclusions.

## Pipeline replay without production replacement

```powershell
python -m scripts.verify_pipeline
python -m scripts.verify_pipeline --run --output-dir scratch/NEW_PIPELINE_REPLAY --as-of 2026-10-17
```

The default is an offline plan. `--run` requires the provisioned real raw-record snapshot, source archives and a role allowed to create an isolated schema. Derived artifacts/checkpoints go to a fresh scratch directory; the replay removes its test schema and verifies production preservation. It performs no new download. Restore the matching baseline assets/database before expecting the recorded coverage on another machine.

## Verification and historical payload recovery

Use the [root verification commands](../README.md#verify) with fresh paths and the installed dependencies. Database integration is opt-in; an empty CI database is used only for schema smoke checks. Historical compiled previews and audit manifests describe their dated source versions. [Archive instructions](../reports/ARCHIVE.md) recover pruned tracked test captures/drafts byte-for-byte; live runtime assets and current tests do not depend on those captured outputs.
