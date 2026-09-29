"""
The bridge node: the swarm's ROS 2 topics on one side, NATS on the other (ADR 0024).

    ros2 run sar_gcs_bridge bridge_node --ros-args -p nats_url:=nats://127.0.0.1:4222

rclpy spins in a background thread; the NATS client and every decision (``core.Bridge``)
live on the asyncio loop in the main thread. ROS callbacks only decode a message and
hand it to the loop, so the core never runs in two threads at once. Publishing to ROS
from the loop is safe: rclpy publishers may be used from any thread.

Topics and QoS are the onboard ones (``swarm_sar.ros.topics``, ``swarm_sar.ros.util``):
drone states best effort, missions and commands reliable and transient-local, like the
onboard ``swarm_sar_mission`` tool. Nothing here is a flight decision: the bridge only
carries what the station sent, and the drones validate it again.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import threading
import time
from typing import Any, List, Optional, Set

from sar_gcs_bridge import wire
from sar_gcs_bridge.core import Bridge, Outgoing
from swarm_sar.core.messages import MissionSpec

TICK_S = 0.1
HEARTBEAT_S = 1.0


class BridgeNode:  # pragma: no cover - needs ROS 2 and NATS (tested in the ROS container)
    """Owns the ROS node, the NATS connection and the bridge core."""

    def __init__(self) -> None:
        import rclpy
        from swarm_sar.ros.codec import Codec, MessageTypes, MessageValidationError
        from swarm_sar.ros.topics import COMMAND_TOPIC, MISSION_TOPIC, STATUS_TOPIC
        from swarm_sar.ros.util import broadcast_qos, DEFAULT_BROADCAST_DEPTH, latched_qos

        self._rclpy = rclpy
        self._invalid = MessageValidationError
        self.node = rclpy.create_node('sar_gcs_bridge')
        self.swarm = str(self.node.declare_parameter('swarm', 'default').value)
        self.nats_url = str(self.node.declare_parameter('nats_url', 'nats://127.0.0.1:4222').value)
        self._types = MessageTypes.load()
        self._codec = Codec(self._types)
        self.core = Bridge(self.swarm, time.time)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._nc: Any = None
        self._invalid_count = 0
        self._tasks: Set['asyncio.Future[None]'] = set()
        self.node.create_subscription(self._types.DroneState, STATUS_TOPIC, self._on_status,
                                      broadcast_qos(DEFAULT_BROADCAST_DEPTH))
        self._mission_pub = self.node.create_publisher(self._types.Mission, MISSION_TOPIC,
                                                       latched_qos())
        self._command_pub = self.node.create_publisher(self._types.SwarmCommand, COMMAND_TOPIC,
                                                       latched_qos())

    # -- ROS side (executor thread) --------------------------------------------------------

    def _on_status(self, msg: Any) -> None:
        try:
            status, _ = self._codec.decode_status(msg)
        except self._invalid as exc:
            self._invalid_count += 1
            self.node.get_logger().warning(f'invalid DroneState dropped: {exc}',
                                           throttle_duration_sec=5.0)
            return
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._forward_status, status)

    def _publish(self, messages: List[Outgoing]) -> None:
        for message in messages:
            if isinstance(message, MissionSpec):
                self._mission_pub.publish(self._codec.encode_mission(message))
            else:
                self._command_pub.publish(self._codec.encode_command(message))

    # -- NATS side (asyncio loop) ---------------------------------------------------------

    def _forward_status(self, status: Any) -> None:
        message = self.core.on_status(status)
        if message is not None and self._nc is not None and self._nc.is_connected:
            task = asyncio.ensure_future(
                self._nc.publish(wire.subject(self.swarm, 'status'), wire.encode(message)))
            self._tasks.add(task)  # keep a reference until it is done
            task.add_done_callback(self._tasks.discard)

    async def _on_command(self, msg: Any) -> None:
        answer, command = self.core.command(msg.data)
        if command is not None:
            self._publish([command])
            self.node.get_logger().info(
                f'{command.kind.name} to {sorted(command.drone_ids)} '
                f'(sequence {command.sequence})')
        else:
            self.node.get_logger().warning(f'command refused: {answer["error"]}')
        await msg.respond(wire.encode(answer))

    async def _on_mission(self, msg: Any) -> None:
        answer, spec = self.core.mission(msg.data)
        if spec is not None:
            self._publish([spec])
            self.node.get_logger().info(
                f'mission {spec.mission_id!r} (sequence {spec.sequence}, '
                f'{len(spec.area)} vertices)')
        else:
            self.node.get_logger().warning(f'mission refused: {answer["error"]}')
        await msg.respond(wire.encode(answer))

    async def run(self) -> None:
        """Connect to NATS (retrying), then republish and send heartbeats until cancelled."""
        import nats

        self._loop = asyncio.get_running_loop()
        while True:
            try:
                self._nc = await nats.connect(self.nats_url, name='sar_gcs_bridge',
                                              max_reconnect_attempts=-1, reconnect_time_wait=1,
                                              connect_timeout=2, error_cb=self._on_nats_error,
                                              disconnected_cb=self._on_disconnected,
                                              reconnected_cb=self._on_reconnected)
                break
            except Exception as exc:  # noqa: B902 - any connection failure: retry
                self.node.get_logger().warning(f'NATS {self.nats_url} unreachable ({exc}); '
                                               'retrying', throttle_duration_sec=10.0)
                await asyncio.sleep(2.0)
        await self._nc.subscribe(wire.subject(self.swarm, 'command'), cb=self._on_command)
        await self._nc.subscribe(wire.subject(self.swarm, 'mission'), cb=self._on_mission)
        self.node.get_logger().info(f'bridging swarm {self.swarm!r} to NATS {self.nats_url}')
        next_heartbeat = 0.0
        while True:
            self._publish(self.core.due())
            if time.monotonic() >= next_heartbeat and self._nc.is_connected:
                await self._nc.publish(wire.subject(self.swarm, 'bridge'),
                                       wire.encode(self.core.heartbeat()))
                next_heartbeat = time.monotonic() + HEARTBEAT_S
            await asyncio.sleep(TICK_S)

    async def _on_nats_error(self, error: Exception) -> None:
        self.node.get_logger().warning(f'NATS: {error!r}', throttle_duration_sec=5.0)

    async def _on_disconnected(self) -> None:
        self.node.get_logger().warning('NATS disconnected; reconnecting')

    async def _on_reconnected(self) -> None:
        self.node.get_logger().info('NATS reconnected')

    async def close(self) -> None:
        """Close the NATS connection."""
        if self._nc is not None:
            with contextlib.suppress(Exception):
                await self._nc.close()


def main(args: Optional[List[str]] = None) -> int:  # pragma: no cover - needs ROS 2
    """Run the bridge until SIGINT or SIGTERM."""
    import rclpy
    from rclpy.executors import SingleThreadedExecutor

    rclpy.init(args=args)
    bridge = BridgeNode()
    executor = SingleThreadedExecutor()
    executor.add_node(bridge.node)
    spinner = threading.Thread(target=executor.spin, name='ros-executor', daemon=True)
    spinner.start()

    async def serve() -> None:
        task = asyncio.ensure_future(bridge.run())
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await bridge.close()

    try:
        asyncio.run(serve())
    finally:
        executor.shutdown()
        bridge.node.destroy_node()
        rclpy.try_shutdown()
    return 0
