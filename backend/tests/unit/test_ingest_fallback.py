"""Compatibility failures retry only in a fresh, explicitly opted-in staging DB."""

from __future__ import annotations

import sys

import duckdb
import pytest

from app.db.dataset_lifecycle import DatasetLifecycle
from app.ingest import run
from app.ingest.compatibility import V2CompatibilityError
from app.state.app_state import AppStateRepository

pytestmark = pytest.mark.ingest_contract


def test_v2_compatibility_failure_can_fallback_to_legacy_staging(tmp_path, monkeypatch) -> None:
    export = tmp_path / "export.xml"
    export.write_text(
        '<HealthData><Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" '
        'startDate="2024-01-01 00:00:00 +0000" endDate="2024-01-01 00:01:00 +0000" '
        'value="12" /></HealthData>'
    )
    target = tmp_path / "health.duckdb"
    monkeypatch.setenv("TTI_DB_PATH", str(target))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setattr(sys, "argv", ["ingest", str(export)])
    monkeypatch.setenv("TTI_INGEST_FALLBACK_LEGACY", "1")

    import app.ingest.coordinator as coordinator

    monkeypatch.setattr(
        coordinator,
        "ingest_v2",
        lambda **_kwargs: (_ for _ in ()).throw(V2CompatibilityError("forced incompatibility")),
    )
    run.main()

    generation = DatasetLifecycle(target).active()
    assert generation is not None
    conn = duckdb.connect(str(generation.database_path), read_only=True)
    assert conn.execute("SELECT COUNT(*) FROM records").fetchone() == (1,)
    conn.close()
    activated = AppStateRepository().get_active()
    assert activated is not None
    assert activated.parser_version == "legacy-v1-fallback"
    assert "forced incompatibility" in activated.warnings[0]
