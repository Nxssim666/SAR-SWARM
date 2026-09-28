"""
Depth camera messages (``sensor_msgs/Image``, ``sensor_msgs/CameraInfo``) to core types.

Supports what depth drivers publish: ``16UC1`` (millimetres, 0 = no return,
e.g. Intel RealSense ``image_rect_raw``) and ``32FC1`` (metres, 0/NaN/inf =
no return). Images must be rectified; distortion coefficients are ignored.
Every size field is checked before the buffer is touched, so a malformed
message cannot make the node read out of bounds or allocate without limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from swarm_sar.core.depth import CameraIntrinsics, MAX_IMAGE_SIDE
from swarm_sar.ros.codec import MessageValidationError

_ENCODINGS = {'16UC1': (2, 'u2', 0.001), 'mono16': (2, 'u2', 0.001), '32FC1': (4, 'f4', 1.0)}


@dataclass(frozen=True)
class SensorTypes:
    """The ``sensor_msgs`` classes the drone node subscribes to."""

    Image: Any
    CameraInfo: Any

    @classmethod
    def load(cls) -> 'SensorTypes':
        """Import the real classes."""
        from sensor_msgs.msg import CameraInfo, Image
        return cls(Image, CameraInfo)


def decode_depth_image(msg: Any) -> np.ndarray:
    """Return the image as a ``(height, width)`` float32 array in metres (0 = no return)."""
    try:
        return _decode_depth_image(msg)
    except MessageValidationError:
        raise
    except (ValueError, TypeError, AttributeError, BufferError) as exc:
        raise MessageValidationError(f'invalid depth image: {exc}') from exc


def _decode_depth_image(msg: Any) -> np.ndarray:
    encoding = str(msg.encoding)
    if encoding not in _ENCODINGS:
        raise MessageValidationError(f'unsupported depth encoding {encoding!r} '
                                     f'(expected one of {sorted(_ENCODINGS)})')
    size, kind, scale = _ENCODINGS[encoding]
    height, width, step = int(msg.height), int(msg.width), int(msg.step)
    if not (1 <= height <= MAX_IMAGE_SIDE and 1 <= width <= MAX_IMAGE_SIDE):
        raise MessageValidationError(f'implausible image size {width}x{height}')
    if not width * size <= step <= MAX_IMAGE_SIDE * 8:
        raise MessageValidationError(f'row step {step} does not fit {width} pixels')
    data = memoryview(msg.data).cast('B')
    needed = step * (height - 1) + width * size
    if len(data) < needed:
        raise MessageValidationError(f'image buffer has {len(data)} bytes, needs {needed}')
    dtype = np.dtype(('>' if msg.is_bigendian else '<') + kind)
    rows = np.lib.stride_tricks.as_strided(
        np.frombuffer(data, dtype=np.uint8), shape=(height, width * size),
        strides=(step, 1), writeable=False)
    pixels = np.ascontiguousarray(rows).view(dtype).reshape(height, width)
    # Scale in float32: 16UC1 millimetres to metres; 32FC1 is metres already.
    return pixels.astype(np.float32) * np.float32(scale)


def decode_camera_info(msg: Any) -> CameraIntrinsics:
    """Return the pinhole intrinsics of a rectified image."""
    try:
        if int(msg.binning_x) > 1 or int(msg.binning_y) > 1:
            raise ValueError('binned camera info is not supported')
        roi = msg.roi
        if int(roi.width) or int(roi.height):
            if int(roi.width) != int(msg.width) or int(roi.height) != int(msg.height):
                raise ValueError('region-of-interest camera info is not supported')
        k = [float(v) for v in msg.k]
        if len(k) != 9:
            raise ValueError('K must have 9 elements')
        return CameraIntrinsics(int(msg.width), int(msg.height), k[0], k[4], k[2], k[5])
    except (ValueError, TypeError, AttributeError) as exc:
        raise MessageValidationError(f'invalid CameraInfo: {exc}') from exc
