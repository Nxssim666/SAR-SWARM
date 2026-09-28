"""Tests for swarm_sar.core.pose: flight-controller reports and the pose history."""

import math

import numpy as np
import pytest
from swarm_sar.core.frames import level_attitude
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.pose import (AttitudeReport, LocalPositionReport, PoseHistory, PoseSample)


def report(**overrides):
    fields = {'stamp': 1.0, 'position': (1.0, 2.0, 3.0), 'velocity': (0.5, 0.0, 0.0),
              'xy_valid': True, 'z_valid': True, 'v_xy_valid': True, 'heading_valid': True,
              'dead_reckoning': False, 'global_reference': GeoPoint(47.0, 8.0),
              'reset_marker': (0, 0, 0)}
    fields.update(overrides)
    return LocalPositionReport(**fields)


def sample(t, x=0.0, heading=0.0):
    return PoseSample(t, (x, 0.0, 4.0), (1.0, 0.0, 0.0), level_attitude(heading))


@pytest.mark.parametrize('flag', ['xy_valid', 'z_valid', 'v_xy_valid', 'heading_valid'])
def test_local_position_is_unusable_when_any_estimate_is_invalid(flag):
    assert report().usable
    assert not report(**{flag: False}).usable


def test_dead_reckoning_makes_the_position_unusable():
    assert not report(dead_reckoning=True).usable


def test_local_position_validation():
    with pytest.raises(ValueError):
        report(position=(1.0, 2.0))
    with pytest.raises(ValueError):
        report(velocity=(math.nan, 0.0, 0.0))
    with pytest.raises(ValueError):
        report(stamp=math.inf)


def test_attitude_report_normalizes_and_freezes_the_quaternion():
    a = AttitudeReport(0.0, [1.02, 0.0, 0.0, 0.0], 0)
    np.testing.assert_allclose(a.quaternion, [1.0, 0.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        a.quaternion[0] = 0.5
    with pytest.raises(ValueError):
        AttitudeReport(0.0, [0.0, 0.0, 0.0, 0.0], 0)
    with pytest.raises(ValueError):
        AttitudeReport(math.nan, [1.0, 0.0, 0.0, 0.0], 0)


def test_pose_sample_derives_rotation_and_heading():
    s = sample(0.0, heading=1.0)
    assert s.heading == pytest.approx(1.0)
    np.testing.assert_allclose(s.rotation @ [1.0, 0.0, 0.0], [math.cos(1.0), math.sin(1.0), 0.0])
    with pytest.raises(ValueError):
        s.rotation[0, 0] = 2.0


def test_history_interpolates_position_and_attitude():
    h = PoseHistory(2.0)
    h.append(sample(0.0, x=0.0, heading=0.0))
    h.append(sample(1.0, x=2.0, heading=1.0))
    mid = h.at(0.25, tolerance=0.1)
    assert mid.stamp == 0.25
    assert mid.position[0] == pytest.approx(0.5)
    assert mid.heading == pytest.approx(0.25)


def test_history_answers_recent_requests_with_the_latest_sample_only_within_tolerance():
    h = PoseHistory(2.0)
    h.append(sample(1.0))
    assert h.at(1.05, tolerance=0.1) is h.latest
    assert h.at(1.2, tolerance=0.1) is None
    assert h.at(0.5, tolerance=0.1) is None  # older than the buffer: never a wrong pose
    assert h.at(math.nan, tolerance=0.1) is None
    assert PoseHistory(1.0).at(0.0, 1.0) is None


def test_history_drops_out_of_order_samples_and_old_ones():
    h = PoseHistory(1.0)
    assert h.append(sample(1.0))
    assert not h.append(sample(1.0))
    assert not h.append(sample(0.5))
    for t in (1.5, 2.0, 2.4):
        h.append(sample(t))
    assert len(h) == 3 and h.at(1.2, 0.1) is None  # 1.0 fell out of the 1 s horizon
    h.clear()
    assert len(h) == 0 and h.latest is None
    with pytest.raises(ValueError):
        PoseHistory(0.0)
