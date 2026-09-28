"""Geofence containment for command checks: exclusion zones win, inclusion zones bound."""

from collections.abc import Iterable
from dataclasses import dataclass

from shapely import Point, Polygon

from fleet_service.domain.enums import GeofenceKind


@dataclass(frozen=True)
class Fence:
    """One enabled geofence, as a planar lon/lat polygon (containment only, no distances)."""

    name: str
    kind: GeofenceKind
    polygon: Polygon
    max_altitude_relative_m: float | None


@dataclass(frozen=True)
class GeofenceSet:
    """The enabled geofences of the active incidents."""

    fences: tuple[Fence, ...] = ()

    @classmethod
    def of(cls, fences: Iterable[Fence]) -> "GeofenceSet":
        """Build from fences."""
        return cls(tuple(fences))

    def violation(
        self, latitude: float, longitude: float, altitude_relative_m: float | None
    ) -> str | None:
        """Return why a position is not allowed, or None if it is."""
        point = Point(longitude, latitude)
        containing = [f for f in self.fences if f.polygon.covers(point)]
        for fence in containing:
            if fence.kind is GeofenceKind.EXCLUSION:
                return f"inside exclusion geofence {fence.name!r}"
        inclusions = [f for f in self.fences if f.kind is GeofenceKind.INCLUSION]
        if inclusions and not any(f.kind is GeofenceKind.INCLUSION for f in containing):
            return "outside every inclusion geofence"
        if altitude_relative_m is not None:
            ceilings = [
                f.max_altitude_relative_m
                for f in containing
                if f.max_altitude_relative_m is not None
            ]
            if ceilings and altitude_relative_m > min(ceilings):
                return f"above the geofence ceiling of {min(ceilings):.0f} m"
        return None
