"""Acceptance-only provider/egress denial and subprocess ownership receipts."""

import os
import socket
import subprocess
import sys
from pathlib import Path

_installed = False


def install() -> None:
    """Deny inference and Python TCP egress before importing the application."""
    global _installed
    if _installed:
        return
    _installed = True
    private = Path(os.environ["TTI_ACCEPTANCE_PRIVATE"])

    def event(name: str) -> None:
        with (private / "denials").open("a") as output:
            output.write(name + "\n")

    def audit(name: str, args: tuple) -> None:
        if name == "socket.connect" and args[0].family in {
            socket.AF_INET,
            socket.AF_INET6,
        }:
            event("tcp")
            raise PermissionError("acceptance_tcp_denied")
        if name == "socket.getaddrinfo" and args[0] not in {
            "localhost",
            "127.0.0.1",
            "::1",
            None,
        }:
            event("dns")
            raise PermissionError("acceptance_dns_denied")
        if name == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0]))
            if path.name == ".env" or "personal-assets" in path.parts:
                event("private_file")
                raise PermissionError("acceptance_private_file_denied")

    sys.addaudithook(audit)
    from app.llm import client
    from app.llm.provider_gateway import ProviderGateway, ProviderUnavailableError

    # Avoid even opening either repository .env, including on clean-environment runs.
    client._env_loaded = True
    ProviderGateway.permits = lambda self, stage: False

    async def forbidden(self: object, stage: str, messages: object) -> str:
        event("provider")
        raise ProviderUnavailableError("Synthetic acceptance forbids inference")

    ProviderGateway.complete = forbidden
    original = subprocess.Popen

    class TrackedProcess(original):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self._acceptance_session = bool(kwargs.get("start_new_session"))
            if kwargs.get("start_new_session"):
                # This is a process lifecycle observation, not an importer/job patch.
                with (private / "process-groups").open("a") as output:
                    output.write(f"{self.pid}\n")

        def wait(self, *args: object, **kwargs: object) -> int:
            result = super().wait(*args, **kwargs)
            if getattr(self, "_acceptance_session", False):
                with (private / "process-groups").open("a") as output:
                    output.write(f"{-self.pid}\n")
                self._acceptance_session = False
            return result

    subprocess.Popen = TrackedProcess
    (private / "safety-installed").touch()
