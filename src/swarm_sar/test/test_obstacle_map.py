"""Tests for swarm_sar.core.obstacle_map: free only if recently seen free, never unknown."""

import math

import numpy as np
import pytest
from swarm_sar.core.depth import DepthScan
from swarm_sar.core.obstacle_map import ObstacleMap

RES = 0.2
SIZE = 30.0
MEMORY = 5.0
ALL_AROUND = np.linspace(-math.pi, math.pi, 720, endpoint=False)


def scan(t, origin=(0.0, 0.0), reach=6.0, bearings=ALL_AROUND, obstacles=()):
    bearings = np.asarray(bearings, dtype=float)
    return DepthScan(t, origin, bearings, np.full(bearings.shape, reach),
                     np.asarray(obstacles, dtype=float).reshape(-1, 2), 1.0)


def fresh_map(position=(0.0, 0.0)):
    m = ObstacleMap(RES, SIZE, MEMORY)
    m.recenter(position)
    return m


def cell(m, point):
    ox, oy = m.origin
    return int(math.floor((point[0] - ox) / RES)), int(math.floor((point[1] - oy) / RES))


def test_unobserved_space_is_blocked_beyond_the_self_clear_radius():
    m = fresh_map()
    blocked = m.blocked_offsets((0.0, 0.0), 5.0, now=0.0, self_clear_radius=1.0)
    gaps = np.hypot(blocked[:, 0], blocked[:, 1])
    assert blocked.shape[0] > 0
    assert gaps.min() > 1.0 and gaps.max() < 1.0 + 2 * RES  # only the ring bordering the disc
    assert not m.free_mask(0.0).any()


def test_observed_free_space_is_passable_until_the_memory_expires():
    m = fresh_map()
    m.integrate(scan(0.0))
    assert m.blocked_offsets((0.0, 0.0), 5.0, now=1.0, self_clear_radius=1.0).shape[0] == 0
    assert m.free_mask(MEMORY)[cell(m, (3.0, 0.0))]
    later = m.blocked_offsets((0.0, 0.0), 5.0, now=MEMORY + 0.1, self_clear_radius=1.0)
    assert later.shape[0] > 0  # forgotten: unknown again


def test_clearing_stops_one_cell_short_of_the_evidence():
    m = fresh_map()
    m.integrate(scan(0.0, reach=2.0, bearings=[0.0]))
    free = m.free_mask(0.0)
    assert free[cell(m, (1.5, 0.0))]
    assert not free[cell(m, (1.9, 0.0))]
    assert not free[cell(m, (0.0, 1.0))]  # other bearings were not observed


def test_obstacles_are_not_erased_by_later_free_rays():
    # Regression: rays grazing a trunk's flank from a new viewpoint cleared the flank cells,
    # which cost ~0.2 m of the achieved tree clearance in simulation.
    m = fresh_map()
    m.integrate(scan(0.0, obstacles=[(3.0, 0.0)]))
    m.integrate(scan(1.0, reach=6.0, bearings=[0.0]))  # a ray straight through the obstacle
    assert m.occupied_mask(1.0)[cell(m, (3.0, 0.0))]
    assert not m.free_mask(1.0)[cell(m, (3.0, 0.0))]
    blocked = m.blocked_offsets((0.0, 0.0), 5.0, now=1.0, self_clear_radius=1.0)
    assert np.min(np.hypot(blocked[:, 0] - 3.0, blocked[:, 1])) < RES


def test_obstacles_inside_the_self_clear_radius_are_always_blocked():
    m = fresh_map()
    m.integrate(scan(0.0, obstacles=[(0.6, 0.0)]))
    blocked = m.blocked_offsets((0.0, 0.0), 3.0, now=0.0, self_clear_radius=1.2)
    assert np.min(np.hypot(blocked[:, 0] - 0.6, blocked[:, 1])) < RES


def test_obstacle_memory_expires():
    m = fresh_map()
    m.integrate(scan(0.0, obstacles=[(3.0, 0.0)]))
    assert m.nearest_obstacle((0.0, 0.0), 0.0, 10.0) == pytest.approx(3.0, abs=RES)
    assert m.nearest_obstacle((0.0, 0.0), MEMORY + 0.1, 10.0) == math.inf
    assert m.nearest_obstacle((0.0, 0.0), 0.0, 2.0) == math.inf  # outside the query radius


def test_only_border_cells_are_returned():
    m = fresh_map()
    m.integrate(scan(0.0, reach=3.2))
    blocked = m.blocked_offsets((0.0, 0.0), 6.0, now=0.0, self_clear_radius=1.0)
    gaps = np.hypot(blocked[:, 0], blocked[:, 1])
    assert blocked.shape[0] > 0 and gaps.min() > 2.5 and gaps.max() < 3.5


def test_blocked_offsets_are_relative_to_the_query_position():
    m = fresh_map()
    m.integrate(scan(0.0, obstacles=[(3.0, 1.0)]))
    blocked = m.blocked_offsets((1.0, 1.0), 5.0, now=0.0, self_clear_radius=1.0)
    assert np.min(np.hypot(blocked[:, 0] - 2.0, blocked[:, 1])) < RES


def test_recentering_keeps_evidence_in_place():
    m = fresh_map()
    m.integrate(scan(0.0, obstacles=[(2.0, 0.0)]))
    m.recenter((1.0, 0.0))  # within size / 8: no shift
    assert m.origin == pytest.approx((-15.0, -15.0))
    m.recenter((6.0, 0.0))  # beyond size / 8 (3.75 m): shift by whole cells
    assert m.origin[0] == pytest.approx(-9.0)
    assert m.nearest_obstacle((6.0, 0.0), 0.0, 10.0) == pytest.approx(4.0, abs=RES)
    m.recenter((1000.0, 0.0))  # a jump beyond the map forgets everything
    assert m.nearest_obstacle((1000.0, 0.0), 0.0, 100.0) == math.inf


def test_points_outside_the_map_are_ignored():
    m = fresh_map()
    m.integrate(scan(0.0, reach=40.0, bearings=[0.0], obstacles=[(100.0, 0.0), (-3.0, 0.0)]))
    assert m.nearest_obstacle((0.0, 0.0), 0.0, 1000.0) == pytest.approx(3.0, abs=RES)


def test_first_query_centres_the_map_and_clear_forgets_everything():
    m = ObstacleMap(RES, SIZE, MEMORY)
    assert m.origin is None and m.nearest_obstacle((0.0, 0.0), 0.0, 10.0) == math.inf
    m.blocked_offsets((50.0, 50.0), 2.0, now=0.0, self_clear_radius=1.0)
    assert m.origin == pytest.approx((35.0, 35.0))
    m.integrate(scan(0.0, origin=(50.0, 50.0), obstacles=[(52.0, 50.0)]))
    m.clear()
    assert m.origin is None and not m.occupied_mask(0.0).any()


def test_map_dimensions_and_validation():
    m = ObstacleMap(RES, SIZE, MEMORY)
    assert m.cells_per_side == 150 and m.resolution == RES
    for args in ((0.0, SIZE, MEMORY), (RES, math.nan, MEMORY), (RES, SIZE, -1.0)):
        with pytest.raises(ValueError):
            ObstacleMap(*args)


def test_assumed_free_disc_can_be_anchored_away_from_the_vehicle():
    m = fresh_map()
    around_vehicle = m.blocked_offsets((2.0, 0.0), 3.0, now=0.0, self_clear_radius=1.0)
    anchored = m.blocked_offsets((2.0, 0.0), 3.0, now=0.0, self_clear_radius=1.0,
                                 self_clear_center=(0.0, 0.0))
    # Around the vehicle: the ring at 1 m. Anchored 2 m behind: the vehicle's own
    # surroundings are unobserved and outside the disc, so they block.
    assert np.hypot(around_vehicle[:, 0], around_vehicle[:, 1]).min() > 1.0
    assert np.hypot(anchored[:, 0], anchored[:, 1]).min() < 0.5
