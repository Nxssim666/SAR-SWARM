"""
Drone-to-drone separation, expressed as linear constraints on the velocity command.

Toward every nearby drone the *closing speed* may not exceed the speed from
which this drone could still stop before ``min_separation``, allowing for
``reaction_time`` of latency (stale peer positions plus a held command).
Inside ``min_separation`` the drone must actively open the gap. Every
drone takes full responsibility: it never counts on a neighbour moving
away (the neighbour may stop, and its broadcast is a few tenths of a second
old), but it does give way to a neighbour closing in. A neighbour that does
not cooperate (hovering after a fault, or silent) is therefore still avoided.

Each neighbour contributes one half-plane ``v . n <= limit`` (``n`` points
at the neighbour). The local planner intersects these with the obstacle
constraints along each candidate direction, so no filter can undo another
one's work.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Sequence, Tuple

import numpy as np

from swarm_sar.core.geometry import tie_break_direction, Vec2


@dataclass(frozen=True)
class Neighbor:
    """A nearby drone as seen by the avoiding drone (local frame)."""

    drone_id: int
    position: Vec2
    velocity: Vec2


@dataclass(frozen=True)
class ClosingConstraint:
    """The velocity command must satisfy ``v . normal <= limit``."""

    drone_id: int
    normal: Vec2
    limit: float
    gap: float


def braking_speed(gap: float, min_separation: float, max_accel: float,
                  reaction_time: float) -> float:
    """
    Return the fastest closing speed that can still be stopped before ``min_separation``.

    Solves ``c * reaction_time + c**2 / (2 * max_accel) = gap - min_separation`` for ``c``.
    """
    margin = max(gap - min_separation, 0.0)
    tau = reaction_time
    return max_accel * (math.sqrt(tau * tau + 2.0 * margin / max_accel) - tau)


def avoidance_radius(min_separation: float, max_speed: float, max_accel: float,
                     reaction_time: float) -> float:
    """
    Return the distance beyond which no neighbour can constrain a command.

    It is the gap at which even a head-on encounter (closing at twice the
    maximum speed) is still inside the braking envelope; 0 disables avoidance.
    """
    if min_separation <= 0.0:
        return 0.0
    closing = 2.0 * max_speed
    return min_separation + closing * reaction_time + closing * closing / (2.0 * max_accel)


def separation_constraints(own_id: int, position: Vec2, neighbors: Sequence[Neighbor],
                           min_separation: float, max_speed: float, max_accel: float,
                           reaction_time: float) -> List[ClosingConstraint]:
    """Return one closing-speed constraint per neighbour close enough to matter."""
    radius = avoidance_radius(min_separation, max_speed, max_accel, reaction_time)
    out = []
    for n in neighbors:
        ux, uy, gap = _toward(own_id, position, n)
        if gap >= radius:
            continue
        limit = braking_speed(gap, min_separation, max_accel, reaction_time)
        # Take no credit for a neighbour moving away (it may stop at any moment, and what we
        # know of it is a few tenths of a second old); do give way to one closing in.
        limit += min(n.velocity[0] * ux + n.velocity[1] * uy, 0.0)
        if gap < min_separation:
            limit -= max_speed * (min_separation - gap) / min_separation
        out.append(ClosingConstraint(n.drone_id, (ux, uy), limit, gap))
    return out


def speed_bounds(directions: np.ndarray, constraints: Sequence[ClosingConstraint]
                 ) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return, per unit direction ``(K, 2)``, the speed interval ``[low, high]`` that is allowed.

    A direction heading toward a neighbour gets an upper bound; one heading
    away gets a lower bound when the neighbour is closing in faster than the
    envelope allows (the drone must retreat at least that fast). An empty
    interval (``low > high``) means no speed along that direction is safe.
    """
    count = directions.shape[0]
    low = np.zeros(count)
    high = np.full(count, math.inf)
    for c in constraints:
        proj = directions @ np.asarray(c.normal)
        toward = proj > 1e-9
        away = proj < -1e-9
        high[toward] = np.minimum(high[toward], c.limit / proj[toward])
        low[away] = np.maximum(low[away], c.limit / proj[away])
        if c.limit < 0.0:
            high[~toward & ~away] = -math.inf  # moving sideways cannot open the gap
    return low, high


def _toward(own_id: int, position: Vec2, n: Neighbor) -> Tuple[float, float, float]:
    """Return the unit vector toward ``n`` and the gap to it (tie-broken if coincident)."""
    dx, dy = n.position[0] - position[0], n.position[1] - position[1]
    gap = math.hypot(dx, dy)
    if gap > 1e-6:
        return dx / gap, dy / gap, gap
    away_x, away_y = tie_break_direction(own_id, n.drone_id)
    return -away_x, -away_y, gap
