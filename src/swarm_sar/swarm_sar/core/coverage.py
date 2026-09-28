"""
Coverage bookkeeping: a square grid over the mission area recording when each cell was seen.

Every drone owns its own ``CoverageMap``; there is no global map. Knowledge
spreads by gossip: drones broadcast the cells they observed recently (and,
occasionally, every cell they have ever observed) and peers merge them with
an element-wise maximum. Maximum is idempotent, commutative and
associative, so updates can be lost, repeated, reordered or relayed without
double counting, and a periodic full snapshot repairs whatever was lost.

The grid is defined by the mission (area polygon and cell size), so every
drone on the same mission derives the identical grid and cell indices can
be exchanged directly.
"""

from __future__ import annotations

import functools
import math
from typing import Optional, Sequence, Tuple

import numpy as np

from swarm_sar.core.geometry import as_vec2, Bounds, points_in_polygon, Vec2

NEVER_SEEN = -math.inf
MAX_CELLS = 250_000


class GridGeometry:
    """
    A square-cell grid laid over a bounding box, optionally masked by a polygon.

    Cells are square so the sensor footprint is isotropic in cell units.
    Cells whose centre lies outside the bounds or outside the polygon are
    marked invalid and ignored everywhere (coverage fractions, goal
    selection, merges).
    """

    __slots__ = ('bounds', 'cell_size', 'polygon', 'nx', 'ny', 'centers_x', 'centers_y', 'cx',
                 'cy', 'valid', 'num_valid')

    def __init__(self, bounds: Bounds, cell_size: float,
                 polygon: Optional[Sequence[Vec2]] = None) -> None:
        if isinstance(cell_size, bool) or not math.isfinite(cell_size) or cell_size <= 0:
            raise ValueError(f'cell_size must be a positive number, got {cell_size!r}')
        nx = max(1, math.ceil(bounds.width / cell_size - 1e-9))
        ny = max(1, math.ceil(bounds.height / cell_size - 1e-9))
        if nx * ny > MAX_CELLS:
            raise ValueError(f'{nx}x{ny} grid exceeds {MAX_CELLS} cells; use a coarser grid')
        self.bounds = bounds
        self.cell_size = float(cell_size)
        self.polygon: Optional[Tuple[Vec2, ...]] = (
            None if polygon is None else tuple((float(x), float(y)) for x, y in polygon))
        self.nx = nx
        self.ny = ny
        self.centers_x = bounds.xmin + (np.arange(nx) + 0.5) * self.cell_size
        self.centers_y = bounds.ymin + (np.arange(ny) + 0.5) * self.cell_size
        self.cx, self.cy = np.meshgrid(self.centers_x, self.centers_y, indexing='ij')
        valid = (self.cx <= bounds.xmax + 1e-9) & (self.cy <= bounds.ymax + 1e-9)
        if self.polygon is not None:
            valid &= points_in_polygon(self.cx, self.cy, self.polygon)
        self.valid = valid
        self.num_valid = int(np.count_nonzero(valid))
        if self.num_valid == 0:
            raise ValueError('no grid cell centre lies inside the area; use a finer grid')
        for array in (self.centers_x, self.centers_y, self.cx, self.cy, self.valid):
            array.setflags(write=False)

    @property
    def shape(self) -> Tuple[int, int]:
        """Return ``(nx, ny)``."""
        return (self.nx, self.ny)

    @property
    def size(self) -> int:
        """Return the total number of cells (valid or not)."""
        return self.nx * self.ny

    def index_of(self, point: Sequence[float]) -> Tuple[int, int]:
        """Return the (clamped) cell index containing ``point``."""
        ix = int(math.floor((point[0] - self.bounds.xmin) / self.cell_size))
        iy = int(math.floor((point[1] - self.bounds.ymin) / self.cell_size))
        return (min(max(ix, 0), self.nx - 1), min(max(iy, 0), self.ny - 1))

    def center_of(self, ix: int, iy: int) -> Vec2:
        """Return the centre of cell ``(ix, iy)``."""
        return (float(self.centers_x[ix]), float(self.centers_y[iy]))

    def _key(self) -> tuple:
        return (self.bounds.as_tuple(), self.cell_size, self.polygon)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, GridGeometry) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        vertices = 0 if self.polygon is None else len(self.polygon)
        return (f'GridGeometry(bounds={self.bounds.as_tuple()}, cell_size={self.cell_size}, '
                f'polygon_vertices={vertices})')


@functools.lru_cache(maxsize=32)
def grid_geometry(bounds: Bounds, cell_size: float,
                  polygon: Optional[Tuple[Vec2, ...]] = None) -> GridGeometry:
    """Return a shared, immutable geometry (identical inputs give the identical grid)."""
    return GridGeometry(bounds, float(cell_size), polygon)


class CoverageMap:
    """When each grid cell was last observed, as known to one drone."""

    def __init__(self, geometry: GridGeometry, revisit_period: float) -> None:
        if not math.isfinite(revisit_period) or revisit_period <= 0:
            raise ValueError(f'revisit_period must be positive, got {revisit_period!r}')
        self._geometry = geometry
        self._revisit_period = float(revisit_period)
        self._last_seen = np.full(geometry.shape, NEVER_SEEN, dtype=np.float64)

    @property
    def geometry(self) -> GridGeometry:
        """Return the grid geometry."""
        return self._geometry

    @property
    def last_seen(self) -> np.ndarray:
        """Return a read-only view of the per-cell last-observed times."""
        view = self._last_seen.view()
        view.setflags(write=False)
        return view

    def snapshot(self) -> np.ndarray:
        """Return an independent, read-only copy of the per-cell last-observed times."""
        copy = self._last_seen.copy()
        copy.setflags(write=False)
        return copy

    def observe(self, position: Sequence[float], radius: float, t: float) -> None:
        """
        Mark every cell whose centre lies within ``radius`` of ``position`` as seen at ``t``.

        The cell containing ``position`` is marked too when the position is
        inside the grid, so coverage still progresses when the footprint is
        smaller than a cell.
        """
        px, py = as_vec2(position, 'position')
        if not math.isfinite(radius) or radius < 0:
            raise ValueError(f'radius must be a non-negative number, got {radius!r}')
        if not math.isfinite(t):
            raise ValueError(f'observation time must be finite, got {t!r}')
        g = self._geometry
        if not g.bounds.contains((px, py), margin=radius):
            return
        ix0, iy0 = g.index_of((px - radius, py - radius))
        ix1, iy1 = g.index_of((px + radius, py + radius))
        dx = g.centers_x[ix0:ix1 + 1, None] - px
        dy = g.centers_y[None, iy0:iy1 + 1] - py
        inside = dx * dx + dy * dy <= radius * radius
        region = self._last_seen[ix0:ix1 + 1, iy0:iy1 + 1]
        region[inside] = np.maximum(region[inside], t)
        if g.bounds.contains((px, py)):
            ox, oy = g.index_of((px, py))
            if self._last_seen[ox, oy] < t:
                self._last_seen[ox, oy] = t

    def merge_cells(self, cells: np.ndarray, times: np.ndarray, now: float) -> int:
        """
        Fold a peer's sparse update into this map (element-wise maximum); return cells merged.

        ``cells`` are flat indices ``ix * ny + iy``. Timestamps later than
        ``now`` are clamped to ``now``, so a peer with a fast (or faulty)
        clock cannot mark cells as seen in the future and hide them from the
        search. Updates are rejected whole, before anything is merged, if
        any index is out of range or any time is not finite.
        """
        flat_cells = np.asarray(cells)
        stamps = np.asarray(times, dtype=np.float64)
        if flat_cells.ndim != 1 or stamps.shape != flat_cells.shape:
            raise ValueError('cells and times must be 1-D arrays of the same length')
        if flat_cells.size == 0:
            return 0
        if not np.issubdtype(flat_cells.dtype, np.integer):
            raise ValueError('cell indices must be integers')
        if int(flat_cells.min()) < 0 or int(flat_cells.max()) >= self._geometry.size:
            raise ValueError(f'cell index outside the {self._geometry.size}-cell grid')
        if not np.all(np.isfinite(stamps)):
            raise ValueError('coverage times must be finite')
        if not math.isfinite(now):
            raise ValueError(f'now must be finite, got {now!r}')
        flat = self._last_seen.reshape(-1)
        np.maximum.at(flat, flat_cells.astype(np.int64), np.minimum(stamps, now))
        return int(flat_cells.size)

    def cells_seen_since(self, since: float) -> Tuple[np.ndarray, np.ndarray]:
        """Return flat indices and times of valid cells observed at or after ``since``."""
        mask = (self._last_seen >= since) & self._geometry.valid & np.isfinite(self._last_seen)
        flat = np.flatnonzero(mask.reshape(-1))
        return flat.astype(np.uint32), self._last_seen.reshape(-1)[flat].copy()

    def priority(self, t: float) -> np.ndarray:
        """
        Return how stale each cell is at time ``t``, from 0 (just seen) to 1.

        Never-seen cells are 1 and invalid cells (outside the area) are 0.
        """
        staleness = np.clip((t - self._last_seen) / self._revisit_period, 0.0, 1.0)
        staleness[~self._geometry.valid] = 0.0
        return staleness

    def seen_fraction(self, t: float, window: float = math.inf) -> float:
        """Return the fraction of valid cells observed within ``window`` before ``t``."""
        seen = np.isfinite(self._last_seen) & ((t - self._last_seen) <= window)
        return float(np.count_nonzero(seen & self._geometry.valid)) / self._geometry.num_valid
