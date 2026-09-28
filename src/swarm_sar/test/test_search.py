"""Tests for swarm_sar.core.search."""

import math

import numpy as np
import pytest
from swarm_sar.core.coverage import CoverageMap, GridGeometry
from swarm_sar.core.geometry import Bounds, distance, point_in_polygon
from swarm_sar.core.search import SearchPlanner

BOUNDS = Bounds(0.0, 0.0, 100.0, 100.0)
GRID = GridGeometry(BOUNDS, 5.0)
NOW = 0.0


def planner(geometry=GRID, **overrides):
    params = {'sensor_range': 10.0, 'distance_scale': 30.0, 'switch_ratio': 1.5,
              'arrival_radius': 3.0}
    params.update(overrides)
    return SearchPlanner(geometry, **params)


def test_region_mask_splits_between_two_drones_and_ignores_coincident_ones():
    p = planner()
    left = p.region_mask((25.0, 50.0), [(75.0, 50.0)])
    assert left[:10, :].all() and not left[10:, :].any()
    assert p.region_mask((50.0, 50.0), [(50.0, 50.0)]).all()
    assert p.region_mask((50.0, 50.0), []).sum() == GRID.num_valid


def test_footprint_gain_sums_density_under_the_disc():
    p = planner(sensor_range=5.0)  # radius of exactly one cell: a plus-shaped kernel of 5 cells
    gain = p.footprint_gain(np.ones(GRID.shape))
    assert gain[10, 10] == 5.0
    assert gain[0, 0] == 3.0  # corner: two neighbours fall outside the grid
    assert not p.footprint_gain(np.zeros(GRID.shape)).any()


def test_lone_drone_with_symmetric_unexplored_ring_does_not_stall():
    # Regression (v1): Lloyd iteration left a drone at the centre forever because the
    # centroid of a symmetric ring of unexplored ground is the drone itself.
    coverage = CoverageMap(GRID, revisit_period=100.0)
    centre = (50.0, 50.0)
    coverage.observe(centre, 10.0, t=0.0)
    plan = planner().plan(centre, [], coverage.priority(0.0), NOW)
    assert plan.reason == SearchPlanner.FRONTIER
    assert distance(plan.goal, centre) > 3.0


def test_goals_stay_inside_own_region():
    density = np.ones(GRID.shape)
    a_pos, b_pos = (20.0, 50.0), (80.0, 50.0)
    goal_a = planner().plan(a_pos, [b_pos], density, NOW).goal
    goal_b = planner().plan(b_pos, [a_pos], density, NOW).goal
    assert distance(goal_a, a_pos) <= distance(goal_a, b_pos)
    assert distance(goal_b, b_pos) <= distance(goal_b, a_pos)


def test_commitment_switches_only_for_a_clearly_better_goal():
    far_a, far_b = (92.5, 92.5), (22.5, 22.5)
    p = planner(distance_scale=1e6)  # isolate value from travel distance
    density = np.zeros(GRID.shape)
    density[18, 18] = 1.0  # cell A
    first = p.plan((10.0, 10.0), [], density, NOW)
    assert first.reason == SearchPlanner.FRONTIER and distance(first.goal, far_a) <= 10.0
    assert p.committed_goal == first.goal
    density[4, 4] = 1.2  # B is better, but not by the 1.5x switch ratio: stay on A
    second = p.plan((12.0, 12.0), [], density, NOW)
    assert second.reason == SearchPlanner.COMMITTED and second.goal == first.goal
    density[4, 4] = 2.0  # B is now clearly better (e.g. a datum appeared): switch
    third = p.plan((14.0, 14.0), [], density, NOW)
    assert third.reason == SearchPlanner.FRONTIER and distance(third.goal, far_b) <= 10.0


def test_commitment_released_when_goal_loses_value_or_is_reached():
    p = planner()
    density = np.zeros(GRID.shape)
    density[18, 18] = 1.0
    density[2, 2] = 1.0
    first = p.plan((50.0, 50.0), [], density, NOW)
    # the committed ground gets searched by someone else: re-plan elsewhere
    gx, gy = GRID.index_of(first.goal)
    density[max(gx - 2, 0):gx + 3, max(gy - 2, 0):gy + 3] = 0.0
    second = p.plan((50.0, 50.0), [], density, NOW)
    assert second.reason == SearchPlanner.FRONTIER and distance(second.goal, first.goal) > 20.0
    # arriving at the goal also releases the commitment
    assert p.plan(second.goal, [], density, NOW).reason != SearchPlanner.COMMITTED
    p.reset()
    assert p.committed_goal is None


def test_commitment_released_when_goal_leaves_my_region():
    p = planner(distance_scale=1e6)
    density = np.zeros(GRID.shape)
    density[18, 18] = 1.0
    density[2, 2] = 0.9
    first = p.plan((50.0, 50.0), [], density, NOW)
    assert distance(first.goal, (92.5, 92.5)) <= 10.0
    # A peer arrives next to the goal: that ground is now theirs.
    second = p.plan((50.0, 50.0), [(90.0, 90.0)], density, NOW)
    assert second.reason == SearchPlanner.FRONTIER
    assert distance(second.goal, (12.5, 12.5)) <= 10.0


def test_unreachable_goals_are_skipped_until_the_cooldown_expires():
    p = planner(distance_scale=1e6)
    density = np.zeros(GRID.shape)
    density[18, 18] = 1.0
    density[2, 2] = 0.5
    first = p.plan((50.0, 50.0), [], density, now=0.0)
    p.mark_unreachable(first.goal, radius=6.0, until=60.0)
    assert p.committed_goal is None
    during = p.plan((50.0, 50.0), [], density, now=30.0)
    assert distance(during.goal, first.goal) > 6.0
    after = p.plan((50.0, 50.0), [], density, now=61.0)
    assert distance(after.goal, first.goal) <= 10.0


def test_blocked_goal_is_still_observed_from_a_neighbouring_cell():
    p = planner(distance_scale=1e6)
    density = np.zeros(GRID.shape)
    density[10, 10] = 1.0
    goal = GRID.center_of(10, 10)
    p.mark_unreachable(goal, radius=0.0, until=100.0)
    plan = p.plan((20.0, 20.0), [], density, now=50.0)
    assert plan.reason == SearchPlanner.FRONTIER and plan.goal != goal
    assert distance(plan.goal, goal) <= 10.0  # its footprint still covers the ground


def test_mark_unreachable_blocks_at_least_the_goal_cell_and_never_shortens_a_block():
    p = planner(sensor_range=2.0, distance_scale=1e6)  # footprint = the cell itself
    density = np.zeros(GRID.shape)
    density[10, 10] = 1.0
    goal = GRID.center_of(10, 10)
    p.mark_unreachable(goal, radius=0.0, until=100.0)
    p.mark_unreachable(goal, radius=0.0, until=10.0)  # a later, shorter block must not win
    assert p.plan((20.0, 20.0), [], density, now=50.0).reason == SearchPlanner.IDLE
    assert p.plan((20.0, 20.0), [], density, now=101.0).goal == goal


def test_idle_when_nothing_is_left_to_search():
    plan = planner().plan((10.0, 10.0), [(90.0, 90.0)], np.zeros(GRID.shape), NOW)
    assert plan.reason == SearchPlanner.IDLE
    assert plan.value == 0.0
    assert plan.goal[0] + plan.goal[1] < 100.0  # inside the lower-left region


def test_idle_goal_lies_inside_a_non_convex_area():
    # Regression: the mean of an L-shaped region's cells lies in the notch, outside the area;
    # idling there would park the drone outside the mission polygon.
    l_shape = ((0.0, 0.0), (100.0, 0.0), (100.0, 20.0), (20.0, 20.0), (20.0, 100.0),
               (0.0, 100.0))
    grid = GridGeometry(BOUNDS, 5.0, l_shape)
    plan = planner(grid).plan((10.0, 10.0), [], np.zeros(grid.shape), NOW)
    assert plan.reason == SearchPlanner.IDLE
    assert point_in_polygon(plan.goal, l_shape)


def test_degenerate_region_falls_back_to_exact_voronoi_centroid():
    # A drone boxed in by four close neighbours owns no cell centre at all.
    me = (50.0, 50.0)
    boxed_in = [(51.0, 50.0), (49.0, 50.0), (50.0, 51.0), (50.0, 49.0)]
    plan = planner().plan(me, boxed_in, np.ones(GRID.shape), NOW)
    assert plan.reason == SearchPlanner.DEGENERATE
    assert distance(plan.goal, me) < 1.0


def test_plan_rejects_mismatched_density_and_bad_parameters():
    with pytest.raises(ValueError, match='shape'):
        planner().plan((10.0, 10.0), [], np.ones((3, 3)), NOW)
    with pytest.raises(ValueError):
        planner(switch_ratio=0.9)
    with pytest.raises(ValueError):
        planner(sensor_range=-1.0)
    with pytest.raises(ValueError):
        planner(arrival_radius=math.nan)
