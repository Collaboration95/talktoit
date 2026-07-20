"""Dry-run ingest reports policy without activating or parsing local health data."""

from __future__ import annotations

import json
import sys

import pytest

from app.ingest import run
from app.ingest.compatibility import V2CompatibilityError
from app.state.app_state import AppStateRepository


def test_dry_run_report_is_json_and_does_not_open_database(monkeypatch, tmp_path, capsys) -> None:
    export = tmp_path / "export.xml"
    export.write_text("<HealthData/>")
    monkeypatch.setattr(sys, "argv", ["ingest", str(export), "--dry-run-report"])
    run.main()
    report = json.loads(capsys.readouterr().out)
    assert report["activation"] == "not_started"
    assert report["source_size_bytes"] == export.stat().st_size
    assert report["resolved_workers"] == 1
    assert report["quality_checks"] == [
        "schema",
        "reconciliation",
        "canonical-counts",
        "typed-category-capture",
        "child-relation-integrity",
        "staged-activation",
        "manifest",
    ]


def test_completed_report_is_non_sensitive_structured_json(monkeypatch, tmp_path, capsys) -> None:
    """A completed generated import exposes policy and timing without source contents."""
    export = tmp_path / "export.xml"
    export.write_text(
        "<HealthData>"
        '<Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" '
        'startDate="2024-01-01 00:00:00 +0000" endDate="2024-01-01 00:01:00 +0000" '
        'value="42"/>'
        "</HealthData>"
    )
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setattr(sys, "argv", ["ingest", str(export), "--report-json"])

    run.main()

    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert report["mode"] == "v2"
    assert report["resolved_workers"] == 1
    assert report["counts"]["records"] == 1
    assert report["timing_seconds"]["total_time_seconds"] >= 0
    assert "export.xml" not in json.dumps(report)


def test_v2_compatibility_failure_keeps_previous_active_dataset(monkeypatch, tmp_path) -> None:
    """A failed staged V2 import cannot overwrite the active database or manifest."""
    export = tmp_path / "missing-field.xml"
    export.write_text(
        "<HealthData>"
        '<Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" '
        'startDate="2024-01-01 00:00:00 +0000" value="42"/>'
        "</HealthData>"
    )
    target = tmp_path / "health.duckdb"
    target.write_bytes(b"previous-active-database")
    state_path = tmp_path / "state.sqlite"
    monkeypatch.setenv("TTI_DB_PATH", str(target))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(state_path))
    previous = AppStateRepository().activate(
        source_bytes=b"previous",
        source_size_bytes=8,
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start="2023-01-01",
        coverage_end="2023-01-02",
        counts={"records": 1},
    )
    monkeypatch.setattr(sys, "argv", ["ingest", str(export)])

    with pytest.raises(V2CompatibilityError):
        run.main()

    assert target.read_bytes() == b"previous-active-database"
    assert AppStateRepository().get_active().id == previous.id  # type: ignore[union-attr]
