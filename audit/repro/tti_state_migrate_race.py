"""Repro: AppStateRepository instances each migrate the same SQLite file.

Every call to AppStateRepository() builds a fresh instance with a fresh
self._migrate_lock, so the "migrate at most once" guard does not serialize
across instances. The route modules that ignore app.api.deps construct a
repository per request, so two concurrent first requests race the
CREATE TABLE conversations statements in AppStateRepository.migrate (which are
not IF NOT EXISTS).

Part 1 runs concurrent first-use migrations and reports whether the race
raised "table conversations already exists".
Part 2 makes the failing path deterministic by resetting user_version to 1 on a
database whose tables already exist.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, "backend")

from app.state.app_state import AppStateRepository  # noqa: E402


def attempt_race(rounds: int = 60) -> str:
    failures: list[str] = []
    for _ in range(rounds):
        path = Path(tempfile.mkdtemp()) / "app_state.sqlite"
        barrier = threading.Barrier(4)
        errors: list[BaseException] = []

        def worker() -> None:
            repo = AppStateRepository(path=path)
            barrier.wait()
            try:
                repo.schema_version()
            except BaseException as exc:  # noqa: BLE001 - repro reports everything
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if errors:
            failures.append(f"{type(errors[0]).__name__}: {errors[0]}")
            break
    return failures[0] if failures else "no failure observed"


def deterministic_failure() -> str:
    path = Path(tempfile.mkdtemp()) / "app_state.sqlite"
    AppStateRepository(path=path).migrate()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    try:
        AppStateRepository(path=path).migrate()
    except sqlite3.OperationalError as exc:
        return f"OperationalError: {exc}"
    return "no failure observed"


if __name__ == "__main__":
    print("concurrent 4-instance first-use race:", attempt_race())
    print("migrate() re-run with user_version reset to 1:", deterministic_failure())
