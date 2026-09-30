"""
Points of interest (M4): marked by operators over the API, or reported by swarm drones as
survivor sightings (once per sighting, updated while the drone keeps seeing it).
"""

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from fleet_service.context import AppContext
from fleet_service.db.models import Alert, Poi
from fleet_service.domain.enums import (
    AlertKind,
    LinkState,
    Role,
    SwarmHealth,
    SwarmPhase,
)
from fleet_service.domain.telemetry import SurvivorSighting, SwarmState
from test_alert_engine import record, sample

from factories import BASE, aircraft, incident


@pytest.fixture
async def inc(client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]) -> dict[str, Any]:
    return await incident(client, auth[Role.SUPERVISOR])


async def test_operators_mark_confirm_and_list_points_of_interest(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    url = f"/api/v1/incidents/{inc['id']}/pois"
    body = {
        "kind": "clue",
        "position": {"latitude": BASE["latitude"] + 0.001, "longitude": BASE["longitude"]},
        "uncertainty_m": 15.0,
        "notes": "Backpack by the trail",
    }

    created = await client.post(url, json=body, headers=auth[Role.OPERATOR])
    denied = await client.post(url, json=body, headers=auth[Role.OBSERVER])
    poi = created.json()
    changed = await client.patch(
        f"/api/v1/pois/{poi['id']}", json={"status": "confirmed"}, headers=auth[Role.OPERATOR]
    )
    listed = await client.get(url, params={"status": "confirmed"}, headers=auth[Role.OBSERVER])

    assert created.status_code == 201, created.text
    assert poi["kind"] == "clue"
    assert poi["status"] == "new"
    assert poi["aircraft_id"] is None
    assert denied.status_code == 403
    assert changed.json()["status"] == "confirmed"
    assert [p["id"] for p in listed.json()["items"]] == [poi["id"]]


async def test_a_point_outside_the_operating_area_is_refused(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], inc: dict[str, Any]
) -> None:
    # Swapped coordinates land in another continent: the operating area catches it.
    response = await client.post(
        f"/api/v1/incidents/{inc['id']}/pois",
        json={"position": {"latitude": BASE["longitude"], "longitude": BASE["latitude"]}},
        headers=auth[Role.OPERATOR],
    )

    assert response.status_code == 422


def sighted(at: datetime, lat_offset: float = 0.0) -> SwarmState:
    return SwarmState(
        drone_id=3,
        phase=SwarmPhase.TRACK,
        health=SwarmHealth.OK,
        faults=frozenset(),
        mission_sequence=1,
        command_sequence=0,
        nearest_obstacle_m=None,
        survivor_sighting=SurvivorSighting(
            BASE["latitude"] + 0.002 + lat_offset, BASE["longitude"], 8.0, at
        ),
    )


async def test_a_survivor_sighting_becomes_one_point_and_one_critical_alert(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    context: AppContext,
    inc: dict[str, Any],
) -> None:
    runtime = context.runtime()
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    registered = await aircraft(client, auth[Role.SUPERVISOR], "SW-1", swarm_drone_id=3)
    drone = runtime.registry.get(registered["id"])
    assert drone is not None
    drone.sample = record(sample(registered["id"], swarm=sighted(now))).sample
    drone.link = LinkState.LIVE

    async with context.database().ops_session() as db:
        await runtime.pois.evaluate(db, now, runtime.registry)
        # The drone keeps seeing the same person, 5 m further north, 10 s later.
        assert drone.sample is not None
        drone.sample = dataclasses.replace(
            drone.sample, swarm=sighted(now + timedelta(seconds=10), 0.000045)
        )
        await runtime.pois.evaluate(db, now + timedelta(seconds=10), runtime.registry)
        pois = (await db.scalars(select(Poi))).all()
        alerts = (
            await db.scalars(select(Alert).where(Alert.kind == AlertKind.SURVIVOR_SIGHTING))
        ).all()

    assert len(pois) == 1
    assert pois[0].kind.value == "survivor_sighting"
    assert pois[0].incident_id == inc["id"]  # the only active incident
    assert pois[0].aircraft_id == registered["id"]
    assert pois[0].latitude == pytest.approx(BASE["latitude"] + 0.002045)
    assert len(alerts) == 1
    assert alerts[0].severity.value == "critical"
    assert "possible survivor" in alerts[0].message
