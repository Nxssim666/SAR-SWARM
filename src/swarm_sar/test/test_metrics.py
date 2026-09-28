"""Tests for swarm_sar.core.metrics: the passive observer's KPIs."""

import math

import numpy as np
import pytest
from swarm_sar.core.coverage import GridGeometry
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.geometry import Bounds
from swarm_sar.core.messages import DroneStatus, HealthLevel, Phase
from swarm_sar.core.metrics import CSV_COLUMNS, csv_row, MetricsTracker
from swarm_sar.core.tracking import TargetEstimate

GEOMETRY = GridGeometry(Bounds(0.0, 0.0, 100.0, 100.0), 10.0)


def tracker():
    return MetricsTracker(GEOMETRY, detection_range=10.0, fresh_window=50.0, alive_timeout=1.5,
                          continuity_threshold=10.0)


def status(drone_id, stamp, phase=Phase.SEARCH, health=HealthLevel.OK, estimate=None,
           nearest=math.inf):
    return DroneStatus(drone_id, stamp, GeoPoint(47.0, 8.0), (0.0, 0.0), 0.0, phase, health, 0,
                       1, 0, estimate=estimate, nearest_obstacle=nearest)


def estimate_at(x, y, t):
    return TargetEstimate(np.array([x, y, 0.0, 0.0]), np.eye(4), t, t)


def test_standby_drones_and_unknown_positions_explore_nothing():
    m = tracker()
    m.record(status(1, 0.0, phase=Phase.STANDBY), (50.0, 50.0), 0.0)
    m.record(status(2, 0.0), None, 0.0)
    snap = m.snapshot(0.0)
    assert snap.explored_fraction == 0.0 and snap.drones_alive == 2
    assert snap.mission_time == 0.0


def test_exploration_milestones_and_mission_time():
    m = tracker()
    m.record(status(1, 10.0), (50.0, 50.0), 10.0)
    snap = m.snapshot(12.0)
    assert snap.mission_time == pytest.approx(2.0)
    assert snap.explored_fraction == pytest.approx(4 / 100)
    for i, x in enumerate(np.arange(5.0, 100.0, 10.0)):
        for y in np.arange(5.0, 100.0, 10.0):
            m.record(status(2, 13.0 + i * 0.01 + y * 1e-4), (x, y), 13.0)
    summary = m.summary()
    assert summary.time_to_explored[0.5] is None  # not until the next snapshot
    m.snapshot(14.0)
    summary = m.summary()
    assert summary.explored_fraction == 1.0
    assert summary.time_to_explored == {0.5: 4.0, 0.75: 4.0, 0.9: 4.0}


def test_duplicates_and_reordered_broadcasts_are_ignored():
    m = tracker()
    m.record(status(1, 5.0), (5.0, 5.0), 5.0)
    m.record(status(1, 4.0), (95.0, 95.0), 5.1)
    m.record(status(1, 5.0), (95.0, 95.0), 5.2)
    assert m.explored_snapshot()[9, 9] == -math.inf


def test_silent_drones_are_not_alive():
    m = tracker()
    m.record(status(1, 0.0), (5.0, 5.0), 0.0)
    m.record(status(2, 1.0), (15.0, 5.0), 1.0)
    assert m.snapshot(1.2).drones_alive == 2
    assert m.snapshot(1.6).drones_alive == 1


def test_counts_separation_holding_degraded_and_obstacles():
    m = tracker()
    m.record(status(1, 0.0, phase=Phase.HOLD, nearest=2.5), (0.0, 0.0), 0.0)
    m.record(status(2, 0.0, health=HealthLevel.DEGRADED, nearest=1.5), (3.0, 4.0), 0.0)
    m.record(status(3, 0.0, phase=Phase.STANDBY, nearest=0.1), (30.0, 40.0), 0.0)
    snap = m.snapshot(0.0)
    assert snap.num_holding == 1 and snap.num_degraded == 1
    assert snap.min_separation == pytest.approx(5.0)
    assert snap.min_obstacle_distance == pytest.approx(1.5)  # standby drones are not flying
    assert m.summary().min_separation == pytest.approx(5.0)


def test_detection_error_and_continuity():
    m = tracker()
    m.record(status(1, 0.0), (5.0, 5.0), 0.0)
    m.record_target((50.0, 50.0))
    m.snapshot(0.0)
    m.record(status(1, 1.0, phase=Phase.TRACK, estimate=estimate_at(53.0, 54.0, 1.0)),
             (45.0, 45.0), 1.0)
    first = m.snapshot(1.0)
    assert first.target_detected and first.time_to_first_detection == pytest.approx(1.0)
    assert first.tracking_error == pytest.approx(5.0) and first.num_tracking == 1
    m.record(status(1, 2.0, phase=Phase.TRACK, estimate=estimate_at(80.0, 50.0, 2.0)),
             (45.0, 45.0), 2.0)
    m.snapshot(2.0)
    m.record(status(1, 3.0, phase=Phase.TRACK, estimate=estimate_at(50.0, 50.0, 3.0)),
             (45.0, 45.0), 3.0)
    m.snapshot(3.0)
    summary = m.summary()
    assert summary.mean_tracking_error == pytest.approx((30.0 + 0.0) / 2)
    assert summary.track_continuity == pytest.approx(0.5)


def test_csv_row_matches_the_columns():
    m = tracker()
    m.record(status(1, 0.0), (5.0, 5.0), 0.0)
    row = csv_row(m.snapshot(0.0))
    assert len(row) == len(CSV_COLUMNS)
    values = dict(zip(CSV_COLUMNS, row))
    assert values['target_detected'] == 'false' and values['tracking_error'] == ''
    # Three cell centres lie within the 10 m detector footprint around (5, 5).
    assert values['drones_alive'] == '1' and values['explored_fraction'] == '0.0300'
