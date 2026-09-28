"""Tests for swarm_sar.core.avoidance: the drone-to-drone closing-speed constraints."""

import math

import numpy as np
import pytest
from swarm_sar.core.avoidance import (avoidance_radius, braking_speed, ClosingConstraint,
                                      Neighbor, separation_constraints, speed_bounds)

MIN_SEP = 3.0
MAX_SPEED = 3.0
MAX_ACCEL = 2.0
TAU = 0.6


def constraints(neighbors, own_id=0, position=(0.0, 0.0)):
    return separation_constraints(own_id, position, neighbors, MIN_SEP, MAX_SPEED, MAX_ACCEL,
                                  TAU)


def unit(angle_deg):
    a = math.radians(angle_deg)
    return np.array([[math.cos(a), math.sin(a)]])


def test_braking_speed_solves_the_stopping_equation():
    for gap in (3.5, 5.0, 12.0):
        c = braking_speed(gap, MIN_SEP, MAX_ACCEL, TAU)
        assert c * TAU + c * c / (2.0 * MAX_ACCEL) == pytest.approx(gap - MIN_SEP)
    assert braking_speed(MIN_SEP, MIN_SEP, MAX_ACCEL, TAU) == 0.0
    assert braking_speed(1.0, MIN_SEP, MAX_ACCEL, TAU) == 0.0
    assert braking_speed(10.0, MIN_SEP, MAX_ACCEL, 1.0) < braking_speed(10.0, MIN_SEP,
                                                                        MAX_ACCEL, 0.1)


def test_avoidance_radius_is_where_a_head_on_pair_first_matters():
    radius = avoidance_radius(MIN_SEP, MAX_SPEED, MAX_ACCEL, TAU)
    assert braking_speed(radius, MIN_SEP, MAX_ACCEL, TAU) == pytest.approx(2 * MAX_SPEED)
    assert avoidance_radius(0.0, MAX_SPEED, MAX_ACCEL, TAU) == 0.0
    assert constraints([Neighbor(1, (radius + 0.01, 0.0), (0.0, 0.0))]) == []
    assert len(constraints([Neighbor(1, (radius - 0.01, 0.0), (0.0, 0.0))])) == 1


def test_hovering_neighbour_limits_the_closing_speed_to_the_envelope():
    (c,) = constraints([Neighbor(7, (0.0, 6.0), (0.0, 0.0))])
    assert c.drone_id == 7 and c.gap == pytest.approx(6.0)
    assert c.normal == pytest.approx((0.0, 1.0))
    assert c.limit == pytest.approx(braking_speed(6.0, MIN_SEP, MAX_ACCEL, TAU))


def test_no_credit_for_a_neighbour_moving_away():
    # Regression: crediting a receding neighbour let followers close to 2.64 m (min 3 m)
    # whenever the leader braked.
    static = constraints([Neighbor(1, (6.0, 0.0), (0.0, 0.0))])[0].limit
    receding = constraints([Neighbor(1, (6.0, 0.0), (2.0, 0.0))])[0].limit
    assert receding == pytest.approx(static)


def test_a_neighbour_closing_in_tightens_the_limit_by_its_speed():
    static = constraints([Neighbor(1, (6.0, 0.0), (0.0, 0.0))])[0].limit
    closing = constraints([Neighbor(1, (6.0, 0.0), (-2.0, 0.0))])[0].limit
    assert closing == pytest.approx(static - 2.0)


def test_inside_min_separation_the_limit_forces_a_retreat():
    (c,) = constraints([Neighbor(1, (1.5, 0.0), (0.0, 0.0))])
    assert c.limit == pytest.approx(-MAX_SPEED * 0.5)
    low, high = speed_bounds(unit(180.0), [c])
    assert low[0] == pytest.approx(MAX_SPEED * 0.5) and high[0] == math.inf


def test_coincident_drones_get_opposite_normals():
    a = constraints([Neighbor(1, (0.0, 0.0), (0.0, 0.0))], own_id=0)[0]
    b = constraints([Neighbor(0, (0.0, 0.0), (0.0, 0.0))], own_id=1)[0]
    assert math.hypot(*a.normal) == pytest.approx(1.0)
    assert a.normal == pytest.approx((-b.normal[0], -b.normal[1]))
    assert a.limit < 0.0 and b.limit < 0.0


def test_speed_bounds_per_direction():
    c = ClosingConstraint(1, (1.0, 0.0), 1.0, 5.0)
    low, high = speed_bounds(np.vstack([unit(0.0), unit(60.0), unit(90.0), unit(180.0)]), [c])
    np.testing.assert_allclose(low, [0.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(high, [1.0, 2.0, math.inf, math.inf])


def test_speed_bounds_negative_limit_rules_out_sideways_and_toward():
    c = ClosingConstraint(1, (1.0, 0.0), -1.0, 2.0)
    low, high = speed_bounds(np.vstack([unit(0.0), unit(90.0), unit(180.0), unit(120.0)]), [c])
    assert low[0] > high[0]                  # toward: infeasible
    assert high[1] == -math.inf              # sideways cannot open the gap
    assert low[2] == pytest.approx(1.0)      # straight away: at least 1 m/s
    assert low[3] == pytest.approx(2.0)      # 60 deg off straight away: twice as fast


def test_speed_bounds_without_constraints_is_unbounded():
    low, high = speed_bounds(unit(33.0), [])
    assert low[0] == 0.0 and high[0] == math.inf
