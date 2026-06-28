"""GPX route file → GeoJSON LineString parser.

Lightweight parser that extracts track points from a GPX file.
Only the coordinate list is returned; metadata (elevation, time) is ignored.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree  # type: ignore[import-untyped]

from app.models.templates import GpsRoute

# GPX XML namespace
_NS = "http://www.topografix.com/GPX/1/1"


def parse_gpx_route(file_path: str | Path) -> GpsRoute | None:
    """Parse a GPX file and return a GeoJSON LineString of the first track.

    Args:
        file_path: Path to the GPX file. Relative paths are resolved against
            the directory of the original export.xml (the file reference is a
            sibling of the export).

    Returns:
        A :class:`GpsRoute` with track coordinates, or ``None`` if the file
        cannot be parsed or contains no track points.
    """
    path = Path(file_path)
    if not path.exists():
        return None

    try:
        tree = etree.parse(str(path))
        root = tree.getroot()
    except Exception:
        return None

    # Collect all track points from the first track segment
    coords: list[list[float]] = []
    for trkpt in root.iter(f"{{{_NS}}}trkpt"):
        lat_str = trkpt.get("lat")
        lon_str = trkpt.get("lon")
        if lat_str is not None and lon_str is not None:
            coords.append([float(lon_str), float(lat_str)])

    if not coords:
        return None

    return GpsRoute(type="LineString", coordinates=coords)
