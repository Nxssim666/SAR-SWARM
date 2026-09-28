"""
Target estimation: a constant-velocity Kalman filter plus covariance intersection.

Each drone runs its own filter. Own detections are folded in with ordinary
Kalman updates (sensor noise is independent of everything else, so that is
exact). Estimates heard from peers are fused with covariance intersection
(CI), which stays consistent for *unknown* cross-correlation. That matters
here because gossip echoes information around the network: naive averaging
or Kalman-fusing a peer's estimate that already contains my own earlier
estimate would count the same measurement twice and make every drone
overconfident. CI of an estimate with itself returns it unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

import numpy as np

from swarm_sar.core.geometry import as_vec2, Vec2

_MIN_STD = 1e-3
_H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
_H.setflags(write=False)
_I4 = np.eye(4)
_I4.setflags(write=False)
_STAMP_TOLERANCE = 1e-6


def _checked_covariance(matrix: np.ndarray, size: int, name: str) -> np.ndarray:
    cov = np.array(matrix, dtype=np.float64)
    if cov.size != size * size:
        raise ValueError(f'{name} must have {size * size} elements, got shape {cov.shape}')
    cov = cov.reshape(size, size)
    if not np.all(np.isfinite(cov)):
        raise ValueError(f'{name} must be finite')
    asymmetry = float(np.max(np.abs(cov - cov.T)))
    if asymmetry > 1e-9 + 1e-6 * float(np.max(np.abs(cov))):
        raise ValueError(f'{name} must be symmetric')
    cov = 0.5 * (cov + cov.T)
    try:
        np.linalg.cholesky(cov)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f'{name} must be positive definite') from exc
    cov.setflags(write=False)
    return cov


def _finite_time(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'{name} must be finite, got {value!r}')
    return result


@dataclass(frozen=True, eq=False)
class Detection:
    """One position measurement of the target with its noise covariance (m^2)."""

    stamp: float
    position: Vec2
    covariance: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, 'stamp', _finite_time(self.stamp, 'detection stamp'))
        object.__setattr__(self, 'position', as_vec2(self.position, 'detection position'))
        object.__setattr__(self, 'covariance',
                           _checked_covariance(self.covariance, 2, 'detection covariance'))

    @classmethod
    def isotropic(cls, stamp: float, position: Vec2, std: float) -> 'Detection':
        """Build a detection with independent, equal noise on x and y."""
        sigma = max(float(std), _MIN_STD)
        return cls(stamp, position, np.eye(2) * sigma * sigma)


@dataclass(frozen=True, eq=False)
class TargetEstimate:
    """Target state ``[x, y, vx, vy]`` and covariance, valid at ``stamp``."""

    state: np.ndarray
    covariance: np.ndarray
    stamp: float
    last_measurement_time: float

    def __post_init__(self) -> None:
        state = np.array(self.state, dtype=np.float64)
        if state.size != 4:
            raise ValueError(f'estimate state must have 4 elements, got shape {state.shape}')
        state = state.reshape(4)
        if not np.all(np.isfinite(state)):
            raise ValueError('estimate state must be finite')
        state.setflags(write=False)
        stamp = _finite_time(self.stamp, 'estimate stamp')
        measured = _finite_time(self.last_measurement_time, 'estimate last_measurement_time')
        if measured > stamp + _STAMP_TOLERANCE:
            raise ValueError('estimate cannot contain a measurement newer than its own stamp')
        object.__setattr__(self, 'state', state)
        object.__setattr__(self, 'covariance',
                           _checked_covariance(self.covariance, 4, 'estimate covariance'))
        object.__setattr__(self, 'stamp', stamp)
        object.__setattr__(self, 'last_measurement_time', measured)

    @classmethod
    def _computed(cls, state: np.ndarray, covariance: np.ndarray, stamp: float,
                  last_measurement_time: float) -> 'TargetEstimate':
        """
        Build from values this module computed itself, skipping the costly PD check.

        Anything arriving from outside (peers, ROS messages) goes through the
        normal constructor, which validates every field.
        """
        state = np.array(state, dtype=np.float64).reshape(4)
        cov = np.array(covariance, dtype=np.float64).reshape(4, 4)
        cov = 0.5 * (cov + cov.T)
        if not (np.all(np.isfinite(state)) and np.all(np.isfinite(cov))):
            raise FloatingPointError('target estimate became non-finite')
        state.setflags(write=False)
        cov.setflags(write=False)
        estimate = object.__new__(cls)
        object.__setattr__(estimate, 'state', state)
        object.__setattr__(estimate, 'covariance', cov)
        object.__setattr__(estimate, 'stamp', float(stamp))
        object.__setattr__(estimate, 'last_measurement_time', float(last_measurement_time))
        return estimate

    @property
    def position(self) -> Vec2:
        """Return the estimated position."""
        return (float(self.state[0]), float(self.state[1]))

    @property
    def velocity(self) -> Vec2:
        """Return the estimated velocity."""
        return (float(self.state[2]), float(self.state[3]))

    @property
    def position_covariance(self) -> np.ndarray:
        """Return the 2x2 position block of the covariance."""
        return self.covariance[:2, :2]

    @property
    def position_std(self) -> float:
        """Return the 1-sigma position uncertainty along its worst axis."""
        return math.sqrt(max(float(np.linalg.eigvalsh(self.position_covariance)[-1]), 0.0))

    def with_last_measurement_time(self, measured: float) -> 'TargetEstimate':
        """Return a copy with ``last_measurement_time`` replaced."""
        if measured == self.last_measurement_time:
            return self
        if measured > self.stamp + _STAMP_TOLERANCE:
            raise ValueError('estimate cannot contain a measurement newer than its own stamp')
        return TargetEstimate._computed(self.state, self.covariance, self.stamp, measured)


class ConstantVelocityTracker:
    """Constant-velocity Kalman filter with white-noise acceleration."""

    def __init__(self, accel_psd: float, max_speed: float) -> None:
        if not math.isfinite(accel_psd) or accel_psd <= 0:
            raise ValueError(f'accel_psd must be positive, got {accel_psd!r}')
        if not math.isfinite(max_speed) or max_speed <= 0:
            raise ValueError(f'max_speed must be positive, got {max_speed!r}')
        self._q = float(accel_psd)
        self._max_speed = float(max_speed)

    def initialize(self, detection: Detection) -> TargetEstimate:
        """Start a track at a detection with unknown velocity (1-sigma = max speed)."""
        cov = np.zeros((4, 4))
        cov[:2, :2] = detection.covariance
        cov[2, 2] = cov[3, 3] = self._max_speed ** 2
        state = [detection.position[0], detection.position[1], 0.0, 0.0]
        return TargetEstimate._computed(np.array(state), cov, detection.stamp, detection.stamp)

    def predict(self, estimate: TargetEstimate, t: float) -> TargetEstimate:
        """Propagate ``estimate`` to time ``t``; never predicts backwards."""
        dt = t - estimate.stamp
        if dt <= 0.0:
            return estimate
        f = np.eye(4)
        f[0, 2] = f[1, 3] = dt
        dt2, dt3 = dt * dt, dt * dt * dt
        q = self._q * np.array([[dt3 / 3.0, 0.0, dt2 / 2.0, 0.0],
                                [0.0, dt3 / 3.0, 0.0, dt2 / 2.0],
                                [dt2 / 2.0, 0.0, dt, 0.0],
                                [0.0, dt2 / 2.0, 0.0, dt]])
        state = f @ estimate.state
        cov = f @ estimate.covariance @ f.T + q
        return TargetEstimate._computed(state, cov, t, estimate.last_measurement_time)

    def align(self, estimate: TargetEstimate, t: float) -> TargetEstimate:
        """
        Bring ``estimate`` to time ``t``.

        Forward in time this is an ordinary prediction. An estimate stamped
        *after* ``t`` (a peer or sensor whose clock runs slightly fast, within
        the tolerated skew) is re-stamped to ``t`` with its position
        uncertainty inflated by how far the target could move in the gap, so
        it stays usable and consistent instead of being dropped.
        """
        if t >= estimate.stamp:
            return self.predict(estimate, t)
        lag = estimate.stamp - t
        cov = np.array(estimate.covariance)
        cov[:2, :2] += np.eye(2) * (self._max_speed * lag) ** 2
        return TargetEstimate._computed(estimate.state, cov, t,
                                        min(estimate.last_measurement_time, t))

    def update(self, estimate: TargetEstimate, detection: Detection) -> TargetEstimate:
        """
        Fold one detection into ``estimate`` (Joseph-form update).

        A detection older than the estimate (out of sequence, e.g. delayed in
        transit) is applied at the estimate's time with its noise inflated
        by how far the target could have moved in the meantime, instead of
        rewinding the filter.
        """
        noise = detection.covariance
        if detection.stamp >= estimate.stamp:
            prior = self.predict(estimate, detection.stamp)
        else:
            prior = estimate
            lag = estimate.stamp - detection.stamp
            noise = noise + np.eye(2) * (self._max_speed * lag) ** 2
        cov = prior.covariance
        innovation_cov = cov[:2, :2] + noise
        gain = np.linalg.solve(innovation_cov, cov[:2, :]).T
        residual = np.asarray(detection.position) - prior.state[:2]
        state = prior.state + gain @ residual
        joseph = _I4 - gain @ _H
        cov = joseph @ cov @ joseph.T + gain @ noise @ gain.T
        measured = max(prior.last_measurement_time, min(detection.stamp, prior.stamp))
        return TargetEstimate._computed(state, cov, prior.stamp, measured)


def _dominates(better: np.ndarray, worse: np.ndarray) -> bool:
    """Return True if ``worse - better`` is positive semi-definite."""
    diff = worse - better
    scale = max(float(np.max(np.abs(worse))), 1e-12)
    return float(np.linalg.eigvalsh(0.5 * (diff + diff.T))[0]) >= -1e-9 * scale


def _golden_section_minimize(fn: Callable[[float], float], lo: float, hi: float,
                             iterations: int) -> float:
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - ratio * (b - a), a + ratio * (b - a)
    fc, fd = fn(c), fn(d)
    for _ in range(iterations):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = fn(c)
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = fn(d)
    candidates = [(fn(lo), lo), (fn(hi), hi), (fn((a + b) / 2.0), (a + b) / 2.0)]
    return min(candidates)[1]


def covariance_intersection(a: TargetEstimate, b: TargetEstimate,
                            iterations: int = 20) -> TargetEstimate:
    """
    Fuse two estimates of the same state with unknown cross-correlation.

    The weight is chosen to minimise the determinant of the fused
    covariance. When one covariance is uniformly tighter the result is that
    estimate unchanged (the CI optimum lies at the boundary), which is also
    the common, cheap case in a gossip network.
    """
    if abs(a.stamp - b.stamp) > _STAMP_TOLERANCE:
        raise ValueError('covariance_intersection needs estimates predicted to the same time')
    measured = max(a.last_measurement_time, b.last_measurement_time)
    if _dominates(a.covariance, b.covariance):
        return a.with_last_measurement_time(measured)
    if _dominates(b.covariance, a.covariance):
        return b.with_last_measurement_time(measured)
    try:
        info_a = np.linalg.inv(a.covariance)
        info_b = np.linalg.inv(b.covariance)
    except np.linalg.LinAlgError:
        best = a if np.linalg.det(a.covariance) <= np.linalg.det(b.covariance) else b
        return best.with_last_measurement_time(measured)

    def cost(w: float) -> float:
        sign, logdet = np.linalg.slogdet(w * info_a + (1.0 - w) * info_b)
        return -logdet if sign > 0 else math.inf

    w = _golden_section_minimize(cost, 0.0, 1.0, iterations)
    info = w * info_a + (1.0 - w) * info_b
    cov = np.linalg.inv(info)
    state = cov @ (w * info_a @ a.state + (1.0 - w) * info_b @ b.state)
    return TargetEstimate._computed(state, cov, a.stamp, measured)
