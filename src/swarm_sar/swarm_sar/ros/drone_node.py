"""
The drone node: runs ``DroneController`` on a companion computer and does all of its I/O.

One process per drone, next to the flight controller:

* PX4 (uXRCE-DDS): local position, attitude and status in; offboard
  heartbeat, trajectory setpoints and mode requests out.
* Depth camera: ``sensor_msgs/Image`` + ``CameraInfo`` in (e.g. the
  ``realsense2_camera`` driver).
* Swarm radio (shared DDS topics over the mesh network): status and
  coverage in and out; missions and operator commands in.
* Onboard search detector: georeferenced ``TargetReport`` in.

``control_enabled`` is the rollout switch. While false (the default) the
node runs everything but sends nothing to PX4 ("shadow mode"): the exact
setpoints it would send are published on ``~/shadow/trajectory_setpoint``
so they can be checked during manual flights before the companion is ever
given control.

The controller is not thread-safe. ``run_node`` spins the node on rclpy's
single-threaded executor, which serializes every callback; do not add the
node to a multi-threaded executor.
"""

from __future__ import annotations

from collections import Counter
import time
from typing import Any, List, Optional, Sequence

from rclpy.node import Node
from swarm_sar.core.config import ConfigError, DroneConfig
from swarm_sar.core.controller import (CAMERA_WARNING, ControllerEvent, DepthOutcome,
                                       DISENGAGED, DroneController, ENGAGED, FAULTS_CHANGED,
                                       FC_REQUESTED, FRAME_RESET, GOAL_UNREACHABLE,
                                       MISSION_ACCEPTED, MISSION_REJECTED, PHASE_CHANGED,
                                       WAYPOINT_UNREACHABLE)
from swarm_sar.core.depth import CameraIntrinsics, DepthFrame
from swarm_sar.core.messages import MAX_DRONE_ID
from swarm_sar.ros import px4
from swarm_sar.ros.codec import Codec, MessageTypes, MessageValidationError, time_to_seconds
from swarm_sar.ros.sensors import decode_camera_info, decode_depth_image, SensorTypes
from swarm_sar.ros.topics import (COMMAND_TOPIC, COVERAGE_TOPIC, MISSION_TOPIC, PX4_ATTITUDE,
                                  PX4_LOCAL_POSITION, PX4_OFFBOARD_MODE, PX4_STATUS, px4_topic,
                                  PX4_TRAJECTORY_SETPOINT, PX4_VEHICLE_COMMAND,
                                  SHADOW_SETPOINT_TOPIC, STATUS_TOPIC, TARGET_REPORT_TOPIC)
from swarm_sar.ros.util import (broadcast_qos, declare_bool, declare_config, declare_int,
                                declare_text, DEFAULT_BROADCAST_DEPTH, guarded, latched_qos,
                                now_seconds, px4_qos, reliable_qos, run_node, sensor_qos)

DIAGNOSTICS_PERIOD_S = 10.0
_WARN_EVENTS = (MISSION_REJECTED, WAYPOINT_UNREACHABLE, FRAME_RESET, FC_REQUESTED,
                CAMERA_WARNING, FAULTS_CHANGED)
_INFO_EVENTS = (PHASE_CHANGED, ENGAGED, DISENGAGED, MISSION_ACCEPTED, GOAL_UNREACHABLE)


class DroneNode(Node):
    """ROS 2 I/O around one ``DroneController``."""

    def __init__(self, **node_kwargs: Any) -> None:
        super().__init__('drone', **node_kwargs)
        self._cfg = declare_config(self, DroneConfig)
        drone_id = declare_int(self, 'drone_id', -1, 'Unique id of this drone in the swarm', 0,
                               MAX_DRONE_ID)
        px4_namespace = declare_text(self, 'px4_namespace', '',
                                     "Namespace of PX4's uXRCE-DDS topics ('' or e.g. /px4_1)")
        system_id = declare_int(self, 'px4_system_id', 1,
                                'MAVLink system id of the flight controller (MAV_SYS_ID)', 1, 255)
        self._control_enabled = declare_bool(
            self, 'control_enabled', False,
            'Send setpoints and mode requests to PX4 (false: shadow mode, nothing is sent)')
        depth_topic = declare_text(self, 'depth_topic', 'camera/camera/depth/image_rect_raw',
                                   'Depth image topic (16UC1 millimetres or 32FC1 metres)')
        info_topic = declare_text(self, 'camera_info_topic', 'camera/camera/depth/camera_info',
                                  'Camera info topic matching the depth image')
        depth = declare_int(self, 'swarm_qos_depth', DEFAULT_BROADCAST_DEPTH,
                            'History depth of the shared swarm channels', 1, 10_000)
        if not depth_topic or not info_topic:
            raise ConfigError('depth_topic and camera_info_topic must not be empty')
        try:
            topic = {name: px4_topic(px4_namespace, name) for name in (
                PX4_LOCAL_POSITION, PX4_ATTITUDE, PX4_STATUS, PX4_OFFBOARD_MODE,
                PX4_TRAJECTORY_SETPOINT, PX4_VEHICLE_COMMAND)}
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        for note in self._cfg.warnings():
            self.get_logger().warning(note)

        self._system_id = system_id
        self._types = MessageTypes.load()
        self._px4 = px4.Px4Types.load()
        sensors = SensorTypes.load()
        self._codec = Codec(self._types)
        self._controller = DroneController(drone_id, self._cfg)
        self._intrinsics: Optional[CameraIntrinsics] = None
        self._counts: Counter = Counter()
        self._last_tick_start: Optional[float] = None
        self._last_tick_duration = 0.0
        self._slow_ticks = 0

        fc = px4_qos()
        self.create_subscription(self._px4.VehicleLocalPosition, topic[PX4_LOCAL_POSITION],
                                 guarded(self, 'local position')(self._on_local_position), fc)
        self.create_subscription(self._px4.VehicleAttitude, topic[PX4_ATTITUDE],
                                 guarded(self, 'attitude')(self._on_attitude), fc)
        self.create_subscription(self._px4.VehicleStatus, topic[PX4_STATUS],
                                 guarded(self, 'vehicle status')(self._on_vehicle_status), fc)
        self.create_subscription(sensors.CameraInfo, info_topic,
                                 guarded(self, 'camera info')(self._on_camera_info),
                                 sensor_qos())
        self.create_subscription(sensors.Image, depth_topic,
                                 guarded(self, 'depth image')(self._on_depth), sensor_qos())
        swarm = broadcast_qos(depth)
        self.create_subscription(self._types.DroneState, STATUS_TOPIC,
                                 guarded(self, 'peer status')(self._on_status), swarm)
        self.create_subscription(self._types.CoverageUpdate, COVERAGE_TOPIC,
                                 guarded(self, 'coverage')(self._on_coverage), swarm)
        self.create_subscription(self._types.Mission, MISSION_TOPIC,
                                 guarded(self, 'mission')(self._on_mission), latched_qos())
        self.create_subscription(self._types.SwarmCommand, COMMAND_TOPIC,
                                 guarded(self, 'command')(self._on_command), latched_qos())
        self.create_subscription(self._types.TargetReport, TARGET_REPORT_TOPIC,
                                 guarded(self, 'target report')(self._on_target_report),
                                 reliable_qos())

        self._status_pub = self.create_publisher(self._types.DroneState, STATUS_TOPIC, swarm)
        self._coverage_pub = self.create_publisher(self._types.CoverageUpdate, COVERAGE_TOPIC,
                                                   swarm)
        if self._control_enabled:
            self._offboard_pub = self.create_publisher(self._px4.OffboardControlMode,
                                                       topic[PX4_OFFBOARD_MODE], fc)
            self._setpoint_pub = self.create_publisher(self._px4.TrajectorySetpoint,
                                                       topic[PX4_TRAJECTORY_SETPOINT], fc)
            self._command_pub = self.create_publisher(self._px4.VehicleCommand,
                                                      topic[PX4_VEHICLE_COMMAND], fc)
        else:
            self._shadow_pub = self.create_publisher(self._px4.TrajectorySetpoint,
                                                     SHADOW_SETPOINT_TOPIC, reliable_qos())
        self.create_timer(self._cfg.control_period, guarded(self, 'control tick')(self._tick))
        self.create_timer(DIAGNOSTICS_PERIOD_S, guarded(self, 'diagnostics')(self._diagnostics))
        mode = 'CONTROL ENABLED' if self._control_enabled else 'shadow mode (no PX4 output)'
        self.get_logger().info(f'drone {drone_id}: {mode}; PX4 under {topic[PX4_STATUS]!r}, '
                               f'depth {depth_topic!r}')

    # -- inbound ---------------------------------------------------------------------
    def _reject(self, kind: str, exc: Exception) -> None:
        self._counts[f'invalid_{kind}'] += 1
        self.get_logger().warning(f'dropped invalid {kind}: {exc}', throttle_duration_sec=5.0)

    def _on_local_position(self, msg: Any) -> None:
        try:
            report = px4.decode_local_position(msg, now_seconds(self))
        except MessageValidationError as exc:
            self._reject('local_position', exc)
            return
        self._controller.on_local_position(report)

    def _on_attitude(self, msg: Any) -> None:
        try:
            report = px4.decode_attitude(msg, now_seconds(self))
        except MessageValidationError as exc:
            self._reject('attitude', exc)
            return
        self._controller.on_attitude(report)

    def _on_vehicle_status(self, msg: Any) -> None:
        try:
            report = px4.decode_vehicle_status(msg, now_seconds(self))
        except MessageValidationError as exc:
            self._reject('vehicle_status', exc)
            return
        self._controller.on_vehicle_status(report)

    def _on_camera_info(self, msg: Any) -> None:
        try:
            self._intrinsics = decode_camera_info(msg)
        except MessageValidationError as exc:
            self._reject('camera_info', exc)

    def _on_depth(self, msg: Any) -> None:
        intrinsics = self._intrinsics
        if intrinsics is None:
            self._counts['depth_without_camera_info'] += 1
            return
        try:
            image = decode_depth_image(msg)
            frame = DepthFrame(time_to_seconds(msg.header.stamp), image, intrinsics)
        except (MessageValidationError, ValueError) as exc:
            self._reject('depth', exc)
            return
        outcome = self._controller.on_depth(frame, now_seconds(self))
        self._counts[f'depth_{outcome.value}'] += 1
        if outcome is not DepthOutcome.PROCESSED:
            self.get_logger().warning(f'depth frame not used: {outcome.value}',
                                      throttle_duration_sec=5.0)

    def _on_status(self, msg: Any) -> None:
        try:
            status, protocol = self._codec.decode_status(msg)
        except MessageValidationError as exc:
            self._reject('status', exc)
            return
        receipt = self._controller.on_peer_status(status, now_seconds(self), protocol)
        self._counts[f'status_{receipt.value}'] += 1

    def _on_coverage(self, msg: Any) -> None:
        try:
            update = self._codec.decode_coverage(msg)
        except MessageValidationError as exc:
            self._reject('coverage', exc)
            return
        receipt = self._controller.on_coverage(update, now_seconds(self))
        self._counts[f'coverage_{receipt.value}'] += 1

    def _on_mission(self, msg: Any) -> None:
        try:
            spec = self._codec.decode_mission(msg)
        except MessageValidationError as exc:
            self._reject('mission', exc)
            return
        receipt = self._controller.on_mission(spec, now_seconds(self))
        self._counts[f'mission_{receipt.value}'] += 1

    def _on_command(self, msg: Any) -> None:
        try:
            command = self._codec.decode_command(msg)
        except MessageValidationError as exc:
            self._reject('command', exc)
            return
        receipt = self._controller.on_command(command, now_seconds(self))
        self._counts[f'command_{receipt.value}'] += 1

    def _on_target_report(self, msg: Any) -> None:
        try:
            report = self._codec.decode_target_report(msg)
        except MessageValidationError as exc:
            self._reject('target_report', exc)
            return
        receipt = self._controller.on_target_report(report, now_seconds(self))
        self._counts[f'target_report_{receipt.value}'] += 1

    # -- control ----------------------------------------------------------------------
    def _tick(self) -> None:
        started = time.perf_counter()
        period = self._cfg.control_period
        late = (self._last_tick_start is not None
                and started - self._last_tick_start > 2.0 * period)
        overrun = late or self._last_tick_duration > period
        self._last_tick_start = started
        now = now_seconds(self)
        out = self._controller.tick(now, overrun)
        if out.setpoint is not None:
            setpoint = px4.encode_trajectory_setpoint(self._px4, out.setpoint, now)
            if self._control_enabled:
                self._offboard_pub.publish(px4.encode_offboard_mode(self._px4, now))
                self._setpoint_pub.publish(setpoint)
            else:
                self._shadow_pub.publish(setpoint)
        if out.fc_request is not None:
            if self._control_enabled:
                self._command_pub.publish(px4.encode_vehicle_command(
                    self._px4, out.fc_request, self._system_id, now))
            else:
                self.get_logger().warning(f'shadow mode: would request {out.fc_request.value}',
                                          throttle_duration_sec=5.0)
        if out.status is not None:
            self._status_pub.publish(self._codec.encode_status(out.status))
        if out.coverage is not None:
            self._coverage_pub.publish(self._codec.encode_coverage(out.coverage))
        self._log_events(out.events)
        self._last_tick_duration = time.perf_counter() - started
        if self._last_tick_duration > period:
            self._slow_ticks += 1
            self.get_logger().warning(
                f'control tick took {self._last_tick_duration * 1e3:.0f} ms '
                f'(period {period * 1e3:.0f} ms)', throttle_duration_sec=10.0)

    def _log_events(self, events: Sequence[ControllerEvent]) -> None:
        for event in events:
            text = f'{event.kind}: {event.detail}'
            if event.kind in _WARN_EVENTS:
                self.get_logger().warning(text)
            elif event.kind in _INFO_EVENTS:
                self.get_logger().info(text)
            else:
                self.get_logger().debug(text)

    def _diagnostics(self) -> None:
        counts = ', '.join(f'{k}={v}' for k, v in sorted(self._counts.items()))
        self.get_logger().info(f'phase {self._controller.phase.name}; slow ticks '
                               f'{self._slow_ticks}; messages [{counts}]')


def main(args: Optional[List[str]] = None) -> int:
    """Run the drone node."""
    return run_node(DroneNode, args)
