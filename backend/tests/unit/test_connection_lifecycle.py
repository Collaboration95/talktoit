"""Connection lifecycle: leased connections survive replacement and deletion."""

from __future__ import annotations

from pathlib import Path

from app.db.connection import close_open_connections, connect, lease_connection


def test_leased_connection_is_not_closed_by_a_lifecycle_swap(tmp_path: Path) -> None:
    """A request holding a connection keeps working across an import swap."""
    target = tmp_path / "health.duckdb"
    conn = connect(target)
    try:
        with lease_connection(conn):
            assert close_open_connections(target) == 0
            assert conn.execute("SELECT 1").fetchone() == (1,)
        # Released: the next swap closes it so the following request re-opens.
        assert close_open_connections(target) == 1
    finally:
        conn.close()


def test_idle_connections_are_closed_for_the_target_only(tmp_path: Path) -> None:
    """Closing one database does not touch idle connections to another."""
    first = connect(tmp_path / "first.duckdb")
    second = connect(tmp_path / "second.duckdb")
    try:
        assert close_open_connections(tmp_path / "first.duckdb") == 1
        assert second.execute("SELECT 1").fetchone() == (1,)
    finally:
        first.close()
        second.close()
    assert close_open_connections(tmp_path / "second.duckdb") == 1
