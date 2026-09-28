"""
A minimal PX4-like MAVLink vehicle for local tests of the MAVLink driver (ADR 0022).

It lets the real MAVSDK binding and the whole command pipeline run on any machine,
without PX4. It speaks just enough of PX4's dialect for what the driver uses: heartbeat
with PX4 custom modes, position, GNSS, battery, landed state and home; command acks;
parameter set. Its "flight" is teleport-grade kinematics. It is test-only on purpose:
flight behaviour is verified against PX4 SITL in CI (ADR 0023), not against this.

Each vehicle runs in its own thread with its own UDP socket, like a PX4 instance, and
sends to the ground station's port; several vehicles may share that port.
"""

import contextlib
import math
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

os.environ.setdefault("MAVLINK20", "1")

from pymavlink.dialects.v20 import common as mav  # MAVLINK20 must be set first

# PX4 custom modes (main mode, sub mode).
MODES = {
    "hold": (4, 3),  # AUTO.LOITER
    "takeoff": (4, 2),
    "mission": (4, 4),
    "return": (4, 5),
    "land": (4, 6),
    "ready": (4, 1),
    "position": (3, 0),
    "offboard": (6, 0),
}
FLIGHT_COMMANDS = {
    mav.MAV_CMD_COMPONENT_ARM_DISARM,
    mav.MAV_CMD_NAV_TAKEOFF,
    mav.MAV_CMD_NAV_LAND,
    mav.MAV_CMD_NAV_RETURN_TO_LAUNCH,
    mav.MAV_CMD_DO_SET_MODE,
    mav.MAV_CMD_DO_REPOSITION,
}
EARTH_RADIUS_M = 6_371_000.0
SPEED_MPS = 15.0
CLIMB_MPS = 5.0


@dataclass
class VehicleState:
    """What the vehicle is doing; read and changed by tests only between steps."""

    latitude: float
    longitude: float
    home_amsl_m: float = 488.0
    altitude_relative_m: float = 0.0
    armed: bool = False
    in_air: bool = False
    mode: str = "hold"
    battery_pct: int = 90
    gps_ok: bool = True
    target: tuple[float, float, float] | None = None  # latitude, longitude, relative altitude
    params: dict[str, float] = field(default_factory=lambda: {"MIS_TAKEOFF_ALT": 2.5})


class _Sender:
    """The file-like target pymavlink's codec writes encoded messages to."""

    def __init__(self, sock: socket.socket, destination: tuple[str, int]) -> None:
        self._socket = sock
        self._destination = destination

    def write(self, data: bytes) -> None:
        with contextlib.suppress(OSError):  # nobody listening yet: like a radio, send on
            self._socket.sendto(data, self._destination)


class MavlinkVehicle:
    """One simulated autopilot on its own thread and socket."""

    def __init__(
        self,
        gcs_port: int,
        system_id: int,
        latitude: float = 47.3977,
        longitude: float = 8.5456,
        *,
        deny: frozenset[int] = frozenset(),
        silent: bool = False,
    ) -> None:
        self.system_id = system_id
        self.state = VehicleState(latitude, longitude)
        self.home = (latitude, longitude)
        self.deny = deny  # MAV_CMD ids refused with MAV_RESULT_DENIED
        self.silent = silent  # never acknowledge flight commands
        self.received: list[int] = []  # MAV_CMD ids received, in order
        # A plain socket and pymavlink's codec: mavutil's "udpout" binds the destination
        # port on Windows, which breaks several vehicles sharing one ground station port.
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.setblocking(False)
        self._codec: Any = mav.MAVLink(_Sender(self._socket, ("127.0.0.1", gcs_port)), system_id, 1)
        self._codec.robust_parsing = True
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"vehicle-{system_id}", daemon=True)

    def __enter__(self) -> "MavlinkVehicle":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        self._socket.close()

    def update(self, **changes: Any) -> None:
        """Change the state (e.g. ``gps_ok=False``) between steps."""
        with self._lock:
            for name, value in changes.items():
                setattr(self.state, name, value)

    # --- the loop --------------------------------------------------------------------------

    def _run(self) -> None:
        next_step = next_heartbeat = time.monotonic()
        while not self._stop.is_set():
            for message in self._receive():
                with self._lock:
                    self._handle(message)
            now = time.monotonic()
            if now >= next_step:
                with self._lock:
                    self._step(0.1)
                    self._stream()
                next_step = now + 0.1
            if now >= next_heartbeat:
                with self._lock:
                    self._heartbeat()
                next_heartbeat = now + 1.0
            time.sleep(0.01)

    def _receive(self) -> list[Any]:
        messages: list[Any] = []
        while True:
            try:
                data = self._socket.recv(65535)
            except (BlockingIOError, ConnectionResetError):  # Windows reports ICMP unreachable
                return messages
            messages.extend(self._codec.parse_buffer(data) or [])

    def _mav(self) -> Any:
        return self._codec

    # --- behaviour ---------------------------------------------------------------------------

    def _step(self, dt: float) -> None:
        s = self.state
        if s.mode == "takeoff":
            goal = s.params["MIS_TAKEOFF_ALT"]
            s.altitude_relative_m = min(goal, s.altitude_relative_m + CLIMB_MPS * dt)
            if s.altitude_relative_m >= goal:
                s.mode = "hold"
        elif s.mode in ("hold", "return") and s.target is not None:
            self._fly_to(s.target, dt)
        elif s.mode == "land":
            s.altitude_relative_m = max(0.0, s.altitude_relative_m - CLIMB_MPS * dt)
            if s.altitude_relative_m == 0.0:
                s.in_air = False
                s.armed = False

    def _fly_to(self, target: tuple[float, float, float], dt: float) -> None:
        s = self.state
        north = math.radians(target[0] - s.latitude) * EARTH_RADIUS_M
        east = (
            math.radians(target[1] - s.longitude)
            * EARTH_RADIUS_M
            * math.cos(math.radians(s.latitude))
        )
        distance = math.hypot(north, east)
        step = SPEED_MPS * dt
        if distance <= step:
            s.latitude, s.longitude = target[0], target[1]
            s.target = None
            if s.mode == "return":
                s.mode = "land"
        else:
            s.latitude += (target[0] - s.latitude) * step / distance
            s.longitude += (target[1] - s.longitude) * step / distance
        s.altitude_relative_m = target[2]

    def _handle(self, message: Any) -> None:
        kind = message.get_type()
        if kind == "PARAM_SET" and message.target_system == self.system_id:
            self.state.params[message.param_id] = message.param_value
            self._mav().param_value_send(
                message.param_id.encode(), message.param_value, message.param_type, 1, 0
            )
        elif kind in ("COMMAND_LONG", "COMMAND_INT") and message.target_system in (
            0,
            self.system_id,
        ):
            self._command(message, kind == "COMMAND_INT")

    def _command(self, message: Any, is_int: bool) -> None:
        command = message.command
        self.received.append(command)
        if command in FLIGHT_COMMANDS and self.silent:
            return
        result = self._apply(message, is_int) if command not in self.deny else mav.MAV_RESULT_DENIED
        self._mav().command_ack_send(
            command, result, target_system=message.get_srcSystem(), target_component=0
        )

    def _apply(self, message: Any, is_int: bool) -> int:
        s = self.state
        command = message.command
        if command == mav.MAV_CMD_COMPONENT_ARM_DISARM:
            if message.param1 >= 0.5:
                s.armed = True
            elif s.in_air:
                return int(mav.MAV_RESULT_DENIED)
            else:
                s.armed = False
        elif command == mav.MAV_CMD_NAV_TAKEOFF:
            if not s.armed:
                return int(mav.MAV_RESULT_DENIED)
            s.in_air, s.mode = True, "takeoff"
        elif command == mav.MAV_CMD_NAV_LAND:
            s.mode, s.target = "land", None
        elif command == mav.MAV_CMD_NAV_RETURN_TO_LAUNCH:
            self._set_mode("return")
        elif command == mav.MAV_CMD_DO_SET_MODE:  # how MAVSDK asks PX4 for hold and return
            wanted = (int(message.param2), int(message.param3))
            name = next((n for n, m in MODES.items() if m == wanted), None)
            if name is None:
                return int(mav.MAV_RESULT_UNSUPPORTED)
            self._set_mode(name)
        elif command == mav.MAV_CMD_DO_REPOSITION:
            latitude = message.x / 1e7 if is_int else message.param5
            longitude = message.y / 1e7 if is_int else message.param6
            s.mode, s.target = "hold", (latitude, longitude, message.z - s.home_amsl_m)
        elif command in (mav.MAV_CMD_REQUEST_MESSAGE, 520):  # 520: autopilot capabilities
            requested = int(message.param1) if command == mav.MAV_CMD_REQUEST_MESSAGE else 148
            if requested == mav.MAVLINK_MSG_ID_AUTOPILOT_VERSION:
                self._autopilot_version()
            elif requested == mav.MAVLINK_MSG_ID_HOME_POSITION:
                self._home()
        return int(mav.MAV_RESULT_ACCEPTED)

    def _set_mode(self, name: str) -> None:
        s = self.state
        s.mode = name
        s.target = (*self.home, max(s.altitude_relative_m, 10.0)) if name == "return" else None

    # --- telemetry ---------------------------------------------------------------------------

    def _heartbeat(self) -> None:
        s = self.state
        base = mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED | (
            mav.MAV_MODE_FLAG_SAFETY_ARMED if s.armed else 0
        )
        main, sub = MODES[s.mode]
        self._mav().heartbeat_send(
            mav.MAV_TYPE_HEXAROTOR,
            mav.MAV_AUTOPILOT_PX4,
            base,
            (main << 16) | (sub << 24),
            mav.MAV_STATE_ACTIVE if s.armed else mav.MAV_STATE_STANDBY,
        )

    def _stream(self) -> None:
        s = self.state
        m = self._mav()
        boot_ms = int(time.monotonic() * 1000) & 0xFFFFFFFF
        latitude, longitude = int(s.latitude * 1e7), int(s.longitude * 1e7)
        amsl_mm = int((s.home_amsl_m + s.altitude_relative_m) * 1000)
        if s.gps_ok:
            m.global_position_int_send(
                boot_ms, latitude, longitude, amsl_mm, int(s.altitude_relative_m * 1000),
                0, 0, 0, 9000,
            )  # fmt: skip
        m.gps_raw_int_send(
            boot_ms * 1000,
            3 if s.gps_ok else 1,
            latitude,
            longitude,
            amsl_mm,
            80,
            120,
            0,
            0,
            14 if s.gps_ok else 0,
        )
        m.battery_status_send(0, 0, 0, 2500, [4000] * 6 + [65535] * 4, 1000, -1, -1, s.battery_pct)
        landed = mav.MAV_LANDED_STATE_IN_AIR if s.in_air else mav.MAV_LANDED_STATE_ON_GROUND
        m.extended_sys_state_send(mav.MAV_VTOL_STATE_UNDEFINED, landed)
        self._home()

    def _home(self) -> None:
        self._mav().home_position_send(
            int(self.home[0] * 1e7),
            int(self.home[1] * 1e7),
            int(self.state.home_amsl_m * 1000),
            0.0, 0.0, 0.0, [1.0, 0.0, 0.0, 0.0], 0.0, 0.0, 0.0,
        )  # fmt: skip

    def _autopilot_version(self) -> None:
        capabilities = (
            mav.MAV_PROTOCOL_CAPABILITY_MAVLINK2
            | mav.MAV_PROTOCOL_CAPABILITY_COMMAND_INT
            | mav.MAV_PROTOCOL_CAPABILITY_PARAM_FLOAT
            | mav.MAV_PROTOCOL_CAPABILITY_MISSION_INT
        )
        self._mav().autopilot_version_send(
            capabilities, 0, 0, 0, 0, [0] * 8, [0] * 8, [0] * 8, 0, 0, self.system_id
        )
