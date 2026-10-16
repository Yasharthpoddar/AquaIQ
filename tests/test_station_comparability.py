"""Checks for matched-well comparisons without invented station identities."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

MODULE = Path(__file__).resolve().parents[1] / "data_ingestion/station_comparability.py"
spec = importlib.util.spec_from_file_location("station_comparability_under_test", MODULE)
station = importlib.util.module_from_spec(spec)
spec.loader.exec_module(station)


def sample(month="2026-01", depth=10., **changes):
    row = {"state_name": "Gujarat", "district_name": "Gandhinagar", "block": "Kalol",
        "village": "Village A", "latitude": 23.23, "longitude": 72.63,
        "gwl_m_bgl": depth, "units": "m_bgl", "source_sha256": "a" * 64,
        "source_file": "official.pdf", "source_month": month,
        "observation_date": month + "-10", "district_id": "GJ-Gandhinagar", "audit_reason": ""}
    row.update(changes)
    return row


def compare(a, b):
    return station.compare_snapshots([pd.DataFrame(a), pd.DataFrame(b)], as_of="2026-10-15")


def test_separates_matched_changes_from_network_composition():
    before = [sample(depth=10), sample(depth=90, village="Village B", latitude=23.3)]
    after = [sample("2026-04", 12), sample("2026-04", 1, village="Village C", latitude=23.4)]
    report, matches = compare(before, after)
    pair = report["pairs"][0]
    assert pair["matched_stations"] == 1
    assert pair["matched_mean_depth_change_m"] == 2
    assert pair["all_station_mean_change_m"] == -43.5
    assert pair["composition_changed"] is True
    assert pair["overlap_fraction_before"] == .5
    assert pair["districts"][0]["matched_mean_depth_change_m"] == 2
    assert matches.iloc[0].aquifer_metadata_consistent == False
    assert not report["calibrated"]


def test_district_rename_does_not_create_different_station():
    report, _ = compare([sample()], [sample("2026-04", 12, district_name="Renamed district")])
    assert report["pairs"][0]["matched_stations"] == 1


@pytest.mark.parametrize("field,new", [("district_id", "GJ-Other"), ("aquifer", "confined"), ("station_id", "new-well")])
def test_metadata_conflict_excludes_pair(field, new):
    report, _ = compare([sample()], [sample("2026-04", 12, **{field: new})])
    assert report["pairs"][0]["matched_stations"] == 0
    assert report["pairs"][0]["pair_exclusions"]


def test_canonical_ids_are_not_merged_by_punctuation_normalization():
    report, _ = compare([sample(district_id="GJ-One_Two")],
        [sample("2026-04", 12, district_id="GJ-One-Two")])
    assert report["pairs"][0]["matched_stations"] == 0


def test_future_analysis_cutoff_is_not_a_future_observation_escape():
    with pytest.raises(ValueError, match="no later than today"):
        station.prepare_snapshot(pd.DataFrame([sample()]), as_of="2099-01-01")


def test_source_well_ids_and_aquifers_are_retained():
    report, matches = compare([sample(station_id="GJ-001", aquifer="Unconfined")],
        [sample("2026-04", 12, station_id="GJ-001", aquifer="Unconfined")])
    assert report["pairs"][0]["matched_stations"] == 1
    assert matches.iloc[0].source_station_id_present
    assert matches.iloc[0].aquifer_metadata_consistent


def test_no_nearest_coordinate_matching():
    report, _ = compare([sample()], [sample("2026-04", 12, latitude=23.2301)])
    assert report["pairs"][0]["matched_stations"] == 0


def test_identical_duplicates_count_once_and_conflicts_are_removed():
    rows = [sample(), sample(), sample(depth=20, village="B"), sample(depth=21, village="B")]
    report, _ = compare(rows, [sample("2026-04", 12)])
    assert report["snapshots"][0]["accepted_readings"] == 1
    assert report["snapshots"][0]["exclusion_reasons"]["conflicting_station_date_depths"] == 2
    assert report["pairs"][0]["matched_stations"] == 1


def test_ambiguous_well_at_same_location_is_not_averaged():
    frame = pd.DataFrame([sample(station_id="one"), sample(station_id="two", observation_date="2026-01-11")])
    accepted, _, report = station.prepare_snapshot(frame, as_of="2026-10-15")
    assert accepted.empty
    assert report["exclusion_reasons"]["ambiguous_station_id"] == 2


def test_multiple_actual_dates_are_equal_weight_station_means():
    before = [sample(depth=10), sample(depth=14, observation_date="2026-01-11")]
    report, _ = compare(before, [sample("2026-04", 15)])
    assert report["pairs"][0]["matched_mean_depth_change_m"] == 3


@pytest.mark.parametrize("change,reason", [
    ({"observation_date": "2027-01-01", "source_month": "2027-01"}, "future_observation"),
    ({"observation_date": "bad"}, "invalid_observation_date"),
    ({"source_month": "2026-02"}, "source_month_mismatch"),
    ({"units": "feet"}, "unverified_units"),
    ({"source_sha256": "not-a-hash"}, "missing_source_digest"),
    ({"latitude": 0}, "invalid_coordinates"),
    ({"gwl_m_bgl": float("inf")}, "invalid_depth"),
    ({"audit_reason": "unresolved_canonical_district"}, "source_audit_rejected"),
    ({"village": ""}, "missing_village"),
])
def test_invalid_rows_are_audited(change, reason):
    accepted, audit, report = station.prepare_snapshot(pd.DataFrame([sample(**change)]), as_of="2026-10-15")
    assert accepted.empty
    assert reason in audit.iloc[0].comparison_rejection
    assert report["excluded_rows"] == 1


def test_raw_extraction_schema_can_match_without_inventing_canonical_district():
    before = sample()
    before.pop("audit_reason")
    before.pop("district_id")
    before["reported_date"] = "10-01-2026"
    before.pop("observation_date")
    after = {**before, "source_month": "2026-04", "reported_date": "10-04-2026", "gwl_m_bgl": 11}
    report, _ = compare([before], [after])
    assert report["pairs"][0]["matched_stations"] == 1
    assert report["pairs"][0]["districts"] == []
    assert not report["snapshots"][0]["source_audit_present"]


def test_audit_does_not_override_conflicting_reported_date():
    accepted, audit, _ = station.prepare_snapshot(pd.DataFrame([
        sample(reported_date="11-01-2026")]), as_of="2026-10-15")
    assert accepted.empty
    assert "reported_and_audited_date_mismatch" in audit.iloc[0].comparison_rejection


def test_two_distinct_snapshot_months_are_required():
    with pytest.raises(ValueError, match="At least two"):
        station.compare_snapshots([pd.DataFrame([sample()])], as_of="2026-10-15")
    with pytest.raises(ValueError, match="distinct"):
        compare([sample()], [sample()])
    with pytest.raises(ValueError, match="one observation month"):
        compare([sample(), sample("2026-04")], [sample("2026-05")])


def test_output_guards_existing_sources_and_active_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(station, "ROOT", tmp_path)
    source = tmp_path / "reports/candidates/source.csv"
    source.parent.mkdir(parents=True)
    source.write_text("keep")
    for bad in (source, tmp_path / "data/processed/replace.csv", tmp_path.parent / "escape.csv"):
        with pytest.raises(ValueError):
            station.candidate_output(bad, [source])
    assert station.candidate_output(source.parent / "new.json", [source]).name == "new.json"


def test_default_cli_is_offline(capsys):
    assert station.main([]) == 0
    assert '"status": "offline_plan"' in capsys.readouterr().out
