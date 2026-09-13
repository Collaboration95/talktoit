"""CLI import activation safety: lock, staging cleanup, and rollback."""

from __future__ import annotations

import errno
import sys
import types
from pathlib import Path

import pytest

from app.ingest import run
from app.ingest.compatibility import V2CompatibilityError
from app.state.app_state import AppStateRepository

VALID_EXPORT = (
    "<HealthData>"
    '<Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" '
    'startDate="2024-01-01 00:00:00 +0000" endDate="2024-01-01 00:01:00 +0000" '
    'value="42"/>'
    "</HealthData>"
)


def _prepare_import(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Write a valid export and point the CLI at temporary DB/state paths."""
    export = tmp_path / "export.xml"
    export.write_text(VALID_EXPORT)
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setattr(sys, "argv", ["ingest", str(export)])
    return export


def test_failed_manifest_activation_restores_previous_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A manifest failure rolls the database back instead of leaving a mismatch."""
    _prepare_import(monkeypatch, tmp_path)
    target = tmp_path / "health.duckdb"
    target.write_bytes(b"previous-active-database")

    def fail_activation(self: AppStateRepository, source: Path, **manifest: object) -> None:
        raise RuntimeError("manifest write failed")

    monkeypatch.setattr(AppStateRepository, "activate_file", fail_activation)

    with pytest.raises(RuntimeError, match="manifest write failed"):
        run.main()

    assert target.read_bytes() == b"previous-active-database"
    # Neither the staged database nor the rollback copy may be left behind.
    assert not list(tmp_path.glob("tti-import-*.duckdb"))
    assert not list(tmp_path.glob("*.previous"))


def test_parse_failure_leaves_no_staging_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A parser error cleans the staged database and preserves the active one."""
    export = tmp_path / "truncated.xml"
    export.write_text('<HealthData><Record type="HKQuantityTypeIdentifierStepCount"')
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setattr(sys, "argv", ["ingest", str(export)])
    target = tmp_path / "health.duckdb"
    target.write_bytes(b"previous-active-database")

    with pytest.raises(V2CompatibilityError):
        run.main()

    assert target.read_bytes() == b"previous-active-database"
    assert not list(tmp_path.glob("tti-import-*.duckdb"))


def test_unexpected_lock_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A platform where flock exists but fails must abort, not import unlocked."""
    _prepare_import(monkeypatch, tmp_path)

    def unsupported_flock(*args: object) -> None:
        raise OSError(errno.ENOTSUP, "flock unsupported")

    fake_fcntl = types.SimpleNamespace(flock=unsupported_flock, LOCK_EX=2, LOCK_UN=8)
    monkeypatch.setattr(run, "_load_fcntl", lambda: fake_fcntl)

    with pytest.raises(OSError, match="flock unsupported"):
        run.main()

    assert not (tmp_path / "health.duckdb").exists()
    assert not list(tmp_path.glob("tti-import-*.duckdb"))
