"""
Swarm-level state: who I can hear, the shared target estimate, and the tracker election.

Peers are only known through their broadcasts. A peer that falls silent is
kept for ``lost_peer_memory`` as a stationary obstacle at its last position
(it may have lost its radio, not its motors, and a drone that stops hearing
its peers holds where it is), but it no longer takes part in partitioning or
the election.

Target estimation (from the v1 agent, unchanged in substance): own
detections go into a constant-velocity Kalman filter, peer estimates are
fused by covariance intersection, and a track whose uncertainty grows past
``track_drop_std`` is dropped, leaving a *datum* that biases the search
toward the last known position. A dropped track cannot be revived by peers
gossiping the same old information back (zombie tracks).

Tracker election: among drones on the same mission that hold an estimate,
the ``num_trackers`` nearest to it (distance compared in bands of twice the
ring radius, ties by id, incumbents get half a ring radius of hysteresis)
track; everyone else keeps searching.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from swarm_sar.core.config import DroneConfig
from swarm_sar.core.coverage import GridGeometry
from swarm_sar.core.geometry import distance, Vec2
from swarm_sar.core.messages import DroneStatus, PROTOCOL_VERSION, Receipt
from swarm_sar.core.tracking import (ConstantVelocityTracker, covariance_intersection,
                                     Detection, TargetEstimate)

MAX_PEERS = 1000
MAX_EXTRAPOLATION_S = 1.0

TRACK_INITIATED = 'track_initiated'
TRACK_ADOPTED = 'track_adopted'
TRACK_DROPPED = 'track_dropped'


@dataclass(frozen=True)
class PeerRecord:
    """The latest broadcast of one peer and when it was heard."""

    status: DroneStatus
    received_at: float
    lost_at: Optional[float] = None


class PeerTable:
    """Latest broadcast per peer, with loss detection."""

    def __init__(self, own_id: int, config: DroneConfig) -> None:
        self._own_id = own_id
        self._cfg = config
        self._records: Dict[int, PeerRecord] = {}

    def __len__(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        """Forget every peer."""
        self._records.clear()

    def shift_time(self, delta: float) -> None:
        """Move receive times by ``delta`` seconds (the companion clock was stepped)."""
        self._records = {
            pid: PeerRecord(r.status, r.received_at + delta,
                            None if r.lost_at is None else r.lost_at + delta)
            for pid, r in self._records.items()}

    def offer(self, status: DroneStatus, now: float, protocol: int = PROTOCOL_VERSION
              ) -> Receipt:
        """Consider a peer broadcast; return whether (and why not) it was accepted."""
        if protocol != PROTOCOL_VERSION:
            return Receipt.INCOMPATIBLE
        if status.drone_id == self._own_id:
            return Receipt.OWN
        if status.stamp > now + self._cfg.max_clock_skew:
            return Receipt.FUTURE
        if now - status.stamp > self._cfg.peer_timeout:
            return Receipt.STALE
        known = self._records.get(status.drone_id)
        if known is not None and known.status.stamp >= status.stamp:
            return Receipt.OUT_OF_ORDER
        if known is None and len(self._records) >= MAX_PEERS:
            return Receipt.IGNORED
        self._records[status.drone_id] = PeerRecord(status, now)
        return Receipt.ACCEPTED

    def expire(self, now: float) -> None:
        """Mark silent peers lost; forget lost peers after ``lost_peer_memory``."""
        silent_after = now - self._cfg.peer_timeout
        forget_after = now - self._cfg.lost_peer_memory
        for pid, record in list(self._records.items()):
            if record.lost_at is None:
                if record.received_at < silent_after:
                    self._records[pid] = PeerRecord(record.status, record.received_at, now)
            elif record.lost_at < forget_after:
                del self._records[pid]

    def active(self) -> List[DroneStatus]:
        """Return the latest status of every peer still heard."""
        return [r.status for r in self._records.values() if r.lost_at is None]

    def lost(self) -> List[DroneStatus]:
        """Return the last status of every recently lost peer."""
        return [r.status for r in self._records.values() if r.lost_at is not None]


@dataclass(frozen=True)
class Datum:
    """Last known position of a lost target (mission frame)."""

    position: Vec2
    std: float
    time: float


class TargetEstimator:
    """This drone's belief about the target (mission frame)."""

    def __init__(self, config: DroneConfig) -> None:
        self._cfg = config
        self._tracker = ConstantVelocityTracker(config.target_accel_psd, config.target_max_speed)
        self._estimate: Optional[TargetEstimate] = None
        self._datum: Optional[Datum] = None
        self._dropped_measurement_time = -math.inf

    @property
    def estimate(self) -> Optional[TargetEstimate]:
        """Return the live estimate, if any."""
        return self._estimate

    @property
    def datum(self) -> Optional[Datum]:
        """Return the datum left by the last dropped track, if still active."""
        return self._datum

    def reset(self) -> None:
        """Forget everything (new mission frame)."""
        self._estimate = None
        self._datum = None
        self._dropped_measurement_time = -math.inf

    def shift_time(self, delta: float) -> None:
        """Move every stored time by ``delta`` seconds (the companion clock was stepped)."""
        estimate = self._estimate
        if estimate is not None:
            self._estimate = TargetEstimate(estimate.state, estimate.covariance,
                                            estimate.stamp + delta,
                                            estimate.last_measurement_time + delta)
        if self._datum is not None:
            self._datum = Datum(self._datum.position, self._datum.std, self._datum.time + delta)
        self._dropped_measurement_time += delta

    def update(self, now: float, own_position: Optional[Vec2], tracking: bool,
               detections: Sequence[Detection],
               peer_estimates: Iterable[Tuple[int, TargetEstimate]]) -> List[Tuple[str, str]]:
        """
        Fold in own detections and peer estimates at ``now``; return (event, detail) pairs.

        ``own_position`` (mission frame) may be None when this drone cannot
        localise itself in the mission frame; it then never counts as
        involved in a dropped track.
        """
        cfg = self._cfg
        events: List[Tuple[str, str]] = []
        estimate = self._estimate
        for detection in sorted(detections, key=lambda d: d.stamp):
            if detection.stamp > now + cfg.max_clock_skew:
                continue
            if now - detection.stamp > cfg.max_detection_age:
                continue
            if estimate is None:
                estimate = self._tracker.initialize(detection)
                self._datum = None
                x, y = detection.position
                events.append((TRACK_INITIATED, f'target detected at ({x:.1f}, {y:.1f})'))
            else:
                estimate = self._tracker.update(estimate, detection)
        if estimate is not None:
            estimate = self._tracker.align(estimate, now)

        for drone_id, heard in peer_estimates:
            heard = self._tracker.align(heard, now)
            if heard.position_std > cfg.track_drop_std:
                continue
            if estimate is None:
                if heard.last_measurement_time <= self._dropped_measurement_time:
                    continue  # nothing newer than the track this drone already gave up on
                estimate = heard
                self._datum = None
                events.append((TRACK_ADOPTED, f'from drone {drone_id}'))
            else:
                estimate = covariance_intersection(estimate, heard)

        if estimate is not None and estimate.position_std > cfg.track_drop_std:
            x, y = estimate.position
            # Only drones that were involved leave a datum; a far-away relay whose copy
            # merely went stale must not be lured toward a target others still hold.
            involved = tracking or (own_position is not None and distance(
                own_position, estimate.position) <= 2.0 * cfg.recruit_radius)
            if involved:
                self._datum = Datum(estimate.position, estimate.position_std, now)
            self._dropped_measurement_time = max(self._dropped_measurement_time,
                                                 estimate.last_measurement_time)
            events.append((TRACK_DROPPED,
                           f'uncertainty {estimate.position_std:.1f} m at ({x:.1f}, {y:.1f})'
                           + ('; searching around it' if involved else '')))
            estimate = None
        self._estimate = estimate
        return events

    def datum_boost(self, now: float, geometry: GridGeometry) -> Optional[np.ndarray]:
        """Return a per-cell multiplier concentrating the search near the datum, if any."""
        datum = self._datum
        cfg = self._cfg
        if datum is None or cfg.datum_gain <= 0.0:
            return None
        elapsed = now - datum.time
        if elapsed > cfg.datum_ttl:
            self._datum = None
            return None
        sigma = max(math.hypot(datum.std, cfg.target_max_speed * max(elapsed, 0.0)),
                    geometry.cell_size)
        d2 = (geometry.cx - datum.position[0]) ** 2 + (geometry.cy - datum.position[1]) ** 2
        return 1.0 + cfg.datum_gain * np.exp(-d2 / (2.0 * sigma * sigma))


def election_key(dist_to_target: float, drone_id: int, tracking: bool,
                 standoff: float) -> Tuple[Tuple[int, int], float]:
    """
    Return ``((distance band, id), effective distance)`` for the tracker election.

    Distances are compared in bands of twice the ring radius, so every drone
    already on the ring shares band 0 and ties break by id instead of by
    centimetre differences that would make roles flap. Incumbent trackers get
    half a ring radius of bonus (hysteresis).
    """
    effective = max(dist_to_target - 0.5 * standoff, 0.0) if tracking else dist_to_target
    return (int(effective // (2.0 * standoff)), drone_id), effective


def elect_tracker(own_id: int, own_position: Vec2, own_tracking: bool, target: Vec2,
                  candidates: Iterable[Tuple[int, Vec2, bool]], config: DroneConfig) -> bool:
    """Return True if this drone should track: it is among the nearest estimate holders."""
    own_key, own_effective = election_key(distance(own_position, target), own_id,
                                          own_tracking, config.track_standoff)
    if own_effective > config.recruit_radius:
        return False
    better = 0
    for pid, position, tracking in candidates:
        key, _ = election_key(distance(position, target), pid, tracking, config.track_standoff)
        if key < own_key:
            better += 1
    return better < config.num_trackers


def extrapolate(position: Vec2, velocity: Vec2, stamp: float, now: float) -> Vec2:
    """Return where a peer probably is now (dead reckoning over at most one second)."""
    dt = min(max(now - stamp, 0.0), MAX_EXTRAPOLATION_S)
    return (position[0] + velocity[0] * dt, position[1] + velocity[1] * dt)
