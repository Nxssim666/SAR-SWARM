"""
Tests for swarm_sar.ros.px4 against verbatim PX4 v1.15 message definitions.

Every sign and unit crossing the NED/ENU boundary is pinned here, together
with the offboard protocol details PX4 rejects silently when wrong.
"""

import math

from fake_msgs import FakeMessages
import numpy as np
import pytest
from swarm_sar.core.controller import Setpoint, SetpointKind
from swarm_sar.core.frames import quat_multiply, quat_to_matrix
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.pose import FlightMode
from swarm_sar.core.supervisor import FcRequest
from swarm_sar.ros import px4
from swarm_sar.ros.codec import MessageValidationError

FAKES = FakeMessages()
TYPES = px4.Px4Types(*(FAKES.get(f'px4_msgs/{name}') for name in (
    'VehicleLocalPosition', 'VehicleAttitude', 'VehicleStatus', 'OffboardControlMode',
    'TrajectorySetpoint', 'VehicleCommand')))


def local_position(**fields):
    msg = TYPES.VehicleLocalPosition()
    defaults = {'x': 1.0, 'y': 2.0, 'z': -3.0, 'vx': 0.5, 'vy': -0.25, 'vz': 0.1,
                'xy_valid': True, 'z_valid': True, 'v_xy_valid': True,
                'heading_good_for_control': True, 'dead_reckoning': False, 'xy_global': True,
                'ref_lat': 47.397742, 'ref_lon': 8.545594, 'ref_timestamp': 1000}
    defaults.update(fields)
    for name, value in defaults.items():
        setattr(msg, name, value)
    return msg


def test_local_position_is_converted_from_ned_to_enu():
    report = px4.decode_local_position(local_position(), received_at=12.5)
    assert report.stamp == 12.5
    assert report.position == (2.0, 1.0, 3.0)        # east, north, up
    assert report.velocity == pytest.approx((-0.25, 0.5, -0.1))
    assert report.usable
    assert report.global_reference == GeoPoint(47.397742, 8.545594)


@pytest.mark.parametrize('fields', [
    {'xy_valid': False}, {'z_valid': False}, {'v_xy_valid': False},
    {'heading_good_for_control': False}, {'dead_reckoning': True}, {'x': math.nan},
    {'vy': math.inf},
])
def test_any_invalid_estimate_makes_the_position_unusable(fields):
    report = px4.decode_local_position(local_position(**fields), 0.0)
    assert not report.usable
    assert all(math.isfinite(v) for v in report.position + report.velocity)


@pytest.mark.parametrize('fields', [{'xy_global': False}, {'ref_lat': math.nan},
                                    {'ref_lat': 91.0}])
def test_missing_or_invalid_global_reference_is_none(fields):
    assert px4.decode_local_position(local_position(**fields), 0.0).global_reference is None


def test_reset_marker_covers_resets_and_a_new_reference_point():
    base = px4.decode_local_position(local_position(), 0.0).reset_marker
    for fields in ({'xy_reset_counter': 1}, {'z_reset_counter': 1},
                   {'heading_reset_counter': 1}, {'ref_timestamp': 2000}):
        assert px4.decode_local_position(local_position(**fields), 0.0).reset_marker != base


def test_attitude_facing_east_is_enu_heading_zero():
    msg = TYPES.VehicleAttitude()
    yaw = math.pi / 2  # PX4: nose east
    msg.q = np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)], dtype=np.float32)
    msg.quat_reset_counter = 3
    report = px4.decode_attitude(msg, 1.0)
    forward = quat_to_matrix(report.quaternion) @ [1.0, 0.0, 0.0]
    np.testing.assert_allclose(forward, [1.0, 0.0, 0.0], atol=1e-6)
    assert report.reset_counter == 3


def test_attitude_with_pitch_keeps_nose_up_as_positive_z():
    msg = TYPES.VehicleAttitude()
    pitch = math.radians(15.0)
    q_pitch = np.array([math.cos(pitch / 2), 0.0, math.sin(pitch / 2), 0.0])
    msg.q = np.asarray(quat_multiply(np.array([1.0, 0.0, 0.0, 0.0]), q_pitch), dtype=np.float32)
    forward = quat_to_matrix(px4.decode_attitude(msg, 1.0).quaternion) @ [1.0, 0.0, 0.0]
    assert forward[2] == pytest.approx(math.sin(pitch), abs=1e-6)  # facing north, nose up
    assert forward[1] == pytest.approx(math.cos(pitch), abs=1e-6)


def test_invalid_attitude_is_a_validation_error():
    msg = TYPES.VehicleAttitude()
    msg.q = np.zeros(4, dtype=np.float32)
    with pytest.raises(MessageValidationError):
        px4.decode_attitude(msg, 1.0)


@pytest.mark.parametrize('nav_state, mode', [
    (14, FlightMode.OFFBOARD), (4, FlightMode.HOLD), (5, FlightMode.RETURN),
    (18, FlightMode.LAND), (2, FlightMode.OTHER), (0, FlightMode.OTHER)])
def test_vehicle_status_modes(nav_state, mode):
    msg = TYPES.VehicleStatus()
    msg.nav_state = nav_state
    msg.arming_state = TYPES.VehicleStatus.ARMING_STATE_ARMED
    report = px4.decode_vehicle_status(msg, 2.0)
    assert report.mode is mode and report.armed
    msg.arming_state = TYPES.VehicleStatus.ARMING_STATE_DISARMED
    assert not px4.decode_vehicle_status(msg, 2.0).armed


def test_mode_constants_match_the_px4_definitions():
    status = TYPES.VehicleStatus
    assert px4.NAV_STATE_OFFBOARD == status.NAVIGATION_STATE_OFFBOARD
    assert px4.NAV_STATE_AUTO_LOITER == status.NAVIGATION_STATE_AUTO_LOITER
    assert px4.NAV_STATE_AUTO_RTL == status.NAVIGATION_STATE_AUTO_RTL
    assert px4.NAV_STATE_AUTO_LAND == status.NAVIGATION_STATE_AUTO_LAND
    assert px4.ARMING_STATE_ARMED == status.ARMING_STATE_ARMED
    command = TYPES.VehicleCommand
    assert px4.VEHICLE_CMD_DO_SET_MODE == command.VEHICLE_CMD_DO_SET_MODE
    assert px4.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH == command.VEHICLE_CMD_NAV_RETURN_TO_LAUNCH
    assert px4.VEHICLE_CMD_NAV_LAND == command.VEHICLE_CMD_NAV_LAND


def test_offboard_heartbeat_enables_position_and_velocity_only():
    msg = px4.encode_offboard_mode(TYPES, 1.25)
    assert msg.timestamp == 1_250_000
    assert msg.position and msg.velocity
    assert not (msg.acceleration or msg.attitude or msg.body_rate or msg.thrust_and_torque
                or msg.direct_actuator)


def test_position_setpoint_is_ned_with_no_velocity():
    sp = Setpoint(SetpointKind.POSITION, (2.0, 1.0, 3.0), (0.0, 0.0), 0.0)
    msg = px4.encode_trajectory_setpoint(TYPES, sp, 2.0)
    np.testing.assert_allclose(msg.position, [1.0, 2.0, -3.0])  # north, east, down
    assert np.all(np.isnan(msg.velocity)) and np.all(np.isnan(msg.acceleration))
    assert msg.yaw == pytest.approx(math.pi / 2)  # ENU heading 0 = east = PX4 yaw 90 deg
    assert math.isnan(msg.yawspeed)


def test_velocity_setpoint_flies_xy_by_velocity_and_holds_altitude():
    sp = Setpoint(SetpointKind.VELOCITY, (5.0, 6.0, 4.0), (1.5, -0.5), math.pi / 2)
    msg = px4.encode_trajectory_setpoint(TYPES, sp, 2.0)
    assert np.isnan(msg.position[0]) and np.isnan(msg.position[1])
    assert msg.position[2] == pytest.approx(-4.0)
    np.testing.assert_allclose(msg.velocity[:2], [-0.5, 1.5])  # north, east
    assert np.isnan(msg.velocity[2])
    assert msg.yaw == pytest.approx(0.0, abs=1e-7)  # facing north


@pytest.mark.parametrize('request_, command, params', [
    (FcRequest.HOLD, 176, (1.0, 4.0, 3.0)),
    (FcRequest.RETURN, 20, None),
    (FcRequest.LAND, 21, None),
])
def test_vehicle_commands(request_, command, params):
    msg = px4.encode_vehicle_command(TYPES, request_, target_system=3, now=4.0)
    assert msg.command == command and msg.timestamp == 4_000_000
    assert msg.target_system == 3 and msg.target_component == 1
    assert msg.source_component == px4.COMPANION_COMPONENT_ID and msg.from_external
    if params is not None:
        assert (msg.param1, msg.param2, msg.param3) == params
    if request_ is FcRequest.LAND:
        assert math.isnan(msg.param5) and math.isnan(msg.param6) and math.isnan(msg.param7)


def test_malformed_px4_messages_are_validation_errors():
    msg = local_position()
    object.__setattr__(msg, '_x', 'garbage')  # what a broken bridge could deliver
    with pytest.raises(MessageValidationError):
        px4.decode_local_position(msg, 0.0)
    status = TYPES.VehicleStatus()
    object.__setattr__(status, '_nav_state', None)
    with pytest.raises(MessageValidationError):
        px4.decode_vehicle_status(status, 0.0)
