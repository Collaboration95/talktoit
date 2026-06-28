"""Unit tests for the GPX parser (R1-01)."""

from __future__ import annotations

from pathlib import Path

from app.ingest.gpx import parse_gpx_route

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "route.gpx"


def test_parse_valid_gpx() -> None:
    """Parsing a valid GPX file returns a GeoJSON LineString."""
    result = parse_gpx_route(str(FIXTURE))
    assert result is not None
    assert result.type == "LineString"
    assert len(result.coordinates) == 3
    # GPX: lon="103.8198" lat="1.3521" → GeoJSON: [lon, lat] = [103.8198, 1.3521]
    assert result.coordinates[0] == [103.8198, 1.3521]
    assert result.coordinates[1] == [103.8204, 1.3532]
    assert result.coordinates[2] == [103.8210, 1.3545]


def test_parse_nonexistent_file() -> None:
    """A nonexistent GPX file returns None."""
    result = parse_gpx_route("/nonexistent/path.gpx")
    assert result is None


def test_parse_empty_gpx() -> None:
    """A GPX file with no track points returns None."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".gpx", delete=False) as f:
        f.write(
            '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg></trkseg></trk></gpx>'
        )
        temp_path = f.name

    try:
        result = parse_gpx_route(temp_path)
        assert result is None
    finally:
        Path(temp_path).unlink()
