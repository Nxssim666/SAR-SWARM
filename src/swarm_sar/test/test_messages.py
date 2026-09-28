"""Tests for swarm_sar.core.messages: every inbound field is validated on construction."""

import math

import numpy as np
import pytest
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.messages import (CommandKind, CoverageUpdate, DroneStatus, HealthLevel,
                                     MAX_AREA_VERTICES, MAX_COMMAND_TARGETS, MAX_SEQUENCE,
                                     MAX_WAYPOINTS, MissionSpec, Phase, SwarmCommand,
                                     TargetReport)
from swarm_sar.core.tracking import Detection, TargetEstimate

P = GeoPoint(47.0, 8.0)
AREA = (GeoPoint(47.0, 8.0), GeoPoint(47.001, 8.0), GeoPoint(47.001, 8.001))


def status(**overrides):
    fields = {'drone_id': 3, 'stamp': 10.0, 'position': P, 'velocity': (1.0, 0.0),
              'heading': 0.5, 'phase': Phase.SEARCH, 'health': HealthLevel.OK, 'faults': 0,
              'mission_sequence': 2, 'command_sequence': 0}
    fields.update(overrides)
    return DroneStatus(**fields)


def mission(**overrides):
    fields = {'sequence': 1, 'mission_id': 'm', 'origin': P, 'altitude': 10.0,
              'grid_resolution': 5.0, 'waypoints': (P,), 'area': AREA}
    fields.update(overrides)
    return MissionSpec(**fields)


def test_status_normalizes_enums_and_defaults():
    s = status(phase=2, health=1, goal=[1, 2])
    assert s.phase is Phase.SEARCH and s.health is HealthLevel.DEGRADED
    assert s.goal == (1.0, 2.0) and s.nearest_obstacle == math.inf and s.estimate is None
    assert status(position=None).position is None


@pytest.mark.parametrize('overrides', [
    {'drone_id': -1}, {'drone_id': 2 ** 31}, {'drone_id': True}, {'drone_id': 1.0},
    {'stamp': math.nan}, {'position': (47.0, 8.0)}, {'velocity': (math.inf, 0.0)},
    {'heading': math.nan}, {'phase': 9}, {'health': 5}, {'faults': -1}, {'faults': 2 ** 32},
    {'faults': True}, {'mission_sequence': -1}, {'command_sequence': MAX_SEQUENCE + 1},
    {'goal': (math.nan, 0.0)}, {'estimate': 'x'}, {'nearest_obstacle': math.nan},
    {'nearest_obstacle': -0.1},
])
def test_status_rejects_malformed_fields(overrides):
    with pytest.raises(ValueError):
        status(**overrides)


def test_status_carries_an_estimate():
    estimate = TargetEstimate(np.zeros(4), np.eye(4), 1.0, 1.0)
    assert status(estimate=estimate).estimate is estimate
    with pytest.raises(ValueError):
        status(estimate=Detection.isotropic(1.0, (0.0, 0.0), 1.0))


def test_coverage_update_freezes_its_arrays_and_validates():
    u = CoverageUpdate(1, 2.0, 1, False, [3, 4], [1.0, 2.0])
    assert u.cells.dtype == np.int64 and not u.cells.flags.writeable
    assert not u.last_seen.flags.writeable
    empty = CoverageUpdate(1, 2.0, 1, True, np.array([], dtype=np.uint32), [])
    assert empty.cells.size == 0 and empty.full
    for bad in ({'cells': [1.5], 'times': [1.0]}, {'cells': [-1], 'times': [1.0]},
                {'cells': [1, 2], 'times': [1.0]}, {'cells': [1], 'times': [math.inf]},
                {'cells': [[1]], 'times': [[1.0]]}):
        with pytest.raises(ValueError):
            CoverageUpdate(1, 2.0, 1, False, bad['cells'], bad['times'])
    with pytest.raises(ValueError):
        CoverageUpdate(1, 2.0, 0, False, [], [])  # coverage always belongs to a mission


def test_target_report_validation():
    assert TargetReport(1.0, P, 2, 1).std == 2.0
    for std, confidence in ((0.0, 0.5), (math.nan, 0.5), (1.0, 1.5), (1.0, -0.1),
                            (1.0, math.nan)):
        with pytest.raises(ValueError):
            TargetReport(1.0, P, std, confidence)
    with pytest.raises(ValueError):
        TargetReport(1.0, (47.0, 8.0), 1.0, 0.5)


def test_mission_spec_validation():
    spec = mission(waypoints=[P, P])
    assert spec.waypoints == (P, P) and isinstance(spec.area, tuple)
    for overrides in ({'sequence': 0}, {'sequence': MAX_SEQUENCE + 1}, {'mission_id': 'a\nb'},
                      {'mission_id': 'x' * 65}, {'mission_id': 5}, {'origin': (47.0, 8.0)},
                      {'altitude': 0.0}, {'altitude': math.nan}, {'grid_resolution': -5.0},
                      {'waypoints': (P,) * (MAX_WAYPOINTS + 1)}, {'area': AREA[:2]},
                      {'area': (P,) * (MAX_AREA_VERTICES + 1)}, {'area': AREA + ((1, 2),)}):
        with pytest.raises(ValueError):
            mission(**overrides)


def test_swarm_command_targets():
    everyone = SwarmCommand(1, CommandKind.HOLD, 0.0)
    some = SwarmCommand(2, 3, 0.0, frozenset({1, 2}))
    assert everyone.applies_to(99) and some.applies_to(2) and not some.applies_to(3)
    assert some.kind is CommandKind.RETURN_TO_LAUNCH
    with pytest.raises(ValueError):
        SwarmCommand(1, 9, 0.0)
    with pytest.raises(ValueError):
        SwarmCommand(1, CommandKind.HOLD, 0.0, frozenset({-1}))
    with pytest.raises(ValueError):
        SwarmCommand(1, CommandKind.HOLD, 0.0, frozenset(range(MAX_COMMAND_TARGETS + 1)))
    with pytest.raises(ValueError):
        SwarmCommand(0, CommandKind.HOLD, 0.0)
