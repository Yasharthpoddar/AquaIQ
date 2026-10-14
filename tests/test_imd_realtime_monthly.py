"""Complete daily sums and immutable provenance gate offline candidate export."""
from datetime import date
import json
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from data_ingestion import imd_realtime_monthly as monthly
from data_ingestion.imd_realtime import DOWNLOAD_URL, NY, NX, completed_month_dates
from data_ingestion.ingest_imd_era5 import validate_weather_artifact

AS_OF = date(2026, 10, 14)


def stage_day(directory, day, missing_cell=False):
    grid = np.full((NY, NX), -999., dtype="<f4")
    grid[0, :3] = [1., -999. if missing_cell else 2., 0.]
    path = directory / ("rain_" + day.strftime("%d%m%Y") + ".bin")
    grid.tofile(path)
    metadata = {"url": DOWNLOAD_URL, "form": {"rain": day.strftime("%d%m%Y")},
                "content_type": "application/octet-stream", "size_bytes": path.stat().st_size,
                "content_disposition": "attachment; filename=" + day.strftime("rain_ind0.25_%y_%m_%d.grd"),
                "sha256": monthly._sha256(path)}
    path.with_suffix(".download.json").write_text(json.dumps(metadata), encoding="utf-8")
    return path


@pytest.fixture
def export_fixture(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(monthly, "ROOT", project)
    (project / "config.yaml").write_text("paths:\n  geojson_boundaries: data/raw/india_districts.geojson\n")
    geojson = project / "data/raw/india_districts.geojson"
    geojson.parent.mkdir(parents=True)
    geojson.write_text('{"fixture": "canonical boundaries"}')
    staged = project / "data/raw/updates/run/daily"
    staged.mkdir(parents=True)
    for day in completed_month_dates("2026-02", "2026-02", AS_OF):
        stage_day(staged, day)
    annual = staged.parent / "annual.grd"
    annual.write_bytes(b"small provenanced source fixture")
    annual_sidecar = annual.with_suffix(".download.json")
    annual_sidecar.write_text('{"fixture": "annual provenance"}')
    comparison = staged.parent / "comparison.bin"
    comparison.write_bytes(b"sampled daily source fixture")
    comparison_sidecar = comparison.with_suffix(".download.json")
    comparison_sidecar.write_text('{"fixture": "sample provenance"}')
    report = staged.parent / "overlap.manifest.json"
    raw_report = {"status": "verified_overlap", "annual_source": {
        "path": str(annual), "sha256": monthly._sha256(annual),
        "sidecar_path": str(annual_sidecar), "sidecar_sha256": monthly._sha256(annual_sidecar)},
        "comparisons": [{"date": "2025-06-15", "realtime_path": str(comparison),
            "realtime_sha256": monthly._sha256(comparison), "realtime_sidecar_path": str(comparison_sidecar),
            "realtime_sidecar_sha256": monthly._sha256(comparison_sidecar)}],
        "thresholds": {"fixture": "predeclared overlap policy"},
        "date_coverage": {"fixture": "verified by comparator"}}
    report.write_text(json.dumps(raw_report), encoding="utf-8")
    report_hash = monthly._sha256(report)

    def validated_report(path, *, as_of):
        assert path == report and as_of == AS_OF
        if monthly._sha256(path) != report_hash:
            raise ValueError("Overlap report no longer passes verification")
        return {"sampled_overlap_ready": True, "report_path": str(report), "report_sha256": report_hash,
                "annual_sha256": raw_report["annual_source"]["sha256"], "status": "verified_overlap",
                "sampled_dates": ["2025-01-01", "2025-06-15", "2025-09-30"],
                "scope_limit": "Agreement covers only sampled dates.",
                "additional_requirement": "Complete all requested days.", "production_changes_made": False}

    gate = Mock(side_effect=validated_report)
    monkeypatch.setattr(monthly, "validate_verified_overlap_report", gate)
    boundaries = pd.DataFrame({"district": ["Same", "Same", None],
                               "st_nm": ["State A", "State B", "Unnamed outline"]})
    reader = Mock(return_value=boundaries)
    monkeypatch.setattr(monthly.gpd, "read_file", reader)

    def assign(points, districts):
        assert len(districts) == 2  # Unnamed state outlines cannot form districts.
        points = points.copy()
        points["district"] = "Same"
        points["st_nm"] = "State B"
        points.loc[points.index[0], "st_nm"] = "State A"
        points["spatial_method"] = "within"
        points["distance_m"] = 0.
        points["_grid_index"] = np.arange(len(points))
        return points

    assignment = Mock(side_effect=assign)
    monkeypatch.setattr(monthly, "assign_district", assignment)
    output = project / "reports/candidates/rainfall.csv"
    normals = project / "reports/candidates/normals.csv"
    return {"project": project, "staged": staged, "report": report, "geojson": geojson,
            "output": output, "normals": normals, "gate": gate, "reader": reader,
            "assignment": assignment, "annual": annual, "comparison_sidecar": comparison_sidecar,
            "assign": assign}


def export(fixture, **changes):
    arguments = {"start": "2026-02", "end": "2026-02", "staged_dir": fixture["staged"],
                 "overlap_report": fixture["report"], "output": fixture["output"],
                 "normals_output": fixture["normals"], "as_of": AS_OF}
    arguments.update(changes)
    return monthly.export_monthly(**arguments)


def assert_no_outputs(fixture):
    for path in (fixture["output"], fixture["normals"]):
        assert not path.exists() and not path.with_suffix(".manifest.json").exists()


def test_real_complete_month_exports_state_qualified_units_dates_and_daily_provenance(export_fixture):
    fixture = export_fixture
    before = {path: path.read_bytes() for path in fixture["staged"].iterdir()}
    result = export(fixture)
    assert result["days"] == 28 and result["months"] == ["2026-02"]
    assert result["production_changes_made"] is False and result["network_requests_made"] == 0
    assert {path: path.read_bytes() for path in fixture["staged"].iterdir()} == before
    frame = pd.read_csv(fixture["output"])
    assert frame[["district", "st_nm", "year", "month"]].to_dict("records") == [
        {"district": "Same", "st_nm": "State A", "year": 2026, "month": 2},
        {"district": "Same", "st_nm": "State B", "year": 2026, "month": 2}]
    assert list(frame.rainfall_mm) == [28., 28.]
    assert list(frame.n_cells) == [1, 2]
    manifest = validate_weather_artifact(fixture["output"], {"rainfall_mm": "mm/month"})
    assert manifest["daily_aggregation"] == "sum_all_calendar_days_required"
    assert manifest["generator"] == "imd_realtime_monthly"
    assert manifest["product_status"] == "provisional_real_time" and manifest["candidate_only"] is True
    assert manifest["geojson_sha256"] == monthly._sha256(fixture["geojson"])
    assert len(manifest["sources"]) == manifest["n_days"] == 28
    assert manifest["sources"][0]["date"] == "2026-02-01"
    assert manifest["sources"][-1]["date"] == "2026-02-28"
    for item in manifest["sources"]:
        assert item["sha256"] == monthly._sha256(item["path"])
        assert item["sidecar_sha256"] == monthly._sha256(item["sidecar_path"])
    assert manifest["sampled_overlap"]["report_sha256"] == monthly._sha256(fixture["report"])
    assert manifest["sampled_overlap"]["thresholds"] == {"fixture": "predeclared overlap policy"}
    assert "sampled dates" in manifest["sampled_overlap"]["scope_limit"]
    normals = pd.read_csv(fixture["normals"])
    assert normals.n_years.eq(1).all() and normals.baseline_start.eq(2026).all()
    assert normals.purpose.eq("descriptive_all_years_not_historical_model_features").all()
    validate_weather_artifact(fixture["normals"], {"rainfall_mm": "mm/month"})
    fixture["gate"].assert_called_once_with(fixture["report"], as_of=AS_OF)


def test_missing_cell_stays_missing_for_entire_month_and_real_zero_is_preserved(export_fixture):
    fixture = export_fixture
    stage_day(fixture["staged"], date(2026, 2, 15), missing_cell=True)
    export(fixture)
    points = fixture["assignment"].call_args.args[0]
    assert len(points) == 2
    assert not ((points.lat_idx == 0) & (points.lon_idx == 1)).any()
    frame = pd.read_csv(fixture["output"])
    assert list(frame.rainfall_mm) == [28., 0.]
    assert list(frame.n_cells) == [1, 1]


def test_missing_later_month_fails_before_any_output_or_spatial_work(export_fixture):
    fixture = export_fixture
    with pytest.raises(ValueError, match="Incomplete calendar month"):
        export(fixture, end="2026-03")
    assert_no_outputs(fixture)
    fixture["reader"].assert_not_called()
    fixture["assignment"].assert_not_called()


@pytest.mark.parametrize("corruption", ["missing_binary", "missing_sidecar", "checksum", "date", "source"])
def test_missing_or_changed_daily_inputs_prevent_export(export_fixture, corruption):
    fixture = export_fixture
    path = fixture["staged"] / "rain_15022026.bin"
    sidecar = path.with_suffix(".download.json")
    if corruption == "missing_binary":
        path.unlink()
    elif corruption == "missing_sidecar":
        sidecar.unlink()
    else:
        metadata = json.loads(sidecar.read_text())
        if corruption == "checksum":
            path.write_bytes(path.read_bytes() + b"changed")
        elif corruption == "date":
            metadata["form"]["rain"] = "16022026"
        else:
            metadata["url"] = "https://example.invalid/rain.php"
        sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        export(fixture)
    assert_no_outputs(fixture)
    fixture["assignment"].assert_not_called()


def test_unverified_or_changed_overlap_report_prevents_export(export_fixture):
    fixture = export_fixture
    fixture["report"].write_text('{"status": "review_required"}')
    with pytest.raises(ValueError, match="no longer passes"):
        export(fixture)
    assert_no_outputs(fixture)
    fixture["reader"].assert_not_called()


def test_different_boundary_provenance_prevents_export(export_fixture):
    fixture = export_fixture
    different = fixture["project"] / "data/raw/updates/different.geojson"
    different.write_text('{"fixture": "different district boundaries"}')
    with pytest.raises(ValueError, match="canonical boundary provenance"):
        export(fixture, geojson=different)
    assert_no_outputs(fixture)
    fixture["reader"].assert_not_called()


@pytest.mark.parametrize("changed_input", ["report", "geojson", "daily_sidecar", "annual", "comparison_sidecar"])
def test_provenance_changing_during_spatial_work_fails_before_writes(export_fixture, changed_input):
    fixture = export_fixture
    target = (fixture["staged"] / "rain_15022026.download.json" if changed_input == "daily_sidecar"
              else fixture[changed_input])

    def changing_assignment(points, districts):
        result = fixture["assign"](points, districts)
        target.write_bytes(target.read_bytes() + b"changed")
        return result

    fixture["assignment"].side_effect = changing_assignment
    with pytest.raises(ValueError, match="changed before candidate export"):
        export(fixture)
    assert_no_outputs(fixture)


@pytest.mark.parametrize("bad_output", ["processed", "active_raw", "outside", "same_csv", "overlap_alias"])
def test_output_paths_cannot_publish_or_overwrite_input_provenance(export_fixture, bad_output):
    fixture = export_fixture
    output, normals = fixture["output"], fixture["normals"]
    if bad_output == "processed":
        output = fixture["project"] / "data/processed/rainfall.csv"
    elif bad_output == "active_raw":
        output = fixture["project"] / "data/raw/imd/rainfall.csv"
    elif bad_output == "outside":
        output = fixture["project"].parent / "outside.csv"
    elif bad_output == "same_csv":
        normals = output
    else:
        output = fixture["report"].parent / "overlap.csv"  # Its manifest would replace the input report.
    original = fixture["report"].read_bytes()
    with pytest.raises(ValueError, match="Outputs must remain|must be distinct|cannot overwrite"):
        export(fixture, output=output, normals_output=normals)
    assert fixture["report"].read_bytes() == original
    assert_no_outputs(fixture)
    fixture["gate"].assert_not_called()


def test_cli_requires_explicit_candidate_output_paths(export_fixture):
    fixture = export_fixture
    with pytest.raises(SystemExit) as error:
        monthly.main(["--start", "2026-02", "--end", "2026-02", "--staged-dir", str(fixture["staged"]),
                      "--overlap-report", str(fixture["report"]), "--output", str(fixture["output"])])
    assert error.value.code == 2
    assert_no_outputs(fixture)


def test_cli_exports_only_requested_candidates(export_fixture, monkeypatch, capsys):
    fixture = export_fixture
    exporter = Mock(return_value={"status": "candidate_exported", "network_requests_made": 0})
    monkeypatch.setattr(monthly, "export_monthly", exporter)
    result = monthly.main(["--start", "2026-02", "--end", "2026-02", "--staged-dir", str(fixture["staged"]),
                           "--overlap-report", str(fixture["report"]), "--output", str(fixture["output"]),
                           "--normals-output", str(fixture["normals"])])
    exporter.assert_called_once_with("2026-02", "2026-02", fixture["staged"], fixture["report"],
                                    fixture["output"], fixture["normals"], None)
    assert json.loads(capsys.readouterr().out) == result


def test_rerun_can_replace_complete_untampered_own_candidates(export_fixture):
    fixture = export_fixture
    export(fixture)
    before = [path.read_bytes() for path in (fixture["output"], fixture["normals"])]
    fixture["gate"].reset_mock()
    result = export(fixture)
    assert result["status"] == "candidate_exported"
    assert [path.read_bytes() for path in (fixture["output"], fixture["normals"])] == before
    for path in (fixture["output"], fixture["normals"]):
        manifest = validate_weather_artifact(path, {"rainfall_mm": "mm/month"})
        assert manifest["generator"] == "imd_realtime_monthly"
    fixture["gate"].assert_called_once_with(fixture["report"], as_of=AS_OF)


@pytest.mark.parametrize("artifact", ["output", "normals"])
@pytest.mark.parametrize("existing_kind", ["unrelated_pair", "csv_only", "manifest_only", "bad_json",
                                           "tampered_csv", "wrong_generator", "not_candidate"])
def test_existing_unrelated_partial_or_tampered_outputs_fail_before_source_checks(export_fixture, artifact, existing_kind):
    fixture = export_fixture
    path = fixture[artifact]
    manifest_path = path.with_suffix(".manifest.json")
    path.parent.mkdir(parents=True)
    if existing_kind != "manifest_only":
        path.write_text("district,st_nm,year,month,rainfall_mm\nSame,State A,2025,2,35\n")
    if existing_kind != "csv_only":
        manifest = {"artifact_version": "weather-v3", "generator": "imd_realtime_monthly",
                    "candidate_only": True, "product_status": "provisional_real_time",
                    "csv_sha256": monthly._sha256(path) if path.exists() else "missing_csv"}
        if existing_kind == "unrelated_pair":
            manifest.pop("generator")
        elif existing_kind == "wrong_generator":
            manifest["generator"] = "merge_rainfall_update"
        elif existing_kind == "not_candidate":
            manifest["candidate_only"] = False
        manifest_path.write_text("not JSON" if existing_kind == "bad_json" else json.dumps(manifest))
    if existing_kind == "tampered_csv":
        path.write_text(path.read_text() + "changed after manifest hashing\n")
    before = {target: target.read_bytes() for target in (path, manifest_path) if target.exists()}
    with pytest.raises(ValueError, match="Existing"):
        export(fixture)
    assert {target: target.read_bytes() for target in before} == before
    other = fixture["normals" if artifact == "output" else "output"]
    assert not other.exists() and not other.with_suffix(".manifest.json").exists()
    fixture["gate"].assert_not_called()
    fixture["reader"].assert_not_called()
    fixture["assignment"].assert_not_called()


def test_existing_annual_merge_in_updates_is_not_an_owned_export(export_fixture):
    fixture = export_fixture
    existing = fixture["staged"].parent / "imd_1992_2025_combined.csv"
    existing.write_text("district,st_nm,year,month,rainfall_mm\nSame,State A,2025,2,35\n")
    sidecar = existing.with_suffix(".manifest.json")
    sidecar.write_text(json.dumps({"artifact_version": "weather-v3", "units": {"rainfall_mm": "mm/month"},
                                  "csv_sha256": monthly._sha256(existing), "append_provenance": {"overlap_policy": "reject"}}))
    before = [existing.read_bytes(), sidecar.read_bytes()]
    with pytest.raises(ValueError, match="unrelated"):
        export(fixture, output=existing)
    assert [existing.read_bytes(), sidecar.read_bytes()] == before
    assert_no_outputs(fixture)
    fixture["gate"].assert_not_called()


def test_interrupted_publication_leaves_partial_pair_that_rerun_refuses(export_fixture, monkeypatch):
    fixture = export_fixture
    atomic_json = monthly._atomic_json
    monkeypatch.setattr(monthly, "_atomic_json", Mock(side_effect=OSError("Interrupted before manifest publication")))
    with pytest.raises(OSError, match="Interrupted"):
        export(fixture)
    assert fixture["output"].is_file() and fixture["normals"].is_file()
    assert not fixture["output"].with_suffix(".manifest.json").exists()
    assert not fixture["normals"].with_suffix(".manifest.json").exists()
    monkeypatch.setattr(monthly, "_atomic_json", atomic_json)
    fixture["gate"].reset_mock()
    before = [path.read_bytes() for path in (fixture["output"], fixture["normals"])]
    with pytest.raises(ValueError, match="complete own-generator"):
        export(fixture)
    assert [path.read_bytes() for path in (fixture["output"], fixture["normals"])] == before
    fixture["gate"].assert_not_called()


def test_existing_candidate_modified_during_processing_is_preserved_and_not_replaced(export_fixture):
    fixture = export_fixture
    export(fixture)
    old_normals = fixture["normals"].read_bytes()

    def modifying_assignment(points, districts):
        fixture["output"].write_text("A concurrent edit must not be overwritten\n")
        return fixture["assign"](points, districts)

    fixture["assignment"].side_effect = modifying_assignment
    with pytest.raises(ValueError, match="tampered"):
        export(fixture)
    assert fixture["output"].read_text() == "A concurrent edit must not be overwritten\n"
    assert fixture["normals"].read_bytes() == old_normals
