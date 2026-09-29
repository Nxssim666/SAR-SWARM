"""The bridge's decisions (core.py) and wire format (wire.py), without ROS or NATS."""

import json
import math

from fake_msgs import FakeMessages
import numpy as np
import pytest
from sar_gcs_bridge import wire
from sar_gcs_bridge.core import (Bridge, COMMAND_REPEAT_S, COMMAND_WINDOW_S, heading_degrees,
                                 MISSION_WINDOW_S, STATUS_MIN_PERIOD_S)
from swarm_sar.core.geodesy import GeoPoint, LocalProjection
from swarm_sar.core.messages import (CommandKind, DroneStatus, HealthLevel, MissionSpec, Phase,
                                     SwarmCommand)
from swarm_sar.core.supervisor import Fault
from swarm_sar.core.tracking import TargetEstimate
from swarm_sar.ros.codec import Codec, MessageTypes

NOW = 1_790_000_000.0  # realistic wall-clock seconds
HERE = GeoPoint(47.397742, 8.545594)
FAKES = FakeMessages()
CODEC = Codec(MessageTypes(
    DroneState=FAKES.get('swarm_sar_interfaces/DroneState'),
    TargetEstimate=FAKES.get('swarm_sar_interfaces/TargetEstimate'),
    CoverageUpdate=FAKES.get('swarm_sar_interfaces/CoverageUpdate'),
    Mission=FAKES.get('swarm_sar_interfaces/Mission'),
    SwarmCommand=FAKES.get('swarm_sar_interfaces/SwarmCommand'),
    TargetReport=FAKES.get('swarm_sar_interfaces/TargetReport'),
    SwarmMetrics=FAKES.get('swarm_sar_interfaces/SwarmMetrics'),
    Time=FAKES.get('builtin_interfaces/Time')))


class Clock:
    """A clock the test moves."""

    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


def status(**overrides):
    fields = {'drone_id': 3, 'stamp': NOW, 'position': HERE, 'velocity': (3.0, 4.0),
              'heading': 0.0, 'phase': Phase.SEARCH, 'health': HealthLevel.OK, 'faults': 0,
              'mission_sequence': 0, 'command_sequence': 0}
    fields.update(overrides)
    return DroneStatus(**fields)


def request(**fields):
    return json.dumps(fields).encode()


def mission_request(**overrides):
    square = [{'latitude': HERE.latitude + dy, 'longitude': HERE.longitude + dx}
              for dx, dy in ((-0.001, -0.001), (0.001, -0.001), (0.001, 0.001), (-0.001, 0.001))]
    fields = {'mission_id': 'sector-a', 'origin': {'latitude': HERE.latitude,
                                                   'longitude': HERE.longitude},
              'altitude_relative_m': 20.0, 'grid_resolution_m': 5.0, 'waypoints': [],
              'area': square}
    fields.update(overrides)
    return request(**fields)


# -- units ------------------------------------------------------------------------------


@pytest.mark.parametrize(('enu_heading', 'degrees_true'), [
    (0.0, 90.0),                # facing east
    (math.pi / 2.0, 0.0),       # facing north
    (math.pi, 270.0),           # facing west
    (-math.pi / 2.0, 180.0),    # facing south
    (math.pi / 4.0, 45.0),      # north-east
    (3.0 * math.pi / 4.0, 315.0),  # north-west
])
def test_heading_is_converted_to_degrees_true_clockwise_from_north(enu_heading, degrees_true):
    assert heading_degrees(enu_heading) == pytest.approx(degrees_true)
    assert 0.0 <= heading_degrees(enu_heading) < 360.0


def test_heading_that_is_not_finite_is_unknown():
    assert heading_degrees(math.nan) is None


def test_a_drone_state_becomes_a_status_message():
    bridge = Bridge('default', Clock())
    faults = int(Fault.DEPTH_STALE | Fault.MISSION_REJECTED)

    message = bridge.on_status(status(faults=faults, nearest_obstacle=math.inf))

    assert message['drone_id'] == 3
    assert message['phase'] == 'search'
    assert message['health'] == 'ok'
    assert message['faults'] == ['depth_stale', 'mission_rejected']
    assert message['position'] == {'latitude': HERE.latitude, 'longitude': HERE.longitude}
    assert message['velocity_east_mps'] == 3.0  # DroneStatus.velocity is (east, north)
    assert message['velocity_north_mps'] == 4.0
    assert message['groundspeed_mps'] == 5.0
    assert message['heading_deg'] == pytest.approx(90.0)
    assert message['nearest_obstacle_m'] is None  # inf: nothing known nearby
    assert message['survivor_sighting'] is None
    assert message['received_at'] == NOW


def test_a_drone_without_a_global_reference_has_no_position():
    message = Bridge('default', Clock()).on_status(status(position=None))
    assert message['position'] is None


def test_states_are_forwarded_at_most_five_times_a_second_per_drone():
    clock = Clock()
    bridge = Bridge('default', clock)

    first = bridge.on_status(status())
    too_soon = bridge.on_status(status(command_sequence=5))
    other_drone = bridge.on_status(status(drone_id=4))
    clock.now += STATUS_MIN_PERIOD_S
    later = bridge.on_status(status(command_sequence=6))

    assert first is not None and other_drone is not None and later is not None
    assert too_soon is None
    assert bridge.drones[3].command_sequence == 6  # the newest state is always recorded


def test_an_estimate_becomes_a_survivor_sighting_through_the_mission_origin():
    bridge = Bridge('default', Clock())
    answer, spec = bridge.mission(mission_request())
    covariance = np.diag([9.0, 9.0, 1.0, 1.0])
    estimate = TargetEstimate(np.array([100.0, 0.0, 0.0, 0.0]), covariance, NOW - 1.0, NOW - 2.0)

    message = bridge.on_status(status(mission_sequence=spec.sequence, estimate=estimate))

    sighting = message['survivor_sighting']
    expected = LocalProjection(HERE).to_geo(100.0, 0.0)  # 100 m east of the origin
    assert sighting['latitude'] == pytest.approx(expected.latitude)
    assert sighting['longitude'] == pytest.approx(expected.longitude)
    assert sighting['longitude'] > HERE.longitude
    assert sighting['std_m'] == pytest.approx(3.0)
    assert sighting['stamp'] == NOW - 1.0


def test_an_estimate_of_a_mission_this_bridge_did_not_send_is_not_placed():
    estimate = TargetEstimate(np.zeros(4), np.eye(4), NOW, NOW)
    message = Bridge('default', Clock()).on_status(status(mission_sequence=42,
                                                          estimate=estimate))
    assert message['survivor_sighting'] is None


# -- requests -----------------------------------------------------------------------------


def test_a_command_request_becomes_an_onboard_command_numbered_on_the_ground_clock():
    bridge = Bridge('default', Clock())

    answer, command = bridge.command(request(kind='hold', drone_ids=[2, 1]))

    assert isinstance(command, SwarmCommand)
    assert command.kind is CommandKind.HOLD
    assert command.drone_ids == frozenset({1, 2})
    assert command.sequence == int(NOW * 1000)
    assert command.stamp == NOW
    assert answer == {'sequence': command.sequence, 'error': None}


def test_sequences_strictly_increase_even_if_the_clock_stalls_or_steps_back():
    clock = Clock()
    bridge = Bridge('default', clock)

    first = bridge.command(request(kind='hold', drone_ids=[1]))[1].sequence
    second = bridge.command(request(kind='resume', drone_ids=[1]))[1].sequence
    clock.now -= 5.0
    third = bridge.mission(mission_request())[1].sequence

    assert first < second < third


@pytest.mark.parametrize('body', [
    b'not json',
    request(kind='hold'),                               # missing drone_ids
    request(kind='hold', drone_ids=[1], extra=True),    # unknown field
    request(kind='terminate', drone_ids=[1]),           # not a swarm command
    request(kind='hold', drone_ids=[]),
    request(kind='hold', drone_ids=[-1]),               # the onboard validation
    request(kind='hold', drone_ids=[True]),
])
def test_a_malformed_command_is_refused_with_a_reason(body):
    answer, command = Bridge('default', Clock()).command(body)

    assert command is None
    assert answer['sequence'] is None
    assert answer['error']


def test_a_mission_request_is_validated_by_the_onboard_code():
    bridge = Bridge('default', Clock())

    answer, spec = bridge.mission(mission_request())
    _, too_few = bridge.mission(mission_request(area=[{'latitude': 1.0, 'longitude': 2.0}] * 2))
    _, long_id = bridge.mission(mission_request(mission_id='x' * 65))

    assert isinstance(spec, MissionSpec)
    assert spec.altitude == 20.0
    assert spec.origin == HERE
    assert len(spec.area) == 4
    assert answer['sequence'] == spec.sequence
    assert too_few is None
    assert long_id is None


def test_what_the_bridge_publishes_passes_the_onboard_codec():
    bridge = Bridge('default', Clock())
    _, command = bridge.command(request(kind='land', drone_ids=[1, 2]))
    _, spec = bridge.mission(mission_request())

    decoded_command = CODEC.decode_command(CODEC.encode_command(command))
    decoded_mission = CODEC.decode_mission(CODEC.encode_mission(spec))

    assert decoded_command == command
    assert decoded_mission.sequence == spec.sequence
    assert decoded_mission.area == spec.area


# -- republishing -------------------------------------------------------------------------


def test_a_command_is_republished_until_every_addressed_drone_has_processed_it():
    clock = Clock()
    bridge = Bridge('default', clock)
    bridge.on_status(status(drone_id=1))
    bridge.on_status(status(drone_id=2))
    _, command = bridge.command(request(kind='hold', drone_ids=[1, 2]))

    assert bridge.due() == []  # just sent
    clock.now += COMMAND_REPEAT_S
    assert bridge.due() == [command]
    bridge.on_status(status(drone_id=1, command_sequence=command.sequence))
    clock.now += COMMAND_REPEAT_S
    assert bridge.due() == [command]  # drone 2 has not
    bridge.on_status(status(drone_id=2, command_sequence=command.sequence))
    clock.now += COMMAND_REPEAT_S
    assert bridge.due() == []


def test_republishing_stops_after_its_window():
    clock = Clock()
    bridge = Bridge('default', clock)
    bridge.command(request(kind='hold', drone_ids=[9]))  # never heard
    bridge.mission(mission_request())

    clock.now += COMMAND_WINDOW_S + 1.0
    assert all(isinstance(m, MissionSpec) for m in bridge.due())
    clock.now += MISSION_WINDOW_S
    assert bridge.due() == []


def test_a_mission_is_republished_until_every_drone_heard_flies_it():
    clock = Clock()
    bridge = Bridge('default', clock)
    bridge.on_status(status(drone_id=1))
    _, spec = bridge.mission(mission_request())

    clock.now += 1.0
    assert bridge.due() == [spec]
    bridge.on_status(status(drone_id=1, mission_sequence=spec.sequence))
    clock.now += 1.0
    assert bridge.due() == []


def test_the_heartbeat_lists_the_drones_heard():
    bridge = Bridge('blue', Clock())
    bridge.on_status(status(drone_id=5))
    bridge.on_status(status(drone_id=2))

    assert bridge.heartbeat() == {'bridge_version': wire.BRIDGE_VERSION, 'swarm': 'blue',
                                  'stamp': NOW, 'drones_heard': [2, 5]}
    assert wire.subject('blue', 'status') == 'sar.v1.swarm.blue.status'
