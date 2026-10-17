"""Reproduce the six pipeline stages without replacing the active release.

The default prints a plan. --run creates a fresh PostgreSQL schema, seeds it
with the existing real raw observations (including verified incremental
updates), and redirects all derived artifacts into a new scratch directory.
The temporary schema is removed on exit; artifacts and measured results remain.
No external downloads or production publication occur.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import time
import uuid
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TABLES = ("districts", "raw_data", "features", "predictions", "crisis_scores", "scoring_runs")


def output_directory(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to((ROOT / "scratch").resolve()) or path.exists():
        raise ValueError("Verification needs a new directory inside this repository's scratch folder")
    return path


def file_snapshot():
    paths = [ROOT / "config.yaml"]
    for directory in (ROOT / "data/processed", ROOT / "models/checkpoints"):
        paths.extend(path for path in directory.rglob("*") if path.is_file())
    result = {}
    for path in paths:
        with path.open("rb") as stream:
            result[str(path.relative_to(ROOT))] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


class _DigestStream:
    def __init__(self):
        self.digest = hashlib.sha256()

    def write(self, value):
        self.digest.update(value.encode() if isinstance(value, str) else value)


def database_snapshot(connection):
    result = {}
    with connection.cursor() as cursor:
        for table in TABLES:
            stream = _DigestStream()
            cursor.copy_expert(f"COPY (SELECT * FROM public.{table} ORDER BY 1) TO STDOUT WITH CSV", stream)
            cursor.execute(f"SELECT count(*) FROM public.{table}")
            result[table] = {"rows": cursor.fetchone()[0], "sha256": stream.digest.hexdigest()}
    return result


def prepare_artifacts(output):
    (output / "data/raw").mkdir(parents=True)
    (output / "data/processed").mkdir(parents=True)
    (output / "models/checkpoints").mkdir(parents=True)
    (output / "reports").mkdir(parents=True)
    shutil.copy2(ROOT / "config.yaml", output / "config.yaml")
    shutil.copy2(ROOT / "data/raw/india_districts.geojson", output / "data/raw/india_districts.geojson")
    for name in ("ensemble.py", "fuzzy_logic.py", "tiers.py"):
        shutil.copy2(ROOT / "models" / name, output / "models" / name)
    # Verified weather inputs are copied; the ingester writes correction audits
    # only beneath the isolated ROOT. The archived CGWB CSV remains read-only.
    for name in ("imd_rainfall_district_monthly", "era5_district_monthly"):
        for suffix in (".csv", ".manifest.json"):
            shutil.copy2(ROOT / "data/processed" / (name + suffix), output / "data/processed" / (name + suffix))


def verify(output, cutoff):
    from psycopg2 import sql
    from db import connection as database

    original_connect = database.get_connection
    namespace = "aquaiq_verify_" + uuid.uuid4().hex
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "as_of": cutoff.isoformat(),
              "schema": namespace, "output": str(output), "status": "running", "stages": [],
              "input_policy": "Existing real raw_data snapshot plus archived source ingestion; no synthetic observations"}
    output.mkdir(parents=True)
    before_files = file_snapshot()
    source = original_connect()
    source.set_session(readonly=True, isolation_level="REPEATABLE READ")
    created = False

    def isolated_connect():
        connection = original_connect()
        with connection.cursor() as cursor:
            # Excluding public is essential: missing isolated tables must fail.
            cursor.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(namespace)))
        connection.commit()
        return connection

    try:
        report["production_before"] = database_snapshot(source)
        prepare_artifacts(output)
        with original_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(namespace)))
                cursor.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(namespace)))
                cursor.execute((ROOT / "db/schema.sql").read_text(encoding="utf-8"))
                cursor.execute((ROOT / "db/migrations/003_pipeline_provenance.sql").read_text(encoding="utf-8"))
                cursor.execute("INSERT INTO districts(district_id,district_name,state) "
                               "SELECT district_id,district_name,state FROM public.districts")
                cursor.execute("INSERT INTO raw_data(district_id,date,source,metric,value) "
                               "SELECT district_id,date,source,metric,value FROM public.raw_data")
        connection.close()
        created = True
        database.get_connection = isolated_connect
        modules = {name: importlib.import_module(name) for name in (
            "data_ingestion.ingest_cgwb", "data_ingestion.ingest_imd_era5", "data_ingestion.enrich_districts",
            "preprocessing.pipeline", "preprocessing.features", "models.xgboost_model",
            "models.ensemble", "models.climate_forecast", "models.backtest", "models.score_all",
            "scripts.run_pipeline")}
        for name, module in modules.items():
            if name != "data_ingestion.ingest_cgwb":
                module.ROOT = output
        for name in ("preprocessing.pipeline", "preprocessing.features"):
            modules[name].PROCESSED_DIR = output / "data/processed"
        weather = modules["data_ingestion.ingest_imd_era5"]
        weather.IMD_CSV = output / "data/processed/imd_rainfall_district_monthly.csv"
        weather.ERA5_CSV = output / "data/processed/era5_district_monthly.csv"
        modules["models.xgboost_model"].CHECKPOINT_PATH = output / "models/checkpoints/aquaiq_xgb.json"
        modules["models.climate_forecast"].CHECKPOINT_PATH = output / "models/checkpoints/aquaiq_monthly_climate.json"
        runner = modules["scripts.run_pipeline"]
        for stage, action in (("ingest", runner.step_ingest), ("preprocess", runner.step_preprocess),
                              ("features", runner.step_features), ("train", runner.step_train),
                              ("backtest", runner.step_backtest),
                              ("score_all", lambda: runner.step_score_all(cutoff))):
            started = time.monotonic()
            success = action()
            report["stages"].append({"stage": stage, "passed": success,
                                     "seconds": round(time.monotonic() - started, 3)})
            if not success:
                raise RuntimeError(f"Isolated pipeline failed at {stage}")
        with isolated_connect() as connection:
            report["isolated_rows"] = {}
            with connection.cursor() as cursor:
                for table in TABLES:
                    cursor.execute(f"SELECT count(*) FROM {table}")
                    report["isolated_rows"][table] = cursor.fetchone()[0]
                counts = report["isolated_rows"]
                if (counts["predictions"] < 1 or counts["raw_data"] < 1
                        or counts["crisis_scores"] != counts["districts"]):
                    raise RuntimeError("Verification requires real predictions and a complete district score publication")
                with (output / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
                    cursor.copy_expert("COPY (SELECT * FROM predictions ORDER BY district_id,forecast_date) "
                                       "TO STDOUT WITH CSV HEADER", stream)
                with (output / "crisis_scores.csv").open("w", newline="", encoding="utf-8") as stream:
                    cursor.copy_expert("COPY (SELECT * FROM crisis_scores ORDER BY district_id) "
                                       "TO STDOUT WITH CSV HEADER", stream)
        connection.close()
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        database.get_connection = original_connect
        source.close()
        if created:
            with original_connect() as connection:
                with connection.cursor() as cursor:
                    # namespace is generated here, never supplied by the caller.
                    cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(namespace)))
            connection.close()
        report["temporary_schema_removed"] = created
        with original_connect() as connection:
            connection.set_session(readonly=True)
            report["production_after"] = database_snapshot(connection)
        connection.close()
        report["production_database_unchanged"] = report.get("production_before") == report["production_after"]
        report["production_artifacts_unchanged"] = before_files == file_snapshot()
        (output / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["production_database_unchanged"] or not report["production_artifacts_unchanged"]:
        raise RuntimeError("Production snapshot changed during isolated verification; inspect verification.json")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output-dir", default="scratch/pipeline-verification-" + uuid.uuid4().hex[:12])
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    try:
        output = output_directory(args.output_dir)
    except ValueError as error:
        parser.error(str(error))
    if args.as_of > date.today():
        parser.error("--as-of cannot be in the future")
    if not args.run:
        print(json.dumps({"status": "plan", "output": str(output), "stages":
                          ["ingest", "preprocess", "features", "train", "backtest", "score_all"],
                          "writes": "Fresh temporary DB schema and scratch artifacts only"}, indent=2))
        return
    report = verify(output, args.as_of)
    print(json.dumps({key: report[key] for key in ("status", "output", "isolated_rows",
                                                 "production_database_unchanged", "production_artifacts_unchanged")}, indent=2))


if __name__ == "__main__":
    main()
