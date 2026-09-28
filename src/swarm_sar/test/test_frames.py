"""
Tests for swarm_sar.core.frames: every sign convention between ENU, NED, FRD and optical.

A wrong sign here makes the drone fly (or look) the wrong way, and the
camera-based safety net cannot catch it because the camera would be
looking the wrong way too. So every axis and rotation direction is pinned.
"""

import math

import numpy as np
import pytest
from swarm_sar.core.frames import (CameraMount, enu_to_ned, euler_frd, heading_from_rotation,
                                   heading_to_px4_yaw, level_attitude, ned_to_enu,
                                   px4_attitude_to_enu, px4_yaw_to_heading, quat_multiply,
                                   quat_normalized, quat_slerp, quat_to_matrix, R_ENU_NED)
from swarm_sar.core.geometry import wrap_angle


def test_ned_enu_swap_axes_and_flip_z():
    assert ned_to_enu((1.0, 2.0, 3.0)) == (2.0, 1.0, -3.0)  # north 1, east 2, down 3
    assert enu_to_ned(ned_to_enu((1.0, 2.0, 3.0))) == (1.0, 2.0, 3.0)
    np.testing.assert_allclose(R_ENU_NED @ np.array([1.0, 2.0, 3.0]), [2.0, 1.0, -3.0])


def _same_angle(a, b):
    return abs(wrap_angle(a - b)) < 1e-9


@pytest.mark.parametrize('yaw_deg, heading_deg', [(0, 90), (90, 0), (180, -90), (-90, 180),
                                                  (45, 45)])
def test_px4_yaw_and_enu_heading(yaw_deg, heading_deg):
    # PX4 yaw 0 = north, 90 = east (clockwise); ENU heading 0 = east, 90 = north (ccw).
    heading = px4_yaw_to_heading(math.radians(yaw_deg))
    assert _same_angle(heading, math.radians(heading_deg))
    assert _same_angle(heading_to_px4_yaw(heading), math.radians(yaw_deg))


def test_quaternion_helpers():
    q = quat_normalized([1.05, 0.0, 0.0, 0.0])  # float drift is renormalized, not rejected
    with pytest.raises(ValueError):
        quat_normalized([1.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        quat_normalized([math.nan, 0.0, 0.0, 1.0])
    with pytest.raises(ValueError, match='unit'):
        quat_normalized([5.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(q, [1.0, 0.0, 0.0, 0.0])
    about_z = np.array([math.cos(0.25), 0.0, 0.0, math.sin(0.25)])  # 0.5 rad about z
    np.testing.assert_allclose(quat_to_matrix(quat_multiply(about_z, about_z)),
                               quat_to_matrix(np.array([math.cos(0.5), 0, 0, math.sin(0.5)])),
                               atol=1e-12)
    half = quat_slerp(np.array([1.0, 0, 0, 0]), np.array([math.cos(0.5), 0, 0, math.sin(0.5)]),
                      0.5)
    np.testing.assert_allclose(half, about_z, atol=1e-12)


@pytest.mark.parametrize('heading', [0.0, math.pi / 2, math.pi, -math.pi / 2, 0.3, -2.0])
def test_level_attitude_points_the_nose_along_the_heading(heading):
    rotation = quat_to_matrix(level_attitude(heading))
    forward = rotation @ np.array([1.0, 0.0, 0.0])
    down = rotation @ np.array([0.0, 0.0, 1.0])
    np.testing.assert_allclose(forward, [math.cos(heading), math.sin(heading), 0.0], atol=1e-12)
    np.testing.assert_allclose(down, [0.0, 0.0, -1.0], atol=1e-12)
    assert heading_from_rotation(rotation) == pytest.approx(heading)


def test_px4_attitude_conversion_for_a_vehicle_facing_east_nose_up():
    # PX4: yaw 90 deg (east), pitch +10 deg (nose up), as FRD-to-NED quaternion.
    yaw, pitch = math.radians(90.0), math.radians(10.0)
    q_yaw = np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])
    q_pitch = np.array([math.cos(pitch / 2), 0.0, math.sin(pitch / 2), 0.0])
    q_ned_frd = quat_multiply(q_yaw, q_pitch)
    rotation = quat_to_matrix(px4_attitude_to_enu(q_ned_frd))
    forward = rotation @ np.array([1.0, 0.0, 0.0])
    assert forward[0] == pytest.approx(math.cos(pitch))  # east
    assert forward[1] == pytest.approx(0.0, abs=1e-12)   # no north component
    assert forward[2] == pytest.approx(math.sin(pitch))  # nose up = ENU +z
    right = rotation @ np.array([0.0, 1.0, 0.0])
    np.testing.assert_allclose(right, [0.0, -1.0, 0.0], atol=1e-12)  # facing east, right is south


def test_euler_frd_signs():
    forward = np.array([1.0, 0.0, 0.0])
    up_pitch = euler_frd(0.0, math.radians(30.0), 0.0) @ forward
    assert up_pitch[2] < 0.0  # FRD z is down: pitch up lifts the nose
    right_yaw = euler_frd(0.0, 0.0, math.radians(30.0)) @ forward
    assert right_yaw[1] > 0.0
    right_roll = euler_frd(math.radians(30.0), 0.0, 0.0) @ np.array([0.0, 1.0, 0.0])
    assert right_roll[2] > 0.0  # roll right lowers the right side


def test_camera_mount_maps_optical_axes_to_the_body():
    mount = CameraMount.from_degrees((0.1, 0.0, 0.0), (0.0, 0.0, 0.0))
    r = mount.r_frd_optical
    np.testing.assert_allclose(r @ [0.0, 0.0, 1.0], [1.0, 0.0, 0.0])  # optical z = forward
    np.testing.assert_allclose(r @ [1.0, 0.0, 0.0], [0.0, 1.0, 0.0])  # optical x = right
    np.testing.assert_allclose(r @ [0.0, 1.0, 0.0], [0.0, 0.0, 1.0])  # optical y = down
    tilted = CameraMount.from_degrees((0.0, 0.0, 0.0), (0.0, -20.0, 0.0))
    look = tilted.r_frd_optical @ [0.0, 0.0, 1.0]
    assert look[2] == pytest.approx(math.sin(math.radians(20.0)))  # looks down
    with pytest.raises(ValueError):
        CameraMount((0.0, 0.0, 0.0), roll=4.0)
    with pytest.raises(ValueError):
        CameraMount((0.0, 0.0), 0.0)
