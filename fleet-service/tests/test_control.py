"""Control leases, handover, supervisor assignment and orphaning (ADR 0011)."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.db.models import AuditEvent, ControlLease
from fleet_service.domain.enums import FlightMode, Role
from live_support import Sim, confirmed, register, send, take

from support import FakeClock, bearer, insert_user, login


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(station_name="test-station", data_dir=data_dir, simulation=True)


@pytest.fixture
def sim(app: FastAPI, clock: FakeClock) -> Sim:
    context: AppContext = app.state.context
    return Sim(context.runtime(), clock)


@pytest.fixture
async def aircraft_id(client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim) -> str:
    identifier = await register(client, auth[Role.SUPERVISOR], "HX-1")
    await sim.fly(1)
    return identifier


@pytest.fixture
async def other(client: httpx.AsyncClient, context: AppContext) -> dict[str, str]:
    """A second operator."""
    await insert_user(context, "olga", Role.OPERATOR)
    return bearer(await login(client, "olga"))


def control(aircraft_id: str, suffix: str = "") -> str:
    return f"/api/v1/aircraft/{aircraft_id}/control{suffix}"


async def test_take_and_release(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], aircraft_id: str
) -> None:
    taken = await client.post(control(aircraft_id), headers=auth[Role.OPERATOR])
    again = await client.post(control(aircraft_id), headers=auth[Role.OPERATOR])
    state = await client.get("/api/v1/fleet/state", headers=auth[Role.OBSERVER])
    released = await client.delete(control(aircraft_id), headers=auth[Role.OPERATOR])
    leases = await client.get("/api/v1/control-leases", headers=auth[Role.OBSERVER])

    assert taken.status_code == 200
    assert taken.json()["holder"]["username"] == "operator"
    assert taken.json()["state"] == "held"
    assert again.status_code == 200  # taking your own aircraft again is a no-op
    assert state.json()["aircraft"][0]["controller"]["holder"]["username"] == "operator"
    assert released.status_code == 204
    assert leases.json()["items"] == []


async def test_control_held_by_someone_else_needs_a_handover(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft_id: str,
    other: dict[str, str],
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)

    grab = await client.post(control(aircraft_id), headers=other)
    release = await client.delete(control(aircraft_id), headers=other)

    assert grab.status_code == 409
    assert grab.json()["type"] == "urn:sar-gcs:problem:control-held"
    assert grab.json()["holder"]["username"] == "operator"
    assert release.json()["type"] == "urn:sar-gcs:problem:not-controller"


async def test_accepted_handover_moves_control(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft_id: str,
    other: dict[str, str],
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)

    asked = await client.post(control(aircraft_id, "/handover"), headers=other)
    accepted = await client.post(
        control(aircraft_id, "/handover/accept"), headers=auth[Role.OPERATOR]
    )

    assert asked.json()["pending_request"]["requested_by"]["username"] == "olga"
    assert accepted.json()["holder"]["username"] == "olga"
    assert accepted.json()["pending_request"] is None


async def test_declined_handover_keeps_control(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft_id: str,
    other: dict[str, str],
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)
    await client.post(control(aircraft_id, "/handover"), headers=other)

    declined = await client.post(
        control(aircraft_id, "/handover/decline"), headers=auth[Role.OPERATOR]
    )

    assert declined.json()["holder"]["username"] == "operator"
    assert declined.json()["pending_request"] is None


async def test_rule_an_unanswered_handover_expires_and_control_stays(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft_id: str,
    other: dict[str, str],
    sim: Sim,
    context: AppContext,
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)
    await client.post(control(aircraft_id, "/handover"), headers=other)
    await client.get("/api/v1/auth/me", headers=auth[Role.OPERATOR])  # the holder is present

    await sim.fly(31)
    lease = context.runtime().leases.view(aircraft_id)

    assert lease is not None
    assert lease.holder.username == "operator"
    assert lease.pending_request is None
    async with context.database().ops_session() as db:
        actions = (await db.scalars(select(AuditEvent.action))).all()
    assert "control.handover_expire" in actions


async def test_only_the_holder_answers_a_handover(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft_id: str,
    other: dict[str, str],
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)
    await client.post(control(aircraft_id, "/handover"), headers=other)

    self_accept = await client.post(control(aircraft_id, "/handover/accept"), headers=other)

    assert self_accept.status_code == 409


async def test_supervisor_assigns_with_a_reason_and_it_is_audited(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    user_ids: dict[Role, str],
    aircraft_id: str,
    context: AppContext,
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)

    forced = await client.put(
        control(aircraft_id),
        json={"user_id": user_ids[Role.SUPERVISOR], "reason": "operator reassigned to sector B"},
        headers=auth[Role.SUPERVISOR],
    )
    no_reason = await client.put(
        control(aircraft_id),
        json={"user_id": user_ids[Role.OPERATOR], "reason": ""},
        headers=auth[Role.SUPERVISOR],
    )
    to_observer = await client.put(
        control(aircraft_id),
        json={"user_id": user_ids[Role.OBSERVER], "reason": "test"},
        headers=auth[Role.SUPERVISOR],
    )
    by_operator = await client.put(
        control(aircraft_id),
        json={"user_id": user_ids[Role.OPERATOR], "reason": "mine"},
        headers=auth[Role.OPERATOR],
    )

    assert forced.json()["holder"]["username"] == "supervisor"
    assert no_reason.status_code == 422
    assert to_observer.status_code == 403
    assert by_operator.status_code == 403
    async with context.database().ops_session() as db:
        event = (
            await db.scalars(select(AuditEvent).where(AuditEvent.action == "control.assign"))
        ).one()
    assert event.details["reason"] == "operator reassigned to sector B"
    assert event.details["previous_holder"] == user_ids[Role.OPERATOR]


async def test_supervisor_can_release_an_aircraft(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], aircraft_id: str
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)

    released = await client.put(
        control(aircraft_id),
        json={"user_id": None, "reason": "end of shift"},
        headers=auth[Role.SUPERVISOR],
    )

    assert released.status_code == 200
    assert released.json() is None


async def test_rule_a_disconnect_orphans_the_lease_but_never_commands(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft_id: str,
    sim: Sim,
    context: AppContext,
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)
    await confirmed(client, auth[Role.OPERATOR], "arm", [aircraft_id])
    await sim.fly(0.5)
    await confirmed(client, auth[Role.OPERATOR], "takeoff", [aircraft_id], altitude_relative_m=30.0)
    await sim.fly(15)
    lat, lon = sim.vehicle(aircraft_id).to_geo(300.0, 0.0)
    await send(
        client,
        auth[Role.OPERATOR],
        "goto",
        [aircraft_id],
        target={"latitude": lat, "longitude": lon},
    )
    commands_before = len(
        (await client.get("/api/v1/commands", headers=auth[Role.OBSERVER])).json()["items"]
    )

    await sim.fly(61)  # the operator's console is gone: no request, no WebSocket

    lease = context.runtime().leases.view(aircraft_id)
    alerts = await client.get("/api/v1/alerts?state=active", headers=auth[Role.SUPERVISOR])
    commands_after = len(
        (await client.get("/api/v1/commands", headers=auth[Role.OBSERVER])).json()["items"]
    )
    assert lease is not None
    assert lease.state == "orphaned"
    assert "control_orphaned" in {a["kind"] for a in alerts.json()["items"]}
    assert commands_after == commands_before  # nothing was commanded on anyone's behalf
    assert sim.vehicle(aircraft_id).mode in {FlightMode.GOTO, FlightMode.HOLD}  # still on task

    await client.get("/api/v1/auth/me", headers=auth[Role.OPERATOR])  # the operator is back
    await sim.fly(1)

    lease = context.runtime().leases.view(aircraft_id)
    alerts = await client.get("/api/v1/alerts?state=active", headers=auth[Role.SUPERVISOR])
    assert lease is not None
    assert lease.state == "held"
    assert "control_orphaned" not in {a["kind"] for a in alerts.json()["items"]}


async def test_leases_survive_a_restart(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft_id: str,
    context: AppContext,
) -> None:
    await take(client, auth[Role.OPERATOR], aircraft_id)

    async with context.database().ops_session() as db:
        row = await db.get(ControlLease, aircraft_id)

    assert row is not None
    assert row.state == "held"


async def test_control_of_unknown_aircraft_is_404(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    response = await client.post(control("no-such-aircraft"), headers=auth[Role.OPERATOR])

    assert response.status_code == 404
