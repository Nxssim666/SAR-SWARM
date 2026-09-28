"""
Depth images to planar obstacle evidence.

The vehicle flies level at a commanded altitude, so what matters is the
horizontal slab it sweeps: the *obstacle band* from ``band_below`` under to
``band_above`` over the vehicle centre. Each depth pixel is a ray from the
camera to a surface. The part of that ray inside the band is space the
camera has *proven* empty; a surface point inside the band is an obstacle.
Everything else, including every invalid pixel (no return, too close, too
far, glare, no texture) is *no evidence at all*, never free space.

The output, ``DepthScan``, bins that evidence by horizontal bearing: per
bin, how far free space is proven, plus the in-band obstacle points. Free
space along a bearing is capped at the nearest obstacle in that bearing,
because the vehicle occupies the whole band height.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Dict, Tuple

import numpy as np

from swarm_sar.core.frames import CameraMount
from swarm_sar.core.geometry import Vec2
from swarm_sar.core.pose import PoseSample

MAX_IMAGE_SIDE = 8192
_MIN_HORIZONTAL = 1e-3


@dataclass(frozen=True)
class CameraIntrinsics:
    """Pinhole intrinsics of a rectified depth image."""

    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float

    def __post_init__(self) -> None:
        for name in ('width', 'height'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) \
                    or not 1 <= value <= MAX_IMAGE_SIDE:
                raise ValueError(f'{name} must be an int in [1, {MAX_IMAGE_SIDE}], got {value!r}')
        for name in ('fx', 'fy', 'cx', 'cy'):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f'{name} must be finite, got {value!r}')
            object.__setattr__(self, name, value)
        if self.fx <= 0.0 or self.fy <= 0.0:
            raise ValueError('focal lengths must be positive')

    @property
    def min_half_fov(self) -> float:
        """Return the narrower of the two horizontal half-angles of view."""
        left = math.atan2(self.cx + 0.5, self.fx)
        right = math.atan2(self.width - 0.5 - self.cx, self.fx)
        return max(min(left, right), 0.0)


@dataclass(frozen=True, eq=False)
class DepthFrame:
    """One depth image in metres (0 or non-finite = no return) and its intrinsics."""

    stamp: float
    depth: np.ndarray
    intrinsics: CameraIntrinsics

    def __post_init__(self) -> None:
        if not math.isfinite(self.stamp):
            raise ValueError('stamp must be finite')
        depth = np.asarray(self.depth)
        if depth.ndim != 2:
            raise ValueError(f'depth must be a 2-D image, got shape {depth.shape}')
        if depth.shape != (self.intrinsics.height, self.intrinsics.width):
            raise ValueError(f'depth image is {depth.shape[1]}x{depth.shape[0]} but the camera '
                             f'info describes {self.intrinsics.width}x{self.intrinsics.height}')
        if not np.issubdtype(depth.dtype, np.floating):
            raise ValueError('depth must be floating point metres')
        object.__setattr__(self, 'depth', depth)


@dataclass(frozen=True, eq=False)
class DepthScan:
    """Planar free-space and obstacle evidence from one depth frame, in local ENU."""

    stamp: float
    origin: Vec2               # camera position (horizontal)
    bearings: np.ndarray       # (B,) bin-centre bearings with evidence [rad, ENU]
    free_range: np.ndarray     # (B,) proven-free horizontal distance along each bearing [m]
    obstacles: np.ndarray      # (M, 2) in-band obstacle points
    valid_fraction: float      # share of sampled pixels with a depth return
    empty: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'empty',
                           self.bearings.size == 0 and self.obstacles.shape[0] == 0)


class DepthProjector:
    """Turns depth frames into ``DepthScan`` evidence for a given camera mount."""

    def __init__(self, mount: CameraMount, stride: int, trusted_range: float,
                 band_above: float, band_below: float, bin_width: float) -> None:
        if stride < 1:
            raise ValueError('stride must be >= 1')
        for name, value in (('trusted_range', trusted_range), ('band_above', band_above),
                            ('band_below', band_below), ('bin_width', bin_width)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be positive, got {value!r}')
        self._mount = mount
        self._stride = int(stride)
        self._trusted = float(trusted_range)
        self._above = float(band_above)
        self._below = float(band_below)
        self._bins = max(1, int(round(2.0 * math.pi / bin_width)))
        self._bin_width = 2.0 * math.pi / self._bins
        self._ray_cache: Dict[Tuple[CameraIntrinsics, int], np.ndarray] = {}

    def _rays(self, k: CameraIntrinsics) -> np.ndarray:
        """Return optical-frame ray directions ``(x/z, y/z, 1)`` of the sampled pixels."""
        key = (k, self._stride)
        rays = self._ray_cache.get(key)
        if rays is None:
            us = np.arange(0, k.width, self._stride, dtype=np.float64)
            vs = np.arange(0, k.height, self._stride, dtype=np.float64)
            uu, vv = np.meshgrid(us, vs)  # rows = v, the same order as depth[::s, ::s]
            rays = np.stack([(uu - k.cx) / k.fx, (vv - k.cy) / k.fy, np.ones_like(uu)],
                            axis=-1).reshape(-1, 3)
            rays.setflags(write=False)
            self._ray_cache = {key: rays}  # one camera per drone: keep only the latest
        return rays

    def process(self, frame: DepthFrame, pose: PoseSample) -> DepthScan:
        """Project ``frame`` taken at ``pose`` into bearing-binned evidence (local ENU)."""
        rays = self._rays(frame.intrinsics)
        depth = frame.depth[::self._stride, ::self._stride].reshape(-1).astype(np.float64)
        valid = np.isfinite(depth) & (depth > 0.0)
        count = int(np.count_nonzero(valid))
        r_enu_optical = pose.rotation @ self._mount.r_frd_optical
        camera = pose.rotation @ np.asarray(self._mount.offset_frd)
        origin = (pose.position[0] + float(camera[0]), pose.position[1] + float(camera[1]))
        valid_fraction = count / depth.size if depth.size else 0.0
        if count == 0:
            return DepthScan(frame.stamp, origin, np.empty(0), np.empty(0), np.empty((0, 2)),
                             valid_fraction)

        points = rays[valid] * depth[valid, None]         # optical frame, metres
        length = np.linalg.norm(points, axis=1)
        far = length > self._trusted
        points[far] *= (self._trusted / length[far])[:, None]  # beyond trust: free up to it only
        rel = points @ r_enu_optical.T                      # camera-to-point vectors, ENU

        # Height along each ray relative to the vehicle centre: cz + t * dz for t in [0, 1].
        cz = float(camera[2])
        dz = rel[:, 2]
        end = cz + dz
        above = end > self._above
        below = end < -self._below
        t_exit = np.ones_like(dz)
        with np.errstate(divide='ignore', invalid='ignore'):
            t_exit[above] = (self._above - cz) / dz[above]
            t_exit[below] = (-self._below - cz) / dz[below]
        t_exit = np.clip(np.nan_to_num(t_exit, nan=0.0, posinf=0.0, neginf=0.0), 0.0, 1.0)

        horizontal = np.hypot(rel[:, 0], rel[:, 1])
        usable = horizontal > _MIN_HORIZONTAL
        free_len = horizontal * t_exit
        hit = usable & ~far & ~above & ~below
        bins = ((np.arctan2(rel[:, 1], rel[:, 0]) + math.pi) // self._bin_width).astype(np.int64)
        bins %= self._bins

        free_max = np.zeros(self._bins)
        np.maximum.at(free_max, bins[usable], free_len[usable])
        hit_min = np.full(self._bins, math.inf)
        np.minimum.at(hit_min, bins[hit], horizontal[hit])
        evidence = (free_max > 0.0) | np.isfinite(hit_min)
        index = np.flatnonzero(evidence)
        free_range = np.minimum(free_max, hit_min)[index]
        bearings = -math.pi + (index + 0.5) * self._bin_width
        obstacles = np.column_stack([origin[0] + rel[hit, 0], origin[1] + rel[hit, 1]])
        return DepthScan(frame.stamp, origin, bearings, free_range, obstacles, valid_fraction)
