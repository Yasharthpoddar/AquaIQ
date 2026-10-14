from datetime import date
import hashlib
import json

import numpy as np
import pytest

from data_ingestion.imd_realtime import (
    DOWNLOAD_URL, completed_month_dates, complete_month_grid, main,
    monthly_grid_points, read_daily,
)

AS_OF = date(2026, 10, 13)


def _day(tmp_path, day, grid=None):
    values = np.ones((129, 135), dtype="<f4") if grid is None else grid.astype("<f4")
    target = tmp_path / ("rain_" + day.strftime("%d%m%Y") + ".bin")
    values.tofile(target)
    metadata = {"url": DOWNLOAD_URL, "form": {"rain": day.strftime("%d%m%Y")},
                "content_type": "application/octet-stream", "size_bytes": target.stat().st_size,
                "content_disposition": "attachment; filename=" + day.strftime("rain_ind0.25_%y_%m_%d.grd"),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    target.with_suffix(".download.json").write_text(json.dumps(metadata))
    return target, metadata


def test_plan_has_all_273_days_and_only_completed_months():
    dates = completed_month_dates("2026-01", "2026-09", AS_OF)
    assert len(dates) == 273
    assert dates[0] == date(2026, 1, 1)
    assert dates[-1] == date(2026, 9, 30)
    assert date(2026, 2, 28) in dates


@pytest.mark.parametrize("start,end", [("2026-10", "2026-10"), ("2026-01", "2027-01"),
                                       ("2025-01", "2026-09"), ("2026-09", "2026-08"),
                                       ("2026-1", "2026-09")])
def test_plan_rejects_incomplete_future_unbounded_or_malformed_months(start, end):
    with pytest.raises(ValueError):
        completed_month_dates(start, end, AS_OF)


def test_source_date_and_checksum_are_required(tmp_path):
    path, metadata = _day(tmp_path, date(2026, 1, 1))
    for field, value in [("url", "https://example.invalid/rain.php"),
                         ("sha256", "changed"),
                         ("content_disposition", "attachment; filename=rain_ind0.25_26_01_02.grd")]:
        with pytest.raises(ValueError):
            read_daily(path, date(2026, 1, 1), {**metadata, field: value}, AS_OF)


@pytest.mark.parametrize("value", [np.nan, np.inf, -1.0, 10001.0])
def test_bad_daily_value_is_rejected(tmp_path, value):
    grid = np.ones((129, 135), dtype="<f4")
    grid[4, 5] = value
    path, metadata = _day(tmp_path, date(2026, 1, 1), grid)
    with pytest.raises(ValueError):
        read_daily(path, date(2026, 1, 1), metadata, AS_OF)


def test_one_missing_daily_record_never_becomes_zero_rain(tmp_path):
    for day in completed_month_dates("2026-02", "2026-02", AS_OF)[:-1]:
        _day(tmp_path, day)
    with pytest.raises(ValueError, match="2026-02-28"):
        complete_month_grid(tmp_path, 2026, 2, AS_OF)


def test_missing_cell_does_not_become_a_partial_month_sum(tmp_path):
    for day in completed_month_dates("2026-02", "2026-02", AS_OF):
        grid = np.ones((129, 135), dtype="<f4")
        if day.day == 15:
            grid[4, 5] = -999.0
        _day(tmp_path, day, grid)
    total, sources = complete_month_grid(tmp_path, 2026, 2, AS_OF)
    assert len(sources) == 28
    assert np.isnan(total[4, 5])
    assert total[4, 6] == 28.0
    points = monthly_grid_points(total, 2026, 2)
    assert len(points) == 129 * 135 - 1
    assert points.iloc[0]["latitude"] == 6.5
    assert points.iloc[1]["longitude"] == 66.75
    assert points.iloc[-1]["latitude"] == 38.5


def test_cli_default_is_an_offline_plan(tmp_path, capsys):
    main(["--start", "2026-01", "--end", "2026-09", "--staged-dir", str(tmp_path)])
    result = json.loads(capsys.readouterr().out)
    assert result["days"] == 273
    assert result["network_requests_made"] == 0
    assert result["production_changes_made"] is False
    assert not list(tmp_path.iterdir())
