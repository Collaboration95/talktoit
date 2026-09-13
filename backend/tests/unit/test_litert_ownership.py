"""PID ownership: LiteRT only ever signals a process it actually started."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.llm import litert


def _spawn_sleeper(*extra: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", "import time; time.sleep(30)", *extra],
        start_new_session=True,
    )


def _require_process_table() -> None:
    """Skip when this environment cannot inspect the process table."""
    if litert._process_table_field(os.getpid(), "lstart") is None:
        pytest.skip("process table inspection is unavailable in this environment")


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    return tmp_path


def test_recycled_pid_is_rejected_and_not_signalled(
    monkeypatch: pytest.MonkeyPatch, state_dir: Path
) -> None:
    """A pid whose start time changed is never adopted or killed."""
    monkeypatch.setattr(litert, "resolve_litert_binary", lambda: "/usr/local/bin/litert-lm")
    proc = _spawn_sleeper()
    try:
        litert.pidfile_path().write_text(f"{proc.pid} Mon Jan  1 00:00:00 2001")

        assert litert.status()["running"] is False
        result = litert.stop()

        assert result["stopped"] is False
        assert result["reason"] == "pidfile is not owned by LiteRT"
        assert proc.poll() is None, "an unrelated process must never be signalled"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_process_that_merely_mentions_the_binary_is_not_owned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The command is matched on whole tokens, not as a substring."""
    _require_process_table()
    monkeypatch.setattr(litert, "resolve_litert_binary", lambda: "/usr/local/bin/litert-lm")
    proc = _spawn_sleeper(str(tmp_path / "litert-lm.log"))
    try:
        token = litert._process_table_field(proc.pid, "lstart")
        assert token is not None
        assert litert._owns_process(litert._OwnedProcess(proc.pid, token)) is False
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_matching_command_tokens_are_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process whose executable really is the configured binary is owned."""
    _require_process_table()
    monkeypatch.setattr(litert, "resolve_litert_binary", lambda: sys.executable)
    proc = _spawn_sleeper()
    try:
        token = litert._process_table_field(proc.pid, "lstart")
        assert token is not None
        assert litert._owns_process(litert._OwnedProcess(proc.pid, token)) is True
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_legacy_bare_pid_pidfile_is_still_read(state_dir: Path) -> None:
    """A pidfile written by an older version has no identity token."""
    litert.pidfile_path().write_text(str(os.getpid()))
    owned = litert._read_owned_process()
    assert owned is not None
    assert owned.pid == os.getpid()
    assert owned.start_token is None


def test_stop_reaps_the_child_it_spawned(monkeypatch: pytest.MonkeyPatch, state_dir: Path) -> None:
    """A killed owned child is reaped instead of lingering as a zombie."""
    _require_process_table()
    monkeypatch.setattr(litert, "resolve_litert_binary", lambda: sys.executable)
    proc = _spawn_sleeper()
    token = litert._process_table_field(proc.pid, "lstart")
    assert token is not None
    litert.pidfile_path().write_text(f"{proc.pid} {token}")
    litert._OWNED_CHILDREN[proc.pid] = proc
    try:
        result = litert.stop(timeout_seconds=2.0)
        assert result["stopped"] is True
        assert proc.returncode is not None
    finally:
        litert._OWNED_CHILDREN.pop(proc.pid, None)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_reap_process_terminates_and_reaps() -> None:
    """The spawn-failure cleanup path leaves no live child behind."""
    proc = _spawn_sleeper()
    litert._reap_process(proc)
    assert proc.returncode is not None
