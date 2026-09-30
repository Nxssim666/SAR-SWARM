"""
The station's safeguards (M6): the disk guard, and audit chain heads kept outside the
database so truncation is detectable.
"""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, func, select

from fleet_service.cli import main
from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.db.models import AuditEvent, TelemetrySample
from fleet_service.domain.enums import AlertKind, AlertSeverity, Role
from fleet_service.services.station_health import MB, disk_condition, recording_allowed
from live_support import Sim, register

from support import FakeClock


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(
        station_name="test-station",
        data_dir=data_dir,
        simulation=True,
        disk_warn_free_mb=2048,
        disk_critical_free_mb=512,
    )


@pytest.fixture
def sim(context: AppContext, clock: FakeClock) -> Sim:
    return Sim(context.runtime(), clock)


# --- disk guard ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("free_mb", "severity"),
    [
        (4096, None),
        (2048, None),
        (2047, AlertSeverity.WARNING),
        (511, AlertSeverity.CRITICAL),
    ],
)
def test_disk_low_row_by_row(free_mb: int, severity: AlertSeverity | None) -> None:
    condition = disk_condition(free_mb * MB, 2048, 512)

    assert (condition.severity if condition else None) is severity


def test_unknown_free_space_is_alerted_not_assumed_plenty() -> None:
    condition = disk_condition(None, 2048, 512)

    assert condition is not None
    assert "unknown" in condition.message
    assert recording_allowed(None, 512)  # keep the history; the alert says why to look


async def test_a_nearly_full_disk_alerts_and_pauses_telemetry_history(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    context: AppContext,
    sim: Sim,
) -> None:
    runtime = context.runtime()
    await register(client, auth[Role.SUPERVISOR], "HX-1")
    runtime.free_bytes = lambda: 100 * MB

    await sim.fly(2)
    await runtime.record()
    alerts = await client.get("/api/v1/alerts?state=active", headers=auth[Role.OBSERVER])
    async with context.database().telemetry_session() as db:
        paused = await db.scalar(select(func.count()).select_from(TelemetrySample))

    runtime.free_bytes = lambda: 10_000 * MB
    await sim.fly(1)
    await runtime.record()
    cleared = await client.get("/api/v1/alerts?state=active", headers=auth[Role.OBSERVER])
    async with context.database().telemetry_session() as db:
        resumed = await db.scalar(select(func.count()).select_from(TelemetrySample))

    disk = [a for a in alerts.json()["items"] if a["kind"] == AlertKind.DISK_LOW]
    assert [a["severity"] for a in disk] == ["critical"]
    assert "Telemetry history is paused" in disk[0]["message"]
    assert paused == 0
    assert AlertKind.DISK_LOW not in {a["kind"] for a in cleared.json()["items"]}
    assert resumed == 1


# --- audit heads -----------------------------------------------------------------------------


async def test_the_head_is_appended_only_when_it_changes(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    context: AppContext,
    settings: Settings,
) -> None:
    runtime = context.runtime()

    assert await runtime.export_audit_head() is True  # logins were audited
    assert await runtime.export_audit_head() is False  # nothing new
    await register(client, auth[Role.SUPERVISOR], "HX-1")
    assert await runtime.export_audit_head() is True

    lines = settings.audit_heads_path.read_text().splitlines()
    heads = [json.loads(line) for line in lines]
    assert len(heads) == 2
    assert heads[1]["seq"] > heads[0]["seq"]
    verify = await client.get("/api/v1/audit/verify", headers=auth[Role.SUPERVISOR])
    assert verify.json()["ok"] is True
    assert verify.json()["exported_heads"] == 2


async def test_truncating_the_chain_is_detected_against_the_exported_heads(
    client: httpx.AsyncClient,
    auth: dict[Role, dict[str, str]],
    context: AppContext,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = context.runtime()
    await register(client, auth[Role.SUPERVISOR], "HX-1")
    await runtime.export_audit_head()
    async with context.database().ops_session() as db:
        last = await db.scalar(select(func.max(AuditEvent.seq)))
        # Remove the newest events: the rest of the chain still verifies on its own.
        await db.execute(delete(AuditEvent).where(AuditEvent.seq > (last or 0) - 2))
        await db.commit()

    verify = await client.get("/api/v1/audit/verify", headers=auth[Role.SUPERVISOR])

    assert verify.json()["ok"] is False
    assert verify.json()["broken_at_seq"] is None  # the chain itself is consistent
    assert "truncated" in verify.json()["reason"]
    monkeypatch.setenv("SARGCS_DATA_DIR", str(settings.data_dir))
    from fleet_service.config import get_settings

    get_settings.cache_clear()
    try:
        assert await asyncio.to_thread(main, ["audit-verify"]) == 1  # its own event loop
    finally:
        get_settings.cache_clear()
    assert "TRUNCATED" in capsys.readouterr().err


async def test_a_damaged_head_file_is_reported(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], settings: Settings
) -> None:
    settings.audit_heads_path.write_text("not json\n")

    verify = await client.get("/api/v1/audit/verify", headers=auth[Role.SUPERVISOR])

    assert verify.json()["ok"] is False
    assert "line 1" in verify.json()["reason"]
