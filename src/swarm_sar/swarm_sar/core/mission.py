"""
Missions resolved into the shared mission frame, and the link to each drone's local frame.

A ``MissionSpec`` (WGS84, from the ground station) becomes a
``MissionPlan``: the area polygon and waypoints projected into the mission
frame (ENU metres around the mission origin), validated geometrically, plus
the coverage grid every drone on the mission derives identically.

``FrameLink`` relates the mission frame to one drone's local frame through
WGS84. It is exact (both directions use PX4's projection) rather than a
translation, so it stays correct for missions kilometres from home.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Tuple

from swarm_sar.core.coverage import grid_geometry, GridGeometry
from swarm_sar.core.geodesy import GeoPoint, LocalProjection
from swarm_sar.core.geometry import Bounds, distance, normalize_polygon, Vec2
from swarm_sar.core.messages import MissionSpec

MAX_MISSION_EXTENT_M = 5000.0
MIN_AREA_M2 = 25.0


class MissionError(ValueError):
    """Raised when a mission cannot be flown (malformed geometry, too large, ...)."""


@dataclass(frozen=True, eq=False)
class MissionPlan:
    """A validated mission expressed in the shared mission frame."""

    spec: MissionSpec
    projection: LocalProjection
    area: Tuple[Vec2, ...]
    waypoints: Tuple[Vec2, ...]
    geometry: GridGeometry

    @property
    def sequence(self) -> int:
        """Return the mission sequence number."""
        return self.spec.sequence

    @property
    def altitude(self) -> float:
        """Return the flight altitude above home."""
        return self.spec.altitude


def build_mission_plan(spec: MissionSpec) -> MissionPlan:
    """Project and validate ``spec``; raise ``MissionError`` if it cannot be flown."""
    try:
        projection = LocalProjection(spec.origin)
        area = normalize_polygon([projection.to_local(p) for p in spec.area], MIN_AREA_M2)
        waypoints = tuple(projection.to_local(p) for p in spec.waypoints)
    except ValueError as exc:
        raise MissionError(f'mission {spec.mission_id!r}: {exc}') from exc
    for point in area + waypoints:
        if math.hypot(point[0], point[1]) > MAX_MISSION_EXTENT_M:
            raise MissionError(f'mission {spec.mission_id!r} reaches '
                               f'{math.hypot(point[0], point[1]):.0f} m from its origin '
                               f'(limit {MAX_MISSION_EXTENT_M:.0f} m)')
    try:
        geometry = grid_geometry(Bounds.around(area), spec.grid_resolution, area)
    except ValueError as exc:
        raise MissionError(f'mission {spec.mission_id!r}: {exc}') from exc
    return MissionPlan(spec, projection, area, waypoints, geometry)


def geofence_violation(plan: MissionPlan, home: Vec2, radius: float) -> Optional[str]:
    """
    Return why ``plan`` leaves the geofence disc around ``home`` (mission frame), or None.

    Checking vertices is sufficient: the disc is convex, so the polygon and
    the straight legs between waypoints are inside whenever their vertices are.
    """
    for label, points in (('waypoint', plan.waypoints), ('area vertex', plan.area)):
        for i, point in enumerate(points):
            gap = distance(point, home)
            if gap > radius:
                return f'{label} {i} is {gap:.0f} m from home (geofence {radius:.0f} m)'
    return None


class FrameLink:
    """Convert between one drone's local frame and the mission frame (via WGS84)."""

    __slots__ = ('local', 'mission')

    def __init__(self, local: LocalProjection, mission: LocalProjection) -> None:
        self.local = local
        self.mission = mission

    def local_to_mission(self, point: Vec2) -> Vec2:
        """Convert a local ENU position to the mission frame."""
        return self.mission.to_local(self.local.to_geo(point[0], point[1]))

    def mission_to_local(self, point: Vec2) -> Vec2:
        """Convert a mission-frame position to local ENU."""
        return self.local.to_local(self.mission.to_geo(point[0], point[1]))

    def local_to_geo(self, point: Vec2) -> GeoPoint:
        """Convert a local ENU position to WGS84."""
        return self.local.to_geo(point[0], point[1])

    def geo_to_local(self, point: GeoPoint) -> Vec2:
        """Convert WGS84 to local ENU."""
        return self.local.to_local(point)
