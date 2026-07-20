"""Compatibility failures retry only in a fresh, explicitly opted-in staging DB."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

from app.ingest import run
from app.ingest.compatibility import V2CompatibilityError

pytestmark = pytest.mark.ingest_contract


def test_v2_compatibility_failure_can_fallback_to_legacy_staging(tmp_path, monkeypatch) -> None:
    export = tmp_path / "export.xml"
    export.write_text(
        '<HealthData><Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" '
        'startDate="2024-01-01 00:00:00 +0000" endDate="2024-01-01 00:01:00 +0000" '
        'value="12" /></HealthData>'
    )
    target = tmp_path / "health.duckdb"
    monkeypatch.setattr(run, "resolve_db_path", lambda: target)
    monkeypatch.setattr(sys, "argv", ["ingest", str(export)])
    monkeypatch.setenv("TTI_INGEST_FALLBACK_LEGACY", "1")

    import app.ingest.coordinator as coordinator

    monkeypatch.setattr(
        coordinator,
        "ingest_v2",
        lambda **_kwargs: (_ for _ in ()).throw(V2CompatibilityError("forced incompatibility")),
    )
    activated: dict[str, object] = {}

    class FakeState:
        def activate_file(self, _source: Path, **manifest: object) -> None:
            activated.update(manifest)

    monkeypatch.setattr(run, "AppStateRepository", FakeState)
    run.main()

    conn = duckdb.connect(str(target), read_only=True)
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone() == (1,)
    conn.close()
    assert activated["parser_version"] == "legacy-v1-fallback"
    assert "forced incompatibility" in activated["warnings"][0]  # type: ignore[index]
