"""
Launch-argument definitions and resolution (no ROS imports, so it is unit tested).

Every tunable launch argument is generated from ``DroneConfig``, so
``ros2 launch swarm_sar drone.launch.py --show-args`` always lists the same
defaults and descriptions the node uses. Resolution parses the string
arguments once, validates them by building the config, and returns plain,
correctly typed parameter dictionaries (so ``max_speed:=2`` can never reach
the node as an int where a float is declared).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from swarm_sar.core.config import (config_fields, config_from_text, config_to_parameters,
                                   ConfigError, DroneConfig, format_value, parse_bool,
                                   parse_text)
from swarm_sar.core.messages import MAX_DRONE_ID
from swarm_sar.ros.topics import px4_topic

LOG_LEVELS = ('debug', 'info', 'warn', 'error', 'fatal')


@dataclass(frozen=True)
class LaunchArgument:
    """One ``DeclareLaunchArgument``."""

    name: str
    default: str
    description: str


@dataclass(frozen=True)
class NodePlan:
    """Validated, typed result of resolving launch arguments for one node."""

    namespace: str
    log_level: str
    parameters: Dict[str, Any]


_COMMON = (
    LaunchArgument('use_sim_time', 'false', 'Use /clock instead of wall time'),
    LaunchArgument('log_level', 'info', f'Log level: {", ".join(LOG_LEVELS)}'),
)
_DRONE = (
    LaunchArgument('drone_id', '0', f'Unique id of this drone (0-{MAX_DRONE_ID})'),
    LaunchArgument('namespace', '', 'ROS namespace of the node (default: drone_<drone_id>)'),
    LaunchArgument('control_enabled', 'false',
                   'true: send setpoints to PX4; false: shadow mode (nothing is sent)'),
    LaunchArgument('px4_namespace', '', "Namespace of PX4's topics ('' or e.g. /px4_1)"),
    LaunchArgument('px4_system_id', '1', 'MAVLink system id of the flight controller'),
    LaunchArgument('depth_topic', 'camera/camera/depth/image_rect_raw', 'Depth image topic'),
    LaunchArgument('camera_info_topic', 'camera/camera/depth/camera_info',
                   'Camera info topic of the depth image'),
)
_MONITOR = (
    LaunchArgument('metrics_csv', '', 'Write metrics to this CSV file (empty: off)'),
    LaunchArgument('publish_period', '0.5', 'Metrics and visualisation period [s]'),
    LaunchArgument('report_period', '5.0', 'Log line and CSV row period [s]'),
)


def _config_arguments() -> Tuple[LaunchArgument, ...]:
    return tuple(LaunchArgument(spec.name, format_value(spec.default), spec.description)
                 for spec in config_fields(DroneConfig))


def drone_launch_arguments() -> Tuple[LaunchArgument, ...]:
    """Return every argument of ``drone.launch.py``."""
    return _DRONE + _COMMON + _config_arguments()


def monitor_launch_arguments() -> Tuple[LaunchArgument, ...]:
    """Return every argument of ``monitor.launch.py``."""
    return _MONITOR + _COMMON + _config_arguments()


def _defaults(arguments: Tuple[LaunchArgument, ...], raw: Mapping[str, str]) -> Dict[str, str]:
    values = {arg.name: arg.default for arg in arguments}
    values.update({k: v for k, v in raw.items() if k in values})
    return values


def _log_level(text: str) -> str:
    level = text.strip().lower()
    if level not in LOG_LEVELS:
        raise ConfigError(f'log_level must be one of {LOG_LEVELS}, got {text!r}')
    return level


def resolve_drone_arguments(raw: Mapping[str, str]) -> NodePlan:
    """Parse and validate ``drone.launch.py`` arguments; raise ``ConfigError`` on bad input."""
    values = _defaults(drone_launch_arguments(), raw)
    config = config_from_text(DroneConfig, values)
    drone_id = parse_text(int, values['drone_id'], 'drone_id')
    if not 0 <= drone_id <= MAX_DRONE_ID:
        raise ConfigError(f'drone_id must be in [0, {MAX_DRONE_ID}], got {drone_id}')
    system_id = parse_text(int, values['px4_system_id'], 'px4_system_id')
    if not 1 <= system_id <= 255:
        raise ConfigError(f'px4_system_id must be in [1, 255], got {system_id}')
    px4_namespace = values['px4_namespace'].strip()
    try:
        px4_topic(px4_namespace, 'fmu')
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    for name in ('depth_topic', 'camera_info_topic'):
        if not values[name].strip():
            raise ConfigError(f'{name} must not be empty')
    parameters: Dict[str, Any] = config_to_parameters(config)
    parameters.update({
        'drone_id': drone_id, 'px4_system_id': system_id, 'px4_namespace': px4_namespace,
        'control_enabled': parse_bool(values['control_enabled'], 'control_enabled'),
        'depth_topic': values['depth_topic'].strip(),
        'camera_info_topic': values['camera_info_topic'].strip(),
        'use_sim_time': parse_bool(values['use_sim_time'], 'use_sim_time')})
    namespace = values['namespace'].strip() or f'drone_{drone_id}'
    return NodePlan(namespace, _log_level(values['log_level']), parameters)


def resolve_monitor_arguments(raw: Mapping[str, str]) -> NodePlan:
    """Parse and validate ``monitor.launch.py`` arguments."""
    values = _defaults(monitor_launch_arguments(), raw)
    config = config_from_text(DroneConfig, values)
    parameters: Dict[str, Any] = config_to_parameters(config)
    for name in ('publish_period', 'report_period'):
        period = parse_text(float, values[name], name)
        if not period > 0.0:
            raise ConfigError(f'{name} must be positive, got {period}')
        parameters[name] = period
    parameters['metrics_csv'] = values['metrics_csv'].strip()
    parameters['use_sim_time'] = parse_bool(values['use_sim_time'], 'use_sim_time')
    return NodePlan('', _log_level(values['log_level']), parameters)
