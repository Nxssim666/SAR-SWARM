"""
The bridge's decisions, without ROS or NATS (ADR 0024).

* Drone states become ``status`` messages in the ground station's units: heading in
  degrees true, clockwise from north (``DroneState.heading`` is radians counter-clockwise
  from east; the conversion is the onboard ``core.frames``); the onboard "target"
  estimate, in the mission frame, becomes a survivor sighting in WGS84, through the
  origin of the mission this bridge sent under that sequence.
* Requests become onboard ``SwarmCommand`` and ``MissionSpec`` messages, validated by
  the onboard code itself, numbered with milliseconds on this bridge's clock, strictly
  increasing (drones reject a sequence ahead of their own clock).
* The protocol has no acknowledgement beyond the drones' states, so the bridge
  republishes: a command until every addressed drone reports it processed, a mission
  until every drone heard flies it, each for a bounded time.

Everything here runs in one thread; ``node.py`` hands ROS callbacks over to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, Dict, List, Optional, Tuple, Union

from sar_gcs_bridge import wire
from swarm_sar.core.frames import heading_to_px4_yaw
from swarm_sar.core.geodesy import GeoPoint, LocalProjection
from swarm_sar.core.messages import (CommandKind, DroneStatus, MissionSpec, SwarmCommand)
from swarm_sar.ros.mission_cli import sequence_at

COMMAND_REPEAT_S = 0.5
COMMAND_WINDOW_S = 10.0
MISSION_REPEAT_S = 1.0
MISSION_WINDOW_S = 30.0
STATUS_MIN_PERIOD_S = 0.2  # at most 5 states per drone per second go to the station
MISSION_ORIGINS_KEPT = 16

Outgoing = Union[SwarmCommand, MissionSpec]


def heading_degrees(heading: float) -> Optional[float]:
    """Convert an ENU heading (rad, counter-clockwise from east) to degrees true [0, 360)."""
    if not math.isfinite(heading):
        return None
    degrees = math.degrees(heading_to_px4_yaw(heading)) % 360.0
    return 0.0 if degrees >= 360.0 else degrees


@dataclass
class _Pending:
    """A message being republished until the drones catch up, or its window ends."""

    message: Outgoing
    first_sent: float
    next_send: float


@dataclass
class Bridge:
    """Sequencing, republishing and conversion for one swarm."""

    swarm: str
    clock: Callable[[], float]  # seconds since the Unix epoch (the ground clock)
    drones: Dict[int, DroneStatus] = field(default_factory=dict)
    _last_sequence: int = 0
    _last_forwarded: Dict[int, float] = field(default_factory=dict)
    _origins: Dict[int, GeoPoint] = field(default_factory=dict)
    _pending: List[_Pending] = field(default_factory=list)

    # -- drone states ------------------------------------------------------------------

    def on_status(self, status: DroneStatus) -> Optional[Dict[str, object]]:
        """Record a drone's state; return the message for the station, or None (rate limit)."""
        now = self.clock()
        self.drones[status.drone_id] = status
        last = self._last_forwarded.get(status.drone_id)
        if last is not None and now - last < STATUS_MIN_PERIOD_S:
            return None
        self._last_forwarded[status.drone_id] = now
        return self.status_message(status, now)

    def status_message(self, status: DroneStatus, received_at: float) -> Dict[str, object]:
        """Convert a drone state to the station's ``status`` message."""
        position = status.position
        return wire.status(
            drone_id=status.drone_id, stamp=status.stamp, received_at=received_at,
            phase=int(status.phase), health=int(status.health), faults=status.faults,
            mission_sequence=status.mission_sequence,
            command_sequence=status.command_sequence,
            position=None if position is None else (position.latitude, position.longitude),
            heading_deg=heading_degrees(status.heading),
            velocity_north=float(status.velocity[1]), velocity_east=float(status.velocity[0]),
            nearest_obstacle=status.nearest_obstacle,
            sighting=self._sighting(status))

    def _sighting(self, status: DroneStatus) -> Optional[Tuple[float, float, float, float]]:
        estimate = status.estimate
        origin = self._origins.get(status.mission_sequence)
        if estimate is None or origin is None:
            # Without the origin of the drone's mission the estimate cannot be placed:
            # unknown, never a guess (it may be a mission another station sent).
            return None
        east, north = estimate.position
        point = LocalProjection(origin).to_geo(east, north)
        return (point.latitude, point.longitude, float(estimate.position_std),
                float(estimate.stamp))

    # -- requests ----------------------------------------------------------------------

    def _next_sequence(self, now: float) -> int:
        self._last_sequence = max(sequence_at(now), self._last_sequence + 1)
        return self._last_sequence

    def command(self, data: bytes) -> Tuple[Dict[str, object], Optional[SwarmCommand]]:
        """Answer a command request; return the reply and the command to publish (or None)."""
        now = self.clock()
        try:
            kind, drone_ids = wire.parse_command(data)
            command = SwarmCommand(self._next_sequence(now), CommandKind(wire.COMMANDS[kind]),
                                   now, frozenset(drone_ids))
        except ValueError as exc:  # WireError, or the onboard validation
            return wire.reply(error=str(exc)), None
        self._pending.append(_Pending(command, now, now + COMMAND_REPEAT_S))
        return wire.reply(sequence=command.sequence), command

    def mission(self, data: bytes) -> Tuple[Dict[str, object], Optional[MissionSpec]]:
        """Answer a mission request; return the reply and the mission to publish (or None)."""
        now = self.clock()
        try:
            fields = wire.parse_mission(data)
            spec = MissionSpec(
                sequence=self._next_sequence(now), mission_id=fields['mission_id'],
                origin=GeoPoint(*fields['origin']),
                altitude=fields['altitude_relative_m'],
                grid_resolution=fields['grid_resolution_m'],
                waypoints=tuple(GeoPoint(*p) for p in fields['waypoints']),
                area=tuple(GeoPoint(*p) for p in fields['area']))
        except ValueError as exc:
            return wire.reply(error=str(exc)), None
        self._origins[spec.sequence] = spec.origin
        for old in sorted(self._origins)[:-MISSION_ORIGINS_KEPT]:
            del self._origins[old]
        self._pending.append(_Pending(spec, now, now + MISSION_REPEAT_S))
        return wire.reply(sequence=spec.sequence), spec

    # -- republishing ------------------------------------------------------------------

    def _caught_up(self, message: Outgoing) -> bool:
        if isinstance(message, SwarmCommand):
            addressed = message.drone_ids or frozenset(self.drones)
            return all(i in self.drones and self.drones[i].command_sequence >= message.sequence
                       for i in addressed)
        return bool(self.drones) and all(
            s.mission_sequence >= message.sequence for s in self.drones.values())

    def due(self) -> List[Outgoing]:
        """Return the messages to publish again now, and forget the finished ones."""
        now = self.clock()
        due: List[Outgoing] = []
        keep: List[_Pending] = []
        for pending in self._pending:
            command = isinstance(pending.message, SwarmCommand)
            window = COMMAND_WINDOW_S if command else MISSION_WINDOW_S
            if self._caught_up(pending.message) or now - pending.first_sent > window:
                continue
            if now >= pending.next_send:
                due.append(pending.message)
                pending.next_send = now + (COMMAND_REPEAT_S if command else MISSION_REPEAT_S)
            keep.append(pending)
        self._pending = keep
        return due

    def heartbeat(self) -> Dict[str, object]:
        """Return the bridge's heartbeat."""
        return wire.heartbeat(self.swarm, self.clock(), list(self.drones))
