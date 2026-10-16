import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "data_ingestion/cgwb_historical_january.py"
spec = importlib.util.spec_from_file_location("cgwb_historical_january_under_test", MODULE)
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


def words(date="10-01-25"):
    result = [{"text": word, "x0": 275 + index * 10, "top": 20.1} for index, word in enumerate(archive.TITLE.split())]
    result += [{"text": word, "x0": x, "top": 31.1} for word, x in zip(archive.HEADERS, archive.HEADER_X)]
    cells = ["Gujarat", "Gandhinagar", "Kalol", "Village", "23.23", "72.63", date, "12.3"]
    result += [{"text": word, "x0": x + (10 if index == 7 else 0), "top": 42.1} for index, (word, x) in enumerate(zip(cells, archive.HEADER_X))]
    return result


def parse(items):
    return archive.parse_archive_page(items, 1, page_width=841.92004, page_height=595.32001)


def test_verified_title_layout_preserves_actual_dates_and_metadata():
    row = parse(words())[0]
    assert row["reported_date"] == "10-01-2025"
    assert row["raw_reported_date"] == "10-01-25"
    assert row["source_month"] == "2025-01"
    assert row["units"] == "m_bgl"
    assert row["source_dataset_aquifer"] == "Unconfined"
    assert row["source_dataset_aquifer_basis"] == "dataset_title_not_well_log"
    assert "aquifer" not in row
    assert row["gwl_m_bgl"] == "12.3"
    assert "station_id" not in row


@pytest.mark.parametrize("date", ["10-01-24", "10-02-25", "32-01-25", "10-01-2025"])
def test_unknown_year_month_or_date_is_not_inferred(date):
    with pytest.raises(ValueError, match="source date"):
        parse(words(date))


def test_unknown_units_title_header_or_dimensions_fail():
    bad = words()
    bad[7]["text"] = "feet)"
    with pytest.raises(ValueError, match="title"):
        parse(bad)
    bad = words()
    bad[len(archive.TITLE.split()) + 1]["x0"] += 3
    with pytest.raises(ValueError, match="header positions"):
        parse(bad)
    with pytest.raises(ValueError, match="dimensions"):
        archive.parse_archive_page(words(), 1, page_width=792, page_height=612)


def test_default_cli_is_offline_and_existing_outputs_protected(tmp_path, monkeypatch, capsys):
    assert archive.main([]) == 0
    assert "offline_plan" in capsys.readouterr().out
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="explicit new"):
        archive.main(["--pdf", "unused.pdf"])
    output = tmp_path / "reports/candidates/existing"
    output.mkdir(parents=True)
    with pytest.raises(ValueError, match="must be new"):
        archive.main(["--pdf", "unused.pdf", "--output-dir", str(output)])
