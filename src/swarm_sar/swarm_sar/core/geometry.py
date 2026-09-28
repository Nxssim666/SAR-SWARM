"""Planar geometry: vectors, angles, polygons and bounded Voronoi cells."""

from __future__ import annotations

from dataclasses import dataclass
import math
import numbers
from typing import Iterable, List, Sequence, Tuple, Union

import numpy as np

Vec2 = Tuple[float, float]
Vec3 = Tuple[float, float, float]
# Anything indexable as numbers: tuples, lists and numpy arrays alike.
Coordinates = Union[Sequence[float], np.ndarray]

_EPS = 1e-9
_CROSS_EPS = 1e-6  # m^2: tolerance for orientation tests on metre-scale coordinates
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


def as_vec2(value: Sequence[float], name: str = 'vector') -> Vec2:
    """Return ``value`` as a tuple of two finite floats, or raise ``ValueError``."""
    return _as_vec(value, 2, name)  # type: ignore[return-value]


def as_vec3(value: Sequence[float], name: str = 'vector') -> Vec3:
    """Return ``value`` as a tuple of three finite floats, or raise ``ValueError``."""
    return _as_vec(value, 3, name)  # type: ignore[return-value]


def _as_vec(value: Sequence[float], size: int, name: str) -> Tuple[float, ...]:
    try:
        if len(value) != size or isinstance(value, (str, bytes)):
            raise ValueError
        items = tuple(float(v) for v in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be {size} numbers, got {value!r}') from exc
    if not all(math.isfinite(v) for v in items):
        raise ValueError(f'{name} must be finite, got {value!r}')
    return items


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the planar Euclidean distance between two points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def saturate(v: Vec2, limit: float) -> Vec2:
    """Scale ``v`` down (never up) so that its norm is at most ``limit``."""
    norm = math.hypot(v[0], v[1])
    if norm <= limit or norm == 0.0:
        return (float(v[0]), float(v[1]))
    scale = limit / norm
    return (v[0] * scale, v[1] * scale)


def wrap_angle(angle: float) -> float:
    """Wrap ``angle`` into ``(-pi, pi]``."""
    wrapped = math.fmod(angle + math.pi, 2.0 * math.pi)
    if wrapped <= 0.0:
        wrapped += 2.0 * math.pi
    return wrapped - math.pi


def heading_of(v: Vec2) -> float:
    """Return the direction of ``v`` in radians counter-clockwise from +x."""
    return math.atan2(v[1], v[0])


def unit(angle: float) -> Vec2:
    """Return the unit vector pointing along ``angle``."""
    return (math.cos(angle), math.sin(angle))


def id_direction(agent_id: int) -> Vec2:
    """Return a deterministic unit vector derived from ``agent_id``."""
    return unit(_GOLDEN_ANGLE * agent_id)


def tie_break_direction(own_id: int, other_id: int) -> Vec2:
    """
    Return a unit vector that separates two agents sitting on the same point.

    The result is antisymmetric in the two ids, so the agents are always
    pushed in opposite directions, even when their positions are
    bit-identical and no geometric direction exists.
    """
    if own_id == other_id:
        raise ValueError('tie_break_direction needs two distinct ids')
    low, high = min(own_id, other_id), max(own_id, other_id)
    angle = _GOLDEN_ANGLE * (low * 7919 + high)
    sign = 1.0 if own_id < other_id else -1.0
    return (sign * math.cos(angle), sign * math.sin(angle))


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned rectangle, in metres."""

    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def __post_init__(self) -> None:
        for name in ('xmin', 'ymin', 'xmax', 'ymax'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise ValueError(f'bounds.{name} must be a number, got {value!r}')
            if not math.isfinite(value):
                raise ValueError(f'bounds.{name} must be finite, got {value!r}')
            object.__setattr__(self, name, float(value))
        if self.xmax <= self.xmin or self.ymax <= self.ymin:
            raise ValueError(
                f'bounds must satisfy xmin < xmax and ymin < ymax, got {self.as_tuple()}')

    @classmethod
    def from_sequence(cls, values: Iterable[float]) -> 'Bounds':
        """Build bounds from ``[xmin, ymin, xmax, ymax]``."""
        try:
            items = list(values)
        except TypeError as exc:
            raise ValueError(f'bounds must be a sequence of 4 numbers, got {values!r}') from exc
        if len(items) != 4:
            raise ValueError(
                f'bounds needs exactly 4 numbers [xmin, ymin, xmax, ymax], got {items}')
        return cls(*items)

    @classmethod
    def around(cls, points: Sequence[Sequence[float]]) -> 'Bounds':
        """Return the bounding box of ``points``."""
        if not points:
            raise ValueError('Bounds.around needs at least one point')
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
        return cls(min(xs), min(ys), max(xs), max(ys))

    def as_tuple(self) -> Tuple[float, float, float, float]:
        """Return ``(xmin, ymin, xmax, ymax)``."""
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    @property
    def width(self) -> float:
        """Return the extent along x."""
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        """Return the extent along y."""
        return self.ymax - self.ymin

    def contains(self, point: Sequence[float], margin: float = 0.0) -> bool:
        """Return True if ``point`` lies inside the bounds grown by ``margin``."""
        return (self.xmin - margin <= point[0] <= self.xmax + margin
                and self.ymin - margin <= point[1] <= self.ymax + margin)

    def clamp(self, point: Sequence[float]) -> Vec2:
        """Return the closest point inside the bounds."""
        return (min(max(float(point[0]), self.xmin), self.xmax),
                min(max(float(point[1]), self.ymin), self.ymax))


def clip_polygon_halfplane(polygon: Sequence[Vec2], anchor: Vec2, normal: Vec2) -> List[Vec2]:
    """
    Clip a convex polygon to the half-plane ``dot(p - anchor, normal) <= 0``.

    This is one Sutherland-Hodgman pass. ``normal`` is normalised first so
    the on-the-line tolerance is expressed in metres whatever its length.
    """
    norm = math.hypot(normal[0], normal[1])
    if norm == 0.0:
        return [(float(p[0]), float(p[1])) for p in polygon]
    nx, ny = normal[0] / norm, normal[1] / norm

    def side(p: Vec2) -> float:
        return (p[0] - anchor[0]) * nx + (p[1] - anchor[1]) * ny

    clipped: List[Vec2] = []
    for i in range(len(polygon)):
        cur, prev = polygon[i], polygon[i - 1]
        s_cur, s_prev = side(cur), side(prev)
        cur_in, prev_in = s_cur <= _EPS, s_prev <= _EPS
        if cur_in != prev_in:
            t = min(max(s_prev / (s_prev - s_cur), 0.0), 1.0)
            clipped.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
        if cur_in:
            clipped.append((float(cur[0]), float(cur[1])))
    return clipped


def voronoi_cell(center: Vec2, neighbors: Iterable[Vec2], bounds: Bounds) -> List[Vec2]:
    """
    Return the Voronoi cell of ``center`` among ``neighbors``, clipped to ``bounds``.

    Only the neighbours passed in are considered, which is exactly the
    information a range-limited robot has; a neighbour at the same point
    as ``center`` has no separating bisector and is skipped.
    """
    polygon: List[Vec2] = [(bounds.xmin, bounds.ymin), (bounds.xmax, bounds.ymin),
                           (bounds.xmax, bounds.ymax), (bounds.xmin, bounds.ymax)]
    cx, cy = center
    for qx, qy in neighbors:
        dx, dy = qx - cx, qy - cy
        if dx * dx + dy * dy < _EPS * _EPS:
            continue
        polygon = clip_polygon_halfplane(polygon, ((cx + qx) / 2.0, (cy + qy) / 2.0), (dx, dy))
        if not polygon:
            break
    return polygon


def signed_area(polygon: Sequence[Vec2]) -> float:
    """Return the signed area of a polygon (positive when counter-clockwise)."""
    twice = 0.0
    for i in range(len(polygon)):
        x0, y0 = polygon[i - 1]
        x1, y1 = polygon[i]
        twice += x0 * y1 - x1 * y0
    return twice / 2.0


def polygon_area_centroid(polygon: Sequence[Vec2]) -> Tuple[Vec2, float]:
    """
    Return ``(centroid, area)`` of a simple polygon (shoelace formula).

    Degenerate input (fewer than three vertices or zero area) returns the
    vertex average and an area of zero instead of dividing by zero.
    """
    count = len(polygon)
    if count == 0:
        raise ValueError('polygon_area_centroid needs at least one vertex')
    mean = (sum(p[0] for p in polygon) / count, sum(p[1] for p in polygon) / count)
    if count < 3:
        return mean, 0.0
    twice_area = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(count):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % count]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(twice_area) < _EPS:
        return mean, 0.0
    return (cx / (3.0 * twice_area), cy / (3.0 * twice_area)), abs(twice_area) / 2.0


def points_in_polygon(xs: np.ndarray, ys: np.ndarray, polygon: Sequence[Vec2]) -> np.ndarray:
    """Return a boolean array: which points lie inside ``polygon`` (even-odd rule)."""
    px = np.asarray(xs, dtype=np.float64)
    py = np.asarray(ys, dtype=np.float64)
    inside = np.zeros(np.broadcast(px, py).shape, dtype=bool)
    for i in range(len(polygon)):
        x0, y0 = polygon[i - 1]
        x1, y1 = polygon[i]
        if y0 == y1:
            continue  # a horizontal edge is never crossed by the rightward ray
        crosses = (y0 > py) != (y1 > py)
        x_at = x0 + (py - y0) * (x1 - x0) / (y1 - y0)
        inside ^= crosses & (px < x_at)
    return inside


def point_in_polygon(point: Sequence[float], polygon: Sequence[Vec2]) -> bool:
    """Return True if ``point`` lies inside ``polygon``."""
    return bool(points_in_polygon(np.array(point[0]), np.array(point[1]), polygon))


def _orientation(a: Vec2, b: Vec2, c: Vec2) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _within_box(a: Vec2, b: Vec2, p: Vec2) -> bool:
    return (min(a[0], b[0]) - _EPS <= p[0] <= max(a[0], b[0]) + _EPS
            and min(a[1], b[1]) - _EPS <= p[1] <= max(a[1], b[1]) + _EPS)


def segments_intersect(p1: Vec2, p2: Vec2, q1: Vec2, q2: Vec2) -> bool:
    """Return True if segments ``p1p2`` and ``q1q2`` share any point (touching counts)."""
    d1 = _orientation(q1, q2, p1)
    d2 = _orientation(q1, q2, p2)
    d3 = _orientation(p1, p2, q1)
    d4 = _orientation(p1, p2, q2)
    if (((d1 > _CROSS_EPS and d2 < -_CROSS_EPS) or (d1 < -_CROSS_EPS and d2 > _CROSS_EPS))
            and ((d3 > _CROSS_EPS and d4 < -_CROSS_EPS)
                 or (d3 < -_CROSS_EPS and d4 > _CROSS_EPS))):
        return True
    return ((abs(d1) <= _CROSS_EPS and _within_box(q1, q2, p1))
            or (abs(d2) <= _CROSS_EPS and _within_box(q1, q2, p2))
            or (abs(d3) <= _CROSS_EPS and _within_box(p1, p2, q1))
            or (abs(d4) <= _CROSS_EPS and _within_box(p1, p2, q2)))


def normalize_polygon(vertices: Sequence[Sequence[float]], min_area: float = 0.0
                      ) -> Tuple[Vec2, ...]:
    """
    Validate a polygon and return it as a counter-clockwise tuple of vertices.

    Accepts an explicitly closed ring (last vertex equal to the first) and
    drops repeated consecutive vertices. Rejects fewer than three distinct
    vertices, self-intersections and areas below ``min_area``, because every
    downstream consumer (grid masks, point-in-polygon tests) silently
    misbehaves on such input.
    """
    points: List[Vec2] = []
    for i, vertex in enumerate(vertices):
        p = as_vec2(vertex, f'vertex {i}')
        if not points or distance(points[-1], p) > _EPS:
            points.append(p)
    if len(points) > 1 and distance(points[0], points[-1]) <= _EPS:
        points.pop()
    count = len(points)
    if count < 3:
        raise ValueError(f'a polygon needs at least 3 distinct vertices, got {count}')
    for i in range(count):
        a1, a2 = points[i], points[(i + 1) % count]
        for j in range(i + 1, count):
            if j == i or (j + 1) % count == i or j == (i + 1) % count:
                continue  # adjacent edges share a vertex by construction
            if segments_intersect(a1, a2, points[j], points[(j + 1) % count]):
                raise ValueError(f'polygon edges {i} and {j} intersect')
    area = signed_area(points)
    if abs(area) <= max(min_area, _EPS):
        raise ValueError(f'polygon area {abs(area):.3g} m^2 is below the minimum {min_area} m^2')
    if area < 0.0:
        points.reverse()
    return tuple(points)
