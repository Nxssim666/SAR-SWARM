"""
Terrain heights from offline DEM grids (ADR 0030).

A region's grid is a regular latitude/longitude raster of heights above mean sea level
(Copernicus GLO-30, EGM2008 geoid), written by ``scripts/fetch_region.py``: ``<id>.npy``
(float32, NaN where unknown) with a ``<id>.json`` header. Heights are interpolated
bilinearly; outside every grid, or next to an unknown cell, the height is unknown
(``None``), never a guess (ADR 0002, S7).
"""

import json
import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger(__name__)
_EDGE = 1e-6  # cells: a point on the grid's edge is inside despite floating-point rounding


@dataclass(frozen=True)
class TerrainGrid:
    """One region's heights: cell (0, 0) is centred at (``lat0``, ``lon0``), the north-west."""

    region: str
    heights: NDArray[np.float32]  # rows north to south, columns west to east
    lat0: float
    lon0: float
    lat_step: float  # degrees per row (southwards), > 0
    lon_step: float  # degrees per column (eastwards), > 0
    attribution: str = ""

    def elevation_amsl(self, latitude: float, longitude: float) -> float | None:
        """The height at a point, or None outside the grid or next to an unknown cell."""
        rows, cols = self.heights.shape
        row = (self.lat0 - latitude) / self.lat_step
        col = (longitude - self.lon0) / self.lon_step
        if not (-_EDGE <= row <= rows - 1 + _EDGE and -_EDGE <= col <= cols - 1 + _EDGE):
            return None
        row, col = min(max(row, 0.0), rows - 1.0), min(max(col, 0.0), cols - 1.0)
        r0, c0 = min(int(row), rows - 2), min(int(col), cols - 2)
        fr, fc = row - r0, col - c0
        cell = self.heights[r0 : r0 + 2, c0 : c0 + 2].astype(np.float64)
        if np.isnan(cell).any():
            return None
        top = cell[0, 0] * (1 - fc) + cell[0, 1] * fc
        bottom = cell[1, 0] * (1 - fc) + cell[1, 1] * fc
        return float(top * (1 - fr) + bottom * fr)

    def sample(
        self, latitudes: NDArray[np.float64], longitudes: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """Heights at many points at once (same rule as ``elevation_amsl``); NaN if unknown."""
        rows, cols = self.heights.shape
        row = (self.lat0 - latitudes) / self.lat_step
        col = (longitudes - self.lon0) / self.lon_step
        inside = (
            (row >= -_EDGE)
            & (row <= rows - 1 + _EDGE)
            & (col >= -_EDGE)
            & (col <= cols - 1 + _EDGE)
        )
        row, col = np.clip(row, 0.0, rows - 1.0), np.clip(col, 0.0, cols - 1.0)
        r0 = np.clip(np.floor(np.where(inside, row, 0.0)).astype(np.int64), 0, rows - 2)
        c0 = np.clip(np.floor(np.where(inside, col, 0.0)).astype(np.int64), 0, cols - 2)
        fr, fc = row - r0, col - c0
        h = self.heights.astype(np.float64)
        top = h[r0, c0] * (1 - fc) + h[r0, c0 + 1] * fc
        bottom = h[r0 + 1, c0] * (1 - fc) + h[r0 + 1, c0 + 1] * fc
        result = top * (1 - fr) + bottom * fr  # NaN if any corner is unknown
        return np.where(inside, result, np.nan)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """West, south, east, north of the cell centres."""
        rows, cols = self.heights.shape
        return (
            self.lon0,
            self.lat0 - (rows - 1) * self.lat_step,
            self.lon0 + (cols - 1) * self.lon_step,
            self.lat0,
        )


class TerrainSet:
    """Every loaded region; a point takes the first grid that knows its height."""

    def __init__(self, grids: Iterable[TerrainGrid] = ()) -> None:
        self.grids = list(grids)

    def elevation_amsl(self, latitude: float, longitude: float) -> float | None:
        """The height at a point, or None if no grid knows it."""
        for grid in self.grids:
            height = grid.elevation_amsl(latitude, longitude)
            if height is not None:
                return height
        return None

    def sample(
        self, latitudes: NDArray[np.float64], longitudes: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """Heights at many points; NaN where no grid knows the height."""
        result = np.full(np.shape(latitudes), np.nan)
        for grid in self.grids:
            unknown = np.isnan(result)
            if not unknown.any():
                break
            result[unknown] = grid.sample(latitudes[unknown], longitudes[unknown])
        return result

    def covers(self, points: Iterable[tuple[float, float]]) -> bool:
        """True if the height of every (latitude, longitude) point is known."""
        return all(self.elevation_amsl(lat, lon) is not None for lat, lon in points)

    @property
    def regions(self) -> list[str]:
        """The loaded regions' ids."""
        return [g.region for g in self.grids]

    @classmethod
    def load(cls, directory: Path) -> "TerrainSet":
        """Load every ``<id>.json`` + ``<id>.npy`` pair in ``directory`` (none: empty set)."""
        grids = []
        if directory.is_dir():
            for header_path in sorted(directory.glob("*.json")):
                try:
                    header = json.loads(header_path.read_text(encoding="utf-8"))
                    heights = np.load(header_path.with_suffix(".npy")).astype(np.float32)
                    grid = TerrainGrid(
                        region=str(header["region"]),
                        heights=heights,
                        lat0=float(header["lat0"]),
                        lon0=float(header["lon0"]),
                        lat_step=float(header["lat_step"]),
                        lon_step=float(header["lon_step"]),
                        attribution=str(header.get("attribution", "")),
                    )
                except (OSError, ValueError, KeyError) as exc:
                    log.warning("terrain %s not loaded: %s", header_path.name, exc)
                    continue
                if heights.shape != (header["rows"], header["cols"]) or not (
                    math.isfinite(grid.lat_step) and grid.lat_step > 0 and grid.lon_step > 0
                ):
                    log.warning("terrain %s not loaded: inconsistent header", header_path.name)
                    continue
                grids.append(grid)
        log.info("terrain regions loaded: %s", [g.region for g in grids] or "none")
        return cls(grids)
