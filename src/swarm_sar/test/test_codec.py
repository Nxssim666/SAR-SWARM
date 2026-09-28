"""Tests for swarm_sar.ros.codec against strict rosidl-like fakes of the real .msg files."""

import array
import math

from fake_msgs import FakeMessages, INTERFACES_DIR
import numpy as np
import pytest
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.messages import (CommandKind, CoverageUpdate, DroneStatus, HealthLevel,
                                     MissionSpec, Phase, PROTOCOL_VERSION, SwarmCommand,
                                     TargetReport)
from swarm_sar.core.metrics import MetricsSnapshot
from swarm_sar.core.supervisor import Fault
from swarm_sar.core.tracking import TargetEstimate
from swarm_sar.ros.codec import (Codec, MAX_COVERAGE_CELLS, MessageTypes,
                                 MessageValidationError, seconds_to_time, time_to_seconds)

FAKES = FakeMessages()
TYPES = MessageTypes(
    DroneState=FAKES.get('swarm_sar_interfaces/DroneState'),
    TargetEstimate=FAKES.get('swarm_sar_interfaces/TargetEstimate'),
    CoverageUpdate=FAKES.get('swarm_sar_interfaces/CoverageUpdate'),
    Mission=FAKES.get('swarm_sar_interfaces/Mission'),
    SwarmCommand=FAKES.get('swarm_sar_interfaces/SwarmCommand'),
    TargetReport=FAKES.get('swarm_sar_interfaces/TargetReport'),
    SwarmMetrics=FAKES.get('swarm_sar_interfaces/SwarmMetrics'),
    Time=FAKES.get('builtin_interfaces/Time'))
CODEC = Codec(TYPES)
NOW = 1_758_000_000.25  # realistic ROS wall-clock seconds
HERE = GeoPoint(47.397742, 8.545594)


def estimate(stamp=NOW):
    cov = np.diag([2.0, 3.0, 0.5, 0.25])
    cov[0, 1] = cov[1, 0] = 0.4
    return TargetEstimate(np.array([10.0, 20.0, 1.0, -0.5]), cov, stamp, stamp - 0.4)


def status(**overrides):
    fields = {'drone_id': 7, 'stamp': NOW, 'position': HERE, 'velocity': (1.0, -2.0),
              'heading': 0.5, 'phase': Phase.TRACK, 'health': HealthLevel.DEGRADED,
              'faults': int(Fault.DEPTH_STALE | Fault.CONTROL_OVERRUN), 'mission_sequence': 12,
              'command_sequence': 2 ** 40, 'goal': (15.0, 32.0), 'estimate': estimate(),
              'nearest_obstacle': 1.5}
    fields.update(overrides)
    return DroneStatus(**fields)


def test_every_interface_definition_parses_with_valid_names():
    names = sorted(p.stem for p in INTERFACES_DIR.glob('*.msg'))
    assert names == ['CoverageUpdate', 'DroneState', 'Mission', 'SwarmCommand', 'SwarmMetrics',
                     'TargetEstimate', 'TargetReport']
    for name in names:
        FAKES.get(f'swarm_sar_interfaces/{name}')()


def test_wire_constants_match_the_core_enums():
    msg = TYPES.DroneState
    assert msg.PROTOCOL_VERSION == PROTOCOL_VERSION
    for phase in Phase:
        assert getattr(msg, f'PHASE_{phase.name}') == int(phase)
    for level in HealthLevel:
        assert getattr(msg, f'HEALTH_{level.name}') == int(level)
    for fault in Fault:
        if fault.name != 'NONE':
            assert getattr(msg, f'FAULT_{fault.name}') == int(fault)
    for kind in CommandKind:
        assert getattr(TYPES.SwarmCommand, kind.name) == int(kind)


def test_fakes_enforce_rosidl_types():
    msg = TYPES.DroneState()
    with pytest.raises(AssertionError):
        msg.drone_id = np.int64(3)
    with pytest.raises(AssertionError):
        msg.heading = 1
    with pytest.raises(AttributeError):
        msg.no_such_field = 1.0
    coverage = TYPES.CoverageUpdate()
    with pytest.raises(AssertionError):
        coverage.last_seen = np.zeros(4)


def test_status_round_trip():
    original = status()
    decoded, protocol = CODEC.decode_status(CODEC.encode_status(original))
    assert protocol == PROTOCOL_VERSION
    assert decoded.drone_id == 7 and decoded.phase is Phase.TRACK
    assert decoded.health is HealthLevel.DEGRADED and decoded.faults == original.faults
    assert decoded.position == HERE and decoded.goal == (15.0, 32.0)
    assert decoded.stamp == pytest.approx(NOW, abs=1e-9)
    assert decoded.command_sequence == 2 ** 40 and decoded.mission_sequence == 12
    assert decoded.velocity == pytest.approx((1.0, -2.0))  # float32 on the wire
    assert decoded.nearest_obstacle == pytest.approx(1.5)
    np.testing.assert_allclose(decoded.estimate.covariance, original.estimate.covariance)
    assert decoded.estimate.last_measurement_time == pytest.approx(NOW - 0.4, abs=1e-9)


def test_status_without_optional_parts():
    original = status(position=None, goal=None, estimate=None, nearest_obstacle=math.inf)
    msg = CODEC.encode_status(original)
    assert not msg.has_position and not msg.has_goal and not msg.has_target_estimate
    decoded, _ = CODEC.decode_status(msg)
    assert decoded.position is None and decoded.goal is None and decoded.estimate is None
    assert decoded.nearest_obstacle == math.inf


def corrupt(field, value):
    msg = CODEC.encode_status(status())
    target = msg
    *path, name = field.split('.')
    for part in path:
        target = getattr(target, part)
    setattr(target, name, value)
    return msg


@pytest.mark.parametrize('field, value', [
    ('phase', 9), ('health', 7), ('latitude', 91.0), ('longitude', math.nan),
    ('heading', math.inf), ('velocity_east', math.nan), ('goal_x', math.inf),
    ('nearest_obstacle', -1.0), ('stamp.nanosec', 1_000_000_000),
    ('target_estimate.covariance', np.full(16, math.nan)),
    ('target_estimate.covariance', -np.eye(4).reshape(16)),
    ('target_estimate.last_measurement_stamp.sec', 2 ** 31 - 1),
])
def test_malformed_status_is_rejected_as_validation_error(field, value):
    with pytest.raises(MessageValidationError):
        CODEC.decode_status(corrupt(field, value))


def test_status_from_another_protocol_version_reports_it():
    msg = CODEC.encode_status(status())
    msg.protocol_version = 1
    assert CODEC.decode_status(msg)[1] == 1  # the peer table, not the codec, refuses it


def test_coverage_round_trip_and_limits():
    update = CoverageUpdate(3, NOW, 9, True, np.array([0, 5, 4_000_000_000], dtype=np.uint32),
                            np.array([1.0, 2.5, NOW]))
    msg = CODEC.encode_coverage(update)
    assert isinstance(msg.cells, array.array) and msg.cells.typecode == 'I'
    decoded = CODEC.decode_coverage(msg)
    assert decoded.full and decoded.mission_sequence == 9
    assert list(decoded.cells) == [0, 5, 4_000_000_000]
    np.testing.assert_allclose(decoded.last_seen, [1.0, 2.5, NOW])
    empty = CODEC.decode_coverage(CODEC.encode_coverage(
        CoverageUpdate(3, NOW, 9, False, np.array([], dtype=np.uint32), np.array([]))))
    assert empty.cells.size == 0
    too_big = TYPES.CoverageUpdate()
    too_big.mission_sequence = 1
    too_big.cells = array.array('I', bytes(4 * (MAX_COVERAGE_CELLS + 1)))
    too_big.last_seen = array.array('d', bytes(8 * (MAX_COVERAGE_CELLS + 1)))
    with pytest.raises(MessageValidationError, match='exceeds'):
        CODEC.decode_coverage(too_big)


@pytest.mark.parametrize('mutate', [
    lambda m: setattr(m, 'last_seen', array.array('d', [1.0])),         # length mismatch
    lambda m: setattr(m, 'last_seen', array.array('d', [math.nan, 1.0])),
    lambda m: setattr(m, 'mission_sequence', 0),                         # no mission
])
def test_malformed_coverage_is_rejected(mutate):
    msg = CODEC.encode_coverage(CoverageUpdate(3, NOW, 9, False, [1, 2], [1.0, 2.0]))
    mutate(msg)
    with pytest.raises(MessageValidationError):
        CODEC.decode_coverage(msg)


def mission_spec():
    return MissionSpec(sequence=1_758_000_000_123, mission_id='forest-block 7', origin=HERE,
                       altitude=4.0, grid_resolution=5.0,
                       waypoints=(GeoPoint(47.3979, 8.5458),),
                       area=(GeoPoint(47.3974, 8.5460), GeoPoint(47.3974, 8.5470),
                             GeoPoint(47.3981, 8.5470)))


def test_mission_round_trip():
    decoded = CODEC.decode_mission(CODEC.encode_mission(mission_spec()))
    assert decoded.sequence == 1_758_000_000_123 and decoded.mission_id == 'forest-block 7'
    assert decoded.origin == HERE and decoded.area == mission_spec().area
    assert decoded.waypoints == mission_spec().waypoints and decoded.altitude == 4.0


@pytest.mark.parametrize('mutate', [
    lambda m: setattr(m, 'area_longitudes', array.array('d', [8.5])),     # unpaired
    lambda m: setattr(m, 'mission_id', 'bad\nid'),
    lambda m: setattr(m, 'altitude', math.nan),
    lambda m: setattr(m, 'sequence', 0),
    lambda m: setattr(m, 'origin_latitude', 90.5),
    lambda m: (setattr(m, 'area_latitudes', array.array('d', [47.0] * 300)),
               setattr(m, 'area_longitudes', array.array('d', [8.0] * 300))),
])
def test_malformed_missions_are_rejected(mutate):
    msg = CODEC.encode_mission(mission_spec())
    mutate(msg)
    with pytest.raises(MessageValidationError):
        CODEC.decode_mission(msg)


def test_command_round_trip_and_validation():
    command = SwarmCommand(42, CommandKind.RETURN_TO_LAUNCH, NOW, frozenset({3, 1}))
    msg = CODEC.encode_command(command)
    assert list(msg.drone_ids) == [1, 3] and msg.command == TYPES.SwarmCommand.RETURN_TO_LAUNCH
    assert CODEC.decode_command(msg) == command
    msg.command = 99
    with pytest.raises(MessageValidationError):
        CODEC.decode_command(msg)
    flood = CODEC.encode_command(command)
    flood.drone_ids = array.array('I', range(5000))
    with pytest.raises(MessageValidationError, match='exceeds'):
        CODEC.decode_command(flood)


def test_target_report_round_trip_and_validation():
    report = TargetReport(NOW, HERE, 1.5, 0.75)
    decoded = CODEC.decode_target_report(CODEC.encode_target_report(report))
    assert decoded.position == HERE and decoded.confidence == pytest.approx(0.75)
    msg = CODEC.encode_target_report(report)
    msg.confidence = 1.5
    with pytest.raises(MessageValidationError):
        CODEC.decode_target_report(msg)


def test_metrics_encode_unknowns_as_nan():
    snapshot = MetricsSnapshot(12.0, 3, 0.5, 0.25, 1, 0, 2, False, None, None, None, 1.2)
    msg = CODEC.encode_metrics(snapshot, NOW, 'mission')
    assert msg.header.frame_id == 'mission' and msg.drones_alive == 3
    assert math.isnan(msg.time_to_first_detection) and math.isnan(msg.min_separation)
    assert msg.min_obstacle_distance == 1.2 and msg.num_degraded == 2


def test_time_conversions():
    # Regression: scaling epoch seconds by 1e9 before splitting lost up to ~256 ns.
    stamp = seconds_to_time(NOW, TYPES.Time)
    assert (stamp.sec, stamp.nanosec) == (1_758_000_000, 250_000_000)
    assert time_to_seconds(stamp) == pytest.approx(NOW, abs=1e-9)
    assert seconds_to_time(1.9999999999, TYPES.Time).sec == 2
    assert seconds_to_time(-0.5, TYPES.Time).sec == -1  # nanosec stays non-negative
    for bad in (math.nan, math.inf, 2.0 ** 40):
        with pytest.raises(ValueError):
            seconds_to_time(bad, TYPES.Time)
