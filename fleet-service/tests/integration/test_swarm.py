"""
The ground station tasks a swarm through the real bridge (ADR 0024, ADR 0026): three
simulated swarm_sar drones (the onboard controller, ``sim/swarm/swarm_sim.py``) on ROS 2,
``sar_gcs_bridge``, NATS, and the fleet service's swarm link, driven over REST.

Runs only with ``SARGCS_SWARM=1`` (the ``swarm`` CI workflow, which starts
``sim/swarm/compose.yaml``). The tests share the swarm and run in file order.
"""

import asyncio
import math
import os
from pathlib import Path
from typing import Any

import pytest

from fleet_service.config import Settings
from link_support import Station, until

import factories

pytestmark = [
    pytest.mark.swarm,
    pytest.mark.skipif(
        os.environ.get("SARGCS_SWARM") != "1", reason="needs the swarm: set SARGCS_SWARM=1"
    ),
]

NATS_URL = os.environ.get("SARGCS_SWARM_NATS", "nats://127.0.0.1:4222")
COMPOSE = Path(__file__).resolve().parents[3] / "sim" / "swarm" / "compose.yaml"
ORIGIN = (47.397742, 8.545594)  # the simulator's site (PX4's default home)
DRONES = (0, 1, 2)
HEARD_TIMEOUT_S = 120.0  # the containers start, DDS discovers, the bridge connects
EFFECT_TIMEOUT_S = 30.0


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        station_name="swarm",
        data_dir=data_dir,
        mavlink_links=False,
        nats_url=NATS_URL,
        link_stale_after_s=2.0,
        link_lost_after_s=6.0,
        command_timeout_s=5.0,
        command_effect_timeout_s=EFFECT_TIMEOUT_S,
        confirmation_ttl_s=60.0,
    )


def heard(telemetry: dict[str, Any]) -> bool:
    return telemetry["swarm"] is not None and telemetry["position"] is not None


def metres_from_origin(telemetry: dict[str, Any]) -> float:
    lat, lon = telemetry["position"]["latitude"], telemetry["position"]["longitude"]
    north = (lat - ORIGIN[0]) * 111_195.0
    east = (lon - ORIGIN[1]) * 111_195.0 * math.cos(math.radians(ORIGIN[0]))
    return math.hypot(north, east)


async def swarm(station: Station) -> list[str]:
    ids = []
    for drone_id in DRONES:
        aircraft_id = await station.register(f"SW-{drone_id}", swarm_drone_id=drone_id)
        await station.take(aircraft_id)
        ids.append(aircraft_id)
    for aircraft_id in ids:
        await station.wait_for(aircraft_id, heard, HEARD_TIMEOUT_S, "the drone's state")
    return ids


async def mission_for(station: Station, aircraft_ids: list[str]) -> str:
    """A 40 m square 20-60 m north of the site, at the drones' 4 m (their altitude limit)."""
    client, headers = station.client, station.headers
    base = {"latitude": ORIGIN[0], "longitude": ORIGIN[1]}
    incident = await factories.incident(client, headers, base=base)
    lat, lon = ORIGIN[0] + 40.0 / 111_195.0, ORIGIN[1]
    area = await factories.search_area(
        client, headers, incident["id"], geometry=factories.square(lat, lon, half=0.00018)
    )
    mission = await factories.mission(
        client,
        headers,
        incident["id"],
        kind="swarm_area",
        search_area_id=area["id"],
        default_altitude_relative_m=4.0,
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


async def test_the_swarm_is_tracked_through_the_bridge(station: Station) -> None:
    ids = await swarm(station)

    for aircraft_id in ids:
        telemetry = await station.telemetry(aircraft_id)
        assert telemetry is not None
        assert telemetry["source"] == "swarm"
        assert metres_from_origin(telemetry) < 100.0
        assert telemetry["heading_deg"] is not None
        assert 0.0 <= telemetry["heading_deg"] < 360.0
        assert telemetry["groundspeed_mps"] is not None
        # DroneState carries none of these: unknown (ADR 0002, S7).
        assert telemetry["altitude_relative_m"] is None
        assert telemetry["battery_pct"] is None
        assert telemetry["gps_fix"] is None


async def test_the_swarm_accepts_an_area_mission_and_a_hold(station: Station) -> None:
    ids = await swarm(station)
    mission_id = await mission_for(station, ids)

    started = await station.command("mission_start", ids, mission_id=mission_id)
    assert set((await station.settled(started, EFFECT_TIMEOUT_S + 10)).values()) == {"verified"}
    mission = await station.client.get(f"/api/v1/missions/{mission_id}", headers=station.headers)
    assert mission.json()["status"] == "active"

    held = await station.command("hold", ids)
    assert set((await station.settled(held, EFFECT_TIMEOUT_S + 10)).values()) == {"verified"}
    for aircraft_id in ids:
        telemetry = await station.telemetry(aircraft_id)
        assert telemetry is not None
        assert telemetry["swarm"]["phase"] == "hold"

    resumed = await station.command("resume", ids)
    assert set((await station.settled(resumed, EFFECT_TIMEOUT_S + 10)).values()) == {"verified"}


async def test_the_link_recovers_after_a_nats_restart(station: Station) -> None:
    ids = await swarm(station)

    restart = await asyncio.create_subprocess_exec(
        "docker", "compose", "-f", str(COMPOSE), "restart", "nats"
    )
    assert await asyncio.wait_for(restart.wait(), 60.0) == 0

    async def all_live_again() -> bool:
        states = [await station.aircraft(a) for a in ids]
        return all(s["link"] == "live" for s in states)

    await until(all_live_again, 60.0, "every drone live again after the NATS restart")
    held = await station.command("hold", ids)
    assert set((await station.settled(held, EFFECT_TIMEOUT_S + 10)).values()) == {"verified"}
