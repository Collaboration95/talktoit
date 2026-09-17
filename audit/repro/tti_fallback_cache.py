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
from app.llm.orchestrator import _make_fallback_response  # noqa: E402
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
conv = repo.create_conversation("audit", ds.id)

# Turn 1: the provider is down, so the request degrades to a fallback envelope.
question = "What is my VO2 max trend over the last month?"
req = ChatRequest(conversation_id=conv, question=question)
prep = _prepare_chat(req, conn, repo)
print("pass 1 cache_hit=", prep.cache_hit, "prepared_response=", prep.response)
fallback = _make_fallback_response(question)
_finalize_chat(prep, req, fallback, 0.0)

# Turn 2: the provider is healthy again and would answer for real.
prep2 = _prepare_chat(ChatRequest(conversation_id=conv, question=question), conn, repo)
print(
    "pass 2 cache_hit=",
    prep2.cache_hit,
    "template=",
    prep2.response.template_id if prep2.response else None,
    "provenance=",
    prep2.response.metadata.provenance if prep2.response else None,
    "narrative=",
    prep2.response.narrative if prep2.response else None,
)
