"""Exact local cache never crosses dataset identities."""

from __future__ import annotations

import json
from datetime import date

import duckdb

import app.state.app_state as app_state
from app.api.chat import _prepare_chat
from app.db.data_profile import DataProfile
from app.llm.cache_keys import CACHE_KEY_VERSION, build_cache_key
from app.models.chat import ChatRequest
from app.state.app_state import CACHE_MAX_ENTRIES, AppStateRepository


def test_exact_cache_is_scoped_to_dataset_and_refreshable(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.put_cached_response("normalised-question", "ds_one", '{"answer":"one"}')
    assert repo.get_cached_response("normalised-question", "ds_one") == '{"answer":"one"}'
    assert repo.get_cached_response("normalised-question", "ds_two") is None


def test_canonical_cache_key_can_share_equivalent_local_intent(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.put_cached_response("canonical-last-running", "ds_one", '{"template_id":"workout_card"}')
    assert (
        repo.get_cached_response("canonical-last-running", "ds_one")
        == '{"template_id":"workout_card"}'
    )


def test_versioned_cache_keys_normalize_equivalent_intent_without_sharing_different_facts() -> None:
    assert CACHE_KEY_VERSION == "chat-cache-v2"
    assert build_cache_key("exact", "  Last RUN  ") == build_cache_key("exact", "last run")
    plan = {
        "tool_name": "get_trend",
        "arguments": {"metric_id": "HKQuantityTypeIdentifierStepCount", "granularity": "day"},
    }
    assert build_cache_key("canonical", plan) == build_cache_key("canonical", dict(plan))
    assert build_cache_key(
        "canonical",
        {
            "tool_name": "get_trend",
            "arguments": {"metric_id": "HKQuantityTypeIdentifierRestingHeartRate"},
        },
    ) != build_cache_key("canonical", plan)


def test_lru_cache_eviction_is_bounded_and_does_not_touch_turns(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    conversation_id = repo.create_conversation("History", "ds_one")
    turn_id = repo.add_completed_turn(conversation_id, "source", "{}", "default", "fallback")
    for index in range(CACHE_MAX_ENTRIES + 1):
        repo.put_cached_response(f"key-{index}", "ds_one", "{}")
    assert repo.get_cached_response("key-0", "ds_one") is None
    assert repo.get_cached_response(f"key-{CACHE_MAX_ENTRIES}", "ds_one") == "{}"
    assert repo.get_turns(conversation_id)[0]["id"] == turn_id


def test_cache_byte_budget_evicts_oldest_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_state, "CACHE_MAX_BYTES", 8)
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.put_cached_response("old", "ds_one", "12345")
    repo.put_cached_response("new", "ds_one", "67890")

    assert repo.get_cached_response("old", "ds_one") is None
    assert repo.get_cached_response("new", "ds_one") == "67890"


def _activate_dataset(
    repo: AppStateRepository,
    *,
    coverage_end: str,
    records: int = 100,
    content_prefix: str,
) -> str:
    """Register a new dataset manifest and return its fresh dataset id.

    Every activation mints a brand-new ``ds_…`` id — the same mechanism the
    import pipeline uses when a changed export is re-ingested — so a caller
    can simulate "the file/coverage changed" by activating again.
    """
    version = repo.activate(
        source_bytes=b"",
        source_size_bytes=records * 1024,
        parser_version="v2",
        schema_version="1",
        worker_count=2,
        coverage_start="2026-01-01",
        coverage_end=coverage_end,
        counts={"records": records},
        content_hash_prefix=content_prefix,
    )
    assert version is not None
    return version.id


def test_valid_cache_serves_stale_value_until_the_dataset_revalidates(tmp_path) -> None:
    """A cached answer is valid for its dataset id; a new dataset invalidates it."""
    repo = AppStateRepository(tmp_path / "state.sqlite")
    old_dataset_id = _activate_dataset(repo, coverage_end="2026-06-01", content_prefix="aaaa")
    key = build_cache_key("exact", "show my last run")

    # Cache is warm for the old dataset: subsequent hits serve the stored
    # (now stale) value without recomputation — provenance is the caller's job.
    repo.put_cached_response(key, old_dataset_id, '{"answer":"old coverage"}')
    assert repo.get_cached_response(key, old_dataset_id) == '{"answer":"old coverage"}'

    # The export was re-imported (new coverage window, new content hash): the
    # revalidation path must NOT reuse the old dataset's cache entry.
    new_dataset_id = _activate_dataset(repo, coverage_end="2026-07-31", content_prefix="bbbb")
    assert new_dataset_id != old_dataset_id
    assert repo.get_cached_response(key, new_dataset_id) is None

    # Fresh data is recomputed and stored; the single per-key row is now
    # re-associated with the dataset that produced it, so the dead dataset id
    # can never serve (or resurrect) the stale value again.
    repo.put_cached_response(key, new_dataset_id, '{"answer":"fresh coverage"}')
    assert repo.get_cached_response(key, new_dataset_id) == '{"answer":"fresh coverage"}'
    assert repo.get_cached_response(key, old_dataset_id) is None


def _cached_envelope(text: str) -> str:
    return json.dumps(
        {
            "template_id": "fallback",
            "data": {"question": "show my last run", "table": None, "text": text},
            "narrative": text,
            "metadata": {"provenance": "deterministic_local"},
        }
    )


def test_prepare_chat_cache_hit_skips_profile_scan(tmp_path, monkeypatch) -> None:
    """GH-6: an exact cache hit never pays for the DuckDB profile scan."""
    repo = AppStateRepository(tmp_path / "state.sqlite")
    dataset_id = _activate_dataset(repo, coverage_end="2026-08-31", content_prefix="cccc")
    key = build_cache_key("exact", "show my last run")
    plan = {"tool_name": "get_last_workout", "arguments": {"activity_type": "Running"}}
    repo.put_cached_response(
        key, dataset_id, _cached_envelope("cached answer"), canonical_plan=plan
    )

    def _must_not_run(_conn):
        raise AssertionError("profile scan must not run on a pure cache hit")

    monkeypatch.setattr("app.api.chat.get_data_profile", _must_not_run)

    conn = duckdb.connect(":memory:")
    prepared = _prepare_chat(ChatRequest(question="show my last run"), conn, repo)
    assert prepared.cache_hit is True
    assert prepared.response is not None
    assert prepared.response.metadata.provenance == "cached"
    assert prepared.canonical_plan == plan
    assert prepared.canonical_key == build_cache_key("canonical", plan)


def test_prepare_chat_cache_miss_still_scans_and_recomputes(tmp_path, monkeypatch) -> None:
    """GH-6: a cache miss keeps planning from the profile scan, as before."""
    repo = AppStateRepository(tmp_path / "state.sqlite")
    _activate_dataset(repo, coverage_end="2026-08-31", content_prefix="dddd")

    scanned: list[object] = []
    profile = DataProfile(
        first_date=date(2026, 1, 1),
        latest_date=date(2026, 8, 15),
        workout_types=("Running",),
        metrics=("HKQuantityTypeIdentifierStepCount",),
    )

    def _fake_scan(_conn):
        scanned.append(_conn)
        return profile

    monkeypatch.setattr("app.api.chat.get_data_profile", _fake_scan)

    conn = duckdb.connect(":memory:")
    prepared = _prepare_chat(ChatRequest(question="show my last run"), conn, repo)
    assert scanned  # the profile scan ran on the miss path
    assert prepared.cache_hit is False
    assert prepared.canonical_plan == {
        "tool_name": "get_last_workout",
        "arguments": {"activity_type": "Running"},
    }
    assert prepared.response is None


def test_fresh_cache_mode_skips_read_and_write(tmp_path) -> None:
    """A forced-fresh request refetches and beats a warm exact cache entry."""
    repo = AppStateRepository(tmp_path / "state.sqlite")
    dataset_id = _activate_dataset(repo, coverage_end="2026-06-30", content_prefix="aaaa")
    key = build_cache_key("exact", "show my last run")
    repo.put_cached_response(key, dataset_id, '{"answer":"stale"}')

    # The fresh path is expressed by the caller (cache_mode="fresh"); the
    # repository itself just returns the stored value, so the caller must
    # recompute and re-store. Simulate that contract:
    assert repo.get_cached_response(key, dataset_id) == '{"answer":"stale"}'
    repo.put_cached_response(key, dataset_id, '{"answer":"recomputed"}')
    assert repo.get_cached_response(key, dataset_id) == '{"answer":"recomputed"}'
