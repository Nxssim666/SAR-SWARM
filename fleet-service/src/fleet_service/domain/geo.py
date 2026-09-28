"""
Geospatial types and validation (ADR 0014).

Points carry explicit ``latitude``/``longitude`` keys. Areas are GeoJSON polygons
(RFC 7946, ``[lon, lat]``), and every vertex must lie inside the incident's
operating area: a swapped pair is otherwise still a valid-looking coordinate, often
in another continent, and this check is what catches it.
"""

from collections.abc import Iterable, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pyproj import Geod
from shapely import Polygon
from shapely.geometry.polygon import orient
from shapely.validation import explain_validity

MAX_POLYGON_VERTICES = 256  # the onboard swarm protocol's limit, kept for every area
_GEOD = Geod(ellps="WGS84")

# Strict: a numeric string is not a coordinate.
Latitude = Annotated[float, Field(strict=True, ge=-90.0, le=90.0, allow_inf_nan=False)]
Longitude = Annotated[float, Field(strict=True, ge=-180.0, le=180.0, allow_inf_nan=False)]
Position = tuple[Longitude, Latitude]
# A closed ring repeats its first position last: 3..256 vertices -> 4..257 positions.
Ring = Annotated[list[Position], Field(min_length=4, max_length=MAX_POLYGON_VERTICES + 1)]


class GeoPoint(BaseModel):
    """A WGS84 position with explicit keys (never a bare pair)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    latitude: Latitude
    longitude: Longitude


class PolygonGeoJSON(BaseModel):
    """
    A GeoJSON Polygon with one ring (no holes), 3 to 256 distinct vertices, valid
    (not self-intersecting, non-zero area), normalized to a counter-clockwise ring.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["Polygon"]
    coordinates: list[Ring] = Field(
        min_length=1,
        max_length=1,
        description="Exactly one closed ring of [longitude, latitude] positions (RFC 7946).",
    )

    @field_validator("coordinates")
    @classmethod
    def _valid_ring(cls, rings: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
        ring = rings[0]
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("the ring must be closed: at least 4 positions, first equal to last")
        vertices = ring[:-1]
        distinct = len(set(vertices))
        if distinct < 3:
            raise ValueError("the ring needs at least 3 distinct vertices")
        if len(vertices) > MAX_POLYGON_VERTICES:
            raise ValueError(f"the ring has more than {MAX_POLYGON_VERTICES} vertices")
        longitudes = [lon for lon, _ in vertices]
        if max(longitudes) - min(longitudes) > 180.0:
            raise ValueError("polygons crossing the antimeridian are not supported")
        polygon = Polygon(ring)
        if not polygon.is_valid:
            raise ValueError(f"invalid polygon: {explain_validity(polygon)}")
        if polygon.area <= 0.0:
            raise ValueError("the polygon has zero area")
        oriented = orient(polygon, sign=1.0)
        return [[(float(x), float(y)) for x, y, *_ in oriented.exterior.coords]]

    def vertices(self) -> list[GeoPoint]:
        """Return the distinct vertices (the closing position omitted)."""
        return [GeoPoint(latitude=lat, longitude=lon) for lon, lat in self.coordinates[0][:-1]]

    def area_m2(self) -> float:
        """Return the geodesic area on the WGS84 ellipsoid, in square metres."""
        area, _ = _GEOD.geometry_area_perimeter(Polygon(self.coordinates[0]))
        return abs(float(area))


def distance_m(a: GeoPoint, b: GeoPoint) -> float:
    """Return the geodesic distance between two points on the WGS84 ellipsoid."""
    _, _, dist = _GEOD.inv(a.longitude, a.latitude, b.longitude, b.latitude)
    return float(dist)


def outside_operating_area(
    points: Iterable[GeoPoint], base: GeoPoint, radius_m: float
) -> list[int]:
    """Return the indices of ``points`` farther than ``radius_m`` from ``base``."""
    points = list(points)
    if not points:
        return []
    _, _, dists = _GEOD.inv(
        [base.longitude] * len(points),
        [base.latitude] * len(points),
        [p.longitude for p in points],
        [p.latitude for p in points],
    )
    return [i for i, d in enumerate(dists) if d > radius_m]


def describe_outside(indices: Sequence[int], what: str) -> str:
    """Human-readable message for points outside the operating area."""
    shown = ", ".join(str(i) for i in indices[:10]) + (" …" if len(indices) > 10 else "")
    return (
        f"{len(indices)} {what} outside the incident's operating area (indices {shown}). "
        "Check that latitude and longitude are not swapped: GeoJSON order is [longitude, latitude]."
    )
