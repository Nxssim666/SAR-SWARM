"""
Validated configuration shared by the drone node, the simulator and the launch files.

Every tunable is declared exactly once, in the dataclasses below, with its
default, unit, help text and limits. ROS parameters, launch arguments and
the simulator CLI are generated from these dataclasses, so their defaults
cannot drift apart.

What to do (the area, the waypoints, the altitude, the grid) is *not*
configuration: it arrives at runtime in a mission from the ground station.
Configuration describes the vehicle, its sensors and the algorithms.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
import math
import numbers
import typing
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type, TypeVar

from swarm_sar.core.geometry import Bounds

MAX_DRONES = 1000
MAX_MAP_CELLS = 1_000_000

T = TypeVar('T', bound='ConfigBase')


class ConfigError(ValueError):
    """Raised when a configuration value is missing, malformed or out of range."""


def _param(default: Any, help_text: str, *, unit: str = '', gt: Optional[float] = None,
           ge: Optional[float] = None, lt: Optional[float] = None,
           le: Optional[float] = None, choices: Tuple[str, ...] = ()) -> Any:
    return field(default=default, metadata={
        'help': help_text, 'unit': unit, 'gt': gt, 'ge': ge, 'lt': lt, 'le': le,
        'choices': choices})


@dataclass(frozen=True)
class FieldSpec:
    """Public description of one configuration field."""

    name: str
    field_type: Any
    default: Any
    help_text: str
    unit: str

    @property
    def description(self) -> str:
        """Return the help text with its unit, for parameter/argument descriptions."""
        return f'{self.help_text} [{self.unit}]' if self.unit else self.help_text


class ConfigBase:
    """Coerce and validate every field of a frozen config dataclass on construction."""

    def __post_init__(self) -> None:
        hints = typing.get_type_hints(type(self))
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            value = coerce_value(hints[f.name], getattr(self, f.name), f.name)
            _check_limits(f, value)
            object.__setattr__(self, f.name, value)
        self._validate()

    def _validate(self) -> None:
        """Cross-field checks; override in subclasses."""

    def warnings(self) -> List[str]:
        """Return advisory messages for legal-but-questionable settings."""
        return []


def braking_limited_speed(distance: float, deceleration: float, reaction_time: float) -> float:
    """Return the speed from which a vehicle can still stop within ``distance``."""
    d = max(distance, 0.0)
    return deceleration * (math.sqrt(reaction_time ** 2 + 2.0 * d / deceleration)
                           - reaction_time)


@dataclass(frozen=True)
class DroneConfig(ConfigBase):
    """Everything one drone needs to fly; missions arrive separately at runtime."""

    # -- flight envelope ----------------------------------------------------
    control_period: float = _param(0.1, 'Control loop and setpoint period', unit='s', gt=0,
                                   le=0.25)
    max_speed: float = _param(3.0, 'Maximum horizontal speed command', unit='m/s', gt=0, le=15)
    max_accel: float = _param(
        2.0, 'Deceleration the vehicle can always achieve; also the speed-up limit',
        unit='m/s^2', gt=0)
    reaction_time: float = _param(
        0.6, 'Worst case from an obstacle entering the depth image to braking starting',
        unit='s', gt=0)
    approach_gain: float = _param(0.8, 'Proportional gain toward goals', unit='1/s', gt=0)
    altitude_tolerance: float = _param(
        0.5, 'Horizontal motion waits until the altitude error is below this', unit='m', gt=0)
    max_altitude_correction: float = _param(
        2.0, 'Largest altitude change made without the pilot (the camera cannot see '
        'above or below)', unit='m', gt=0)
    min_altitude: float = _param(2.0, 'Lowest mission altitude accepted', unit='m', gt=0)
    max_altitude: float = _param(60.0, 'Highest mission altitude accepted', unit='m', gt=0)
    geofence_radius: float = _param(
        1000.0, 'Missions must lie within this distance of home; the drone holds beyond it',
        unit='m', gt=0)
    # -- depth perception -----------------------------------------------------
    camera_offset: Tuple[float, float, float] = _param(
        (0.1, 0.0, 0.0), 'Camera position in the body frame [forward, right, down]', unit='m')
    camera_rpy_deg: Tuple[float, float, float] = _param(
        (0.0, 0.0, 0.0), 'Camera mount roll, pitch (positive up), yaw (positive right)',
        unit='deg')
    depth_stride: int = _param(4, 'Use every n-th depth pixel in each direction', ge=1, le=32)
    depth_trusted_range: float = _param(8.0, 'Depth returns are trusted up to this range',
                                        unit='m', gt=0, le=40)
    band_above: float = _param(1.0, 'Obstacle band above the vehicle centre', unit='m', gt=0)
    band_below: float = _param(1.0, 'Obstacle band below the vehicle centre', unit='m', gt=0)
    bearing_bin_deg: float = _param(1.0, 'Angular resolution of free-space evidence',
                                    unit='deg', gt=0, le=10)
    max_depth_age: float = _param(0.25, 'Reject depth frames older than this on arrival',
                                  unit='s', gt=0)
    min_valid_depth_fraction: float = _param(
        0.05, 'Below this share of valid depth pixels the camera counts as blind', ge=0, lt=1)
    # -- obstacle map and local planner ------------------------------------
    obstacle_clearance: float = _param(
        0.8, 'Distance kept between the vehicle centre and obstacles or unobserved space',
        unit='m', gt=0)
    self_clear_radius: float = _param(
        1.4, 'Unobserved space this close to where the vehicle stood still is assumed free '
        '(a forward camera cannot see its own surroundings)', unit='m', gt=0)
    map_resolution: float = _param(0.2, 'Obstacle map cell size', unit='m', gt=0)
    map_size: float = _param(30.0, 'Side of the vehicle-centred obstacle map', unit='m', gt=0)
    map_memory: float = _param(5.0, 'How long observed free space stays trusted', unit='s',
                               gt=0)
    planning_directions: int = _param(72, 'Candidate travel directions evaluated per tick',
                                      ge=8, le=720)
    yaw_follow_speed: float = _param(
        0.5, 'Above this speed the camera is turned toward the direction of travel',
        unit='m/s', gt=0)
    min_progress_speed: float = _param(
        0.2, 'Slower progress toward the goal counts as blocked (turn to look instead)',
        unit='m/s', ge=0)
    min_separation: float = _param(3.0, 'Distance collision avoidance keeps between drones',
                                   unit='m', ge=0)
    lost_peer_memory: float = _param(
        60.0, 'A peer that falls silent is still avoided at its last position this long '
        '(a silent drone holds where it was: see hold_on_radio_silence)', unit='s', ge=0)
    # -- mission execution -----------------------------------------------------
    waypoint_radius: float = _param(
        8.0, 'Distance at which a transit waypoint is reached (generous: many drones share it)',
        unit='m', gt=0)
    detection_range: float = _param(
        10.0, "Ground radius covered by the search detector's field of view", unit='m', gt=0)
    arrival_radius: float = _param(3.0, 'Distance at which a search goal counts as reached',
                                   unit='m', gt=0)
    revisit_period: float = _param(180.0, 'Time for a searched cell to become fully stale',
                                   unit='s', gt=0)
    search_distance_scale: float = _param(40.0, 'Distance discount when choosing search goals',
                                          unit='m', gt=0)
    goal_switch_ratio: float = _param(
        1.5, 'Abandon the current search goal only for one scoring this many times better',
        ge=1)
    stuck_timeout: float = _param(15.0, 'Give up on a goal after this long without progress',
                                  unit='s', gt=0)
    stuck_min_progress: float = _param(1.0, 'Progress toward a goal that resets the stuck timer',
                                       unit='m', gt=0)
    unreachable_goal_cooldown: float = _param(
        60.0, 'An unreachable search goal is not retried for this long', unit='s', ge=0)
    # -- swarm communication -------------------------------------------------
    state_broadcast_period: float = _param(0.2, 'Period of the status broadcast', unit='s',
                                           gt=0)
    coverage_broadcast_period: float = _param(1.0, 'Period of coverage updates', unit='s',
                                              gt=0)
    coverage_recent_window: float = _param(
        5.0, 'Coverage updates repeat cells observed within this window', unit='s', gt=0)
    coverage_full_period: float = _param(
        20.0, 'Period of full coverage snapshots (repairs lost updates)', unit='s', gt=0)
    peer_timeout: float = _param(1.5, 'A peer not heard from for this long counts as lost',
                                 unit='s', gt=0)
    max_clock_skew: float = _param(
        0.5, 'Tolerated clock offset between nodes; larger future stamps are rejected',
        unit='s', ge=0)
    command_max_age: float = _param(30.0, 'Operator commands older than this are ignored',
                                    unit='s', gt=0)
    hold_on_radio_silence: bool = _param(
        True, 'Hold when peers heard during the mission all fall silent: the own radio has '
        'probably failed and other drones can no longer be avoided')
    # -- target tracking ---------------------------------------------------------
    num_trackers: int = _param(2, 'How many of the nearest drones converge on a found target',
                               ge=1)
    recruit_radius: float = _param(30.0, 'Only drones this close to the estimate may track',
                                   unit='m', gt=0)
    track_standoff: float = _param(6.0, 'Radius of the ring trackers hold around the target',
                                   unit='m', gt=0)
    target_max_speed: float = _param(2.0, 'Upper bound on target speed assumed by the tracker',
                                     unit='m/s', gt=0)
    target_accel_psd: float = _param(0.3, 'Target acceleration noise density (CV model)',
                                     unit='m^2/s^3', gt=0)
    track_drop_std: float = _param(15.0, 'Drop a track whose position 1-sigma exceeds this',
                                   unit='m', gt=0)
    max_detection_age: float = _param(1.0, 'Ignore detections older than this', unit='s', gt=0)
    min_detection_confidence: float = _param(0.5, 'Ignore detections scored below this',
                                             ge=0, le=1)
    datum_ttl: float = _param(90.0, 'How long a lost target keeps biasing the search',
                              unit='s', ge=0)
    datum_gain: float = _param(4.0, 'Extra search weight near the last known position', ge=0)
    # -- safety supervisor -------------------------------------------------------
    pose_timeout: float = _param(0.3, 'Pose older than this is unusable', unit='s', gt=0)
    fc_timeout: float = _param(
        2.0, 'Flight-controller status older than this means link lost (PX4 sends it at a few '
        'Hz, on a lossy serial link some are dropped)', unit='s', gt=0)
    depth_timeout: float = _param(0.5, 'No processed depth frame for this long stops motion',
                                  unit='s', gt=0)
    degraded_escalation_time: float = _param(
        10.0, 'Hand the vehicle to the flight controller (Hold) after this long unable to move',
        unit='s', gt=0)
    fc_request_period: float = _param(1.0, 'Resend interval for flight-mode requests',
                                      unit='s', gt=0)

    def _validate(self) -> None:
        if self.min_altitude >= self.max_altitude:
            raise ConfigError('min_altitude must be below max_altitude')
        if self.reaction_time < self.control_period:
            raise ConfigError('reaction_time must include at least one control_period')
        if self.pose_timeout <= self.control_period or self.fc_timeout <= self.control_period:
            raise ConfigError('pose_timeout and fc_timeout must exceed control_period')
        if self.depth_timeout < self.max_depth_age:
            raise ConfigError('depth_timeout must be at least max_depth_age')
        down = self.camera_offset[2]
        if not -self.band_above < down < self.band_below:
            raise ConfigError('the camera must sit inside the obstacle band '
                              '(camera_offset[2] between -band_above and band_below)')
        if self.self_clear_radius < self.obstacle_clearance:
            raise ConfigError('self_clear_radius must be at least obstacle_clearance, otherwise '
                              'the vehicle can never leave its own position')
        if self.map_resolution > self.obstacle_clearance / 2.0:
            raise ConfigError('map_resolution must be at most half of obstacle_clearance')
        lookahead = self.depth_trusted_range + self.obstacle_clearance + self.map_resolution
        if self.map_size < 8.0 / 3.0 * lookahead:
            raise ConfigError(f'map_size must be at least {8.0 / 3.0 * lookahead:.1f} m so the '
                              'planning window stays inside the map between re-centrings')
        cells = math.ceil(self.map_size / self.map_resolution) ** 2
        if cells > MAX_MAP_CELLS:
            raise ConfigError(f'obstacle map would have {cells} cells (limit {MAX_MAP_CELLS})')
        if self.track_standoff >= self.detection_range:
            raise ConfigError('track_standoff must be smaller than detection_range, otherwise '
                              'trackers hold a ring from which they cannot see the target')
        if self.recruit_radius < self.track_standoff:
            raise ConfigError('recruit_radius must be at least track_standoff')
        if self.arrival_radius >= self.detection_range:
            raise ConfigError('arrival_radius must be smaller than detection_range')
        if self.peer_timeout <= 2.0 * self.state_broadcast_period:
            raise ConfigError('peer_timeout must exceed two state broadcast periods')
        if self.coverage_recent_window < self.coverage_broadcast_period:
            raise ConfigError('coverage_recent_window must cover at least one broadcast period')
        if abs(math.radians(self.camera_rpy_deg[1])) >= math.pi / 2.0:
            raise ConfigError('camera pitch must be within +-90 degrees')

    def warnings(self) -> List[str]:
        """Return advisory messages for settings that work but degrade behaviour."""
        notes = []
        reachable = braking_limited_speed(self.depth_trusted_range - self.obstacle_clearance,
                                          self.max_accel, self.reaction_time)
        if self.max_speed > reachable:
            notes.append(f'max_speed {self.max_speed} m/s exceeds what the trusted depth range '
                         f'allows; effective limit is {reachable:.1f} m/s')
        if self.target_max_speed >= self.max_speed:
            notes.append('target_max_speed >= max_speed: drones cannot keep up with a target '
                         'moving at the assumed maximum speed')
        if self.self_clear_radius > 3.0:
            notes.append('self_clear_radius above 3 m assumes a lot of unobserved space is free')
        if self.coverage_broadcast_period > self.revisit_period / 4.0:
            notes.append('coverage_broadcast_period is long relative to revisit_period; '
                         "drones will duplicate each other's search effort")
        return notes


@dataclass(frozen=True)
class SimConfig(ConfigBase):
    """The simulated world used by the standalone simulator and the closed-loop tests."""

    origin_latitude: float = _param(47.397742, 'Mission origin latitude (PX4 SITL default)',
                                    unit='deg', ge=-85, le=85)
    origin_longitude: float = _param(8.545594, 'Mission origin longitude (PX4 SITL default)',
                                     unit='deg', ge=-180, le=180)
    area_size: float = _param(80.0, 'Side of the square search area', unit='m', gt=0, le=2000)
    transit_distance: float = _param(30.0, 'Distance from the launch site to the area',
                                     unit='m', ge=0, le=1000)
    altitude: float = _param(4.0, 'Mission altitude above home', unit='m', gt=0)
    grid_resolution: float = _param(5.0, 'Coverage grid cell size sent with the mission',
                                    unit='m', gt=0)
    tree_density: float = _param(80.0, 'Trees per hectare', unit='1/ha', ge=0, le=2000)
    tree_radius: Tuple[float, float] = _param((0.15, 0.4), 'Trunk radius range [min, max]',
                                              unit='m')
    clearing_radius: float = _param(10.0, 'Tree-free radius around the launch site', unit='m',
                                    ge=0)
    target_speed: float = _param(0.8, 'Target walking speed', unit='m/s', ge=0)
    detection_noise_std: float = _param(1.0, 'Search detector position noise (1-sigma)',
                                        unit='m', ge=0)
    detection_probability: float = _param(0.8, 'Chance a visible target is reported per tick',
                                          gt=0, le=1)
    camera_width: int = _param(96, 'Synthetic depth image width', ge=8, le=1280)
    camera_height: int = _param(54, 'Synthetic depth image height', ge=8, le=960)
    camera_hfov_deg: float = _param(87.0, 'Synthetic depth camera horizontal field of view',
                                    unit='deg', gt=10, lt=170)
    camera_max_range: float = _param(12.0, 'Synthetic depth camera maximum range', unit='m',
                                     gt=0)
    depth_noise: float = _param(0.01, 'Depth noise, relative to range', ge=0, le=0.2)
    depth_dropout: float = _param(0.02, 'Share of pixels randomly returned invalid', ge=0, lt=1)
    radio_range: float = _param(120.0, 'Simulated radio range', unit='m', gt=0)
    packet_loss: float = _param(0.0, 'Probability an in-range message is lost', ge=0, lt=1)
    drone_radius: float = _param(0.3, 'Physical radius of a drone (collision checks)',
                                 unit='m', gt=0)
    vehicle_max_accel: float = _param(3.0, 'Simulated vehicle acceleration limit',
                                      unit='m/s^2', gt=0)
    vehicle_yaw_rate_deg: float = _param(60.0, 'Simulated vehicle yaw rate limit',
                                         unit='deg/s', gt=0)
    vehicle_climb_rate: float = _param(1.5, 'Simulated vehicle vertical speed limit',
                                       unit='m/s', gt=0)
    spawn_spacing: float = _param(4.0, 'Distance between drones at the launch site',
                                  unit='m', gt=0)

    def _validate(self) -> None:
        low, high = self.tree_radius
        if not 0.0 < low <= high:
            raise ConfigError('tree_radius must be [min, max] with 0 < min <= max')
        if self.grid_resolution > self.area_size / 2.0:
            raise ConfigError('grid_resolution must be at most half the area size')


# ---------------------------------------------------------------------------
# generic helpers used by the ROS layer, the launch files and the CLI
# ---------------------------------------------------------------------------

def config_fields(cls: Type[ConfigBase]) -> List[FieldSpec]:
    """Describe the fields of a config dataclass."""
    hints = typing.get_type_hints(cls)
    specs = []
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        specs.append(FieldSpec(f.name, hints[f.name], f.default, f.metadata['help'],
                               f.metadata['unit']))
    return specs


def config_from_mapping(cls: Type[T], values: Mapping[str, Any]) -> T:
    """Build ``cls`` from a mapping, ignoring keys that are not fields of ``cls``."""
    names = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
    try:
        return cls(**{k: v for k, v in values.items() if k in names})
    except ConfigError:
        raise
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def config_from_text(cls: Type[T], values: Mapping[str, str]) -> T:
    """Build ``cls`` from string values (launch arguments, CLI flags)."""
    hints = typing.get_type_hints(cls)
    parsed = {}
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        if f.name in values:
            parsed[f.name] = parse_text(hints[f.name], values[f.name], f.name)
    return config_from_mapping(cls, parsed)


def config_to_parameters(config: ConfigBase) -> Dict[str, Any]:
    """Return plain ROS-parameter-compatible values (float, int, bool, str, list[float])."""
    return {f.name: to_parameter_value(getattr(config, f.name))
            for f in dataclasses.fields(config)}  # type: ignore[arg-type]


def to_parameter_value(value: Any) -> Any:
    """Convert a config value to a ROS parameter value."""
    if isinstance(value, Bounds):
        return list(value.as_tuple())
    if isinstance(value, tuple):
        return [float(v) for v in value]
    return value


def format_value(value: Any) -> str:
    """Format a config value as text that ``parse_text`` reads back unchanged."""
    value = to_parameter_value(value)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, list):
        return '[' + ', '.join(repr(float(v)) for v in value) + ']'
    if isinstance(value, float):
        return repr(value)
    return str(value)


def parse_text(tp: Any, text: str, name: str) -> Any:
    """Parse a string into a value of type ``tp`` without ever evaluating code."""
    if not isinstance(text, str):
        raise ConfigError(f'{name}: expected text, got {text!r}')
    stripped = text.strip()
    try:
        if tp is bool:
            return parse_bool(stripped, name)
        if tp is str:
            return stripped
        if tp is float:
            return float(stripped)
        if tp is int:
            number = float(stripped)
            if not number.is_integer():
                raise ValueError(f'{stripped!r} is not an integer')
            return int(number)
        if tp is Bounds or typing.get_origin(tp) is tuple:
            return parse_number_list(stripped)
    except ValueError as exc:
        raise ConfigError(f'{name}: cannot parse {text!r}: {exc}') from exc
    raise ConfigError(f'{name}: unsupported type {tp!r}')


def parse_bool(text: str, name: str) -> bool:
    """Parse common spellings of a boolean."""
    lowered = text.strip().lower()
    if lowered in ('true', '1', 'yes', 'on'):
        return True
    if lowered in ('false', '0', 'no', 'off'):
        return False
    raise ConfigError(f'{name}: expected true/false, got {text!r}')


def parse_number_list(text: str) -> List[float]:
    """Parse ``'[1, 2, 3]'``, ``'1,2,3'`` or ``'1 2 3'`` into floats."""
    body = text.strip()
    if body[:1] in '[(' and body[-1:] in '])':
        body = body[1:-1]
    parts = [p for p in body.replace(',', ' ').split() if p]
    if not parts:
        raise ValueError('empty list')
    return [float(p) for p in parts]


def coerce_value(tp: Any, value: Any, name: str) -> Any:
    """Coerce ``value`` to type ``tp``, accepting only lossless conversions."""
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ConfigError(f'{name} must be a number, got {value!r}')
        result = float(value)
        if not math.isfinite(result):
            raise ConfigError(f'{name} must be finite, got {value!r}')
        return result
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ConfigError(f'{name} must be an integer, got {value!r}')
        if isinstance(value, numbers.Integral):
            return int(value)
        as_float = float(value)
        if math.isfinite(as_float) and as_float.is_integer():
            return int(as_float)
        raise ConfigError(f'{name} must be an integer, got {value!r}')
    if tp is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return parse_bool(value, name)
        raise ConfigError(f'{name} must be true or false, got {value!r}')
    if tp is str:
        if not isinstance(value, str):
            raise ConfigError(f'{name} must be a string, got {value!r}')
        return value
    if tp is Bounds:
        if isinstance(value, Bounds):
            return value
        try:
            return Bounds.from_sequence(value)
        except ValueError as exc:
            raise ConfigError(f'{name}: {exc}') from exc
    if typing.get_origin(tp) is tuple:
        items = typing.get_args(tp)
        if isinstance(value, (str, bytes)):
            raise ConfigError(f'{name} must be a sequence, got {value!r}')
        try:
            seq = list(value)
        except TypeError as exc:
            raise ConfigError(f'{name} must be a sequence, got {value!r}') from exc
        if len(seq) != len(items):
            raise ConfigError(f'{name} needs {len(items)} values, got {len(seq)}')
        return tuple(coerce_value(t, v, f'{name}[{i}]')
                     for i, (t, v) in enumerate(zip(items, seq)))
    raise ConfigError(f'{name}: unsupported type {tp!r}')


def _check_limits(f: 'dataclasses.Field[Any]', value: Any) -> None:
    meta = f.metadata
    if meta.get('choices') and value not in meta['choices']:
        raise ConfigError(f'{f.name} must be one of {meta["choices"]}, got {value!r}')
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return
    if meta.get('gt') is not None and not value > meta['gt']:
        raise ConfigError(f'{f.name} must be > {meta["gt"]}, got {value}')
    if meta.get('ge') is not None and not value >= meta['ge']:
        raise ConfigError(f'{f.name} must be >= {meta["ge"]}, got {value}')
    if meta.get('lt') is not None and not value < meta['lt']:
        raise ConfigError(f'{f.name} must be < {meta["lt"]}, got {value}')
    if meta.get('le') is not None and not value <= meta['le']:
        raise ConfigError(f'{f.name} must be <= {meta["le"]}, got {value}')
