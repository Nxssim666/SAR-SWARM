"""
A local metric frame for planning: the UTM zone of the area (ADR 0014, ADR 0028).

Patterns are geometry in metres (x east, y north). Planning in UTM keeps distances and
angles true to well under 0.1 % over a search area; results go back to WGS84.
"""

import math
from collections.abc import Iterable, Sequence

import numpy as np
from numpy.typing import NDArray
from pyproj import Transformer
from shapely import LineString, MultiPolygon, Polygon


def utm_epsg(latitude: float, longitude: float) -> int:
    """The EPSG code of the WGS84 UTM zone containing a point."""
    zone = min(int((longitude + 180.0) // 6.0) + 1, 60)
    return (32600 if latitude >= 0.0 else 32700) + zone


class LocalFrame:
    """Converts between WGS84 (longitude, latitude) and UTM metres around a reference point."""

    def __init__(self, latitude: float, longitude: float) -> None:
        self.epsg = utm_epsg(latitude, longitude)
        self._forward = Transformer.from_crs(4326, self.epsg, always_xy=True)
        self._inverse = Transformer.from_crs(self.epsg, 4326, always_xy=True)

    @classmethod
    def around(cls, ring: Sequence[tuple[float, float]]) -> "LocalFrame":
        """The frame of a [longitude, latitude] ring's mean position."""
        lon = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        return cls(lat, lon)

    def xy(self, longitude: float, latitude: float) -> tuple[float, float]:
        """WGS84 -> metres."""
        x, y = self._forward.transform(longitude, latitude)
        return float(x), float(y)

    def lonlat(self, x: float, y: float) -> tuple[float, float]:
        """Metres -> WGS84 (longitude, latitude)."""
        lon, lat = self._inverse.transform(x, y)
        return float(lon), float(lat)

    def lonlat_arrays(
        self, x: NDArray[np.float64], y: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Metres -> WGS84 for many points: (longitudes, latitudes)."""
        lon, lat = self._inverse.transform(x, y)
        return np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)

    def polygon(self, ring: Iterable[tuple[float, float]]) -> Polygon:
        """A [longitude, latitude] ring as a metric polygon."""
        return Polygon([self.xy(lon, lat) for lon, lat in ring])

    def ring(self, polygon: Polygon) -> list[tuple[float, float]]:
        """A metric polygon's exterior as a closed [longitude, latitude] ring."""
        return [self.lonlat(x, y) for x, y in polygon.exterior.coords]

    def line(self, points: Iterable[tuple[float, float]]) -> LineString:
        """(latitude, longitude) points as a metric line."""
        return LineString([self.xy(lon, lat) for lat, lon in points])


def bearing_vector(bearing_deg: float) -> tuple[float, float]:
    """A unit (east, north) vector for a bearing in degrees true, clockwise from north."""
    rad = math.radians(bearing_deg)
    return math.sin(rad), math.cos(rad)


def long_axis_bearing(polygon: Polygon | MultiPolygon) -> float:
    """The bearing (0-180 degrees) of the long side of the polygon's minimum rectangle."""
    rectangle = polygon.minimum_rotated_rectangle
    if not isinstance(rectangle, Polygon):  # degenerate: a line or a point
        return 0.0
    coords = list(rectangle.exterior.coords)
    sides = [(coords[i + 1][0] - coords[i][0], coords[i + 1][1] - coords[i][1]) for i in range(2)]
    dx, dy = max(sides, key=lambda s: math.hypot(*s))
    return math.degrees(math.atan2(dx, dy)) % 180.0
