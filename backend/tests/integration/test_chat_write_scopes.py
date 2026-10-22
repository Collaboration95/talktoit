"""Pending turns commit before preparation; slow work never owns a writer."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import duckdb
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.api import chat as chat_module
from app.db.schema import SQL_CREATE_TABLES
from app.ingest.coordinator import ingest_v2
from app.llm.provider_gateway import ProviderGateway, ProviderUnavailableError
from app.main import create_app
from app.state.app_state import AppStateRepository
from tests.dataset_support import fixture_connection
from tests.integration.test_chat_cache_revalidation import FIXTURE, _activate


@pytest.fixture
def chat_store(monkeypatch, tmp_path):
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    repo = AppStateRepository()
    dataset_id = _activate(repo, records=100, coverage_end="2026-06-30")
    db = duckdb.connect(":memory:")
    db.execute(SQL_CREATE_TABLES)
    ingest_v2(str(FIXTURE), db)
    app = create_app()
    app.dependency_overrides[chat_module._get_conn] = lambda: (yield from fixture_connection(db))
    client = MagicMock()
    client.complete = AsyncMock(side_effect=AssertionError("provider calls are denied"))
    app.dependency_overrides[chat_module._get_gateway] = lambda: ProviderGateway(
        client, mode="local_only"
    )
    yield app, repo, dataset_id
    app.dependency_overrides.clear()
    db.close()


@pytest.mark.parametrize("phase", ["get_data_profile", "plan_local_question", "evaluate"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_pending_visible_and_writer_completes_before_preparation_release(
    chat_store, monkeypatch, phase, cancel
):
    app, repo, dataset_id = chat_store
    conversation_id = repo.create_conversation("Original", dataset_id)
    entered, release = threading.Event(), threading.Event()
    target = chat_module
    real = getattr(target, phase)

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10), "preparation barrier was never released"
        return real(*args, **kwargs)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        if phase == "evaluate":
            # A completed trusted intent is needed to exercise candidate evaluation.
            monkeypatch.setattr(chat_module, "candidates_enabled", lambda: True)
            first = await client.post(
                "/api/chat",
                json={"question": "Show my last run", "conversation_id": conversation_id},
            )
            assert first.status_code == 200
            with repo.session() as store:
                store.execute("DELETE FROM cache_entries")
        monkeypatch.setattr(target, phase, blocked)
        task = asyncio.create_task(
            client.post(
                "/api/chat",
                json={"question": "Show my last run", "conversation_id": conversation_id},
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            turns = repo.get_turns(conversation_id)
            assert turns and turns[-1]["state"] == "pending"
            pending_id = turns[-1]["id"]
            # Real separate SQLite connection and real write, with no latency SLA.
            writer = asyncio.create_task(
                asyncio.to_thread(repo.create_conversation, "Unrelated", dataset_id)
            )
            unrelated_id = await asyncio.wait_for(asyncio.shield(writer), 3)
            assert repo.get_conversation(unrelated_id) is not None
            assert not release.is_set()
            if cancel:
                task.cancel()
        finally:
            release.set()
            if cancel and task.cancelling():
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                response = await asyncio.wait_for(task, 10)
        turns = repo.get_turns(conversation_id)
        assert turns[-1]["id"] == pending_id
        assert turns[-1]["state"] == ("cancelled" if cancel else "completed")
        assert sum(t["id"] == pending_id for t in turns) == 1
        assert repo.terminate_turn(pending_id, state="failed", message="late") is False
        if not cancel:
            assert response.status_code == 200
            assert response.json()["metadata"]["dataset_version_id"] == dataset_id
            assert response.json()["metadata"]["turn_id"] == pending_id


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (RuntimeError("private internals"), 500, "internal_failure"),
        (TimeoutError("private internals"), 504, "request_timeout"),
        (duckdb.OperationalError("private internals"), 503, "data_unavailable"),
        (ProviderUnavailableError("private internals"), 503, "provider_unavailable"),
        (HTTPException(status_code=409, detail="Start a new conversation."), 409, None),
    ],
)
async def test_preparation_failure_terminates_committed_turn(
    chat_store, monkeypatch, failure, status, code
):
    app, repo, dataset_id = chat_store
    conversation_id = repo.create_conversation("Failure", dataset_id)

    def fail(_conn):
        raise failure

    monkeypatch.setattr(chat_module, "get_data_profile", fail)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/chat", json={"question": "Show my last run", "conversation_id": conversation_id}
        )
    assert response.status_code == status
    if code:
        assert response.json()["detail"]["code"] == code
    assert "private internals" not in response.text
    turns = repo.get_turns(conversation_id)
    assert len(turns) == 1
    assert turns[0]["state"] == "failed"
    assert repo.terminate_turn(str(turns[0]["id"]), state="cancelled", message="late") is False


async def test_exact_conversation_hit_bypasses_profile_and_finishes_new_turn(
    chat_store, monkeypatch
):
    app, repo, dataset_id = chat_store
    conversation_id = repo.create_conversation("Cached", dataset_id)
    payload = {"question": "Show my last run", "conversation_id": conversation_id}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/api/chat", json=payload)
        assert first.status_code == 200

        def denied(_conn):
            pytest.fail("exact cache must bypass profiling")

        monkeypatch.setattr(chat_module, "get_data_profile", denied)
        second = await client.post("/api/chat", json=payload)
    assert second.status_code == 200
    assert second.json()["metadata"]["provenance"] == "cached"
    assert second.json()["data"] == first.json()["data"]
    turns = repo.get_turns(conversation_id)
    assert [t["state"] for t in turns] == ["completed", "completed"]
    assert [t["ordinal"] for t in turns] == [1, 2]
    assert len({t["id"] for t in turns}) == 2


async def test_rejected_exact_hit_commits_cache_bookkeeping_before_profile(chat_store, monkeypatch):
    app, repo, dataset_id = chat_store
    conversation_id = repo.create_conversation("Rejected cache", dataset_id)
    payload = {"question": "Show my last run", "conversation_id": conversation_id}
    entered, release = threading.Event(), threading.Event()
    real_profile = chat_module.get_data_profile

    def blocked(conn):
        entered.set()
        assert release.wait(10)
        return real_profile(conn)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/chat", json=payload)).status_code == 200
        with repo.session() as store:
            store.execute("UPDATE cache_entries SET response_json = 'invalid envelope'")
        monkeypatch.setattr(chat_module, "get_data_profile", blocked)
        task = asyncio.create_task(client.post("/api/chat", json=payload))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            writer = asyncio.create_task(
                asyncio.to_thread(repo.create_conversation, "Unrelated", dataset_id)
            )
            await asyncio.wait_for(asyncio.shield(writer), 3)
            assert not release.is_set()
        finally:
            release.set()
            response = await task
            await writer
    assert response.status_code == 200
    assert [t["state"] for t in repo.get_turns(conversation_id)] == ["completed", "completed"]


async def test_cancel_before_handle_publication_terminates_after_commit(chat_store, monkeypatch):
    app, repo, dataset_id = chat_store
    conversation_id = repo.create_conversation("Commit race", dataset_id)
    entered, release = threading.Event(), threading.Event()
    real_create = AppStateRepository.create_pending_turn

    def blocked(self, *args, **kwargs):
        turn_id = real_create(self, *args, **kwargs)
        entered.set()
        assert release.wait(10)
        return turn_id

    monkeypatch.setattr(AppStateRepository, "create_pending_turn", blocked)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        task = asyncio.create_task(
            client.post(
                "/api/chat",
                json={"question": "Show my last run", "conversation_id": conversation_id},
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            task.cancel()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
    turns = repo.get_turns(conversation_id)
    assert len(turns) == 1
    assert turns[0]["state"] == "cancelled"


async def test_cancelled_preparation_failure_uses_published_handle(chat_store, monkeypatch):
    app, repo, dataset_id = chat_store
    conversation_id = repo.create_conversation("Cancel and fail", dataset_id)
    entered, release = threading.Event(), threading.Event()

    def fail(_conn):
        entered.set()
        assert release.wait(10)
        raise RuntimeError("private failure after cancellation")

    monkeypatch.setattr(chat_module, "get_data_profile", fail)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        task = asyncio.create_task(
            client.post(
                "/api/chat",
                json={"question": "Show my last run", "conversation_id": conversation_id},
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            assert repo.get_turns(conversation_id)[0]["state"] == "pending"
            task.cancel()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
    turns = repo.get_turns(conversation_id)
    assert len(turns) == 1
    assert turns[0]["state"] == "cancelled"


async def test_distinct_fresh_questions_keep_per_request_profiles(chat_store, monkeypatch):
    app, repo, dataset_id = chat_store
    conversation_id = repo.create_conversation("No profile cache", dataset_id)
    real_profile = chat_module.get_data_profile
    profiles = []

    def counted(conn):
        result = real_profile(conn)
        profiles.append(result)
        return result

    monkeypatch.setattr(chat_module, "get_data_profile", counted)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for question in ("Show my last run", "Show my last walk"):
            response = await client.post(
                "/api/chat",
                json={
                    "question": question,
                    "conversation_id": conversation_id,
                    "cache_mode": "fresh",
                },
            )
            assert response.status_code == 200
    assert len(profiles) == 2
    assert profiles[0] is not profiles[1]
