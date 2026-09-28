"""
Simulated aircraft for development, tests, demos and GCS load tests (ADR 0021).

This is a kinematic model, not a flight-dynamics simulator and not a substitute for
PX4 SITL (M2): speeds, climb rates and battery drain are plausible constants, fixed-wing
aircraft loiter on a circle and "land" by descending on it. What it does model on
purpose is what the ground station must handle: modes and their transitions, commands
that aircraft refuse, and PX4-like failsafes that act without the ground station
(ADR 0002, S1): link lost for 10 s -> return; GNSS lost -> land; battery 10 % -> return,
5 % -> land. Faults are injected per aircraft (link down, GNSS lost, battery level).

Positions live in a local east/north frame (metres) around the simulation origin and
are converted with an equirectangular approximation, which is fine for a simulator
covering a few kilometres. Everything is deterministic for a given seed.
"""

import asyncio
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fleet_service.domain.commands import FLIGHT_COMMANDS
from fleet_service.domain.enums import Airframe, CommandKind, FlightMode, GpsFix
from fleet_service.domain.geo import GeoPoint
from fleet_service.domain.telemetry import TelemetrySample
from fleet_service.drivers.base import CommandResult, DriverCommand, TelemetrySink

EARTH_RADIUS_M = 6_371_000.0
FAILSAFE_LINK_LOSS_S = 10.0
FAILSAFE_RTL_BATTERY_PCT = 10.0
FAILSAFE_LAND_BATTERY_PCT = 5.0
RTL_MIN_ALTITUDE_M = 50.0
DEFAULT_TAKEOFF_ALTITUDE_M = 30.0
SPAWN_SPACING_M = 15.0
SPAWN_COLUMNS = 10


@dataclass(frozen=True)
class AirframeModel:
    """Performance constants of a simulated airframe."""

    cruise_mps: float
    climb_mps: float
    descent_mps: float
    accel_mps2: float
    hovers: bool
    loiter_radius_m: float
    endurance_s: float  # full battery, in flight
    cells: int
    arrive_radius_m: float


MODELS = {
    Airframe.MULTIROTOR_HEXA: AirframeModel(8.0, 3.0, 2.0, 3.0, True, 0.0, 25 * 60, 6, 1.5),
    Airframe.MULTIROTOR_QUAD: AirframeModel(10.0, 3.0, 2.0, 4.0, True, 0.0, 20 * 60, 4, 1.5),
    Airframe.FIXED_WING: AirframeModel(18.0, 4.0, 2.5, 2.0, False, 60.0, 60 * 60, 4, 60.0),
}


class MockVehicle:
    """One simulated aircraft."""

    def __init__(
        self,
        airframe: Airframe,
        origin: GeoPoint,
        origin_amsl_m: float,
        spawn: tuple[float, float],
        battery_pct: float,
        satellites: int,
    ) -> None:
        self.airframe = airframe
        self.model = MODELS[airframe]
        self.origin = origin
        self.origin_amsl_m = origin_amsl_m
        self.x, self.y = spawn
        self.z = 0.0
        self.home = spawn
        self.heading_deg = 0.0
        self.speed = 0.0
        self.vz = 0.0
        self.armed = False
        self.in_air = False
        self.mode = FlightMode.HOLD
        self.battery_pct = battery_pct
        self.satellites = satellites
        self.link_up = True
        self.gps_ok = True
        self.link_down_s = 0.0
        self.target_alt = 0.0
        self.anchor: tuple[float, float, float] | None = None  # hold point or goto target
        self.paused_goto: tuple[float, float, float] | None = None
        self.rtl_alt = RTL_MIN_ALTITUDE_M
        self.last_failsafe: str | None = None

    # --- frames ---------------------------------------------------------------------------

    def to_local(self, latitude: float, longitude: float) -> tuple[float, float]:
        """WGS84 -> local east/north metres around the origin."""
        lat0 = math.radians(self.origin.latitude)
        east = math.radians(longitude - self.origin.longitude) * EARTH_RADIUS_M * math.cos(lat0)
        north = math.radians(latitude - self.origin.latitude) * EARTH_RADIUS_M
        return east, north

    def to_geo(self, east: float, north: float) -> tuple[float, float]:
        """Local east/north metres -> WGS84 (latitude, longitude)."""
        lat0 = math.radians(self.origin.latitude)
        latitude = self.origin.latitude + math.degrees(north / EARTH_RADIUS_M)
        longitude = self.origin.longitude + math.degrees(east / (EARTH_RADIUS_M * math.cos(lat0)))
        return latitude, longitude

    # --- commands ---------------------------------------------------------------------------

    def command(self, cmd: DriverCommand) -> CommandResult:
        """Apply a command as an autopilot would, or refuse it with its reason."""
        kind = cmd.kind
        if kind is CommandKind.ARM:
            if self.armed or self.in_air:
                return CommandResult.nack("already armed")
            if not self.gps_ok:
                return CommandResult.nack("arming denied: no GNSS fix")
            if self.battery_pct < FAILSAFE_RTL_BATTERY_PCT:
                return CommandResult.nack("arming denied: battery too low")
            self.armed = True
            return CommandResult.ack()
        if kind is CommandKind.DISARM:
            if self.in_air:
                return CommandResult.nack("disarm denied: in flight")
            self.armed = False
            self.mode = FlightMode.HOLD
            return CommandResult.ack()
        if kind is CommandKind.TAKEOFF:
            if not self.armed:
                return CommandResult.nack("takeoff denied: not armed")
            if self.in_air:
                return CommandResult.nack("takeoff denied: already flying")
            self.mode = FlightMode.TAKEOFF
            self.target_alt = cmd.altitude_relative_m or DEFAULT_TAKEOFF_ALTITUDE_M
            return CommandResult.ack()
        if not self.in_air:
            return CommandResult.nack(f"{kind.value} denied: on the ground")
        if kind is CommandKind.HOLD:
            if self.mode is FlightMode.GOTO:
                self.paused_goto = self.anchor
            self._hold_here()
        elif kind is CommandKind.RESUME:
            if self.paused_goto is None:
                return CommandResult.nack("nothing to resume")
            self.anchor, self.paused_goto = self.paused_goto, None
            self.mode = FlightMode.GOTO
        elif kind is CommandKind.RETURN_TO_LAUNCH:
            self._start_return()
        elif kind is CommandKind.LAND:
            self._start_land()
        elif kind is CommandKind.GOTO:
            if not self.gps_ok:
                return CommandResult.nack("goto denied: no position")
            if cmd.latitude is None or cmd.longitude is None:
                return CommandResult.nack("goto denied: no target")
            east, north = self.to_local(cmd.latitude, cmd.longitude)
            altitude = cmd.altitude_relative_m if cmd.altitude_relative_m is not None else self.z
            self.anchor = (east, north, altitude)
            self.paused_goto = None
            self.mode = FlightMode.GOTO
        else:
            return CommandResult.nack(f"{kind.value} is not supported by the simulator")
        return CommandResult.ack()

    def _hold_here(self) -> None:
        self.mode = FlightMode.HOLD
        self.anchor = (self.x, self.y, self.z)

    def _start_return(self) -> None:
        self.mode = FlightMode.RETURN
        self.rtl_alt = max(self.z, RTL_MIN_ALTITUDE_M)
        self.paused_goto = None

    def _start_land(self) -> None:
        self.mode = FlightMode.LAND
        self.anchor = (self.x, self.y, 0.0)
        self.paused_goto = None

    # --- simulation step -----------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance the simulation by ``dt`` seconds."""
        self._failsafes(dt)
        if not self.in_air:
            if self.mode is FlightMode.TAKEOFF and self.armed:
                self._vertical_toward(self.target_alt, dt)
                if self.z > 0.1:
                    self.in_air = True
            else:
                self.speed, self.vz = 0.0, 0.0
            self._drain(dt)
            return
        if self.mode is FlightMode.TAKEOFF:
            if not self.model.hovers:
                self._advance_straight(self.model.cruise_mps, dt)
            self._vertical_toward(self.target_alt, dt)
            if self.z >= self.target_alt - 0.5:
                self._hold_here()
        elif self.mode is FlightMode.HOLD and self.anchor is not None:
            self._station_keep(self.anchor, dt)
        elif self.mode is FlightMode.GOTO and self.anchor is not None:
            if self._fly_to(self.anchor, dt):
                self.mode = FlightMode.HOLD  # arrived: hold at the target
        elif self.mode is FlightMode.RETURN:
            self._return(dt)
        elif self.mode is FlightMode.LAND:
            self._land(dt)
        self._drain(dt)

    def _failsafes(self, dt: float) -> None:
        self.link_down_s = 0.0 if self.link_up else self.link_down_s + dt
        if not self.in_air:
            return
        busy = self.mode in (FlightMode.RETURN, FlightMode.LAND)
        if self.battery_pct <= FAILSAFE_LAND_BATTERY_PCT and self.mode is not FlightMode.LAND:
            self._failsafe("battery critical: land", self._start_land)
        elif self.battery_pct <= FAILSAFE_RTL_BATTERY_PCT and not busy:
            self._failsafe("battery low: return", self._start_return)
        elif not self.gps_ok and self.mode is not FlightMode.LAND:
            self._failsafe("GNSS lost: land", self._start_land)
        elif self.link_down_s > FAILSAFE_LINK_LOSS_S and not busy:
            self._failsafe("data link lost: return", self._start_return)

    def _failsafe(self, reason: str, action: Callable[[], None]) -> None:
        self.last_failsafe = reason
        action()

    def _drain(self, dt: float) -> None:
        if self.in_air:
            rate = 100.0 / self.model.endurance_s
        elif self.armed:
            rate = 100.0 / (self.model.endurance_s * 10)
        else:
            rate = 0.0
        self.battery_pct = max(0.0, self.battery_pct - rate * dt)

    # --- motion helpers ----------------------------------------------------------------------

    def _vertical_toward(self, target: float, dt: float) -> None:
        delta = max(-self.model.descent_mps * dt, min(self.model.climb_mps * dt, target - self.z))
        self.z = max(0.0, self.z + delta)
        self.vz = delta / dt if dt > 0 else 0.0

    def _advance_straight(self, speed: float, dt: float) -> None:
        heading = math.radians(self.heading_deg)
        self.speed = speed
        self.x += math.sin(heading) * speed * dt
        self.y += math.cos(heading) * speed * dt

    def _fly_to(self, target: tuple[float, float, float], dt: float) -> bool:
        """Move toward ``target``; True once within the arrival radius."""
        tx, ty, tz = target
        self._vertical_toward(tz, dt)
        dx, dy = tx - self.x, ty - self.y
        distance = math.hypot(dx, dy)
        if distance <= self.model.arrive_radius_m:
            return abs(self.z - tz) < 1.0 or not self.model.hovers
        if self.model.hovers:
            braking = math.sqrt(2 * self.model.accel_mps2 * distance)
            desired = min(self.model.cruise_mps, braking)
            self.speed = min(desired, self.speed + self.model.accel_mps2 * dt)
        else:
            self.speed = self.model.cruise_mps
        travel = min(distance, self.speed * dt)
        self.x += dx / distance * travel
        self.y += dy / distance * travel
        self.heading_deg = math.degrees(math.atan2(dx, dy)) % 360.0
        return False

    def _station_keep(self, anchor: tuple[float, float, float], dt: float) -> None:
        if self.model.hovers:
            self._fly_to(anchor, dt)
            if math.hypot(anchor[0] - self.x, anchor[1] - self.y) <= self.model.arrive_radius_m:
                self.speed = 0.0
        else:
            self._loiter(anchor, dt)

    def _loiter(self, centre: tuple[float, float, float], dt: float) -> None:
        cx, cy, cz = centre
        radius = self.model.loiter_radius_m
        self._vertical_toward(cz, dt)
        offset_x, offset_y = self.x - cx, self.y - cy
        distance = math.hypot(offset_x, offset_y)
        speed = self.model.cruise_mps * 0.8
        self.speed = speed
        if distance > radius + 5.0:  # fly to the circle first
            self._fly_to(
                (cx + offset_x / distance * radius, cy + offset_y / distance * radius, cz), dt
            )
            self.speed = speed
            return
        angle = math.atan2(offset_y, offset_x) - speed / radius * dt  # clockwise orbit
        self.x, self.y = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        # Clockwise velocity is (sin a, -cos a) in east/north; heading is clockwise from north.
        self.heading_deg = math.degrees(math.atan2(math.sin(angle), -math.cos(angle))) % 360.0

    def _return(self, dt: float) -> None:
        hx, hy = self.home
        if self.z < self.rtl_alt - 0.5 and self.model.hovers:
            self._vertical_toward(self.rtl_alt, dt)
            return
        if self._fly_to((hx, hy, self.rtl_alt), dt):
            self.mode = FlightMode.LAND
            self.anchor = (hx, hy, 0.0)

    def _land(self, dt: float) -> None:
        anchor = self.anchor or (self.x, self.y, 0.0)
        if self.model.hovers:
            self.speed = 0.0
            self._vertical_toward(0.0, dt)
        else:
            self._loiter((anchor[0], anchor[1], 0.0), dt)
        if self.z <= 0.0:
            self._touchdown()

    def _touchdown(self) -> None:
        self.z, self.speed, self.vz = 0.0, 0.0, 0.0
        self.in_air = False
        self.armed = False  # auto-disarm after landing, as PX4 does
        self.mode = FlightMode.HOLD
        self.anchor = None
        self.paused_goto = None

    # --- telemetry ----------------------------------------------------------------------------

    def sample(self, aircraft_id: str, ts: datetime) -> TelemetrySample:
        """The telemetry the aircraft would report now."""
        latitude: float | None
        longitude: float | None
        if self.gps_ok:
            latitude, longitude = self.to_geo(self.x, self.y)
        else:
            latitude = longitude = None
        home_lat, home_lon = self.to_geo(*self.home)
        return TelemetrySample(
            aircraft_id=aircraft_id,
            ts=ts,
            source="mock",
            latitude=latitude,
            longitude=longitude,
            altitude_amsl_m=round(self.origin_amsl_m + self.z, 2),
            altitude_relative_m=round(self.z, 2),
            heading_deg=round(self.heading_deg, 1),
            groundspeed_mps=round(self.speed, 2),
            climb_rate_mps=round(self.vz, 2),
            battery_pct=round(self.battery_pct, 2),
            battery_v=round(self.model.cells * (3.5 + 0.7 * self.battery_pct / 100.0), 2),
            gps_fix=GpsFix.FIX_3D if self.gps_ok else GpsFix.NONE,
            satellites=self.satellites if self.gps_ok else 0,
            flight_mode=self.mode,
            armed=self.armed,
            in_air=self.in_air,
            home_latitude=home_lat,
            home_longitude=home_lon,
        )


class MockDriver:
    """The driver of one simulated aircraft."""

    source = "mock"
    capabilities = FLIGHT_COMMANDS

    def __init__(self, aircraft_id: str, vehicle: MockVehicle) -> None:
        self.aircraft_id = aircraft_id
        self.vehicle = vehicle
        self._sink: TelemetrySink | None = None
        self._link = asyncio.Event()
        self._link.set()

    def start(self, sink: TelemetrySink) -> None:
        """Begin delivering telemetry."""
        self._sink = sink

    def stop(self) -> None:
        """Stop delivering telemetry."""
        self._sink = None

    def emit(self, ts: datetime) -> None:
        """Deliver the current sample, unless the simulated link is down."""
        if self._sink is not None and self.vehicle.link_up:
            self._sink(self.vehicle.sample(self.aircraft_id, ts))

    async def execute(self, command: DriverCommand) -> CommandResult:
        """Deliver ``command``; waits while the simulated link is down (callers time out)."""
        await self._link.wait()
        return self.vehicle.command(command)

    def inject(
        self, *, link: bool | None = None, gps: bool | None = None, battery_pct: float | None = None
    ) -> None:
        """Inject faults: link up/down, GNSS ok/lost, battery level."""
        if link is not None:
            self.vehicle.link_up = link
            if link:
                self._link.set()
            else:
                self._link.clear()
        if gps is not None:
            self.vehicle.gps_ok = gps
        if battery_pct is not None:
            self.vehicle.battery_pct = battery_pct


class MockFleet:
    """All simulated aircraft; spawns them on a grid at the origin, in registration order."""

    def __init__(self, origin: GeoPoint, origin_amsl_m: float, seed: int) -> None:
        self.origin = origin
        self.origin_amsl_m = origin_amsl_m
        self._rng = random.Random(seed)  # noqa: S311 - simulation, not security
        self._slot = 0
        self.drivers: dict[str, MockDriver] = {}

    def add(self, aircraft_id: str, airframe: Airframe) -> MockDriver:
        """Create the simulated aircraft for a registered one."""
        column, row = self._slot % SPAWN_COLUMNS, self._slot // SPAWN_COLUMNS
        self._slot += 1
        vehicle = MockVehicle(
            airframe,
            self.origin,
            self.origin_amsl_m,
            spawn=(column * SPAWN_SPACING_M, row * SPAWN_SPACING_M),
            battery_pct=round(98.0 + 2.0 * self._rng.random(), 1),
            satellites=self._rng.randint(12, 18),
        )
        driver = MockDriver(aircraft_id, vehicle)
        self.drivers[aircraft_id] = driver
        return driver

    def remove(self, aircraft_id: str) -> None:
        """Delete a simulated aircraft."""
        self.drivers.pop(aircraft_id, None)

    def step(self, dt: float, now: datetime) -> None:
        """Advance every aircraft and deliver its telemetry."""
        for driver in tuple(self.drivers.values()):
            driver.vehicle.step(dt)
            driver.emit(now)
