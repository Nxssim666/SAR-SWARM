"""
Flight-controller state as the core sees it, and a short pose history for sensor fusion.

The flight-controller adapter (``swarm_sar.ros.px4`` for PX4) converts
autopilot messages into these types, already in local ENU. The core never
sees PX4 message types, NED, or PX4 mode numbers, so a different autopilot
only needs a different adapter.

Every report is stamped with the time it was *received* on the companion's
clock. Pairing depth images with poses by receive time avoids depending on
autopilot/companion time synchronisation; the residual error is the
transport jitter (milliseconds), which is small against the obstacle
clearance.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
import enum
import math
from typing import List, Optional, Tuple

import numpy as np

from swarm_sar.core.frames import heading_from_rotation, quat_normalized, quat_slerp
from swarm_sar.core.frames import quat_to_matrix
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.geometry import as_vec3, Vec3


class FlightMode(enum.Enum):
    """The flight-controller modes the core distinguishes."""

    OFFBOARD = 'offboard'  # the companion computer is in control
    HOLD = 'hold'          # the flight controller holds position on its own
    RETURN = 'return'      # return to launch
    LAND = 'land'
    OTHER = 'other'        # anything else (manual, position, mission, failsafe modes, ...)


@dataclass(frozen=True)
class VehicleStatusReport:
    """Arming state and active flight mode."""

    stamp: float
    armed: bool
    mode: FlightMode


@dataclass(frozen=True)
class LocalPositionReport:
    """The estimator's local position, already converted to local ENU."""

    stamp: float
    position: Vec3
    velocity: Vec3
    xy_valid: bool
    z_valid: bool
    v_xy_valid: bool
    heading_valid: bool
    dead_reckoning: bool
    global_reference: Optional[GeoPoint]
    reset_marker: Tuple[int, ...]  # changes whenever the local frame jumps or is re-anchored

    def __post_init__(self) -> None:
        object.__setattr__(self, 'position', as_vec3(self.position, 'position'))
        object.__setattr__(self, 'velocity', as_vec3(self.velocity, 'velocity'))
        if not math.isfinite(self.stamp):
            raise ValueError('stamp must be finite')

    @property
    def usable(self) -> bool:
        """Return True if position, velocity and heading can be used for control."""
        return (self.xy_valid and self.z_valid and self.v_xy_valid and self.heading_valid
                and not self.dead_reckoning)


@dataclass(frozen=True)
class AttitudeReport:
    """The vehicle attitude as an FRD-to-ENU quaternion ``(w, x, y, z)``."""

    stamp: float
    quaternion: np.ndarray
    reset_counter: int

    def __post_init__(self) -> None:
        q = quat_normalized(self.quaternion, 'attitude')
        q.setflags(write=False)
        object.__setattr__(self, 'quaternion', q)
        if not math.isfinite(self.stamp):
            raise ValueError('stamp must be finite')


@dataclass(frozen=True)
class PoseSample:
    """Position, velocity and attitude at one instant, in local ENU."""

    stamp: float
    position: Vec3
    velocity: Vec3
    quaternion: np.ndarray
    rotation: np.ndarray = field(init=False, repr=False)
    heading: float = field(init=False)

    def __post_init__(self) -> None:
        q = np.array(self.quaternion, dtype=np.float64)
        q.setflags(write=False)
        rotation = quat_to_matrix(q)
        rotation.setflags(write=False)
        object.__setattr__(self, 'quaternion', q)
        object.__setattr__(self, 'rotation', rotation)
        object.__setattr__(self, 'heading', heading_from_rotation(rotation))


class PoseHistory:
    """A short, time-ordered buffer of pose samples with interpolation."""

    def __init__(self, horizon: float) -> None:
        if not math.isfinite(horizon) or horizon <= 0:
            raise ValueError(f'horizon must be positive, got {horizon!r}')
        self._horizon = float(horizon)
        self._stamps: List[float] = []
        self._samples: List[PoseSample] = []

    def __len__(self) -> int:
        return len(self._samples)

    @property
    def latest(self) -> Optional[PoseSample]:
        """Return the newest sample, if any."""
        return self._samples[-1] if self._samples else None

    def clear(self) -> None:
        """Forget every sample (after a local-frame reset the old ones are wrong)."""
        self._stamps.clear()
        self._samples.clear()

    def shift_time(self, delta: float) -> None:
        """Move every sample by ``delta`` seconds (the companion clock was stepped)."""
        self._samples = [PoseSample(s.stamp + delta, s.position, s.velocity, s.quaternion)
                         for s in self._samples]
        self._stamps = [s.stamp for s in self._samples]

    def append(self, sample: PoseSample) -> bool:
        """Add ``sample``; out-of-order samples are dropped (returns False)."""
        if self._stamps and sample.stamp <= self._stamps[-1]:
            return False
        self._stamps.append(sample.stamp)
        self._samples.append(sample)
        cutoff = sample.stamp - self._horizon
        drop = bisect.bisect_left(self._stamps, cutoff)
        if drop:
            del self._stamps[:drop]
            del self._samples[:drop]
        return True

    def at(self, t: float, tolerance: float) -> Optional[PoseSample]:
        """
        Return the pose at time ``t``, interpolated between the bracketing samples.

        Requests newer than the latest sample are answered with the latest
        sample only if it is at most ``tolerance`` old; requests older than
        the buffer return None rather than a wrong pose.
        """
        if not self._samples or not math.isfinite(t):
            return None
        if t >= self._stamps[-1]:
            return self._samples[-1] if t - self._stamps[-1] <= tolerance else None
        if t < self._stamps[0]:
            return None
        i = bisect.bisect_right(self._stamps, t)
        before, after = self._samples[i - 1], self._samples[i]
        span = after.stamp - before.stamp
        w = (t - before.stamp) / span if span > 0 else 0.0
        position = tuple(a + w * (b - a) for a, b in zip(before.position, after.position))
        velocity = tuple(a + w * (b - a) for a, b in zip(before.velocity, after.velocity))
        quaternion = quat_slerp(before.quaternion, after.quaternion, w)
        return PoseSample(t, position, velocity, quaternion)  # type: ignore[arg-type]
