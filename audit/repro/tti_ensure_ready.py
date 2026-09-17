"""Repro: repository writers that skip _ensure_ready() crash on an un-migrated store."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "backend")

from app.state.app_state import AppStateRepository  # noqa: E402

tmp = Path(tempfile.mkdtemp())

# Control: a read accessor self-migrates on a never-migrated store.
repo = AppStateRepository(tmp / "fresh.sqlite")
try:
    repo.list_conversations()
    print("list_conversations: ok (self-migrated)")
except Exception as exc:
    print("list_conversations:", type(exc).__name__, exc)

# Suspect: the chat-path writers do not.
repo2 = AppStateRepository(tmp / "fresh2.sqlite")
try:
    repo2.finish_turn("tr_missing", response_json="{}", cache_outcome="fallback")
    print("finish_turn: ok")
except Exception as exc:
    print("finish_turn:", type(exc).__name__, exc)

repo3 = AppStateRepository(tmp / "fresh3.sqlite")
try:
    repo3.terminate_turn("tr_missing", state="failed", message="boom")
    print("terminate_turn: ok")
except Exception as exc:
    print("terminate_turn:", type(exc).__name__, exc)

repo4 = AppStateRepository(tmp / "fresh4.sqlite")
conv = repo4.create_conversation("t", "ds_one")
repo5 = AppStateRepository(tmp / "fresh5.sqlite")
print(
    "note: create_conversation on fresh5 self-migrated =",
    (tmp / "fresh5.sqlite").exists(),
)
