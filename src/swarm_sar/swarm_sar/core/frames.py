"""
Coordinate frames, rotations and the camera mount.

Conventions (all right-handed; every conversion in the code base goes
through this module so there is exactly one place where a sign can be
wrong, and it is tested exhaustively):

* **local ENU**: x east, y north, z up, metres from the flight
  controller's local origin (where PX4's estimator started). Control,
  perception and collision avoidance run here, so none of the
  safety-critical maths depends on GPS consistency.
* **mission ENU**: x east, y north, metres from the mission origin; shared
  by every drone on the same mission (coverage grid, partition, target).
* **NED / FRD**: PX4's local frame (north, east, down) and body frame
  (forward, right, down).
* **optical**: the ROS camera convention, x right, y down, z forward.
* **heading**: ENU convention, radians counter-clockwise from east. PX4's
  yaw is clockwise from north, so ``yaw = pi/2 - heading``.

Quaternions are ``(w, x, y, z)`` (Hamilton), as in PX4 messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Sequence, Tuple

import numpy as np

from swarm_sar.core.geometry import as_vec3, Coordinates, Vec3, wrap_angle

_QUAT_NORM_TOLERANCE = 0.1


def _frozen(array: np.ndarray) -> np.ndarray:
    array.setflags(write=False)
    return array


# Maps NED vectors to ENU vectors (and back: it is its own inverse).
R_ENU_NED = _frozen(np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]]))
# Maps optical-frame vectors to FRD body vectors for a camera looking forward.
R_FRD_OPTICAL = _frozen(np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]))
# Rotation R_ENU_NED as a quaternion: 180 degrees about (1, 1, 0) / sqrt(2).
Q_ENU_NED = _frozen(np.array([0.0, math.sqrt(0.5), math.sqrt(0.5), 0.0]))


def ned_to_enu(v: Sequence[float]) -> Vec3:
    """Convert a NED vector or position to ENU."""
    return (float(v[1]), float(v[0]), -float(v[2]))


def enu_to_ned(v: Sequence[float]) -> Vec3:
    """Convert an ENU vector or position to NED."""
    return (float(v[1]), float(v[0]), -float(v[2]))


def px4_yaw_to_heading(yaw: float) -> float:
    """Convert PX4 yaw (clockwise from north) to ENU heading (counter-clockwise from east)."""
    return wrap_angle(math.pi / 2.0 - yaw)


def heading_to_px4_yaw(heading: float) -> float:
    """Convert ENU heading to PX4 yaw."""
    return wrap_angle(math.pi / 2.0 - heading)


def quat_normalized(q: Coordinates, name: str = 'quaternion') -> np.ndarray:
    """Return ``q`` as a unit quaternion array, rejecting non-finite or far-from-unit input."""
    arr = np.array(q, dtype=np.float64).reshape(-1)
    if arr.size != 4 or not np.all(np.isfinite(arr)):
        raise ValueError(f'{name} must be 4 finite numbers, got {q!r}')
    norm = float(np.linalg.norm(arr))
    if abs(norm - 1.0) > _QUAT_NORM_TOLERANCE:
        raise ValueError(f'{name} must be a unit quaternion, got norm {norm:.3f}')
    return arr / norm


def quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Return the Hamilton product ``a * b``."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw])


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """Return the rotation matrix of a unit quaternion."""
    w, x, y, z = q
    return np.array([
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)],
        [2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)],
        [2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)]])


def quat_slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Spherically interpolate between unit quaternions (shortest arc)."""
    dot = float(np.dot(a, b))
    if dot < 0.0:
        b = -b
        dot = -dot
    if dot > 0.9995:
        result = a + t * (b - a)
        return result / np.linalg.norm(result)
    theta = math.acos(min(dot, 1.0))
    sin_theta = math.sin(theta)
    return (math.sin((1.0 - t) * theta) * a + math.sin(t * theta) * b) / sin_theta


def px4_attitude_to_enu(q_ned_frd: Coordinates) -> np.ndarray:
    """Convert PX4's FRD-to-NED attitude quaternion into an FRD-to-ENU quaternion."""
    q = quat_multiply(Q_ENU_NED, quat_normalized(q_ned_frd, 'attitude'))
    return q / np.linalg.norm(q)


def level_attitude(heading: float) -> np.ndarray:
    """Return the FRD-to-ENU quaternion of a level vehicle pointing along ``heading``."""
    yaw = heading_to_px4_yaw(heading)
    q_ned_frd = np.array([math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)])
    return px4_attitude_to_enu(q_ned_frd)


def heading_from_rotation(r_enu_frd: np.ndarray) -> float:
    """Return the ENU heading of the body's forward axis."""
    forward = r_enu_frd[:, 0]
    return math.atan2(float(forward[1]), float(forward[0]))


def euler_frd(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """
    Return ``Rz(yaw) @ Ry(pitch) @ Rx(roll)`` in the FRD convention.

    Positive pitch raises the forward axis, positive yaw turns it to the
    right, positive roll lowers the right side.
    """
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    return rz @ ry @ rx


@dataclass(frozen=True)
class CameraMount:
    """Where the depth camera sits on the vehicle and which way it looks."""

    offset_frd: Vec3
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    r_frd_optical: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'offset_frd', as_vec3(self.offset_frd, 'camera offset'))
        for name in ('roll', 'pitch', 'yaw'):
            value = float(getattr(self, name))
            if not math.isfinite(value) or abs(value) > math.pi:
                raise ValueError(f'camera {name} must be within +-pi rad, got {value!r}')
            object.__setattr__(self, name, value)
        rotation = euler_frd(self.roll, self.pitch, self.yaw) @ R_FRD_OPTICAL
        object.__setattr__(self, 'r_frd_optical', _frozen(rotation))

    @classmethod
    def from_degrees(cls, offset_frd: Sequence[float],
                     rpy_deg: Tuple[float, float, float]) -> 'CameraMount':
        """Build a mount from an FRD offset and roll/pitch/yaw in degrees."""
        roll, pitch, yaw = (math.radians(float(v)) for v in rpy_deg)
        return cls(as_vec3(offset_frd, 'camera offset'), roll, pitch, yaw)
