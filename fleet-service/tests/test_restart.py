"""
A ground-station restart (M6, ADR 0035): commands it interrupted are closed with a reason,
never re-sent; live state comes back from the aircraft.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.db.models import AuditEvent, Command, CommandTarget
from fleet_service.domain.enums import CommandKind, CommandState, CommandTargetState, Role
from fleet_service.main import create_app
from live_support import Sim, register

from support import FakeClock


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(station_name="test-station", data_dir=data_dir, simulation=True)


def command(
    command_id: str, kind: CommandKind, state: CommandState, user_id: str, clock: FakeClock
) -> Command:
    return Command(
        id=command_id,
        kind=kind,
        params={},
        issued_by=user_id,
        request_hash="0" * 64,
        state=state,
        confirmation_required=False,
        confirmation_expires_at=None,
        confirmed_at=None,
        created_at=clock.now(),
        completed_at=None if state is CommandState.IN_PROGRESS else clock.now(),
    )


def target(command_id: str, aircraft_id: str, state: CommandTargetState, clock: FakeClock) -> Any:
    return CommandTarget(
        command_id=command_id,
        aircraft_id=aircraft_id,
        state=state,
        reason_code=None,
        reason=None,
        updated_at=clock.now(),
    )


async def test_a_restart_closes_interrupted_commands_and_never_resends_them(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    user_ids: dict[Role, str],
    context: AppContext,
    settings: Settings,
    clock: FakeClock,
) -> None:
    aircraft_id = await register(client, auth[Role.SUPERVISOR], "HX-1")
    operator = user_ids[Role.OPERATOR]
    # As a crash would leave them: a takeoff sent but unanswered, a hold acked whose effect
    # was being checked, and a disarm already verified (finished: left alone).
    async with context.database().ops_session() as db:
        db.add_all(
            [
                command(
                    "c-takeoff", CommandKind.TAKEOFF, CommandState.IN_PROGRESS, operator, clock
                ),
                command("c-hold", CommandKind.HOLD, CommandState.COMPLETED, operator, clock),
                command("c-disarm", CommandKind.DISARM, CommandState.COMPLETED, operator, clock),
            ]
        )
        await db.flush()
        db.add_all(
            [
                target("c-takeoff", aircraft_id, CommandTargetState.DISPATCHED, clock),
                target("c-hold", aircraft_id, CommandTargetState.ACKED, clock),
                target("c-disarm", aircraft_id, CommandTargetState.VERIFIED, clock),
            ]
        )
        await db.commit()
    clock.advance(minutes=1)

    restarted = create_app(
        settings, clock=clock, passwords=fast_passwords_for_tests(), start_loops=False
    )
    async with restarted.router.lifespan_context(restarted):
        runtime = restarted.state.context.runtime()
        sim = Sim(runtime, clock)
        await sim.fly(2)
        async with restarted.state.context.database().ops_session() as db:
            states = {
                t.command_id: (t.state, t.reason_code)
                for t in (await db.scalars(select(CommandTarget))).all()
            }
            takeoff = await db.get(Command, "c-takeoff")
            interrupts = (
                await db.scalars(select(AuditEvent).where(AuditEvent.action == "command.interrupt"))
            ).all()
        vehicle = runtime.simulator.drivers[aircraft_id].vehicle
        live = runtime.registry.live(aircraft_id)

    assert states == {
        "c-takeoff": (CommandTargetState.TIMEOUT, "interrupted"),
        "c-hold": (CommandTargetState.UNVERIFIED, "interrupted"),
        "c-disarm": (CommandTargetState.VERIFIED, None),
    }
    assert takeoff is not None
    assert takeoff.state is CommandState.COMPLETED
    assert {e.entity_id for e in interrupts} == {"c-takeoff", "c-hold"}
    assert all(e.actor_username == "system:restart" for e in interrupts)
    assert vehicle.armed is False  # nothing was re-sent
    assert vehicle.in_air is False
    assert live is not None
    assert live.link == "live"  # state comes back from the aircraft


async def test_a_clean_start_has_nothing_to_close(context: AppContext) -> None:
    async with context.database().ops_session() as db:
        assert await context.runtime().commands.load(db, context.clock.now()) == 0
