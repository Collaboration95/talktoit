"""Tests for the bounded, file-versioned GPX route cache."""

from __future__ import annotations

from pathlib import Path

from app.ingest import gpx

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "route.gpx"


def test_gpx_route_cache_reuses_a_file_version(monkeypatch) -> None:
    gpx.clear_gpx_route_cache()
    calls = 0
    original_parse = gpx.etree.parse

    def parse(path: str, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original_parse(path, *args, **kwargs)

    monkeypatch.setattr(gpx.etree, "parse", parse)

    first = gpx.parse_gpx_route(FIXTURE)
    second = gpx.parse_gpx_route(FIXTURE)

    assert first == second
    assert first is not None
    assert calls == 1


def test_gpx_route_cache_negatively_caches_missing_and_invalid_routes(
    tmp_path: Path, monkeypatch
) -> None:
    gpx.clear_gpx_route_cache()
    calls = 0
    original_parse = gpx.etree.parse

    def parse(path: str, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original_parse(path, *args, **kwargs)

    monkeypatch.setattr(gpx.etree, "parse", parse)

    missing = tmp_path / "missing.gpx"
    assert gpx.parse_gpx_route(missing) is None
    assert gpx.parse_gpx_route(missing) is None
    assert calls == 0

    invalid = tmp_path / "invalid.gpx"
    invalid.write_text("not xml", encoding="utf-8")
    assert gpx.parse_gpx_route(invalid) is None
    assert gpx.parse_gpx_route(invalid) is None
    assert calls == 1
