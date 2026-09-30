"""
Data retention (M5): what the station keeps, and for how long.

Purged, when older than the configured number of days (0 keeps forever):

* **telemetry samples** (``telemetry.db``), by their timestamp;
* **cleared alerts**, by when they cleared (active and acknowledged ones are kept);
* **finished commands** (completed, rejected, expired) and their per-aircraft targets, by
  when they were created.

Never purged: the audit trail (its hash chain must stay whole; ADR 0019), users, incidents,
missions, search areas and points of interest (the incident record). Each purge is itself
audited with what it removed. Runs in the runtime's retention loop and as
``fleet-service purge`` (``--dry-run`` only counts).
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.db.models import Alert, Command, TelemetrySample
from fleet_service.domain.enums import AlertState, CommandState
from fleet_service.services import audit

FINISHED_COMMANDS = (CommandState.COMPLETED, CommandState.REJECTED, CommandState.EXPIRED)


@dataclass(frozen=True)
class RetentionPolicy:
    """How many days to keep each kind of record; 0 keeps it forever."""

    telemetry_days: int
    alert_days: int
    command_days: int


@dataclass(frozen=True)
class PurgeReport:
    """What a purge removed (or, in a dry run, would remove)."""

    telemetry_samples: int
    alerts: int
    commands: int
    dry_run: bool


def _cutoff(now: datetime, days: int) -> datetime | None:
    return now - timedelta(days=days) if days > 0 else None


async def purge(
    ops: AsyncSession,
    telemetry: AsyncSession,
    policy: RetentionPolicy,
    now: datetime,
    actor: audit.Actor,
    *,
    dry_run: bool = False,
) -> PurgeReport:
    """Remove what the policy no longer keeps; audit it; commit both databases."""
    samples = alerts = commands = 0

    telemetry_cutoff = _cutoff(now, policy.telemetry_days)
    if telemetry_cutoff is not None:
        cutoff_us = int(telemetry_cutoff.timestamp() * 1_000_000)
        old = TelemetrySample.ts_us < cutoff_us
        samples = await telemetry.scalar(select(func.count()).where(old)) or 0
        if samples and not dry_run:
            await telemetry.execute(delete(TelemetrySample).where(old))

    alert_cutoff = _cutoff(now, policy.alert_days)
    if alert_cutoff is not None:
        cleared = (Alert.state == AlertState.CLEARED) & (Alert.cleared_at < alert_cutoff)
        alerts = await ops.scalar(select(func.count()).select_from(Alert).where(cleared)) or 0
        if alerts and not dry_run:
            await ops.execute(delete(Alert).where(cleared))

    command_cutoff = _cutoff(now, policy.command_days)
    if command_cutoff is not None:
        finished = Command.state.in_(FINISHED_COMMANDS) & (Command.created_at < command_cutoff)
        commands = await ops.scalar(select(func.count()).select_from(Command).where(finished)) or 0
        if commands and not dry_run:
            await ops.execute(delete(Command).where(finished))  # targets cascade

    report = PurgeReport(samples, alerts, commands, dry_run)
    if not dry_run and (samples or alerts or commands):
        await audit.record(
            ops,
            actor,
            now,
            "retention.purge",
            details={"removed": asdict(report), "policy": asdict(policy)},
        )
        await telemetry.commit()
        await ops.commit()
    return report
