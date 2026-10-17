"""Inspect COPY records in a PostgreSQL custom dump without restoring it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def inspect_copy(lines):
    tables, current, identities = {}, None, {}
    for line in lines:
        line = line.rstrip("\r\n")
        if current is not None:
            if line == r"\.":
                current = None
                continue
            row = line.split("\t")
            item = tables[current]
            if len(row) != len(item["columns"]):
                raise ValueError("Unexpected COPY field count in database export")
            item["rows"] += 1
            for column, value in zip(item["columns"], row):
                if value == r"\N":
                    item["missing_counts"][column] += 1
                elif column == "district_id":
                    identities[current].add(value)
                elif column in ("date", "forecast_date"):
                    item["date_start"] = min(item["date_start"] or value, value)
                    item["date_end"] = max(item["date_end"] or value, value)
            continue
        match = re.match(r'^COPY ([\w."-]+) \((.+)\) FROM stdin;$', line)
        if match:
            current = match.group(1)
            columns = [column.strip().strip('"') for column in match.group(2).split(",")]
            tables[current] = {"columns": columns, "rows": 0, "date_start": None, "date_end": None,
                               "missing_counts": dict.fromkeys(columns, 0)}
            identities[current] = set()
    if current is not None:
        raise ValueError("Truncated COPY section in database export")
    for name, item in tables.items():
        item["districts"] = len(identities[name])
        item["numeric_district_ids"] = sum(value.isdigit() for value in identities[name])
    return tables


def locate_restore():
    executable = shutil.which("pg_restore")
    if executable:
        return executable
    windows = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "PostgreSQL"
    candidates = sorted(windows.glob("*/bin/pg_restore.exe"))
    if candidates:
        return str(candidates[-1])
    raise RuntimeError("Install the matching PostgreSQL client or put pg_restore on PATH")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=ROOT / "data/backup_pre_d1_migration.dump")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/audit-2026-10-17/database_export.json")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "reports") or output.suffix.lower() != ".json":
        parser.error("Export audit must be a JSON report under reports/")
    with args.file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    # Passing --file=- generates SQL on stdout. No database connection is made.
    command = [locate_restore(), "--data-only", "--no-owner", "--no-privileges", "--file=-", str(args.file)]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, encoding="utf-8") as process:
        tables = inspect_copy(process.stdout)
        if process.wait() != 0:
            raise RuntimeError("pg_restore could not inspect the export; no restoration was attempted")
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "path": str(args.file),
              "sha256": digest, "bytes": args.file.stat().st_size, "database_connected": False,
              "tables": tables, "limitation": "Historical backup; rows are not merged with current data, and units/provenance are not inferred."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({name: item["rows"] for name, item in tables.items()}))
    return report


if __name__ == "__main__":
    main()
