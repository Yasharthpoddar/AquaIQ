"""Append verified, non-overlapping rainfall months to an isolated artifact.

Does not change production files or the database. The original daily binaries,
district boundaries and source manifests remain the provenance of the output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data_ingestion.ingest_imd_era5 import validate_weather_artifact


def merge_rainfall(old_path, update_path, output_path, normals_path):
    old_path, update_path, output_path, normals_path = map(Path, (old_path, update_path, output_path, normals_path))
    if output_path.resolve() in {old_path.resolve(), update_path.resolve()}:
        raise ValueError("Merged rainfall must be staged separately from its input artifacts")
    if normals_path.resolve() in {old_path.resolve(), update_path.resolve(), output_path.resolve()}:
        raise ValueError("Rainfall normals must be staged separately from input and merged artifacts")
    manifests = [validate_weather_artifact(path, {"rainfall_mm": "mm/month"})
                 for path in (old_path, update_path)]
    if (not manifests[0].get("geojson_sha256") or not manifests[1].get("geojson_sha256")
            or manifests[0]["geojson_sha256"] != manifests[1]["geojson_sha256"]
            or any(item.get("daily_aggregation") != "sum_all_calendar_days_required" for item in manifests)):
        raise ValueError("Rainfall updates require matching boundaries and complete-day monthly totals")
    frames = [pd.read_csv(path) for path in (old_path, update_path)]
    keys = ["district", "st_nm", "year", "month"]
    for frame in frames:
        if (frame.empty or frame.duplicated(keys).any() or frame[keys].isna().any().any()
                or not frame.month.between(1, 12).all() or not np.isfinite(frame.rainfall_mm).all()
                or frame.rainfall_mm.lt(0).any()):
            raise ValueError("Rainfall input has invalid or duplicate district months")
    if not frames[0][keys].merge(frames[1][keys], on=keys).empty:
        raise ValueError("Rainfall update overlaps existing months; corrections need a separate audited procedure")
    merged = pd.concat(frames, ignore_index=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    # Describe the data available; feature engineering still uses causal
    # expanding prior-year normals, not these descriptive all-year averages.
    normals = merged.groupby(["district", "st_nm", "month"]).agg(
        climatological_normal_mm=("rainfall_mm", "mean"), n_years=("year", "nunique"),
        baseline_start=("year", "min"), baseline_end=("year", "max")).reset_index()
    normals["purpose"] = "descriptive_all_years_not_historical_model_features"
    normals_path.parent.mkdir(parents=True, exist_ok=True)
    normals.to_csv(normals_path, index=False)
    metadata = {**manifests[0], "generator": "merge_rainfall_update",
                "sources": manifests[0]["sources"] + manifests[1]["sources"],
                "baseline_start": int(merged.year.min()), "baseline_end": int(merged.year.max()),
                "n_years": int(merged.year.nunique()),
                "csv_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
                "append_provenance": {"existing_csv_sha256": manifests[0]["csv_sha256"],
                                      "update_csv_sha256": manifests[1]["csv_sha256"],
                                      "existing_rows": len(frames[0]), "appended_rows": len(frames[1]),
                                      "overlap_policy": "reject"}}
    # A provisional daily update must not inherit the old annual artifact's
    # identity without retaining its different source/verification status.
    update_status = manifests[1].get("product_status")
    if update_status is not None:
        metadata["append_provenance"]["update_product_status"] = update_status
    if "sampled_overlap" in manifests[1]:
        metadata["append_provenance"]["sampled_overlap"] = manifests[1]["sampled_overlap"]
    statuses = set(manifests[0].get("source_product_statuses", []))
    statuses.update(item["product_status"] for item in metadata["sources"] if item.get("product_status"))
    statuses.update(item["product_status"] for item in manifests if item.get("product_status"))
    if statuses:
        metadata["source_product_statuses"] = sorted(statuses)
        metadata["contains_provisional_real_time"] = (
            "provisional_real_time" in statuses or bool(manifests[0].get("contains_provisional_real_time")))
    output_path.with_suffix(".manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    normals_path.with_suffix(".manifest.json").write_text(json.dumps({**metadata,
        "csv_sha256": hashlib.sha256(normals_path.read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
    return metadata["append_provenance"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--update", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--normals-output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(merge_rainfall(args.existing, args.update, args.output, args.normals_output), indent=2))


if __name__ == "__main__":
    main()
