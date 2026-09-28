"""
The MAVLink path end to end on one machine: REST, command pipeline, MAVLink driver, the
real MAVSDK v4 binding, UDP, and minimal PX4-like vehicles (``mavlink_vehicle``).

Real time and real sockets; each test takes a few seconds. What PX4 itself does with the
commands is tested against SITL in CI (``tests/integration``, ADR 0023).
"""

import socket
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.clock import SystemClock
from fleet_service.config import Settings
from fleet_service.domain.enums import Role
from fleet_service.main import create_app
from link_support import Station, free_udp_port, until
from mavlink_vehicle import MavlinkVehicle

from support import bearer, login

LINK_TIMEOUT_S = 10.0
FLIGHT_TIMEOUT_S = 15.0


@pytest.fixture
def port() -> int:
    return free_udp_port()


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        station_name="test-station",
        data_dir=data_dir,
        mavlink_links=True,
        command_timeout_s=2.0,
        command_effect_timeout_s=8.0,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """The app on the real clock, with its loops running."""
    application = create_app(
        settings, clock=SystemClock(), passwords=fast_passwords_for_tests(), start_loops=True
    )
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def station(client: httpx.AsyncClient, user_ids: dict[Role, str], port: int) -> Station:
    del user_ids  # the users must exist before logging in
    return Station(client, bearer(await login(client, Role.SUPERVISOR.value)))


def heard(telemetry: dict[str, Any]) -> bool:
    """Every stream has arrived: fix and position, and a heartbeat's flight mode."""
    return bool(telemetry["gps_fix"] == "3d" and telemetry["flight_mode"] != "unknown")


def link(port: int, system_id: int) -> dict[str, Any]:
    return {"mavlink_connection": f"udp://:{port}", "mavlink_system_id": system_id}


async def test_aircraft_sharing_a_port_are_told_apart_by_system_id(
    station: Station, port: int
) -> None:
    first = await station.register("HX-1", **link(port, 21))
    second = await station.register("HX-2", **link(port, 22))
    silent = await station.register("HX-3", **link(port, 23))

    with (
        MavlinkVehicle(port, 21, 47.3977, 8.5456),
        MavlinkVehicle(port, 22, 47.3990, 8.5470),
    ):
        one = await station.wait_for(first, heard, LINK_TIMEOUT_S, "HX-1")
        two = await station.wait_for(second, heard, LINK_TIMEOUT_S, "HX-2")
        three = await station.aircraft(silent)

    assert one["source"] == "mavlink"
    assert one["position"]["latitude"] == pytest.approx(47.3977, abs=1e-6)
    assert two["position"]["latitude"] == pytest.approx(47.3990, abs=1e-6)
    assert one["altitude_amsl_m"] == pytest.approx(488.0, abs=0.01)
    assert one["battery_pct"] == 90
    assert one["flight_mode"] == "hold"
    assert one["armed"] is False
    assert three["link"] == "offline"


async def test_a_flight_through_the_pipeline_is_acked_and_verified(
    station: Station, port: int
) -> None:
    hexa = await station.register("HX-1", **link(port, 31))
    await station.take(hexa)

    with MavlinkVehicle(port, 31):
        await station.wait_for(hexa, heard, LINK_TIMEOUT_S, "a fix")
        steps: list[tuple[str, dict[str, Any]]] = [
            ("arm", {}),
            ("takeoff", {"altitude_relative_m": 10.0}),
            ("goto", {"target": {"latitude": 47.3986, "longitude": 8.5456}}),
            ("hold", {}),
            ("resume", {}),
            ("return_to_launch", {}),
        ]
        results = {}
        for kind, params in steps:
            outcome = await station.command(kind, [hexa], **params)
            results[kind] = await station.settled(outcome, FLIGHT_TIMEOUT_S)
        await station.wait_for(hexa, lambda t: t["in_air"] is False, FLIGHT_TIMEOUT_S, "landing")

    assert {kind: states[hexa] for kind, states in results.items()} == {
        kind: "verified" for kind, _ in steps
    }


async def test_a_refusal_reaches_the_operator_with_its_reason(station: Station, port: int) -> None:
    hexa = await station.register("HX-1", **link(port, 41))
    await station.take(hexa)

    with MavlinkVehicle(port, 41, deny=frozenset({400})):  # MAV_CMD_COMPONENT_ARM_DISARM
        await station.wait_for(hexa, heard, LINK_TIMEOUT_S, "a fix")
        outcome = await station.command("arm", [hexa])

    target = outcome["targets"][0]
    assert target["state"] == "nacked"
    assert target["reason"] == "The aircraft refused the command."


async def test_an_unanswered_command_times_out(station: Station, port: int) -> None:
    hexa = await station.register("HX-1", **link(port, 51))
    await station.take(hexa)

    with MavlinkVehicle(port, 51, silent=True):
        await station.wait_for(hexa, heard, LINK_TIMEOUT_S, "a fix")
        outcome = await station.command("arm", [hexa])

    assert outcome["targets"][0]["state"] == "timeout"


async def test_relinking_moves_the_aircraft_and_removal_frees_the_port(
    station: Station, port: int
) -> None:
    hexa = await station.register("HX-1", **link(port, 61))

    with MavlinkVehicle(port, 61, 47.3977, 8.5456), MavlinkVehicle(port, 62, 47.3990, 8.5470):
        await station.wait_for(hexa, heard, LINK_TIMEOUT_S, "sys 61")
        response = await station.client.patch(
            f"/api/v1/aircraft/{hexa}", json={"mavlink_system_id": 62}, headers=station.headers
        )
        assert response.status_code == 200, response.text
        moved = await station.wait_for(
            hexa,
            lambda t: t["position"] is not None and t["position"]["latitude"] > 47.3985,
            LINK_TIMEOUT_S,
            "sys 62",
        )
        response = await station.client.delete(f"/api/v1/aircraft/{hexa}", headers=station.headers)
        assert response.status_code == 204, response.text

    async def port_free() -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.bind(("0.0.0.0", port))  # noqa: S104 - the hub listened on all interfaces
            except OSError:
                return False
            return True

    assert moved["position"]["latitude"] == pytest.approx(47.3990, abs=1e-6)
    assert await until(port_free, 5.0, "the hub to release its port")
