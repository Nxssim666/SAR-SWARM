"""
The simulated world: trees, the lost person, the search detector and the mission layout.

Everything here is ground truth in the mission frame (ENU metres around the
mission origin). The flight code never sees it directly: trees reach it only
through synthetic depth images, the target only through noisy georeferenced
detections, and the mission only through a ``MissionSpec``.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from swarm_sar.core.config import SimConfig
from swarm_sar.core.geodesy import GeoPoint, LocalProjection
from swarm_sar.core.geometry import as_vec2, Bounds, Coordinates, point_in_polygon, Vec2
from swarm_sar.core.messages import MissionSpec, TargetReport

TREE_HEIGHT = 15.0
_MAX_WAYPOINTS_PER_STEP = 16
_MAX_SAMPLE_ATTEMPTS = 1000
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))
# Smallest neighbour distance of the spiral r = sqrt(n + 0.5), theta = n * golden angle.
_SUNFLOWER_MIN_GAP = 1.54


class Forest:
    """Vertical cylindrical trunks standing on flat ground (z = 0)."""

    def __init__(self, centers: np.ndarray, radii: np.ndarray,
                 heights: Optional[np.ndarray] = None) -> None:
        centers = np.asarray(centers, dtype=np.float64).reshape(-1, 2)
        radii = np.asarray(radii, dtype=np.float64).reshape(-1)
        if radii.shape[0] != centers.shape[0]:
            raise ValueError('one radius per tree centre is required')
        if heights is None:
            heights = np.full(radii.shape, TREE_HEIGHT)
        heights = np.asarray(heights, dtype=np.float64).reshape(-1)
        if heights.shape != radii.shape:
            raise ValueError('one height per tree is required')
        if not (np.all(np.isfinite(centers)) and np.all(radii > 0) and np.all(heights > 0)):
            raise ValueError('tree geometry must be finite and positive')
        for array in (centers, radii, heights):
            array.setflags(write=False)
        self.centers = centers
        self.radii = radii
        self.heights = heights

    @classmethod
    def empty(cls) -> 'Forest':
        """Return a world without trees."""
        return cls(np.empty((0, 2)), np.empty(0))

    @classmethod
    def random(cls, bounds: Bounds, density_per_ha: float, radius_range: Tuple[float, float],
               keep_out: Sequence[Tuple[Vec2, float]], rng: np.random.Generator) -> 'Forest':
        """
        Scatter trunks uniformly, keeping ``keep_out`` discs clear.

        Trunks keep 2 m of air between each other so the forest is dense but
        passable, which is what a search drone should be able to fly through.
        """
        area_ha = bounds.width * bounds.height / 10_000.0
        count = int(round(density_per_ha * area_ha))
        gap = 2.0
        cell = 2.0 * radius_range[1] + gap  # any conflicting trunk is in a neighbouring cell
        buckets: Dict[Tuple[int, int], List[Tuple[Vec2, float]]] = {}
        centers: List[Vec2] = []
        radii: List[float] = []
        attempts = 0
        while len(centers) < count and attempts < count * 50 + 100:
            attempts += 1
            p = (float(rng.uniform(bounds.xmin, bounds.xmax)),
                 float(rng.uniform(bounds.ymin, bounds.ymax)))
            r = float(rng.uniform(radius_range[0], radius_range[1]))
            if any(math.dist(p, c) < radius + r for c, radius in keep_out):
                continue
            key = (int(math.floor(p[0] / cell)), int(math.floor(p[1] / cell)))
            nearby = (tree for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                      for tree in buckets.get((key[0] + dx, key[1] + dy), ()))
            if any(math.dist(p, c) < rc + r + gap for c, rc in nearby):
                continue
            buckets.setdefault(key, []).append((p, r))
            centers.append(p)
            radii.append(r)
        return cls(np.array(centers).reshape(-1, 2), np.array(radii))

    def __len__(self) -> int:
        return int(self.radii.shape[0])

    def clearance(self, point: Coordinates, altitude: float = 0.0) -> float:
        """Return the horizontal distance from ``point`` to the nearest trunk surface."""
        if len(self) == 0:
            return math.inf
        tall = self.heights >= altitude
        if not tall.any():
            return math.inf
        gaps = (np.hypot(self.centers[tall, 0] - point[0], self.centers[tall, 1] - point[1])
                - self.radii[tall])
        return float(gaps.min())

    def near(self, point: Coordinates, radius: float) -> 'Forest':
        """Return the trees whose surface lies within ``radius`` of ``point``."""
        if len(self) == 0:
            return self
        gaps = np.hypot(self.centers[:, 0] - point[0], self.centers[:, 1] - point[1]) - self.radii
        keep = gaps <= radius
        return Forest(self.centers[keep], self.radii[keep], self.heights[keep])


class Target:
    """A lost person walking between random points inside the area at constant speed."""

    def __init__(self, area: Sequence[Vec2], speed: float, rng: np.random.Generator,
                 position: Vec2) -> None:
        if not math.isfinite(speed) or speed < 0:
            raise ValueError(f'speed must be a non-negative number, got {speed!r}')
        self._area = tuple(area)
        self._speed = float(speed)
        self._rng = rng
        self._position = as_vec2(position, 'position')
        self._waypoint = sample_in_polygon(self._area, rng)

    @property
    def position(self) -> Vec2:
        """Return the true position."""
        return self._position

    def step(self, dt: float) -> None:
        """Walk for ``dt`` seconds, rolling over as many waypoints as needed."""
        if not math.isfinite(dt) or dt < 0:
            raise ValueError(f'dt must be a non-negative number, got {dt!r}')
        remaining = self._speed * dt
        x, y = self._position
        for _ in range(_MAX_WAYPOINTS_PER_STEP):
            if remaining <= 0.0:
                break
            wx, wy = self._waypoint
            gap = math.hypot(wx - x, wy - y)
            if gap <= remaining:
                x, y = wx, wy
                remaining -= gap
                self._waypoint = sample_in_polygon(self._area, self._rng)
            else:
                x += (wx - x) / gap * remaining
                y += (wy - y) / gap * remaining
                remaining = 0.0
        self._position = (x, y)


class SearchDetector:
    """The downward search camera plus person detector, reduced to a noisy disc footprint."""

    def __init__(self, detection_range: float, noise_std: float, probability: float,
                 projection: LocalProjection) -> None:
        if not math.isfinite(detection_range) or detection_range <= 0:
            raise ValueError('detection_range must be positive')
        if not math.isfinite(noise_std) or noise_std < 0:
            raise ValueError('noise_std must be non-negative')
        if not 0.0 < probability <= 1.0:
            raise ValueError('probability must be in (0, 1]')
        self._range = float(detection_range)
        self._noise = float(noise_std)
        self._pd = float(probability)
        self._projection = projection

    def sense(self, drone: Vec2, target: Vec2, stamp: float,
              rng: np.random.Generator) -> Optional[TargetReport]:
        """Return a georeferenced report, or None if out of view or missed."""
        if math.dist(drone, target) > self._range:
            return None
        if self._pd < 1.0 and rng.random() >= self._pd:
            return None
        nx, ny = rng.normal(0.0, self._noise, 2) if self._noise > 0.0 else (0.0, 0.0)
        where = self._projection.to_geo(target[0] + float(nx), target[1] + float(ny))
        return TargetReport(stamp, where, max(self._noise, 0.1), 0.9)


def sample_in_polygon(polygon: Sequence[Vec2], rng: np.random.Generator) -> Vec2:
    """Draw a uniform random point inside ``polygon`` (rejection sampling)."""
    box = Bounds.around(polygon)
    for _ in range(_MAX_SAMPLE_ATTEMPTS):
        p = (float(rng.uniform(box.xmin, box.xmax)), float(rng.uniform(box.ymin, box.ymax)))
        if point_in_polygon(p, polygon):
            return p
    raise ValueError('could not sample a point inside the polygon')


def spawn_positions(count: int, spacing: float, center: Vec2 = (0.0, 0.0)) -> List[Vec2]:
    """
    Return launch positions on a sunflower (Vogel) spiral around ``center``.

    Deterministic per index and at least ``spacing`` apart for any count.
    """
    out = []
    for i in range(count):
        radius = spacing / _SUNFLOWER_MIN_GAP * math.sqrt(i + 0.5)
        angle = _GOLDEN_ANGLE * i
        out.append((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)))
    return out


def mission_layout(sim: SimConfig) -> Tuple[Tuple[Vec2, ...], Tuple[Vec2, ...]]:
    """
    Return ``(waypoints, area)`` in the mission frame for a simulated mission.

    The launch site is the mission origin. Two transit waypoints form a
    dogleg toward a square area whose near edge is ``transit_distance`` away.
    """
    t, a = sim.transit_distance, sim.area_size
    area = ((t, -a / 2.0), (t + a, -a / 2.0), (t + a, a / 2.0), (t, a / 2.0))
    waypoints = ((0.5 * t, 0.25 * a), (t + 5.0, 0.0)) if t > 0 else ()
    return waypoints, area


def mission_spec(sim: SimConfig, sequence: int = 1, mission_id: str = 'sim') -> MissionSpec:
    """Return the ``MissionSpec`` the simulated ground station sends."""
    origin = GeoPoint(sim.origin_latitude, sim.origin_longitude)
    projection = LocalProjection(origin)
    waypoints, area = mission_layout(sim)
    return MissionSpec(sequence=sequence, mission_id=mission_id, origin=origin,
                       altitude=sim.altitude, grid_resolution=sim.grid_resolution,
                       waypoints=tuple(projection.to_geo(x, y) for x, y in waypoints),
                       area=tuple(projection.to_geo(x, y) for x, y in area))
