"""
A short-memory, vehicle-centred map of observed free space and obstacles (local ENU).

Each cell remembers when it was last seen free and last seen occupied. A
cell is **free** only if it was seen free within ``memory`` seconds *and*
not seen occupied within ``memory`` seconds; anything else is blocked,
whether it is a recent obstacle or simply unobserved. That asymmetry is
the core safety property: the planner can only ever move into space the
camera recently proved empty.

Obstacle evidence is deliberately not erased by later free-space rays:
as the viewpoint moves, rays grazing a trunk's flank would otherwise clear
the very cells that make the flank an obstacle (found in simulation, where
it shaved ~0.2 m off the achieved clearance). A person walking through the
map leaves ``memory`` seconds of occupied trail instead, which is the
conservative way to be wrong.

The window follows the vehicle. It is re-centred in whole cells once the
vehicle has drifted ``size / 8`` from the centre, so the planning window
(configured to fit in ``3/8`` of the size) never reaches past the edge.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Tuple

import numpy as np

from swarm_sar.core.depth import DepthScan
from swarm_sar.core.geometry import Vec2


class ObstacleMap:
    """Rolling evidence grid in local ENU."""

    def __init__(self, resolution: float, size: float, memory: float) -> None:
        for name, value in (('resolution', resolution), ('size', size), ('memory', memory)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be positive, got {value!r}')
        self._res = float(resolution)
        self._n = int(math.ceil(size / resolution))
        self._memory = float(memory)
        self._free = np.full((self._n, self._n), -math.inf)
        self._occupied = np.full((self._n, self._n), -math.inf)
        self._origin: Optional[Tuple[float, float]] = None  # lower-left corner of cell (0, 0)

    @property
    def resolution(self) -> float:
        """Return the cell size."""
        return self._res

    @property
    def cells_per_side(self) -> int:
        """Return the number of cells along each side."""
        return self._n

    @property
    def origin(self) -> Optional[Tuple[float, float]]:
        """Return the lower-left corner of the map, or None before the first centring."""
        return self._origin

    def shift_time(self, delta: float) -> None:
        """Move every evidence time by ``delta`` seconds (the companion clock was stepped)."""
        self._free += delta
        self._occupied += delta

    def clear(self) -> None:
        """Forget all evidence (after a local-frame reset it no longer lines up)."""
        self._free.fill(-math.inf)
        self._occupied.fill(-math.inf)
        self._origin = None

    def recenter(self, position: Vec2) -> None:
        """Keep ``position`` near the middle of the map, shifting by whole cells."""
        half = self._n // 2
        if self._origin is None:
            self._origin = (math.floor(position[0] / self._res) * self._res - half * self._res,
                            math.floor(position[1] / self._res) * self._res - half * self._res)
            return
        cx = self._origin[0] + half * self._res
        cy = self._origin[1] + half * self._res
        limit = self._n * self._res / 8.0
        if abs(position[0] - cx) <= limit and abs(position[1] - cy) <= limit:
            return
        sx = int(round((position[0] - cx) / self._res))
        sy = int(round((position[1] - cy) / self._res))
        self._free = _shifted(self._free, sx, sy)
        self._occupied = _shifted(self._occupied, sx, sy)
        self._origin = (self._origin[0] + sx * self._res, self._origin[1] + sy * self._res)

    def _cells(self, xs: np.ndarray, ys: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        assert self._origin is not None
        ix = np.floor((xs - self._origin[0]) / self._res).astype(np.int64)
        iy = np.floor((ys - self._origin[1]) / self._res).astype(np.int64)
        inside = (ix >= 0) & (ix < self._n) & (iy >= 0) & (iy < self._n)
        return ix, iy, inside

    def integrate(self, scan: DepthScan) -> None:
        """
        Fold one scan in: clear along each bearing, then mark obstacle points.

        Clearing stops one cell short of where the evidence ends. Free
        evidence never overrides obstacle evidence (see the module notes).
        """
        if self._origin is None:
            self.recenter(scan.origin)
        t = scan.stamp
        if scan.bearings.size:
            reach = scan.free_range - self._res
            longest = float(reach.max())
            if longest > 0.0:
                steps = np.arange(0.0, longest, self._res / 2.0)
                along = steps[None, :] < reach[:, None]
                xs = scan.origin[0] + steps[None, :] * np.cos(scan.bearings)[:, None]
                ys = scan.origin[1] + steps[None, :] * np.sin(scan.bearings)[:, None]
                ix, iy, inside = self._cells(xs[along], ys[along])
                self._free[ix[inside], iy[inside]] = t
        if scan.obstacles.shape[0]:
            ix, iy, inside = self._cells(scan.obstacles[:, 0], scan.obstacles[:, 1])
            self._occupied[ix[inside], iy[inside]] = t

    def free_mask(self, now: float) -> np.ndarray:
        """Return which cells are known free at ``now``."""
        return (now - self._free <= self._memory) & ~(now - self._occupied <= self._memory)

    def occupied_mask(self, now: float) -> np.ndarray:
        """Return which cells held an obstacle within the memory window."""
        return now - self._occupied <= self._memory

    def blocked_offsets(self, position: Vec2, radius: float, now: float,
                        self_clear_radius: float,
                        self_clear_center: Optional[Vec2] = None) -> np.ndarray:
        """
        Return ``(N, 2)`` offsets from ``position`` to blocked cell centres within ``radius``.

        Unobserved cells within ``self_clear_radius`` of ``self_clear_center``
        (default: ``position``) are not blocked: the vehicle's own
        surroundings, which a forward camera cannot see. Observed obstacles
        are always blocked. Cells outside the map count as blocked like any
        other unobserved space.
        """
        w = self._window(position, radius, now)
        if self_clear_center is None:
            exempt = w.dist <= self_clear_radius
        else:
            exempt = np.hypot(w.ox + (position[0] - self_clear_center[0]),
                              w.oy + (position[1] - self_clear_center[1])) <= self_clear_radius
        blocked = ~w.free & (w.occupied | ~exempt)
        # The vehicle's own cell is free (the vehicle is in it) unless an obstacle was seen
        # there. That also makes the border argument below hold wherever the vehicle is.
        blocked[w.span, w.span] = w.occupied[w.span, w.span]
        # Only blocked cells bordering passable space can be the first thing a straight path
        # from the (passable) vehicle position runs into; interior cells never are.
        passable = ~blocked
        border = np.zeros_like(blocked)
        border[1:, :] |= passable[:-1, :]
        border[:-1, :] |= passable[1:, :]
        border[:, 1:] |= passable[:, :-1]
        border[:, :-1] |= passable[:, 1:]
        border[1:, 1:] |= passable[:-1, :-1]
        border[:-1, :-1] |= passable[1:, 1:]
        border[1:, :-1] |= passable[:-1, 1:]
        border[:-1, 1:] |= passable[1:, :-1]
        keep = blocked & border & (w.dist <= radius)
        return np.column_stack([w.ox[keep], w.oy[keep]])

    def occupied_offsets(self, position: Vec2, radius: float, now: float) -> np.ndarray:
        """Return ``(N, 2)`` offsets from ``position`` to recent obstacle cells in ``radius``."""
        w = self._window(position, radius, now)
        keep = w.occupied & (w.dist <= radius)
        return np.column_stack([w.ox[keep], w.oy[keep]])

    def _window(self, position: Vec2, radius: float, now: float) -> '_Window':
        """Cut the square of cells around ``position`` that covers ``radius`` out of the map."""
        if self._origin is None:
            self.recenter(position)
        assert self._origin is not None
        span = int(math.ceil(radius / self._res)) + 1
        width = 2 * span + 1
        px = (position[0] - self._origin[0]) / self._res
        py = (position[1] - self._origin[1]) / self._res
        i0, j0 = int(math.floor(px)) - span, int(math.floor(py)) - span
        dx = (np.arange(i0, i0 + width) + 0.5 - px) * self._res
        dy = (np.arange(j0, j0 + width) + 0.5 - py) * self._res
        ox, oy = np.meshgrid(dx, dy, indexing='ij')
        free = np.zeros(ox.shape, dtype=bool)
        occupied = np.zeros(ox.shape, dtype=bool)
        lo_i, lo_j = max(i0, 0), max(j0, 0)
        hi_i, hi_j = min(i0 + width, self._n), min(j0 + width, self._n)
        if lo_i < hi_i and lo_j < hi_j:
            src = (slice(lo_i, hi_i), slice(lo_j, hi_j))
            dst = (slice(lo_i - i0, hi_i - i0), slice(lo_j - j0, hi_j - j0))
            occupied[dst] = now - self._occupied[src] <= self._memory
            free[dst] = (now - self._free[src] <= self._memory) & ~occupied[dst]
        return _Window(ox, oy, np.hypot(ox, oy), free, occupied, span)

    def nearest_obstacle(self, position: Vec2, now: float, radius: float) -> float:
        """Return the distance to the nearest recent obstacle cell centre within ``radius``."""
        if self._origin is None:
            return math.inf
        occupied = self.occupied_mask(now)
        if not occupied.any():
            return math.inf
        ix, iy = np.nonzero(occupied)
        xs = self._origin[0] + (ix + 0.5) * self._res
        ys = self._origin[1] + (iy + 0.5) * self._res
        gaps = np.hypot(xs - position[0], ys - position[1])
        nearest = float(gaps.min())
        return nearest if nearest <= radius else math.inf


@dataclass(frozen=True)
class _Window:
    """Cells around a query position: offsets of their centres and their evidence."""

    ox: np.ndarray
    oy: np.ndarray
    dist: np.ndarray
    free: np.ndarray
    occupied: np.ndarray
    span: int  # index of the query position's own cell along both axes


def _shifted(grid: np.ndarray, sx: int, sy: int) -> np.ndarray:
    """Return ``grid`` moved by ``(-sx, -sy)`` cells, with vacated cells set to -inf."""
    n = grid.shape[0]
    out = np.full_like(grid, -math.inf)
    if abs(sx) >= n or abs(sy) >= n:
        return out
    src_x = slice(max(sx, 0), n + min(sx, 0))
    dst_x = slice(max(-sx, 0), n + min(-sx, 0))
    src_y = slice(max(sy, 0), n + min(sy, 0))
    dst_y = slice(max(-sy, 0), n + min(-sy, 0))
    out[dst_x, dst_y] = grid[src_x, src_y]
    return out
