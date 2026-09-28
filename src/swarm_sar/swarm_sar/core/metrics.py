"""
Mission KPIs computed by a passive observer (ground station or simulator).

The observer sees every drone broadcast (and, in simulation, the target's
ground truth). It keeps its own coverage map built from reported drone
positions, i.e. what has *physically* been inside some detector footprint,
which is the honest denominator for "how much of the area was searched".
Nothing here is ever fed back into the swarm.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from swarm_sar.core.coverage import CoverageMap, GridGeometry
from swarm_sar.core.geometry import distance, Vec2
from swarm_sar.core.messages import DroneStatus, HealthLevel, Phase

COVERAGE_MILESTONES = (0.5, 0.75, 0.9)
CSV_COLUMNS = ('mission_time', 'drones_alive', 'explored_fraction', 'fresh_fraction',
               'num_tracking', 'num_holding', 'num_degraded', 'target_detected',
               'time_to_first_detection', 'tracking_error', 'min_separation',
               'min_obstacle_distance')


@dataclass(frozen=True)
class MetricsSnapshot:
    """Instantaneous mission state."""

    mission_time: float
    drones_alive: int
    explored_fraction: float
    fresh_fraction: float
    num_tracking: int
    num_holding: int
    num_degraded: int
    target_detected: bool
    time_to_first_detection: Optional[float]
    tracking_error: Optional[float]
    min_separation: Optional[float]
    min_obstacle_distance: Optional[float]


@dataclass(frozen=True)
class MetricsSummary:
    """Whole-mission KPIs."""

    mission_time: float
    explored_fraction: float
    time_to_explored: Dict[float, Optional[float]]
    time_to_first_detection: Optional[float]
    mean_tracking_error: Optional[float]
    track_continuity: Optional[float]
    min_separation: Optional[float]
    min_obstacle_distance: Optional[float]


@dataclass(frozen=True)
class _Observed:
    status: DroneStatus
    position: Optional[Vec2]
    received_at: float


class MetricsTracker:
    """Accumulate KPIs from drone broadcasts (mission-frame positions) and ground truth."""

    def __init__(self, geometry: GridGeometry, detection_range: float, fresh_window: float,
                 alive_timeout: float, continuity_threshold: float) -> None:
        self._coverage = CoverageMap(geometry, fresh_window)
        self._range = float(detection_range)
        self._fresh_window = float(fresh_window)
        self._alive_timeout = float(alive_timeout)
        self._continuity_threshold = float(continuity_threshold)
        self._latest: Dict[int, _Observed] = {}
        self._target: Optional[Vec2] = None
        self._start: Optional[float] = None
        self._first_detection: Optional[float] = None
        self._milestones: Dict[float, Optional[float]] = dict.fromkeys(COVERAGE_MILESTONES)
        self._last_snapshot: Optional[float] = None
        self._since_detection = 0.0
        self._tracked = 0.0
        self._error_integral = 0.0
        self._error_time = 0.0
        self._min_separation: Optional[float] = None
        self._min_obstacle: Optional[float] = None
        self._mission_time = 0.0
        self._explored = 0.0

    @property
    def geometry(self) -> GridGeometry:
        """Return the mission grid the metrics are computed on."""
        return self._coverage.geometry

    def record(self, status: DroneStatus, position: Optional[Vec2], received_at: float) -> None:
        """Record a broadcast with its mission-frame position (duplicates/reordering ignored)."""
        previous = self._latest.get(status.drone_id)
        if previous is not None and previous.status.stamp >= status.stamp:
            return
        self._latest[status.drone_id] = _Observed(status, position, received_at)
        if status.phase in (Phase.STANDBY,) or position is None:
            return
        if self._start is None:
            self._start = status.stamp
        self._coverage.observe(position, self._range, status.stamp)
        if status.estimate is not None and self._first_detection is None:
            self._first_detection = status.stamp

    def record_target(self, position: Vec2) -> None:
        """Record the target's ground-truth position (simulation only)."""
        self._target = (float(position[0]), float(position[1]))

    def explored_snapshot(self) -> np.ndarray:
        """Return a read-only copy of the per-cell last-observed times."""
        return self._coverage.snapshot()

    def alive(self, now: float) -> List[Tuple[DroneStatus, Optional[Vec2]]]:
        """Forget drones not heard from within ``alive_timeout``; return the rest."""
        cutoff = now - self._alive_timeout
        for drone_id in [d for d, o in self._latest.items() if o.received_at < cutoff]:
            del self._latest[drone_id]
        return [(o.status, o.position) for o in self._latest.values()]

    def snapshot(self, now: float) -> MetricsSnapshot:
        """Compute the current KPIs and fold this interval into the mission totals."""
        alive = self.alive(now)
        start = self._start if self._start is not None else now
        mission_time = max(now - start, 0.0)
        explored = self._coverage.seen_fraction(now)
        fresh = self._coverage.seen_fraction(now, self._fresh_window)
        for milestone, reached in self._milestones.items():
            if reached is None and explored >= milestone:
                self._milestones[milestone] = mission_time
        statuses = [s for s, _ in alive]
        error = self._tracking_error(statuses)
        min_gap = _min_pairwise_distance([p for _, p in alive if p is not None])
        if min_gap is not None:
            self._min_separation = (min_gap if self._min_separation is None
                                    else min(self._min_separation, min_gap))
        obstacles = [s.nearest_obstacle for s in statuses if math.isfinite(s.nearest_obstacle)
                     and s.phase is not Phase.STANDBY]
        min_obstacle = min(obstacles) if obstacles else None
        if min_obstacle is not None:
            self._min_obstacle = (min_obstacle if self._min_obstacle is None
                                  else min(self._min_obstacle, min_obstacle))
        self._accumulate(now, error)
        self._mission_time = mission_time
        self._explored = explored
        first = None if self._first_detection is None else self._first_detection - start
        return MetricsSnapshot(
            mission_time=mission_time, drones_alive=len(alive), explored_fraction=explored,
            fresh_fraction=fresh,
            num_tracking=sum(1 for s in statuses if s.phase is Phase.TRACK),
            num_holding=sum(1 for s in statuses if s.phase is Phase.HOLD),
            num_degraded=sum(1 for s in statuses if s.health is not HealthLevel.OK),
            target_detected=self._first_detection is not None, time_to_first_detection=first,
            tracking_error=error, min_separation=min_gap, min_obstacle_distance=min_obstacle)

    def summary(self) -> MetricsSummary:
        """Return whole-mission KPIs accumulated over all snapshots so far."""
        first = None
        if self._first_detection is not None and self._start is not None:
            first = self._first_detection - self._start
        return MetricsSummary(
            mission_time=self._mission_time, explored_fraction=self._explored,
            time_to_explored=dict(self._milestones), time_to_first_detection=first,
            mean_tracking_error=(self._error_integral / self._error_time
                                 if self._error_time > 0 else None),
            track_continuity=(self._tracked / self._since_detection
                              if self._since_detection > 0 else None),
            min_separation=self._min_separation, min_obstacle_distance=self._min_obstacle)

    def _tracking_error(self, statuses: List[DroneStatus]) -> Optional[float]:
        if self._target is None:
            return None
        estimates = [s.estimate for s in statuses if s.estimate is not None]
        if not estimates:
            return None
        best = min(estimates, key=lambda e: e.position_std)
        return distance(best.position, self._target)

    def _accumulate(self, now: float, error: Optional[float]) -> None:
        """Credit the interval since the previous snapshot, if the target was known throughout."""
        previous, self._last_snapshot = self._last_snapshot, now
        if previous is None or now <= previous:
            return
        if self._first_detection is None or previous < self._first_detection:
            return
        dt = now - previous
        self._since_detection += dt
        if error is not None:
            self._error_integral += error * dt
            self._error_time += dt
            if error <= self._continuity_threshold:
                self._tracked += dt


def csv_row(snapshot: MetricsSnapshot) -> Tuple[str, ...]:
    """Format a snapshot as a CSV row matching ``CSV_COLUMNS`` (empty = not available)."""
    def cell(value: object) -> str:
        if value is None:
            return ''
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, float):
            return f'{value:.4f}'
        return str(value)
    return tuple(cell(getattr(snapshot, column)) for column in CSV_COLUMNS)


def _min_pairwise_distance(points: List[Vec2]) -> Optional[float]:
    if len(points) < 2:
        return None
    arr = np.asarray(points, dtype=np.float64)
    diff = arr[:, None, :] - arr[None, :, :]
    gaps = np.hypot(diff[..., 0], diff[..., 1])
    gaps[np.diag_indices(len(points))] = math.inf
    return float(gaps.min())
