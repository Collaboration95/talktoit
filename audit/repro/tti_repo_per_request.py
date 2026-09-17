"""Repro: routes that ignore app.api.deps re-migrate the store per request.

app/api/deps.py exists so handlers share the lifespan-owned repositories and
"never open a migration connection again" (app/state/app_state.py:137-139).
app/api/status.py, saved_views.py, conversations.py and diagnostics.py instead
call AppStateRepository()/DiagnosticsRepository() inside every handler, so each
request builds a new instance with a fresh _migrated flag and runs migrate().

The script runs the real lifespan (one migration at startup) through
TestClient, then counts migrate() calls for two requests to each route.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "backend")

tmp = Path(tempfile.mkdtemp())
os.environ["TTI_APP_STATE_PATH"] = str(tmp / "app_state.sqlite")
os.environ.setdefault("TTI_DB_PATH", str(tmp / "health.duckdb"))
os.environ["TTI_LOCAL_AUTOSTART"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

import app.state.app_state as app_state_module  # noqa: E402
import app.state.diagnostics as diagnostics_module  # noqa: E402
from app.main import app  # noqa: E402

counts = {"app_state": 0, "diagnostics": 0}

_app_state_migrate = app_state_module.AppStateRepository.migrate
_diagnostics_migrate = diagnostics_module.DiagnosticsRepository.migrate


def _count_app_state(self):  # type: ignore[no-untyped-def]
    counts["app_state"] += 1
    return _app_state_migrate(self)


def _count_diagnostics(self):  # type: ignore[no-untyped-def]
    counts["diagnostics"] += 1
    return _diagnostics_migrate(self)


app_state_module.AppStateRepository.migrate = _count_app_state
diagnostics_module.DiagnosticsRepository.migrate = _count_diagnostics

ROUTES = (
    "/api/status",
    "/api/saved-views",
    "/api/conversations",
    "/api/diagnostics",
)

with TestClient(app) as client:
    at_startup = dict(counts)
    counts["app_state"] = 0
    counts["diagnostics"] = 0
    for route in ROUTES:
        for _ in range(2):
            response = client.get(route)
            assert response.status_code == 200, (route, response.status_code)
    after = dict(counts)

print(f"startup lifespan migrations: {at_startup}")
print(f"migrate() calls for 2x each of {ROUTES}: {after}")
