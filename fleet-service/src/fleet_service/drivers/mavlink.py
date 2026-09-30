"""
MAVLink aircraft through MAVSDK v4, the native in-process binding (ADR 0010, ADR 0022).

A *hub* is one MAVSDK instance on one connection (a UDP port, a serial radio). Every
aircraft whose registration names that connection is served by the same hub and told
apart by its MAVLink system id, so one radio or one ``mavlink-router`` endpoint carries
the whole fleet. A driver waits until its hub has heard from its system id; until then
the aircraft is offline and commands wait (the pipeline times them out).

Telemetry is whatever the aircraft streams; the ground station does not raise stream
rates, because on a shared radio that budget belongs to the link configuration. The
driver keeps the newest value of each subscription and emits a canonical sample five
times a second while anything new arrived, so silence on the link shows up as a stale
link, not as repeated old samples. A position older than ``POSITION_TIMEOUT_S`` or
without a 3D fix is reported unknown (ADR 0014). A GNSS report older than ``GPS_TIMEOUT_S``
counts as no fix: a failed receiver may just go quiet, and MAVSDK keeps its last report.

PX4 has no "going to a point" mode: a reposition flies in HOLD (loiter). The driver
remembers the target it sent and reports GOTO until the aircraft arrives or leaves HOLD,
so operators and command verification see what the aircraft is doing. HOLD keeps that
target for RESUME, which sends it again.
"""

import asyncio
import contextlib
import logging
import math
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from mavsdk import log_subscribe
from mavsdk.asyncio import ComponentType, Configuration, Mavsdk, MavsdkConnectionError
from mavsdk.asyncio.plugins.action import ActionAsync, ActionError, ActionResult
from mavsdk.asyncio.plugins.mission import (
    MissionAsync,
    MissionError,
    MissionItem,
    MissionPlan,
    MissionResult,
)
from mavsdk.asyncio.plugins.telemetry import TelemetryAsync

from fleet_service.clock import Clock
from fleet_service.domain.commands import AUTOPILOT_COMMANDS
from fleet_service.domain.enums import Airframe, CommandKind, FlightMode, GpsFix
from fleet_service.domain.geo import GeoPoint, distance_m
from fleet_service.domain.telemetry import TelemetrySample
from fleet_service.drivers.base import (
    CommandResult,
    DriverCommand,
    Outcome,
    RouteMission,
    TelemetrySink,
)

log = logging.getLogger(__name__)

EMIT_PERIOD_S = 0.2
POSITION_TIMEOUT_S = 3.0
GPS_TIMEOUT_S = 5.0
SCAN_PERIOD_S = 1.0
RECONNECT_PERIOD_S = 5.0
GOTO_SETTLE_S = 3.0  # a reposition may take this long to show up as HOLD
ARRIVE_RADIUS_M = {
    Airframe.MULTIROTOR_HEXA: 3.0,
    Airframe.MULTIROTOR_QUAD: 3.0,
    Airframe.FIXED_WING: 120.0,  # it circles the target on its loiter radius
}

_MODES = {
    "READY": FlightMode.HOLD,
    "TAKEOFF": FlightMode.TAKEOFF,
    "HOLD": FlightMode.HOLD,
    "MISSION": FlightMode.MISSION,
    "RETURN_TO_LAUNCH": FlightMode.RETURN,
    "LAND": FlightMode.LAND,
    "OFFBOARD": FlightMode.OFFBOARD,
    "MANUAL": FlightMode.MANUAL,
    "ALTCTL": FlightMode.MANUAL,
    "POSCTL": FlightMode.MANUAL,
    "ACRO": FlightMode.MANUAL,
    "STABILIZED": FlightMode.MANUAL,
    "RATTITUDE": FlightMode.MANUAL,
}

_FIXES = {
    "FIX_2D": GpsFix.FIX_2D,
    "FIX_3D": GpsFix.FIX_3D,
    "FIX_DGPS": GpsFix.DGPS,
    "RTK_FLOAT": GpsFix.RTK_FLOAT,
    "RTK_FIXED": GpsFix.RTK_FIXED,
}

# Results that mean "no answer from the aircraft": the pipeline reports a timeout.
_NO_ANSWER = {ActionResult.NO_SYSTEM, ActionResult.CONNECTION_ERROR, ActionResult.TIMEOUT}
_MISSION_NO_ANSWER = {MissionResult.NO_SYSTEM, MissionResult.TIMEOUT}


def flight_mode(px4_mode: str) -> FlightMode:
    """Our flight mode for a MAVSDK ``FlightMode`` name."""
    return _MODES.get(px4_mode, FlightMode.UNKNOWN)


def gps_fix(fix_type: str) -> GpsFix:
    """Our fix quality for a MAVSDK ``FixType`` name."""
    return _FIXES.get(fix_type, GpsFix.NONE)


def normalize_url(url: str) -> str:
    """One spelling per connection, so aircraft on the same port share a hub.

    ``udp://:14550`` and ``udp://0.0.0.0:14550`` are the legacy spellings of a listening
    UDP port, which MAVSDK v4 calls ``udpin://0.0.0.0:14550``.
    """
    url = url.strip()
    if url.startswith("udp://"):
        host, _, port = url.removeprefix("udp://").rpartition(":")
        return f"udpin://{host or '0.0.0.0'}:{port}"  # noqa: S104 - a listening port, by intent
    return url


def _number(value: float | None) -> float | None:
    """MAVSDK reports unknown floats as NaN."""
    if value is None or math.isnan(value):
        return None
    return float(value)


@dataclass
class _Target:
    """A reposition the aircraft was sent."""

    latitude: float
    longitude: float
    altitude_amsl_m: float
    sent_at: float  # monotonic


@dataclass
class _Latest:
    """The newest value of each telemetry subscription."""

    latitude: float | None = None
    longitude: float | None = None
    altitude_amsl_m: float | None = None
    altitude_relative_m: float | None = None
    position_at: float = -math.inf  # monotonic
    heading_deg: float | None = None
    groundspeed_mps: float | None = None
    climb_rate_mps: float | None = None
    battery_pct: float | None = None
    battery_v: float | None = None
    gps_fix: GpsFix = GpsFix.NONE
    satellites: int | None = None
    gps_at: float = -math.inf  # monotonic
    px4_mode: str = "UNKNOWN"
    armed: bool | None = None
    in_air: bool | None = None
    home_latitude: float | None = None
    home_longitude: float | None = None
    home_amsl_m: float | None = None
    mission_item: int | None = None
    mission_items: int | None = None


# Read-back tolerances: MAVLink carries positions as 1e-7 degrees and altitudes as float32.
READBACK_DEGREES = 2e-7
READBACK_METRES = 0.05


def mission_items(route: RouteMission) -> list[Any]:
    """MAVSDK mission items for a route (altitudes above home; NaN: not set)."""
    nan = math.nan
    return [
        MissionItem(
            latitude_deg=p.latitude,
            longitude_deg=p.longitude,
            relative_altitude_m=p.altitude_relative_m,
            speed_m_s=p.speed_mps if p.speed_mps is not None else nan,
            is_fly_through=not p.loiter_s,
            gimbal_pitch_deg=nan,
            gimbal_yaw_deg=nan,
            camera_action=MissionItem.CameraAction.NONE,
            loiter_time_s=p.loiter_s if p.loiter_s else nan,
            camera_photo_interval_s=nan,
            acceptance_radius_m=nan,
            yaw_deg=nan,
            camera_photo_distance_m=nan,
            vehicle_action=MissionItem.VehicleAction.NONE,
        )
        for p in route.items
    ]


def readback_mismatch(sent: list[Any], received: list[Any]) -> str | None:
    """Why the aircraft's copy of a mission differs from what was sent, or None."""
    if len(received) != len(sent):
        return f"the aircraft holds {len(received)} items, {len(sent)} were sent"
    for i, (a, b) in enumerate(zip(sent, received, strict=True)):
        if (
            abs(a.latitude_deg - b.latitude_deg) > READBACK_DEGREES
            or abs(a.longitude_deg - b.longitude_deg) > READBACK_DEGREES
        ):
            return f"item {i} is at a different position"
        if abs(a.relative_altitude_m - b.relative_altitude_m) > READBACK_METRES:
            return f"item {i} is at a different altitude"
    return None


class MavlinkDriver:
    """One aircraft on a MAVLink hub, identified by its system id."""

    source = "mavlink"
    capabilities = AUTOPILOT_COMMANDS

    def __init__(
        self,
        aircraft_id: str,
        system_id: int,
        airframe: Airframe,
        clock: Clock,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.aircraft_id = aircraft_id
        self.system_id = system_id
        self.airframe = airframe
        self._clock = clock
        self._monotonic = monotonic
        self._sink: TelemetrySink | None = None
        self._latest = _Latest()
        self._fresh = False
        self._target: _Target | None = None
        self._paused: _Target | None = None
        self._action: Any = None
        self._mission: Any = None
        self._mission_paused = False
        self._bound = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    # --- lifecycle ---------------------------------------------------------------------------

    def start(self, sink: TelemetrySink) -> None:
        """Begin delivering telemetry (once the hub has found the aircraft)."""
        self._sink = sink
        self._tasks.append(asyncio.create_task(self._emit_loop(), name=f"mavlink-emit-{self}"))

    def stop(self) -> None:
        """Stop delivering telemetry; subscriptions end at the next loop iteration."""
        self._sink = None
        for task in self._tasks:
            task.cancel()

    async def aclose(self) -> None:
        """Stop and wait until every subscription has been released."""
        self.stop()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    @property
    def bound(self) -> bool:
        """True once the hub has heard from this aircraft."""
        return self._bound.is_set()

    def bind(self, telemetry: Any, action: Any, mission: Any = None) -> None:
        """Attach the aircraft's MAVSDK plugins (called by the hub on discovery)."""
        self._action = action
        self._mission = mission
        subscriptions: list[tuple[Callable[[], AsyncIterator[Any]], Callable[[Any], None]]] = [
            (telemetry.subscribe_position, self._on_position),
            (telemetry.subscribe_heading, self._on_heading),
            (telemetry.subscribe_velocity_ned, self._on_velocity),
            (telemetry.subscribe_battery, self._on_battery),
            (telemetry.subscribe_gps_info, self._on_gps),
            (telemetry.subscribe_flight_mode, self._on_flight_mode),
            (telemetry.subscribe_armed, self._on_armed),
            (telemetry.subscribe_in_air, self._on_in_air),
            (telemetry.subscribe_home, self._on_home),
        ]
        if mission is not None:
            subscriptions.append((mission.subscribe_mission_progress, self._on_progress))
        for subscribe, apply in subscriptions:
            self._tasks.append(
                asyncio.create_task(
                    self._follow(subscribe, apply), name=f"mavlink-{apply.__name__}-{self}"
                )
            )
        self._bound.set()

    def __str__(self) -> str:
        return f"sys{self.system_id}"

    # --- telemetry ---------------------------------------------------------------------------

    async def _follow(
        self, subscribe: Callable[[], AsyncIterator[Any]], apply: Callable[[Any], None]
    ) -> None:
        try:
            async for value in subscribe():
                apply(value)
                self._fresh = True
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("MAVLink subscription %s of %s failed", apply.__name__, self)

    def _on_position(self, position: Any) -> None:
        latest = self._latest
        latest.latitude = _number(position.latitude_deg)
        latest.longitude = _number(position.longitude_deg)
        latest.altitude_amsl_m = _number(position.absolute_altitude_m)
        latest.altitude_relative_m = _number(position.relative_altitude_m)
        latest.position_at = self._monotonic()

    def _on_heading(self, heading: Any) -> None:
        self._latest.heading_deg = _number(heading.heading_deg)

    def _on_velocity(self, velocity: Any) -> None:
        north, east, down = (
            _number(velocity.north_m_s),
            _number(velocity.east_m_s),
            _number(velocity.down_m_s),
        )
        self._latest.groundspeed_mps = (
            math.hypot(north, east) if north is not None and east is not None else None
        )
        self._latest.climb_rate_mps = -down if down is not None else None

    def _on_battery(self, battery: Any) -> None:
        if battery.id not in (0, None):
            return  # the first battery is the one the failsafes watch
        self._latest.battery_pct = _number(battery.remaining_percent)
        self._latest.battery_v = _number(battery.voltage_v)

    def _on_gps(self, info: Any) -> None:
        self._latest.gps_fix = gps_fix(info.fix_type.name)
        self._latest.satellites = info.num_satellites
        self._latest.gps_at = self._monotonic()

    def _on_flight_mode(self, mode: Any) -> None:
        self._latest.px4_mode = mode.name

    def _on_armed(self, armed: bool) -> None:
        self._latest.armed = armed

    def _on_in_air(self, in_air: bool) -> None:
        self._latest.in_air = in_air

    def _on_home(self, home: Any) -> None:
        self._latest.home_latitude = _number(home.latitude_deg)
        self._latest.home_longitude = _number(home.longitude_deg)
        self._latest.home_amsl_m = _number(home.absolute_altitude_m)

    def _on_progress(self, progress: Any) -> None:
        total = int(progress.total)
        self._latest.mission_items = total if total > 0 else None
        self._latest.mission_item = int(progress.current) if total > 0 else None

    async def _emit_loop(self) -> None:
        while True:
            await asyncio.sleep(EMIT_PERIOD_S)
            if self._fresh and self._sink is not None:
                self._fresh = False
                self._sink(self.sample())

    def sample(self) -> TelemetrySample:
        """The canonical sample of what the aircraft last reported."""
        latest = self._latest
        now = self._monotonic()
        gps_current = now - latest.gps_at <= GPS_TIMEOUT_S
        fix = latest.gps_fix if gps_current else GpsFix.NONE
        positioned = (
            fix.has_3d
            and latest.latitude is not None
            and latest.longitude is not None
            and now - latest.position_at <= POSITION_TIMEOUT_S
        )
        return TelemetrySample(
            aircraft_id=self.aircraft_id,
            ts=self._clock.now(),
            source=self.source,
            latitude=latest.latitude if positioned else None,
            longitude=latest.longitude if positioned else None,
            altitude_amsl_m=latest.altitude_amsl_m if positioned else None,
            altitude_relative_m=latest.altitude_relative_m if positioned else None,
            heading_deg=latest.heading_deg,
            groundspeed_mps=latest.groundspeed_mps,
            climb_rate_mps=latest.climb_rate_mps,
            battery_pct=latest.battery_pct,
            battery_v=latest.battery_v,
            gps_fix=fix,
            satellites=latest.satellites if gps_current else None,
            flight_mode=self._mode(now, positioned),
            armed=latest.armed,
            in_air=latest.in_air,
            home_latitude=latest.home_latitude,
            home_longitude=latest.home_longitude,
            mission_item=latest.mission_item,
            mission_items=latest.mission_items,
        )

    def _mode(self, now: float, positioned: bool) -> FlightMode:
        mode = flight_mode(self._latest.px4_mode)
        target = self._target
        if target is None:
            return mode
        if mode is not FlightMode.HOLD:
            if now - target.sent_at > GOTO_SETTLE_S:
                self._target = None  # someone (or a failsafe) switched mode: the goto is over
            return mode
        if positioned and self._arrived(target):
            self._target = None
            return mode
        return FlightMode.GOTO

    def _arrived(self, target: _Target) -> bool:
        latest = self._latest
        assert latest.latitude is not None  # noqa: S101
        assert latest.longitude is not None  # noqa: S101
        here = GeoPoint(latitude=latest.latitude, longitude=latest.longitude)
        there = GeoPoint(latitude=target.latitude, longitude=target.longitude)
        return distance_m(here, there) <= ARRIVE_RADIUS_M[self.airframe]

    # --- commands ----------------------------------------------------------------------------

    async def execute(self, command: DriverCommand) -> CommandResult:
        """Send ``command``; waits while the aircraft is undiscovered (callers time out)."""
        await self._bound.wait()
        if command.kind is CommandKind.MISSION_START:
            if command.route is None:
                return CommandResult.nack("Swarm missions go through the swarm link.")
            return await self._start_mission(command.route)
        if command.kind is CommandKind.MISSION_PAUSE:
            result = await self._mission_result(self._mission.pause_mission())
            self._mission_paused = result.outcome is Outcome.ACKED
            return result
        if command.kind is CommandKind.RESUME and (command.gcs_mission or self._mission_paused):
            result = await self._mission_result(self._mission.start_mission())
            if result.outcome is Outcome.ACKED:
                self._mission_paused = False
            return result
        if command.kind is CommandKind.RESUME:
            if self._paused is None:
                return CommandResult.nack("Nothing to resume: no reposition was paused.")
            target = self._paused
            return await self._goto(target.latitude, target.longitude, target.altitude_amsl_m)
        if command.kind is CommandKind.GOTO:
            amsl_m = self._goto_amsl(command.altitude_relative_m)
            if amsl_m is None:
                return CommandResult.nack("Altitude unknown: cannot place the target.")
            assert command.latitude is not None  # noqa: S101 - the command rules require both
            assert command.longitude is not None  # noqa: S101
            return await self._goto(command.latitude, command.longitude, amsl_m)
        result = await self._call(command)
        if result.outcome is Outcome.ACKED:
            self._paused = self._target if command.kind is CommandKind.HOLD else None
            self._target = None
            if command.kind is CommandKind.HOLD and self._latest.px4_mode == "MISSION":
                self._mission_paused = True  # hold pauses the mission; resume continues it
            elif command.kind is not CommandKind.HOLD:
                self._mission_paused = False
        return result

    async def _start_mission(self, route: RouteMission) -> CommandResult:
        """Upload, read back and compare, then start (ADR 0028). Nothing flies unverified."""
        mission = self._mission
        items = mission_items(route)
        for call in (
            mission.set_return_to_launch_after_mission(route.return_home),
            mission.upload_mission(MissionPlan(items)),
        ):
            result = await self._mission_result(call)
            if result.outcome is not Outcome.ACKED:
                return result
        try:
            copy = await mission.download_mission()
        except MissionError as error:
            if error.result in _MISSION_NO_ANSWER:
                await asyncio.Future()  # never resolves; the pipeline's timeout applies
            return CommandResult.nack(f"The mission could not be read back ({error.result.name}).")
        mismatch = readback_mismatch(items, list(copy.mission_items))
        if mismatch is not None:
            return CommandResult.nack(f"Mission read-back mismatch: {mismatch}; not started.")
        result = await self._mission_result(mission.start_mission())
        if result.outcome is Outcome.ACKED:
            self._target = self._paused = None
            self._mission_paused = False
        return result

    @staticmethod
    async def _mission_result(call: Any) -> CommandResult:
        """Ack, nack with the reason, or wait (no answer: the caller times out)."""
        try:
            await call
        except MissionError as error:
            if error.result in _MISSION_NO_ANSWER:
                await asyncio.Future()  # never resolves; the pipeline's timeout applies
            return CommandResult.nack(f"The aircraft refused the mission ({error.result.name}).")
        return CommandResult.ack()

    def _goto_amsl(self, altitude_relative_m: float | None) -> float | None:
        """MAVLink repositions take AMSL: home plus the height asked for, or the current one."""
        if altitude_relative_m is None:
            return self._latest.altitude_amsl_m
        if self._latest.home_amsl_m is None:
            return None
        return self._latest.home_amsl_m + altitude_relative_m

    async def _goto(self, latitude: float, longitude: float, amsl_m: float) -> CommandResult:
        result = await self._action_result(
            self._action.goto_location(latitude, longitude, amsl_m, math.nan)
        )
        if result.outcome is Outcome.ACKED:
            self._target = _Target(latitude, longitude, amsl_m, self._monotonic())
            self._paused = None
        return result

    async def _call(self, command: DriverCommand) -> CommandResult:
        action = self._action
        match command.kind:
            case CommandKind.ARM:
                return await self._action_result(action.arm())
            case CommandKind.DISARM:
                return await self._action_result(action.disarm())
            case CommandKind.TAKEOFF:
                if command.altitude_relative_m is not None:
                    set_altitude = await self._action_result(
                        action.set_takeoff_altitude(command.altitude_relative_m)
                    )
                    if set_altitude.outcome is not Outcome.ACKED:
                        return set_altitude
                return await self._action_result(action.takeoff())
            case CommandKind.HOLD:
                return await self._action_result(action.hold())
            case CommandKind.RETURN_TO_LAUNCH:
                return await self._action_result(action.return_to_launch())
            case CommandKind.LAND:
                return await self._action_result(action.land())
        return CommandResult.nack(f"{command.kind.value} is not supported over MAVLink yet.")

    @staticmethod
    async def _action_result(call: Any) -> CommandResult:
        """Ack, nack with the aircraft's reason, or wait (no answer: the caller times out)."""
        try:
            await call
        except ActionError as error:
            if error.result in _NO_ANSWER:
                await asyncio.Future()  # never resolves; the pipeline's timeout applies
            return CommandResult.nack(_reason(error.result))
        return CommandResult.ack()


def _reason(result: Any) -> str:
    """Operator-readable text for a MAVSDK ``ActionResult``."""
    texts = {
        "BUSY": "The aircraft is busy.",
        "COMMAND_DENIED": "The aircraft refused the command.",
        "COMMAND_DENIED_LANDED_STATE_UNKNOWN": "Refused: the aircraft does not know if it has "
        "landed.",
        "COMMAND_DENIED_NOT_LANDED": "Refused: the aircraft is not landed.",
        "UNSUPPORTED": "The aircraft does not support this command.",
        "PARAMETER_ERROR": "The aircraft rejected a parameter.",
        "INVALID_ARGUMENT": "The aircraft rejected an argument.",
        "FAILED": "The command failed on the aircraft.",
    }
    return texts.get(result.name, f"Refused by the aircraft ({result.name.lower()}).")


class MavlinkHub:
    """One MAVSDK instance on one connection, serving every aircraft behind it."""

    def __init__(self, url: str, after: "asyncio.Task[None] | None" = None) -> None:
        self.url = url
        self._after = after  # a previous hub on this connection that is still closing
        self._drivers: dict[int, MavlinkDriver] = {}
        self._retired: list[MavlinkDriver] = []  # detached, subscriptions maybe still ending
        self._plugins: dict[int, tuple[Any, Any, Any]] = {}
        self._mavsdk: Mavsdk | None = None
        self._task = asyncio.create_task(self._run(), name=f"mavlink-hub-{url}")

    def attach(self, driver: MavlinkDriver) -> None:
        """Serve ``driver``'s system id; binds at once if the aircraft was already heard."""
        self._drivers[driver.system_id] = driver
        if driver.system_id in self._plugins:
            driver.bind(*self._plugins[driver.system_id])

    def detach(self, driver: MavlinkDriver) -> None:
        """Stop serving ``driver``."""
        if self._drivers.get(driver.system_id) is driver:
            del self._drivers[driver.system_id]
            self._retired.append(driver)

    @property
    def empty(self) -> bool:
        """True when no aircraft uses this connection any more."""
        return not self._drivers

    async def close(self) -> None:
        """Release every driver's subscriptions, then the MAVSDK instance and its port."""
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        for driver in [*self._drivers.values(), *self._retired]:
            await driver.aclose()  # plugins must be unsubscribed before MAVSDK is destroyed
        self._retired.clear()
        self._plugins.clear()
        if self._mavsdk is not None:
            self._mavsdk.destroy()
            self._mavsdk = None

    async def _run(self) -> None:
        if self._after is not None:
            with contextlib.suppress(Exception):
                await self._after
        _route_mavsdk_logs()
        config = Configuration.create_with_component_type(ComponentType.GROUND_STATION)
        self._mavsdk = Mavsdk(config)
        while True:
            try:
                await self._mavsdk.add_any_connection(self.url)
                break
            except MavsdkConnectionError as error:
                log.error("MAVLink connection %s failed (%s); retrying", self.url, error)
                await asyncio.sleep(RECONNECT_PERIOD_S)
        log.info("MAVLink connection %s open", self.url)
        known = 0
        while True:
            count = await self._mavsdk.system_count()
            if count != known:
                known = count
                await self._scan()
            await asyncio.sleep(SCAN_PERIOD_S)

    async def _scan(self) -> None:
        assert self._mavsdk is not None  # noqa: S101
        for system in await self._mavsdk.get_systems():
            system_id = await system.get_system_id()
            if system_id in self._plugins:
                continue
            self._plugins[system_id] = (
                TelemetryAsync(system),
                ActionAsync(system),
                MissionAsync(system),
            )
            log.info("MAVLink system %d heard on %s", system_id, self.url)
            driver = self._drivers.get(system_id)
            if driver is not None:
                driver.bind(*self._plugins[system_id])


class MavlinkLinks:
    """The hubs of every connection in use, created and closed as aircraft come and go."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._hubs: dict[str, MavlinkHub] = {}
        self._closing: dict[str, asyncio.Task[None]] = {}

    def driver(
        self, aircraft_id: str, url: str, system_id: int, airframe: Airframe
    ) -> MavlinkDriver:
        """A driver for an aircraft, on the hub of its connection."""
        url = normalize_url(url)
        hub = self._hubs.get(url)
        if hub is None:
            hub = self._hubs[url] = MavlinkHub(url, after=self._closing.get(url))
        driver = MavlinkDriver(aircraft_id, system_id, airframe, self._clock)
        hub.attach(driver)
        return driver

    def release(self, driver: MavlinkDriver) -> None:
        """Stop a driver; close its hub if no other aircraft uses the connection."""
        driver.stop()
        for url, hub in list(self._hubs.items()):
            hub.detach(driver)
            if hub.empty:
                del self._hubs[url]
                self._closing[url] = asyncio.create_task(hub.close(), name=f"close-{url}")

    async def close(self) -> None:
        """Close every hub (at shutdown)."""
        for hub in self._hubs.values():
            await hub.close()
        self._hubs.clear()
        for task in self._closing.values():
            with contextlib.suppress(Exception):
                await task
        self._closing.clear()


_logs_routed = False


def _route_mavsdk_logs() -> None:
    """Send MAVSDK's own log lines to our logging instead of stdout (once per process)."""
    global _logs_routed  # one process-wide subscription in the C library
    if _logs_routed:
        return
    _logs_routed = True
    mavsdk_log = logging.getLogger("mavsdk")

    def forward(level: Any, message: str, _file: str | None, _line: int) -> bool:
        mavsdk_log.log(logging.WARNING if level.value >= 2 else logging.DEBUG, "%s", message)
        return True

    log_subscribe(forward)
