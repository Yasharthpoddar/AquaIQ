"""Checkpoint commits survive brief Windows locks and fail without data loss."""
import errno
import json
import os
from pathlib import Path

import pytest

from data_ingestion import imd_realtime as imd


@pytest.fixture
def checkpoint(tmp_path):
    path = tmp_path / "progress.json"
    path.write_bytes(b'{"status":"previous","complete":true}\n')
    return path


def windows_permission_error(code):
    error = PermissionError(errno.EACCES, "checkpoint replacement blocked")
    error.winerror = code
    return error


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_transient_windows_denial_retries_the_same_complete_file(checkpoint, monkeypatch, winerror):
    previous = checkpoint.read_bytes()
    payload = {"status": "next", "completed": ["2026-01-01"]}
    replace = Path.replace
    attempts, waits = [], []

    def briefly_blocked(source, target):
        assert target == checkpoint
        assert checkpoint.read_bytes() == previous
        assert json.loads(source.read_text(encoding="utf-8")) == payload
        attempts.append(source)
        if len(attempts) <= 2:
            raise windows_permission_error(winerror)
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", briefly_blocked)
    monkeypatch.setattr(imd.time, "sleep", waits.append)
    imd._atomic_json(checkpoint, payload)
    assert json.loads(checkpoint.read_text()) == payload
    assert len(attempts) == 3 and len(set(attempts)) == 1
    assert waits == [0.01, 0.02]
    assert not list(checkpoint.parent.glob("*.partial"))


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_persistent_windows_denial_is_bounded_and_keeps_previous_checkpoint(checkpoint, monkeypatch, winerror):
    previous = checkpoint.read_bytes()
    failure = windows_permission_error(winerror)
    attempts, waits = [], []

    def blocked(source, target):
        assert target == checkpoint and checkpoint.read_bytes() == previous
        attempts.append(source)
        raise failure

    monkeypatch.setattr(Path, "replace", blocked)
    monkeypatch.setattr(imd.time, "sleep", waits.append)
    with pytest.raises(PermissionError) as caught:
        imd._atomic_json(checkpoint, {"status": "next"})
    assert caught.value is failure
    assert len(attempts) == 5 and len(set(attempts)) == 1
    assert waits == [0.01, 0.02, 0.04, 0.08]
    assert sum(waits) == pytest.approx(0.15)
    assert checkpoint.read_bytes() == previous
    assert not list(checkpoint.parent.glob("*.partial"))


@pytest.mark.parametrize("failure", [
    PermissionError(errno.EACCES, "ordinary permission denial"),
    windows_permission_error(87),
    OSError(errno.ENOSPC, "disk full"),
])
def test_other_replace_errors_fail_immediately_without_losing_checkpoint(checkpoint, monkeypatch, failure):
    previous = checkpoint.read_bytes()
    attempts, waits = [], []

    def fail(source, target):
        attempts.append(source)
        raise failure

    monkeypatch.setattr(Path, "replace", fail)
    monkeypatch.setattr(imd.time, "sleep", waits.append)
    with pytest.raises(type(failure)) as caught:
        imd._atomic_json(checkpoint, {"status": "next"})
    assert caught.value is failure
    assert len(attempts) == 1 and waits == []
    assert checkpoint.read_bytes() == previous
    assert not list(checkpoint.parent.glob("*.partial"))


@pytest.mark.parametrize("payload,error", [({"value": float("nan")}, ValueError), ({"value": object()}, TypeError)])
def test_invalid_json_never_reaches_checkpoint_commit(checkpoint, monkeypatch, payload, error):
    previous = checkpoint.read_bytes()

    def forbidden(*args):
        pytest.fail("Invalid serialization must fail before replacement or retry")

    monkeypatch.setattr(Path, "replace", forbidden)
    monkeypatch.setattr(imd.time, "sleep", forbidden)
    with pytest.raises(error):
        imd._atomic_json(checkpoint, payload)
    assert checkpoint.read_bytes() == previous
    assert not list(checkpoint.parent.glob("*.partial"))


def test_fsync_failure_never_reaches_checkpoint_commit(checkpoint, monkeypatch):
    previous = checkpoint.read_bytes()

    def full_disk(*args):
        raise OSError(errno.ENOSPC, "fsync failed")

    def forbidden(*args):
        pytest.fail("An unsynced checkpoint must not be committed or retried")

    monkeypatch.setattr(imd.os, "fsync", full_disk)
    monkeypatch.setattr(Path, "replace", forbidden)
    monkeypatch.setattr(imd.time, "sleep", forbidden)
    with pytest.raises(OSError, match="fsync failed"):
        imd._atomic_json(checkpoint, {"status": "next"})
    assert checkpoint.read_bytes() == previous
    assert not list(checkpoint.parent.glob("*.partial"))


def test_successful_checkpoint_does_not_wait(checkpoint, monkeypatch):
    def forbidden(*args):
        pytest.fail("A successful atomic replacement must not wait")

    monkeypatch.setattr(imd.time, "sleep", forbidden)
    imd._atomic_json(checkpoint, {"status": "next"})
    assert json.loads(checkpoint.read_text()) == {"status": "next"}
    assert not list(checkpoint.parent.glob("*.partial"))


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows file-sharing semantics")
@pytest.mark.parametrize("release_during_retry", [True, False])
def test_native_reader_without_delete_sharing(checkpoint, monkeypatch, release_during_retry):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # Open the old report for reading, sharing read/write but denying DELETE.
    # Windows uses delete access for replacement; this is a real OS lock.
    handle = kernel.CreateFileW(str(checkpoint), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    previous = checkpoint.read_bytes()
    replace = Path.replace
    denials, waits = [], []

    def release():
        nonlocal handle
        if handle is not None:
            if not kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())
            handle = None

    def native_replace(source, target):
        try:
            return replace(source, target)
        except PermissionError as error:
            denials.append(error.winerror)
            raise

    def after_denial(delay):
        assert checkpoint.read_bytes() == previous
        waits.append(delay)
        if release_during_retry:
            release()

    monkeypatch.setattr(Path, "replace", native_replace)
    monkeypatch.setattr(imd.time, "sleep", after_denial)
    try:
        if release_during_retry:
            imd._atomic_json(checkpoint, {"status": "next"})
            assert json.loads(checkpoint.read_text()) == {"status": "next"}
            assert 1 <= len(denials) <= 4
        else:
            with pytest.raises(PermissionError):
                imd._atomic_json(checkpoint, {"status": "next"})
            assert checkpoint.read_bytes() == previous
            assert len(denials) == 5 and len(waits) == 4
        assert denials and set(denials) <= {5, 32, 33}
        assert not list(checkpoint.parent.glob("*.partial"))
    finally:
        release()
