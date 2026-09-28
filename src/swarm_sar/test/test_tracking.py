"""Tests for swarm_sar.core.tracking."""

import math

import numpy as np
import pytest
from swarm_sar.core.tracking import (ConstantVelocityTracker, covariance_intersection,
                                     Detection, TargetEstimate)


def estimate(x=0.0, y=0.0, vx=0.0, vy=0.0, cov=None, stamp=0.0, measured=0.0):
    return TargetEstimate(np.array([x, y, vx, vy]), np.eye(4) if cov is None else cov,
                          stamp, measured)


@pytest.mark.parametrize('cov', [np.array([[1.0, 2.0], [2.0, 1.0]]),
                                 np.array([[1.0, 0.5], [0.0, 1.0]]),
                                 np.array([[math.nan, 0.0], [0.0, 1.0]]),
                                 np.eye(3)])
def test_detection_rejects_invalid_covariance(cov):
    with pytest.raises(ValueError):
        Detection(0.0, (0.0, 0.0), cov)


def test_detection_isotropic_floors_zero_noise():
    detection = Detection.isotropic(1.0, (2.0, 3.0), 0.0)
    assert detection.covariance[0, 0] > 0.0
    with pytest.raises(ValueError):
        Detection.isotropic(math.nan, (0.0, 0.0), 1.0)


def test_estimate_validation_and_immutability():
    with pytest.raises(ValueError):
        estimate(x=math.inf)
    with pytest.raises(ValueError):
        TargetEstimate(np.zeros(3), np.eye(4), 0.0, 0.0)
    with pytest.raises(ValueError):
        estimate(cov=-np.eye(4))
    with pytest.raises(ValueError, match='newer'):
        estimate(stamp=1.0, measured=2.0)
    e = estimate()
    with pytest.raises(ValueError):
        e.state[0] = 1.0
    with pytest.raises(ValueError):
        e.covariance[0, 0] = 1.0


def test_predict_moves_with_velocity_grows_uncertainty_and_never_goes_back():
    tracker = ConstantVelocityTracker(accel_psd=0.5, max_speed=3.0)
    start = estimate(vx=1.0, vy=-2.0)
    later = tracker.predict(start, 2.0)
    assert later.position == pytest.approx((2.0, -4.0))
    assert later.position_std > start.position_std
    assert tracker.predict(later, 1.0) is later


def test_align_backwards_restamps_conservatively():
    tracker = ConstantVelocityTracker(accel_psd=0.5, max_speed=3.0)
    ahead = estimate(x=5.0, vx=1.0, stamp=10.5, measured=10.5)
    aligned = tracker.align(ahead, 10.0)
    assert aligned.stamp == 10.0 and aligned.last_measurement_time == 10.0
    assert aligned.position == ahead.position
    assert aligned.covariance[0, 0] == pytest.approx(1.0 + (3.0 * 0.5) ** 2)
    assert tracker.align(ahead, 11.0).stamp == 11.0  # forward is a plain prediction


def test_update_pulls_toward_measurement_and_shrinks_uncertainty():
    tracker = ConstantVelocityTracker(accel_psd=0.5, max_speed=3.0)
    prior = estimate(cov=np.diag([25.0, 25.0, 4.0, 4.0]))
    posterior = tracker.update(prior, Detection.isotropic(0.0, (10.0, 0.0), 1.0))
    assert 9.0 < posterior.position[0] < 10.0
    assert posterior.position_std < prior.position_std
    assert posterior.last_measurement_time == 0.0
    np.testing.assert_allclose(posterior.covariance, posterior.covariance.T)


def test_out_of_sequence_detection_is_applied_conservatively():
    tracker = ConstantVelocityTracker(accel_psd=0.5, max_speed=3.0)
    prior = estimate(cov=np.diag([25.0, 25.0, 4.0, 4.0]), stamp=5.0, measured=0.0)
    fresh = tracker.update(prior, Detection.isotropic(5.0, (10.0, 0.0), 1.0))
    late = tracker.update(prior, Detection.isotropic(4.0, (10.0, 0.0), 1.0))
    assert late.stamp == 5.0 and late.last_measurement_time == 4.0
    assert 0.0 < late.position[0] < fresh.position[0]


def _run_filter(rng, steps=60):
    tracker = ConstantVelocityTracker(accel_psd=0.1, max_speed=3.0)
    truth_v = np.array([1.2, -0.7])
    est = None
    errors = []
    for k in range(steps):
        t = 0.2 * k
        truth = np.array([10.0, 20.0]) + truth_v * t
        detection = Detection.isotropic(t, tuple(truth + rng.normal(0.0, 1.5, 2)), 1.5)
        est = tracker.initialize(detection) if est is None else tracker.update(est, detection)
        errors.append(math.dist(est.position, truth))
    return est, np.concatenate([truth, truth_v]), errors


def test_filter_converges_on_a_constant_velocity_target():
    est, _, errors = _run_filter(np.random.default_rng(42))
    assert np.mean(errors[-20:]) < 1.0  # well below the 1.5 m sensor noise
    assert est.position_std < 1.5


def test_filter_is_statistically_consistent():
    # Mean NEES over Monte-Carlo runs must not exceed the state dimension (4) by more
    # than sampling error: an overconfident filter would poison CI fusion downstream.
    rng = np.random.default_rng(7)
    nees = []
    for _ in range(200):
        est, truth, _ = _run_filter(rng, steps=40)
        err = est.state - truth
        nees.append(float(err @ np.linalg.solve(est.covariance, err)))
    assert 1.0 < np.mean(nees) < 4.6


def test_ci_is_idempotent_so_gossip_echoes_cannot_breed_overconfidence():
    a = estimate(x=3.0, cov=np.diag([4.0, 1.0, 2.0, 2.0]), stamp=1.0)
    fused = a
    for _ in range(10):
        fused = covariance_intersection(fused, a)
    np.testing.assert_allclose(fused.covariance, a.covariance)
    np.testing.assert_allclose(fused.state, a.state)


def test_ci_returns_the_dominant_estimate_unchanged():
    tight = estimate(x=1.0, cov=np.eye(4) * 0.5, measured=0.0)
    loose = estimate(x=5.0, cov=np.eye(4) * 3.0, measured=0.0)
    fused = covariance_intersection(loose, tight)
    np.testing.assert_allclose(fused.state, tight.state)


def test_ci_combines_complementary_information():
    good_x = estimate(x=0.0, y=0.0, cov=np.diag([0.1, 10.0, 1.0, 1.0]), measured=0.0)
    good_y = estimate(x=1.0, y=1.0, cov=np.diag([10.0, 0.1, 1.0, 1.0]), measured=0.0)
    fused = covariance_intersection(good_x, good_y)
    det = np.linalg.det
    assert det(fused.covariance) < min(det(good_x.covariance), det(good_y.covariance))
    assert 0.0 <= fused.position[0] <= 1.0 and 0.0 <= fused.position[1] <= 1.0
    # consistency: fused covariance is never tighter than the tighter input on each axis
    assert fused.covariance[0, 0] >= 0.1 - 1e-9 and fused.covariance[1, 1] >= 0.1 - 1e-9


def test_ci_keeps_the_newest_measurement_time_and_needs_equal_stamps():
    a = estimate(cov=np.diag([1.0, 2.0, 1.0, 1.0]), stamp=5.0, measured=4.0)
    b = estimate(cov=np.diag([2.0, 1.0, 1.0, 1.0]), stamp=5.0, measured=4.5)
    assert covariance_intersection(a, b).last_measurement_time == 4.5
    with pytest.raises(ValueError, match='same time'):
        covariance_intersection(a, estimate(stamp=6.0))


def test_tracker_rejects_bad_parameters():
    with pytest.raises(ValueError):
        ConstantVelocityTracker(accel_psd=0.0, max_speed=1.0)
    with pytest.raises(ValueError):
        ConstantVelocityTracker(accel_psd=1.0, max_speed=math.nan)
