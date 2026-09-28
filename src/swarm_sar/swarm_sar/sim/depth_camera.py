"""
A synthetic depth camera: ray-casts vertical trunks and flat ground on the CPU.

It produces what a real stereo depth camera driver publishes: z-depth in
metres per pixel, with 0 for "no return" (beyond range, sky, dropout). It is
deliberately imperfect (relative noise, random invalid pixels) so the tests
exercise the rule that invalid pixels are never free space. Rendering needs
no GPU, which keeps the full perception-to-control loop testable on any
machine.
"""

from __future__ import annotations

import math

import numpy as np

from swarm_sar.core.depth import CameraIntrinsics
from swarm_sar.sim.world import Forest


def pinhole_intrinsics(width: int, height: int, hfov_rad: float) -> CameraIntrinsics:
    """Return square-pixel intrinsics with the given horizontal field of view."""
    fx = (width / 2.0) / math.tan(hfov_rad / 2.0)
    return CameraIntrinsics(width, height, fx, fx, (width - 1) / 2.0, (height - 1) / 2.0)


class SyntheticDepthCamera:
    """Render z-depth images of a ``Forest`` over flat ground."""

    def __init__(self, intrinsics: CameraIntrinsics, max_range: float, noise: float,
                 dropout: float, rng: np.random.Generator) -> None:
        if not math.isfinite(max_range) or max_range <= 0:
            raise ValueError('max_range must be positive')
        if not 0.0 <= noise < 1.0 or not 0.0 <= dropout < 1.0:
            raise ValueError('noise and dropout must be in [0, 1)')
        self.intrinsics = intrinsics
        self._max_range = float(max_range)
        self._noise = float(noise)
        self._dropout = float(dropout)
        self._rng = rng
        k = intrinsics
        us, vs = np.meshgrid(np.arange(k.width, dtype=np.float64),
                             np.arange(k.height, dtype=np.float64))
        self._rays = np.stack([(us - k.cx) / k.fx, (vs - k.cy) / k.fy, np.ones_like(us)],
                              axis=-1).reshape(-1, 3)

    def render(self, camera_position: np.ndarray, r_world_optical: np.ndarray,
               forest: Forest) -> np.ndarray:
        """Return a ``(height, width)`` float32 depth image in metres (0 = no return)."""
        k = self.intrinsics
        origin = np.asarray(camera_position, dtype=np.float64)
        dirs = self._rays @ np.asarray(r_world_optical).T  # optical z-component is 1: t = depth
        depth = np.full(dirs.shape[0], np.inf)

        down = dirs[:, 2] < -1e-9
        depth[down] = -origin[2] / dirs[down, 2]

        trees = forest.near(origin[:2], self._max_range)
        if len(trees):
            ox = origin[0] - trees.centers[:, 0]  # (T,)
            oy = origin[1] - trees.centers[:, 1]
            dx = dirs[:, 0:1]  # (P, 1)
            dy = dirs[:, 1:2]
            a = dx * dx + dy * dy
            b = 2.0 * (dx * ox + dy * oy)
            c = ox * ox + oy * oy - trees.radii * trees.radii
            disc = b * b - 4.0 * a * c
            with np.errstate(invalid='ignore', divide='ignore'):
                t = (-b - np.sqrt(np.maximum(disc, 0.0))) / (2.0 * a)
            z = origin[2] + t * dirs[:, 2:3]
            hit = (disc >= 0.0) & (a > 1e-12) & (t > 0.0) & (z >= 0.0) & (z <= trees.heights)
            t = np.where(hit, t, np.inf)
            depth = np.minimum(depth, t.min(axis=1))

        ranges = depth * np.linalg.norm(dirs, axis=1)
        valid = np.isfinite(depth) & (ranges <= self._max_range) & (depth > 0.0)
        if self._noise > 0.0:
            depth = depth * (1.0 + self._noise * self._rng.standard_normal(depth.shape))
        if self._dropout > 0.0:
            valid &= self._rng.random(depth.shape) >= self._dropout
        image = np.where(valid, depth, 0.0).astype(np.float32)
        return image.reshape(k.height, k.width)
