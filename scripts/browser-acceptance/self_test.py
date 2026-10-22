"""Exercise the acceptance safety boundary with disposable synthetic inputs."""

import asyncio
import os
import socket
import tempfile
from pathlib import Path

from safety import install


def main() -> None:
    """Prove denied inference, TCP, DNS and .env reads cannot silently pass."""
    with tempfile.TemporaryDirectory(prefix="tti-browser-safety-") as temporary:
        private = Path(temporary)
        os.environ["TTI_ACCEPTANCE_PRIVATE"] = temporary
        install()
        from app.llm import client
        from app.llm.provider_gateway import ProviderGateway, ProviderUnavailableError

        assert client._env_loaded
        assert not ProviderGateway.permits(object(), "planning")
        try:
            asyncio.run(ProviderGateway.complete(object(), "planning", []))
        except ProviderUnavailableError:
            pass
        else:
            raise RuntimeError("provider-denial-not-enforced")
        with socket.socket() as connection:
            try:
                connection.connect(("192.0.2.1", 443))
            except PermissionError:
                pass
            else:
                raise RuntimeError("tcp-denial-not-enforced")
        try:
            socket.getaddrinfo("synthetic.invalid", 443)
        except PermissionError:
            pass
        else:
            raise RuntimeError("dns-denial-not-enforced")
        try:
            (private / ".env").read_text()
        except PermissionError:
            pass
        else:
            raise RuntimeError("private-read-denial-not-enforced")
        assert (private / "denials").read_text().splitlines() == [
            "provider",
            "tcp",
            "dns",
            "private_file",
        ]
        print(
            '{"providerDenied":true,"tcpDenied":true,"dnsDenied":true,"envReadDenied":true}'
        )


if __name__ == "__main__":
    main()
