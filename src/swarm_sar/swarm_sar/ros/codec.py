"""
Conversion between core messages and ``swarm_sar_interfaces`` (protocol version 2).

Message classes are injected through ``MessageTypes`` rather than imported at
module level, so this module can be imported and tested without a ROS 2
installation. Decoding treats every message as untrusted: any malformed or
inconsistent field raises ``MessageValidationError`` (never a stray exception
from deep inside numpy), which the nodes count, log and drop.
"""

from __future__ import annotations

import array
from dataclasses import dataclass
import math
from typing import Any, Optional, Tuple

import numpy as np
from swarm_sar.core.coverage import MAX_CELLS
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.messages import (CommandKind, CoverageUpdate, DroneStatus, HealthLevel,
                                     MAX_AREA_VERTICES, MAX_COMMAND_TARGETS, MAX_WAYPOINTS,
                                     MissionSpec, Phase, PROTOCOL_VERSION, SwarmCommand,
                                     TargetReport)
from swarm_sar.core.metrics import MetricsSnapshot
from swarm_sar.core.tracking import TargetEstimate

_NS_PER_S = 1_000_000_000
_INT32_MIN, _INT32_MAX = -(2 ** 31), 2 ** 31 - 1
MAX_COVERAGE_CELLS = MAX_CELLS  # a full snapshot never holds more cells than a grid


class MessageValidationError(ValueError):
    """Raised when an inbound message is malformed or inconsistent."""


@dataclass(frozen=True)
class MessageTypes:
    """The concrete message classes the codec builds (injected for testability)."""

    DroneState: Any
    TargetEstimate: Any
    CoverageUpdate: Any
    Mission: Any
    SwarmCommand: Any
    TargetReport: Any
    SwarmMetrics: Any
    Time: Any

    @classmethod
    def load(cls) -> 'MessageTypes':
        """Import the generated message classes (requires a sourced ROS 2 workspace)."""
        from builtin_interfaces.msg import Time
        from swarm_sar_interfaces.msg import (CoverageUpdate, DroneState, Mission,
                                              SwarmCommand, SwarmMetrics, TargetReport)
        from swarm_sar_interfaces.msg import TargetEstimate as TargetEstimateMsg
        return cls(DroneState, TargetEstimateMsg, CoverageUpdate, Mission, SwarmCommand,
                   TargetReport, SwarmMetrics, Time)


def seconds_to_time(seconds: float, time_cls: Any) -> Any:
    """Convert float seconds to a ``builtin_interfaces/Time``."""
    if not math.isfinite(seconds):
        raise ValueError(f'cannot convert non-finite time {seconds!r}')
    # Split before scaling: seconds * 1e9 at epoch magnitudes is only exact to ~256 ns.
    whole = math.floor(seconds)
    sec, nanosec = int(whole), int(round((seconds - whole) * _NS_PER_S))
    if nanosec >= _NS_PER_S:
        sec, nanosec = sec + 1, nanosec - _NS_PER_S
    if not _INT32_MIN <= sec <= _INT32_MAX:
        raise ValueError(f'time {seconds!r} does not fit builtin_interfaces/Time')
    return time_cls(sec=sec, nanosec=nanosec)


def time_to_seconds(stamp: Any) -> float:
    """Convert a ``builtin_interfaces/Time`` to float seconds."""
    if not 0 <= stamp.nanosec < _NS_PER_S:
        raise ValueError(f'nanosec out of range: {stamp.nanosec}')
    return stamp.sec + stamp.nanosec / _NS_PER_S


def _geo_pairs(latitudes: Any, longitudes: Any, name: str, limit: int) -> Tuple[GeoPoint, ...]:
    # Sizes are checked before anything is built: the arrays come off the network.
    if len(latitudes) != len(longitudes):
        raise ValueError(f'{name}: {len(latitudes)} latitudes but {len(longitudes)} longitudes')
    if len(latitudes) > limit:
        raise ValueError(f'{name}: {len(latitudes)} points exceeds {limit}')
    return tuple(GeoPoint(float(a), float(o)) for a, o in zip(latitudes, longitudes))


class Codec:
    """Encode core messages and decode ROS messages into validated core messages."""

    def __init__(self, types: MessageTypes) -> None:
        self._t = types

    # -- DroneState ----------------------------------------------------------------
    def encode_status(self, status: DroneStatus) -> Any:
        """Build a DroneState message."""
        msg = self._t.DroneState()
        msg.protocol_version = PROTOCOL_VERSION
        msg.stamp = seconds_to_time(status.stamp, self._t.Time)
        msg.drone_id = status.drone_id
        msg.phase = int(status.phase)
        msg.health = int(status.health)
        msg.faults = int(status.faults)
        msg.mission_sequence = status.mission_sequence
        msg.command_sequence = status.command_sequence
        msg.has_position = status.position is not None
        if status.position is not None:
            msg.latitude = status.position.latitude
            msg.longitude = status.position.longitude
        msg.velocity_east = float(status.velocity[0])
        msg.velocity_north = float(status.velocity[1])
        msg.heading = float(status.heading)
        msg.has_goal = status.goal is not None
        if status.goal is not None:
            msg.goal_x, msg.goal_y = float(status.goal[0]), float(status.goal[1])
        msg.has_target_estimate = status.estimate is not None
        if status.estimate is not None:
            self._fill_estimate(msg.target_estimate, status.estimate)
        msg.nearest_obstacle = float(status.nearest_obstacle)
        return msg

    def decode_status(self, msg: Any) -> Tuple[DroneStatus, int]:
        """Validate a DroneState message; return it with the sender's protocol version."""
        try:
            estimate = (self._decode_estimate(msg.target_estimate)
                        if msg.has_target_estimate else None)
            position = GeoPoint(msg.latitude, msg.longitude) if msg.has_position else None
            status = DroneStatus(
                drone_id=int(msg.drone_id), stamp=time_to_seconds(msg.stamp), position=position,
                velocity=(msg.velocity_east, msg.velocity_north), heading=msg.heading,
                phase=Phase(msg.phase), health=HealthLevel(msg.health), faults=int(msg.faults),
                mission_sequence=int(msg.mission_sequence),
                command_sequence=int(msg.command_sequence),
                goal=(msg.goal_x, msg.goal_y) if msg.has_goal else None, estimate=estimate,
                nearest_obstacle=msg.nearest_obstacle)
            return status, int(msg.protocol_version)
        except (ValueError, TypeError, AttributeError) as exc:
            raise MessageValidationError(f'invalid DroneState: {exc}') from exc

    # -- CoverageUpdate ------------------------------------------------------------
    def encode_coverage(self, update: CoverageUpdate) -> Any:
        """Build a CoverageUpdate message."""
        msg = self._t.CoverageUpdate()
        msg.stamp = seconds_to_time(update.stamp, self._t.Time)
        msg.drone_id = update.drone_id
        msg.mission_sequence = update.mission_sequence
        msg.full = update.full
        msg.cells = array.array('I', np.ascontiguousarray(update.cells, dtype=np.uint32).tobytes())
        msg.last_seen = array.array(
            'd', np.ascontiguousarray(update.last_seen, dtype=np.float64).tobytes())
        return msg

    def decode_coverage(self, msg: Any) -> CoverageUpdate:
        """Validate a CoverageUpdate message (index range is checked against the grid later)."""
        try:
            if len(msg.cells) > MAX_COVERAGE_CELLS:
                raise ValueError(f'{len(msg.cells)} cells exceeds {MAX_COVERAGE_CELLS}')
            cells = np.asarray(msg.cells, dtype=np.int64)
            times = np.asarray(msg.last_seen, dtype=np.float64)
            return CoverageUpdate(int(msg.drone_id), time_to_seconds(msg.stamp),
                                  int(msg.mission_sequence), bool(msg.full), cells, times)
        except (ValueError, TypeError, AttributeError) as exc:
            raise MessageValidationError(f'invalid CoverageUpdate: {exc}') from exc

    # -- Mission -----------------------------------------------------------------------
    def encode_mission(self, spec: MissionSpec) -> Any:
        """Build a Mission message."""
        msg = self._t.Mission()
        msg.sequence = spec.sequence
        msg.mission_id = spec.mission_id
        msg.origin_latitude = spec.origin.latitude
        msg.origin_longitude = spec.origin.longitude
        msg.altitude = float(spec.altitude)
        msg.grid_resolution = float(spec.grid_resolution)
        msg.waypoint_latitudes = array.array('d', [p.latitude for p in spec.waypoints])
        msg.waypoint_longitudes = array.array('d', [p.longitude for p in spec.waypoints])
        msg.area_latitudes = array.array('d', [p.latitude for p in spec.area])
        msg.area_longitudes = array.array('d', [p.longitude for p in spec.area])
        return msg

    def decode_mission(self, msg: Any) -> MissionSpec:
        """Validate a Mission message (form only; geometry is checked by the controller)."""
        try:
            return MissionSpec(
                sequence=int(msg.sequence), mission_id=str(msg.mission_id),
                origin=GeoPoint(msg.origin_latitude, msg.origin_longitude),
                altitude=msg.altitude, grid_resolution=msg.grid_resolution,
                waypoints=_geo_pairs(msg.waypoint_latitudes, msg.waypoint_longitudes,
                                     'waypoints', MAX_WAYPOINTS),
                area=_geo_pairs(msg.area_latitudes, msg.area_longitudes, 'area',
                                MAX_AREA_VERTICES))
        except (ValueError, TypeError, AttributeError) as exc:
            raise MessageValidationError(f'invalid Mission: {exc}') from exc

    # -- SwarmCommand ------------------------------------------------------------------
    def encode_command(self, command: SwarmCommand) -> Any:
        """Build a SwarmCommand message."""
        msg = self._t.SwarmCommand()
        msg.sequence = command.sequence
        msg.stamp = seconds_to_time(command.stamp, self._t.Time)
        msg.command = int(command.kind)
        msg.drone_ids = array.array('I', sorted(command.drone_ids))
        return msg

    def decode_command(self, msg: Any) -> SwarmCommand:
        """Validate a SwarmCommand message."""
        try:
            if len(msg.drone_ids) > MAX_COMMAND_TARGETS:
                raise ValueError(f'{len(msg.drone_ids)} target drones exceeds '
                                 f'{MAX_COMMAND_TARGETS}')
            return SwarmCommand(int(msg.sequence), CommandKind(msg.command),
                                time_to_seconds(msg.stamp),
                                frozenset(int(i) for i in msg.drone_ids))
        except (ValueError, TypeError, AttributeError) as exc:
            raise MessageValidationError(f'invalid SwarmCommand: {exc}') from exc

    # -- TargetReport ------------------------------------------------------------------
    def encode_target_report(self, report: TargetReport) -> Any:
        """Build a TargetReport message."""
        msg = self._t.TargetReport()
        msg.stamp = seconds_to_time(report.stamp, self._t.Time)
        msg.latitude = report.position.latitude
        msg.longitude = report.position.longitude
        msg.position_std = float(report.std)
        msg.confidence = float(report.confidence)
        return msg

    def decode_target_report(self, msg: Any) -> TargetReport:
        """Validate a TargetReport message."""
        try:
            return TargetReport(time_to_seconds(msg.stamp), GeoPoint(msg.latitude, msg.longitude),
                                msg.position_std, msg.confidence)
        except (ValueError, TypeError, AttributeError) as exc:
            raise MessageValidationError(f'invalid TargetReport: {exc}') from exc

    # -- SwarmMetrics --------------------------------------------------------------------
    def encode_metrics(self, snapshot: MetricsSnapshot, stamp: float, frame_id: str) -> Any:
        """Build a SwarmMetrics message (NaN for values not available)."""
        msg = self._t.SwarmMetrics()
        msg.header.stamp = seconds_to_time(stamp, self._t.Time)
        msg.header.frame_id = frame_id
        msg.mission_time = float(snapshot.mission_time)
        msg.drones_alive = int(snapshot.drones_alive)
        msg.explored_fraction = float(snapshot.explored_fraction)
        msg.fresh_fraction = float(snapshot.fresh_fraction)
        msg.num_tracking = int(snapshot.num_tracking)
        msg.num_holding = int(snapshot.num_holding)
        msg.num_degraded = int(snapshot.num_degraded)
        msg.target_detected = bool(snapshot.target_detected)
        msg.time_to_first_detection = _or_nan(snapshot.time_to_first_detection)
        msg.tracking_error = _or_nan(snapshot.tracking_error)
        msg.min_separation = _or_nan(snapshot.min_separation)
        msg.min_obstacle_distance = _or_nan(snapshot.min_obstacle_distance)
        return msg

    # -- helpers -----------------------------------------------------------------------
    def _fill_estimate(self, msg: Any, estimate: TargetEstimate) -> None:
        msg.stamp = seconds_to_time(estimate.stamp, self._t.Time)
        msg.last_measurement_stamp = seconds_to_time(estimate.last_measurement_time, self._t.Time)
        msg.state = np.array(estimate.state, dtype=np.float64)
        msg.covariance = np.array(estimate.covariance, dtype=np.float64).reshape(16)

    @staticmethod
    def _decode_estimate(msg: Any) -> TargetEstimate:
        return TargetEstimate(np.asarray(msg.state, dtype=np.float64),
                              np.asarray(msg.covariance, dtype=np.float64),
                              time_to_seconds(msg.stamp),
                              time_to_seconds(msg.last_measurement_stamp))


def _or_nan(value: Optional[float]) -> float:
    return math.nan if value is None else float(value)
