"""The simulated aircraft (ADR 0021): modes, commands, failsafes, determinism."""

import asyncio
import math
from typing import Any

import pytest

from fleet_service.domain.enums import Airframe, CommandKind, FlightMode, GpsFix
from fleet_service.domain.geo import GeoPoint, distance_m
from fleet_service.domain.patterns import RoutePoint
from fleet_service.drivers.base import DriverCommand, Outcome, RouteMission
from fleet_service.drivers.mock import MockFleet, MockVehicle

from support import START

ORIGIN = GeoPoint(latitude=47.3977, longitude=8.5456)
DT = 0.1


def vehicle(airframe: Airframe = Airframe.MULTIROTOR_HEXA, battery: float = 100.0) -> MockVehicle:
    return MockVehicle(
        airframe, ORIGIN, 500.0, spawn=(0.0, 0.0), battery_pct=battery, satellites=14
    )


def run(v: MockVehicle, seconds: float) -> None:
    for _ in range(round(seconds / DT)):
        v.step(DT)


def ok(v: MockVehicle, kind: CommandKind, **params: Any) -> None:
    result = v.command(DriverCommand(kind, **params))
    assert result.outcome is Outcome.ACKED, result.reason


def airborne(airframe: Airframe = Airframe.MULTIROTOR_HEXA, altitude: float = 40.0) -> MockVehicle:
    v = vehicle(airframe)
    ok(v, CommandKind.ARM)
    ok(v, CommandKind.TAKEOFF, altitude_relative_m=altitude)
    run(v, 30)
    return v


def test_takeoff_climbs_to_the_requested_altitude_then_holds() -> None:
    v = airborne(altitude=40.0)

    assert v.in_air
    assert v.mode is FlightMode.HOLD
    assert v.z == pytest.approx(40.0, abs=0.6)
    assert math.hypot(v.x, v.y) < 2.0  # a multirotor climbs vertically


def test_goto_arrives_and_holds_at_the_target() -> None:
    v = airborne()
    lat, lon = v.to_geo(300.0, 400.0)

    ok(v, CommandKind.GOTO, latitude=lat, longitude=lon, altitude_relative_m=60.0)
    run(v, 90)

    assert v.mode is FlightMode.HOLD
    assert math.hypot(v.x - 300.0, v.y - 400.0) < 2.0
    assert v.z == pytest.approx(60.0, abs=1.0)


def test_hold_pauses_a_goto_and_resume_continues_it() -> None:
    v = airborne()
    lat, lon = v.to_geo(0.0, 500.0)
    ok(v, CommandKind.GOTO, latitude=lat, longitude=lon)
    run(v, 10)

    ok(v, CommandKind.HOLD)
    paused_at = v.y
    run(v, 10)
    assert abs(v.y - paused_at) < 10.0  # brakes and stays put

    ok(v, CommandKind.RESUME)
    run(v, 90)
    assert math.hypot(v.x, v.y - 500.0) < 2.0


def test_resume_without_a_paused_goto_is_refused() -> None:
    v = airborne()

    result = v.command(DriverCommand(CommandKind.RESUME))

    assert result.outcome is Outcome.NACKED
    assert result.reason == "nothing to resume"


def test_return_to_launch_flies_home_lands_and_disarms() -> None:
    v = airborne()
    lat, lon = v.to_geo(200.0, 0.0)
    ok(v, CommandKind.GOTO, latitude=lat, longitude=lon)
    run(v, 60)

    ok(v, CommandKind.RETURN_TO_LAUNCH)
    run(v, 30)
    assert v.z >= 49.0  # climbs to the return altitude first
    run(v, 120)

    assert not v.in_air
    assert not v.armed  # auto-disarm after landing
    assert math.hypot(v.x, v.y) < 2.0


def test_fixed_wing_loiters_on_its_radius_and_never_stops() -> None:
    v = airborne(Airframe.FIXED_WING, altitude=80.0)
    run(v, 60)
    centre_x, centre_y, _ = v.anchor or (0.0, 0.0, 0.0)

    radii = []
    for _ in range(100):
        v.step(DT)
        radii.append(math.hypot(v.x - centre_x, v.y - centre_y))

    assert min(radii) == pytest.approx(60.0, abs=1.0)
    assert max(radii) == pytest.approx(60.0, abs=1.0)
    assert v.speed > 10.0


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        (CommandKind.TAKEOFF, "takeoff denied: not armed"),
        (CommandKind.HOLD, "hold denied: on the ground"),
        (CommandKind.LAND, "land denied: on the ground"),
    ],
)
def test_aircraft_refuse_commands_that_do_not_fit_their_state(
    kind: CommandKind, reason: str
) -> None:
    result = vehicle().command(DriverCommand(kind))

    assert result.outcome is Outcome.NACKED
    assert result.reason == reason


def test_disarm_is_refused_in_flight() -> None:
    result = airborne().command(DriverCommand(CommandKind.DISARM))

    assert result.reason == "disarm denied: in flight"


def test_failsafe_link_loss_returns_after_ten_seconds() -> None:
    v = airborne()
    v.link_up = False

    run(v, 9.5)
    before = v.mode
    run(v, 1.0)

    assert before is FlightMode.HOLD
    assert v.mode is FlightMode.RETURN
    assert v.last_failsafe == "data link lost: return"


def test_failsafe_gnss_loss_lands_and_hides_the_position() -> None:
    v = airborne()
    v.gps_ok = False

    run(v, 0.2)
    sample = v.sample("a1", START)

    assert v.mode is FlightMode.LAND
    assert sample.latitude is None
    assert sample.longitude is None
    assert sample.gps_fix is GpsFix.NONE


@pytest.mark.parametrize(("battery", "mode"), [(9.5, FlightMode.RETURN), (4.5, FlightMode.LAND)])
def test_failsafe_battery(battery: float, mode: FlightMode) -> None:
    v = airborne()
    v.battery_pct = battery

    v.step(DT)

    assert v.mode is mode


def test_battery_drains_over_a_realistic_endurance() -> None:
    v = airborne()
    before = v.battery_pct

    run(v, 60)

    assert before - v.battery_pct == pytest.approx(100 / 25, abs=0.2)  # 25 min endurance


def test_samples_are_in_canonical_units() -> None:
    v = airborne(altitude=40.0)
    sample = v.sample("a1", START)

    assert sample.altitude_relative_m == pytest.approx(40.0, abs=0.6)
    assert sample.altitude_amsl_m == pytest.approx(540.0, abs=0.6)
    assert sample.flight_mode is FlightMode.HOLD
    assert sample.armed is True
    assert sample.in_air is True
    assert sample.latitude is not None
    assert sample.longitude is not None
    home = GeoPoint(latitude=sample.home_latitude or 0.0, longitude=sample.home_longitude or 0.0)
    here = GeoPoint(latitude=sample.latitude, longitude=sample.longitude)
    assert distance_m(home, here) < 2.0


def test_local_and_geographic_frames_round_trip() -> None:
    v = vehicle()
    lat, lon = v.to_geo(1234.0, -567.0)

    east, north = v.to_local(lat, lon)

    assert east == pytest.approx(1234.0, abs=1e-6)
    assert north == pytest.approx(-567.0, abs=1e-6)
    assert distance_m(ORIGIN, GeoPoint(latitude=lat, longitude=lon)) == pytest.approx(
        math.hypot(1234.0, 567.0), rel=0.005
    )


def test_fleet_is_deterministic_for_a_seed() -> None:
    def fly(seed: int) -> list[tuple[float, float, float]]:
        fleet = MockFleet(ORIGIN, 500.0, seed)
        for i in range(3):
            fleet.add(f"a{i}", Airframe.MULTIROTOR_QUAD)
        for driver in fleet.drivers.values():
            driver.vehicle.command(DriverCommand(CommandKind.ARM))
            driver.vehicle.command(DriverCommand(CommandKind.TAKEOFF, altitude_relative_m=20.0))
        for _ in range(100):
            fleet.step(DT, START)
        return [(d.vehicle.x, d.vehicle.z, d.vehicle.battery_pct) for d in fleet.drivers.values()]

    assert fly(7) == fly(7)
    assert fly(7) != fly(8)  # the seed changes initial batteries


def test_fleet_spawns_on_a_grid_in_registration_order() -> None:
    fleet = MockFleet(ORIGIN, 500.0, 0)

    spawns = [fleet.add(f"a{i}", Airframe.MULTIROTOR_HEXA).vehicle.home for i in range(12)]

    assert spawns[0] == (0.0, 0.0)
    assert spawns[1] == (15.0, 0.0)
    assert spawns[10] == (0.0, 15.0)
    assert len(set(spawns)) == 12


async def test_commands_wait_while_the_link_is_down() -> None:
    fleet = MockFleet(ORIGIN, 500.0, 0)
    driver = fleet.add("a1", Airframe.MULTIROTOR_HEXA)
    driver.inject(link=False)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(driver.execute(DriverCommand(CommandKind.ARM)), timeout=0.05)

    driver.inject(link=True)
    result = await asyncio.wait_for(driver.execute(DriverCommand(CommandKind.ARM)), timeout=0.05)
    assert result.outcome is Outcome.ACKED


def test_telemetry_stops_while_the_link_is_down() -> None:
    fleet = MockFleet(ORIGIN, 500.0, 0)
    driver = fleet.add("a1", Airframe.MULTIROTOR_HEXA)
    received: list[object] = []
    driver.start(received.append)

    fleet.step(DT, START)
    driver.inject(link=False)
    fleet.step(DT, START)
    fleet.step(DT, START)

    assert len(received) == 1


def route(
    *points: tuple[float, float], altitude: float = 30.0, loiter: float | None = None
) -> RouteMission:
    return RouteMission(
        "m1", tuple(RoutePoint(lat, lon, altitude, None, loiter) for lat, lon in points)
    )


def test_a_mission_is_flown_item_by_item_and_reports_its_progress() -> None:
    v = airborne(altitude=30.0)
    a = v.to_geo(0.0, 100.0)
    b = v.to_geo(100.0, 100.0)

    ack = v.command(DriverCommand(CommandKind.MISSION_START, route=route(a, b)))
    for _ in range(100):  # 10 s
        v.step(0.1)
    halfway = v.sample("a1", START)
    for _ in range(400):
        v.step(0.1)
    done = v.sample("a1", START)

    assert ack.outcome is Outcome.ACKED
    assert halfway.flight_mode is FlightMode.MISSION
    assert halfway.mission_items == 2
    assert halfway.mission_item in (0, 1)
    assert done.mission_item == done.mission_items == 2  # PX4: the count once done
    assert done.flight_mode in (FlightMode.RETURN, FlightMode.LAND, FlightMode.HOLD)


def test_pause_holds_a_mission_and_resume_continues_from_the_same_item() -> None:
    v = airborne(altitude=30.0)
    far = v.to_geo(0.0, 1000.0)
    v.command(DriverCommand(CommandKind.MISSION_START, route=route(far)))
    for _ in range(50):
        v.step(0.1)

    paused = v.command(DriverCommand(CommandKind.MISSION_PAUSE))
    where = (v.x, v.y)
    for _ in range(50):
        v.step(0.1)
    held = math.dist(where, (v.x, v.y))
    resumed = v.command(DriverCommand(CommandKind.RESUME))
    v.step(0.1)

    assert paused.outcome is Outcome.ACKED
    assert held < 3.0
    assert resumed.outcome is Outcome.ACKED
    assert v.mode is FlightMode.MISSION
    assert v.mission_index == 0  # still flying to the same item


def test_a_start_delay_is_flown_as_a_loiter_at_the_first_item() -> None:
    v = airborne(altitude=30.0)
    here = v.to_geo(v.x, v.y)
    there = v.to_geo(0.0, 200.0)
    v.command(
        DriverCommand(
            CommandKind.MISSION_START,
            route=RouteMission(
                "m1", (RoutePoint(*here, 30.0, None, 20.0), RoutePoint(*there, 30.0))
            ),
        )
    )

    for _ in range(150):  # 15 s: still waiting
        v.step(0.1)
    waiting = v.mission_index
    for _ in range(100):  # 25 s: gone
        v.step(0.1)

    assert waiting == 0
    assert v.mission_index == 1


def test_a_mission_without_items_or_on_the_ground_is_refused() -> None:
    grounded = vehicle()

    empty = airborne(altitude=30.0).command(DriverCommand(CommandKind.MISSION_START, route=None))
    on_ground = grounded.command(
        DriverCommand(CommandKind.MISSION_START, route=route(grounded.to_geo(0.0, 10.0)))
    )

    assert empty.outcome is Outcome.NACKED
    assert on_ground.outcome is Outcome.NACKED


def test_an_airplane_flies_each_lane_on_its_line_not_diagonally() -> None:
    # Found by the M5 E2E suite: the simulated airplane accepts a waypoint 60 m early. Flying
    # straight to the next point then cut every lane of a 40 m lawnmower diagonally. Like
    # PX4's path following, it now tracks the line between waypoints.
    v = airborne(Airframe.FIXED_WING, altitude=60.0)
    lanes = [(-60.0, 40.0), (-20.0, 40.0), (20.0, 40.0)]  # east of each lane, 400 m long
    points = []
    for i, (east, _) in enumerate(lanes):
        south, north = (-200.0, 200.0) if i % 2 == 0 else (200.0, -200.0)
        points += [v.to_geo(east, south), v.to_geo(east, north)]
    ok(v, CommandKind.MISSION_START, route=route(*points, altitude=60.0))

    worst = {east: 0.0 for east, _ in lanes}
    for _ in range(3000):  # 300 s
        v.step(DT)
        if v.mode is not FlightMode.MISSION:
            break
        if -120.0 <= v.y <= 120.0:  # the middle of the lanes, where the search is
            lane = v.mission_index // 2
            if v.mission_index % 2 == 1 and lane < len(lanes):
                east = lanes[lane][0]
                worst[east] = max(worst[east], abs(v.x - east))

    assert v.mission_index == len(points)
    assert max(worst.values()) < 10.0, worst  # on its lane, 40 m from the next one
