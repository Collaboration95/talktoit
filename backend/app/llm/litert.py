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
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.state.app_state import (
    DEFAULT_LITERT_BASE_URL,
    DEFAULT_LITERT_MODEL,
    default_state_path,
)

LITERT_DEFAULT_HOST = "127.0.0.1"
LITERT_DEFAULT_PORT = 9379

# Env flags for the managed local-LLM lifecycle (GH-44/45/46). Autostart is on
# by default because `local` is the default provider; set TTI_LOCAL_AUTOSTART=0
# for manual Start/Stop only. TTI_LOCAL_STOP_ON_EXIT=1 opts into stopping the
# owned server when the backend exits (default leaves it warm across restarts).
AUTOSTART_ENV_VAR = "TTI_LOCAL_AUTOSTART"
AUTOSTART_TIMEOUT_ENV_VAR = "TTI_LOCAL_AUTOSTART_TIMEOUT_SECONDS"
STOP_ON_EXIT_ENV_VAR = "TTI_LOCAL_STOP_ON_EXIT"
AUTOSTART_TIMEOUT_DEFAULT_SECONDS = 3.0
AUTOSTART_TIMEOUT_MAX_SECONDS = 30.0
_LIFECYCLE_LOCK = threading.Lock()
# Children this process spawned and still owns, so stop() can reap them.
_OWNED_CHILDREN: dict[int, subprocess.Popen[bytes]] = {}


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
        return None
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
    owned = _read_owned_process()
    return owned.pid if owned is not None else None


@dataclass(frozen=True)
class _OwnedProcess:
    """A recorded pid plus the identity token that proves it is still ours."""

    pid: int
    start_token: str | None


def _read_owned_process() -> _OwnedProcess | None:
    """Return the recorded process, tolerating a legacy bare-pid pidfile."""
    pidfile = pidfile_path()
    if not pidfile.exists():
        return None
    try:
        text = pidfile.read_text().strip()
    except OSError:
        return None
    if not text:
        return None
    pid_text, _, token = text.partition(" ")
    try:
        pid = int(pid_text)
    except ValueError:
        return None
    return _OwnedProcess(pid=pid, start_token=token.strip() or None)


def _process_table_field(pid: int, field: str) -> str | None:
    """Return one collapsed ps field for a pid, or None when unavailable."""
    try:
        result = subprocess.run(  # noqa: S603 - querying the local process table
            ["ps", "-p", str(pid), "-o", f"{field}="],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = " ".join(result.stdout.split())
    return value or None


def _write_owned_pidfile(pid: int) -> None:
    """Record the pid and its start time so a recycled pid is never adopted."""
    token = _process_table_field(pid, "lstart")
    pidfile_path().write_text(f"{pid} {token}" if token else str(pid))


def _unlink_pidfile_if_owned_by(pid: int) -> None:
    """Drop the pidfile only when it still describes this pid."""
    owned = _read_owned_process()
    if owned is None or owned.pid != pid:
        return
    try:
        pidfile_path().unlink()
    except OSError:
        pass


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
    owned = _read_owned_process()
    running = owned is not None and _owns_process(owned)
    base_url = _litert_base_url()
    model = _litert_model()
    binary = resolve_litert_binary()
    pidfile = pidfile_path()
    log = log_path()
    return {
        "running": running,
        "pid": owned.pid if owned is not None and running else None,
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
    """Build the ``litert-lm serve`` command.

    ``litert-lm serve`` selects the model from its own config (the model
    imported via ``litert-lm import``); it takes no ``--model`` flag, so the
    default command only pins host/port. The ``model`` argument is kept for
    backward compatibility and ignored. Use ``LITERT_SERVE_CMD`` (or
    ``--config`` inside it) to serve a non-default model.
    """
    override = _litert_serve_cmd()
    if override is not None:
        if resolve_litert_binary() is None:
            return []
        return override
    binary = resolve_litert_binary()
    if binary is None:
        return []
    del model  # model selection lives in the litert-lm config, not CLI flags
    # Default command: litert-lm serve --host 127.0.0.1 --port 9379
    # If the LiteRT binary accepts different flags, the user can override via LITERT_SERVE_CMD.
    return [
        binary,
        "serve",
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
    with _LIFECYCLE_LOCK:
        return _start_locked(model=model, wait_seconds=wait_seconds, poll_interval=poll_interval)


def _start_locked(
    model: str | None = None, wait_seconds: float = 8.0, poll_interval: float = 0.5
) -> dict[str, object]:
    """Start LiteRT while the lifecycle lock is held."""
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

    # If a stale pidfile exists for a process we do not own, remove it.
    owned = _read_owned_process()
    if owned is not None and not _owns_process(owned):
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

    _OWNED_CHILDREN[proc.pid] = proc

    # Own the pid: only the spawner may later kill it. The pidfile records the
    # process start time alongside the pid so a recycled pid is never adopted.
    try:
        _write_owned_pidfile(proc.pid)
    except OSError as exc:
        _OWNED_CHILDREN.pop(proc.pid, None)
        _reap_process(proc)
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
        # If the process died early, surface it and drop the pidfile we just
        # wrote so the next caller is not misled by a stale pid.
        if proc.poll() is not None:
            _OWNED_CHILDREN.pop(proc.pid, None)
            _unlink_pidfile_if_owned_by(proc.pid)
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
    with _LIFECYCLE_LOCK:
        return _stop_locked(timeout_seconds)


def _owns_process(owned: _OwnedProcess) -> bool:
    """Return whether the recorded pid is still the LiteRT process we started.

    A recycled pid is rejected by the recorded start time, and the command is
    matched on whole tokens, so an unrelated process that merely mentions the
    binary name (for example a log-file path) is never signalled.
    """
    if not _is_running(owned.pid):
        return False
    if owned.start_token is not None:
        current = _process_table_field(owned.pid, "lstart")
        if current is None or current != owned.start_token:
            return False
    command = _process_table_field(owned.pid, "command")
    if command is None:
        return False
    binary = resolve_litert_binary()
    expected = Path(binary).name if binary else "litert-lm"
    return expected in {Path(token).name for token in command.split()}


def _reap_owned_child(pid: int) -> None:
    """Reap a child this process spawned earlier so it cannot linger as a zombie."""
    proc = _OWNED_CHILDREN.pop(pid, None)
    if proc is None:
        return
    try:
        proc.wait(timeout=2)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _reap_process(proc: subprocess.Popen[bytes], timeout_seconds: float = 2.0) -> None:
    """Terminate (then kill) a child we just spawned and reap it."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=timeout_seconds)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _stop_locked(timeout_seconds: float = 5.0) -> dict[str, object]:
    """Stop LiteRT while the lifecycle lock is held."""
    owned = _read_owned_process()
    if owned is None:
        return {"stopped": False, "reason": "no pidfile", **status()}
    if not _is_running(owned.pid):
        try:
            pidfile_path().unlink()
        except OSError:
            pass
        return {"stopped": False, "reason": "not running", **status()}
    if not _owns_process(owned):
        return {"stopped": False, "reason": "pidfile is not owned by LiteRT", **status()}

    try:
        os.kill(owned.pid, signal.SIGTERM)
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
        if not _is_running(owned.pid):
            break
        time.sleep(0.2)
    else:
        # Force kill if still alive.
        try:
            os.kill(owned.pid, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.2)

    # Reap the child we spawned so it cannot linger as a zombie.
    _reap_owned_child(owned.pid)
    try:
        pidfile_path().unlink()
    except OSError:
        pass
    return {"stopped": True, **status()}


def autostart_enabled() -> bool:
    """Return whether backend startup may start the owned server (default on)."""
    raw = os.environ.get(AUTOSTART_ENV_VAR, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def stop_on_exit() -> bool:
    """Return whether backend shutdown should stop the owned server (default off)."""
    raw = os.environ.get(STOP_ON_EXIT_ENV_VAR, "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def autostart_timeout_seconds() -> float:
    """Return the bounded startup health-wait, clamped to a safe range."""
    try:
        value = float(
            os.environ.get(AUTOSTART_TIMEOUT_ENV_VAR, str(AUTOSTART_TIMEOUT_DEFAULT_SECONDS))
        )
    except ValueError:
        return AUTOSTART_TIMEOUT_DEFAULT_SECONDS
    if value <= 0:
        return AUTOSTART_TIMEOUT_DEFAULT_SECONDS
    return min(value, AUTOSTART_TIMEOUT_MAX_SECONDS)


def ensure_running(wait_seconds: float | None = None) -> dict[str, object]:
    """Start the owned server unless it is already running or disabled.

    Never raises: a missing binary, a disabled flag, or a spawn failure is
    encoded in the returned dict so startup/CLI callers can log it and carry
    on with degraded (deterministic-only) answers.
    """
    try:
        current = status()
        if current.get("running"):
            return {"started": False, "already_running": True, **status()}
        if not autostart_enabled():
            return {"started": False, "reason": "autostart disabled", **status()}
        return start(
            wait_seconds=wait_seconds if wait_seconds is not None else autostart_timeout_seconds()
        )
    except Exception as exc:
        return {"started": False, "error": str(exc), **status()}
