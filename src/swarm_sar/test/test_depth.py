"""Tests for swarm_sar.core.depth: depth pixels to band-limited free space and obstacles."""

import math

import numpy as np
import pytest
from swarm_sar.core.depth import CameraIntrinsics, DepthFrame, DepthProjector
from swarm_sar.core.frames import CameraMount, level_attitude
from swarm_sar.core.pose import PoseSample

WIDTH, HEIGHT = 64, 36
FX = (WIDTH / 2.0) / math.tan(math.radians(87.0) / 2.0)
K = CameraIntrinsics(WIDTH, HEIGHT, FX, FX, (WIDTH - 1) / 2.0, (HEIGHT - 1) / 2.0)
TRUSTED = 8.0
BAND = 1.0
BIN = math.radians(1.0)


def projector(mount=None, stride=1):
    mount = mount or CameraMount((0.0, 0.0, 0.0))
    return DepthProjector(mount, stride, TRUSTED, BAND, BAND, BIN)


def pose(heading=0.0, position=(0.0, 0.0, 4.0)):
    return PoseSample(0.0, position, (0.0, 0.0, 0.0), level_attitude(heading))


def frame(depth):
    return DepthFrame(1.0, np.asarray(depth, dtype=np.float32), K)


def ground_depth(height):
    """Z-depth of flat ground ``height`` below a level camera (0 = no return above the horizon)."""
    vs = np.arange(HEIGHT, dtype=float)[:, None] - K.cy
    down = np.broadcast_to(vs / K.fy, (HEIGHT, WIDTH))
    with np.errstate(divide='ignore'):
        return np.where(down > 1e-9, height / down, 0.0)


def test_wall_ahead_gives_in_band_obstacles_and_free_space_up_to_it():
    s = projector().process(frame(np.full((HEIGHT, WIDTH), 5.0)), pose())
    assert s.valid_fraction == 1.0
    assert s.obstacles.shape[0] > 0
    np.testing.assert_allclose(s.obstacles[:, 0], 5.0, atol=1e-5)  # the wall is at x = 5
    assert np.abs(s.obstacles[:, 1]).max() <= 5.0 * math.tan(math.radians(43.5)) + 1e-6
    # Free space along each bearing reaches the wall and no further (within the bin width).
    upper = 5.0 / np.cos(np.abs(s.bearings) + BIN / 2.0)
    lower = 5.0 / np.cos(np.maximum(np.abs(s.bearings) - BIN / 2.0, 0.0))
    assert np.all(s.free_range <= upper + 1e-9) and np.all(s.free_range >= lower - 1e-9)


def test_only_the_band_counts_as_obstacle():
    s = projector().process(frame(np.full((HEIGHT, WIDTH), 5.0)), pose())
    heights = []
    rows = np.arange(HEIGHT)
    for v in rows:
        z = -(v - K.cy) / K.fy * 5.0
        heights.append(z)
    in_band_rows = sum(1 for z in heights if -BAND <= z <= BAND)
    assert s.obstacles.shape[0] == in_band_rows * WIDTH


def test_invalid_pixels_are_no_evidence_at_all():
    depth = np.zeros((HEIGHT, WIDTH))
    depth[0, :4] = [np.nan, np.inf, -1.0, 0.0]
    s = projector().process(frame(depth), pose())
    assert s.empty and s.valid_fraction == 0.0
    assert s.bearings.size == 0 and s.obstacles.shape == (0, 2)


def test_returns_beyond_the_trusted_range_are_free_up_to_it_but_not_obstacles():
    s = projector().process(frame(np.full((HEIGHT, WIDTH), 30.0)), pose())
    assert s.obstacles.shape[0] == 0
    assert s.free_range.max() == pytest.approx(TRUSTED, abs=0.05)
    assert s.free_range.max() <= TRUSTED + 1e-9


def test_ground_below_the_band_is_free_space_not_an_obstacle():
    s = projector().process(frame(ground_depth(3.0)), pose())
    assert s.obstacles.shape[0] == 0
    assert 0.0 < s.valid_fraction < 1.0  # the sky gives no return
    assert s.free_range.max() == pytest.approx(TRUSTED, abs=0.05)


def test_ground_inside_the_band_is_an_obstacle():
    # Flying 0.5 m above the ground: the ground itself is in the band (a slope or a bank).
    s = projector().process(frame(ground_depth(0.5)), pose())
    assert s.obstacles.shape[0] > 0
    assert s.free_range.max() < TRUSTED


def test_evidence_is_rotated_into_the_vehicle_heading():
    s = projector().process(frame(np.full((HEIGHT, WIDTH), 5.0)), pose(heading=math.pi / 2))
    np.testing.assert_allclose(s.obstacles[:, 1], 5.0, atol=1e-5)  # facing north
    assert np.all(np.abs(s.bearings - math.pi / 2) <= math.radians(44.0))


def test_camera_offset_moves_the_origin_and_the_points():
    mount = CameraMount((0.5, 0.0, 0.0))
    s = projector(mount).process(frame(np.full((HEIGHT, WIDTH), 5.0)),
                                 pose(heading=math.pi / 2, position=(10.0, 20.0, 4.0)))
    assert s.origin == pytest.approx((10.0, 20.5))
    np.testing.assert_allclose(s.obstacles[:, 1], 25.5, atol=1e-5)


def test_camera_yawed_right_looks_right():
    mount = CameraMount.from_degrees((0.0, 0.0, 0.0), (0.0, 0.0, 90.0))
    s = projector(mount).process(frame(np.full((HEIGHT, WIDTH), 5.0)), pose())
    np.testing.assert_allclose(s.obstacles[:, 1], -5.0, atol=1e-5)  # facing east, right = south


def test_stride_subsamples_pixels_without_changing_the_geometry():
    full = projector().process(frame(np.full((HEIGHT, WIDTH), 5.0)), pose())
    sparse = projector(stride=4).process(frame(np.full((HEIGHT, WIDTH), 5.0)), pose())
    assert 0 < sparse.obstacles.shape[0] < full.obstacles.shape[0]
    np.testing.assert_allclose(sparse.obstacles[:, 0], 5.0, atol=1e-5)


def test_projector_caches_rays_per_camera():
    p = projector()
    p.process(frame(np.full((HEIGHT, WIDTH), 5.0)), pose())
    other = CameraIntrinsics(32, 18, FX / 2, FX / 2, 15.5, 8.5)
    s = p.process(DepthFrame(1.0, np.full((18, 32), 5.0, dtype=np.float32), other), pose())
    np.testing.assert_allclose(s.obstacles[:, 0], 5.0, atol=1e-5)


@pytest.mark.parametrize('kwargs', [{'width': 0}, {'width': True}, {'height': 10000},
                                    {'fx': 0.0}, {'fy': -1.0}, {'cx': math.nan}])
def test_intrinsics_validation(kwargs):
    params = {'width': WIDTH, 'height': HEIGHT, 'fx': FX, 'fy': FX, 'cx': 31.5, 'cy': 17.5}
    params.update(kwargs)
    with pytest.raises(ValueError):
        CameraIntrinsics(**params)


def test_min_half_fov_takes_the_narrower_side():
    assert K.min_half_fov == pytest.approx(math.atan(32.0 / FX))
    off_centre = CameraIntrinsics(WIDTH, HEIGHT, FX, FX, 10.0, 17.5)
    assert off_centre.min_half_fov == pytest.approx(math.atan(10.5 / FX))
    assert CameraIntrinsics(WIDTH, HEIGHT, FX, FX, -5.0, 17.5).min_half_fov == 0.0


@pytest.mark.parametrize('depth, stamp, fragment', [
    (np.zeros((HEIGHT, WIDTH + 1), np.float32), 1.0, 'camera info'),
    (np.zeros((HEIGHT, WIDTH), np.uint16), 1.0, 'floating'),
    (np.zeros((HEIGHT, WIDTH, 1), np.float32), 1.0, '2-D'),
    (np.zeros((HEIGHT, WIDTH), np.float32), math.nan, 'stamp'),
])
def test_depth_frame_validation(depth, stamp, fragment):
    with pytest.raises(ValueError, match=fragment):
        DepthFrame(stamp, depth, K)


def test_projector_validation():
    mount = CameraMount((0.0, 0.0, 0.0))
    with pytest.raises(ValueError):
        DepthProjector(mount, 0, TRUSTED, BAND, BAND, BIN)
    with pytest.raises(ValueError):
        DepthProjector(mount, 1, math.inf, BAND, BAND, BIN)
    with pytest.raises(ValueError):
        DepthProjector(mount, 1, TRUSTED, 0.0, BAND, BIN)
