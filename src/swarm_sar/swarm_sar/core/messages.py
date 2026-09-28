"""
Transport-agnostic messages exchanged between drones and with the ground station.

The ROS layer converts these to and from ``swarm_sar_interfaces`` messages;
the simulator passes them around directly. Construction validates every
field, so anything that reaches the decision logic has already been checked
whichever transport it arrived on.

Positions that cross a drone boundary are WGS84 (``GeoPoint``): each drone
has its own local frame. Fields in the *mission frame* (goals, target
estimates, coverage cells) are only meaningful to drones on the same
mission, which is why they travel with the mission sequence number.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
import math
import numbers
from typing import FrozenSet, Iterable, Optional, Tuple

import numpy as np

from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.geometry import as_vec2, Vec2
from swarm_sar.core.tracking import TargetEstimate

PROTOCOL_VERSION = 2
MAX_DRONE_ID = 2 ** 31 - 1
MAX_SEQUENCE = 2 ** 63 - 1
MAX_MISSION_ID_LENGTH = 64
MAX_AREA_VERTICES = 256
MAX_WAYPOINTS = 64
MAX_COMMAND_TARGETS = 1024
# Mission and command sequence numbers are milliseconds on the ground-station clock.
SEQUENCE_UNITS_PER_SECOND = 1000


class Phase(enum.IntEnum):
    """What a drone is doing with its mission."""

    STANDBY = 0  # no mission, or the flight controller is not in offboard control
    TRANSIT = 1  # flying the mission's waypoints toward the area
    SEARCH = 2   # searching its share of the area
    TRACK = 3    # holding a ring around a found target
    HOLD = 4     # stopped by the operator or by a mission fault


class HealthLevel(enum.IntEnum):
    """How much of its job a drone can currently do."""

    OK = 0
    DEGRADED = 1  # can hold position but must not move (e.g. depth camera stale)
    CRITICAL = 2  # cannot control the vehicle (e.g. pose or flight-controller link lost)


class Receipt(enum.Enum):
    """Outcome of offering an inbound message to a drone."""

    ACCEPTED = 'accepted'
    OWN = 'own'
    STALE = 'stale'
    FUTURE = 'future'
    OUT_OF_ORDER = 'out_of_order'
    WRONG_MISSION = 'wrong_mission'
    INCOMPATIBLE = 'incompatible'
    IGNORED = 'ignored'


class CommandKind(enum.IntEnum):
    """Operator commands broadcast by the ground station."""

    HOLD = 1              # stop and hover where you are (companion keeps control)
    RESUME = 2            # continue the mission after HOLD or a stuck waypoint
    RETURN_TO_LAUNCH = 3  # hand the vehicle to the flight controller's RTL
    LAND = 4              # hand the vehicle to the flight controller's LAND


def check_id(drone_id: int) -> int:
    """Validate a drone id."""
    if isinstance(drone_id, bool) or not isinstance(drone_id, numbers.Integral):
        raise ValueError(f'drone_id must be an integer, got {drone_id!r}')
    if not 0 <= drone_id <= MAX_DRONE_ID:
        raise ValueError(f'drone_id must be in [0, {MAX_DRONE_ID}], got {drone_id}')
    return int(drone_id)


def check_sequence(sequence: int, name: str, allow_zero: bool) -> int:
    """Validate a sequence number."""
    if isinstance(sequence, bool) or not isinstance(sequence, numbers.Integral):
        raise ValueError(f'{name} must be an integer, got {sequence!r}')
    low = 0 if allow_zero else 1
    if not low <= sequence <= MAX_SEQUENCE:
        raise ValueError(f'{name} must be in [{low}, {MAX_SEQUENCE}], got {sequence}')
    return int(sequence)


def sequence_is_plausible(sequence: int, now: float, max_clock_skew: float) -> bool:
    """
    Return False for a sequence number ahead of the receiver's clock.

    Sequence numbers only ever increase, so a single forged or corrupted one
    near the maximum would lock a drone out of every later mission or
    command; tying them to the clock bounds how far ahead one can be.
    """
    return sequence <= (now + max_clock_skew) * SEQUENCE_UNITS_PER_SECOND


def check_time(value: float, name: str) -> float:
    """Validate a timestamp or duration in seconds."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'{name} must be finite, got {value!r}')
    return result


@dataclass(frozen=True, eq=False)
class DroneStatus:
    """A drone's periodic broadcast: where it is, what it does, how healthy it is."""

    drone_id: int
    stamp: float
    position: Optional[GeoPoint]  # None until the drone has a global reference
    velocity: Vec2                # east, north [m/s]
    heading: float                # ENU heading [rad]
    phase: Phase
    health: HealthLevel
    faults: int
    mission_sequence: int         # 0 = no active mission
    command_sequence: int         # last operator command processed (acknowledgement)
    goal: Optional[Vec2] = None                  # mission frame
    estimate: Optional[TargetEstimate] = None    # mission frame
    nearest_obstacle: float = math.inf           # [m], inf when nothing is known nearby

    def __post_init__(self) -> None:
        object.__setattr__(self, 'drone_id', check_id(self.drone_id))
        object.__setattr__(self, 'stamp', check_time(self.stamp, 'stamp'))
        if self.position is not None and not isinstance(self.position, GeoPoint):
            raise ValueError('position must be a GeoPoint or None')
        object.__setattr__(self, 'velocity', as_vec2(self.velocity, 'velocity'))
        object.__setattr__(self, 'heading', check_time(self.heading, 'heading'))
        object.__setattr__(self, 'phase', Phase(self.phase))
        object.__setattr__(self, 'health', HealthLevel(self.health))
        if isinstance(self.faults, bool) or not isinstance(self.faults, numbers.Integral) \
                or not 0 <= self.faults < 2 ** 32:
            raise ValueError(f'faults must be a 32-bit mask, got {self.faults!r}')
        object.__setattr__(self, 'faults', int(self.faults))
        object.__setattr__(self, 'mission_sequence',
                           check_sequence(self.mission_sequence, 'mission_sequence', True))
        object.__setattr__(self, 'command_sequence',
                           check_sequence(self.command_sequence, 'command_sequence', True))
        if self.goal is not None:
            object.__setattr__(self, 'goal', as_vec2(self.goal, 'goal'))
        if self.estimate is not None and not isinstance(self.estimate, TargetEstimate):
            raise ValueError(f'estimate must be a TargetEstimate, got {type(self.estimate)}')
        nearest = float(self.nearest_obstacle)
        if math.isnan(nearest) or nearest < 0.0:
            raise ValueError(f'nearest_obstacle must be >= 0, got {self.nearest_obstacle!r}')
        object.__setattr__(self, 'nearest_obstacle', nearest)


@dataclass(frozen=True, eq=False)
class CoverageUpdate:
    """Cells a drone observed, as flat indices into its mission's grid with times."""

    drone_id: int
    stamp: float
    mission_sequence: int
    full: bool
    cells: np.ndarray
    last_seen: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, 'drone_id', check_id(self.drone_id))
        object.__setattr__(self, 'stamp', check_time(self.stamp, 'stamp'))
        object.__setattr__(self, 'mission_sequence',
                           check_sequence(self.mission_sequence, 'mission_sequence', False))
        object.__setattr__(self, 'full', bool(self.full))
        cells = np.array(self.cells)
        times = np.array(self.last_seen, dtype=np.float64)
        if cells.ndim != 1 or times.shape != cells.shape:
            raise ValueError('cells and last_seen must be 1-D and of equal length')
        if cells.size and not np.issubdtype(cells.dtype, np.integer):
            raise ValueError('cells must be integer indices')
        cells = cells.astype(np.int64)
        if cells.size and int(cells.min()) < 0:
            raise ValueError('cell indices must be non-negative')
        if not np.all(np.isfinite(times)):
            raise ValueError('last_seen must be finite')
        cells.setflags(write=False)
        times.setflags(write=False)
        object.__setattr__(self, 'cells', cells)
        object.__setattr__(self, 'last_seen', times)


@dataclass(frozen=True)
class TargetReport:
    """A georeferenced detection of the search target by a drone's onboard detector."""

    stamp: float
    position: GeoPoint
    std: float         # 1-sigma horizontal position uncertainty [m]
    confidence: float  # detector score in [0, 1]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'stamp', check_time(self.stamp, 'stamp'))
        if not isinstance(self.position, GeoPoint):
            raise ValueError('position must be a GeoPoint')
        std = float(self.std)
        if not math.isfinite(std) or std <= 0.0:
            raise ValueError(f'std must be positive, got {self.std!r}')
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f'confidence must be in [0, 1], got {self.confidence!r}')
        object.__setattr__(self, 'std', std)
        object.__setattr__(self, 'confidence', confidence)


@dataclass(frozen=True, eq=False)
class MissionSpec:
    """What the operator asked the swarm to do, in WGS84 (validated for form only)."""

    sequence: int                  # strictly increasing per ground station; higher replaces
    mission_id: str                # human-readable label
    origin: GeoPoint               # origin of the shared mission frame
    altitude: float                # [m] above each drone's home
    grid_resolution: float         # [m] coverage grid cell size (identical for every drone)
    waypoints: Tuple[GeoPoint, ...]
    area: Tuple[GeoPoint, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'sequence', check_sequence(self.sequence, 'sequence', False))
        if not isinstance(self.mission_id, str) or not self.mission_id.isprintable() \
                or len(self.mission_id) > MAX_MISSION_ID_LENGTH:
            raise ValueError(f'mission_id must be printable text of at most '
                             f'{MAX_MISSION_ID_LENGTH} characters')
        if not isinstance(self.origin, GeoPoint):
            raise ValueError('origin must be a GeoPoint')
        for name in ('altitude', 'grid_resolution'):
            value = check_time(getattr(self, name), name)
            if value <= 0.0:
                raise ValueError(f'{name} must be positive, got {value}')
            object.__setattr__(self, name, value)
        waypoints = tuple(self.waypoints)
        area = tuple(self.area)
        if len(waypoints) > MAX_WAYPOINTS:
            raise ValueError(f'at most {MAX_WAYPOINTS} waypoints are allowed')
        if not 3 <= len(area) <= MAX_AREA_VERTICES:
            raise ValueError(f'the area needs 3 to {MAX_AREA_VERTICES} vertices, got {len(area)}')
        if not all(isinstance(p, GeoPoint) for p in waypoints + area):
            raise ValueError('waypoints and area vertices must be GeoPoints')
        object.__setattr__(self, 'waypoints', waypoints)
        object.__setattr__(self, 'area', area)


@dataclass(frozen=True)
class SwarmCommand:
    """An operator command; ``drone_ids`` empty means every drone."""

    sequence: int
    kind: CommandKind
    stamp: float
    drone_ids: FrozenSet[int] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'sequence', check_sequence(self.sequence, 'sequence', False))
        object.__setattr__(self, 'kind', CommandKind(self.kind))
        object.__setattr__(self, 'stamp', check_time(self.stamp, 'stamp'))
        ids: Iterable[int] = self.drone_ids
        targets = frozenset(check_id(i) for i in ids)
        if len(targets) > MAX_COMMAND_TARGETS:
            raise ValueError(f'at most {MAX_COMMAND_TARGETS} target drones per command')
        object.__setattr__(self, 'drone_ids', targets)

    def applies_to(self, drone_id: int) -> bool:
        """Return True if this command is addressed to ``drone_id``."""
        return not self.drone_ids or drone_id in self.drone_ids
