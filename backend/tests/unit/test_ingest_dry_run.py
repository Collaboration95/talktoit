"""Dry-run ingest reports policy without activating or parsing local health data."""

from __future__ import annotations

import json
import sys

from app.ingest import run


def test_dry_run_report_is_json_and_does_not_open_database(monkeypatch, tmp_path, capsys) -> None:
    export = tmp_path / "export.xml"
    export.write_text("<HealthData/>")
    monkeypatch.setattr(sys, "argv", ["ingest", str(export), "--dry-run-report"])
    run.main()
    report = json.loads(capsys.readouterr().out)
    assert report["activation"] == "not_started"
    assert report["source_size_bytes"] == export.stat().st_size
    assert report["resolved_workers"] == 1
