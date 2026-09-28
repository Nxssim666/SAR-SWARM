"""
RViz2 message builders for the ground-station monitor (MarkerArray, OccupancyGrid).

Pure functions over injected message classes, so they are tested without
ROS. Everything is drawn in the mission frame (fixed frame ``mission``).
"""

from __future__ import annotations

import array
from dataclasses import dataclass
import math
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np
from swarm_sar.core.coverage import GridGeometry
from swarm_sar.core.geometry import Vec2
from swarm_sar.core.messages import DroneStatus, HealthLevel, Phase
from swarm_sar.core.mission import MissionPlan
from swarm_sar.ros.codec import seconds_to_time

PHASE_RGBA = {
    Phase.STANDBY: (0.60, 0.60, 0.60, 0.90),
    Phase.TRANSIT: (0.55, 0.45, 0.85, 0.95),
    Phase.SEARCH: (0.20, 0.55, 0.95, 0.95),
    Phase.TRACK: (0.95, 0.45, 0.15, 0.95),
    Phase.HOLD: (0.95, 0.80, 0.10, 0.95),
}
CRITICAL_RGBA = (0.90, 0.10, 0.10, 1.00)
AREA_RGBA = (0.20, 0.80, 0.40, 0.90)
ROUTE_RGBA = (0.80, 0.80, 0.80, 0.80)
GOAL_RGBA = (1.00, 1.00, 1.00, 0.35)
ESTIMATE_RGBA = (1.00, 0.85, 0.10, 0.45)
TEXT_RGBA = (1.00, 1.00, 1.00, 0.95)
ARROW_LENGTH_M = 2.5
ESTIMATE_SIGMAS = 2.0


@dataclass(frozen=True)
class VizTypes:
    """Message classes needed to build visualisations."""

    Marker: Any
    MarkerArray: Any
    Point: Any
    ColorRGBA: Any
    OccupancyGrid: Any
    Time: Any

    @classmethod
    def load(cls) -> 'VizTypes':
        """Import the real message classes."""
        from builtin_interfaces.msg import Time
        from geometry_msgs.msg import Point
        from nav_msgs.msg import OccupancyGrid
        from std_msgs.msg import ColorRGBA
        from visualization_msgs.msg import Marker, MarkerArray
        return cls(Marker, MarkerArray, Point, ColorRGBA, OccupancyGrid, Time)


def build_markers(types: VizTypes, drones: Sequence[Tuple[DroneStatus, Vec2]],
                  plan: Optional[MissionPlan], stamp: float, frame_id: str) -> Any:
    """
    Return a MarkerArray: mission area and route, drones, goals, best target estimate.

    ``drones`` pairs each status with its mission-frame position. The array
    starts with DELETEALL so markers of drones that went silent do not linger.
    """
    marker = types.Marker
    markers = [_delete_all(types, stamp, frame_id)]
    if plan is not None:
        area = _marker(types, 'area', 0, marker.LINE_STRIP, stamp, frame_id)
        _scale(area, 0.4, 0.0, 0.0)
        area.color = _color(types, AREA_RGBA)
        area.points = [_point(types, p) for p in plan.area + plan.area[:1]]
        markers.append(area)
        if plan.waypoints:
            route = _marker(types, 'route', 0, marker.LINE_STRIP, stamp, frame_id)
            _scale(route, 0.25, 0.0, 0.0)
            route.color = _color(types, ROUTE_RGBA)
            route.points = [_point(types, p) for p in plan.waypoints]
            markers.append(route)
    for status, position in drones:
        rgba = CRITICAL_RGBA if status.health is HealthLevel.CRITICAL \
            else PHASE_RGBA[status.phase]
        arrow = _marker(types, 'drones', status.drone_id, marker.ARROW, stamp, frame_id)
        _place(arrow, position)
        arrow.pose.orientation.z = math.sin(status.heading / 2.0)
        arrow.pose.orientation.w = math.cos(status.heading / 2.0)
        _scale(arrow, ARROW_LENGTH_M, 0.6, 0.6)
        arrow.color = _color(types, rgba)
        markers.append(arrow)
        label = _marker(types, 'labels', status.drone_id, marker.TEXT_VIEW_FACING, stamp,
                        frame_id)
        _place(label, position, height=2.0)
        _scale(label, 0.0, 0.0, 1.2)
        label.color = _color(types, TEXT_RGBA)
        label.text = f'{status.drone_id} {status.phase.name}' + (
            '' if status.health is HealthLevel.OK else f' {status.health.name}')
        markers.append(label)

    goals = _marker(types, 'goals', 0, marker.LINE_LIST, stamp, frame_id)
    _scale(goals, 0.15, 0.0, 0.0)
    goals.color = _color(types, GOAL_RGBA)
    goal_points: List[Any] = []
    for status, position in drones:
        if status.goal is not None:
            goal_points.extend((_point(types, position), _point(types, status.goal)))
    goals.points = goal_points
    markers.append(goals)

    estimates = [s.estimate for s, _ in drones if s.estimate is not None]
    if estimates:
        best = min(estimates, key=lambda e: e.position_std)
        (semi_major, semi_minor), yaw = _ellipse(best.position_covariance)
        disc = _marker(types, 'target_estimate', 0, marker.CYLINDER, stamp, frame_id)
        _place(disc, best.position)
        disc.pose.orientation.z = math.sin(yaw / 2.0)
        disc.pose.orientation.w = math.cos(yaw / 2.0)
        _scale(disc, max(2.0 * semi_major, 0.1), max(2.0 * semi_minor, 0.1), 0.2)
        disc.color = _color(types, ESTIMATE_RGBA)
        markers.append(disc)

    array_msg = types.MarkerArray()
    array_msg.markers = markers
    return array_msg


def build_coverage_grid(types: VizTypes, last_seen: np.ndarray, geometry: GridGeometry,
                        now: float, revisit_period: float, stamp: float, frame_id: str) -> Any:
    """
    Return an OccupancyGrid: 0 = just searched, 100 = stale or never searched, -1 = outside.

    OccupancyGrid rows run along x (index = iy * width + ix), so the
    ``(nx, ny)`` array is transposed before flattening.
    """
    staleness = np.clip((now - last_seen) / revisit_period, 0.0, 1.0)
    values = np.rint(staleness * 100.0).astype(np.int8)
    values[~geometry.valid] = -1
    grid = types.OccupancyGrid()
    grid.header.stamp = seconds_to_time(stamp, types.Time)
    grid.header.frame_id = frame_id
    grid.info.map_load_time = seconds_to_time(stamp, types.Time)
    grid.info.resolution = float(geometry.cell_size)
    grid.info.width = geometry.nx
    grid.info.height = geometry.ny
    grid.info.origin.position.x = float(geometry.bounds.xmin)
    grid.info.origin.position.y = float(geometry.bounds.ymin)
    grid.data = array.array('b', np.ascontiguousarray(values.T).tobytes())
    return grid


def _ellipse(cov: np.ndarray) -> Tuple[Tuple[float, float], float]:
    """Return ``((semi-major, semi-minor), yaw)`` of the ESTIMATE_SIGMAS ellipse of ``cov``."""
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    semi_minor, semi_major = (ESTIMATE_SIGMAS * math.sqrt(max(float(v), 0.0))
                              for v in eigenvalues)
    major_axis = eigenvectors[:, 1]
    return (semi_major, semi_minor), math.atan2(float(major_axis[1]), float(major_axis[0]))


def _delete_all(types: VizTypes, stamp: float, frame_id: str) -> Any:
    marker = types.Marker()
    marker.header.stamp = seconds_to_time(stamp, types.Time)
    marker.header.frame_id = frame_id
    marker.action = types.Marker.DELETEALL
    return marker


def _marker(types: VizTypes, ns: str, marker_id: int, marker_type: int, stamp: float,
            frame_id: str) -> Any:
    """
    Return an ADD marker of the given type.

    Marker.CYLINDER == Marker.DELETEALL == 3: type and action are different
    fields and must never be compared with each other.
    """
    marker = types.Marker()
    marker.header.stamp = seconds_to_time(stamp, types.Time)
    marker.header.frame_id = frame_id
    marker.ns = ns
    marker.id = int(marker_id)
    marker.type = marker_type
    marker.action = types.Marker.ADD
    marker.pose.orientation.w = 1.0
    return marker


def _place(marker: Any, xy: Vec2, height: float = 0.0) -> None:
    marker.pose.position.x = float(xy[0])
    marker.pose.position.y = float(xy[1])
    marker.pose.position.z = float(height)


def _scale(marker: Any, x: float, y: float, z: float) -> None:
    marker.scale.x, marker.scale.y, marker.scale.z = float(x), float(y), float(z)


def _color(types: VizTypes, rgba: Tuple[float, float, float, float]) -> Any:
    return types.ColorRGBA(r=rgba[0], g=rgba[1], b=rgba[2], a=rgba[3])


def _point(types: VizTypes, xy: Vec2) -> Any:
    return types.Point(x=float(xy[0]), y=float(xy[1]), z=0.0)
