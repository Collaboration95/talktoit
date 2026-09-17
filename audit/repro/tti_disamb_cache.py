"""Repro: a context-dependent disambiguation prompt is cached and replayed."""

import os
import sys
import tempfile
from pathlib import Path

tmp = tempfile.mkdtemp()
os.environ["TTI_APP_STATE_PATH"] = str(Path(tmp) / "state.sqlite")
sys.path.insert(0, "backend")

import duckdb  # noqa: E402

from app.api.chat import _finalize_chat, _prepare_chat  # noqa: E402
from app.db.schema import SQL_CREATE_TABLES  # noqa: E402
from app.models.chat import ChatRequest  # noqa: E402
from app.state.app_state import AppStateRepository  # noqa: E402

conn = duckdb.connect(":memory:")
conn.execute(SQL_CREATE_TABLES)

repo = AppStateRepository()
repo.migrate()
ds = repo.activate(
    source_bytes=b"fixture",
    source_size_bytes=7,
    parser_version="v2",
    schema_version="1",
    worker_count=1,
    coverage_start=None,
    coverage_end=None,
    counts={},
)

# Conversation A holds TWO historical results -> ambiguous follow-up.
conv_a = repo.create_conversation("audit A", ds.id)
plan_one = {"tool_name": "get_last_workout", "arguments": {"activity_type": "Running"}}
plan_two = {"tool_name": "get_top_workouts", "arguments": {"n": 5}}
repo.add_completed_turn(
    conv_a, "my last run", "{}", "default", "cached", canonical_plan=plan_one
)
repo.add_completed_turn(
    conv_a, "top 5 runs", "{}", "default", "cached", canonical_plan=plan_two
)

question = "show me that one again"
req = ChatRequest(conversation_id=conv_a, question=question)
prep = _prepare_chat(req, conn, repo, None)
print("conv A disambiguated =", prep.disambiguated)
print("conv A response      =", prep.response.narrative if prep.response else None)
_finalize_chat(prep, req, prep.response, 0.0)

# Conversation B has NO prior results: the same words must not be ambiguous.
conv_b = repo.create_conversation("audit B", ds.id)
prep2 = _prepare_chat(
    ChatRequest(conversation_id=conv_b, question=question), conn, repo, None
)
print("conv B cache_hit     =", prep2.cache_hit)
print("conv B response      =", prep2.response.narrative if prep2.response else None)
print(
    "conv B provenance    =",
    prep2.response.metadata.provenance if prep2.response else None,
)
