"""Verified rainfall updates append months without changing historical values."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from data_ingestion.ingest_imd_era5 import validate_weather_artifact
from data_ingestion.merge_rainfall_update import merge_rainfall


def _write_rainfall_artifact(path, frame, *, year, **changes):
    frame.to_csv(path, index=False)
    manifest = {
        "artifact_version": "weather-v3", "units": {"rainfall_mm": "mm/month"},
        "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "geojson_sha256": "fixed-canonical-boundaries-sha256",
        "daily_aggregation": "sum_all_calendar_days_required",
        "sources": [{"year": year, "path": f"ind{year}.grd", "sha256": f"source-{year}-sha256"}],
        "baseline_start": year, "baseline_end": year, "n_years": 1,
        "climatology_purpose": "descriptive_only", **changes,
    }
    path.with_suffix(".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


@pytest.fixture
def rainfall_bundle(tmp_path):
    old = pd.DataFrame({
        "district": ["Gandhinagar", "Krishna", "Gandhinagar"],
        "st_nm": ["Gujarat", "Andhra Pradesh", "Gujarat"],
        "year": [2024, 2024, 2024], "month": [1, 1, 2],
        "rainfall_mm": [12.5, 0., 30.],
        "spatial_method": ["within_district"] * 3, "n_cells": [2, 3, 2],
    })
    update = old.copy()
    update["year"] = 2025
    update["rainfall_mm"] = [22.5, 2., 40.]
    existing_path = tmp_path / "existing.csv"
    update_path = tmp_path / "update.csv"
    _write_rainfall_artifact(existing_path, old, year=2024)
    _write_rainfall_artifact(update_path, update, year=2025)
    return existing_path, update_path, tmp_path / "merged.csv", tmp_path / "normals.csv", old, update


def test_merge_preserves_original_rows_and_inputs_with_append_provenance(rainfall_bundle):
    existing, update, output, normals, old_frame, update_frame = rainfall_bundle
    original_inputs = [path.read_bytes() for path in (existing, update)]
    original_manifests = [path.with_suffix(".manifest.json").read_bytes() for path in (existing, update)]
    provenance = merge_rainfall(existing, update, output, normals)
    merged = pd.read_csv(output)
    pd.testing.assert_frame_equal(merged.iloc[:len(old_frame)].reset_index(drop=True), old_frame)
    pd.testing.assert_frame_equal(merged.iloc[len(old_frame):].reset_index(drop=True), update_frame)
    assert [path.read_bytes() for path in (existing, update)] == original_inputs
    assert [path.with_suffix(".manifest.json").read_bytes() for path in (existing, update)] == original_manifests
    assert provenance == {
        "existing_csv_sha256": hashlib.sha256(original_inputs[0]).hexdigest(),
        "update_csv_sha256": hashlib.sha256(original_inputs[1]).hexdigest(),
        "existing_rows": 3, "appended_rows": 3, "overlap_policy": "reject",
    }
    manifest = validate_weather_artifact(output, {"rainfall_mm": "mm/month"})
    assert [source["year"] for source in manifest["sources"]] == [2024, 2025]
    assert manifest["baseline_start"] == 2024
    assert manifest["baseline_end"] == 2025
    assert manifest["n_years"] == 2


def test_all_year_normals_are_descriptive_with_explicit_year_coverage(rainfall_bundle):
    existing, update, output, normals, _, _ = rainfall_bundle
    merge_rainfall(existing, update, output, normals)
    frame = pd.read_csv(normals)
    assert frame.purpose.eq("descriptive_all_years_not_historical_model_features").all()
    january = frame.loc[(frame.district == "Gandhinagar") & (frame.month == 1)].iloc[0]
    assert january.climatological_normal_mm == 17.5
    assert january.n_years == 2
    assert january.baseline_start == 2024
    assert january.baseline_end == 2025
    manifest = validate_weather_artifact(normals, {"rainfall_mm": "mm/month"})
    assert manifest["climatology_purpose"] == "descriptive_only"


def test_provisional_update_and_sampled_verification_remain_visible_after_merge(rainfall_bundle):
    existing, update, output, normals, _, new_frame = rainfall_bundle
    overlap = {"sampled_overlap_ready": True, "report_sha256": "sample-report-hash",
               "scope_limit": "Agreement covers sampled dates only."}
    _write_rainfall_artifact(update, new_frame, year=2025,
                             product_status="provisional_real_time", sampled_overlap=overlap,
                             sources=[{"year": 2025, "path": "rain_01012025.bin", "sha256": "daily-source",
                                       "product_status": "provisional_real_time"}])
    provenance = merge_rainfall(existing, update, output, normals)
    assert provenance["update_product_status"] == "provisional_real_time"
    assert provenance["sampled_overlap"] == overlap
    for path in (output, normals):
        manifest = validate_weather_artifact(path, {"rainfall_mm": "mm/month"})
        assert manifest["contains_provisional_real_time"] is True
        assert manifest["source_product_statuses"] == ["provisional_real_time"]
        assert manifest["sources"][-1]["product_status"] == "provisional_real_time"
        assert manifest["append_provenance"]["sampled_overlap"] == overlap


def test_existing_district_month_overlap_is_rejected_without_outputs(rainfall_bundle):
    existing, update, output, normals, old, _ = rainfall_bundle
    _write_rainfall_artifact(update, old.iloc[[0]], year=2024)
    with pytest.raises(ValueError, match="overlaps existing months"):
        merge_rainfall(existing, update, output, normals)
    assert not output.exists() and not normals.exists()


@pytest.mark.parametrize("which", ["existing", "update"])
def test_csv_hash_failure_blocks_merge(rainfall_bundle, which):
    existing, update, output, normals, _, _ = rainfall_bundle
    target = existing if which == "existing" else update
    target.write_text(target.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash does not match"):
        merge_rainfall(existing, update, output, normals)
    assert not output.exists() and not normals.exists()


@pytest.mark.parametrize("changes", [
    {"geojson_sha256": "different-canonical-boundaries"},
    {"daily_aggregation": "mean_of_available_days"},
    {"daily_aggregation": None},
])
def test_boundaries_and_complete_calendar_day_metadata_must_agree(rainfall_bundle, changes):
    existing, update, output, normals, _, new = rainfall_bundle
    _write_rainfall_artifact(update, new, year=2025, **changes)
    with pytest.raises(ValueError, match="matching boundaries and complete-day monthly totals"):
        merge_rainfall(existing, update, output, normals)
    assert not output.exists() and not normals.exists()


def test_matching_missing_boundary_hashes_do_not_establish_geographic_provenance(rainfall_bundle):
    existing, update, output, normals, old, new = rainfall_bundle
    _write_rainfall_artifact(existing, old, year=2024, geojson_sha256=None)
    _write_rainfall_artifact(update, new, year=2025, geojson_sha256=None)
    with pytest.raises(ValueError, match="matching boundaries and complete-day monthly totals"):
        merge_rainfall(existing, update, output, normals)
    assert not output.exists() and not normals.exists()


@pytest.mark.parametrize("field,value", [
    ("rainfall_mm", -1.), ("rainfall_mm", np.inf), ("rainfall_mm", np.nan),
    ("month", 0), ("month", 13), ("district", None),
])
def test_invalid_rainfall_months_are_rejected_before_writing(rainfall_bundle, field, value):
    existing, update, output, normals, _, new = rainfall_bundle
    new.loc[0, field] = value
    _write_rainfall_artifact(update, new, year=2025)
    with pytest.raises(ValueError, match="invalid or duplicate district months"):
        merge_rainfall(existing, update, output, normals)
    assert not output.exists() and not normals.exists()


def test_duplicate_rainfall_months_are_rejected(rainfall_bundle):
    existing, update, output, normals, _, new = rainfall_bundle
    _write_rainfall_artifact(update, pd.concat([new, new.iloc[[0]]], ignore_index=True), year=2025)
    with pytest.raises(ValueError, match="invalid or duplicate district months"):
        merge_rainfall(existing, update, output, normals)


@pytest.mark.parametrize("input_name", ["existing", "update"])
def test_merged_output_cannot_overwrite_input(rainfall_bundle, input_name):
    existing, update, _, normals, _, _ = rainfall_bundle
    target = existing if input_name == "existing" else update
    original = target.read_bytes()
    with pytest.raises(ValueError, match="staged separately"):
        merge_rainfall(existing, update, target, normals)
    assert target.read_bytes() == original


@pytest.mark.parametrize("target_name", ["existing", "update", "merged"])
def test_normals_cannot_overwrite_either_input_or_merged_artifact(rainfall_bundle, target_name):
    existing, update, output, _, _, _ = rainfall_bundle
    target = {"existing": existing, "update": update, "merged": output}[target_name]
    original_inputs = [path.read_bytes() for path in (existing, update)]
    with pytest.raises(ValueError):
        merge_rainfall(existing, update, output, target)
    assert [path.read_bytes() for path in (existing, update)] == original_inputs
