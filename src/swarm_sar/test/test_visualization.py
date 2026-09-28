"""Tests for swarm_sar.ros.visualization against strict fakes of the standard messages."""

import array
import math

from fake_msgs import FakeMessages
import numpy as np
import pytest
from swarm_sar.core.coverage import grid_geometry, NEVER_SEEN
from swarm_sar.core.geodesy import GeoPoint, LocalProjection
from swarm_sar.core.geometry import Bounds
from swarm_sar.core.messages import DroneStatus, HealthLevel, MissionSpec, Phase
from swarm_sar.core.mission import build_mission_plan
from swarm_sar.core.tracking import TargetEstimate
from swarm_sar.ros.visualization import (build_coverage_grid, build_markers, CRITICAL_RGBA,
                                         PHASE_RGBA, VizTypes)

FAKES = FakeMessages()
TYPES = VizTypes(Marker=FAKES.get('visualization_msgs/Marker'),
                 MarkerArray=FAKES.get('visualization_msgs/MarkerArray'),
                 Point=FAKES.get('geometry_msgs/Point'),
                 ColorRGBA=FAKES.get('std_msgs/ColorRGBA'),
                 OccupancyGrid=FAKES.get('nav_msgs/OccupancyGrid'),
                 Time=FAKES.get('builtin_interfaces/Time'))
ORIGIN = GeoPoint(47.397742, 8.545594)
FRAME = LocalProjection(ORIGIN)


def plan(waypoints=((15.0, 20.0), (35.0, 0.0))):
    area = ((30.0, -40.0), (110.0, -40.0), (110.0, 40.0), (30.0, 40.0))
    return build_mission_plan(MissionSpec(
        sequence=1, mission_id='viz', origin=ORIGIN, altitude=4.0, grid_resolution=5.0,
        waypoints=tuple(FRAME.to_geo(*w) for w in waypoints),
        area=tuple(FRAME.to_geo(*a) for a in area)))


def status(drone_id, phase, health=HealthLevel.OK, goal=None, estimate=None, heading=0.0):
    return DroneStatus(drone_id, 10.0, ORIGIN, (0.0, 0.0), heading, phase, health, 0, 1, 0,
                       goal=goal, estimate=estimate)


def drones():
    cov = np.diag([9.0, 1.0, 0.1, 0.1])
    estimate = TargetEstimate(np.array([50.0, 5.0, 0.0, 0.0]), cov, 10.0, 10.0)
    return [(status(0, Phase.SEARCH, goal=(60.0, 10.0), heading=math.pi / 2), (40.0, 0.0)),
            (status(1, Phase.TRACK, estimate=estimate), (45.0, 5.0)),
            (status(2, Phase.HOLD, health=HealthLevel.CRITICAL), (70.0, -10.0))]


def by_namespace(markers):
    out = {}
    for m in markers[1:]:
        out.setdefault(m.ns, []).append(m)
    return out


def test_markers_start_with_delete_all_and_cover_every_layer():
    markers = build_markers(TYPES, drones(), plan(), 10.0, 'mission').markers
    marker = TYPES.Marker
    assert markers[0].action == marker.DELETEALL
    assert all(m.action == marker.ADD and m.header.frame_id == 'mission' for m in markers[1:])
    layers = by_namespace(markers)
    area = layers['area'][0]
    assert area.type == marker.LINE_STRIP and len(area.points) == 5  # closed ring
    assert area.points[0].x == area.points[-1].x
    assert len(layers['route'][0].points) == 2
    assert {m.id for m in layers['drones']} == {0, 1, 2}
    assert len(layers['labels']) == 3 and 'CRITICAL' in layers['labels'][2].text
    assert len(layers['goals'][0].points) == 2
    disc = layers['target_estimate'][0]
    # CYLINDER shares the value 3 with DELETEALL: it must be an ADD of type CYLINDER.
    assert disc.type == marker.CYLINDER and disc.action == marker.ADD
    assert disc.scale.x == pytest.approx(12.0) and disc.scale.y == pytest.approx(4.0)


def test_drone_colours_follow_phase_and_health():
    layers = by_namespace(build_markers(TYPES, drones(), plan(), 10.0, 'mission').markers)
    arrows = {m.id: m for m in layers['drones']}
    rgba = lambda c: (c.r, c.g, c.b, c.a)  # noqa: E731
    assert rgba(arrows[0].color) == pytest.approx(PHASE_RGBA[Phase.SEARCH])
    assert rgba(arrows[2].color) == pytest.approx(CRITICAL_RGBA)
    assert arrows[0].pose.orientation.z == pytest.approx(math.sin(math.pi / 4))


def test_markers_without_plan_or_estimates_omit_those_layers():
    plain = [(status(0, Phase.STANDBY), (0.0, 0.0))]
    markers = build_markers(TYPES, plain, None, 10.0, 'mission').markers
    assert set(by_namespace(markers)) == {'drones', 'labels', 'goals'}
    no_route = by_namespace(build_markers(TYPES, plain, plan(()), 10.0, 'mission').markers)
    assert 'route' not in no_route and 'area' in no_route


def test_coverage_grid_layout_values_and_invalid_cells():
    geometry = grid_geometry(Bounds(0.0, 0.0, 100.0, 50.0), 11.0)  # 10 x 5 cells
    last_seen = np.full(geometry.shape, NEVER_SEEN)
    last_seen[2, 1] = 100.0   # just seen
    last_seen[3, 1] = 55.0    # half stale
    grid = build_coverage_grid(TYPES, last_seen, geometry, now=100.0, revisit_period=90.0,
                               stamp=100.0, frame_id='mission')
    assert (grid.info.width, grid.info.height) == (10, 5)
    assert grid.info.resolution == 11.0
    assert isinstance(grid.data, array.array) and len(grid.data) == 50
    cell = list(grid.data)
    assert cell[1 * 10 + 2] == 0       # row-major along x: index = iy * width + ix
    assert cell[1 * 10 + 3] == 50
    assert cell[0] == 100              # never seen
    assert cell[9] == -1               # column centred outside the bounds
