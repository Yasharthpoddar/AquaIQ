"""Guard official groundwater extraction and fixed-geography station means."""
import hashlib
import json
from unittest.mock import Mock

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from data_ingestion import cgwb_updates as groundwater_updates
from data_ingestion.cgwb_updates import (
    FIELDS, HEADERS, HEADER_X, audit_records, build_district_lookup,
    parse_page_words, spatial_districts,
)


@pytest.fixture
def crosswalk():
    return pd.DataFrame([
        {"legacy_district_id": "100", "canonical_district_id": "AP-Krishna",
         "canonical_name": "Krishna", "canonical_state": "Andhra Pradesh"},
        {"legacy_district_id": "101", "canonical_district_id": "AP-Guntur",
         "canonical_name": "Guntur", "canonical_state": "Andhra Pradesh"},
        {"legacy_district_id": "200", "canonical_district_id": "GJ-Gandhinagar",
         "canonical_name": "Gandhinagar", "canonical_state": "Gujarat"},
    ])


@pytest.fixture
def boundaries():
    return gpd.GeoDataFrame(
        {"district": ["Krishna", "Guntur", "Gandhinagar"],
         "st_nm": ["Andhra Pradesh", "Andhra Pradesh", "Gujarat"]},
        geometry=[box(80, 16, 81, 17), box(79, 16, 80, 17), box(72, 23, 73, 24)],
        crs="EPSG:4326",
    )


def record(**changes):
    values = {
        "state_name": "Andhra Pradesh", "district_name": "Krishna",
        "block": "Example Block", "village": "Station A", "latitude": 16.5,
        "longitude": 80.5, "reported_date": "10-01-2026", "gwl_m_bgl": 10.,
        "source_month": "2026-01", "source_page": 1, "source_line_top": 80.,
        "units": "m_bgl",
    }
    return {**values, **changes}


def page_words(title="DEPTH TO WATER LEVEL (in mbgl) January - 2026"):
    # Synthetic words use the independently specified official eight columns.
    words = [{"text": title, "top": 10., "x0": 30.}]
    words.extend({"text": field, "top": 40., "x0": x}
                 for field, x in zip(HEADERS, HEADER_X))
    texts = ["Andhra Pradesh", "NTR", "Example Block", "Station A",
             "16.50", "80.50", "10-01-2026", "12.50"]
    positions = [99., 168., 283., 385., 494., 540., 604., 665.]
    words.extend({"text": field, "top": 60., "x0": x}
                 for field, x in zip(texts, positions))
    return words


def test_verified_pdf_layout_preserves_source_row_date_units_and_modern_name():
    rows = parse_page_words(list(reversed(page_words())), 7, expected_month="2026-01")
    assert len(rows) == 1
    assert {field: rows[0][field] for field in FIELDS} == {
        "state_name": "Andhra Pradesh", "district_name": "NTR",
        "block": "Example Block", "village": "Station A", "latitude": "16.50",
        "longitude": "80.50", "reported_date": "10-01-2026", "gwl_m_bgl": "12.50",
    }
    assert rows[0]["source_page"] == 7
    assert rows[0]["source_month"] == "2026-01"
    assert rows[0]["units"] == "m_bgl"
    assert rows[0]["source_line_top"] == 60.


@pytest.mark.parametrize("title", [
    "DEPTH TO WATER LEVEL (in metres above sea level) January - 2026",
    "DEPTH TO WATER LEVEL (in feet) January - 2026",
    "DEPTH TO WATER LEVEL (in mbgl)",
    "GROUNDWATER ELEVATION (in mbgl) January - 2026",
])
def test_unknown_measurement_units_or_missing_observation_month_fail(title):
    with pytest.raises(ValueError, match="unverified depth units or observation month"):
        parse_page_words(page_words(title), 1, expected_month="2026-01")


def test_pdf_source_month_must_match_requested_month():
    with pytest.raises(ValueError, match="source month disagrees"):
        parse_page_words(page_words(), 1, expected_month="2026-02")


@pytest.mark.parametrize("mutation", ["renamed_header", "shifted_column", "wrong_page_width", "empty_table"])
def test_unfamiliar_layout_or_empty_table_is_rejected(mutation):
    words = page_words()
    width = 792.
    if mutation == "renamed_header":
        words[1]["text"] = "STATE"
    elif mutation == "shifted_column":
        words[2]["x0"] += 4
    elif mutation == "wrong_page_width":
        width = 595.
    else:
        words = words[:1 + len(HEADERS)]
    with pytest.raises(ValueError):
        parse_page_words(words, 1, page_width=width, expected_month="2026-01")


def test_split_district_maps_by_actual_location_to_fixed_old_boundary(crosswalk, boundaries):
    source = pd.DataFrame([record(district_name="NTR", district_code="999")])
    audit, monthly = audit_records(source, crosswalk, as_of="2026-10-13", boundaries=boundaries)
    assert audit.loc[0, "audit_reason"] == ""
    assert audit.loc[0, "district_name"] == "NTR"
    assert audit.loc[0, "district_id"] == "AP-Krishna"
    assert audit.loc[0, "mapping_basis"] == "station_within_fixed_canonical_boundary"
    assert monthly.loc[0, "district_id"] == "AP-Krishna"
    assert monthly.loc[0, "date"] == pd.Timestamp("2026-01-01")
    assert monthly.loc[0, "first_observation_date"] == pd.Timestamp("2026-01-10")
    assert monthly.loc[0, "gwl_mean"] == 10.
    assert monthly.loc[0, "units"] == "m_bgl"
    assert bool(monthly.loc[0, "is_observed"]) is True


def test_station_outside_polygons_has_no_nearest_or_exact_name_fallback(crosswalk, boundaries):
    source = pd.DataFrame([record(longitude=82.)])
    assignments = spatial_districts(source, boundaries, build_district_lookup(crosswalk))
    assert assignments == [(None, "outside_canonical_boundaries")]
    audit, monthly = audit_records(source, crosswalk, as_of="2026-10-13", boundaries=boundaries)
    assert "unresolved_canonical_district" in audit.loc[0, "audit_reason"]
    assert monthly.empty


def test_common_boundary_between_distinct_districts_is_ambiguous(crosswalk, boundaries):
    source = pd.DataFrame([record(longitude=80.)])
    assert spatial_districts(source, boundaries, build_district_lookup(crosswalk)) == [(None, "ambiguous_boundary")]
    audit, monthly = audit_records(source, crosswalk, as_of="2026-10-13", boundaries=boundaries)
    assert audit.loc[0, "mapping_basis"] == "ambiguous_boundary"
    assert monthly.empty


def test_overlapping_polygons_for_different_districts_are_rejected(crosswalk, boundaries):
    overlap = boundaries.copy()
    overlap.loc[1, "geometry"] = box(80.2, 16.2, 80.8, 16.8)
    source = pd.DataFrame([record()])
    assert spatial_districts(source, overlap, build_district_lookup(crosswalk)) == [(None, "ambiguous_boundary")]


def test_multiple_polygon_parts_for_same_district_do_not_create_ambiguity(crosswalk, boundaries):
    same = pd.concat([boundaries, boundaries.iloc[[0]]], ignore_index=True)
    source = pd.DataFrame([record()])
    assert spatial_districts(source, same, build_district_lookup(crosswalk)) == [
        ("AP-Krishna", "station_within_fixed_canonical_boundary"),
    ]


def test_unnamed_state_outline_does_not_compete_with_district_polygon(crosswalk, boundaries):
    outline = gpd.GeoDataFrame({"district": [None], "st_nm": ["Andhra Pradesh"]},
                               geometry=[box(79, 16, 81, 17)], crs="EPSG:4326")
    combined = pd.concat([boundaries, outline], ignore_index=True)
    source = pd.DataFrame([record()])
    assert spatial_districts(source, combined, build_district_lookup(crosswalk))[0][0] == "AP-Krishna"


def test_source_state_mismatch_rejects_otherwise_valid_coordinate_match(crosswalk, boundaries):
    source = pd.DataFrame([record(state_name="Gujarat", district_name="Gandhinagar")])
    audit, monthly = audit_records(source, crosswalk, as_of="2026-10-13", boundaries=boundaries)
    assert audit.loc[0, "district_id"] == "AP-Krishna"
    assert "source_state_disagrees_with_boundary" in audit.loc[0, "audit_reason"]
    assert monthly.empty


def test_missing_crs_or_unresolved_canonical_polygon_fails_before_mapping(crosswalk, boundaries):
    source = pd.DataFrame([record()])
    no_crs = boundaries.set_crs(None, allow_override=True)
    with pytest.raises(ValueError, match="explicit CRS"):
        spatial_districts(source, no_crs, build_district_lookup(crosswalk))
    unknown = boundaries.copy()
    unknown.loc[0, "district"] = "Unknown"
    with pytest.raises(ValueError, match="unambiguous canonical"):
        spatial_districts(source, unknown, build_district_lookup(crosswalk))


def test_duplicate_readings_do_not_increase_monthly_weight_or_counts(crosswalk):
    source = pd.DataFrame([record(), record(), record(village="Station B", gwl_m_bgl=20.)])
    audit, monthly = audit_records(source, crosswalk, as_of="2026-10-13")
    assert list(audit.audit_reason) == ["", "duplicate_station_date_reading", ""]
    assert monthly.loc[0, "gwl_mean"] == 15.
    assert monthly.loc[0, "station_count"] == 2
    assert monthly.loc[0, "reading_count"] == 2


def test_conflicting_same_station_date_values_are_all_excluded(crosswalk):
    source = pd.DataFrame([record(), record(gwl_m_bgl=12.), record(village="Station B", gwl_m_bgl=20.)])
    audit, monthly = audit_records(source, crosswalk, as_of="2026-10-13")
    assert list(audit.audit_reason) == ["conflicting_station_date_depths", "conflicting_station_date_depths", ""]
    assert monthly.loc[0, "gwl_mean"] == 20.
    assert monthly.loc[0, "station_count"] == 1
    assert monthly.loc[0, "reading_count"] == 1


def test_more_frequent_station_sampling_does_not_overweight_district_average(crosswalk):
    source = pd.DataFrame([
        record(reported_date="05-01-2026", gwl_m_bgl=0.),
        record(reported_date="15-01-2026", gwl_m_bgl=10.),
        record(village="Station B", gwl_m_bgl=20.),
    ])
    audit, monthly = audit_records(source, crosswalk, as_of="2026-10-13")
    assert audit.audit_reason.eq("").all()
    # Station A averages 5 m, station B averages 20 m: (5 + 20) / 2.
    assert monthly.loc[0, "gwl_mean"] == 12.5
    assert monthly.loc[0, "station_count"] == 2
    assert monthly.loc[0, "reading_count"] == 3
    assert monthly.loc[0, "first_observation_date"] == pd.Timestamp("2026-01-05")
    assert monthly.loc[0, "last_observation_date"] == pd.Timestamp("2026-01-15")


@pytest.mark.parametrize("changes, reason", [
    ({"latitude": np.nan}, "invalid_india_coordinates"),
    ({"longitude": 181.}, "invalid_india_coordinates"),
    ({"latitude": "not-a-coordinate"}, "invalid_india_coordinates"),
    ({"gwl_m_bgl": np.inf}, "nonfinite_depth"),
    ({"gwl_m_bgl": "missing"}, "nonfinite_depth"),
    ({"gwl_m_bgl": -.1}, "negative_depth"),
    ({"reported_date": "31-02-2026"}, "invalid_reported_date"),
    ({"reported_date": "20-01-2026"}, "future_observation"),
    ({"source_month": "2026-02"}, "date_disagrees_with_source_month"),
    ({"state_name": ""}, "missing_state_district"),
    ({"district_name": ""}, "missing_state_district"),
])
def test_invalid_groundwater_source_rows_cannot_become_observations(crosswalk, boundaries, changes, reason):
    source = pd.DataFrame([record(**changes)])
    audit, monthly = audit_records(source, crosswalk, as_of="2026-01-15", boundaries=boundaries)
    assert reason in audit.loc[0, "audit_reason"].split(";")
    assert monthly.empty


def test_case_normalization_resolves_without_cross_state_guessing(crosswalk):
    source = pd.DataFrame([record(state_name="ANDHRA PRADESH", district_name="krishna")])
    audit, monthly = audit_records(source, crosswalk, as_of="2026-10-13")
    assert audit.audit_reason.eq("").all()
    assert monthly.loc[0, "district_id"] == "AP-Krishna"
    wrong_state = pd.DataFrame([record(state_name="Gujarat")])
    audit, monthly = audit_records(wrong_state, crosswalk, as_of="2026-10-13")
    assert audit.loc[0, "mapping_basis"] == "unmapped_state_district"
    assert monthly.empty


def _write_candidate_bundle(directory, frame, manifest):
    candidate = directory / "canonical_district_month_candidates.csv"
    frame.to_csv(candidate, index=False)
    manifest["output_sha256"][candidate.name] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def candidate_bundle(tmp_path, monkeypatch):
    fixture_root = tmp_path / "project"
    boundary = fixture_root / "data/raw/india_districts.geojson"
    boundary.parent.mkdir(parents=True)
    boundary.write_text("fixed-boundary-generation", encoding="utf-8")
    monkeypatch.setattr(groundwater_updates, "ROOT", fixture_root)
    directory = tmp_path / "candidate"
    directory.mkdir()
    frame = pd.DataFrame([{
        "district_id": "AP-Krishna", "date": "2026-01-01", "gwl_mean": 10.,
        "station_count": 2, "reading_count": 3,
        "first_observation_date": "2026-01-05", "last_observation_date": "2026-01-15",
        "source": "CGWB", "metric": "GWL", "units": "m_bgl", "is_observed": True,
        "date_basis": "calendar_month_of_source_reported_observation_date",
    }])
    manifest = {
        "artifact_version": "cgwb-pdf-update-v1", "units": {"gwl": "m_bgl"},
        "geojson_sha256": hashlib.sha256(boundary.read_bytes()).hexdigest(),
        "source_sha256": "source-pdf-fixture-sha256", "output_sha256": {},
    }
    _write_candidate_bundle(directory, frame, manifest)
    return directory, frame, manifest


def test_verified_groundwater_candidate_keeps_observation_dates_and_station_counts(candidate_bundle):
    directory, _, expected_manifest = candidate_bundle
    frame, manifest = groundwater_updates.validate_candidates(directory, as_of="2026-10-13")
    assert manifest == expected_manifest
    assert frame.loc[0, "date"] == pd.Timestamp("2026-01-01")
    assert frame.loc[0, "first_observation_date"] == pd.Timestamp("2026-01-05")
    assert frame.loc[0, "last_observation_date"] == pd.Timestamp("2026-01-15")
    assert frame.loc[0, "station_count"] == 2
    assert frame.loc[0, "reading_count"] == 3


def test_changed_groundwater_csv_hash_rejects_before_a_database_connection(candidate_bundle, monkeypatch):
    directory, frame, _ = candidate_bundle
    frame.loc[0, "gwl_mean"] = 999.
    frame.to_csv(directory / "canonical_district_month_candidates.csv", index=False)
    from db import connection
    connect = Mock(side_effect=AssertionError("No database connection is permitted for invalid input"))
    monkeypatch.setattr(connection, "get_connection", connect)
    with pytest.raises(ValueError, match="hash differs"):
        groundwater_updates.main(["--apply-candidates", str(directory), "--as-of", "2026-10-13"])
    connect.assert_not_called()


@pytest.mark.parametrize("field,value,message", [
    ("geojson_sha256", None, "geographic mapping"),
    ("geojson_sha256", "other-boundary-generation", "different district boundary"),
    ("units", {"gwl": "feet"}, "verified depth units"),
    ("artifact_version", "unverified-v0", "verified depth units"),
])
def test_unverified_groundwater_manifest_is_refused(candidate_bundle, field, value, message):
    directory, frame, manifest = candidate_bundle
    manifest[field] = value
    _write_candidate_bundle(directory, frame, manifest)
    with pytest.raises(ValueError, match=message):
        groundwater_updates.validate_candidates(directory, as_of="2026-10-13")


@pytest.mark.parametrize("field,value", [
    ("gwl_mean", -1.), ("gwl_mean", np.inf), ("gwl_mean", np.nan),
    ("date", "2026-01-02"), ("date", "2027-01-01"),
    ("first_observation_date", "2025-12-31"),
    ("last_observation_date", "2026-02-01"),
    ("first_observation_date", "2026-01-16"),
    ("last_observation_date", "2027-01-15"),
    ("units", "feet"), ("source", "OTHER"), ("metric", "elevation"),
    ("is_observed", False), ("station_count", 0), ("reading_count", 1),
])
def test_groundwater_candidate_valid_hash_does_not_override_value_and_date_guards(candidate_bundle, field, value):
    directory, frame, manifest = candidate_bundle
    frame.loc[0, field] = value
    _write_candidate_bundle(directory, frame, manifest)
    with pytest.raises(ValueError, match="invalid observations, dates or units"):
        groundwater_updates.validate_candidates(directory, as_of="2026-10-13")


@pytest.mark.parametrize("field", ["date", "first_observation_date", "last_observation_date"])
def test_unparseable_groundwater_candidate_dates_fail_as_validation_errors(candidate_bundle, field):
    directory, frame, manifest = candidate_bundle
    frame.loc[0, field] = "not-a-date"
    _write_candidate_bundle(directory, frame, manifest)
    with pytest.raises(ValueError):
        groundwater_updates.validate_candidates(directory, as_of="2026-10-13")


def test_duplicate_groundwater_candidate_months_are_refused(candidate_bundle):
    directory, frame, manifest = candidate_bundle
    _write_candidate_bundle(directory, pd.concat([frame, frame], ignore_index=True), manifest)
    with pytest.raises(ValueError, match="unique nonempty district months"):
        groundwater_updates.validate_candidates(directory, as_of="2026-10-13")
