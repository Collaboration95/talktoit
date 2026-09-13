"""Lifecycle tests for the local-first LLM defaults and LiteRT autostart.

Covers GH-44 (``local`` is the first-run provider default everywhere) and
GH-45/46 (bounded, never-fatal autostart helpers plus the lifespan hook).
Process-spawning paths are monkeypatched so these tests are hermetic on
machines with or without the ``litert-lm`` binary installed.
"""

from __future__ import annotations

import pytest

from app.llm import litert
from app.llm.provider_gateway import get_gateway_for_config, provider_from_env
from app.main import create_app
from app.state.app_state import AppStateRepository, _provider_defaults
from app.state.diagnostics import DiagnosticsRepository


def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove provider selection env so first-run defaults are exercised."""
    monkeypatch.delenv("TTI_PROVIDER", raising=False)
    monkeypatch.delenv("TTI_LLM_PROVIDER", raising=False)


def _autostart_events() -> list:
    """Return litert_autostart events from the default app-state store."""
    return [
        event
        for event in DiagnosticsRepository().recent(limit=100, category="app")
        if event.name == "litert_autostart"
    ]


async def _boot_lifespan(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Boot the real lifespan once against an isolated app-state store."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    app = create_app()
    async with app.router.lifespan_context(app):
        pass


# ---------------------------------------------------------------------------
# GH-44: local is the default provider
# ---------------------------------------------------------------------------


def test_provider_defaults_first_run_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """No env and no stored row means the LiteRT provider, model, and URL."""
    _clear_provider_env(monkeypatch)
    defaults = _provider_defaults()
    assert defaults["provider"] == "local"
    assert defaults["model"] == defaults["litert_model"] == "gemma4-e2b"
    assert defaults["base_url"] == defaults["litert_base_url"] == "http://127.0.0.1:9379/v1"


def test_provider_defaults_explicit_groq_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit opt-in to the hosted provider keeps working."""
    monkeypatch.setenv("TTI_PROVIDER", "groq")
    defaults = _provider_defaults()
    assert defaults["provider"] == "groq"
    assert defaults["model"] == defaults["groq_model"]
    assert defaults["base_url"] == defaults["groq_base_url"]


def test_provider_from_env_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset or invalid env selects local; only an explicit groq opts out."""
    _clear_provider_env(monkeypatch)
    assert provider_from_env() == "local"
    monkeypatch.setenv("TTI_PROVIDER", "groq")
    assert provider_from_env() == "groq"
    monkeypatch.setenv("TTI_PROVIDER", "bogus")
    assert provider_from_env() == "local"


def test_gateway_for_empty_config_defaults_to_local() -> None:
    """An empty config (and an invalid provider) resolves to the local gateway."""
    assert get_gateway_for_config({}).provider == "local"
    assert get_gateway_for_config({"provider": "bogus"}).provider == "local"


def test_persisted_provider_config_defaults_to_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A fresh store reports local; a stored groq choice is never rewritten."""
    _clear_provider_env(monkeypatch)
    repo = AppStateRepository(tmp_path / "state.sqlite")
    assert repo.get_provider_config()["provider"] == "local"
    repo.set_provider_config({"provider": "groq"})
    assert repo.get_provider_config()["provider"] == "groq"


# ---------------------------------------------------------------------------
# GH-45: autostart flag parsing
# ---------------------------------------------------------------------------


def test_autostart_enabled_defaults_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Autostart is on unless explicitly disabled."""
    monkeypatch.delenv("TTI_LOCAL_AUTOSTART", raising=False)
    assert litert.autostart_enabled() is True
    for raw in ("0", "false", "no", "off", "  OFF  "):
        monkeypatch.setenv("TTI_LOCAL_AUTOSTART", raw)
        assert litert.autostart_enabled() is False
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART", "1")
    assert litert.autostart_enabled() is True


def test_stop_on_exit_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend shutdown leaves the owned server warm unless opted in."""
    monkeypatch.delenv("TTI_LOCAL_STOP_ON_EXIT", raising=False)
    assert litert.stop_on_exit() is False
    monkeypatch.setenv("TTI_LOCAL_STOP_ON_EXIT", "1")
    assert litert.stop_on_exit() is True
    monkeypatch.setenv("TTI_LOCAL_STOP_ON_EXIT", "0")
    assert litert.stop_on_exit() is False


def test_autostart_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garbage, non-positive, and huge timeouts all fall back to safe values."""
    monkeypatch.delenv("TTI_LOCAL_AUTOSTART_TIMEOUT_SECONDS", raising=False)
    assert litert.autostart_timeout_seconds() == 3.0
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART_TIMEOUT_SECONDS", "bogus")
    assert litert.autostart_timeout_seconds() == 3.0
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART_TIMEOUT_SECONDS", "-5")
    assert litert.autostart_timeout_seconds() == 3.0
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART_TIMEOUT_SECONDS", "600")
    assert litert.autostart_timeout_seconds() == 30.0
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART_TIMEOUT_SECONDS", "1.5")
    assert litert.autostart_timeout_seconds() == 1.5


# ---------------------------------------------------------------------------
# GH-45: ensure_running never raises and never double-starts
# ---------------------------------------------------------------------------


def test_ensure_running_is_noop_when_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """A live server means no spawn attempt at all."""

    def fake_start(**_kwargs):
        raise AssertionError("must not spawn when already running")

    monkeypatch.setattr(litert, "status", lambda: {"running": True, "binary_available": True})
    monkeypatch.setattr(litert, "start", fake_start)
    result = litert.ensure_running()
    assert result["already_running"] is True
    assert result["started"] is False


def test_ensure_running_respects_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Autostart off means the server is untouched, with a clear reason."""

    def fake_start(**_kwargs):
        raise AssertionError("must not spawn when disabled")

    monkeypatch.setenv("TTI_LOCAL_AUTOSTART", "0")
    monkeypatch.setattr(litert, "status", lambda: {"running": False, "binary_available": True})
    monkeypatch.setattr(litert, "start", fake_start)
    result = litert.ensure_running()
    assert result["started"] is False
    assert result["reason"] == "autostart disabled"


def test_ensure_running_delegates_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """The happy path forwards the bounded timeout to start()."""
    seen: dict[str, object] = {}

    def fake_start(wait_seconds: float = 8.0, **_kwargs):
        seen["wait_seconds"] = wait_seconds
        return {"started": True, "running": True, "binary_available": True}

    monkeypatch.setenv("TTI_LOCAL_AUTOSTART_TIMEOUT_SECONDS", "2")
    monkeypatch.setattr(litert, "status", lambda: {"running": False, "binary_available": True})
    monkeypatch.setattr(litert, "start", fake_start)
    result = litert.ensure_running()
    assert result["started"] is True
    assert seen["wait_seconds"] == 2.0


def test_ensure_running_swallows_spawn_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """A crashing start() is encoded, never raised — startup must survive."""

    def boom(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(litert, "status", lambda: {"running": False, "binary_available": False})
    monkeypatch.setattr(litert, "start", boom)
    result = litert.ensure_running()
    assert result["started"] is False
    assert "disk full" in str(result["error"])


# ---------------------------------------------------------------------------
# GH-45: lifespan hook
# ---------------------------------------------------------------------------


async def test_lifespan_autostarts_when_local(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Effective provider local + enabled flag records a healthy autostart event."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr(
        litert,
        "ensure_running",
        lambda **_kwargs: {"started": True, "running": True, "binary_available": True},
    )
    monkeypatch.setattr(litert, "health", lambda *_, **__: {"ok": True, "latency_ms": 1.0})
    await _boot_lifespan(monkeypatch, tmp_path)
    events = _autostart_events()
    assert len(events) == 1
    assert events[0].status == "ok"
    assert events[0].meta["started"] == "true"
    assert events[0].meta["running"] == "true"
    assert events[0].meta["healthy"] == "true"
    assert events[0].meta["error_class"] == ""


async def test_lifespan_skips_autostart_when_groq(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A persisted groq choice means the lifespan never touches LiteRT."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))

    def forbidden(**_kwargs):
        raise AssertionError("must not touch LiteRT for the groq provider")

    monkeypatch.setattr(litert, "ensure_running", forbidden)
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.migrate()
    repo.set_provider_config({"provider": "groq"})
    app = create_app()
    async with app.router.lifespan_context(app):
        pass
    assert _autostart_events() == []


async def test_lifespan_records_disabled_autostart(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Autostart off is a visible degraded event, not a silent skip."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART", "0")
    await _boot_lifespan(monkeypatch, tmp_path)
    events = _autostart_events()
    assert len(events) == 1
    assert events[0].status == "degraded"
    assert events[0].meta["error_class"] == "autostart_disabled"


async def test_lifespan_survives_autostart_crash(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Even a raising ensure_running cannot break backend startup."""
    _clear_provider_env(monkeypatch)

    def boom(**_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(litert, "ensure_running", boom)
    # Must not raise; the lifespan completes and serves traffic.
    await _boot_lifespan(monkeypatch, tmp_path)
    assert _autostart_events() == []


# ---------------------------------------------------------------------------
# GH-45: start/stop edge paths (no subprocesses spawned)
# ---------------------------------------------------------------------------


def test_start_is_noop_when_already_running(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A live pidfile means start() never builds a command."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setattr(litert, "status", lambda: {"running": True, "pid": 4242})
    result = litert.start()
    assert result["already_running"] is True
    assert result["started"] is False


def test_start_reports_missing_binary_without_spawning(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """No binary is a clean error dict, never an exception."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setattr(litert, "resolve_litert_binary", lambda: None)
    result = litert.start()
    assert result["started"] is False
    assert "not found" in str(result["error"])


def test_stop_without_pidfile_is_clean(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Stopping with no pidfile is a no-op with a clear reason."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    result = litert.stop()
    assert result["stopped"] is False
    assert result["reason"] == "no pidfile"


def test_health_reports_unreachable_server() -> None:
    """A closed localhost port is ok:false, never an exception."""
    import os

    os.environ["LITERT_BASE_URL"] = "http://127.0.0.1:9/v1"
    try:
        result = litert.health(timeout_seconds=0.5)
    finally:
        del os.environ["LITERT_BASE_URL"]
    assert result["ok"] is False


def test_serve_command_override_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """LITERT_SERVE_CMD replaces the default binary + flags."""
    monkeypatch.setenv("LITERT_SERVE_CMD", "/opt/custom/litert serve --model foo")
    assert litert.resolve_litert_binary() is None
    assert litert._build_serve_command() == []


def test_default_serve_command_has_no_model_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """serve selects the model from its own config; flags only pin host/port."""
    monkeypatch.delenv("LITERT_SERVE_CMD", raising=False)
    monkeypatch.setattr(litert, "resolve_litert_binary", lambda: "/usr/local/bin/litert-lm")
    assert litert._build_serve_command() == [
        "/usr/local/bin/litert-lm",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "9379",
    ]
