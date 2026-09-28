"""
Ground-station command line: send a mission, send operator commands, check acknowledgements.

    swarm_sar_mission example > mission.json
    swarm_sar_mission send mission.json          # serves the mission until Ctrl-C
    swarm_sar_mission hold --drones 2,5          # or: resume, rtl, land (default: every drone)
    swarm_sar_mission send mission.json --use-sim-time   # PX4 SITL: drones run on /clock

Every drone reports the mission and the last command it applied in its
status broadcast, so this tool shows exactly which drones have acknowledged.
A command exits 0 only when every addressed drone that is online has
acknowledged it before ``--timeout``.

Sequence numbers and command stamps come from this tool's ROS clock (wall
time, or ``/clock`` with ``--use-sim-time``), in milliseconds, and must use
the same clock as the drones: drones ignore sequences ahead of their own
clock, commands older than ``command_max_age``, and missions that are not
newer than their current one.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from typing import Dict, FrozenSet, List, Optional, Sequence

from swarm_sar.core.messages import (CommandKind, DroneStatus, MissionSpec,
                                     SEQUENCE_UNITS_PER_SECOND, SwarmCommand)
from swarm_sar.mission_file import example_mission, MissionFileError, parse_mission

COMMANDS = {'hold': CommandKind.HOLD, 'resume': CommandKind.RESUME,
            'rtl': CommandKind.RETURN_TO_LAUNCH, 'land': CommandKind.LAND}
REPUBLISH_PERIOD_S = 2.0
CLOCK_WAIT_S = 5.0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(prog='swarm_sar_mission', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('example', help='print an example mission file')
    clock = argparse.ArgumentParser(add_help=False)
    clock.add_argument('--use-sim-time', action='store_true',
                       help='take sequence numbers and stamps from /clock, like drones '
                            'launched with use_sim_time:=true')
    send = sub.add_parser('send', parents=[clock],
                          help='validate and send a mission, then serve it')
    send.add_argument('file', help='mission JSON file')
    for name in COMMANDS:
        cmd = sub.add_parser(name, parents=[clock], help=f'send the {COMMANDS[name].name} command')
        cmd.add_argument('--drones', default='', help='comma-separated drone ids (default all)')
        cmd.add_argument('--timeout', type=float, default=10.0,
                         help='seconds to wait for acknowledgements')
    return parser


def parse_drone_ids(text: str) -> FrozenSet[int]:
    """Parse ``'1,2, 5'`` into drone ids (empty text means every drone)."""
    ids = set()
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f'drone ids must be non-negative integers, got {part!r}')
        ids.add(int(part))
    return frozenset(ids)


def sequence_at(seconds: float) -> int:
    """Return the sequence number for ``seconds`` on the ground-station clock."""
    sequence = int(seconds * SEQUENCE_UNITS_PER_SECOND)
    if sequence < 1:
        raise ValueError('the clock has not started (with --use-sim-time: is /clock published?)')
    return sequence


def mission_at(spec: MissionSpec, seconds: float) -> MissionSpec:
    """Return ``spec`` numbered for sending at ``seconds`` on the ground-station clock."""
    return dataclasses.replace(spec, sequence=sequence_at(seconds))


def command_at(kind: CommandKind, targets: FrozenSet[int], seconds: float) -> SwarmCommand:
    """Return the command to send at ``seconds`` on the ground-station clock."""
    return SwarmCommand(sequence_at(seconds), kind, seconds, targets)


def unacknowledged(command: SwarmCommand, online: Dict[int, DroneStatus]) -> List[int]:
    """Return the addressed, online drones that have not yet applied ``command``."""
    return sorted(i for i, s in online.items()
                  if command.applies_to(i) and s.command_sequence < command.sequence)


def mission_holdouts(spec: MissionSpec, online: Dict[int, DroneStatus]) -> List[int]:
    """Return the online drones not (yet) flying ``spec``."""
    return sorted(i for i, s in online.items() if s.mission_sequence != spec.sequence)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI; return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.action == 'example':
        sys.stdout.write(example_mission())
        return 0
    try:
        if args.action == 'send':
            with open(args.file, encoding='utf-8') as handle:
                # Validated now; it gets its real sequence number once the clock is known.
                spec = parse_mission(handle.read(), 1)
            return _serve_mission(spec, args.use_sim_time)
        targets = parse_drone_ids(args.drones)
        return _send_command(COMMANDS[args.action], targets, args.timeout, args.use_sim_time)
    except (OSError, MissionFileError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


def _ros_session(use_sim_time: bool):  # pragma: no cover - needs ROS 2
    import rclpy
    from rclpy.parameter import Parameter
    from swarm_sar.ros.codec import Codec, MessageTypes, MessageValidationError
    from swarm_sar.ros.topics import COMMAND_TOPIC, MISSION_TOPIC, STATUS_TOPIC
    from swarm_sar.ros.util import broadcast_qos, DEFAULT_BROADCAST_DEPTH, latched_qos
    rclpy.init()
    node = rclpy.create_node('swarm_sar_mission', parameter_overrides=[
        Parameter('use_sim_time', Parameter.Type.BOOL, use_sim_time)])
    types = MessageTypes.load()
    codec = Codec(types)
    online: Dict[int, DroneStatus] = {}

    def on_status(msg: object) -> None:
        try:
            status, _ = codec.decode_status(msg)
        except MessageValidationError:
            return
        online[status.drone_id] = status

    node.create_subscription(types.DroneState, STATUS_TOPIC, on_status,
                             broadcast_qos(DEFAULT_BROADCAST_DEPTH))
    mission_pub = node.create_publisher(types.Mission, MISSION_TOPIC, latched_qos())
    command_pub = node.create_publisher(types.SwarmCommand, COMMAND_TOPIC, latched_qos())
    return rclpy, node, codec, online, mission_pub, command_pub


def _clock_seconds(rclpy, node) -> float:  # pragma: no cover - needs ROS 2
    """Return the node clock; with simulated time, wait briefly for the first /clock."""
    deadline = time.monotonic() + CLOCK_WAIT_S
    seconds = node.get_clock().now().nanoseconds / 1e9
    while seconds <= 0.0 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        seconds = node.get_clock().now().nanoseconds / 1e9
    return seconds


def _serve_mission(spec: MissionSpec, use_sim_time: bool) -> int:  # pragma: no cover
    rclpy, node, codec, online, mission_pub, _ = _ros_session(use_sim_time)
    try:
        spec = mission_at(spec, _clock_seconds(rclpy, node))
        message = codec.encode_mission(spec)
        print(f'serving mission {spec.mission_id!r} (sequence {spec.sequence}); Ctrl-C to stop')
        last_report = ''
        next_publish = 0.0
        while rclpy.ok():
            if time.monotonic() >= next_publish:
                mission_pub.publish(message)
                next_publish = time.monotonic() + REPUBLISH_PERIOD_S
            rclpy.spin_once(node, timeout_sec=0.1)
            holdouts = mission_holdouts(spec, online)
            report = (f'{len(online) - len(holdouts)}/{len(online)} online drones flying it'
                      + (f'; not yet: {holdouts}' if holdouts else ''))
            if report != last_report:
                print(report)
                last_report = report
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return 0


def _send_command(kind: CommandKind, targets: FrozenSet[int], timeout: float,
                  use_sim_time: bool) -> int:  # pragma: no cover - needs ROS 2
    rclpy, node, codec, online, _, command_pub = _ros_session(use_sim_time)
    pending: List[int] = []
    try:
        command = command_at(kind, targets, _clock_seconds(rclpy, node))
        command_pub.publish(codec.encode_command(command))
        deadline = time.monotonic() + max(timeout, 0.0)
        while time.monotonic() < deadline and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            pending = unacknowledged(command, online)
            if online and not pending:
                break
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    if not online:
        print(f'{kind.name}: no drone heard; nothing acknowledged', file=sys.stderr)
        return 1
    if pending:
        print(f'{kind.name}: not acknowledged by {pending}', file=sys.stderr)
        return 1
    print(f'{kind.name} acknowledged by every addressed drone online')
    return 0
