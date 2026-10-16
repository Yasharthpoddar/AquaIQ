"""Resumable rainfall staging: download, verify, export and merge candidates.

Default execution is an offline plan. --run permits bounded HTTP downloads and
candidate writes only. No ingestion, training, score publication or production
file replacement is implemented here. A scheduler may safely retry this job.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import numpy as np
import pandas as pd
import yaml

from data_ingestion.imd_realtime import (
    _atomic_json, completed_month_dates, download_dates, download_range,
)
from data_ingestion.imd_realtime_comparison import compare_staged_days
from data_ingestion.imd_realtime_monthly import export_monthly
from data_ingestion.merge_rainfall_update import merge_rainfall
from data_ingestion.ingest_imd_era5 import validate_weather_artifact

ROOT = Path(__file__).resolve().parents[1]


class JobAlreadyRunning(RuntimeError):
    pass


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def job_lock(path):
    """An OS lock is released on process exit, including a crash; no stale PID test."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise JobAlreadyRunning("Another rainfall staging run holds the project lock") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def first_unimported_month(project_root, *, as_of=None):
    """Infer the next month only from a provenanced, gap-free district artifact.

    CSV publication is an operator-controlled marker: it must be promoted with
    its database/model release. This staging job never infers DB commit status.
    """
    project = Path(project_root).resolve()
    path = project / "data/processed/imd_rainfall_district_monthly.csv"
    manifest = validate_weather_artifact(path, {"rainfall_mm": "mm/month"})
    config = yaml.safe_load((project / "config.yaml").read_text(encoding="utf-8"))
    canonical = (project / config["paths"]["geojson_boundaries"]).resolve()
    if (not manifest.get("geojson_sha256") or digest(canonical) != manifest["geojson_sha256"]
            or manifest.get("daily_aggregation") != "sum_all_calendar_days_required"
            or not isinstance(manifest.get("sources"), list) or not manifest["sources"]
            or any(not isinstance(item, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
                   for item in manifest["sources"])):
        raise ValueError("Automatic start requires verified complete-day rainfall and canonical/source provenance")
    columns = ["district", "st_nm", "year", "month", "rainfall_mm"]
    frame = pd.read_csv(path, usecols=columns)
    if frame.empty or frame[columns].isna().any().any():
        raise ValueError("Automatic start refuses empty or missing rainfall records")
    for column in ("year", "month", "rainfall_mm"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if (not np.isfinite(frame[["year", "month", "rainfall_mm"]]).all().all()
            or not frame["year"].between(1901, 9998).all()
            or not frame["year"].eq(frame["year"].astype(int)).all()
            or not frame["month"].between(1, 12).all()
            or not frame["month"].eq(frame["month"].astype(int)).all()
            or frame["rainfall_mm"].lt(0).any()
            or any(frame[column].astype(str).str.strip().eq("").any() for column in ("district", "st_nm"))
            or frame.duplicated(["district", "st_nm", "year", "month"]).any()):
        raise ValueError("Automatic start refuses invalid/duplicate district rainfall months")
    frame["period"] = frame["year"].astype(int) * 12 + frame["month"].astype(int) - 1
    first, last = int(frame.period.min()), int(frame.period.max())
    counts = frame.groupby(["district", "st_nm"]).period.nunique()
    if not counts.eq(last - first + 1).all():
        raise ValueError("Existing rainfall contains district/month holes; automatic start will not skip them")
    today = as_of or date.today()
    last_completed = today.year * 12 + today.month - 2
    if last > last_completed:
        raise ValueError("Published rainfall contains an incomplete or future month")
    next_period = last + 1
    return {"start": f"{next_period // 12:04d}-{next_period % 12 + 1:02d}",
            "latest_imported_month": f"{last // 12:04d}-{last % 12 + 1:02d}",
            "csv_sha256": manifest["csv_sha256"], "manifest_sha256": digest(path.with_suffix(".manifest.json")),
            "districts": len(counts), "verified_contiguous_months": last - first + 1,
            "provenance_scope": "published CSV and manifest; database publication is operator-controlled"}


def make_plan(project_root, start=None, end=None, *, as_of=None, annual_year=2025,
              annual_file=None):
    project = Path(project_root).resolve()
    if not (project / "config.yaml").is_file():
        raise ValueError("Project root must contain config.yaml")
    today = as_of or date.today()
    end = end or (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    automatic = first_unimported_month(project, as_of=today) if start in (None, "auto") else None
    start = automatic["start"] if automatic else start
    if automatic and start > end:
        # Validate end syntax/completion even though there is no download work.
        completed_month_dates(end, end, today)
        return {"schema_version": "aquaiq-rainfall-stage-v1", "project_root": str(project),
                "status": "no_new_completed_months", "start": start, "end": end,
                "planned_days": 0, "automatic_start": automatic,
                "network_requests_made": 0, "production_changes_made": False, "actions": []}
    days = completed_month_dates(start, end, today)
    if isinstance(annual_year, bool) or not isinstance(annual_year, int) or not 1901 <= annual_year < today.year:
        raise ValueError("The comparison annual year must be a completed year from 1901 onward")
    source = (Path(annual_file) if annual_file else project / "data/raw/updates/20261013/imd" /
              f"Rainfall_ind{annual_year}_rfp25.grd").resolve()
    cache = (project / "data/raw/updates/rainfall_refresh").resolve()
    candidate = (project / "reports/candidates/rainfall_refresh" / f"{start}_{end}").resolve()
    for path, parent in ((cache, project / "data/raw/updates"),
                         (candidate, project / "reports/candidates")):
        if not path.is_relative_to(parent.resolve()) or not path.is_relative_to(project):
            raise ValueError("Staging and candidate paths must remain inside the project")
    overlap_directory = (cache / "overlap" / str(annual_year)).resolve()
    daily_directory = (cache / "daily").resolve()
    if not all(path.is_relative_to(cache) for path in (overlap_directory, daily_directory)):
        raise ValueError("Daily staging paths cannot escape their cache through symbolic links")
    return {
        "schema_version": "aquaiq-rainfall-stage-v1", "project_root": str(project),
        "start": start, "end": end, "planned_days": len(days),
        "annual_year": annual_year, "annual_file": str(source),
        "overlap_dates": [f"{annual_year}-01-01", f"{annual_year}-06-15", f"{annual_year}-09-30"],
        "overlap_directory": str(overlap_directory),
        "daily_directory": str(daily_directory), "candidate_directory": str(candidate),
        "existing_rainfall": str(project / "data/processed/imd_rainfall_district_monthly.csv"),
        "lock_file": str(cache / "staging.lock"), "production_changes_made": False,
        "actions": ["download_overlap", "compare_overlap", "download_target",
                    "export_complete_months", "merge_candidate"],
        "scope": "staging_only; provisional rainfall; no database/model/score writes",
        **({"automatic_start": automatic} if automatic else {}),
    }


def _save_comparison(path, comparison):
    """Preserve report hashes across retries when sampled evidence is unchanged."""
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8-sig"))
        normalized = lambda item: {key: value for key, value in item.items() if key != "created_at_utc"}
        if normalized(previous) != normalized(comparison):
            raise ValueError("Existing overlap evidence changed; review the candidate before replacing its provenance")
        return previous
    _atomic_json(path, comparison)
    return comparison


def _merged_candidate(existing, update, directory):
    """Reuse our verified pair or assemble fresh files before publishing them."""
    outputs = [directory / "combined.csv", directory / "combined_normals.csv"]
    paths = outputs + [item.with_suffix(".manifest.json") for item in outputs]
    if any(item.exists() for item in paths):
        if not all(item.is_file() for item in paths):
            raise ValueError("Partial merged outputs need review; refusing to overwrite them")
        inputs = [json.loads(item.with_suffix(".manifest.json").read_text(encoding="utf-8-sig"))
                  for item in (existing, update)]
        for csv_path in outputs:
            meta = json.loads(csv_path.with_suffix(".manifest.json").read_text(encoding="utf-8-sig"))
            provenance = meta.get("append_provenance", {})
            if (meta.get("generator") != "merge_rainfall_update"
                    or meta.get("csv_sha256") != digest(csv_path)
                    or meta.get("sources") != inputs[0].get("sources", []) + inputs[1].get("sources", [])
                    or provenance.get("sampled_overlap") != inputs[1].get("sampled_overlap")
                    or provenance.get("existing_csv_sha256") != digest(existing)
                    or provenance.get("update_csv_sha256") != digest(update)):
                raise ValueError("Existing merged candidate differs from verified inputs; choose a new range or review it")
        return {"status": "already_present", "output": str(outputs[0])}
    with tempfile.TemporaryDirectory(prefix=".merge-", dir=directory) as temporary:
        staged = [Path(temporary) / item.name for item in outputs]
        details = merge_rainfall(existing, update, staged[0], staged[1])
        for source, destination in zip(staged, outputs):
            source.replace(destination)
            source.with_suffix(".manifest.json").replace(destination.with_suffix(".manifest.json"))
    return {"status": "candidate_merged", "output": str(outputs[0]), **details}


def run_staging(plan, *, as_of=None, attempts=2, timeout=(10, 20),
                max_days=10, max_consecutive_failures=1, max_failures=2):
    """Persist phase checkpoints and reuse validated daily files on the next run."""
    if plan.get("status") == "no_new_completed_months":
        return plan
    directory = Path(plan["candidate_directory"])
    identity = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    report = {"schema_version": "aquaiq-rainfall-stage-progress-v1", "plan": plan,
              "plan_sha256": identity, "status": "running", "phases": {},
              "production_changes_made": False}
    progress_path = directory / "progress.json"

    def save(status=None):
        if status:
            report["status"] = status
        report["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        _atomic_json(progress_path, report)
        return report

    with job_lock(plan["lock_file"]):
        directory.mkdir(parents=True, exist_ok=True)
        if progress_path.exists():
            previous = json.loads(progress_path.read_text(encoding="utf-8-sig"))
            if (previous.get("schema_version") != report["schema_version"]
                    or previous.get("plan_sha256") != identity):
                raise ValueError("Existing progress belongs to another staging plan")
        save()
        options = {"as_of": as_of, "attempts": attempts, "timeout": timeout,
                   "max_days": max_days, "max_consecutive_failures": max_consecutive_failures,
                   "max_failures": max_failures}
        try:
            report["phases"]["overlap_download"] = download_dates(
                plan["overlap_dates"], Path(plan["overlap_directory"]), **options)
            save()
            if report["phases"]["overlap_download"]["status"] != "complete":
                return save("waiting_for_overlap_source")
            overlap = compare_staged_days(Path(plan["annual_file"]), plan["annual_year"],
                                         Path(plan["overlap_directory"]), plan["overlap_dates"], as_of=as_of)
            overlap_path = directory / "overlap.json"
            overlap = _save_comparison(overlap_path, overlap)
            report["phases"]["overlap_comparison"] = overlap
            save()
            if not overlap.get("verified_overlap"):
                return save("overlap_requires_review")
            report["phases"]["target_download"] = download_range(
                plan["start"], plan["end"], Path(plan["daily_directory"]), **options)
            save()
            if report["phases"]["target_download"]["status"] != "complete":
                return save("waiting_for_complete_months")
            monthly, normals = directory / "monthly.csv", directory / "normals.csv"
            report["phases"]["monthly_export"] = export_monthly(
                plan["start"], plan["end"], Path(plan["daily_directory"]),
                overlap_path, monthly, normals, as_of=as_of)
            save()
            report["phases"]["merge"] = _merged_candidate(
                Path(plan["existing_rainfall"]), monthly, directory)
            report["candidate_hashes"] = {item.name: digest(item) for item in directory.iterdir()
                if item.is_file() and (item.suffix == ".csv" or item.name.endswith(".manifest.json"))}
            return save("candidate_ready_for_review")
        except Exception as error:
            report["error"] = {"type": type(error).__name__, "message": str(error)}
            save("failed")
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--start", default="auto", help="First missing month, or YYYY-MM override")
    parser.add_argument("--end", help="Defaults to the last completed month")
    parser.add_argument("--annual-year", type=int, default=2025)
    parser.add_argument("--annual-file", type=Path)
    parser.add_argument("--run", action="store_true", help="Permit staging downloads and candidate writes")
    parser.add_argument("--max-days", type=int, default=10, help="Maximum pending requests per phase per run")
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--connect-timeout", type=float, default=10)
    parser.add_argument("--read-timeout", type=float, default=20)
    args = parser.parse_args(argv)
    plan = make_plan(args.project_root, args.start, args.end,
                     annual_year=args.annual_year, annual_file=args.annual_file)
    result = (plan if plan.get("status") == "no_new_completed_months" else
              run_staging(plan, attempts=args.attempts, max_days=args.max_days,
                         timeout=(args.connect_timeout, args.read_timeout))) if args.run else {
                             "status": "offline_plan", "network_requests_made": 0, **plan}
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] in {"offline_plan", "candidate_ready_for_review", "no_new_completed_months"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
