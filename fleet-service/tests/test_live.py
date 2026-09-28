"""Live state, link states, alerts, telemetry history and fault injection (simulation mode)."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.domain.enums import Role
from live_support import Sim, confirmed, register, take

from support import FakeClock


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(station_name="test-station", data_dir=data_dir, simulation=True)


@pytest.fixture
def sim(app: FastAPI, clock: FakeClock) -> Sim:
    context: AppContext = app.state.context
    return Sim(context.runtime(), clock)


@pytest.fixture
async def hexa(client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim) -> str:
    identifier = await register(client, auth[Role.SUPERVISOR], "HX-1")
    await take(client, auth[Role.OPERATOR], identifier)
    await sim.fly(1)
    return identifier


async def fly_up(
    client: httpx.AsyncClient, headers: dict[str, str], sim: Sim, aircraft_id: str
) -> None:
    await confirmed(client, headers, "arm", [aircraft_id])
    await sim.fly(0.5)
    await confirmed(client, headers, "takeoff", [aircraft_id], altitude_relative_m=30.0)
    await sim.fly(15)


async def active_alerts(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> dict[str, dict[str, object]]:
    response = await client.get("/api/v1/alerts", params={"state": "active"}, headers=headers)
    return {a["kind"]: a for a in response.json()["items"]}


def inject(sim: Sim, aircraft_id: str, **faults: object) -> None:
    assert sim.runtime.simulator is not None
    sim.runtime.simulator.drivers[aircraft_id].inject(**faults)  # type: ignore[arg-type]


async def test_fleet_state_shows_simulation_and_live_telemetry(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], hexa: str
) -> None:
    response = await client.get("/api/v1/fleet/state", headers=auth[Role.OBSERVER])

    body = response.json()
    assert body["simulation"] is True
    aircraft = body["aircraft"][0]
    assert aircraft["callsign"] == "HX-1"
    assert aircraft["link"] == "live"
    telemetry = aircraft["telemetry"]
    assert telemetry["source"] == "mock"
    assert telemetry["flight_mode"] == "hold"
    assert telemetry["in_air"] is False
    assert telemetry["gps_fix"] == "3d"
    assert telemetry["position"]["latitude"] == pytest.approx(47.3977, abs=1e-3)


async def test_new_aircraft_are_offline_until_heard(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    await register(client, auth[Role.SUPERVISOR], "NEW-1")

    aircraft = (await client.get("/api/v1/fleet/state", headers=auth[Role.OBSERVER])).json()[
        "aircraft"
    ]

    assert aircraft[0]["link"] == "offline"
    assert aircraft[0]["telemetry"] is None


async def test_link_goes_stale_then_lost_then_live_again_with_alerts(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], hexa: str, sim: Sim
) -> None:
    inject(sim, hexa, link=False)

    await sim.fly(4)
    stale = await active_alerts(client, auth[Role.OBSERVER])
    await sim.fly(12)
    lost = await active_alerts(client, auth[Role.OBSERVER])
    inject(sim, hexa, link=True)
    await sim.fly(1)
    back = await active_alerts(client, auth[Role.OBSERVER])

    assert set(stale) == {"link_stale"}
    assert set(lost) == {"link_lost"}
    assert lost["link_lost"]["severity"] == "critical"
    assert back == {}


async def test_battery_alerts_follow_the_thresholds(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], hexa: str, sim: Sim
) -> None:
    inject(sim, hexa, battery_pct=25.0)
    await sim.fly(0.5)
    low = await active_alerts(client, auth[Role.OBSERVER])
    inject(sim, hexa, battery_pct=12.0)
    await sim.fly(0.5)
    critical = await active_alerts(client, auth[Role.OBSERVER])

    assert set(low) == {"battery_low"}
    assert set(critical) == {"battery_critical"}


async def test_gnss_loss_in_flight_hides_the_position_and_alerts(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], hexa: str, sim: Sim
) -> None:
    await fly_up(client, auth[Role.OPERATOR], sim, hexa)

    inject(sim, hexa, gps=False)
    await sim.fly(1)

    aircraft = (await client.get("/api/v1/fleet/state", headers=auth[Role.OBSERVER])).json()[
        "aircraft"
    ][0]
    alerts = await active_alerts(client, auth[Role.OBSERVER])
    assert aircraft["telemetry"]["position"] is None  # unknown, never a stale guess
    assert aircraft["telemetry"]["gps_fix"] == "none"
    assert aircraft["telemetry"]["flight_mode"] == "land"  # the aircraft's own failsafe
    assert alerts["gps_lost"]["severity"] == "critical"


async def test_acknowledging_condition_and_event_alerts(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], hexa: str, sim: Sim
) -> None:
    inject(sim, hexa, battery_pct=25.0)
    await sim.fly(0.5)
    alert = (await active_alerts(client, auth[Role.OBSERVER]))["battery_low"]

    by_observer = await client.post(
        f"/api/v1/alerts/{alert['id']}/acknowledge", headers=auth[Role.OBSERVER]
    )
    acked = await client.post(
        f"/api/v1/alerts/{alert['id']}/acknowledge", headers=auth[Role.OPERATOR]
    )
    twice = await client.post(
        f"/api/v1/alerts/{alert['id']}/acknowledge", headers=auth[Role.OPERATOR]
    )
    inject(sim, hexa, battery_pct=90.0)
    await sim.fly(0.5)
    history = await client.get("/api/v1/alerts", headers=auth[Role.OBSERVER])

    assert by_observer.status_code == 403
    assert acked.json()["state"] == "acknowledged"  # the condition still holds
    assert acked.json()["acknowledged_by"] is not None
    assert twice.status_code == 409
    assert history.json()["items"][0]["state"] == "cleared"  # cleared once the battery recovered


async def test_telemetry_history_is_recorded_once_per_interval(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], hexa: str, sim: Sim
) -> None:
    for _ in range(5):
        await sim.fly(1)
        await sim.runtime.record()

    response = await client.get(f"/api/v1/aircraft/{hexa}/telemetry", headers=auth[Role.OBSERVER])
    limited = await client.get(
        f"/api/v1/aircraft/{hexa}/telemetry", params={"limit": 2}, headers=auth[Role.OBSERVER]
    )

    samples = response.json()["samples"]
    assert len(samples) == 5
    assert samples[0]["ts"] < samples[-1]["ts"]
    assert samples[0]["gps_fix"] == "3d"
    assert samples[0]["in_air"] is False
    assert limited.json()["truncated"] is True


async def test_fault_injection_is_audited(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], hexa: str
) -> None:
    response = await client.post(
        f"/api/v1/simulation/aircraft/{hexa}/faults",
        json={"gps": False},
        headers=auth[Role.SUPERVISOR],
    )
    empty = await client.post(
        f"/api/v1/simulation/aircraft/{hexa}/faults", json={}, headers=auth[Role.SUPERVISOR]
    )
    audit = await client.get(
        "/api/v1/audit", params={"action": "simulation."}, headers=auth[Role.SUPERVISOR]
    )

    assert response.status_code == 200
    assert empty.status_code == 422
    assert audit.json()["items"][0]["details"] == {"gps": False}


async def test_deleted_aircraft_leave_the_live_state(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    identifier = await register(client, auth[Role.SUPERVISOR], "TMP-1")
    await sim.fly(0.5)

    deleted = await client.delete(f"/api/v1/aircraft/{identifier}", headers=auth[Role.SUPERVISOR])
    state = await client.get("/api/v1/fleet/state", headers=auth[Role.OBSERVER])

    assert deleted.status_code == 204
    assert state.json()["aircraft"] == []
    assert sim.runtime.simulator is not None
    assert identifier not in sim.runtime.simulator.drivers
