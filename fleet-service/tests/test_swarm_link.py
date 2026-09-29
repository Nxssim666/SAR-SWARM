"""
The swarm link end to end on one machine (ADR 0024): REST, command pipeline, swarm
driver, NATS (a real nats-server) and a fake bridge that speaks the wire contract.

Real time; each test takes a few seconds. The real bridge against the onboard swarm runs
in the ``swarm`` CI workflow (``tests/integration/test_swarm.py``).
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.clock import SystemClock
from fleet_service.config import Settings
from fleet_service.domain.enums import Role, SwarmFault
from fleet_service.main import create_app
from link_support import Station, until
from nats_support import FakeBridge, NatsServer, fake_bridge, free_tcp_port, require_nats_server

import factories
from support import bearer, login

LINK_TIMEOUT_S = 10.0


@pytest.fixture
def nats_server() -> Iterator[NatsServer]:
    server = NatsServer(require_nats_server(), free_tcp_port())
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def settings(data_dir: Path, nats_server: NatsServer) -> Settings:
    return Settings(
        station_name="test-station",
        data_dir=data_dir,
        mavlink_links=False,
        nats_url=nats_server.url,
        link_stale_after_s=1.5,
        link_lost_after_s=4.0,
        command_timeout_s=3.0,
        command_effect_timeout_s=5.0,
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
async def station(client: httpx.AsyncClient, user_ids: dict[Role, str]) -> Station:
    del user_ids  # the users must exist before logging in
    return Station(client, bearer(await login(client, Role.SUPERVISOR.value)))


@pytest.fixture
async def bridge(nats_server: NatsServer) -> AsyncIterator[FakeBridge]:
    async with fake_bridge(nats_server.url) as running:
        yield running


def heard(telemetry: dict[str, Any]) -> bool:
    return telemetry["swarm"] is not None


async def swarm_fleet(station: Station, bridge: FakeBridge, *drone_ids: int) -> list[str]:
    """Register swarm aircraft, take control, and wait until each is heard."""
    ids = []
    for drone_id in drone_ids:
        bridge.add(drone_id)
        aircraft_id = await station.register(f"SW-{drone_id}", swarm_drone_id=drone_id)
        await station.take(aircraft_id)
        ids.append(aircraft_id)
    for aircraft_id in ids:
        await station.wait_for(aircraft_id, heard, LINK_TIMEOUT_S, "swarm status")
    return ids


async def planned_swarm_mission(station: Station, aircraft_ids: list[str]) -> str:
    """An active incident, a search area and a planned swarm mission tasking the aircraft."""
    client, headers = station.client, station.headers
    incident = await factories.incident(client, headers)
    area = await factories.search_area(client, headers, incident["id"])
    mission = await factories.mission(
        client,
        headers,
        incident["id"],
        kind="swarm_area",
        search_area_id=area["id"],
        default_altitude_relative_m=30.0,
    )
    for aircraft_id in aircraft_ids:
        await factories.create(
            client, "tasks", headers, {"mission_id": mission["id"], "aircraft_id": aircraft_id}
        )
    response = await client.patch(
        f"/api/v1/missions/{mission['id']}", json={"status": "planned"}, headers=headers
    )
    assert response.status_code == 200, response.text
    mission_id: str = mission["id"]
    return mission_id


async def test_a_drone_state_becomes_the_aircraft_s_telemetry(
    station: Station, bridge: FakeBridge
) -> None:
    [aircraft_id] = await swarm_fleet(station, bridge, 7)

    telemetry = await station.telemetry(aircraft_id)

    assert telemetry is not None
    assert telemetry["source"] == "swarm"
    assert telemetry["position"] == {"latitude": 47.3977, "longitude": 8.5456}
    assert telemetry["heading_deg"] == 90.0
    assert telemetry["groundspeed_mps"] == 2.5
    # The companion does not report these: unknown, never a plausible default (ADR 0002, S7).
    for unknown in ("altitude_amsl_m", "altitude_relative_m", "battery_pct", "gps_fix", "armed"):
        assert telemetry[unknown] is None, unknown
    assert telemetry["flight_mode"] == "unknown"
    assert telemetry["swarm"]["drone_id"] == 7
    assert telemetry["swarm"]["phase"] == "standby"


async def test_a_bulk_hold_is_one_swarm_command_acked_and_verified(
    station: Station, bridge: FakeBridge
) -> None:
    ids = await swarm_fleet(station, bridge, 1, 2)

    outcome = await station.command("hold", ids)
    states = await station.settled(outcome, 10.0)

    assert set(states.values()) == {"verified"}, states
    assert [(c.kind, c.drone_ids) for c in bridge.commands] == [("hold", [1, 2])]


async def test_resume_is_verified_by_the_swarm_phase(station: Station, bridge: FakeBridge) -> None:
    [aircraft_id] = await swarm_fleet(station, bridge, 3)
    await station.settled(await station.command("hold", [aircraft_id]), 10.0)
    await station.wait_for(aircraft_id, lambda t: t["swarm"]["phase"] == "hold", 5.0, "hold")

    states = await station.settled(await station.command("resume", [aircraft_id]), 10.0)

    assert states == {aircraft_id: "verified"}


async def test_a_refusal_by_the_bridge_is_a_nack_with_its_reason(
    station: Station, bridge: FakeBridge
) -> None:
    [aircraft_id] = await swarm_fleet(station, bridge, 4)
    bridge.refuse = "drone_ids: 4 is not a known drone"

    outcome = await station.command("hold", [aircraft_id])

    [target] = outcome["targets"]
    assert target["state"] == "nacked"
    assert "not a known drone" in target["reason"]


async def test_no_reply_from_the_bridge_is_a_timeout_never_an_ack(
    station: Station, bridge: FakeBridge
) -> None:
    [aircraft_id] = await swarm_fleet(station, bridge, 5)
    bridge.silent = True

    outcome = await station.command("land", [aircraft_id])

    assert [t["state"] for t in outcome["targets"]] == ["timeout"]


async def test_a_swarm_mission_start_is_confirmed_sent_once_and_activates_the_mission(
    station: Station, bridge: FakeBridge
) -> None:
    ids = await swarm_fleet(station, bridge, 1, 2, 3)
    mission_id = await planned_swarm_mission(station, ids)

    outcome = await station.command("mission_start", ids, mission_id=mission_id)
    states = await station.settled(outcome, 10.0)

    assert set(states.values()) == {"verified"}, states
    [sent] = bridge.missions  # one request for the three drones
    assert sent.mission_id == mission_id
    assert sent.altitude_relative_m == 30.0
    assert len(sent.area) == 4  # the GeoJSON ring's closing vertex is dropped
    assert sent.origin.latitude == pytest.approx(factories.BASE["latitude"], abs=1e-6)
    assert sent.origin.longitude == pytest.approx(factories.BASE["longitude"], abs=1e-6)
    mission = await station.client.get(f"/api/v1/missions/{mission_id}", headers=station.headers)
    assert mission.json()["status"] == "active"


async def test_a_mission_the_drones_reject_is_nacked(station: Station, bridge: FakeBridge) -> None:
    ids = await swarm_fleet(station, bridge, 1)
    mission_id = await planned_swarm_mission(station, ids)
    bridge.reject_missions = True

    outcome = await station.command("mission_start", ids, mission_id=mission_id)

    [target] = outcome["targets"]
    assert target["state"] == "nacked", target
    assert "rejected" in target["reason"]
    assert SwarmFault.MISSION_REJECTED in bridge.drones[1].faults


async def test_a_swarm_mission_must_go_to_every_swarm_aircraft(
    station: Station, bridge: FakeBridge
) -> None:
    ids = await swarm_fleet(station, bridge, 1, 2)
    mission_id = await planned_swarm_mission(station, ids[:1])

    outcome = await station.command("mission_start", ids[:1], mission_id=mission_id)

    assert outcome["state"] == "rejected"
    assert outcome["targets"][0]["reason_code"] == "swarm-mission-partial"
    assert bridge.missions == []


async def test_the_link_survives_a_nats_restart(
    station: Station, bridge: FakeBridge, nats_server: NatsServer
) -> None:
    [aircraft_id] = await swarm_fleet(station, bridge, 6)

    nats_server.stop()

    async def degraded() -> str | None:
        link: str = (await station.aircraft(aircraft_id))["link"]
        return link if link in ("stale", "lost") else None

    await until(degraded, LINK_TIMEOUT_S, "the link to go stale")
    outcome = await station.command("hold", [aircraft_id])  # safe to try on a degraded link
    assert [t["state"] for t in outcome["targets"]] == ["timeout"]  # not sent: no answer

    nats_server.start()
    await station.wait_for(aircraft_id, heard, 20.0, "states again after the restart")
    states = await station.settled(await station.command("hold", [aircraft_id]), 10.0)
    assert states == {aircraft_id: "verified"}
