"""Tests for swarm_sar.ros.sensors: depth images and camera info, treated as untrusted input."""

import array
import math

from fake_msgs import FakeMessages
import numpy as np
import pytest
from swarm_sar.ros.codec import MessageValidationError
from swarm_sar.ros.sensors import decode_camera_info, decode_depth_image

FAKES = FakeMessages()
Image = FAKES.get('sensor_msgs/Image')
CameraInfo = FAKES.get('sensor_msgs/CameraInfo')


def image(pixels, encoding, step=None, bigendian=False):
    pixels = np.asarray(pixels)
    msg = Image()
    msg.height, msg.width = int(pixels.shape[0]), int(pixels.shape[1])
    msg.encoding = encoding
    msg.is_bigendian = 1 if bigendian else 0
    row_bytes = pixels.shape[1] * pixels.itemsize
    msg.step = int(step if step is not None else row_bytes)
    rows = [pixels[r].tobytes() + bytes(msg.step - row_bytes) for r in range(pixels.shape[0])]
    msg.data = array.array('B', b''.join(rows))
    return msg


def test_16uc1_millimetres_become_metres():
    raw = np.array([[0, 1000], [2500, 65535]], dtype='<u2')
    depth = decode_depth_image(image(raw, '16UC1'))
    assert depth.dtype == np.float32
    np.testing.assert_allclose(depth, [[0.0, 1.0], [2.5, 65.535]], rtol=1e-6)


def test_32fc1_keeps_invalid_markers_and_honours_endianness():
    raw = np.array([[1.5, np.nan], [np.inf, 0.0]], dtype='>f4')
    depth = decode_depth_image(image(raw, '32FC1', bigendian=True))
    assert depth[0, 0] == 1.5 and math.isnan(depth[0, 1]) and math.isinf(depth[1, 0])


def test_row_padding_is_skipped():
    raw = np.array([[1, 2, 3], [4, 5, 6]], dtype='<u2')
    depth = decode_depth_image(image(raw, 'mono16', step=16))
    np.testing.assert_allclose(depth, [[0.001, 0.002, 0.003], [0.004, 0.005, 0.006]])


@pytest.mark.parametrize('mutate, fragment', [
    (lambda m: setattr(m, 'encoding', 'rgb8'), 'encoding'),
    (lambda m: setattr(m, 'height', 0), 'size'),
    (lambda m: setattr(m, 'width', 100_000), 'size'),
    (lambda m: setattr(m, 'step', 2), 'step'),
    (lambda m: setattr(m, 'step', 10 ** 9), 'step'),
    (lambda m: setattr(m, 'data', array.array('B', bytes(3))), 'buffer'),
    (lambda m: setattr(m, 'height', 3), 'buffer'),
])
def test_malformed_images_are_rejected_before_touching_memory(mutate, fragment):
    msg = image(np.ones((2, 2), dtype='<u2'), '16UC1')
    mutate(msg)
    with pytest.raises(MessageValidationError, match=fragment):
        decode_depth_image(msg)


def test_unexpected_buffer_types_are_validation_errors():
    msg = image(np.ones((2, 2), dtype='<u2'), '16UC1')
    object.__setattr__(msg, '_data', [1, 2, 3, 4, 5, 6, 7, 8])  # a list has no buffer
    with pytest.raises(MessageValidationError):
        decode_depth_image(msg)


def camera_info(**fields):
    msg = CameraInfo()
    msg.width, msg.height = 848, 480
    msg.k = np.array([420.0, 0.0, 424.5, 0.0, 421.0, 239.5, 0.0, 0.0, 1.0])
    for name, value in fields.items():
        setattr(msg, name, value)
    return msg


def test_camera_info_to_intrinsics():
    k = decode_camera_info(camera_info())
    assert (k.width, k.height, k.fx, k.fy, k.cx, k.cy) == (848, 480, 420.0, 421.0, 424.5, 239.5)
    assert math.degrees(2 * k.min_half_fov) == pytest.approx(90.5, abs=0.5)


def test_camera_info_with_full_frame_roi_is_accepted():
    info = camera_info()
    info.roi.width, info.roi.height = 848, 480
    assert decode_camera_info(info).width == 848


@pytest.mark.parametrize('fields', [{'binning_x': 2}, {'k': np.zeros(9)},
                                    {'width': 0}])
def test_unsupported_or_invalid_camera_info_is_rejected(fields):
    with pytest.raises(MessageValidationError):
        decode_camera_info(camera_info(**fields))


def test_cropped_camera_info_is_rejected():
    info = camera_info()
    info.roi.width, info.roi.height = 400, 240
    with pytest.raises(MessageValidationError, match='region-of-interest'):
        decode_camera_info(info)
