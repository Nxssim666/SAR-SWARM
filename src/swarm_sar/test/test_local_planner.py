"""Tests for swarm_sar.core.local_planner, including closed-loop encounters."""

import math

import numpy as np
import pytest
from swarm_sar.core.avoidance import Neighbor
from swarm_sar.core.config import braking_limited_speed, DroneConfig
from swarm_sar.core.depth import DepthScan
from swarm_sar.core.local_planner import braking_speeds, free_distances, LocalPlanner
from swarm_sar.core.obstacle_map import ObstacleMap
from swarm_sar.sim.vehicle import SimVehicle

CFG = DroneConfig()
HALF_FOV = math.radians(43.5)
DT = CFG.control_period
ALL_AROUND = np.linspace(-math.pi, math.pi, 720, endpoint=False)


def planner(config=CFG):
    p = LocalPlanner(config)
    p.set_field_of_view(HALF_FOV)
    return p


def empty_map(config=CFG):
    return ObstacleMap(config.map_resolution, config.map_size, config.map_memory)


def scan_of(t, origin, points=(), reach=8.0, bearings=ALL_AROUND):
    """Return a perfect planar scan: free along each bearing up to the first obstacle."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    bearings = np.asarray(bearings, dtype=float)
    free = np.full(bearings.shape, reach)
    if pts.shape[0]:
        dx, dy = pts[:, 0] - origin[0], pts[:, 1] - origin[1]
        for i, b in enumerate(bearings):
            along = dx * math.cos(b) + dy * math.sin(b)
            perp = np.abs(dy * math.cos(b) - dx * math.sin(b))
            ahead = (along > 0.0) & (perp < 0.1)
            if ahead.any():
                free[i] = min(reach, float(along[ahead].min()))
    visible = np.hypot(pts[:, 0] - origin[0], pts[:, 1] - origin[1]) <= reach
    return DepthScan(t, origin, bearings, free, pts[visible], 1.0)


def seen_map(position=(0.0, 0.0), points=(), t=0.0):
    m = empty_map()
    m.recenter(position)
    m.integrate(scan_of(t, position, points))
    return m


def wall(x, y_from, y_to):
    return [(x, y) for y in np.arange(y_from, y_to + 1e-9, 0.1)]


def test_free_distances_geometry():
    blocked = np.array([[5.0, 0.0]])
    free = free_distances(blocked, np.array([0.0, math.pi / 2, math.pi]), 1.0, 8.0)
    np.testing.assert_allclose(free, [4.0, 8.0, 8.0])
    inside = free_distances(np.array([[0.5, 0.0]]), np.array([0.0, math.pi]), 1.0, 8.0)
    np.testing.assert_allclose(inside, [0.0, 8.0])  # moving away from a cell in the disc is fine
    assert free_distances(np.empty((0, 2)), np.array([0.3]), 1.0, 8.0)[0] == 8.0
    grazing = free_distances(np.array([[5.0, 0.6]]), np.array([0.0]), 1.0, 8.0)
    assert grazing[0] == pytest.approx(5.0 - 0.8)


def test_braking_speeds_match_the_config_helper():
    d = np.array([-1.0, 0.0, 0.4, 4.05, 20.0])
    expected = [braking_limited_speed(x, CFG.max_accel, CFG.reaction_time) for x in d]
    np.testing.assert_allclose(braking_speeds(d, CFG.max_accel, CFG.reaction_time), expected)


def test_no_travel_before_the_camera_field_of_view_is_known():
    p = LocalPlanner(CFG)
    assert p.view_half_angle is None
    result = p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), seen_map(), [], 0.0, DT)
    assert result.velocity == (0.0, 0.0) and result.blocked
    with pytest.raises(ValueError):
        p.set_field_of_view(0.0)
    with pytest.raises(ValueError):
        p.set_field_of_view(math.nan)


def test_speeds_up_gradually_and_brakes_at_once():
    p, m = planner(), seen_map()
    speeds = [math.hypot(*p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT).velocity)
              for _ in range(20)]
    np.testing.assert_allclose(speeds[:3], [0.2, 0.4, 0.6])
    assert speeds[-1] == pytest.approx(CFG.max_speed)
    blocked_ahead = seen_map(points=wall(2.0, -5.0, 5.0))
    result = p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), blocked_ahead, [], 0.0, DT)
    free = 2.0 - CFG.obstacle_clearance - CFG.map_resolution
    assert math.hypot(*result.velocity) <= braking_limited_speed(free, CFG.max_accel,
                                                                 CFG.reaction_time) + 1e-9


def test_unobserved_space_only_allows_the_self_clear_creep():
    p, m = planner(), empty_map()
    allowance = braking_limited_speed(CFG.self_clear_radius - CFG.obstacle_clearance,
                                      CFG.max_accel, CFG.reaction_time)
    for _ in range(10):
        result = p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
        assert math.hypot(*result.velocity) <= allowance + 1e-9


def test_never_translates_outside_the_camera_view():
    # Regression: without the view limit a slow sideways or backwards drift could creep
    # into never-observed space, since the self-clear disc moves with the vehicle.
    p, m = planner(), seen_map()
    for _ in range(10):
        result = p.plan(0, (0.0, 0.0), 0.0, (0.0, -3.0), m, [], 0.0, DT)
        direction = math.atan2(result.velocity[1], result.velocity[0])
        assert abs(direction) <= HALF_FOV + 1e-9
        assert result.velocity[1] < 0.0  # still makes progress toward the south
    behind = planner().plan(0, (0.0, 0.0), 0.0, (-3.0, 0.0), m, [], 0.0, DT)
    assert behind.velocity == (0.0, 0.0) and behind.blocked
    assert behind.heading == pytest.approx(math.pi)  # turn the camera toward the goal


def test_camera_yaw_shifts_the_view_and_the_heading():
    config = DroneConfig(camera_rpy_deg=(0.0, 0.0, 90.0))  # camera looks to the right
    p, m = planner(config), seen_map()
    result = None
    for _ in range(10):
        result = p.plan(0, (0.0, 0.0), 0.0, (0.0, -3.0), m, [], 0.0, DT)
    assert result.velocity[1] < -0.5 and abs(result.velocity[0]) < 1e-6
    assert result.heading == pytest.approx(0.0, abs=1e-9)  # nose east, camera south
    east = planner(config).plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
    direction = math.atan2(east.velocity[1], east.velocity[0])
    assert abs(direction + math.pi / 2) <= HALF_FOV + 1e-9  # only where the camera looks
    assert east.velocity[0] > 0.0


def test_heading_follows_travel_when_fast_and_looks_at_the_goal_when_slow():
    p, m = planner(), seen_map()
    first = p.plan(0, (0.0, 0.0), 0.0, (3.0, 1.0), m, [], 0.0, DT, look_heading=1.0)
    assert first.heading == pytest.approx(1.0)  # 0.2 m/s: below yaw_follow_speed
    for _ in range(5):
        result = p.plan(0, (0.0, 0.0), 0.0, (3.0, 1.0), m, [], 0.0, DT, look_heading=1.0)
    assert result.heading == pytest.approx(math.atan2(result.velocity[1], result.velocity[0]))


def test_stops_short_of_a_wall_and_reports_blocked():
    p, m = planner(), seen_map(points=wall(3.0, -8.0, 8.0))
    x, result = 0.0, None
    for step in range(100):
        result = p.plan(0, (x, 0.0), 0.0, (3.0, 0.0), m, [], step * DT * 0.01, DT)
        x += result.velocity[0] * DT
    assert result.blocked and result.velocity == (0.0, 0.0) and not result.yielding
    assert 3.0 - x >= CFG.obstacle_clearance
    assert 3.0 - x < CFG.obstacle_clearance + 0.6


def test_assumed_free_disc_stays_where_the_vehicle_stood_still():
    # Regression: a disc that moved with the vehicle let it slide past trunk flanks it had
    # never seen (0.74 m from a trunk with 0.8 m clearance configured, in simulation).
    p = planner()
    m = seen_map(points=[], t=0.0)
    p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
    assert p.self_clear_center == (0.0, 0.0)
    p.plan(0, (0.5, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
    assert p.self_clear_center == (0.0, 0.0)  # moving: the disc stays behind
    p.reset()
    p.plan(0, (0.5, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
    assert p.self_clear_center == (0.5, 0.0)


def test_moving_vehicle_does_not_assume_its_unseen_surroundings_free():
    p = planner()
    m = empty_map()  # nothing observed at all
    first = p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
    assert math.hypot(*first.velocity) > 0.0  # leaving a hover inside the disc is allowed
    x, result = 0.0, first
    for _ in range(40):
        x += result.velocity[0] * DT
        result = p.plan(0, (x, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
        if result.velocity == (0.0, 0.0):
            break
    # Without observations it can never get further than the disc lets it.
    assert x <= CFG.self_clear_radius


def _fly(starts, goals, headings, obstacles=(), steps=400):
    """Fly a closed loop: perfect planar sensing inside the camera view, exact peers."""
    vehicles = [SimVehicle((x, y, 4.0), h, 3.0, math.radians(60.0), 1.5)
                for (x, y), h in zip(starts, headings)]
    planners = [planner() for _ in vehicles]
    maps = [empty_map() for _ in vehicles]
    closest_pair, closest_obstacle = math.inf, math.inf
    pts = np.asarray(obstacles, dtype=float).reshape(-1, 2)
    for step in range(steps):
        now = step * DT
        commands = []
        for i, v in enumerate(vehicles):
            here = (float(v.position[0]), float(v.position[1]))
            view = v.heading + np.linspace(-HALF_FOV, HALF_FOV, 88)
            maps[i].recenter(here)
            maps[i].integrate(scan_of(now, here, pts, bearings=view))
            goal = goals[i]
            desired = (0.0, 0.0) if goal is None else (
                CFG.approach_gain * (goal[0] - here[0]), CFG.approach_gain * (goal[1] - here[1]))
            others = [Neighbor(j, (float(o.position[0]), float(o.position[1])),
                               (float(o.velocity[0]), float(o.velocity[1])))
                      for j, o in enumerate(vehicles) if j != i]
            commands.append(planners[i].plan(i, here, v.heading, desired, maps[i], others, now,
                                             DT))
        for v, c in zip(vehicles, commands):
            v.step(c.velocity, 4.0, c.heading, DT)
        for i, a in enumerate(vehicles):
            if pts.shape[0]:
                closest_obstacle = min(closest_obstacle, float(np.min(
                    np.hypot(pts[:, 0] - a.position[0], pts[:, 1] - a.position[1]))))
            for b in vehicles[i + 1:]:
                closest_pair = min(closest_pair, float(np.linalg.norm(a.position - b.position)))
    return vehicles, closest_pair, closest_obstacle


def test_head_on_drones_both_arrive_and_keep_their_separation():
    vehicles, closest, _ = _fly([(-20.0, 0.0), (20.0, 0.0)], [(20.0, 0.0), (-20.0, 0.0)],
                                [0.0, math.pi])
    assert closest >= 0.95 * CFG.min_separation
    assert np.hypot(*(vehicles[0].position[:2] - (20.0, 0.0))) < 2.0
    assert np.hypot(*(vehicles[1].position[:2] - (-20.0, 0.0))) < 2.0


def test_slides_past_a_hovering_drone_on_its_path():
    vehicles, closest, _ = _fly([(-20.0, 0.0), (0.0, 0.0)], [(20.0, 0.0), None],
                                [0.0, math.pi / 2])
    assert closest >= 0.95 * CFG.min_separation
    assert np.hypot(*(vehicles[0].position[:2] - (20.0, 0.0))) < 2.0


def test_detours_around_a_post_keeping_the_clearance():
    post = [(8.0 + 0.3 * math.cos(a), 0.3 * math.sin(a))
            for a in np.linspace(0.0, 2 * math.pi, 24, endpoint=False)]
    vehicles, _, closest = _fly([(0.0, 0.0)], [(16.0, 0.0)], [0.0], obstacles=post, steps=300)
    assert closest >= CFG.obstacle_clearance - 0.05
    assert np.hypot(*(vehicles[0].position[:2] - (16.0, 0.0))) < 2.0


def test_escapes_a_drone_that_is_too_close_even_outside_the_view():
    p = planner()
    m = seen_map()
    intruder = [Neighbor(1, (1.5, 0.0), (0.0, 0.0))]  # ahead and inside min_separation
    result = p.plan(0, (0.0, 0.0), 0.0, (0.0, 0.0), m, intruder, 0.0, DT)
    assert not result.blocked
    assert result.velocity[0] <= -CFG.max_speed * 0.5 + 1e-9  # straight back, at least this fast
    assert abs(result.heading) == pytest.approx(math.pi)       # and turn to see where it goes


def test_flies_the_desired_velocity_unchanged_when_it_is_safe():
    p, m = planner(), seen_map()
    far = [Neighbor(1, (8.0, 0.0), (0.0, 0.0))]  # close enough to count, too far to bind
    for _ in range(20):
        result = p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, far, 0.0, DT)
    assert result.velocity == pytest.approx((CFG.max_speed, 0.0))
    assert not result.yielding


def test_prefers_passing_on_the_right_and_reports_yielding():
    p, m = planner(), seen_map()
    hovering = [Neighbor(1, (5.0, 0.0), (0.0, 0.0))]
    for _ in range(10):
        result = p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, hovering, 0.0, DT)
    assert result.velocity[1] < 0.0  # heading east, right is south
    assert result.yielding           # a drone, not an obstacle, is in the way


def test_reset_forgets_the_speed_history():
    p, m = planner(), seen_map()
    for _ in range(5):
        p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
    p.reset()
    result = p.plan(0, (0.0, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
    assert math.hypot(*result.velocity) == pytest.approx(CFG.max_accel * DT)


def trunk(x, y, radius=0.3):
    return [(x + radius * math.cos(a), y + radius * math.sin(a))
            for a in np.linspace(0.0, 2 * math.pi, 24, endpoint=False)]


def test_blocked_by_a_seen_obstacle_it_looks_for_a_way_around():
    # Regression: a drone facing a trunk between it and its goal kept the camera on the
    # goal, so every direction it could see stayed blocked and it waited forever.
    view = np.linspace(-HALF_FOV, HALF_FOV, 88)
    m = empty_map()
    m.recenter((0.0, 0.0))
    # Crept up until the trunk's cells sit just outside the corridor (1.0 m ahead).
    m.integrate(scan_of(0.0, (0.1, 0.0), trunk(1.4, 0.0), bearings=view))
    result = planner().plan(0, (0.1, 0.0), 0.0, (3.0, 0.0), m, [], 0.0, DT)
    assert result.blocked and result.velocity == (0.0, 0.0)
    assert HALF_FOV < abs(result.heading) < math.pi / 2  # beside the trunk, not at it
    assert result.heading < 0.0                          # and to the right first


def test_blocked_only_by_unobserved_space_it_looks_at_the_goal():
    result = planner().plan(0, (0.0, 0.0), 0.0, (0.0, -3.0), empty_map(), [], 0.0, DT,
                            look_heading=-1.2)
    assert result.heading == pytest.approx(-1.2)
