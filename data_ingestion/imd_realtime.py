"""Stage and validate IMD daily rainfall; never invent missing calendar days.

The CLI defaults to an offline plan. HTTP requests require explicit --download.
Downloads are resumable, bounded and staging-only; this module never changes
production CSVs, models or the database. Format checks do not establish product
identity: compare historical samples against the verified annual archive too.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

import numpy as np
import pandas as pd

SOURCE_PAGE = "https://imdpune.gov.in/cmpg/Realtimedata/Rainfall/Rain_Download.html"
DOWNLOAD_URL = "https://imdpune.gov.in/cmpg/Realtimedata/Rainfall/rain.php"
CONTROL_URL = "https://imdpune.gov.in/cmpg/Realtimedata/Rainfall/dataddmmyyyy.php"
GRID_DOCS = "https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html"
NY, NX = 129, 135
DAY_BYTES = NY * NX * 4


class DailyDownloadError(RuntimeError):
    """A daily source could not be validated within the bounded retry budget."""

    def __init__(self, day, attempts, reason):
        self.day, self.attempts = day, attempts
        super().__init__(f"{day.isoformat()}: {attempts} attempts failed: {reason}")


def _atomic_json(path: Path, payload: dict) -> None:
    """Keep a complete resumable report if writing the next report is interrupted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".partial",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _download_options(attempts, timeout, backoff_seconds):
    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 10:
        raise ValueError("Download attempts must be between 1 and 10")
    if (not isinstance(timeout, (tuple, list)) or len(timeout) != 2
            or any(not isinstance(value, (int, float)) or isinstance(value, bool)
                   or not math.isfinite(value) or not 0 < value <= 60 for value in timeout)):
        raise ValueError("Connect/read timeouts must be finite seconds between 0 and 60")
    if (not isinstance(backoff_seconds, (int, float)) or isinstance(backoff_seconds, bool)
            or not math.isfinite(backoff_seconds) or not 0 <= backoff_seconds <= 60):
        raise ValueError("Retry backoff must be finite seconds between 0 and 60")


def _staged_paths(directory, day):
    stem = "rain_" + day.strftime("%d%m%Y")
    return directory / (stem + ".bin"), directory / (stem + ".download.json")


def download_daily(directory: Path, day: date, *, session=None, attempts=3,
                   timeout=(10, 20), backoff_seconds=1., sleeper=time.sleep,
                   as_of: date | None = None) -> dict:
    """Reuse a verified pair, or atomically save a strictly validated daily grid.

    Invalid cached files are retained until a replacement passes every check.
    A valid response is only a provisional daily grid, not verified equivalence
    to the annual quality-controlled rainfall product.
    """
    _download_options(attempts, timeout, backoff_seconds)
    today = as_of or date.today()
    if not isinstance(day, date) or isinstance(day, datetime) or day >= today or day.year < 1901:
        raise ValueError("Download date must be a completed day from 1901 onward")
    directory = Path(directory)
    target, sidecar = _staged_paths(directory, day)
    try:
        read_staged_daily(directory, day, today)
        return {"date": day.isoformat(), "path": str(target), "status": "already_present",
                "sha256": _sha256(target), "size_bytes": DAY_BYTES, "attempts": 0}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    import requests

    directory.mkdir(parents=True, exist_ok=True)
    client = session if session is not None else requests.Session()
    last_error = "No valid response"
    try:
        for attempt in range(1, attempts + 1):
            partial, response = None, None
            try:
                response = client.post(DOWNLOAD_URL, data={"rain": day.strftime("%d%m%Y")},
                                       stream=True, timeout=tuple(timeout), allow_redirects=False)
                if response.status_code != 200:
                    raise ValueError(f"IMD returned HTTP {response.status_code}, expected 200")
                if response.url != DOWNLOAD_URL:
                    raise ValueError("IMD response came from an unexpected endpoint")
                metadata = {"url": DOWNLOAD_URL, "form": {"rain": day.strftime("%d%m%Y")},
                            "content_type": response.headers.get("Content-Type", ""),
                            "content_disposition": response.headers.get("Content-Disposition", "")}
                if "html" in metadata["content_type"].lower():
                    raise ValueError("IMD returned HTML instead of a rainfall grid")
                with tempfile.NamedTemporaryFile(dir=directory, prefix=target.name + ".",
                                                 suffix=".partial", delete=False) as stream:
                    partial = Path(stream.name)
                    size = 0
                    for block in response.iter_content(16 * 1024):
                        if not block:
                            continue
                        size += len(block)
                        if size > DAY_BYTES:
                            raise ValueError(f"IMD daily response exceeds {DAY_BYTES} bytes")
                        stream.write(block)
                    stream.flush()
                    os.fsync(stream.fileno())
                metadata.update(size_bytes=size, sha256=_sha256(partial))
                read_daily(partial, day, metadata, today)
                metadata.update(retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                                status="validated_daily_grid_only", staging_only=True,
                                product_status="provisional_real_time", request_method="POST",
                                validation_scope="date_filename_checksum_grid_values; product_identity_requires_overlap_check")
                # Publish provenance last; a crash between replacements is detected
                # by the checksum guard and repaired by a later resumed download.
                partial.replace(target)
                _atomic_json(sidecar, metadata)
                return {"date": day.isoformat(), "path": str(target), "status": "downloaded",
                        "sha256": metadata["sha256"], "size_bytes": size, "attempts": attempt}
            except (requests.RequestException, OSError, ValueError) as error:
                last_error = str(error)
            finally:
                if response is not None:
                    response.close()
                if partial is not None:
                    partial.unlink(missing_ok=True)
            if attempt < attempts:
                sleeper(min(60., backoff_seconds * 2 ** (attempt - 1)))
        raise DailyDownloadError(day, attempts, last_error)
    finally:
        if session is None:
            client.close()


def download_range(start: str, end: str, directory: Path, *, session=None, attempts=3,
                   timeout=(10, 20), backoff_seconds=1., sleeper=time.sleep,
                   as_of: date | None = None, max_consecutive_failures=3,
                   max_failures=10, max_days=None, progress=None) -> dict:
    """Resume complete months and stop a failing source after a bounded budget."""
    days = completed_month_dates(start, end, as_of)
    return _download_planned_days(days, start, end, directory, selection="complete_months",
                                  session=session, attempts=attempts, timeout=timeout,
                                  backoff_seconds=backoff_seconds, sleeper=sleeper, as_of=as_of,
                                  max_consecutive_failures=max_consecutive_failures,
                                  max_failures=max_failures, max_days=max_days, progress=progress)


def selected_dates(values, as_of=None):
    """Bounded, exact calendar dates for historical product-overlap probes."""
    today = as_of or date.today()
    days = []
    for value in values:
        if isinstance(value, datetime):
            raise ValueError("Selected dates must be calendar dates, not timestamps")
        if isinstance(value, date):
            day = value
        elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            day = date.fromisoformat(value)
        else:
            raise ValueError("Selected dates must use YYYY-MM-DD format")
        if day >= today or day.year < 1901:
            raise ValueError("Selected dates must be completed days from 1901 onward")
        days.append(day)
    if not days or len(days) > 366 or len(set(days)) != len(days):
        raise ValueError("Select between 1 and 366 distinct completed days")
    return sorted(days)


def download_dates(values, directory: Path, *, as_of=None, **options):
    """Stage a few explicit days without downloading unrelated months."""
    days = selected_dates(values, as_of)
    return _download_planned_days(days, days[0].isoformat(), days[-1].isoformat(), directory,
                                  selection="explicit_days", as_of=as_of, **options)


def _download_planned_days(days, start, end, directory, *, selection, session=None, attempts=3,
                           timeout=(10, 20), backoff_seconds=1., sleeper=time.sleep,
                           as_of=None, max_consecutive_failures=3, max_failures=10,
                           max_days=None, progress=None):
    _download_options(attempts, timeout, backoff_seconds)
    for name, value in (("max_consecutive_failures", max_consecutive_failures),
                        ("max_failures", max_failures), ("max_days", max_days)):
        if ((value is None and name != "max_days") or (value is not None
                and (not isinstance(value, int) or isinstance(value, bool) or value < 1))):
            raise ValueError(f"{name} must be a positive integer")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Inventory all days first so previously completed files remain visible even
    # when a short network budget is used or the endpoint is unavailable.
    completed, remaining = [], []
    for day in days:
        try:
            read_staged_daily(directory, day, as_of)
            target, _ = _staged_paths(directory, day)
            completed.append({"date": day.isoformat(), "status": "already_present", "path": str(target),
                              "sha256": _sha256(target), "size_bytes": DAY_BYTES, "attempts": 0})
        except (OSError, ValueError, TypeError, AttributeError):
            remaining.append(day)
    failures, tried, consecutive = [], 0, 0
    reason = None
    client = session

    def snapshot():
        downloaded = sum(item["status"] == "downloaded" for item in completed)
        counts = {"downloaded": downloaded, "already_present": len(completed) - downloaded,
                  "failed": len(failures), "pending": len(days) - len(completed) - len(failures)}
        successful = {item["date"] for item in completed}
        failed = {item["date"] for item in failures}
        return {"version": "1.0-imd-realtime-staging", "start": start, "end": end, "selection": selection,
                "updated_at_utc": datetime.now(timezone.utc).isoformat(), "planned_days": len(days),
                "days_complete": len(completed), "status": "complete" if len(completed) == len(days) else "incomplete",
                "counts": counts, "completed": sorted(completed, key=lambda item: item["date"]),
                "failed": failures.copy(), "pending_dates": [day.isoformat() for day in days
                    if day.isoformat() not in successful and day.isoformat() not in failed],
                "stop_reason": reason, "production_changes_made": False,
                "product_identity": "not_established_by_download_checks", "staging_directory": str(directory),
                "download_options": {"attempts": attempts, "timeout_seconds": list(timeout),
                                     "max_consecutive_failures": max_consecutive_failures,
                                     "max_failures": max_failures, "max_days": max_days}}

    def save_progress():
        result = snapshot()
        _atomic_json(directory / "download_progress.json", result)
        if progress is not None:
            progress(result)
        return result

    save_progress()
    try:
        for day in remaining:
            if max_days is not None and tried >= max_days:
                reason = "max_days_budget"
                break
            if client is None:
                import requests
                client = requests.Session()
            tried += 1
            try:
                result = download_daily(directory, day, session=client, attempts=attempts,
                                        timeout=timeout, backoff_seconds=backoff_seconds,
                                        sleeper=sleeper, as_of=as_of)
                completed.append(result)
                consecutive = 0
            except DailyDownloadError as error:
                failures.append({"date": day.isoformat(), "attempts": error.attempts, "error": str(error)})
                consecutive += 1
            if consecutive >= max_consecutive_failures:
                reason = "consecutive_failure_budget"
            elif len(failures) >= max_failures:
                reason = "total_failure_budget"
            save_progress()
            if reason is not None:
                break
        return save_progress()
    finally:
        if session is None and client is not None:
            client.close()


def completed_month_dates(start: str, end: str, as_of: date | None = None) -> list[date]:
    """Plan at most one year's complete months; reject current/future months."""
    if not all(re.fullmatch(r"\d{4}-\d{2}", value) for value in (start, end)):
        raise ValueError("Months must use YYYY-MM format")
    first, last = date.fromisoformat(start + "-01"), date.fromisoformat(end + "-01")
    today = as_of or date.today()
    if first > last:
        raise ValueError("Start month must precede end month")
    if last >= today.replace(day=1):
        raise ValueError("Only completed calendar months may be planned")
    last_day = last.replace(day=calendar.monthrange(last.year, last.month)[1])
    count = (last_day - first).days + 1
    if count > 366:
        raise ValueError("A real-time staging plan is bounded to 366 days")
    return [first + timedelta(days=index) for index in range(count)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_daily(path: Path, day: date, metadata: dict,
               as_of: date | None = None) -> np.ndarray:
    """Require exact source/date identity, checksum, grid and missing sentinel."""
    today = as_of or date.today()
    if not isinstance(metadata, dict):
        raise ValueError("Daily provenance must be a JSON object")
    if day >= today:
        raise ValueError("Today and future daily records are not complete observations")
    if metadata.get("url") != DOWNLOAD_URL:
        raise ValueError("Daily provenance must identify the official IMD rainfall endpoint")
    if metadata.get("form", {}).get("rain") != day.strftime("%d%m%Y"):
        raise ValueError("Daily provenance date differs from the requested date")
    disposition = metadata.get("content_disposition", "")
    filename_match = re.search(r'filename\s*=\s*"?([^";\s]+)', disposition, re.I)
    expected_name = day.strftime("rain_ind0.25_%y_%m_%d.grd")
    if not filename_match or filename_match.group(1) != expected_name:
        raise ValueError("IMD response filename differs from the requested date")
    if "html" in metadata.get("content_type", "").lower():
        raise ValueError("IMD returned an HTML page instead of a rainfall grid")
    if path.stat().st_size != DAY_BYTES or metadata.get("size_bytes") != DAY_BYTES:
        raise ValueError(f"Daily grid must contain exactly {DAY_BYTES} bytes")
    if metadata.get("sha256") != _sha256(path):
        raise ValueError("Daily rainfall checksum differs from its provenance")
    grid = np.fromfile(path, dtype="<f4").reshape(NY, NX)
    if not np.isfinite(grid).all():
        raise ValueError("Daily rainfall contains non-finite values")
    if np.any((grid < 0) & (grid != -999.0)):
        raise ValueError("Unexpected negative rainfall; only -999 is a missing sentinel")
    if not np.any(grid >= 0) or np.any(grid > 10000):
        raise ValueError("Daily rainfall is entirely missing or implausible")
    grid[grid == -999.0] = np.nan
    return grid


def read_staged_daily(directory: Path, day: date,
                      as_of: date | None = None) -> np.ndarray:
    stem = "rain_" + day.strftime("%d%m%Y")
    path = directory / (stem + ".bin")
    metadata = json.loads((directory / (stem + ".download.json")).read_text(encoding="utf-8-sig"))
    return read_daily(path, day, metadata, as_of)


def complete_month_grid(directory: Path, year: int, month: int,
                        as_of: date | None = None) -> tuple[np.ndarray, list[dict]]:
    """Sum every calendar day; cells with any missing daily value stay missing."""
    period = f"{year:04d}-{month:02d}"
    days = completed_month_dates(period, period, as_of)
    missing = [day.isoformat() for day in days
               if not (directory / ("rain_" + day.strftime("%d%m%Y") + ".bin")).exists()
               or not (directory / ("rain_" + day.strftime("%d%m%Y") + ".download.json")).exists()]
    if missing:
        raise ValueError("Incomplete calendar month; missing daily records: " + ", ".join(missing))
    total = np.zeros((NY, NX), dtype=np.float64)
    count = np.zeros((NY, NX), dtype=np.int16)
    sources = []
    for day in days:
        grid = read_staged_daily(directory, day, as_of)
        usable = np.isfinite(grid)
        total[usable] += grid[usable]
        count += usable
        path = directory / ("rain_" + day.strftime("%d%m%Y") + ".bin")
        sources.append({"date": day.isoformat(), "path": str(path), "sha256": _sha256(path)})
    total[count != len(days)] = np.nan
    if not np.isfinite(total).any():
        raise ValueError("No grid cell has complete daily rainfall for this calendar month")
    return total, sources


def monthly_grid_points(grid: np.ndarray, year: int, month: int) -> pd.DataFrame:
    """Use the same south-to-north grid orientation as the annual processor."""
    if grid.shape != (NY, NX):
        raise ValueError("Unexpected rainfall grid shape")
    longitudes, latitudes = np.meshgrid(66.5 + np.arange(NX) * 0.25,
                                      6.5 + np.arange(NY) * 0.25)
    frame = pd.DataFrame({"latitude": latitudes.ravel(), "longitude": longitudes.ravel(),
                          "rainfall_mm": grid.ravel(), "lat_idx": np.repeat(np.arange(NY), NX),
                          "lon_idx": np.tile(np.arange(NX), NY), "year": year, "month": month})
    return frame.dropna(subset=["rainfall_mm"]).reset_index(drop=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan, download and verify staged IMD daily rainfall")
    parser.add_argument("--start", help="First completed month, YYYY-MM")
    parser.add_argument("--end", help="Last completed month, YYYY-MM")
    parser.add_argument("--dates", nargs="+", help="Selected completed dates, YYYY-MM-DD, for historical overlap samples")
    parser.add_argument("--staged-dir", type=Path)
    parser.add_argument("--validate-staged", action="store_true")
    parser.add_argument("--download", action="store_true", help="Explicitly download into staging; never ingest")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--connect-timeout", type=float, default=10)
    parser.add_argument("--read-timeout", type=float, default=20)
    parser.add_argument("--backoff-seconds", type=float, default=1)
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    parser.add_argument("--max-failures", type=int, default=10)
    parser.add_argument("--max-days", type=int, help="Optional number of missing days to attempt this run")
    args = parser.parse_args(argv)
    if args.dates:
        if args.start is not None or args.end is not None or args.validate_staged:
            parser.error("--dates is separate from complete-month --start/--end and --validate-staged")
        days = selected_dates(args.dates)
    else:
        if args.start is None or args.end is None:
            parser.error("Provide both --start and --end, or selected --dates")
        days = completed_month_dates(args.start, args.end)
    if args.download and args.validate_staged:
        parser.error("Choose --download or --validate-staged, then validate after downloading")
    if args.download:
        if args.staged_dir is None:
            parser.error("--download requires --staged-dir")
        def report_progress(result):
            counts = result["counts"]
            print(f"{result['days_complete']}/{result['planned_days']} days validated; "
                  f"{counts['downloaded']} downloaded, {counts['already_present']} reused, "
                  f"{counts['failed']} failed, {counts['pending']} pending", flush=True)
        options = {"attempts": args.attempts, "timeout": (args.connect_timeout, args.read_timeout),
                   "backoff_seconds": args.backoff_seconds,
                   "max_consecutive_failures": args.max_consecutive_failures,
                   "max_failures": args.max_failures, "max_days": args.max_days,
                   "progress": report_progress}
        result = (download_dates(args.dates, args.staged_dir, **options) if args.dates
                  else download_range(args.start, args.end, args.staged_dir, **options))
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "complete" else 1
    result = {"source_page": SOURCE_PAGE, "download_url": DOWNLOAD_URL,
              "control_url": CONTROL_URL, "grid_documentation": GRID_DOCS,
              "days": len(days), "first_day": days[0].isoformat(), "last_day": days[-1].isoformat(),
              "expected_total_bytes": len(days) * DAY_BYTES, "grid": [NY, NX],
              "units": "mm/day", "product_status": "provisional_real_time",
              "network_requests_made": 0, "production_changes_made": False,
              "aggregation": "sum_all_calendar_days_required; missing cells remain missing",
              "source_metadata_warning": "Sample control has stale DSET/TDEF and RFANOMALY text; it cannot establish observation dates or product identity by itself"}
    if args.dates:
        result["selected_dates"] = [day.isoformat() for day in days]
    if args.validate_staged:
        if args.staged_dir is None:
            parser.error("--validate-staged requires --staged-dir")
        result["validated_months"] = []
        for year, month in sorted({(day.year, day.month) for day in days}):
            grid, sources = complete_month_grid(args.staged_dir, year, month)
            result["validated_months"].append({"year": year, "month": month,
                                               "complete_days": len(sources),
                                               "complete_grid_cells": int(np.isfinite(grid).sum())})
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
