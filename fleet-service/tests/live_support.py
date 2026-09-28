"""Helpers for tests of live behaviour: simulated aircraft, commands, simulated time."""

import uuid
from typing import Any

import httpx

from fleet_service.services.runtime import Runtime

from support import FakeClock

SIM_STEP_S = 0.1
EVALUATE_EVERY_S = 0.5


class Sim:
    """Drives the runtime by hand: advance time, step aircraft, evaluate, record."""

    def __init__(self, runtime: Runtime, clock: FakeClock) -> None:
        self.runtime = runtime
        self.clock = clock

    async def fly(self, seconds: float) -> None:
        """Let ``seconds`` of simulated time pass, evaluating every 0.5 s as the loops would."""
        steps = round(seconds / SIM_STEP_S)
        per_evaluation = round(EVALUATE_EVERY_S / SIM_STEP_S)
        for i in range(1, steps + 1):
            self.clock.advance(seconds=SIM_STEP_S)
            self.runtime.step_simulation(SIM_STEP_S)
            if i % per_evaluation == 0:
                await self.runtime.evaluate()

    async def idle(self, seconds: float) -> None:
        """Let time pass without any telemetry (aircraft frozen), then evaluate."""
        self.clock.advance(seconds=seconds)
        await self.runtime.evaluate()

    def vehicle(self, aircraft_id: str) -> Any:
        """The simulated vehicle behind an aircraft."""
        assert self.runtime.simulator is not None
        return self.runtime.simulator.drivers[aircraft_id].vehicle


async def register(
    client: httpx.AsyncClient, headers: dict[str, str], callsign: str, **extra: Any
) -> str:
    """Register an aircraft (simulated in simulation mode); return its id."""
    body = {"callsign": callsign, "airframe": "multirotor_hexa", "mavlink_system_id": None} | extra
    response = await client.post("/api/v1/aircraft", json=body, headers=headers)
    assert response.status_code == 201, response.text
    aircraft_id: str = response.json()["id"]
    return aircraft_id


async def take(client: httpx.AsyncClient, headers: dict[str, str], aircraft_id: str) -> None:
    """Take control of an aircraft."""
    response = await client.post(f"/api/v1/aircraft/{aircraft_id}/control", headers=headers)
    assert response.status_code == 200, response.text


async def send(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    kind: str,
    aircraft_ids: list[str],
    *,
    command_id: str | None = None,
    token: str | None = None,
    **params: Any,
) -> httpx.Response:
    """POST a command (a fresh command_id unless given)."""
    body: dict[str, Any] = {
        "command_id": command_id or str(uuid.uuid4()),
        "kind": kind,
        "aircraft_ids": aircraft_ids,
        **params,
    }
    if token is not None:
        body["confirmation_token"] = token
    return await client.post("/api/v1/commands", json=body, headers=headers)


async def confirmed(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    kind: str,
    aircraft_ids: list[str],
    **params: Any,
) -> dict[str, Any]:
    """Send a command that needs confirmation, confirm it, return the outcome."""
    command_id = str(uuid.uuid4())
    first = await send(client, headers, kind, aircraft_ids, command_id=command_id, **params)
    assert first.status_code == 428, first.text
    second = await send(
        client,
        headers,
        kind,
        aircraft_ids,
        command_id=command_id,
        token=first.json()["confirmation_token"],
        **params,
    )
    assert second.status_code == 200, second.text
    outcome: dict[str, Any] = second.json()
    return outcome


def states(outcome: dict[str, Any]) -> dict[str, str]:
    """Per-aircraft target states of a command outcome."""
    return {t["aircraft_id"]: t["state"] for t in outcome["targets"]}
