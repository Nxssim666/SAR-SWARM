"""
A multicopter and a PX4-like autopilot, reduced to what the companion software interacts with.

``SimVehicle`` is an acceleration-limited point mass with rate-limited yaw
and first-order altitude control. ``SimAutopilot`` wraps it with the
behaviour the companion depends on:

* flight modes (offboard, hold, return, land, and "other" for manual flight),
* the offboard-loss failsafe (no setpoint for ``OFFBOARD_TIMEOUT`` -> hold),
* reports in the companion's terms: local ENU relative to where the
  estimator started, a global reference for that origin, level attitude,
  arming state and mode.

Return-to-launch climbs to ``RTL_ALTITUDE`` first, like PX4, because it
flies straight home without obstacle avoidance.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from swarm_sar.core.controller import Setpoint, SetpointKind
from swarm_sar.core.frames import level_attitude
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.geometry import saturate, Vec2, Vec3, wrap_angle
from swarm_sar.core.pose import (AttitudeReport, FlightMode, LocalPositionReport,
                                 VehicleStatusReport)
from swarm_sar.core.supervisor import FcRequest

OFFBOARD_TIMEOUT = 1.0     # PX4 COM_OF_LOSS_T default
RTL_ALTITUDE = 20.0
LAND_SPEED = 0.7
POSITION_GAIN = 1.0
POSITION_SPEED_LIMIT = 3.0
ALTITUDE_GAIN = 1.5
_SUBSTEPS = 2


class SimVehicle:
    """Point-mass multicopter in world ENU."""

    def __init__(self, position: Vec3, heading: float, max_accel: float, yaw_rate: float,
                 climb_rate: float) -> None:
        for name, value in (('max_accel', max_accel), ('yaw_rate', yaw_rate),
                            ('climb_rate', climb_rate)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be positive, got {value!r}')
        self.position = np.array(position, dtype=np.float64)
        self.velocity = np.zeros(3)
        self.heading = float(heading)
        self._max_accel = float(max_accel)
        self._yaw_rate = float(yaw_rate)
        self._climb_rate = float(climb_rate)

    def step(self, velocity_xy: Vec2, target_z: float, heading: float, dt: float) -> None:
        """Track a horizontal velocity, an altitude and a heading for ``dt`` seconds."""
        if not math.isfinite(dt) or dt < 0:
            raise ValueError(f'dt must be non-negative, got {dt!r}')
        h = dt / _SUBSTEPS
        for _ in range(_SUBSTEPS):
            dvx, dvy = saturate((velocity_xy[0] - self.velocity[0],
                                 velocity_xy[1] - self.velocity[1]), self._max_accel * h)
            self.velocity[0] += dvx
            self.velocity[1] += dvy
            vz = min(max(ALTITUDE_GAIN * (target_z - self.position[2]), -self._climb_rate),
                     self._climb_rate)
            self.velocity[2] = vz
            self.position += self.velocity * h
            error = wrap_angle(heading - self.heading)
            turn = min(max(error, -self._yaw_rate * h), self._yaw_rate * h)
            self.heading = wrap_angle(self.heading + turn)
        if self.position[2] < 0.0:
            self.position[2] = 0.0
            self.velocity[:] = 0.0


class SimAutopilot:
    """Flight modes, failsafes and reports around a ``SimVehicle``."""

    def __init__(self, vehicle: SimVehicle, origin_world: Vec3, origin_geo: GeoPoint,
                 armed: bool = True, mode: FlightMode = FlightMode.OFFBOARD) -> None:
        self.vehicle = vehicle
        self._origin = np.array(origin_world, dtype=np.float64)
        self._origin_geo = origin_geo
        self.armed = armed
        self.mode = mode
        self._setpoint: Optional[Setpoint] = None
        self._setpoint_time = -math.inf
        self._hold = self.vehicle.position.copy()
        self._hold_heading = self.vehicle.heading
        self.failsafes = 0
        self.link_up = True

    @property
    def home(self) -> np.ndarray:
        """Return the world position of the estimator origin (on the ground)."""
        return self._origin

    def engage(self, mode: FlightMode) -> None:
        """Switch mode as the pilot would (e.g. into offboard)."""
        self._enter(mode)

    def offer_setpoint(self, setpoint: Setpoint, now: float) -> None:
        """Receive a setpoint from the companion (ignored unless the link is up)."""
        if not self.link_up:
            return
        self._setpoint = setpoint
        self._setpoint_time = now

    def request(self, request: FcRequest) -> None:
        """Handle a mode request from the companion."""
        if not self.link_up or not self.armed:
            return
        self._enter({FcRequest.HOLD: FlightMode.HOLD, FcRequest.RETURN: FlightMode.RETURN,
                     FcRequest.LAND: FlightMode.LAND}[request])

    def _enter(self, mode: FlightMode) -> None:
        self.mode = mode
        self._hold = self.vehicle.position.copy()
        self._hold_heading = self.vehicle.heading

    def step(self, now: float, dt: float) -> None:
        """Advance the vehicle by ``dt`` under the active mode."""
        v = self.vehicle
        if not self.armed:
            v.step((0.0, 0.0), 0.0, v.heading, dt)
            return
        if self.mode is FlightMode.OFFBOARD and now - self._setpoint_time > OFFBOARD_TIMEOUT:
            self.failsafes += 1
            self._enter(FlightMode.HOLD)
        if self.mode is FlightMode.OFFBOARD and self._setpoint is not None:
            sp = self._setpoint
            if sp.kind is SetpointKind.VELOCITY:
                v.step(sp.velocity, sp.position[2] + self._origin[2], sp.heading, dt)
            else:
                self._fly_to(np.array(sp.position) + self._origin, sp.heading, dt)
        elif self.mode is FlightMode.RETURN:
            target = np.array([self._origin[0], self._origin[1], RTL_ALTITUDE])
            if v.position[2] < RTL_ALTITUDE - 0.5:
                target[:2] = self._hold[:2]
            elif math.hypot(*(v.position[:2] - self._origin[:2])) < 1.0:
                self._enter(FlightMode.LAND)
                return
            self._fly_to(target, v.heading, dt)
        elif self.mode is FlightMode.LAND:
            v.step((0.0, 0.0), max(v.position[2] - LAND_SPEED / ALTITUDE_GAIN, 0.0), v.heading,
                   dt)
            if v.position[2] <= 0.05:
                self.armed = False
        else:  # HOLD, OTHER: the pilot/autopilot holds position
            self._fly_to(self._hold, self._hold_heading, dt)

    def _fly_to(self, target: np.ndarray, heading: float, dt: float) -> None:
        v = self.vehicle
        pull = saturate((POSITION_GAIN * (target[0] - v.position[0]),
                         POSITION_GAIN * (target[1] - v.position[1])), POSITION_SPEED_LIMIT)
        v.step(pull, float(target[2]), heading, dt)

    # -- reports in the companion's terms ------------------------------------------
    def local_position(self, now: float) -> LocalPositionReport:
        """Return the local-position report (ENU relative to the estimator origin)."""
        v = self.vehicle
        return LocalPositionReport(
            stamp=now, position=tuple(v.position - self._origin),  # type: ignore[arg-type]
            velocity=tuple(v.velocity),  # type: ignore[arg-type]
            xy_valid=True, z_valid=True, v_xy_valid=True, heading_valid=True,
            dead_reckoning=False, global_reference=self._origin_geo, reset_marker=(0, 0, 0))

    def attitude(self, now: float) -> AttitudeReport:
        """Return the attitude report (the model flies level)."""
        return AttitudeReport(now, level_attitude(self.vehicle.heading), 0)

    def status(self, now: float) -> VehicleStatusReport:
        """Return arming state and mode."""
        return VehicleStatusReport(now, self.armed, self.mode)
