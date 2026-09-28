"""
The ground station against PX4 itself (ADR 0023): five SIH instances from
``sim/sitl/compose.yaml``, reached over real MAVLink, driven through the REST API.

Runs only with ``SARGCS_SITL=1`` (the ``sitl`` CI workflow, Linux + Docker). The tests
share one PX4 fleet and run in file order; each leaves its aircraft landed, except the
fixed-wing (which keeps circling home) and the link-loss quad (which PX4 returns home).

    instance  system id  airframe          used by
    0-2       1-3        sihsim_hex        tracking, full flight, bulk, GNSS loss
    3         4          sihsim_airplane   fixed-wing takeoff
    4         5          sihsim_quadx      link loss (through the link emulator)
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from linkem import Impairment, LinkEmulator
from mavsdk.asyncio import ComponentType, Configuration, Mavsdk
from mavsdk.asyncio.plugins.failure import FailureAsync, FailureType, FailureUnit

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.clock import SystemClock
from fleet_service.config import Settings
from fleet_service.domain.enums import Role
from fleet_service.main import create_app
from link_support import Station, free_udp_port, until

from support import bearer, login

pytestmark = [
    pytest.mark.sitl,
    pytest.mark.skipif(
        os.environ.get("SARGCS_SITL") != "1", reason="needs PX4 SITL: set SARGCS_SITL=1"
    ),
]

GCS = "udpin://0.0.0.0:14550"  # every instance's ground station link
HOME_AMSL_M = 488.0
BOOT_TIMEOUT_S = 120.0  # containers start, EKF converges, home is set
FLIGHT_TIMEOUT_S = 90.0
HEXAS = {1: "HX-1", 2: "HX-2", 3: "HX-3"}


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        station_name="sitl",
        data_dir=data_dir,
        mavlink_links=True,
        link_stale_after_s=2.0,
        link_lost_after_s=6.0,
        command_timeout_s=5.0,
        command_effect_timeout_s=20.0,
        confirmation_ttl_s=60.0,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings, clock=SystemClock(), passwords=fast_passwords_for_tests(), start_loops=True
    )
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def station(client: httpx.AsyncClient, user_ids: dict[Role, str]) -> Station:
    del user_ids  # the users must exist before logging in
    return Station(client, bearer(await login(client, Role.SUPERVISOR.value)))


def ready(telemetry: dict[str, Any]) -> bool:
    """PX4 accepts arming once it has a 3D fix, a position and a home."""
    return (
        telemetry["gps_fix"] in ("3d", "dgps", "rtk_float", "rtk_fixed")
        and telemetry["position"] is not None
        and telemetry["home"] is not None
        and telemetry["flight_mode"] != "unknown"  # a heartbeat has been heard
    )


async def hexa_fleet(station: Station, *system_ids: int) -> dict[int, str]:
    """Register hexacopters on the shared ground station port; wait until they are ready."""
    ids = {}
    for system_id in system_ids:
        ids[system_id] = await station.register(
            HEXAS[system_id], mavlink_connection=GCS, mavlink_system_id=system_id
        )
        await station.take(ids[system_id])
    for system_id, aircraft_id in ids.items():
        await station.wait_for(aircraft_id, ready, BOOT_TIMEOUT_S, f"sys {system_id} ready")
    return ids


async def arm(station: Station, aircraft_ids: list[str]) -> None:
    """Arm, retrying while PX4's preflight checks are still settling."""
    for _ in range(5):
        outcome = await station.command("arm", aircraft_ids)
        states = await station.settled(outcome, 30.0)
        if set(states.values()) == {"verified"}:
            return
        await asyncio.sleep(3.0)
    raise AssertionError(f"arming failed: {outcome['targets']}")


async def land_all(station: Station, aircraft_ids: list[str]) -> None:
    await station.command("land", aircraft_ids)
    for aircraft_id in aircraft_ids:
        await station.wait_for(
            aircraft_id, lambda t: t["armed"] is False, FLIGHT_TIMEOUT_S, "landed and disarmed"
        )


async def test_the_fleet_is_tracked_on_one_port_by_system_id(station: Station) -> None:
    ids = {
        system_id: await station.register(
            f"AC-{system_id}",
            airframe="fixed_wing" if system_id == 4 else "multirotor_hexa",
            mavlink_connection=GCS,
            mavlink_system_id=system_id,
        )
        for system_id in range(1, 6)
    }

    seen = {
        system_id: await station.wait_for(aircraft_id, ready, BOOT_TIMEOUT_S, f"sys {system_id}")
        for system_id, aircraft_id in ids.items()
    }

    for system_id, telemetry in seen.items():
        assert telemetry["source"] == "mavlink"
        assert telemetry["altitude_amsl_m"] == pytest.approx(HOME_AMSL_M, abs=5.0)
        assert telemetry["battery_pct"] is not None
        assert telemetry["armed"] is False
        # Instance i's home is 25 m east of instance i-1's: system ids must not be mixed up.
        expected_longitude = 8.545594 + (system_id - 1) * 0.000331
        assert telemetry["position"]["longitude"] == pytest.approx(expected_longitude, abs=1e-4)


async def test_a_hexacopter_flies_a_full_tasking(station: Station) -> None:
    hexa = (await hexa_fleet(station, 1))[1]
    here = (await station.telemetry(hexa) or {})["position"]
    target = {"latitude": here["latitude"] + 0.00045, "longitude": here["longitude"]}  # 50 m N

    await arm(station, [hexa])
    takeoff = await station.command("takeoff", [hexa], altitude_relative_m=20.0)
    takeoff_states = await station.settled(takeoff, 60.0)
    await station.wait_for(
        hexa, lambda t: t["altitude_relative_m"] > 17.0, FLIGHT_TIMEOUT_S, "20 m"
    )
    goto = await station.command("goto", [hexa], target=target, altitude_relative_m=20.0)
    goto_states = await station.settled(goto, 60.0)
    arrived = await station.wait_for(
        hexa, lambda t: t["flight_mode"] == "hold", FLIGHT_TIMEOUT_S, "arrival"
    )
    hold_states = await station.settled(await station.command("hold", [hexa]), 60.0)
    rtl_states = await station.settled(await station.command("return_to_launch", [hexa]), 60.0)
    landed = await station.wait_for(
        hexa, lambda t: t["armed"] is False, 2 * FLIGHT_TIMEOUT_S, "return and disarm"
    )

    assert takeoff_states[hexa] == "verified"
    assert goto_states[hexa] == "verified"
    assert arrived["position"]["latitude"] == pytest.approx(target["latitude"], abs=5e-5)
    assert hold_states[hexa] == "verified"
    assert rtl_states[hexa] == "verified"
    assert landed["in_air"] is False


async def test_a_bulk_hold_reaches_every_aircraft(station: Station) -> None:
    ids = await hexa_fleet(station, 1, 2, 3)
    hexas = list(ids.values())

    await arm(station, hexas)
    await station.settled(await station.command("takeoff", hexas, altitude_relative_m=15.0), 60.0)
    for hexa in hexas:
        await station.wait_for(hexa, lambda t: t["in_air"] is True, FLIGHT_TIMEOUT_S, "airborne")
    hold = await station.command("hold", hexas)
    states = await station.settled(hold, 60.0)
    await land_all(station, hexas)

    assert hold["confirmation_required"] is True  # bulk commands are confirmed
    assert states == dict.fromkeys(hexas, "verified")


async def test_a_fixed_wing_takes_off_and_returns(station: Station) -> None:
    plane = await station.register(
        "FW-1", airframe="fixed_wing", mavlink_connection=GCS, mavlink_system_id=4
    )
    await station.take(plane)
    await station.wait_for(plane, ready, BOOT_TIMEOUT_S, "plane ready")

    await arm(station, [plane])
    takeoff = await station.command("takeoff", [plane], altitude_relative_m=40.0)
    assert takeoff["targets"][0]["state"] == "acked", takeoff["targets"]
    # SIH's airplane climbs slowly after a launch-style takeoff (ADR 0023): ~10 m in 50 s.
    airborne = await station.wait_for(
        plane,
        lambda t: t["in_air"] is True and (t["altitude_relative_m"] or 0) > 10.0,
        2 * FLIGHT_TIMEOUT_S,
        "climb-out",
    )
    rtl = await station.settled(await station.command("return_to_launch", [plane]), 60.0)

    assert (await station.settled(takeoff, 60.0))[plane] == "verified"
    assert airborne["flight_mode"] in ("takeoff", "hold")
    assert rtl[plane] == "verified"


async def test_a_lost_link_raises_alerts_and_px4_returns_on_its_own(station: Station) -> None:
    # Only this path reaches instance 4: its onboard link (14544) through the emulator. No
    # hub listens on 14550 during this test, so PX4 hears no other ground station.
    port = free_udp_port()
    async with LinkEmulator(("127.0.0.1", 14544), ("127.0.0.1", port)) as link:
        quad = await station.register(
            "QD-1", mavlink_connection=f"udpin://0.0.0.0:{port}", mavlink_system_id=5
        )
        await station.take(quad)
        await station.wait_for(quad, ready, BOOT_TIMEOUT_S, "quad ready")
        await arm(station, [quad])
        await station.command("takeoff", [quad], altitude_relative_m=15.0)
        await station.wait_for(
            quad, lambda t: t["altitude_relative_m"] > 12.0, FLIGHT_TIMEOUT_S, "15 m"
        )

        link.impairment = Impairment(blackout=True)

        async def alerts(kind: str) -> set[str] | None:
            active = await station.active_alerts(quad)
            return active if kind in active else None

        stale = await until(lambda: alerts("link_stale"), 10.0, "link_stale")
        lost = await until(lambda: alerts("link_lost"), 15.0, "link_lost")
        await asyncio.sleep(8.0)  # PX4: COM_DL_LOSS_T is 5 s
        link.impairment = Impairment()
        back = await station.wait_for(
            quad, lambda t: t["flight_mode"] in ("return", "land"), 20.0, "link back"
        )
        await station.wait_for(
            quad, lambda t: t["armed"] is False, 2 * FLIGHT_TIMEOUT_S, "landed at home"
        )

    assert "link_stale" in stale
    assert "link_lost" in lost
    assert back["flight_mode"] in ("return", "land")  # PX4 decided, not the ground station


async def test_gnss_loss_raises_an_alert(station: Station) -> None:
    hexa = (await hexa_fleet(station, 1))[1]
    await arm(station, [hexa])
    await station.command("takeoff", [hexa], altitude_relative_m=15.0)
    await station.wait_for(hexa, lambda t: t["altitude_relative_m"] > 12.0, FLIGHT_TIMEOUT_S, "up")

    # Fault injection is a test tool, not a station feature: a separate MAVSDK instance on
    # instance 0's onboard port sends MAV_CMD_INJECT_FAILURE (needs SYS_FAILURE_EN=1).
    injector = Mavsdk(Configuration.create_with_component_type(ComponentType.COMPANION_COMPUTER))
    try:
        await injector.add_any_connection("udpin://0.0.0.0:14540")
        system = await until(injector.first_autopilot, 20.0, "instance 0 on 14540")
        failure = FailureAsync(system)
        await failure.inject(FailureUnit.SENSOR_GPS, FailureType.OFF, 0)
        blind = await station.wait_for(
            hexa, lambda t: t["gps_fix"] == "none", 30.0, "the fix to go"
        )
        alerts = await until(lambda: _with(station, hexa, "gps_lost"), 10.0, "the gps_lost alert")
        await failure.inject(FailureUnit.SENSOR_GPS, FailureType.OK, 0)
        await station.wait_for(hexa, ready, 60.0, "the fix to return")
        del failure, system
    finally:
        injector.destroy()
    await land_all(station, [hexa])

    assert blind["position"] is None  # no fix: no position, never a stale one
    assert "gps_lost" in alerts


async def _with(station: Station, aircraft_id: str, kind: str) -> set[str] | None:
    active = await station.active_alerts(aircraft_id)
    return active if kind in active else None
