"""Data retention (M5): old telemetry, cleared alerts and finished commands go; the audit
trail, open alerts and running commands stay; each purge is audited."""

from datetime import timedelta

from sqlalchemy import func, select

from fleet_service.context import AppContext
from fleet_service.db.models import Alert, AuditEvent, Command, TelemetrySample
from fleet_service.domain.enums import (
    AlertKind,
    AlertSeverity,
    AlertState,
    CommandKind,
    CommandState,
    Role,
)
from fleet_service.ids import new_id
from fleet_service.services import audit

from support import FakeClock


async def _seed(context: AppContext, clock: FakeClock, user_id: str) -> None:
    now = clock.now()
    old, recent = now - timedelta(days=100), now - timedelta(days=1)
    async with context.database().telemetry_session() as db:
        for ts in (old, old, recent):
            db.add(
                TelemetrySample(aircraft_id="a1", ts_us=int(ts.timestamp() * 1e6), source="mock")
            )
        await db.commit()
    async with context.database().ops_session() as db:
        for state, cleared_at in (
            (AlertState.CLEARED, old),  # purged
            (AlertState.CLEARED, recent),  # kept: too recent
            (AlertState.ACKNOWLEDGED, None),  # kept: still open
        ):
            db.add(
                Alert(
                    id=new_id(),
                    kind=AlertKind.LINK_LOST,
                    severity=AlertSeverity.WARNING,
                    state=state,
                    aircraft_id=None,
                    dedupe_key=new_id(),
                    message="m",
                    raised_at=old,
                    cleared_at=cleared_at,
                )
            )
        for command_state in (CommandState.COMPLETED, CommandState.IN_PROGRESS):  # the first goes
            db.add(
                Command(
                    id=new_id(),
                    kind=CommandKind.HOLD,
                    params={},
                    issued_by=user_id,
                    request_hash="0" * 64,
                    state=command_state,
                    confirmation_required=False,
                    created_at=old,
                )
            )
        await db.commit()


async def _counts(context: AppContext) -> tuple[int, int, int]:
    async with context.database().telemetry_session() as db:
        samples = await db.scalar(select(func.count()).select_from(TelemetrySample)) or 0
    async with context.database().ops_session() as db:
        alerts = await db.scalar(select(func.count()).select_from(Alert)) or 0
        commands = await db.scalar(select(func.count()).select_from(Command)) or 0
    return samples, alerts, commands


async def test_a_purge_removes_only_what_the_policy_no_longer_keeps(
    context: AppContext, clock: FakeClock, user_ids: dict[Role, str]
) -> None:
    await _seed(context, clock, next(iter(user_ids.values())))

    dry = await context.runtime().purge(dry_run=True)
    after_dry = await _counts(context)
    report = await context.runtime().purge()
    after = await _counts(context)
    again = await context.runtime().purge()

    assert (dry.telemetry_samples, dry.alerts, dry.commands) == (2, 1, 1)
    assert after_dry == (3, 3, 2)  # a dry run changes nothing
    assert (report.telemetry_samples, report.alerts, report.commands) == (2, 1, 1)
    assert after == (1, 2, 1)
    assert (again.telemetry_samples, again.alerts, again.commands) == (0, 0, 0)
    async with context.database().ops_session() as db:
        events = (
            await db.scalars(select(AuditEvent).where(AuditEvent.action == "retention.purge"))
        ).all()
        assert (await audit.verify_chain(db)).ok
    assert len(events) == 1  # the empty second purge records nothing
    assert events[0].details["removed"]["telemetry_samples"] == 2
