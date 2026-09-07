"""Local LiteRT-LM lifecycle manager (GH-42).

Launches ``litert-lm serve`` as a PID-owned detached subprocess when the
user selects the local provider. The implementation reuses the proven
pattern from the ``ss-dcl`` repo: pidfile + log live in the app-state
directory, ``LITERT_SERVE_CMD`` overrides the command, and fallback
resolution checks ``litert-lm`` on PATH and ``~/litert-lm/.venv/bin/``.

The server is OpenAI-compatible: health via ``GET {base_url}/models``,
chat via ``POST {base_url}/chat/completions``.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path

import httpx

from app.state.app_state import (
    DEFAULT_LITERT_BASE_URL,
    DEFAULT_LITERT_MODEL,
    default_state_path,
)

LITERT_DEFAULT_HOST = "127.0.0.1"
LITERT_DEFAULT_PORT = 9379


def _litert_base_url() -> str:
    """Return the LiteRT base URL (OpenAI-compatible ``/v1``)."""
    raw = os.environ.get("LITERT_BASE_URL", DEFAULT_LITERT_BASE_URL).strip()
    return raw or DEFAULT_LITERT_BASE_URL


def _litert_model() -> str:
    """Return the LiteRT model name."""
    raw = os.environ.get("LITERT_MODEL", DEFAULT_LITERT_MODEL).strip()
    return raw or DEFAULT_LITERT_MODEL


def _litert_serve_cmd() -> list[str] | None:
    """Return the LiteRT serve command override, if set."""
    raw = os.environ.get("LITERT_SERVE_CMD", "").strip()
    if not raw:
        return None
    try:
        parts = shlex.split(raw)
    except ValueError:
        return None
    return parts if parts else None


def resolve_litert_binary() -> str | None:
    """Resolve the ``litert-lm`` binary path."""
    override = _litert_serve_cmd()
    if override:
        # If the user gave a full command, the binary is its first token.
        candidate = override[0]
        if Path(candidate).exists() or shutil.which(candidate):
            return candidate
        return candidate
    which = shutil.which("litert-lm")
    if which:
        return which
    # Fallback used by the reference implementation: ~/litert-lm/.venv/bin/litert-lm
    fallback = Path.home() / "litert-lm" / ".venv" / "bin" / "litert-lm"
    if fallback.exists():
        return str(fallback)
    return None


def _state_dir() -> Path:
    """Return the directory that holds the pidfile and log."""
    configured = os.environ.get("TTI_APP_STATE_PATH")
    if configured:
        return Path(configured).resolve().parent
    return default_state_path().resolve().parent


def pidfile_path() -> Path:
    """Return the pidfile path for the owned LiteRT process."""
    return _state_dir() / "litert.pid"


def log_path() -> Path:
    """Return the log path for the LiteRT server."""
    return _state_dir() / "litert.log"


def _read_pid() -> int | None:
    """Return the pid from the pidfile, or None if absent/invalid."""
    pidfile = pidfile_path()
    if not pidfile.exists():
        return None
    try:
        text = pidfile.read_text().strip()
        return int(text) if text else None
    except (ValueError, OSError):
        return None


def _is_running(pid: int) -> bool:
    """Return whether ``pid`` is a live process."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def status() -> dict[str, object]:
    """Return the current LiteRT server status."""
    pid = _read_pid()
    running = _is_running(pid) if pid is not None else False
    base_url = _litert_base_url()
    model = _litert_model()
    binary = resolve_litert_binary()
    pidfile = pidfile_path()
    log = log_path()
    return {
        "running": running,
        "pid": pid if running else None,
        "base_url": base_url,
        "model": model,
        "binary": binary,
        "pidfile": str(pidfile),
        "log_path": str(log),
        "binary_available": binary is not None,
    }


def health(timeout_seconds: float = 2.0) -> dict[str, object]:
    """Check the LiteRT server health via ``GET /models``.

    Returns a dict with ``ok``, ``latency_ms``, and optional ``error``.
    Never raises; failures are encoded in the returned dict.
    """
    base_url = _litert_base_url().rstrip("/")
    # The OpenAI-compatible base already ends with /v1; /models lives at /v1/models.
    url = f"{base_url}/models"
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            if response.status_code < 400:
                return {"ok": True, "latency_ms": latency_ms, "status_code": response.status_code}
            return {
                "ok": False,
                "latency_ms": latency_ms,
                "status_code": response.status_code,
                "error": f"HTTP {response.status_code}",
            }
    except Exception as exc:  # pragma: no cover - network edge
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        return {"ok": False, "latency_ms": latency_ms, "error": str(exc)}


def _build_serve_command(model: str | None = None) -> list[str]:
    """Build the ``litert-lm serve`` command."""
    override = _litert_serve_cmd()
    if override is not None:
        return override
    binary = resolve_litert_binary()
    if binary is None:
        return []
    model = model or _litert_model()
    # Default command: litert-lm serve --model <model> --host 127.0.0.1 --port 9379
    # If the LiteRT binary accepts different flags, the user can override via LITERT_SERVE_CMD.
    return [
        binary,
        "serve",
        "--model",
        model,
        "--host",
        LITERT_DEFAULT_HOST,
        "--port",
        str(LITERT_DEFAULT_PORT),
    ]


def start(
    model: str | None = None,
    wait_seconds: float = 8.0,
    poll_interval: float = 0.5,
) -> dict[str, object]:
    """Start the LiteRT server as a detached subprocess.

    Only the process that created the pidfile owns it; a stale pidfile from a
    dead process is reclaimed. If a live pidfile already exists this is a no-op
    and the current status is returned.

    Returns a status dict with ``started`` and optional ``error``.
    """
    current = status()
    if current.get("running"):
        return {"started": False, "already_running": True, **current}

    cmd = _build_serve_command(model=model)
    if not cmd:
        return {
            "started": False,
            "error": "litert-lm not found: set LITERT_SERVE_CMD or install litert-lm",
            **status(),
        }

    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    pidfile = pidfile_path()
    log = log_path()

    # If a stale pidfile exists for a dead process, remove it.
    pid = _read_pid()
    if pid is not None and not _is_running(pid):
        try:
            pidfile.unlink()
        except OSError:
            pass

    try:
        log_file = log.open("ab")
    except OSError as exc:
        return {"started": False, "error": f"Cannot open log {log}: {exc}", **status()}

    try:
        proc = subprocess.Popen(  # noqa: S603 - intentional: local binary per config
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        log_file.close()
        return {"started": False, "error": f"litert-lm not found: {exc}", **status()}
    except OSError as exc:
        log_file.close()
        return {"started": False, "error": str(exc), **status()}
    finally:
        # Close in parent; child keeps its own fd via dup.
        try:
            log_file.close()
        except OSError:
            pass

    # Own the pid: only the spawner may later kill it.
    try:
        pidfile.write_text(str(proc.pid))
    except OSError as exc:
        return {
            "started": False,
            "error": f"Cannot write pidfile: {exc}",
            "pid": proc.pid,
            **status(),
        }

    # Poll health until the server is ready or we time out.
    deadline = time.monotonic() + wait_seconds
    last_health: dict[str, object] = {"ok": False}
    while time.monotonic() < deadline:
        last_health = health(timeout_seconds=1.0)
        if last_health.get("ok"):
            return {"started": True, **status(), "health": last_health}
        # If the process died early, surface it.
        if proc.poll() is not None:
            return {
                "started": False,
                "error": f"litert-lm exited with code {proc.returncode}",
                "health": last_health,
                **status(),
            }
        time.sleep(poll_interval)

    # Timed out but process is still alive — leave it running; caller can poll health.
    return {
        "started": True,
        "health": last_health,
        "warning": "Server started but health check timed out",
        **status(),
    }


def stop(timeout_seconds: float = 5.0) -> dict[str, object]:
    """Stop the owned LiteRT server.

    Only kills the pid recorded in our pidfile, and only if that pid is still
    alive. Never kills an unrelated process.
    """
    pid = _read_pid()
    if pid is None:
        return {"stopped": False, "reason": "no pidfile", **status()}
    if not _is_running(pid):
        try:
            pidfile_path().unlink()
        except OSError:
            pass
        return {"stopped": False, "reason": "not running", **status()}

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        try:
            pidfile_path().unlink()
        except OSError:
            pass
        return {"stopped": False, "reason": "not running", **status()}
    except PermissionError as exc:
        return {"stopped": False, "error": str(exc), **status()}

    # Wait for graceful shutdown.
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_running(pid):
            break
        time.sleep(0.2)
    else:
        # Force kill if still alive.
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.2)

    try:
        pidfile_path().unlink()
    except OSError:
        pass
    return {"stopped": True, **status()}
