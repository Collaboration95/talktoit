"""Repro: an unknown GET /api/... path returns the SPA index with status 200.

app/main.py mounts the SPA catch-all after the API routers, guarded only by
"frontend/dist exists at import time". With a build present (this working
tree has one), FastAPI falls through to `@app.get("/{full_path:path}")` for
any unmatched path, so a typo or a removed API route answers 200 text/html
instead of a JSON 404.

Run from the repository root:

    ./backend/.venv/bin/python audit/repro/tti_spa_404.py
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

from app.main import app  # noqa: E402

with TestClient(app) as client:
    response = client.get("/api/definitely-not-a-route")
    print(
        "GET /api/definitely-not-a-route ->",
        response.status_code,
        response.headers.get("content-type"),
    )
    print("body starts with:", response.text[:40].replace(chr(10), " "))
