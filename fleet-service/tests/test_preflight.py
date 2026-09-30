"""
Preflight checks in the command pipeline (M6, ADR 0035): arm and takeoff read the aircraft's
failsafe parameters; blocking findings reject the aircraft unless a supervisor overrides,
confirmed and audited.
"""

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.db.models import AuditEvent
from fleet_service.domain.enums import Role
from fleet_service.domain.preflight import ParameterType
from fleet_service.drivers.base import CommandResult, DriverCommand, TelemetrySink
from live_support import Sim, confirmed, register, send, states, take

from support import FakeClock


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        station_name="test-station",
        data_dir=data_dir,
        simulation=True,
        command_timeout_s=0.2,
        preflight_timeout_s=1.0,
    )


@pytest.fixture
def sim(app: FastAPI, clock: FakeClock) -> Sim:
    context: AppContext = app.state.context
    return Sim(context.runtime(), clock)


@pytest.fixture
async def aircraft(client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], sim: Sim) -> str:
    """One hexacopter controlled by the operator, telemetry flowing."""
    aircraft_id = await register(client, auth[Role.SUPERVISOR], "HX-1")
    await take(client, auth[Role.OPERATOR], aircraft_id)
    await sim.fly(1)
    return aircraft_id


async def set_parameters(
    client: httpx.AsyncClient, headers: dict[str, str], aircraft_id: str, **values: float
) -> None:
    response = await client.post(
        f"/api/v1/simulation/aircraft/{aircraft_id}/faults",
        json={"parameters": values},
        headers=headers,
    )
    assert response.status_code == 200, response.text


async def audit_details(context: AppContext, action: str) -> list[dict[str, Any]]:
    async with context.database().ops_session() as db:
        rows = await db.scalars(select(AuditEvent).where(AuditEvent.action == action))
        return [row.details for row in rows]


async def test_a_field_ready_aircraft_arms_with_nothing_to_report(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], aircraft: str
) -> None:
    first = await send(client, auth[Role.OPERATOR], "arm", [aircraft])

    summary = first.json()["summary"]
    assert summary["preflight"] == []
    assert summary["aircraft"][0]["warnings"] == []
    report = await client.get(f"/api/v1/aircraft/{aircraft}/preflight", headers=auth[Role.OBSERVER])
    assert report.json()["ready"] is True
    assert report.json()["values"]["NAV_DLL_ACT"] == 2


async def test_no_link_loss_action_rejects_the_arm_for_an_operator(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], aircraft: str, sim: Sim
) -> None:
    await set_parameters(client, auth[Role.SUPERVISOR], aircraft, NAV_DLL_ACT=0)

    response = await send(client, auth[Role.OPERATOR], "arm", [aircraft])

    assert response.status_code == 200, response.text
    target = response.json()["targets"][0]
    assert target["state"] == "rejected"
    assert target["reason_code"] == "preflight"
    assert "Nothing happens when the link is lost" in target["reason"]
    assert sim.vehicle(aircraft).armed is False


async def test_a_supervisor_overrides_a_failed_preflight_confirmed_and_audited(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    sim: Sim,
    context: AppContext,
) -> None:
    own = await register(client, auth[Role.SUPERVISOR], "HX-2")
    await take(client, auth[Role.SUPERVISOR], own)
    await sim.fly(1)
    await set_parameters(client, auth[Role.SUPERVISOR], own, GF_ACTION=4)

    first = await send(client, auth[Role.SUPERVISOR], "arm", [own])
    assert first.status_code == 428, first.text
    summary = first.json()["summary"]
    assert summary["override"] is True
    assert summary["preflight"] == ["HX-2: The aircraft would terminate on a geofence breach."]
    assert "1 aircraft failed preflight checks (override)" in summary["reasons"]
    assert "overrides another operator's control" not in summary["reasons"]

    outcome = await confirmed(client, auth[Role.SUPERVISOR], "arm", [own])

    assert states(outcome) == {own: "acked"}
    assert sim.vehicle(own).armed is True
    dispatch = (await audit_details(context, "command.dispatch"))[-1]
    assert dispatch["override"] is True
    assert dispatch["overridden"] == ["HX-2: The aircraft would terminate on a geofence breach."]


async def test_warnings_are_shown_in_the_confirmation(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], aircraft: str
) -> None:
    await set_parameters(client, auth[Role.SUPERVISOR], aircraft, COM_LOW_BAT_ACT=0)

    first = await send(client, auth[Role.OPERATOR], "arm", [aircraft])

    assert first.status_code == 428
    assert first.json()["summary"]["aircraft"][0]["warnings"] == [
        "preflight: A critical battery only warns; the aircraft does not return or land."
    ]


async def test_arm_reads_the_parameters_again_but_takeoff_reuses_them(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], aircraft: str, sim: Sim
) -> None:
    await confirmed(client, auth[Role.OPERATOR], "arm", [aircraft])
    await sim.fly(0.5)
    # Changed on board after the arm (no fault injection, so no cache invalidation).
    sim.vehicle(aircraft).parameters["NAV_DLL_ACT"] = 0.0

    takeoff = await confirmed(
        client, auth[Role.OPERATOR], "takeoff", [aircraft], altitude_relative_m=30.0
    )
    assert states(takeoff) == {aircraft: "acked"}  # within max age: the arm's report

    fresh = await client.post(f"/api/v1/aircraft/{aircraft}/preflight", headers=auth[Role.OPERATOR])
    assert fresh.status_code == 200
    assert fresh.json()["ready"] is False
    assert fresh.json()["findings"][0]["parameter"] == "NAV_DLL_ACT"


async def test_a_manual_check_is_audited_and_needs_a_commanding_role(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft: str,
    context: AppContext,
) -> None:
    denied = await client.post(
        f"/api/v1/aircraft/{aircraft}/preflight", headers=auth[Role.OBSERVER]
    )
    assert denied.status_code == 403

    response = await client.post(
        f"/api/v1/aircraft/{aircraft}/preflight", headers=auth[Role.OPERATOR]
    )

    assert response.status_code == 200
    assert await audit_details(context, "aircraft.preflight") == [{"blocking": [], "warnings": []}]


async def test_never_checked_is_not_ready(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], aircraft: str
) -> None:
    report = await client.get(f"/api/v1/aircraft/{aircraft}/preflight", headers=auth[Role.OBSERVER])

    assert report.json() == {
        "aircraft_id": aircraft,
        "checked_at": None,
        "values": {},
        "findings": [],
        "ready": False,
    }


async def test_an_aircraft_that_does_not_answer_is_not_assumed_safe(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    aircraft: str,
    context: AppContext,
    sim: Sim,
) -> None:
    runtime = context.runtime()
    record = runtime.registry.get(aircraft)
    assert record is not None
    record.driver = _Silent(record.driver)

    response = await send(client, auth[Role.OPERATOR], "arm", [aircraft])

    target = response.json()["targets"][0]
    assert target["reason_code"] == "preflight"
    assert "could not be read" in target["reason"]


async def test_only_preflight_parameters_can_be_injected(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], aircraft: str
) -> None:
    response = await client.post(
        f"/api/v1/simulation/aircraft/{aircraft}/faults",
        json={"parameters": {"SYS_AUTOSTART": 1}},
        headers=auth[Role.SUPERVISOR],
    )

    assert response.status_code == 422


class _Silent:
    """A driver whose parameter reads never answer (the service's timeout applies)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.source = inner.source
        self.capabilities = inner.capabilities

    def start(self, sink: TelemetrySink) -> None:
        self._inner.start(sink)

    def stop(self) -> None:
        self._inner.stop()

    async def execute(self, command: DriverCommand) -> CommandResult:
        result: CommandResult = await self._inner.execute(command)
        return result

    async def read_parameters(self, names: dict[str, ParameterType]) -> dict[str, float | None]:
        await asyncio.Future()  # never answers
        return {}
