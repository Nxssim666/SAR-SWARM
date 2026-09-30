"""
Lane patterns: parallel track (lawnmower) and creeping line (ADR 0028).

The area is cut into bands one lane spacing wide, perpendicular to the sweep; each band
is flown once along its middle, from where the band meets the area to where it leaves it.
The bands tile the area, so every point of it is within half a spacing of a lane.
Concave areas give bands with several pieces, each flown as its own lane.

Fixed-wing aircraft get run-in and run-out extensions of one turn radius, and lanes are
ordered so no U-turn is tighter than the turn diameter (``turns.lane_order``).
"""

import math
from collections.abc import Iterator

from shapely import MultiPolygon, Polygon, box
from shapely.affinity import rotate
from shapely.geometry.base import BaseGeometry

from fleet_service.domain.patterns.turns import infeasible_turns, lane_order, min_lane_gap

Point = tuple[float, float]
Segment = tuple[Point, Point]


def _pieces(geometry: BaseGeometry) -> Iterator[Polygon]:
    if isinstance(geometry, Polygon):
        if not geometry.is_empty and geometry.area > 0.0:
            yield geometry
        return
    for part in getattr(geometry, "geoms", ()):
        yield from _pieces(part)


def band_lanes(
    polygon: Polygon | MultiPolygon, spacing_m: float
) -> list[list[tuple[float, float, float]]]:
    """Per band (south to north in the given frame), the lanes as (y, x_min, x_max), west first.

    The frame is already rotated so lanes run along x.
    """
    min_x, min_y, max_x, max_y = polygon.bounds
    count = max(1, math.ceil((max_y - min_y) / spacing_m - 1e-9))
    bands = []
    for i in range(count):
        low = min_y + i * spacing_m
        band = box(min_x - 1.0, low, max_x + 1.0, low + spacing_m)
        lanes = [
            (low + spacing_m / 2.0, piece.bounds[0], piece.bounds[2])
            for piece in _pieces(polygon.intersection(band))
        ]
        bands.append(sorted(lanes, key=lambda lane: lane[1]))
    return [lanes for lanes in bands if lanes]


def lane_route(
    polygon: Polygon | MultiPolygon,
    spacing_m: float,
    lane_bearing_deg: float,
    turn_radius_m: float = 0.0,
    start: Point | None = None,
) -> tuple[list[Point], int]:
    """The metric route over ``polygon``: lanes along ``lane_bearing_deg``; infeasible turns.

    ``start`` (metres) picks the corner the route begins at: the lanes are flown from the
    side nearest to it.
    """
    # Rotate the world so the lanes run along +x: the lane direction (east, north) =
    # (sin b, cos b) has the mathematical angle atan2(cos b, sin b).
    angle = math.degrees(
        math.atan2(
            math.cos(math.radians(lane_bearing_deg)), math.sin(math.radians(lane_bearing_deg))
        )
    )
    turned = rotate(polygon, -angle, origin=(0.0, 0.0))
    bands = band_lanes(turned, spacing_m)
    if start is not None:
        sx, sy = _rotate_point(start, -angle)
        min_y, max_y = turned.bounds[1], turned.bounds[3]
        if abs(sy - max_y) < abs(sy - min_y):
            bands.reverse()
        min_x, max_x = turned.bounds[0], turned.bounds[2]
        east_first = abs(sx - min_x) <= abs(sx - max_x)
    else:
        east_first = True
    gap = min_lane_gap(spacing_m, turn_radius_m)
    order = lane_order(len(bands), gap)
    extension = turn_radius_m
    points: list[Point] = []
    for k, index in enumerate(order):
        eastwards = (k % 2 == 0) == east_first
        lanes = bands[index] if eastwards else list(reversed(bands[index]))
        for y, x_min, x_max in lanes:
            a, b = (x_min - extension, y), (x_max + extension, y)
            points.extend((a, b) if eastwards else (b, a))
    return [_rotate_point(p, angle) for p in points], infeasible_turns(order, gap)


def _rotate_point(point: Point, angle_deg: float) -> Point:
    rad = math.radians(angle_deg)
    x, y = point
    return x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad)
