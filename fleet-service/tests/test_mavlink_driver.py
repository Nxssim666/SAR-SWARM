"""The MAVLink driver against stand-in MAVSDK plugins: mappings, samples, commands."""

import asyncio
import math
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from mavsdk.asyncio.plugins.action import ActionError, ActionResult
from mavsdk.asyncio.plugins.mission import MissionError, MissionResult

from fleet_service.domain.enums import Airframe, CommandKind, FlightMode, GpsFix
from fleet_service.domain.patterns.route import RoutePoint
from fleet_service.drivers import mavlink
from fleet_service.drivers.base import DriverCommand, Outcome, RouteMission
from fleet_service.drivers.mavlink import (
    GPS_TIMEOUT_S,
    MISSION_START_RETRY_S,
    POSITION_TIMEOUT_S,
    MavlinkDriver,
    flight_mode,
    gps_fix,
    normalize_url,
)

from support import FakeClock

HOME = (47.3977, 8.5456, 488.0)


class Monotonic:
    """A monotonic clock tests move by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeTelemetry:
    """Subscriptions fed by the test through ``push``."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Any]] = {}

    def push(self, name: str, value: Any) -> None:
        self._queues.setdefault(name, asyncio.Queue()).put_nowait(value)

    def __getattr__(self, name: str) -> Any:
        topic = name.removeprefix("subscribe_")
        queue = self._queues.setdefault(topic, asyncio.Queue())

        async def subscribe() -> AsyncIterator[Any]:
            while True:
                yield await queue.get()

        return subscribe


class FakeAction:
    """Records calls; fails those named in ``failures`` with the given result."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.failures: dict[str, ActionResult] = {}

    def __getattr__(self, name: str) -> Any:
        async def call(*args: Any) -> None:
            self.calls.append((name, args))
            if name in self.failures:
                raise ActionError(self.failures[name], f"{name}()")

        return call


class FakeMission:
    """Uploads are kept and read back as sent; ``start_mission`` is refused ``refusals`` times.

    Each refusal moves ``monotonic`` on by one second, as a slow aircraft would.
    """

    def __init__(self, monotonic: "Monotonic", refusals: int, result: MissionResult) -> None:
        self.monotonic = monotonic
        self.refusals = refusals
        self.result = result
        self.starts = 0
        self.plan: Any = None

    async def set_return_to_launch_after_mission(self, enable: bool) -> None:
        del enable

    async def upload_mission(self, plan: Any) -> None:
        self.plan = plan

    async def download_mission(self) -> Any:
        return self.plan

    async def start_mission(self) -> None:
        self.starts += 1
        if self.starts <= self.refusals:
            self.monotonic.now += 1.0
            raise MissionError(self.result, "start_mission()")

    async def subscribe_mission_progress(self) -> AsyncIterator[Any]:
        await asyncio.Future()
        yield


def mode(name: str) -> Any:
    return SimpleNamespace(name=name)


def feed(telemetry: FakeTelemetry, **overrides: Any) -> None:
    """A full set of plausible values for a landed hexacopter at home."""
    values: dict[str, Any] = {
        "position": SimpleNamespace(
            latitude_deg=HOME[0],
            longitude_deg=HOME[1],
            absolute_altitude_m=HOME[2],
            relative_altitude_m=0.0,
        ),
        "heading": SimpleNamespace(heading_deg=90.0),
        "velocity_ned": SimpleNamespace(north_m_s=3.0, east_m_s=4.0, down_m_s=-1.0),
        "battery": SimpleNamespace(id=0, remaining_percent=87.0, voltage_v=24.1),
        "gps_info": SimpleNamespace(fix_type=mode("FIX_3D"), num_satellites=14),
        "flight_mode": mode("HOLD"),
        "armed": False,
        "in_air": False,
        "home": SimpleNamespace(
            latitude_deg=HOME[0], longitude_deg=HOME[1], absolute_altitude_m=HOME[2]
        ),
    } | overrides
    for name, value in values.items():
        telemetry.push(name, value)


@pytest.fixture
async def rig() -> AsyncIterator[tuple[MavlinkDriver, FakeTelemetry, FakeAction, Monotonic]]:
    monotonic = Monotonic()
    driver = MavlinkDriver("A1", 7, Airframe.MULTIROTOR_HEXA, FakeClock(), monotonic)
    telemetry, action = FakeTelemetry(), FakeAction()
    driver.bind(telemetry, action)
    yield driver, telemetry, action, monotonic
    await driver.aclose()


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.parametrize(
    ("px4", "ours"),
    [
        ("READY", FlightMode.HOLD),
        ("HOLD", FlightMode.HOLD),
        ("TAKEOFF", FlightMode.TAKEOFF),
        ("RETURN_TO_LAUNCH", FlightMode.RETURN),
        ("OFFBOARD", FlightMode.OFFBOARD),
        ("POSCTL", FlightMode.MANUAL),
        ("FOLLOW_ME", FlightMode.UNKNOWN),
    ],
)
def test_flight_modes_map_to_ours(px4: str, ours: FlightMode) -> None:
    assert flight_mode(px4) is ours


def test_fix_types_map_to_ours() -> None:
    assert gps_fix("NO_FIX") is GpsFix.NONE
    assert gps_fix("FIX_3D") is GpsFix.FIX_3D
    assert gps_fix("RTK_FIXED") is GpsFix.RTK_FIXED


@pytest.mark.parametrize(
    ("given", "normal"),
    [
        ("udp://:14550", "udpin://0.0.0.0:14550"),
        ("udp://0.0.0.0:14550", "udpin://0.0.0.0:14550"),
        (" udpin://0.0.0.0:14550", "udpin://0.0.0.0:14550"),
        ("serial:///dev/ttyUSB0:57600", "serial:///dev/ttyUSB0:57600"),
    ],
)
def test_connection_urls_have_one_spelling(given: str, normal: str) -> None:
    assert normalize_url(given) == normal


async def test_a_sample_carries_canonical_units(rig: Any) -> None:
    driver, telemetry, _, _ = rig
    feed(telemetry)
    await settle()

    sample = driver.sample()

    assert sample.source == "mavlink"
    assert (sample.latitude, sample.longitude, sample.altitude_amsl_m) == HOME
    assert sample.groundspeed_mps == pytest.approx(5.0)
    assert sample.climb_rate_mps == pytest.approx(1.0)
    assert (sample.battery_pct, sample.battery_v) == (87.0, 24.1)
    assert (sample.gps_fix, sample.satellites) == (GpsFix.FIX_3D, 14)
    assert (sample.flight_mode, sample.armed, sample.in_air) == (FlightMode.HOLD, False, False)
    assert (sample.home_latitude, sample.home_longitude) == HOME[:2]


async def test_unknown_values_stay_unknown(rig: Any) -> None:
    driver, telemetry, _, monotonic = rig
    feed(
        telemetry,
        battery=SimpleNamespace(id=0, remaining_percent=math.nan, voltage_v=math.nan),
        gps_info=SimpleNamespace(fix_type=mode("NO_FIX"), num_satellites=0),
    )
    await settle()

    no_fix = driver.sample()
    assert (no_fix.battery_pct, no_fix.battery_v) == (None, None)
    assert no_fix.latitude is None  # a position without a 3D fix is not a position

    feed(telemetry)
    await settle()
    monotonic.now += POSITION_TIMEOUT_S + 0.1  # the fix is fine, but positions stopped
    assert driver.sample().latitude is None

    monotonic.now += GPS_TIMEOUT_S  # the receiver went quiet: its last fix no longer counts
    quiet = driver.sample()
    assert (quiet.gps_fix, quiet.satellites) == (GpsFix.NONE, None)


async def test_only_new_telemetry_is_emitted(rig: Any) -> None:
    driver, telemetry, _, _ = rig
    samples: list[Any] = []
    driver.start(samples.append)
    feed(telemetry)

    await asyncio.sleep(0.5)
    emitted = len(samples)
    await asyncio.sleep(0.5)

    assert emitted >= 1
    assert len(samples) == emitted  # silence on the link: no repeated samples


async def test_commands_map_to_actions(rig: Any) -> None:
    driver, telemetry, action, _ = rig
    feed(telemetry)
    await settle()

    for kind in (CommandKind.ARM, CommandKind.RETURN_TO_LAUNCH, CommandKind.LAND):
        assert (await driver.execute(DriverCommand(kind))).outcome is Outcome.ACKED
    await driver.execute(DriverCommand(CommandKind.TAKEOFF, altitude_relative_m=25.0))

    assert [name for name, _ in action.calls] == [
        "arm",
        "return_to_launch",
        "land",
        "set_takeoff_altitude",
        "takeoff",
    ]
    assert action.calls[3][1] == (25.0,)


async def test_a_refusal_carries_the_aircraft_reason(rig: Any) -> None:
    driver, telemetry, action, _ = rig
    feed(telemetry)
    action.failures["arm"] = ActionResult.COMMAND_DENIED

    result = await driver.execute(DriverCommand(CommandKind.ARM))

    assert result.outcome is Outcome.NACKED
    assert result.reason == "The aircraft refused the command."


async def test_no_answer_is_left_to_the_pipeline_timeout(rig: Any) -> None:
    driver, _, action, _ = rig
    action.failures["hold"] = ActionResult.TIMEOUT

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(driver.execute(DriverCommand(CommandKind.HOLD)), 0.2)


async def test_commands_wait_until_the_aircraft_is_heard() -> None:
    driver = MavlinkDriver("A1", 7, Airframe.MULTIROTOR_HEXA, FakeClock())
    pending = asyncio.create_task(driver.execute(DriverCommand(CommandKind.ARM)))
    await asyncio.sleep(0.05)
    assert not pending.done()

    driver.bind(FakeTelemetry(), FakeAction())

    assert (await pending).outcome is Outcome.ACKED
    await driver.aclose()


async def test_goto_is_sent_in_amsl_and_shown_until_arrival(rig: Any) -> None:
    driver, telemetry, action, _ = rig
    feed(telemetry, in_air=True, armed=True)
    await settle()

    result = await driver.execute(
        DriverCommand(CommandKind.GOTO, altitude_relative_m=40.0, latitude=47.40, longitude=8.55)
    )

    assert result.outcome is Outcome.ACKED
    name, (latitude, longitude, amsl, yaw) = action.calls[-1]
    assert (name, latitude, longitude, amsl) == ("goto_location", 47.40, 8.55, HOME[2] + 40.0)
    assert math.isnan(yaw)
    assert driver.sample().flight_mode is FlightMode.GOTO  # PX4 reports HOLD while repositioning

    telemetry.push(
        "position",
        SimpleNamespace(
            latitude_deg=47.40,
            longitude_deg=8.55,
            absolute_altitude_m=528.0,
            relative_altitude_m=40.0,
        ),
    )
    await settle()
    assert driver.sample().flight_mode is FlightMode.HOLD


async def test_goto_needs_home(rig: Any) -> None:
    driver, telemetry, action, _ = rig
    feed(
        telemetry,
        home=SimpleNamespace(
            latitude_deg=math.nan, longitude_deg=math.nan, absolute_altitude_m=math.nan
        ),
    )
    await settle()

    result = await driver.execute(
        DriverCommand(CommandKind.GOTO, altitude_relative_m=40.0, latitude=47.40, longitude=8.55)
    )

    assert result.outcome is Outcome.NACKED
    assert action.calls == []


async def test_hold_pauses_a_goto_and_resume_sends_it_again(rig: Any) -> None:
    driver, telemetry, action, _ = rig
    feed(telemetry, in_air=True, armed=True)
    await settle()
    assert (await driver.execute(DriverCommand(CommandKind.RESUME))).outcome is Outcome.NACKED

    goto = DriverCommand(CommandKind.GOTO, altitude_relative_m=40.0, latitude=47.40, longitude=8.55)
    await driver.execute(goto)
    await driver.execute(DriverCommand(CommandKind.HOLD))
    assert driver.sample().flight_mode is FlightMode.HOLD

    resumed = await driver.execute(DriverCommand(CommandKind.RESUME))

    assert resumed.outcome is Outcome.ACKED
    assert action.calls[-1] == action.calls[0]  # the same reposition
    assert driver.sample().flight_mode is FlightMode.GOTO


async def test_a_mode_change_ends_the_goto(rig: Any) -> None:
    driver, telemetry, _, monotonic = rig
    feed(telemetry, in_air=True, armed=True)
    await settle()
    await driver.execute(
        DriverCommand(CommandKind.GOTO, altitude_relative_m=40.0, latitude=47.40, longitude=8.55)
    )

    telemetry.push("flight_mode", mode("RETURN_TO_LAUNCH"))  # e.g. a failsafe
    await settle()
    monotonic.now += 5
    assert driver.sample().flight_mode is FlightMode.RETURN
    telemetry.push("flight_mode", mode("HOLD"))
    await settle()

    assert driver.sample().flight_mode is FlightMode.HOLD


ROUTE = RouteMission("M1", (RoutePoint(47.399, 8.5456, 20.0), RoutePoint(47.400, 8.5456, 20.0)))


@pytest.mark.parametrize(
    ("refusals", "outcome", "starts"),
    [
        (0, Outcome.ACKED, 1),
        (3, Outcome.ACKED, 4),  # PX4 still checking the new mission: started once it has
        (100, Outcome.NACKED, int(MISSION_START_RETRY_S)),  # a real refusal, in the end
    ],
)
async def test_a_mission_start_waits_for_the_aircraft_to_check_the_mission(
    monkeypatch: pytest.MonkeyPatch, refusals: int, outcome: Outcome, starts: int
) -> None:
    monkeypatch.setattr(mavlink, "MISSION_START_RETRY_PERIOD_S", 0.0)
    monotonic = Monotonic()
    driver = MavlinkDriver("A1", 7, Airframe.MULTIROTOR_HEXA, FakeClock(), monotonic)
    mission = FakeMission(monotonic, refusals, MissionResult.DENIED)
    driver.bind(FakeTelemetry(), FakeAction(), mission)
    try:
        result = await driver.execute(DriverCommand(CommandKind.MISSION_START, route=ROUTE))
    finally:
        await driver.aclose()

    assert result.outcome is outcome
    assert mission.starts == starts
    if outcome is Outcome.NACKED:
        assert result.reason == "The aircraft refused the mission (DENIED)."


async def test_other_mission_refusals_are_not_retried() -> None:
    monotonic = Monotonic()
    driver = MavlinkDriver("A1", 7, Airframe.MULTIROTOR_HEXA, FakeClock(), monotonic)
    mission = FakeMission(monotonic, 1, MissionResult.NO_MISSION_AVAILABLE)
    driver.bind(FakeTelemetry(), FakeAction(), mission)
    try:
        result = await driver.execute(DriverCommand(CommandKind.MISSION_START, route=ROUTE))
    finally:
        await driver.aclose()

    assert result.outcome is Outcome.NACKED
    assert mission.starts == 1
