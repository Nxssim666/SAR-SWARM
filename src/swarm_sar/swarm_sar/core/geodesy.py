"""
WGS84 positions and the local tangent-plane projection used by PX4.

Everything that crosses a drone boundary (peer positions, missions, target
reports) is exchanged in WGS84, because every drone has its own local
frame (PX4 anchors it where its estimator started) and positions in one
drone's local frame mean nothing to another drone.

``LocalProjection`` reproduces PX4's ``MapProjection`` exactly (same
azimuthal equidistant formulas, same Earth radius), so a local position
computed here agrees with the flight controller's own local position for
the same reference point.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import numbers

from swarm_sar.core.geometry import Vec2

EARTH_RADIUS_M = 6_371_000.0  # PX4 CONSTANTS_RADIUS_OF_EARTH
MAX_ABS_LATITUDE = 85.0  # the projection degenerates near the poles


def _real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f'{name} must be a number, got {value!r}')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'{name} must be finite, got {value!r}')
    return result


@dataclass(frozen=True)
class GeoPoint:
    """A WGS84 latitude/longitude in degrees."""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        latitude = _real(self.latitude, 'latitude')
        longitude = _real(self.longitude, 'longitude')
        if not -90.0 <= latitude <= 90.0:
            raise ValueError(f'latitude must be in [-90, 90], got {latitude}')
        if not -180.0 <= longitude <= 180.0:
            raise ValueError(f'longitude must be in [-180, 180], got {longitude}')
        object.__setattr__(self, 'latitude', latitude)
        object.__setattr__(self, 'longitude', longitude)


def _wrap_longitude(degrees: float) -> float:
    wrapped = math.fmod(degrees + 180.0, 360.0)
    if wrapped < 0.0:
        wrapped += 360.0
    return wrapped - 180.0


class LocalProjection:
    """Map WGS84 positions to metres ``(east, north)`` around a reference point."""

    __slots__ = ('reference', '_lat0', '_lon0', '_sin0', '_cos0')

    def __init__(self, reference: GeoPoint) -> None:
        if abs(reference.latitude) > MAX_ABS_LATITUDE:
            raise ValueError(f'reference latitude {reference.latitude} is too close to a pole '
                             f'(limit {MAX_ABS_LATITUDE} degrees)')
        self.reference = reference
        self._lat0 = math.radians(reference.latitude)
        self._lon0 = math.radians(reference.longitude)
        self._sin0 = math.sin(self._lat0)
        self._cos0 = math.cos(self._lat0)

    def to_local(self, point: GeoPoint) -> Vec2:
        """Return ``(east, north)`` in metres of ``point`` relative to the reference."""
        lat = math.radians(point.latitude)
        dlon = math.radians(point.longitude) - self._lon0
        sin_lat, cos_lat = math.sin(lat), math.cos(lat)
        cos_dlon = math.cos(dlon)
        arg = min(max(self._sin0 * sin_lat + self._cos0 * cos_lat * cos_dlon, -1.0), 1.0)
        c = math.acos(arg)
        k = c / math.sin(c) if abs(c) > 0.0 else 1.0
        north = k * (self._cos0 * sin_lat - self._sin0 * cos_lat * cos_dlon) * EARTH_RADIUS_M
        east = k * cos_lat * math.sin(dlon) * EARTH_RADIUS_M
        return (east, north)

    def to_geo(self, east: float, north: float) -> GeoPoint:
        """Return the WGS84 position ``east``/``north`` metres from the reference."""
        x = _real(north, 'north') / EARTH_RADIUS_M
        y = _real(east, 'east') / EARTH_RADIUS_M
        c = math.hypot(x, y)
        if c == 0.0:
            return self.reference
        sin_c, cos_c = math.sin(c), math.cos(c)
        lat = math.asin(min(max(cos_c * self._sin0 + x * sin_c * self._cos0 / c, -1.0), 1.0))
        lon = self._lon0 + math.atan2(y * sin_c, c * self._cos0 * cos_c - x * self._sin0 * sin_c)
        return GeoPoint(math.degrees(lat), _wrap_longitude(math.degrees(lon)))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, LocalProjection) and self.reference == other.reference

    def __hash__(self) -> int:
        return hash(self.reference)

    def __repr__(self) -> str:
        return f'LocalProjection({self.reference!r})'
