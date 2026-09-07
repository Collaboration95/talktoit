"""GPX route file → GeoJSON LineString parser.

Lightweight parser that extracts track points from a GPX file.
Only the coordinate list is returned; metadata (elevation, time) is ignored.
"""

from __future__ import annotations

from functools import lru_cache
from math import isfinite
from pathlib import Path

from lxml import etree  # type: ignore[import-untyped]

from app.models.templates import GpsRoute

# GPX XML namespace
_NS = "http://www.topografix.com/GPX/1/1"
MAX_ROUTE_POINTS = 500


def simplify_route_points(
    coords: list[list[float]], max_points: int = MAX_ROUTE_POINTS
) -> list[list[float]]:
    """Uniformly downsample an ordered route while retaining its endpoints."""
    if len(coords) <= max_points:
        return coords
    step = (len(coords) - 1) / (max_points - 1)
    return [coords[round(index * step)] for index in range(max_points)]


@lru_cache(maxsize=128)
def _parse_gpx_route_cached(resolved_path: str, mtime_ns: int, size: int) -> GpsRoute | None:
    """Parse one filesystem version of a route, including negative results."""
    if mtime_ns < 0 or size < 0:
        return None

    try:
        tree = etree.parse(resolved_path)
        root = tree.getroot()
    except Exception:
        return None

    # Collect all track points from the first track segment
    coords: list[list[float]] = []
    for trkpt in root.iter(f"{{{_NS}}}trkpt"):
        lat_str = trkpt.get("lat")
        lon_str = trkpt.get("lon")
        if lat_str is not None and lon_str is not None:
            try:
                lon, lat = float(lon_str), float(lat_str)
            except ValueError:
                continue
            if isfinite(lon) and isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90:
                coords.append([lon, lat])

    if not coords:
        return None

    return GpsRoute(type="LineString", coordinates=simplify_route_points(coords))


def clear_gpx_route_cache() -> None:
    """Clear the process-local route cache for test and lifecycle isolation."""
    _parse_gpx_route_cached.cache_clear()


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
    try:
        path = Path(file_path).expanduser().resolve()
        stat = path.stat()
    except (OSError, RuntimeError):
        # Keep missing files negatively cached. A later-created file gets a
        # different (real) stat key and is therefore parsed normally.
        try:
            resolved_path = Path(file_path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError):
            return None
        return _parse_gpx_route_cached(str(resolved_path), -1, -1)

    return _parse_gpx_route_cached(str(path), stat.st_mtime_ns, stat.st_size)
