"""
Decentralized search: choose where to look next inside my own Voronoi region.

Each drone partitions the mission area with the searching peers it can
hear (limited-range Voronoi, Cortes et al. 2004) and only considers cells
in its own region, so drones never compete for the same ground. Within that
region it greedily heads for the cell whose sensor footprint would reveal
the most stale ground per unit of travel, and commits to that goal until it
is reached, becomes much less valuable, or leaves the region.

Commitment is a hysteresis on *relative* score: the current goal is kept
unless another cell scores ``switch_ratio`` times better. That suppresses
dithering between similar options while still reacting at once to new
information (e.g. a datum after a lost track).

In the real world some goals cannot be reached (inside a thicket, behind a
wall the local planner cannot get around). The controller reports those
with ``mark_unreachable`` and the planner leaves that neighbourhood alone
for a while instead of trying the same goal forever.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from swarm_sar.core.coverage import GridGeometry
from swarm_sar.core.geometry import distance, polygon_area_centroid, Vec2, voronoi_cell

_MIN_VALUE = 1e-9


@dataclass(frozen=True)
class SearchPlan:
    """Where to go next and why."""

    goal: Vec2
    reason: str
    value: float


class SearchPlanner:
    """Per-drone search goal selection with commitment and unreachable-goal cooldowns."""

    FRONTIER = 'frontier'
    COMMITTED = 'committed'
    IDLE = 'idle'
    DEGENERATE = 'degenerate'

    def __init__(self, geometry: GridGeometry, sensor_range: float, distance_scale: float,
                 switch_ratio: float, arrival_radius: float) -> None:
        for name, value in (('sensor_range', sensor_range), ('distance_scale', distance_scale),
                            ('arrival_radius', arrival_radius)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be positive, got {value!r}')
        if not (math.isfinite(switch_ratio) and switch_ratio >= 1.0):
            raise ValueError(f'switch_ratio must be >= 1, got {switch_ratio!r}')
        self._geometry = geometry
        self._distance_scale = float(distance_scale)
        self._switch_ratio = float(switch_ratio)
        self._arrival_radius = float(arrival_radius)
        radius_cells = sensor_range / geometry.cell_size
        self._reach = int(math.floor(radius_cells))
        self._offsets: List[Tuple[int, int]] = [
            (dx, dy)
            for dx in range(-self._reach, self._reach + 1)
            for dy in range(-self._reach, self._reach + 1)
            if dx * dx + dy * dy <= radius_cells * radius_cells + 1e-9]
        self._commitment: Optional[Vec2] = None
        self._blocked_until = np.full(geometry.shape, -math.inf)

    @property
    def geometry(self) -> GridGeometry:
        """Return the grid this planner works on."""
        return self._geometry

    @property
    def committed_goal(self) -> Optional[Vec2]:
        """Return the goal currently committed to, if any."""
        return self._commitment

    def reset(self) -> None:
        """Forget the current commitment (e.g. after switching phases)."""
        self._commitment = None

    def shift_time(self, delta: float) -> None:
        """Move every cooldown by ``delta`` seconds (the companion clock was stepped)."""
        self._blocked_until += delta

    def mark_unreachable(self, goal: Vec2, radius: float, until: float) -> None:
        """Exclude cells within ``radius`` of ``goal`` from goal selection until ``until``."""
        g = self._geometry
        near = np.hypot(g.cx - goal[0], g.cy - goal[1]) <= radius
        near[g.index_of(goal)] = True
        self._blocked_until[near] = np.maximum(self._blocked_until[near], until)
        if self._commitment is not None and distance(self._commitment, goal) <= radius:
            self._commitment = None

    def region_mask(self, position: Vec2, neighbors: Sequence[Vec2]) -> np.ndarray:
        """Return valid cells whose centre is at least as close to me as to any neighbour."""
        g = self._geometry
        mask = g.valid.copy()
        px, py = position
        own_sq = px * px + py * py
        for qx, qy in neighbors:
            dx, dy = qx - px, qy - py
            if dx * dx + dy * dy < 1e-18:
                continue
            # |c - p|^2 <= |c - q|^2  <=>  2 c.(q - p) <= |q|^2 - |p|^2
            mask &= 2.0 * (g.cx * dx + g.cy * dy) <= (qx * qx + qy * qy - own_sq) + 1e-9
        return mask

    def footprint_gain(self, density: np.ndarray) -> np.ndarray:
        """Return, per cell, the density a sensor footprint centred there would reveal."""
        reach = self._reach
        nx, ny = self._geometry.shape
        padded = np.pad(density, reach, mode='constant')
        gain = np.zeros_like(density)
        for dx, dy in self._offsets:
            gain += padded[reach + dx:reach + dx + nx, reach + dy:reach + dy + ny]
        return gain

    def plan(self, position: Vec2, neighbors: Sequence[Vec2], density: np.ndarray,
             now: float) -> SearchPlan:
        """
        Choose the next search goal at time ``now``.

        ``density`` is the per-cell value of looking there (normally the
        coverage staleness, possibly boosted near a lost target's datum).
        """
        g = self._geometry
        if density.shape != g.shape:
            raise ValueError(f'density shape {density.shape} does not match grid {g.shape}')
        region = self.region_mask(position, neighbors)
        if not region.any():
            self._commitment = None
            polygon = voronoi_cell(position, neighbors, g.bounds)
            centre = polygon_area_centroid(polygon)[0] if polygon else position
            return SearchPlan(g.bounds.clamp(centre), self.DEGENERATE, 0.0)
        mask = region & (self._blocked_until < now)

        gain = np.where(mask, self.footprint_gain(density), 0.0)
        travel = np.hypot(g.cx - position[0], g.cy - position[1])
        score = gain * np.exp(-travel / self._distance_scale)
        ix, iy = np.unravel_index(int(np.argmax(score)), g.shape)
        best_score = float(score[ix, iy])

        if self._commitment is not None:
            goal = self._commitment
            gx, gy = g.index_of(goal)
            if (mask[gx, gy] and gain[gx, gy] > _MIN_VALUE
                    and distance(position, goal) > self._arrival_radius
                    and best_score <= self._switch_ratio * float(score[gx, gy])):
                return SearchPlan(goal, self.COMMITTED, float(gain[gx, gy]))
            self._commitment = None

        best = float(gain[ix, iy])
        if best <= _MIN_VALUE:
            # Wait at the region cell nearest its mean: the mean itself can lie outside a
            # non-convex area.
            mx, my = float(g.cx[region].mean()), float(g.cy[region].mean())
            spread = np.where(region, np.hypot(g.cx - mx, g.cy - my), np.inf)
            cx, cy = np.unravel_index(int(np.argmin(spread)), g.shape)
            return SearchPlan(g.center_of(int(cx), int(cy)), self.IDLE, 0.0)
        goal = g.center_of(int(ix), int(iy))
        self._commitment = goal
        return SearchPlan(goal, self.FRONTIER, best)
