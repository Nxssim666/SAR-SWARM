"""
Mission files: the operator's JSON description of what the swarm should do.

Positions are objects with explicit ``latitude``/``longitude`` keys rather
than bare pairs, because GeoJSON orders them ``[lon, lat]`` and most other
tools ``[lat, lon]``; a swapped pair is a silent, dangerous error (it moves
the area thousands of kilometres). Unknown keys are rejected so a typo such
as ``altitdue`` cannot silently fall back to a default.

The file is validated completely here, including the geometry checks the
drones will run, so a mission that would be rejected in the air is rejected
at the ground station instead.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.messages import MissionSpec
from swarm_sar.core.mission import build_mission_plan, MissionError

_REQUIRED = ('mission_id', 'origin', 'altitude', 'grid_resolution', 'area')
_OPTIONAL = ('waypoints',)
MAX_FILE_BYTES = 1_000_000

EXAMPLE: Dict[str, Any] = {
    'mission_id': 'example-forest-block',
    'origin': {'latitude': 47.397742, 'longitude': 8.545594},
    'altitude': 4.0,
    'grid_resolution': 5.0,
    'waypoints': [{'latitude': 47.397922, 'longitude': 8.545792},
                  {'latitude': 47.397742, 'longitude': 8.546058}],
    'area': [{'latitude': 47.397382, 'longitude': 8.545991},
             {'latitude': 47.397382, 'longitude': 8.547052},
             {'latitude': 47.398102, 'longitude': 8.547052},
             {'latitude': 47.398102, 'longitude': 8.545991}],
}


class MissionFileError(ValueError):
    """Raised when a mission file is malformed or describes an unflyable mission."""


def example_mission() -> str:
    """Return a commented-by-example mission file."""
    return json.dumps(EXAMPLE, indent=2) + '\n'


def parse_mission(text: str, sequence: int) -> MissionSpec:
    """Parse and fully validate a mission file; ``sequence`` orders it against earlier ones."""
    if len(text.encode('utf-8')) > MAX_FILE_BYTES:
        raise MissionFileError(f'mission file is larger than {MAX_FILE_BYTES} bytes')
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MissionFileError(f'not valid JSON: {exc}') from exc
    if not isinstance(data, dict):
        raise MissionFileError('the mission file must contain a JSON object')
    missing = [k for k in _REQUIRED if k not in data]
    unknown = sorted(set(data) - set(_REQUIRED) - set(_OPTIONAL))
    if missing:
        raise MissionFileError(f'missing keys: {", ".join(missing)}')
    if unknown:
        raise MissionFileError(f'unknown keys: {", ".join(unknown)}')
    try:
        spec = MissionSpec(
            sequence=sequence, mission_id=_text(data['mission_id'], 'mission_id'),
            origin=_point(data['origin'], 'origin'),
            altitude=_number(data['altitude'], 'altitude'),
            grid_resolution=_number(data['grid_resolution'], 'grid_resolution'),
            waypoints=_points(data.get('waypoints', []), 'waypoints'),
            area=_points(data['area'], 'area'))
        build_mission_plan(spec)
    except (MissionError, ValueError) as exc:
        raise MissionFileError(str(exc)) from exc
    return spec


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise MissionFileError(f'{name} must be a string')
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissionFileError(f'{name} must be a number')
    return float(value)


def _point(value: Any, name: str) -> GeoPoint:
    if not isinstance(value, dict) or set(value) != {'latitude', 'longitude'}:
        raise MissionFileError(f'{name} must be an object with exactly "latitude" and '
                               '"longitude"')
    return GeoPoint(_number(value['latitude'], f'{name}.latitude'),
                    _number(value['longitude'], f'{name}.longitude'))


def _points(value: Any, name: str) -> Tuple[GeoPoint, ...]:
    if not isinstance(value, list):
        raise MissionFileError(f'{name} must be a list of positions')
    out: List[GeoPoint] = [_point(item, f'{name}[{i}]') for i, item in enumerate(value)]
    return tuple(out)
