"""Official source integrity, conservative identities, and observed-only means."""
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from data_ingestion import nwdp_manual as manual


@pytest.fixture
def crosswalk():
    return pd.DataFrame([
        {"legacy_district_id": "1", "canonical_district_id": "GJ-A", "canonical_name": "A", "canonical_state": "Gujarat"},
        {"legacy_district_id": "2", "canonical_district_id": "GJ-B", "canonical_name": "B", "canonical_state": "Gujarat"},
    ])


@pytest.fixture
def boundaries():
    return gpd.GeoDataFrame({"district": ["A", "B"], "st_nm": ["Gujarat", "Gujarat"]},
                            geometry=[box(70, 20, 71, 21), box(71, 20, 72, 21)], crs="EPSG:4326")


def record(**changes):
    return {**{"state_name": "Gujarat", "district_name": "A", "station_name": "Well 1", "Agency": "CGWB",
               "latitude": 20.5, "longitude": 70.5, "gwl_m_bgl": 5., "units": "m_bgl",
               "observation_timestamp": pd.Timestamp("2023-01-10 06:00"), "source_month": "2023-01",
               "source_resource_id": "example", "source_sha256": "0" * 64}, **changes}


def audit(rows, crosswalk, boundaries, **kwargs):
    return manual.audit_manual(pd.DataFrame(rows), crosswalk, boundaries, as_of="2026-10-26", **kwargs)


def csv_source(tmp_path, **changes):
    row = dict.fromkeys(manual.CSV_COLUMNS, "-")
    row.update({"SlNo": "1", "Station": "Well 1", "Agency": "CGWB", "State LGD Code": "24", "State": "Gujarat",
                "District LGD Code": "1", "District": "A", "Latitude": "20.50000000", "Longitude": "70.50000000",
                "Data Acquisition Time": "10-01-2023 06:00", manual.VALUE_COLUMN: "5", **changes})
    path = tmp_path / "gwl_manual_quarterly_cgwb_gj_2021_2025.csv"
    pd.DataFrame([row], columns=manual.CSV_COLUMNS).to_csv(path, index=False)
    return path


def parse(path, digest=None):
    return manual.parse_csv(path, source_url="https://nwdp.nwic.gov.in/dataset/x/resource/y/download/example.csv",
                            resource_id="y", expected_sha256=digest or manual.sha256(path))


def test_parser_preserves_actual_time_provider_columns_hash_row_and_units(tmp_path):
    path = csv_source(tmp_path)
    frame = parse(path)
    row = frame.iloc[0]
    assert row.observation_timestamp == pd.Timestamp("2023-01-10 06:00")
    assert row.observation_date == pd.Timestamp("2023-01-10")
    assert row.date == pd.Timestamp("2023-01-01")
    assert row.source_month == "2023-01"
    assert row.source_row == 2
    assert row.units == "m_bgl"
    assert row.RL_MSL == "-"
    assert row.source_sha256 == manual.sha256(path)
    assert row.datum_basis == manual.DATUM_URL


def test_changed_source_hash_fails_before_parsing(tmp_path):
    path = csv_source(tmp_path)
    with pytest.raises(ValueError, match="checksum"):
        parse(path, "0" * 64)


@pytest.mark.parametrize("mutation", ["rename_units", "extra_column", "missing_column", "reorder"])
def test_unreviewed_schema_or_unit_change_fails(tmp_path, mutation):
    path = csv_source(tmp_path)
    frame = pd.read_csv(path)
    if mutation == "rename_units":
        frame = frame.rename(columns={manual.VALUE_COLUMN: "Groundwater elevation MSL"})
    elif mutation == "extra_column":
        frame["New"] = "value"
    elif mutation == "missing_column":
        frame = frame.drop(columns="RL_MSL")
    else:
        frame = frame[frame.columns[::-1]]
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="schema"):
        parse(path)


def test_advertised_2026_2030_header_only_resource_is_valid_but_empty(tmp_path):
    path = tmp_path / "empty.csv"
    pd.DataFrame(columns=manual.CSV_COLUMNS).to_csv(path, index=False)
    frame = parse(path)
    assert frame.empty
    assert "source_sha256" in frame


def test_telemetry_keeps_provider_sign_and_cannot_enter_manual_aggregation(tmp_path, crosswalk, boundaries):
    path = csv_source(tmp_path)
    source = pd.read_csv(path, dtype=str, keep_default_na=False)
    source = source.rename(columns={manual.VALUE_COLUMN: manual.TELEMETRY_VALUE_COLUMN})
    source[manual.TELEMETRY_VALUE_COLUMN] = "-4.69"
    source.to_csv(path, index=False)
    frame = manual.parse_telemetry_csv(path, source_url="https://nwdp.nwic.gov.in/data.csv", resource_id="y", expected_sha256=manual.sha256(path))
    assert frame.iloc[0].gwl_m_bgl == "-4.69"
    assert frame.iloc[0].units == "m_provider_sign_unverified"
    result, _, monthly = audit(frame.to_dict("records"), crosswalk, boundaries)
    assert "unverified_units" in result.iloc[0].audit_reason
    assert "unverified_manual_product" in result.iloc[0].audit_reason
    assert monthly.empty


def test_telemetry_schema_is_not_accepted_as_manual(tmp_path):
    path = csv_source(tmp_path)
    source = pd.read_csv(path).rename(columns={manual.VALUE_COLUMN: manual.TELEMETRY_VALUE_COLUMN})
    source.to_csv(path, index=False)
    with pytest.raises(ValueError, match="schema"):
        parse(path)


@pytest.mark.parametrize("changes,reason", [
    ({"gwl_m_bgl": "dry"}, "nonfinite_depth"),
    ({"gwl_m_bgl": np.inf}, "nonfinite_depth"),
    ({"gwl_m_bgl": -1}, "negative_depth_review"),
    ({"gwl_m_bgl": 1374}, "depth_over_300m_review"),
    ({"latitude": 0}, "invalid_india_coordinates"),
    ({"longitude": 181}, "invalid_india_coordinates"),
    ({"observation_timestamp": "bad"}, "invalid_reported_timestamp"),
    ({"observation_timestamp": pd.Timestamp("2027-01-10")}, "future_observation"),
    ({"observation_timestamp": pd.Timestamp("2019-01-10")}, "before_declared_enrichment_period"),
    ({"units": "feet"}, "unverified_units"),
    ({"source_month": "2023-02"}, "date_disagrees_with_source_month"),
    ({"Agency": "unknown"}, "unverified_agency"),
    ({"station_name": "-"}, "missing_station_label"),
    ({"station_name": "Example Spring"}, "spring_measurement_type_review"),
    ({"state_name": "Rajasthan"}, "source_state_disagrees_with_boundary"),
    ({"longitude": 73}, "unresolved_canonical_district"),
    ({"longitude": 70.9995}, "near_boundary_coordinate_review"),
])
def test_invalid_ambiguous_or_unverified_records_cannot_become_observed_months(crosswalk, boundaries, changes, reason):
    result, _, monthly = audit([record(**changes)], crosswalk, boundaries)
    assert reason in result.iloc[0].audit_reason.split(";")
    assert monthly.empty


def test_source_district_rename_does_not_override_coordinate_mapping(crosswalk, boundaries):
    result, _, monthly = audit([record(district_name="Newer name")], crosswalk, boundaries)
    assert result.iloc[0].audit_reason == ""
    assert result.iloc[0].district_id == "GJ-A"
    assert monthly.iloc[0].station_count == 1


def test_boundary_rule_cannot_be_silently_weakened(crosswalk, boundaries):
    with pytest.raises(ValueError, match="cannot weaken"):
        audit([record()], crosswalk, boundaries, boundary_margin=0)


def test_duplicate_timestamp_depth_not_extra_station_weight(crosswalk, boundaries):
    result, station, monthly = audit([record(), record(), record(station_name="Well 2", longitude=70.6, gwl_m_bgl=15)], crosswalk, boundaries)
    assert result.audit_reason.tolist() == ["", "duplicate_station_timestamp_reading", ""]
    assert len(station) == 2
    assert monthly.iloc[0].gwl_mean == 10
    assert monthly.iloc[0].reading_count == 2


def test_same_station_timestamp_conflicting_values_all_quarantined(crosswalk, boundaries):
    result, _, monthly = audit([record(), record(gwl_m_bgl=7)], crosswalk, boundaries)
    assert result.audit_reason.str.contains("conflicting_station_timestamp_depths").all()
    assert monthly.empty


def test_suffix_aliases_at_same_location_are_quarantined_not_fuzzily_merged(crosswalk, boundaries):
    result, _, monthly = audit([record(), record(station_name="Well 1_1")], crosswalk, boundaries)
    assert result.audit_reason.str.contains("ambiguous_colocated_station_labels").all()
    assert monthly.empty


def test_distinct_station_suffixes_at_distinct_coordinates_remain_distinct(crosswalk, boundaries):
    result, station, monthly = audit([record(), record(station_name="Well 1_1", longitude=70.6, gwl_m_bgl=9)], crosswalk, boundaries)
    assert result.audit_reason.eq("").all()
    assert len(station) == 2
    assert monthly.iloc[0].gwl_mean == 7


def test_many_timestamps_station_means_receive_equal_district_weight(crosswalk, boundaries):
    rows = [record(), record(observation_timestamp=pd.Timestamp("2023-01-20 06:00"), gwl_m_bgl=15),
            record(station_name="Well 2", longitude=70.6, gwl_m_bgl=30)]
    _, _, monthly = audit(rows, crosswalk, boundaries)
    assert monthly.iloc[0].gwl_mean == 20  # ((5 + 15) / 2 + 30) / 2
    assert monthly.iloc[0].reading_count == 3
    assert monthly.iloc[0].first_observation_date == pd.Timestamp("2023-01-10")
    assert monthly.iloc[0].last_observation_date == pd.Timestamp("2023-01-20")
    assert bool(monthly.iloc[0].is_observed)


@pytest.mark.parametrize("old_value,reason", [(5, "already_in_existing_raw"), (8, "conflicts_with_existing_raw_review")])
def test_old_daily_observations_not_reinserted_or_overwritten(crosswalk, boundaries, old_value, reason):
    old = pd.DataFrame([{"state_name": "Gujarat", "station_name": "Well 1", "latitude": 20.5,
                         "longitude": 70.5, "date": "2023-01-10", "currentlevel": old_value}])
    result, _, monthly = audit([record()], crosswalk, boundaries, existing_raw=old)
    assert reason in result.iloc[0].audit_reason
    assert monthly.empty
    assert old.iloc[0].currentlevel == old_value


def test_raw_match_does_not_merge_merely_similar_station_labels(crosswalk, boundaries):
    old = pd.DataFrame([{"state_name": "Gujarat", "station_name": "Well 1_1", "latitude": 20.5,
                         "longitude": 70.5, "date": "2023-01-10", "currentlevel": 5}])
    result, _, monthly = audit([record()], crosswalk, boundaries, existing_raw=old)
    assert result.iloc[0].existing_raw_status == "new_station_date"
    assert len(monthly) == 1


def test_replay_deterministic_and_future_measurement_does_not_alter_past_month(crosswalk, boundaries):
    rows = [record(), record(observation_timestamp=pd.Timestamp("2024-01-10"), source_month="2024-01", gwl_m_bgl=20)]
    _, _, both = audit(rows, crosswalk, boundaries)
    _, _, past = audit(rows[:1], crosswalk, boundaries)
    pd.testing.assert_frame_equal(both.iloc[:1].reset_index(drop=True), past)
    _, _, replay = audit(list(reversed(rows)), crosswalk, boundaries)
    pd.testing.assert_frame_equal(both, replay)


def test_download_never_overwrites_existing_source(tmp_path):
    path = tmp_path / "raw.csv"
    path.write_bytes(b"immutable")
    client = Mock()
    result = manual._download("https://nwdp.nwic.gov.in/data.csv", path, session=client)
    assert result["sha256"] == hashlib.sha256(b"immutable").hexdigest()
    assert result["reused_existing"]
    client.get.assert_not_called()


def test_successful_download_is_atomic_and_hashed(tmp_path):
    response = Mock()
    response.url = "https://nwdp.nwic.gov.in/data.csv"
    response.status_code = 200
    response.headers = {"Content-Type": "text/csv", "Content-Length": "6"}
    response.iter_content.return_value = iter([b"abc", b"def"])
    client = Mock()
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=None)
    client.get.return_value = context
    path = tmp_path / "out.csv"
    result = manual._download(response.url, path, session=client, max_bytes=6)
    assert path.read_bytes() == b"abcdef"
    assert result["sha256"] == hashlib.sha256(b"abcdef").hexdigest()
    assert not path.with_name("out.csv.partial").exists()


def test_download_rejects_size_excess_without_final_or_partial_file(tmp_path, monkeypatch):
    response = Mock()
    response.url = "https://nwdp.nwic.gov.in/data.csv"
    response.headers = {}
    response.iter_content.side_effect = lambda **_: iter([b"abcdefg"])
    client = Mock()
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=None)
    client.get.return_value = context
    monkeypatch.setattr(manual.time, "sleep", lambda _: None)
    path = tmp_path / "out.csv"
    with pytest.raises(ValueError, match="size limit"):
        manual._download(response.url, path, session=client, max_bytes=6)
    assert not path.exists()
    assert not path.with_name("out.csv.partial").exists()


def test_telemetry_acquisition_reuses_only_hash_verified_inputs_without_network(tmp_path):
    path = tmp_path / "telemetry.csv"
    path.write_bytes(b"raw source")
    manifest = {"resources": [{"downloaded": True, "path": str(path), "sha256": manual.sha256(path)}]}
    (tmp_path / "telemetry_acquisition.json").write_text(json.dumps(manifest))
    assert manual.acquire_telemetry_review(tmp_path) == manifest
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash changed"):
        manual.acquire_telemetry_review(tmp_path)


def test_previously_acquired_file_tampering_fails_offline(tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes(b"changed")
    (tmp_path / "manual_acquisition.json").write_text(json.dumps({"resources": [{"downloaded": True, "path": str(source), "sha256": "0" * 64}]}))
    with pytest.raises(ValueError, match="hash changed"):
        manual.acquire_recent(tmp_path)


@pytest.mark.parametrize("url", ["http://nwdp.nwic.gov.in/data.csv", "https://example.org/data.csv",
                                 "https://" + "synthetic-user:synthetic-password" + "@nwdp.nwic.gov.in/data.csv"])
def test_download_rejects_other_hosts_plain_http_and_credential_urls(tmp_path, url):
    with pytest.raises(ValueError, match="public HTTPS NWDP"):
        manual._download(url, tmp_path / "out.csv")


def test_partial_failure_leaves_no_final_source_and_optional_offline_plan_uses_no_network(tmp_path, monkeypatch):
    client = Mock()
    client.get.side_effect = RuntimeError("offline")
    monkeypatch.setattr(manual.time, "sleep", lambda _: None)
    path = tmp_path / "out.csv"
    with pytest.raises(RuntimeError):
        manual._download("https://nwdp.nwic.gov.in/data.csv", path, session=client)
    assert not path.exists()
    assert not path.with_name("out.csv.partial").exists()
    assert client.get.call_count == 3
    assert manual.main([]) == 0
