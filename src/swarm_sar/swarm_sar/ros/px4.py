"""
PX4 adapter: ``px4_msgs`` (uXRCE-DDS) to and from the core's autopilot-agnostic types.

This is the only module that knows PX4 message fields, NED, PX4 mode numbers
and PX4's offboard protocol. Supporting another autopilot means writing a
sibling of this module; nothing in ``swarm_sar.core`` changes.

Offboard protocol (PX4 v1.14/v1.15):

* ``OffboardControlMode`` must stream at more than 2 Hz for the vehicle to
  enter and stay in offboard; it is published with every setpoint.
* ``TrajectorySetpoint`` per-axis NaN means "not controlled". Velocity
  control holds altitude with a position setpoint on z and flies x/y by
  velocity; holding uses position on all axes.
* When the companion sends nothing, PX4's offboard-loss failsafe
  (``COM_OF_LOSS_T``, ``COM_OBL_RC_ACT``) takes over; that is intentional.

The message definitions this code was written against were checked field by
field against ``PX4/px4_msgs`` branch ``release/1.15``. ``px4_msgs`` must
match the flight controller's firmware version exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence

import numpy as np
from swarm_sar.core.controller import Setpoint, SetpointKind
from swarm_sar.core.frames import enu_to_ned, heading_to_px4_yaw, ned_to_enu, px4_attitude_to_enu
from swarm_sar.core.geodesy import GeoPoint
from swarm_sar.core.pose import (AttitudeReport, FlightMode, LocalPositionReport,
                                 VehicleStatusReport)
from swarm_sar.core.supervisor import FcRequest
from swarm_sar.ros.codec import MessageValidationError

ARMING_STATE_ARMED = 2
NAV_STATE_AUTO_LOITER = 4
NAV_STATE_AUTO_RTL = 5
NAV_STATE_OFFBOARD = 14
NAV_STATE_AUTO_LAND = 18
_NAV_STATE_MODES = {NAV_STATE_OFFBOARD: FlightMode.OFFBOARD,
                    NAV_STATE_AUTO_LOITER: FlightMode.HOLD,
                    NAV_STATE_AUTO_RTL: FlightMode.RETURN,
                    NAV_STATE_AUTO_LAND: FlightMode.LAND}

VEHICLE_CMD_NAV_RETURN_TO_LAUNCH = 20
VEHICLE_CMD_NAV_LAND = 21
VEHICLE_CMD_DO_SET_MODE = 176
MODE_FLAG_CUSTOM_MODE_ENABLED = 1.0
PX4_CUSTOM_MAIN_MODE_AUTO = 4.0
PX4_CUSTOM_SUB_MODE_AUTO_LOITER = 3.0
COMPANION_COMPONENT_ID = 191  # MAV_COMP_ID_ONBOARD_COMPUTER
_NAN3 = (math.nan, math.nan, math.nan)


@dataclass(frozen=True)
class Px4Types:
    """The ``px4_msgs`` classes the adapter uses (injected for testability)."""

    VehicleLocalPosition: Any
    VehicleAttitude: Any
    VehicleStatus: Any
    OffboardControlMode: Any
    TrajectorySetpoint: Any
    VehicleCommand: Any

    @classmethod
    def load(cls) -> 'Px4Types':
        """Import the real classes (requires px4_msgs in the sourced workspace)."""
        from px4_msgs.msg import (OffboardControlMode, TrajectorySetpoint, VehicleAttitude,
                                  VehicleCommand, VehicleLocalPosition, VehicleStatus)
        return cls(VehicleLocalPosition, VehicleAttitude, VehicleStatus, OffboardControlMode,
                   TrajectorySetpoint, VehicleCommand)


def microseconds(seconds: float) -> int:
    """Return a PX4 timestamp (microseconds) for ``seconds`` on the node clock."""
    return int(round(seconds * 1e6))


def _finite(values: Sequence[float]) -> bool:
    return all(math.isfinite(float(v)) for v in values)


def decode_local_position(msg: Any, received_at: float) -> LocalPositionReport:
    """Convert ``VehicleLocalPosition`` (NED) into a local-ENU report stamped at receipt."""
    try:
        position_ned = (float(msg.x), float(msg.y), float(msg.z))
        velocity_ned = (float(msg.vx), float(msg.vy), float(msg.vz))
        position_ok = _finite(position_ned)
        velocity_ok = _finite(velocity_ned)
        reference = None
        if msg.xy_global and math.isfinite(msg.ref_lat) and math.isfinite(msg.ref_lon):
            try:
                reference = GeoPoint(float(msg.ref_lat), float(msg.ref_lon))
            except ValueError:
                reference = None
        return LocalPositionReport(
            stamp=received_at,
            position=ned_to_enu(position_ned) if position_ok else (0.0, 0.0, 0.0),
            velocity=ned_to_enu(velocity_ned) if velocity_ok else (0.0, 0.0, 0.0),
            xy_valid=bool(msg.xy_valid) and position_ok,
            z_valid=bool(msg.z_valid) and position_ok,
            v_xy_valid=bool(msg.v_xy_valid) and velocity_ok,
            heading_valid=bool(msg.heading_good_for_control),
            dead_reckoning=bool(msg.dead_reckoning),
            global_reference=reference,
            # Any estimator reset, or a new reference point, re-anchors the local frame.
            reset_marker=(int(msg.xy_reset_counter), int(msg.z_reset_counter),
                          int(msg.heading_reset_counter), int(msg.ref_timestamp)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise MessageValidationError(f'invalid VehicleLocalPosition: {exc}') from exc


def decode_attitude(msg: Any, received_at: float) -> AttitudeReport:
    """Convert ``VehicleAttitude`` (FRD to NED) into an FRD-to-ENU attitude report."""
    try:
        return AttitudeReport(received_at, px4_attitude_to_enu(list(msg.q)),
                              int(msg.quat_reset_counter))
    except (ValueError, TypeError, AttributeError) as exc:
        raise MessageValidationError(f'invalid VehicleAttitude: {exc}') from exc


def decode_vehicle_status(msg: Any, received_at: float) -> VehicleStatusReport:
    """Convert ``VehicleStatus`` into arming state and flight mode."""
    try:
        armed = int(msg.arming_state) == ARMING_STATE_ARMED
        mode = _NAV_STATE_MODES.get(int(msg.nav_state), FlightMode.OTHER)
        return VehicleStatusReport(received_at, armed, mode)
    except (ValueError, TypeError, AttributeError) as exc:
        raise MessageValidationError(f'invalid VehicleStatus: {exc}') from exc


def encode_offboard_mode(types: Px4Types, now: float) -> Any:
    """Build the offboard heartbeat: position (altitude, holds) and velocity control."""
    msg = types.OffboardControlMode()
    msg.timestamp = microseconds(now)
    msg.position = True
    msg.velocity = True
    msg.acceleration = False
    msg.attitude = False
    msg.body_rate = False
    msg.thrust_and_torque = False
    msg.direct_actuator = False
    return msg


def encode_trajectory_setpoint(types: Px4Types, setpoint: Setpoint, now: float) -> Any:
    """Build a ``TrajectorySetpoint`` (NED) from a local-ENU setpoint."""
    msg = types.TrajectorySetpoint()
    msg.timestamp = microseconds(now)
    north, east, down = enu_to_ned(setpoint.position)
    if setpoint.kind is SetpointKind.POSITION:
        position = (north, east, down)
        velocity = _NAN3
    else:
        position = (math.nan, math.nan, down)
        velocity = (float(setpoint.velocity[1]), float(setpoint.velocity[0]), math.nan)
    msg.position = np.array(position, dtype=np.float32)
    msg.velocity = np.array(velocity, dtype=np.float32)
    msg.acceleration = np.array(_NAN3, dtype=np.float32)
    msg.jerk = np.array(_NAN3, dtype=np.float32)
    msg.yaw = float(heading_to_px4_yaw(setpoint.heading))
    msg.yawspeed = math.nan
    return msg


def encode_vehicle_command(types: Px4Types, request: FcRequest, target_system: int,
                           now: float) -> Any:
    """Build the ``VehicleCommand`` that asks PX4 for Hold, RTL or Land."""
    msg = types.VehicleCommand()
    msg.timestamp = microseconds(now)
    if request is FcRequest.HOLD:
        msg.command = VEHICLE_CMD_DO_SET_MODE
        msg.param1 = MODE_FLAG_CUSTOM_MODE_ENABLED
        msg.param2 = PX4_CUSTOM_MAIN_MODE_AUTO
        msg.param3 = PX4_CUSTOM_SUB_MODE_AUTO_LOITER
    elif request is FcRequest.RETURN:
        msg.command = VEHICLE_CMD_NAV_RETURN_TO_LAUNCH
    else:
        msg.command = VEHICLE_CMD_NAV_LAND
        msg.param5 = math.nan  # latitude, longitude, altitude: NaN = land where you are
        msg.param6 = math.nan
        msg.param7 = math.nan
    msg.target_system = int(target_system)
    msg.target_component = 1
    msg.source_system = int(target_system)
    msg.source_component = COMPANION_COMPONENT_ID
    msg.confirmation = 0
    msg.from_external = True
    return msg
