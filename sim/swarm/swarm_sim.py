"""
Simulated swarm_sar drones on ROS 2, for the swarm CI workflow (ADR 0026).

The onboard closed-loop simulation (``swarm_sar.sim.Simulation``: the real
``DroneController`` flying simulated vehicles through a simulated forest) runs in real
time on the Unix-epoch clock, and talks to the ground over the real topics, messages
and codec: it publishes each drone's ``DroneState`` on ``/swarm/v2/status`` and takes
``/swarm/v2/mission`` and ``/swarm/v2/command``. The ground station's bridge cannot tell
it from real companions, except that the drones start airborne and in offboard control
(the simulator's launch), hovering at the simulated altitude.

The simulation's clock starts at 0; drones reject ground sequence numbers ahead of their
own clock, so ``EpochSimulation`` offsets it to the epoch. It starts with the simulator's
own mission (sequence 1), which any ground mission replaces. The onboard code is used
unchanged (ADR 0003).

    python3 sim/swarm/swarm_sim.py --drones 3        # in the ROS container
"""

from __future__ import annotations

import argparse
import time
from typing import Any, List, Optional, Sequence

from swarm_sar.core.config import DroneConfig, SimConfig
from swarm_sar.core.messages import DroneStatus
from swarm_sar.sim.simulation import Simulation


class EpochSimulation(Simulation):
    """The onboard simulation with its clock on the Unix epoch (the ground's clock)."""

    def __init__(self, *args: Any, epoch: float, **kwargs: Any) -> None:
        self._epoch = float(epoch)
        super().__init__(*args, **kwargs)

    @property
    def time(self) -> float:
        """Return the simulated time as seconds since the Unix epoch."""
        return self._epoch + super().time

    def statuses(self) -> List[DroneStatus]:
        """Return the states the drones broadcast in the last step."""
        return [d.last_output.status for d in self.drones
                if d.last_output is not None and d.last_output.status is not None]


def build(drones: int, seed: int, epoch: float) -> EpochSimulation:
    """Return a swarm of ``drones`` at the simulator's default site (Zurich, PX4 home)."""
    return EpochSimulation(DroneConfig(depth_stride=1), SimConfig(), drones, seed, epoch=epoch)


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover - needs ROS 2
    """Run the swarm until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--drones', type=int, default=3)
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args(argv)

    import rclpy
    from swarm_sar.ros.codec import Codec, MessageTypes, MessageValidationError
    from swarm_sar.ros.topics import COMMAND_TOPIC, MISSION_TOPIC, STATUS_TOPIC
    from swarm_sar.ros.util import broadcast_qos, DEFAULT_BROADCAST_DEPTH, latched_qos

    rclpy.init()
    node = rclpy.create_node('swarm_sim')
    types = MessageTypes.load()
    codec = Codec(types)
    sim = build(args.drones, args.seed, time.time())
    status_pub = node.create_publisher(types.DroneState, STATUS_TOPIC,
                                       broadcast_qos(DEFAULT_BROADCAST_DEPTH))

    def on_ground(decode: Any, what: str) -> Any:
        def callback(msg: Any) -> None:
            try:
                message = decode(msg)
            except MessageValidationError as exc:
                node.get_logger().warning(f'invalid {what} dropped: {exc}')
                return
            node.get_logger().info(f'{what} sequence {message.sequence} received')
            sim.send(message)
        return callback

    node.create_subscription(types.Mission, MISSION_TOPIC,
                             on_ground(codec.decode_mission, 'mission'), latched_qos())
    node.create_subscription(types.SwarmCommand, COMMAND_TOPIC,
                             on_ground(codec.decode_command, 'command'), latched_qos())
    node.get_logger().info(f'{args.drones} simulated drones at {sim.projection.reference}')
    period = sim.drone_config.control_period
    try:
        while rclpy.ok():
            # Keep the simulated clock on the wall clock (drones reject future sequences).
            while sim.time + period <= time.time():
                sim.step()
                for status in sim.statuses():
                    status_pub.publish(codec.encode_status(status))
            rclpy.spin_once(node, timeout_sec=period / 2.0)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
