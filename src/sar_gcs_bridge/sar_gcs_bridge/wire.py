"""
The bridge's messages on NATS (ADR 0024), as JSON-compatible dicts.

The ground station's side of this contract is ``fleet_service.drivers.swarm_wire``; a
fleet-service test checks these builders and parsers against it, both ways. Standard
library only, so that test can import this module without ROS or numpy.

Subjects, for swarm ``<swarm>``: ``sar.v1.swarm.<swarm>.status`` (published per drone
state), ``.command`` and ``.mission`` (requests, answered with a reply), ``.bridge``
(heartbeat). Times are seconds since the Unix epoch; unknown values are ``None``.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

SUBJECT_PREFIX = 'sar.v1.swarm'
BRIDGE_VERSION = '1.0.0'

# DroneState.PHASE_* and HEALTH_* values, by index.
PHASES = ('standby', 'transit', 'search', 'track', 'hold')
HEALTH = ('ok', 'degraded', 'critical')
# DroneState.FAULT_* bits.
FAULTS = (
    (1 << 0, 'fc_link'), (1 << 1, 'pose_stale'), (1 << 2, 'pose_invalid'),
    (1 << 3, 'attitude_stale'), (1 << 4, 'no_global_reference'), (1 << 5, 'depth_stale'),
    (1 << 6, 'depth_blind'), (1 << 7, 'outside_geofence'), (1 << 8, 'altitude_mismatch'),
    (1 << 9, 'waypoint_unreachable'), (1 << 10, 'mission_rejected'),
    (1 << 11, 'control_overrun'), (1 << 12, 'radio_silent'),
)
# SwarmCommand.command values.
COMMANDS = {'hold': 1, 'resume': 2, 'return_to_launch': 3, 'land': 4}

Point = Tuple[float, float]  # latitude, longitude


class WireError(ValueError):
    """A request that does not follow the contract (answered with an error reply)."""


def subject(swarm: str, kind: str) -> str:
    """Return the NATS subject of a message kind for ``swarm``."""
    return f'{SUBJECT_PREFIX}.{swarm}.{kind}'


def fault_names(mask: int) -> List[str]:
    """Return the names of the fault bits set in ``mask``, in bit order."""
    return [name for bit, name in FAULTS if mask & bit]


def encode(message: Dict[str, Any]) -> bytes:
    """Serialize a message (compact JSON, UTF-8)."""
    return json.dumps(message, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _point(latitude: float, longitude: float) -> Dict[str, float]:
    return {'latitude': float(latitude), 'longitude': float(longitude)}


def _finite_or_none(value: Optional[float]) -> Optional[float]:
    return None if value is None or not math.isfinite(value) else float(value)


def status(*, drone_id: int, stamp: float, received_at: float, phase: int, health: int,
           faults: int, mission_sequence: int, command_sequence: int,
           position: Optional[Point], heading_deg: Optional[float],
           velocity_north: float, velocity_east: float,
           nearest_obstacle: Optional[float],
           sighting: Optional[Tuple[float, float, float, float]]) -> Dict[str, Any]:
    """
    Build a drone state message.

    ``sighting`` is (latitude, longitude, 1-sigma std in metres, stamp) or None; an
    infinite ``nearest_obstacle`` (nothing known) becomes None.
    """
    north = _finite_or_none(velocity_north)
    east = _finite_or_none(velocity_east)
    speed = math.hypot(north, east) if north is not None and east is not None else None
    return {
        'drone_id': int(drone_id),
        'stamp': float(stamp),
        'received_at': float(received_at),
        'phase': PHASES[phase],
        'health': HEALTH[health],
        'faults': fault_names(faults),
        'mission_sequence': int(mission_sequence),
        'command_sequence': int(command_sequence),
        'position': _point(*position) if position is not None else None,
        'heading_deg': _finite_or_none(heading_deg),
        'groundspeed_mps': speed,
        'velocity_north_mps': north,
        'velocity_east_mps': east,
        'nearest_obstacle_m': _finite_or_none(nearest_obstacle),
        'survivor_sighting': None if sighting is None else {
            'latitude': float(sighting[0]), 'longitude': float(sighting[1]),
            'std_m': float(sighting[2]), 'stamp': float(sighting[3])},
    }


def reply(sequence: Optional[int] = None, error: Optional[str] = None) -> Dict[str, Any]:
    """Build the answer to a request: the sequence published under, or why not."""
    return {'sequence': sequence, 'error': error}


def heartbeat(swarm: str, stamp: float, drones_heard: Sequence[int]) -> Dict[str, Any]:
    """Build the bridge's heartbeat."""
    return {'bridge_version': BRIDGE_VERSION, 'swarm': swarm, 'stamp': float(stamp),
            'drones_heard': sorted(int(i) for i in drones_heard)}


def _object(data: bytes, fields: Sequence[str]) -> Dict[str, Any]:
    try:
        message = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WireError(f'not JSON: {exc}') from exc
    if not isinstance(message, dict):
        raise WireError('expected a JSON object')
    unknown = sorted(set(message) - set(fields))
    missing = sorted(set(fields) - set(message))
    if unknown or missing:
        raise WireError(f'unknown fields {unknown}, missing fields {missing}')
    return message


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise WireError(f'{name} must be a finite number')
    return float(value)


def _points(value: Any, name: str) -> List[Point]:
    if not isinstance(value, list):
        raise WireError(f'{name} must be a list of points')
    points = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {'latitude', 'longitude'}:
            raise WireError(f'{name}: each point needs exactly latitude and longitude')
        points.append((_number(item['latitude'], f'{name} latitude'),
                       _number(item['longitude'], f'{name} longitude')))
    return points


def parse_command(data: bytes) -> Tuple[str, List[int]]:
    """Return (kind, drone ids) of a command request."""
    message = _object(data, ('kind', 'drone_ids'))
    kind = message['kind']
    if kind not in COMMANDS:
        raise WireError(f'kind must be one of {sorted(COMMANDS)}')
    ids = message['drone_ids']
    if not isinstance(ids, list) or not ids \
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise WireError('drone_ids must be a non-empty list of integers')
    return kind, ids


def parse_mission(data: bytes) -> Dict[str, Any]:
    """Return the fields of a mission request, with points as (latitude, longitude)."""
    message = _object(data, ('mission_id', 'origin', 'altitude_relative_m',
                             'grid_resolution_m', 'waypoints', 'area'))
    if not isinstance(message['mission_id'], str):
        raise WireError('mission_id must be text')
    [origin] = _points([message['origin']], 'origin')
    return {
        'mission_id': message['mission_id'],
        'origin': origin,
        'altitude_relative_m': _number(message['altitude_relative_m'], 'altitude_relative_m'),
        'grid_resolution_m': _number(message['grid_resolution_m'], 'grid_resolution_m'),
        'waypoints': _points(message['waypoints'], 'waypoints'),
        'area': _points(message['area'], 'area'),
    }
