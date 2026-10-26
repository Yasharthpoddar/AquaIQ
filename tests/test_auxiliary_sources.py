"""Auxiliary acquisition fails closed without network, DB, or model mutation."""
from copy import deepcopy
from io import BytesIO
import json

import pytest

from data_ingestion import auxiliary_sources as auxiliary


class Response(BytesIO):
    status = 200
    url = "https://official.example.org/resource"

    def __init__(self, content, headers=None):
        super().__init__(content)
        self.headers = headers or {}


def test_checked_pdf_checksum_mismatch_does_not_create_file(tmp_path):
    result = auxiliary.acquire("cgwb_gwra_2025_blocks", tmp_path,
                               opener=lambda *a, **k: Response(b"%PDF-1.7\nchanged"))
    assert result["status"] == {"discovered": True, "accessible": True, "downloaded": False,
                                "parsed": False, "integrated": False, "validated": False}
    assert "checksum" in result["attempts"][-1]["message"]
    assert not list(tmp_path.iterdir())


def test_existing_destination_never_overwritten(tmp_path):
    destination = tmp_path / "soilgrids_point_rural.json"
    destination.write_text("keep")
    with pytest.raises(FileExistsError):
        auxiliary.acquire("soilgrids_point_rural", tmp_path)
    assert destination.read_text() == "keep"


def test_malformed_pdf_or_vrt_or_geojson_rejected():
    for content, file_format in [(b"<html>error</html>", "pdf"),
                                 (b"<VRTDataset/>", "vrt"), (b"{}", "geojson")]:
        with pytest.raises(ValueError):
            auxiliary.validate_content(content, file_format)


def soil_value(value=196):
    return {"type": "Feature", "geometry": {"coordinates": [77.5, 28.5]},
            "properties": {"layers": [{"name": "clay", "unit_measure": {"mapped_units": "g/kg"},
            "depths": [{"label": "0-5cm", "values": {"mean": value}}]}]}}


def test_soil_sample_units_nulls_and_zero_are_not_groundwater(tmp_path):
    for value, expected in [(196, 19.6), (0, 0), (None, None)]:
        payload = json.dumps(soil_value(value)).encode()
        result = auxiliary.validate_content(payload, "json")
        assert result["clay_percent"] == expected
        assert result["groundwater_observations"] == 0
    result = auxiliary.acquire("soilgrids_point_rural", tmp_path,
                               opener=lambda *a, **k: Response(json.dumps(soil_value()).encode()))
    assert result["status"]["validated"]
    assert not result["status"]["integrated"]


@pytest.mark.parametrize("change", ["coordinates", "units", "variable", "depth", "negative"])
def test_soil_schema_drift_fails(change):
    data = soil_value()
    layer = data["properties"]["layers"][0]
    if change == "coordinates": data["geometry"]["coordinates"] = [77.2, 28.6]
    if change == "units": layer["unit_measure"]["mapped_units"] = "%"
    if change == "variable": layer["name"] = "sand"
    if change == "depth": layer["depths"][0]["label"] = "5-15cm"
    if change == "negative": layer["depths"][0]["values"]["mean"] = -1
    with pytest.raises(ValueError):
        auxiliary.validate_content(json.dumps(data).encode(), "json")


def test_oversized_source_rejected_before_read(tmp_path):
    result = auxiliary.acquire("soilgrids_point_rural", tmp_path,
                               opener=lambda *a, **k: Response(b"", {"Content-Length": str(auxiliary.MAX_BYTES + 1)}))
    assert "size budget" in result["attempts"][-1]["message"]
    assert not list(tmp_path.iterdir())


def test_http_timeout_recorded_and_head_is_not_downloaded(tmp_path):
    def timeout(*args, **kwargs): raise TimeoutError("unavailable")
    result = auxiliary.acquire("soilgrids_point_rural", tmp_path, opener=timeout, retries=0)
    assert not result["status"]["accessible"]
    result = auxiliary.acquire("grace_gsfc_availability", tmp_path,
                               opener=lambda *a, **k: Response(b"", {"Content-Length": "530877840"}))
    assert result["status"]["accessible"]
    assert not result["status"]["downloaded"]


def table():
    return [["GWRA - 2025", None, None, None, None],
            ["S. No.", "State", "District", "Assessment Unit Name", "Categorization"],
            ["1", "State", "District", "Unit", "safe"]]


def test_contextual_categories_cannot_become_depth_or_current_risk_tiers():
    result = auxiliary.validate_gwra_tables([table()])
    assert result[0]["category"] == "safe"
    assert "gwl" not in result[0]
    capitalized = deepcopy(table())
    capitalized[2][-1] = "Safe"
    assert auxiliary.validate_gwra_tables([capitalized])[0]["raw_category"] == "Safe"
    for update in [lambda t: t[0].__setitem__(0, "GWRA - 2024"),
                   lambda t: t[2].__setitem__(0, "2"),
                   lambda t: t[2].__setitem__(4, "Crisis"),
                   lambda t: t[2].__setitem__(2, "")]:
        data = deepcopy(table())
        update(data)
        with pytest.raises(ValueError):
            auxiliary.validate_gwra_tables([data])


def test_offline_plan_makes_no_directory_or_download(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(auxiliary, "urlopen", lambda *a, **k: pytest.fail("unexpected network"))
    assert auxiliary.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "offline_plan"
    with pytest.raises(ValueError):
        auxiliary.main(["--download", "--output-dir", str(tmp_path)])
