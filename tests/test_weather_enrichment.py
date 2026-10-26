"""Immutable official weather acquisition and split CDS archive regressions."""
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from data_ingestion import era5_to_district as era5
from data_ingestion import weather_enrichment as weather


def _fields():
    dims = ("valid_time", "latitude", "longitude")
    coords = {"valid_time": pd.date_range("2024-01-01", periods=2, freq="MS"),
              "latitude": [19.25, 19.0], "longitude": [72.75, 73.0]}
    temperature = xr.Dataset({"t2m": (dims, np.full((2, 2, 2), 300, dtype="float32"))}, coords=coords)
    temperature.t2m.attrs["units"] = "K"
    evaporation = xr.Dataset({"pev": (dims, np.full((2, 2, 2), -.002, dtype="float32"))}, coords=coords)
    evaporation.pev.attrs.update(units="m", GRIB_stepType="avgad", GRIB_stream="moda")
    return temperature, evaporation


def _archive(tmp_path, *fields, names=None):
    payload = tmp_path / "download.nc"
    with zipfile.ZipFile(payload, "w") as archive:
        for index, dataset in enumerate(fields):
            source = tmp_path / f"member-{index}.nc"
            dataset.to_netcdf(source, engine="netcdf4")
            archive.writestr(names[index] if names else f"field-{index}.nc", source.read_bytes())
    return payload


def test_split_archive_merges_both_fields_without_touching_raw(tmp_path):
    fields = _fields()
    source = _archive(tmp_path, *fields)
    digest = weather.sha256(source)
    before = sorted(p.name for p in tmp_path.iterdir())
    output = tmp_path / "derived" / "clean.nc"
    assert era5.prepare_era5_nc(source, output) == str(output.resolve())
    assert weather.sha256(source) == digest
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(before + ["derived"])
    with xr.open_dataset(output, engine="netcdf4") as result:
        np.testing.assert_array_equal(result.t2m, fields[0].t2m)
        np.testing.assert_array_equal(result.pev, fields[1].pev)
        np.testing.assert_array_equal(result.t2m_celsius, fields[0].t2m - np.float32(273.15))
        assert result.pev.attrs["GRIB_stepType"] == "avgad"
        assert result.t2m.attrs["units"] == "K"
        assert result.t2m_celsius.attrs["units"] == "degC"
    manifest = json.loads(output.with_suffix(".prepare.json").read_text())
    assert manifest["source_sha256"] == digest
    assert manifest["months"] == 2
    assert manifest["raw_source_modified"] is False
    assert manifest["csv_or_netcdf_sha256"] == weather.sha256(output)


@pytest.mark.parametrize("problem", ["path", "windows_path", "duplicate_variable", "coordinates", "units", "missing_field", "size"])
def test_split_archive_fails_closed(tmp_path, problem):
    temperature, evaporation = _fields()
    options = {}
    if problem == "path":
        options["names"] = ["../outside.nc", "evaporation.nc"]
    elif problem == "windows_path":
        options["names"] = ["..\\outside.nc", "evaporation.nc"]
    elif problem == "duplicate_variable":
        evaporation["t2m"] = temperature.t2m
    elif problem == "coordinates":
        evaporation = evaporation.assign_coords(longitude=[72.8, 73.0])
    elif problem == "units":
        evaporation.pev.attrs = {"units": "mm"}
    elif problem == "missing_field":
        evaporation = evaporation.drop_vars("pev")
    source = _archive(tmp_path, temperature, evaporation, **options)
    output = tmp_path / "clean.nc"
    kwargs = {"max_uncompressed_bytes": 1} if problem == "size" else {}
    with pytest.raises(ValueError):
        era5.prepare_era5_nc(source, output, **kwargs)
    assert not output.exists()
    assert not output.with_suffix(".prepare.json").exists()
    assert not (tmp_path.parent / "outside.nc").exists()


def test_prepare_never_overwrites_existing_file(tmp_path):
    source = _archive(tmp_path, *_fields())
    output = tmp_path / "preserve.nc"
    output.write_bytes(b"unrelated user file")
    with pytest.raises(FileExistsError):
        era5.prepare_era5_nc(source, output)
    assert output.read_bytes() == b"unrelated user file"


def test_prepare_publication_cannot_clobber_racing_user_file(tmp_path, monkeypatch):
    source = _archive(tmp_path, *_fields())
    output = tmp_path / "racing.nc"
    original = era5.publish_new_file

    def race(source, target):
        if target == output:
            output.write_bytes(b"concurrent user file")
        return original(source, target)

    monkeypatch.setattr(era5, "publish_new_file", race)
    with pytest.raises(FileExistsError):
        era5.prepare_era5_nc(source, output)
    assert output.read_bytes() == b"concurrent user file"
    assert not output.with_suffix(".prepare.json").exists()


def test_known_cds_monthly_evaporation_six_hour_label_is_same_month(tmp_path):
    temperature, evaporation = _fields()
    evaporation = evaporation.assign_coords(valid_time=evaporation.valid_time + np.timedelta64(6, "h"))
    source = _archive(tmp_path, temperature, evaporation)
    output = tmp_path / "clean.nc"
    era5.prepare_era5_nc(source, output)
    with xr.open_dataset(output) as result:
        np.testing.assert_array_equal(result.valid_time, temperature.valid_time)
        np.testing.assert_array_equal(result.pev.values, evaporation.pev.values)
    provenance = json.loads(output.with_suffix(".prepare.json").read_text())
    assert provenance["monthly_timestamp_mappings"][1]["source_hour_utc"] == 6


@pytest.mark.parametrize("shift", [np.timedelta64(1, "D"), np.timedelta64(3, "h"), np.timedelta64(1, "M")])
def test_unknown_monthly_time_label_is_not_silently_aligned(tmp_path, shift):
    temperature, evaporation = _fields()
    if shift.dtype.name.endswith("[M]"):
        evaporation = evaporation.assign_coords(valid_time=pd.date_range("2024-02-01", periods=2, freq="MS"))
    else:
        evaporation = evaporation.assign_coords(valid_time=evaporation.valid_time + shift)
    source = _archive(tmp_path, temperature, evaporation)
    with pytest.raises(ValueError):
        era5.prepare_era5_nc(source, tmp_path / "clean.nc")


def test_no_first_member_fallback_or_invalid_clean_overwrite(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    source = _archive(raw, *_fields())
    # Fixture constituent files are not raw downloads in this test.
    for member in raw.glob("member-*.nc"):
        member.unlink()
    clean = tmp_path / "clean.nc"
    monkeypatch.setattr(era5, "ERA5_DIR", raw)
    monkeypatch.setattr(era5, "CLEAN_NC_PATH", clean)
    assert era5.find_or_extract_nc() == str(clean.resolve())
    with xr.open_dataset(clean) as dataset:
        assert {"t2m", "pev"}.issubset(dataset.data_vars)
    assert source.exists()
    clean.write_bytes(b"invalid cache must survive")
    with pytest.raises((OSError, ValueError)):
        era5.find_or_extract_nc()
    assert clean.read_bytes() == b"invalid cache must survive"


class _Response:
    status_code = 200

    def __init__(self, payload, content_type="application/octet-stream"):
        self.payload = payload
        self.headers = {"Content-Type": content_type}
        self.url = weather.PRODUCTS["temperature_max"]["url"]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.payload


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def post(self, url, **kwargs):
        self.calls += 1
        assert kwargs["timeout"] == (15, 30)
        assert kwargs["allow_redirects"] is False
        return self.response


def test_temperature_acquisition_verifies_pair_and_rejects_tampering(tmp_path, monkeypatch):
    monkeypatch.setattr(weather, "ROOT", tmp_path)
    output = tmp_path / "data/raw/official_enrichment/test"
    values = np.full((365, 31, 31), 32, dtype="<f4")
    values[:, 0, 0] = np.float32(99.9)
    client = _Session(_Response(values.tobytes()))
    result = weather.download_product("temperature_max", 2025, output, session=client)
    assert result["valid_grid_day_values"] == 365 * (31 * 31 - 1)
    assert result["sha256"] == hashlib.sha256(values.tobytes()).hexdigest()
    assert result["candidate_only"] is True
    assert weather.download_product("temperature_max", 2025, output, session=client)["already_present"]
    assert client.calls == 1
    (output / "imd_temperature_max_2025.grd").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed provenance"):
        weather.download_product("temperature_max", 2025, output, session=client)


@pytest.mark.parametrize("payload,content_type", [(b"<html>Error</html>", "text/html"), (b"truncated", "application/octet-stream")])
def test_malformed_download_publishes_no_source(tmp_path, monkeypatch, payload, content_type):
    monkeypatch.setattr(weather, "ROOT", tmp_path)
    output = tmp_path / "data/raw/official_enrichment/test"
    with pytest.raises(ValueError):
        weather.download_product("temperature_max", 2025, output, session=_Session(_Response(payload, content_type)))
    assert not list(output.glob("*.grd"))
    assert not list(output.glob("*.partial"))


@pytest.mark.parametrize("kind", ["infinite", "implausible", "missing_day"])
def test_temperature_screening(tmp_path, kind):
    values = np.full((365, 31, 31), 30, dtype="<f4")
    values[0, 0, 0] = np.inf if kind == "infinite" else 80
    if kind == "missing_day":
        values[0] = np.float32(99.9)
    source = tmp_path / "temperature.grd"
    source.write_bytes(values.tobytes())
    with pytest.raises(ValueError):
        weather.validate_product(source, "temperature_max", 2025)


def test_product_and_year_guards_do_not_download(tmp_path):
    client = _Session(_Response(b""))
    for product, year in [("unknown", 2025), ("temperature_max", 2026), ("temperature_max", True), ("temperature_max", 1940)]:
        with pytest.raises(ValueError):
            weather.download_product(product, year, tmp_path, session=client, as_of=pd.Timestamp("2026-10-26").date())
    assert client.calls == 0


@pytest.mark.parametrize("problem", [None, "units", "date", "variable", "values"])
def test_rainfall_schema_calendar_units_and_screening(tmp_path, problem):
    values = np.ones((365, 129, 135), dtype=np.float32)
    values[:, 0, 0] = np.nan
    if problem == "values":
        values[0, 1, 1] = -2
    times = pd.date_range("2025-01-01", periods=365)
    if problem == "date":
        times = times + pd.Timedelta(days=1)
    variable = "unverified_rain" if problem == "variable" else "RAINFALL"
    dataset = xr.Dataset({variable: (("TIME", "LATITUDE", "LONGITUDE"), values)},
                         coords={"TIME": times, "LATITUDE": np.arange(129) * .25 + 6.5,
                                 "LONGITUDE": np.arange(135) * .25 + 66.5})
    dataset[variable].attrs["units"] = "inches" if problem == "units" else "MM"
    source = tmp_path / "rainfall.nc"
    dataset.to_netcdf(source, encoding={variable: {"zlib": True}}, engine="netcdf4")
    if problem:
        with pytest.raises(ValueError):
            weather.validate_product(source, "rainfall_netcdf", 2025)
    else:
        result = weather.validate_product(source, "rainfall_netcdf", 2025)
        assert result["valid_grid_day_values"] == 365 * (129 * 135 - 1)
        assert result["last_observation_date"] == "2025-12-31"
        binary = tmp_path / "rainfall.grd"
        np.nan_to_num(values, nan=-999).astype("<f4").tofile(binary)
        comparison = weather.compare_rainfall_netcdf_binary(source, binary, 2025)
        assert comparison["same_product_observations"]
        assert comparison["new_valid_grid_day_values"] == 0
