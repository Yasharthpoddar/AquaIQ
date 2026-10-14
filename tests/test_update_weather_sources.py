"""Weather staging must reject incomplete sources and future request months."""
from datetime import date
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest
import xarray as xr

from data_ingestion.update_weather_sources import (
    download_imd, era5_requests, expected_imd_bytes, main, validate_era5, validate_imd,
)


def test_era5_request_years_do_not_request_future_cartesian_months():
    requests = era5_requests("2025-01", "2026-09", date(2026, 10, 13))
    assert [request["year"] for request in requests] == [["2025"], ["2026"]]
    assert requests[0]["month"] == [f"{month:02d}" for month in range(1, 13)]
    assert requests[1]["month"] == [f"{month:02d}" for month in range(1, 10)]
    assert all(request["variable"] == ["2m_temperature", "potential_evaporation"] for request in requests)


@pytest.mark.parametrize("start,end", [("2026-10", "2026-10"), ("2026-01", "2027-01"),
                                       ("2026-09", "2025-01"), ("2025-1", "2025-12"),
                                       ("1939-12", "2025-01")])
def test_era5_request_rejects_incomplete_future_or_invalid_months(start, end):
    with pytest.raises(ValueError):
        era5_requests(start, end, date(2026, 10, 13))


def test_imd_annual_expected_bytes_handles_leap_year():
    assert expected_imd_bytes(2025) == 25425900
    assert expected_imd_bytes(2024) == 25495560


def test_imd_truncated_or_html_file_is_rejected(tmp_path):
    path = tmp_path / "wrong.grd"
    path.write_bytes(b"<html>temporarily unavailable</html>")
    with pytest.raises(ValueError, match="exactly"):
        validate_imd(path, 2025)


def test_imd_one_missing_day_is_rejected(tmp_path):
    path = tmp_path / "missing-day.grd"
    grid = np.memmap(path, dtype="<f4", mode="w+", shape=(365, 129, 135))
    grid[:] = 1.0
    grid[11] = -999.0
    grid.flush()
    del grid
    with pytest.raises(ValueError, match="missing calendar day"):
        validate_imd(path, 2025)


def _era5_fixture(path, *, include_pev=True, dates=None, pev_units="m"):
    times = np.asarray(dates or ["2025-01-01", "2025-02-01"], dtype="datetime64[ns]")
    fields = {"t2m": (("valid_time", "latitude", "longitude"), np.full((len(times), 2, 2), 300.0), {"units": "K"})}
    if include_pev:
        fields["pev"] = (("valid_time", "latitude", "longitude"), np.full((len(times), 2, 2), -0.003), {"units": pev_units, "GRIB_stepType": "avgad"})
    xr.Dataset(fields, coords={"valid_time": times, "latitude": [38.0, 6.0], "longitude": [68.0, 98.0]}).to_netcdf(path)


def test_era5_source_metadata_and_units_are_preserved(tmp_path):
    path = tmp_path / "weather.nc"
    _era5_fixture(path)
    request = era5_requests("2025-01", "2025-02", date(2026, 10, 13))[0]
    result = validate_era5(path, request)
    assert result["variables"]["t2m"]["units"] == "K"
    assert result["variables"]["pev"]["GRIB_stepType"] == "avgad"
    assert result["months"] == 2
    assert "days_in_month" in result["conversion_required"]["evapotranspiration"]


@pytest.mark.parametrize("kwargs,message", [({"include_pev": False}, "both 2m temperature"),
                                            ({"dates": ["2025-01-01"]}, "calendar coverage"),
                                            ({"pev_units": "mm/month"}, "Unexpected ERA5 pev units")])
def test_era5_rejects_missing_variables_dates_or_changed_units(tmp_path, kwargs, message):
    path = tmp_path / "bad.nc"
    _era5_fixture(path, **kwargs)
    request = era5_requests("2025-01", "2025-02", date(2026, 10, 13))[0]
    with pytest.raises(ValueError, match=message):
        validate_era5(path, request)


def test_dry_run_does_not_create_output_or_require_cdsapi(tmp_path, capsys):
    output = tmp_path / "never-created"
    main(["era5", "--start", "2025-01", "--end", "2025-12", "--out-dir", str(output), "--dry-run"])
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["requests"][0]["year"] == ["2025"]


def test_era5_zip_variable_split_does_not_extract_archive_paths(tmp_path):
    source = tmp_path / "source.nc"
    _era5_fixture(source)
    target = tmp_path / "response.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.write(source, "../../untrusted-member.nc")
    request = era5_requests("2025-01", "2025-02", date(2026, 10, 13))[0]
    assert validate_era5(target, request)["months"] == 2
    assert not (tmp_path.parent / "untrusted-member.nc").exists()


class _Response:
    headers = {"Content-Type": "application/octet-stream"}
    url = "https://imdpune.gov.in/cmpg/Griddata/rainfall.php"

    def __init__(self, blocks):
        self.blocks = blocks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield from self.blocks


class _Session:
    def __init__(self, response):
        self.response = response

    def post(self, *args, **kwargs):
        return self.response


def test_incomplete_download_never_becomes_an_annual_artifact(tmp_path):
    with pytest.raises(ValueError, match="exactly"):
        download_imd(2025, tmp_path, session=_Session(_Response([b"short download"])))
    assert not list(tmp_path.iterdir())


def test_oversize_response_is_bounded_and_removed(tmp_path, monkeypatch):
    monkeypatch.setattr("data_ingestion.update_weather_sources.expected_imd_bytes", lambda year: 8)
    with pytest.raises(ValueError, match="exceeds"):
        download_imd(2025, tmp_path, session=_Session(_Response([b"1234", b"12345"])))
    assert not list(tmp_path.iterdir())
