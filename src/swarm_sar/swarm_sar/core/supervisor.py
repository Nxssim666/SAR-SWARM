"""
Safety supervisor: input health, what the drone may do, and when to hand over to the autopilot.

The supervisor turns the freshness and validity of every input into a
fault set and a health level:

* **CRITICAL** (pose or flight-controller link unusable): the companion
  cannot compute a meaningful setpoint, so it stops sending them. PX4 then
  leaves offboard on its own (offboard-loss failsafe) and, while the link
  still works, the companion also asks for Hold explicitly.
* **DEGRADED** (e.g. depth stale, camera blind, outside the geofence, no
  peer heard any more): the companion holds position; after
  ``degraded_escalation_time`` it hands the vehicle to the flight
  controller's Hold mode, so a companion that cannot see (or cannot
  deconflict with other drones) never keeps authority indefinitely.

The companion only ever asks for a mode change while it is itself in
control (offboard). If the pilot or the autopilot has taken over, their
decision stands.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
import math
from typing import Optional, Tuple

from swarm_sar.core.config import DroneConfig
from swarm_sar.core.messages import HealthLevel


class Fault(enum.IntFlag):
    """Conditions reported in ``DroneStatus.faults`` (stable bit positions: wire format)."""

    NONE = 0
    FC_LINK = 1 << 0               # no vehicle status from the flight controller
    POSE_STALE = 1 << 1            # no local position recently
    POSE_INVALID = 1 << 2          # estimator reports position/velocity/heading unusable
    ATTITUDE_STALE = 1 << 3        # no attitude recently
    NO_GLOBAL_REFERENCE = 1 << 4   # local frame not anchored to WGS84: mission unusable
    DEPTH_STALE = 1 << 5           # no processed depth frame recently (or no camera info)
    DEPTH_BLIND = 1 << 6           # depth frames arrive but hold almost no returns
    OUTSIDE_GEOFENCE = 1 << 7
    ALTITUDE_MISMATCH = 1 << 8     # too far from the mission altitude to correct unobserved
    WAYPOINT_UNREACHABLE = 1 << 9  # transit waypoint could not be reached; waiting for operator
    MISSION_REJECTED = 1 << 10     # the latest mission could not be accepted (informational)
    CONTROL_OVERRUN = 1 << 11      # a control tick took longer than its period (informational)
    RADIO_SILENT = 1 << 12         # peers were heard, now none are: the own radio may be down


CRITICAL_FAULTS = Fault.FC_LINK | Fault.POSE_STALE | Fault.POSE_INVALID | Fault.ATTITUDE_STALE
MOTION_BLOCKING_FAULTS = (Fault.DEPTH_STALE | Fault.DEPTH_BLIND | Fault.NO_GLOBAL_REFERENCE
                          | Fault.OUTSIDE_GEOFENCE | Fault.ALTITUDE_MISMATCH
                          | Fault.RADIO_SILENT)
# Healthy vehicle, but the operator must act; the mission logic holds (no escalation).
ATTENTION_FAULTS = Fault.WAYPOINT_UNREACHABLE
# Per-tick conditions: reported in every status, but a change is not worth a log line.
TRANSIENT_FAULTS = Fault.CONTROL_OVERRUN


def lasting_faults(faults: int) -> Fault:
    """Return ``faults`` without the transient bits (what alerts and logs compare)."""
    return Fault(int(faults) & ~int(TRANSIENT_FAULTS))


class FcRequest(enum.Enum):
    """Flight-mode changes the companion can ask the flight controller for."""

    HOLD = 'hold'
    RETURN = 'return'
    LAND = 'land'


@dataclass(frozen=True)
class HealthReport:
    """Fault set and what it allows."""

    level: HealthLevel
    faults: Fault

    @property
    def can_control(self) -> bool:
        """Return True if setpoints may be sent at all."""
        return not self.faults & CRITICAL_FAULTS

    @property
    def can_move(self) -> bool:
        """Return True if the vehicle may translate horizontally."""
        return self.can_control and not self.faults & MOTION_BLOCKING_FAULTS


@dataclass(frozen=True)
class SupervisorInputs:
    """Everything the supervisor judges, sampled once per control tick."""

    status_age: float
    pose_age: float
    pose_usable: bool
    attitude_age: float
    depth_age: float
    depth_valid_fraction: Optional[float]
    global_reference: bool
    outside_geofence: bool
    altitude_mismatch: bool
    waypoint_unreachable: bool
    mission_rejected: bool
    overrun: bool
    radio_silent: bool = False


class Supervisor:
    """Stateful health evaluation with a timed escalation to the flight controller."""

    def __init__(self, config: DroneConfig) -> None:
        self._cfg = config
        self._unable_since: Optional[float] = None

    def reset(self) -> None:
        """Forget escalation timing (e.g. after the vehicle leaves offboard)."""
        self._unable_since = None

    def shift_time(self, delta: float) -> None:
        """Move the escalation timer by ``delta`` seconds (the companion clock was stepped)."""
        if self._unable_since is not None:
            self._unable_since += delta

    def update(self, now: float, inputs: SupervisorInputs,
               engaged: bool) -> Tuple[HealthReport, Optional[FcRequest]]:
        """Return the health report and, if due, a request to hand over to Hold."""
        report = assess(self._cfg, inputs)
        if not engaged:
            self._unable_since = None
            return report, None
        if not report.can_control:
            self._unable_since = None
            return report, FcRequest.HOLD
        if report.can_move:
            self._unable_since = None
            return report, None
        if self._unable_since is None:
            self._unable_since = now
        if now - self._unable_since >= self._cfg.degraded_escalation_time:
            return report, FcRequest.HOLD
        return report, None


def assess(config: DroneConfig, inputs: SupervisorInputs) -> HealthReport:
    """Return the fault set and health level for ``inputs`` (pure function)."""
    faults = Fault.NONE
    if not inputs.status_age <= config.fc_timeout:
        faults |= Fault.FC_LINK
    if not inputs.pose_age <= config.pose_timeout:
        faults |= Fault.POSE_STALE
    elif not inputs.pose_usable:
        faults |= Fault.POSE_INVALID
    if not inputs.attitude_age <= config.pose_timeout:
        faults |= Fault.ATTITUDE_STALE
    if not inputs.global_reference:
        faults |= Fault.NO_GLOBAL_REFERENCE
    if not inputs.depth_age <= config.depth_timeout:
        faults |= Fault.DEPTH_STALE
    elif (inputs.depth_valid_fraction is not None
          and inputs.depth_valid_fraction < config.min_valid_depth_fraction):
        faults |= Fault.DEPTH_BLIND
    if inputs.outside_geofence:
        faults |= Fault.OUTSIDE_GEOFENCE
    if inputs.altitude_mismatch:
        faults |= Fault.ALTITUDE_MISMATCH
    if inputs.waypoint_unreachable:
        faults |= Fault.WAYPOINT_UNREACHABLE
    if inputs.mission_rejected:
        faults |= Fault.MISSION_REJECTED
    if inputs.overrun:
        faults |= Fault.CONTROL_OVERRUN
    if inputs.radio_silent:
        faults |= Fault.RADIO_SILENT
    if faults & CRITICAL_FAULTS:
        level = HealthLevel.CRITICAL
    elif faults & (MOTION_BLOCKING_FAULTS | ATTENTION_FAULTS):
        level = HealthLevel.DEGRADED
    else:
        level = HealthLevel.OK
    return HealthReport(level, faults)


def age(now: float, last: Optional[float]) -> float:
    """Return how long ago ``last`` was, or infinity if it never happened."""
    return math.inf if last is None else max(now - last, 0.0)
