"""Tests for swarm_sar.core.mission: projection, validation, geofence and frame links."""

import math

import numpy as np
import pytest
from swarm_sar.core.geodesy import GeoPoint, LocalProjection
from swarm_sar.core.geometry import distance, signed_area
from swarm_sar.core.messages import MissionSpec
from swarm_sar.core.mission import (build_mission_plan, FrameLink, geofence_violation,
                                    MAX_MISSION_EXTENT_M, MissionError)

ORIGIN = GeoPoint(47.397742, 8.545594)
FRAME = LocalProjection(ORIGIN)


def geo(points):
    return tuple(FRAME.to_geo(x, y) for x, y in points)


def spec(area, waypoints=(), resolution=5.0, **overrides):
    fields = {'sequence': 1, 'mission_id': 'test', 'origin': ORIGIN, 'altitude': 10.0,
              'grid_resolution': resolution, 'waypoints': geo(waypoints), 'area': geo(area)}
    fields.update(overrides)
    return MissionSpec(**fields)


SQUARE = ((30.0, -40.0), (110.0, -40.0), (110.0, 40.0), (30.0, 40.0))


def test_plan_projects_the_area_and_waypoints_into_the_mission_frame():
    plan = build_mission_plan(spec(SQUARE, waypoints=[(15.0, 20.0), (35.0, 0.0)]))
    assert plan.sequence == 1 and plan.altitude == 10.0
    np.testing.assert_allclose(plan.waypoints, [(15.0, 20.0), (35.0, 0.0)], atol=1e-6)
    assert signed_area(plan.area) == pytest.approx(80.0 * 80.0, rel=1e-6)
    assert plan.geometry.num_valid == 256


def test_clockwise_and_closed_areas_are_normalized():
    ring = list(SQUARE[::-1]) + [SQUARE[-1]]
    plan = build_mission_plan(spec(ring))
    assert len(plan.area) == 4 and signed_area(plan.area) > 0


@pytest.mark.parametrize('area, fragment', [
    (((0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0)), 'intersect'),
    (((0.0, 0.0), (3.0, 0.0), (0.0, 3.0)), 'minimum'),
    (((0.0, 0.0), (6000.0, 0.0), (6000.0, 100.0)), 'limit'),
])
def test_unflyable_areas_are_rejected_with_a_reason(area, fragment):
    with pytest.raises(MissionError, match=fragment):
        build_mission_plan(spec(area))


def test_far_waypoints_and_too_coarse_grids_are_rejected():
    with pytest.raises(MissionError, match='limit'):
        build_mission_plan(spec(SQUARE, waypoints=[(0.0, 5500.0)]))
    with pytest.raises(MissionError, match='finer'):
        build_mission_plan(spec(((0.0, 0.0), (8.0, 0.0), (0.0, 8.0)), resolution=100.0))
    assert MAX_MISSION_EXTENT_M == 5000.0


def test_geofence_checks_every_vertex_and_waypoint():
    plan = build_mission_plan(spec(SQUARE, waypoints=[(15.0, 20.0)]))
    assert geofence_violation(plan, (0.0, 0.0), 200.0) is None
    reason = geofence_violation(plan, (0.0, 0.0), 100.0)
    assert reason is not None and 'area vertex' in reason
    assert 'waypoint 0' in geofence_violation(plan, (-100.0, -100.0), 130.0)


def test_frame_link_round_trips_between_distant_frames():
    home = GeoPoint(47.40, 8.56)  # about 1.1 km from the mission origin
    link = FrameLink(LocalProjection(home), FRAME)
    for point in ((0.0, 0.0), (250.0, -40.0), (-900.0, 1200.0)):
        back = link.local_to_mission(link.mission_to_local(point))
        assert back == pytest.approx(point, abs=1e-6)
    # The mission origin lies where the drone's local frame says it does.
    origin_local = link.geo_to_local(ORIGIN)
    assert link.local_to_mission(origin_local) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert distance(origin_local, (0.0, 0.0)) == pytest.approx(
        math.hypot(*LocalProjection(home).to_local(ORIGIN)))
    assert link.local_to_geo(origin_local).latitude == pytest.approx(ORIGIN.latitude)
