"""Offline checks for resumable IMD downloads and failed-source isolation."""
from datetime import date
import hashlib
import json

import numpy as np
import pytest
import requests

from data_ingestion import imd_realtime as imd


AS_OF = date(2026, 10, 14)
DAY = date(2026, 1, 1)


def rainfall_bytes(value=1.5):
    return np.full((imd.NY, imd.NX), value, dtype="<f4").tobytes()


class Response:
    def __init__(self, day=DAY, *, body=None, status=200, url=imd.DOWNLOAD_URL,
                 content_type="application/octet-stream", filename=None,
                 chunks=None):
        self.body = rainfall_bytes() if body is None else body
        self.status_code = status
        self.url = url
        self.headers = {
            "Content-Type": content_type,
            "Content-Disposition": "attachment; filename=" + (
                filename or day.strftime("rain_ind0.25_%y_%m_%d.grd")),
            "Content-Length": str(len(self.body)),
        }
        self.chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size=65536):
        if self.chunks is not None:
            yield from self.chunks
            return
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset:offset + chunk_size]

    def close(self):
        self.closed = True


class Session:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls = []
        self.closed = False

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.outcomes:
            result = self.outcomes.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        encoded = kwargs["data"]["rain"]
        day = date(int(encoded[4:]), int(encoded[2:4]), int(encoded[:2]))
        return Response(day)

    def close(self):
        self.closed = True


def staged_paths(directory, day=DAY):
    stem = "rain_" + day.strftime("%d%m%Y")
    return directory / (stem + ".bin"), directory / (stem + ".download.json")


def stage(directory, day=DAY, value=1.5):
    directory.mkdir(parents=True, exist_ok=True)
    binary, sidecar = staged_paths(directory, day)
    body = rainfall_bytes(value)
    binary.write_bytes(body)
    sidecar.write_text(json.dumps({
        "url": imd.DOWNLOAD_URL,
        "form": {"rain": day.strftime("%d%m%Y")},
        "content_type": "application/octet-stream",
        "content_disposition": "attachment; filename=" + day.strftime(
            "rain_ind0.25_%y_%m_%d.grd"),
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }), encoding="utf-8")
    return binary, sidecar


def fetch(directory, session, **kwargs):
    return imd.download_daily(directory, DAY, session=session, attempts=2,
                              backoff_seconds=0, sleeper=lambda _: None,
                              as_of=AS_OF, **kwargs)


def test_download_uses_exact_source_date_and_preserves_auditable_bytes(tmp_path):
    response = Response()
    session = Session([response])
    result = fetch(tmp_path, session)
    binary, sidecar = staged_paths(tmp_path)
    assert result["status"] == "downloaded"
    assert result["date"] == DAY.isoformat()
    assert result["attempts"] == 1
    assert result["size_bytes"] == imd.DAY_BYTES
    assert result["sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
    assert sidecar.is_file()
    assert np.all(imd.read_staged_daily(tmp_path, DAY, AS_OF) == 1.5)
    assert session.calls == [{
        "url": imd.DOWNLOAD_URL, "data": {"rain": "01012026"},
        "stream": True, "timeout": (10, 20), "allow_redirects": False,
    }]
    assert response.closed
    assert not session.closed
    assert len(list(tmp_path.iterdir())) == 2


def test_valid_cached_pair_is_verified_and_reused_without_http(tmp_path):
    binary, sidecar = stage(tmp_path)
    previous = {binary.name: binary.read_bytes(), sidecar.name: sidecar.read_bytes()}
    session = Session()
    result = fetch(tmp_path, session)
    assert result["status"] == "already_present"
    assert result["attempts"] == 0
    assert session.calls == []
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == previous


@pytest.mark.parametrize("option", ["max_consecutive_failures", "max_failures"])
@pytest.mark.parametrize("invalid", [None, 0, -1, True, 1.5])
def test_failure_limits_must_be_positive_integers_before_staging(tmp_path, option, invalid):
    directory = tmp_path / "new-staging"
    client = Session()
    with pytest.raises(ValueError, match=option):
        imd.download_range("2026-01", "2026-01", directory, session=client,
                           as_of=AS_OF, **{option: invalid})
    assert not directory.exists()
    assert not client.calls


def test_selected_probe_dates_do_not_download_unrelated_calendar_days(tmp_path):
    client = Session()
    dates = ["2025-09-30", "2025-01-01", "2025-06-15"]
    report = imd.download_dates(dates, tmp_path, session=client, as_of=AS_OF,
                                attempts=1, sleeper=lambda _: None)
    assert report["status"] == "complete"
    assert report["selection"] == "explicit_days"
    assert report["planned_days"] == report["days_complete"] == 3
    assert [call["data"]["rain"] for call in client.calls] == ["01012025", "15062025", "30092025"]


@pytest.mark.parametrize("dates", [[], ["2025-1-01"], ["20250101"],
                                  ["2025-01-01", "2025-01-01"], ["2026-10-14"]])
def test_invalid_selected_probe_dates_fail_before_network_or_writes(tmp_path, dates):
    directory = tmp_path / "new-staging"
    client = Session()
    with pytest.raises(ValueError):
        imd.download_dates(dates, directory, session=client, as_of=AS_OF)
    assert not directory.exists()
    assert not client.calls


def test_selected_dates_cli_is_offline_until_download_is_explicit(tmp_path, capsys):
    assert imd.main(["--dates", "2025-01-01", "2025-06-15", "2025-09-30",
                     "--staged-dir", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["days"] == 3 and report["network_requests_made"] == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("flags", [[], ["--start", "2026-01"],
                                   ["--dates", "2025-01-01", "--start", "2025-01", "--end", "2025-01"],
                                   ["--dates", "2025-01-01", "--validate-staged"]])
def test_cli_rejects_ambiguous_or_incomplete_date_selection(flags):
    with pytest.raises(SystemExit) as error:
        imd.main(flags)
    assert error.value.code == 2


def test_corrupt_cache_is_replaced_only_after_validated_download(tmp_path):
    binary, sidecar = stage(tmp_path)
    binary.write_bytes(b"old damaged data")
    rejected = Response(filename="rain_ind0.25_26_01_02.grd")
    accepted = Response(body=rainfall_bytes(3.0))
    result = fetch(tmp_path, Session([rejected, accepted]))
    assert result["status"] == "downloaded"
    assert result["attempts"] == 2
    assert np.all(imd.read_staged_daily(tmp_path, DAY, AS_OF) == 3.0)
    assert rejected.closed and accepted.closed
    assert len(list(tmp_path.iterdir())) == 2


def test_failed_replacement_keeps_original_pair_and_cleans_temporary_files(tmp_path):
    binary, sidecar = stage(tmp_path)
    binary.write_bytes(b"old damaged data")
    previous = {binary.name: binary.read_bytes(), sidecar.name: sidecar.read_bytes()}
    session = Session([Response(body=b"short"), Response(body=b"short")])
    with pytest.raises(Exception):
        fetch(tmp_path, session)
    assert len(session.calls) == 2
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == previous


@pytest.mark.parametrize("response", [
    Response(status=302),
    Response(status=500),
    Response(url="https://example.invalid/rain.php"),
    Response(filename="rain_ind0.25_26_01_02.grd"),
    Response(body=b"<html>Try again</html>", content_type="text/html"),
    Response(body=b"short"),
    Response(body=rainfall_bytes() + b"extra"),
    Response(body=rainfall_bytes(-1.0)),
    Response(body=rainfall_bytes(-999.0)),
    Response(body=rainfall_bytes(np.nan)),
])
def test_invalid_response_is_never_left_as_a_staged_record(tmp_path, response):
    session = Session([response])
    with pytest.raises(Exception):
        imd.download_daily(tmp_path, DAY, session=session, attempts=1,
                           backoff_seconds=0, sleeper=lambda _: None, as_of=AS_OF)
    assert len(session.calls) == 1
    assert response.closed
    assert not list(tmp_path.iterdir())


def test_timeout_retries_are_bounded_and_backoff_does_not_follow_success(tmp_path):
    sleeps = []
    session = Session([requests.Timeout("temporary timeout"), Response()])
    result = imd.download_daily(tmp_path, DAY, session=session, attempts=3,
                                backoff_seconds=0.25, sleeper=sleeps.append,
                                as_of=AS_OF)
    assert result["attempts"] == 2
    assert len(session.calls) == 2
    assert len(sleeps) == 1
    assert sleeps[0] >= 0.25


def test_interrupted_stream_is_cleaned_before_retry(tmp_path):
    class InterruptedResponse(Response):
        def iter_content(self, chunk_size=65536):
            yield self.body[:100]
            raise requests.ConnectionError("connection dropped midway")

    interrupted = InterruptedResponse()
    accepted = Response()
    result = fetch(tmp_path, Session([interrupted, accepted]))
    assert result["attempts"] == 2
    assert interrupted.closed and accepted.closed
    assert np.all(imd.read_staged_daily(tmp_path, DAY, AS_OF) == 1.5)
    assert len(list(tmp_path.iterdir())) == 2


def test_oversized_stream_stops_reading_at_bound(tmp_path):
    class ExcessResponse(Response):
        def iter_content(self, chunk_size=65536):
            yield rainfall_bytes() + b"extra"
            pytest.fail("Downloader continued reading after the daily size bound")

    response = ExcessResponse()
    with pytest.raises(Exception):
        imd.download_daily(tmp_path, DAY, session=Session([response]), attempts=1,
                           as_of=AS_OF)
    assert response.closed
    assert not list(tmp_path.iterdir())


def test_owned_session_closes_after_success(tmp_path, monkeypatch):
    session = Session()
    monkeypatch.setattr(requests, "Session", lambda: session)
    imd.download_daily(tmp_path, DAY, attempts=1, as_of=AS_OF)
    assert session.closed


def test_owned_session_closes_after_failure(tmp_path, monkeypatch):
    session = Session([requests.Timeout("timed out")])
    monkeypatch.setattr(requests, "Session", lambda: session)
    with pytest.raises(Exception):
        imd.download_daily(tmp_path, DAY, attempts=1, as_of=AS_OF)
    assert session.closed


def test_current_or_future_day_is_rejected_before_http(tmp_path):
    session = Session()
    for day in [AS_OF, date(2026, 11, 1)]:
        with pytest.raises(ValueError):
            imd.download_daily(tmp_path, day, session=session, as_of=AS_OF)
    assert session.calls == []
    assert not list(tmp_path.iterdir())


def test_range_budget_saves_progress_and_resume_requests_only_missing_days(tmp_path):
    session = Session()
    updates = []
    first = imd.download_range("2026-01", "2026-01", tmp_path,
                               session=session, attempts=1, max_days=2,
                               backoff_seconds=0, sleeper=lambda _: None,
                               as_of=AS_OF, progress=updates.append)
    assert first["status"] == "incomplete"
    assert first["days_complete"] == 2
    assert first["counts"] == {
        "downloaded": 2, "already_present": 0, "failed": 0, "pending": 29,
    }
    assert len(session.calls) == 2
    assert updates
    saved = json.loads((tmp_path / "download_progress.json").read_text())
    assert saved["days_complete"] == first["days_complete"]
    assert saved["status"] == first["status"]

    second_session = Session()
    second = imd.download_range("2026-01", "2026-01", tmp_path,
                                session=second_session, attempts=1,
                                backoff_seconds=0, sleeper=lambda _: None,
                                as_of=AS_OF)
    assert second["status"] == "complete"
    assert second["days_complete"] == 31
    assert second["counts"] == {
        "downloaded": 29, "already_present": 2, "failed": 0, "pending": 0,
    }
    assert len(second_session.calls) == 29
    assert {call["data"]["rain"] for call in second_session.calls}.isdisjoint(
        {"01012026", "02012026"})
    total, sources = imd.complete_month_grid(tmp_path, 2026, 1, AS_OF)
    assert len(sources) == 31
    assert np.all(total == 46.5)
    assert not session.closed and not second_session.closed


def test_range_stops_after_consecutive_failures_without_filling_gaps(tmp_path):
    session = Session([requests.Timeout("offline"), requests.Timeout("offline")])
    report = imd.download_range("2026-01", "2026-01", tmp_path,
                                session=session, attempts=1,
                                max_consecutive_failures=2, max_failures=10,
                                backoff_seconds=0, sleeper=lambda _: None,
                                as_of=AS_OF)
    assert report["status"] == "incomplete"
    assert report["days_complete"] == 0
    assert report["counts"]["failed"] == 2
    assert report["counts"]["pending"] == 29
    assert len(session.calls) == 2
    assert list(tmp_path.glob("*.bin")) == []
    saved = json.loads((tmp_path / "download_progress.json").read_text())
    assert saved["counts"] == report["counts"]


def test_range_owns_one_session_and_closes_it(tmp_path, monkeypatch):
    session = Session()
    created = []

    def create_session():
        created.append(session)
        return session

    monkeypatch.setattr(requests, "Session", create_session)
    report = imd.download_range("2026-01", "2026-01", tmp_path,
                                attempts=1, max_days=2, as_of=AS_OF)
    assert report["days_complete"] == 2
    assert created == [session]
    assert session.closed


def test_range_inventory_includes_valid_cache_after_network_budget(tmp_path):
    stage(tmp_path, date(2026, 1, 31))
    session = Session()
    report = imd.download_range("2026-01", "2026-01", tmp_path,
                                session=session, attempts=1, max_days=1,
                                as_of=AS_OF)
    assert report["days_complete"] == 2
    assert report["counts"]["already_present"] == 1
    assert len(session.calls) == 1
    assert {item["date"] for item in report["completed"]} == {
        "2026-01-01", "2026-01-31",
    }


def test_range_total_failure_cutoff_survives_intervening_success(tmp_path):
    session = Session([
        requests.Timeout("offline"), Response(date(2026, 1, 2)),
        requests.Timeout("offline"),
    ])
    report = imd.download_range("2026-01", "2026-01", tmp_path,
                                session=session, attempts=1,
                                max_consecutive_failures=2, max_failures=2,
                                backoff_seconds=0, sleeper=lambda _: None,
                                as_of=AS_OF)
    assert report["status"] == "incomplete"
    assert report["days_complete"] == 1
    assert report["counts"]["failed"] == 2
    assert report["counts"]["pending"] == 28
    assert len(session.calls) == 3
    with pytest.raises(ValueError, match="Incomplete calendar month"):
        imd.complete_month_grid(tmp_path, 2026, 1, AS_OF)


def test_default_cli_never_constructs_a_network_client(tmp_path, monkeypatch, capsys):
    def unexpected_network():
        pytest.fail("Default CLI must stay offline")

    monkeypatch.setattr(requests, "Session", unexpected_network)
    imd.main(["--start", "2026-01", "--end", "2026-09", "--staged-dir", str(tmp_path)])
    report = json.loads(capsys.readouterr().out)
    assert report["network_requests_made"] == 0
    assert report["production_changes_made"] is False
    assert not list(tmp_path.iterdir())


def test_cli_download_requires_explicit_staging_directory():
    with pytest.raises(SystemExit) as error:
        imd.main(["--start", "2026-01", "--end", "2026-01", "--download"])
    assert error.value.code == 2


def test_cli_explicit_download_exposes_incomplete_exit_status(tmp_path, monkeypatch, capsys):
    calls = []

    def staged_download(start, end, directory, **kwargs):
        calls.append((start, end, directory, kwargs))
        return {"status": "incomplete", "days_complete": 0, "planned_days": 31,
                "counts": {"downloaded": 0, "already_present": 0,
                           "failed": 1, "pending": 30}}

    monkeypatch.setattr(imd, "download_range", staged_download)
    code = imd.main(["--start", "2026-01", "--end", "2026-01", "--download",
                     "--staged-dir", str(tmp_path), "--max-days", "1"])
    assert code == 1
    assert len(calls) == 1
    assert calls[0][:3] == ("2026-01", "2026-01", tmp_path)
    assert calls[0][3]["max_days"] == 1
    assert json.loads(capsys.readouterr().out)["status"] == "incomplete"
