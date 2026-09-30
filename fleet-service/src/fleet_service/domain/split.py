"""
Splitting a search area among aircraft (ADR 0029).

The area is cut into strips across the sweep direction, one per aircraft, with areas in
proportion to each aircraft's weight (cruise speed times endurance: what it can search). Each
strip keeps the full lane length, so every aircraft flies long lanes with few turns, and
strips never overlap, so aircraft searching them stay apart. Strips go to the aircraft in
the order of their starting positions across the sweep, so transits do not cross.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from shapely import MultiPolygon, Polygon, box
from shapely.affinity import rotate
from shapely.geometry.base import BaseGeometry

Area = Polygon | MultiPolygon
_BISECTIONS = 60


@dataclass(frozen=True)
class Share:
    """One aircraft's claim on the area; ``start`` (metres) orders the strips."""

    aircraft_id: str
    weight: float
    start: tuple[float, float] | None = None


def lane_angle(lane_bearing_deg: float) -> float:
    """The mathematical angle (degrees, counter-clockwise from east) of a lane bearing."""
    rad = math.radians(lane_bearing_deg)
    return math.degrees(math.atan2(math.cos(rad), math.sin(rad)))


def rotate_point(point: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    """Rotate a point about the origin, counter-clockwise, by ``angle_deg``."""
    rad = math.radians(angle_deg)
    x, y = point
    return x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad)


def _as_area(geometry: BaseGeometry) -> Area:
    if isinstance(geometry, Polygon | MultiPolygon):
        return geometry
    parts = [g for g in getattr(geometry, "geoms", ()) if isinstance(g, Polygon) and g.area > 0]
    return MultiPolygon(parts)


def split_area(
    area: Polygon, lane_bearing_deg: float, shares: Sequence[Share]
) -> list[tuple[str, Area]]:
    """Strips of ``area`` (metric), one per share, areas in proportion to the weights.

    Returned in strip order across the sweep; shares with a known start are ordered by it,
    the others follow in the given order.
    """
    if not shares:
        return []
    if any(not math.isfinite(s.weight) or s.weight <= 0.0 for s in shares):
        raise ValueError("every weight must be positive")
    angle = lane_angle(lane_bearing_deg)
    turned = rotate(area, -angle, origin=(0.0, 0.0))
    min_x, min_y, max_x, max_y = turned.bounds
    total_area = turned.area

    def band(low: float, high: float) -> BaseGeometry:
        return turned.intersection(box(min_x - 1.0, low, max_x + 1.0, high))

    def across(share: Share) -> float:
        return math.inf if share.start is None else rotate_point(share.start, -angle)[1]

    ordered = sorted(shares, key=across)  # stable: unknown starts keep their order, last
    total = sum(s.weight for s in ordered)
    cuts = [min_y - 1.0]
    running = 0.0
    for share in ordered[:-1]:
        running += share.weight
        target = total_area * running / total
        low, high = cuts[-1], max_y
        for _ in range(_BISECTIONS):
            mid = (low + high) / 2.0
            if band(min_y - 1.0, mid).area < target:
                low = mid
            else:
                high = mid
        cuts.append((low + high) / 2.0)
    cuts.append(max_y + 1.0)
    return [
        (share.aircraft_id, _as_area(rotate(band(low, high), angle, origin=(0.0, 0.0))))
        for share, low, high in zip(ordered, cuts, cuts[1:], strict=False)
    ]
