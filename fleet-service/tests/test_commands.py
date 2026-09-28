"""
The command pipeline against simulated aircraft (ADR 0011, ADR 0020).

Each safety rule of ADR 0011 has a test here; the test names say which rule.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.db.models import AuditEvent
from fleet_service.domain.enums import FlightMode, Role
from live_support import Sim, confirmed, register, send, states, take

from support import FakeClock, bearer, insert_user, login


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        station_name="test-station", data_dir=data_dir, simulation=True, command_timeout_s=0.2
    )


@pytest.fixture
def sim(app: FastAPI, clock: FakeClock) -> Sim:
    context: AppContext = app.state.context
    return Sim(context.runtime(), clock)


@pytest.fixture
async def fleet(client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim) -> list[str]:
    """Two hexacopters, both controlled by the operator, with telemetry flowing."""
    ids = [await register(client, auth[Role.SUPERVISOR], name) for name in ("HX-1", "HX-2")]
    for aircraft_id in ids:
        await take(client, auth[Role.OPERATOR], aircraft_id)
    await sim.fly(1)
    return ids


async def airborne(
    client: httpx.AsyncClient, headers: dict[str, str], sim: Sim, ids: list[str]
) -> None:
    for aircraft_id in ids:
        await confirmed(client, headers, "arm", [aircraft_id])
        await sim.fly(0.5)
        await confirmed(client, headers, "takeoff", [aircraft_id], altitude_relative_m=40.0)
        await sim.fly(0.5)
    await sim.fly(20)


async def audit_count(context: AppContext, action: str) -> int:
    async with context.database().ops_session() as db:
        count = await db.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    return count or 0


# --- happy path ----------------------------------------------------------------------------


async def test_arm_asks_for_confirmation_with_a_server_summary(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str]
) -> None:
    response = await send(client, auth[Role.OPERATOR], "arm", [fleet[0]])

    assert response.status_code == 428
    problem = response.json()
    assert response.headers["content-type"] == "application/problem+json"
    assert problem["type"] == "urn:sar-gcs:problem:confirmation-required"
    assert problem["summary"]["kind"] == "arm"
    assert problem["summary"]["aircraft"] == [
        {"aircraft_id": fleet[0], "callsign": "HX-1", "warnings": []}
    ]
    assert problem["summary"]["reasons"] == ["arm always needs confirmation"]
    assert problem["confirmation_token"]


async def test_confirmed_arm_and_takeoff_fly_and_are_verified(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str], sim: Sim
) -> None:
    armed = await confirmed(client, auth[Role.OPERATOR], "arm", [fleet[0]])
    assert states(armed) == {fleet[0]: "acked"}
    await sim.fly(1)

    takeoff = await confirmed(
        client, auth[Role.OPERATOR], "takeoff", [fleet[0]], altitude_relative_m=40.0
    )
    await sim.fly(20)

    command = await client.get(f"/api/v1/commands/{takeoff['id']}", headers=auth[Role.OBSERVER])
    assert states(command.json()) == {fleet[0]: "verified"}
    assert sim.vehicle(fleet[0]).z == pytest.approx(40.0, abs=0.6)
    assert command.json()["confirmed_at"] is not None


async def test_goto_flies_to_the_target_within_the_confirm_distance(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str], sim: Sim
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])
    lat, lon = sim.vehicle(fleet[0]).to_geo(200.0, 200.0)

    response = await send(
        client,
        auth[Role.OPERATOR],
        "goto",
        [fleet[0]],
        target={"latitude": lat, "longitude": lon},
        altitude_relative_m=50.0,
    )
    await sim.fly(60)

    assert response.status_code == 200  # 283 m: below the 1 km confirmation threshold
    assert states(response.json()) == {fleet[0]: "acked"}
    assert sim.vehicle(fleet[0]).mode is FlightMode.HOLD
    assert sim.vehicle(fleet[0]).z == pytest.approx(50.0, abs=1.0)


async def test_long_goto_needs_confirmation(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str], sim: Sim
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])
    lat, lon = sim.vehicle(fleet[0]).to_geo(0.0, 1500.0)

    response = await send(
        client, auth[Role.OPERATOR], "goto", [fleet[0]], target={"latitude": lat, "longitude": lon}
    )

    assert response.status_code == 428
    assert "goto of 1" in response.json()["summary"]["reasons"][0]


# --- ADR 0011 rules --------------------------------------------------------------------------


async def test_rule_any_operator_may_hold_but_only_the_controller_may_do_more(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    context: AppContext,
    fleet: list[str],
    sim: Sim,
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])
    await insert_user(context, "other", Role.OPERATOR)
    other = bearer(await login(client, "other"))

    hold = await send(client, other, "hold", [fleet[0]])
    rtl = await send(client, other, "return_to_launch", [fleet[0]])

    assert states(hold.json()) == {fleet[0]: "acked"}
    assert rtl.status_code == 200
    assert rtl.json()["state"] == "rejected"
    assert rtl.json()["targets"][0]["reason_code"] == "no-control"


async def test_rule_bulk_commands_need_confirmation(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str], sim: Sim
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, fleet)

    first = await send(client, auth[Role.OPERATOR], "hold", fleet)
    outcome = await confirmed(client, auth[Role.OPERATOR], "hold", fleet)

    assert first.status_code == 428
    assert first.json()["summary"]["reasons"] == ["sent to 2 aircraft"]
    assert states(outcome) == dict.fromkeys(fleet, "acked")


async def test_rule_a_changed_request_invalidates_the_confirmation(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str]
) -> None:
    asked = await send(client, auth[Role.OPERATOR], "arm", [fleet[0]], command_id=None)
    command_id, token = asked.json()["command_id"], asked.json()["confirmation_token"]

    same_id_other_aircraft = await send(
        client, auth[Role.OPERATOR], "arm", [fleet[1]], command_id=command_id, token=token
    )
    token_on_new_command = await send(client, auth[Role.OPERATOR], "arm", [fleet[0]], token=token)

    assert same_id_other_aircraft.status_code == 409
    assert same_id_other_aircraft.json()["type"] == "urn:sar-gcs:problem:command-id-reused"
    assert token_on_new_command.status_code == 428  # asked again, nothing sent


async def test_rule_an_expired_confirmation_sends_nothing(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    fleet: list[str],
    sim: Sim,
    context: AppContext,
) -> None:
    asked = await send(client, auth[Role.OPERATOR], "arm", [fleet[0]])
    command_id, token = asked.json()["command_id"], asked.json()["confirmation_token"]
    await sim.fly(31)

    late = await send(
        client, auth[Role.OPERATOR], "arm", [fleet[0]], command_id=command_id, token=token
    )
    listed = await client.get("/api/v1/commands", headers=auth[Role.OBSERVER])

    assert late.status_code == 428  # a fresh confirmation, the old one is void
    assert sim.vehicle(fleet[0]).armed is False
    assert await audit_count(context, "command.confirmation_expire") == 1
    assert listed.json()["items"][0]["id"] == command_id


async def test_rule_a_replayed_command_id_returns_the_first_outcome(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    fleet: list[str],
    sim: Sim,
    context: AppContext,
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])
    first = await send(client, auth[Role.OPERATOR], "hold", [fleet[0]], command_id=None)
    await sim.fly(1)

    replay = await send(
        client, auth[Role.OPERATOR], "hold", [fleet[0]], command_id=first.json()["id"]
    )

    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["created_at"] == first.json()["created_at"]
    assert await audit_count(context, "command.dispatch") == 3  # arm, takeoff, hold: once


async def test_rule_a_lost_link_allows_only_hold_return_and_land(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    fleet: list[str],
    sim: Sim,
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])
    sim.runtime.simulator.drivers[fleet[0]].inject(link=False)  # type: ignore[union-attr]
    await sim.fly(4)  # stale after 3 s

    lat, lon = sim.vehicle(fleet[0]).to_geo(50.0, 0.0)
    goto = await send(
        client, auth[Role.OPERATOR], "goto", [fleet[0]], target={"latitude": lat, "longitude": lon}
    )
    hold = await send(client, auth[Role.OPERATOR], "hold", [fleet[0]])
    alerts = await client.get("/api/v1/alerts?state=active", headers=auth[Role.OBSERVER])

    assert goto.json()["targets"][0]["reason_code"] == "link-degraded"
    assert states(hold.json()) == {fleet[0]: "timeout"}  # attempted; the radio is silent
    kinds = {a["kind"] for a in alerts.json()["items"]}
    assert {"link_stale", "command_timeout"} <= kinds


async def test_rule_disarm_is_refused_in_flight(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str], sim: Sim
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])

    response = await send(client, auth[Role.OPERATOR], "disarm", [fleet[0]])

    assert response.json()["targets"][0]["reason_code"] == "in-air"
    assert sim.vehicle(fleet[0]).armed is True


async def test_rule_supervisor_override_is_confirmed_and_audited(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    fleet: list[str],
    sim: Sim,
    context: AppContext,
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])

    first = await send(client, auth[Role.SUPERVISOR], "return_to_launch", [fleet[0]])
    outcome = await confirmed(client, auth[Role.SUPERVISOR], "return_to_launch", [fleet[0]])

    assert first.json()["summary"]["override"] is True
    assert "overrides another operator's control" in first.json()["summary"]["reasons"]
    assert outcome["override"] is True
    async with context.database().ops_session() as db:
        dispatch = (
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.action == "command.dispatch")
                .order_by(AuditEvent.seq.desc())
            )
        ).first()
    assert dispatch is not None
    assert dispatch.details["override"] is True
    assert dispatch.actor_username == "supervisor"


async def test_rule_preconditions_are_checked_again_at_dispatch(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str], sim: Sim
) -> None:
    asked = await send(client, auth[Role.OPERATOR], "arm", [fleet[0]])
    sim.runtime.simulator.drivers[fleet[0]].inject(battery_pct=20.0)  # type: ignore[union-attr]
    await sim.fly(0.5)

    outcome = await send(
        client,
        auth[Role.OPERATOR],
        "arm",
        [fleet[0]],
        command_id=asked.json()["command_id"],
        token=asked.json()["confirmation_token"],
    )

    assert outcome.status_code == 200
    assert outcome.json()["state"] == "rejected"
    assert outcome.json()["targets"][0]["reason_code"] == "battery-low"
    assert sim.vehicle(fleet[0]).armed is False


async def test_rule_commands_need_a_lease_or_an_override(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    free = await register(client, auth[Role.SUPERVISOR], "FREE-1")
    await sim.fly(1)

    response = await send(client, auth[Role.OPERATOR], "arm", [free])

    assert response.json()["state"] == "rejected"
    assert response.json()["targets"][0]["reason_code"] == "no-control"


async def test_rule_an_acked_command_without_effect_raises_an_alert(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str], sim: Sim
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])
    outcome = await send(client, auth[Role.OPERATOR], "return_to_launch", [fleet[0]])
    sim.runtime.simulator.drivers[fleet[0]].inject(link=False)  # type: ignore[union-attr]

    await sim.idle(11)  # no telemetry after the ack, then past the 10 s effect timeout

    command = await client.get(
        f"/api/v1/commands/{outcome.json()['id']}", headers=auth[Role.OBSERVER]
    )
    alerts = await client.get("/api/v1/alerts?state=active", headers=auth[Role.OBSERVER])
    assert states(command.json()) == {fleet[0]: "unverified"}
    assert "command_unverified" in {a["kind"] for a in alerts.json()["items"]}


# --- validation ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"kind": "arm", "aircraft_ids": []}, 422),
        ({"kind": "arm", "aircraft_ids": ["x", "x"]}, 422),
        ({"kind": "self_destruct", "aircraft_ids": ["x"]}, 422),
        ({"kind": "takeoff", "aircraft_ids": ["x"]}, 422),  # altitude is required
        ({"kind": "arm", "aircraft_ids": ["no-such-aircraft"]}, 422),
    ],
)
async def test_invalid_command_requests(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    fleet: list[str],
    body: dict[str, Any],
    status: int,
) -> None:
    response = await client.post(
        "/api/v1/commands",
        json={"command_id": "7b0c1f7e-1111-4e8e-9f00-000000000001", **body},
        headers=auth[Role.OPERATOR],
    )

    assert response.status_code == status


async def test_rapid_repeat_commands_are_rate_limited(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str], sim: Sim
) -> None:
    await airborne(client, auth[Role.OPERATOR], sim, [fleet[0]])

    first = await send(client, auth[Role.OPERATOR], "hold", [fleet[0]])
    second = await send(client, auth[Role.OPERATOR], "hold", [fleet[0]])  # same instant

    assert states(first.json()) == {fleet[0]: "acked"}
    assert second.json()["targets"][0]["reason_code"] == "rate-limited"


async def test_commands_to_aircraft_without_a_link_are_rejected(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], fleet: list[str]
) -> None:
    # No simulation step has happened for this new aircraft: it has never been heard.
    silent = await register(client, auth[Role.SUPERVISOR], "NEW-1")
    await take(client, auth[Role.OPERATOR], silent)

    response = await send(client, auth[Role.OPERATOR], "hold", [silent])

    assert response.json()["targets"][0]["reason_code"] == "no-link"
