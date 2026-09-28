"""rclpy helpers shared by the nodes: QoS, parameters, time, error containment, main()."""

from __future__ import annotations

import array
import functools
import traceback
from typing import Any, Callable, List, Optional, Type, TypeVar

from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.logging import get_logger
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from swarm_sar.core.config import (coerce_value, config_fields, config_from_mapping, ConfigBase,
                                   ConfigError, to_parameter_value)

T = TypeVar('T', bound=ConfigBase)

DEFAULT_BROADCAST_DEPTH = 64
_ERROR_THROTTLE_S = 5.0


def broadcast_qos(depth: int) -> QoSProfile:
    """
    Return the QoS for the shared swarm channels (radio-like: best effort, volatile).

    Lost packets are expected and handled by the protocol (periodic
    re-broadcast, idempotent merges); retransmission would only add latency.
    """
    return QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=depth,
                      reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


def reliable_qos(depth: int = 10) -> QoSProfile:
    """Return a reliable, volatile QoS for low-rate point-to-point topics."""
    return QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=depth,
                      reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.VOLATILE)


def latched_qos() -> QoSProfile:
    """
    Return a reliable, transient-local QoS (depth 1).

    Used for missions and operator commands, so a drone that (re)starts
    late still receives the latest one, and for visualisation outputs, which
    then match RViz2 displays of either durability.
    """
    return QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                      reliability=ReliabilityPolicy.RELIABLE,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)


def px4_qos() -> QoSProfile:
    """Return the QoS PX4's uXRCE-DDS bridge expects (as in PX4's ROS 2 examples)."""
    return QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                      reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.TRANSIENT_LOCAL)


def sensor_qos(depth: int = 2) -> QoSProfile:
    """Return the usual sensor-data QoS (best effort, newest frames only)."""
    return QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=depth,
                      reliability=ReliabilityPolicy.BEST_EFFORT,
                      durability=DurabilityPolicy.VOLATILE)


def now_seconds(node: Node) -> float:
    """Return the node clock (ROS time; simulated when use_sim_time is true) in seconds."""
    return node.get_clock().now().nanoseconds / 1e9


def declare_config(node: Node, cls: Type[T]) -> T:
    """Declare every field of ``cls`` as a read-only parameter and build a validated config."""
    values = {}
    for spec in config_fields(cls):
        values[spec.name] = declare_value(node, spec.name, to_parameter_value(spec.default),
                                          spec.description)
    return config_from_mapping(cls, values)


def declare_value(node: Node, name: str, default: Any, description: str) -> Any:
    """
    Declare one read-only, dynamically typed parameter and return its value.

    Dynamic typing lets ``speed:=5`` (an int) satisfy a float parameter;
    the config dataclasses then coerce and validate the value, with a clear
    error message instead of an ``InvalidParameterTypeException`` at start-up.
    """
    descriptor = ParameterDescriptor(description=description, dynamic_typing=True,
                                     read_only=True)
    node.declare_parameter(name, default, descriptor)
    value = node.get_parameter(name).value
    return list(value) if isinstance(value, array.array) else value


def declare_int(node: Node, name: str, default: int, description: str, minimum: int,
                maximum: Optional[int] = None) -> int:
    """Declare an integer parameter and check its range."""
    value = coerce_value(int, declare_value(node, name, default, description), name)
    if value < minimum or (maximum is not None and value > maximum):
        raise ConfigError(f'{name} must be in [{minimum}, {maximum}], got {value}')
    return value


def declare_float(node: Node, name: str, default: float, description: str,
                  minimum: float) -> float:
    """Declare a float parameter that must be strictly greater than ``minimum``."""
    value = coerce_value(float, declare_value(node, name, default, description), name)
    if not value > minimum:
        raise ConfigError(f'{name} must be > {minimum}, got {value}')
    return value


def declare_bool(node: Node, name: str, default: bool, description: str) -> bool:
    """Declare a boolean parameter."""
    return coerce_value(bool, declare_value(node, name, default, description), name)


def declare_text(node: Node, name: str, default: str, description: str) -> str:
    """Declare a string parameter."""
    return coerce_value(str, declare_value(node, name, default, description), name)


def guarded(node: Node, name: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Wrap a callback so an unexpected exception is logged instead of killing the node."""
    def decorate(callback: Callable[..., None]) -> Callable[..., None]:
        @functools.wraps(callback)
        def wrapper(*args: Any) -> None:
            try:
                callback(*args)
            except Exception:  # noqa: B902 - contain the failure, keep the node alive
                node.get_logger().error(f'{name} failed:\n{traceback.format_exc()}',
                                        throttle_duration_sec=_ERROR_THROTTLE_S)
        return wrapper
    return decorate


def run_node(factory: Callable[[], Node], args: Optional[List[str]] = None) -> int:
    """
    Initialise rclpy, spin the node built by ``factory`` and shut down cleanly.

    Returns a process exit code: 0 on normal shutdown, 2 on invalid
    configuration (reported once, at FATAL level, with the reason).
    """
    rclpy.init(args=args)
    node = None
    try:
        node = factory()
        rclpy.spin(node)
        return 0
    except ConfigError as exc:
        get_logger('swarm_sar').fatal(f'invalid configuration: {exc}')
        return 2
    except (KeyboardInterrupt, ExternalShutdownException):
        return 0
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
