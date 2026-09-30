"""
Contour search (ADR 0028): fly along the terrain's contour lines at a constant height above
them, so a slope is searched at a steady distance. Contours are drawn from the offline DEM
(``domain.terrain``) with contourpy, one height step apart, where the step keeps
neighbouring contours about one lane spacing apart on the typical slope of the area.

Without terrain for the whole area there are no contours: the fallback flies rings offset
inwards from the area's edge, one spacing apart, and is marked as a fallback.
"""

import math
from collections.abc import Callable, Iterator

import numpy as np
from contourpy import contour_generator
from shapely import LineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

Point = tuple[float, float]
MAX_GRID = 300  # samples per side of the terrain grid drawn under the area
MIN_STEP_M = 1.0


def _lines(geometry: BaseGeometry) -> Iterator[LineString]:
    if isinstance(geometry, LineString):
        if not geometry.is_empty:
            yield geometry
        return
    for part in getattr(geometry, "geoms", ()):
        yield from _lines(part)


def _chain(lines: list[list[Point]], start: Point | None) -> list[Point]:
    """Join lines greedily: next the nearest line end, reversed if its far end is nearer."""
    points: list[Point] = []
    here = start
    remaining = list(lines)
    while remaining:
        best, flip = 0, False
        if here is not None:
            ends = [
                (math.dist(here, line[-1] if reverse else line[0]), i, reverse)
                for i, line in enumerate(remaining)
                for reverse in (False, True)
            ]
            _, best, flip = min(ends)
        line = remaining.pop(best)
        if flip:
            line = list(reversed(line))
        points.extend(line)
        here = line[-1]
    return points


def contour_lines(
    polygon: Polygon | MultiPolygon,
    spacing_m: float,
    heights: Callable[[np.ndarray, np.ndarray], np.ndarray],
) -> list[tuple[float, list[Point]]] | None:
    """(level, metric line) pairs clipped to ``polygon``, lowest first; None without terrain.

    ``heights(x, y)`` returns the terrain height at metric points (NaN where unknown).
    """
    min_x, min_y, max_x, max_y = polygon.bounds
    resolution = max(spacing_m / 2.0, max(max_x - min_x, max_y - min_y) / MAX_GRID, 1.0)
    xs = np.arange(min_x, max_x + resolution, resolution)
    ys = np.arange(min_y, max_y + resolution, resolution)
    gx, gy = np.meshgrid(xs, ys)
    z = heights(gx, gy)
    if np.isnan(z).any():
        return None
    dz_dy, dz_dx = np.gradient(z, resolution)
    slope = float(np.median(np.hypot(dz_dx, dz_dy)))
    step = max(MIN_STEP_M, spacing_m * slope)
    low, high = float(np.min(z)), float(np.max(z))
    levels = np.arange(math.ceil(low / step) * step, high, step)
    generator = contour_generator(x=xs, y=ys, z=z)
    result: list[tuple[float, list[Point]]] = []
    for level in levels:
        for raw in generator.lines(float(level)):
            array = np.asarray(raw)
            if len(array) < 2:
                continue
            clipped = LineString(array).intersection(polygon)
            for piece in _lines(clipped):
                if piece.length < spacing_m:
                    continue
                simple = piece.simplify(spacing_m / 5.0)
                result.append((float(level), [(float(x), float(y)) for x, y in simple.coords]))
    return result


def contour_route(
    lines: list[tuple[float, list[Point]]], start: Point | None
) -> list[tuple[float, list[Point]]]:
    """Order the lines: level by level from the lowest, each level chained nearest-first."""
    route: list[tuple[float, list[Point]]] = []
    here = start
    for level in sorted({level for level, _ in lines}):
        chained = _chain([line for lv, line in lines if lv == level], here)
        if chained:
            route.append((level, chained))
            here = chained[-1]
    return route


def perimeter_rings(
    polygon: Polygon | MultiPolygon, spacing_m: float, start: Point | None
) -> list[Point]:
    """The fallback: rings offset inwards by ½, 1½, 2½ ... spacings, outermost first."""
    rings: list[list[Point]] = []
    offset = spacing_m / 2.0
    while True:
        inner = polygon.buffer(-offset)
        if inner.is_empty:
            break
        parts = [inner] if isinstance(inner, Polygon) else list(getattr(inner, "geoms", ()))
        for part in parts:
            if isinstance(part, Polygon) and not part.is_empty:
                rings.append([(float(x), float(y)) for x, y in part.exterior.coords])
        offset += spacing_m
    if not rings:  # thinner than one spacing: fly its centre line
        centre = polygon.centroid
        return [(float(centre.x), float(centre.y))]
    points: list[Point] = []
    here = start
    for ring in rings:
        if here is not None:  # enter each ring at its vertex nearest to where we are
            hx, hy = here
            first = min(
                range(len(ring) - 1), key=lambda i: math.hypot(ring[i][0] - hx, ring[i][1] - hy)
            )
            ring = ring[first:-1] + ring[:first] + [ring[first]]
        points.extend(ring)
        here = ring[-1]
    return points
