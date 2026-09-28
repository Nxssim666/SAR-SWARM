"""Migrations, schema drift, timestamps and the audit hash chain."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import sqlite
from sqlalchemy.pool import NullPool

from fleet_service.context import AppContext
from fleet_service.db import migrate
from fleet_service.db.engine import OPS_DB, TELEMETRY_DB
from fleet_service.db.models import OpsBase, TelemetryBase
from fleet_service.db.types import UTCDateTime, format_utc, parse_utc
from fleet_service.services import audit
from fleet_service.services.audit import Actor

from support import START

ACTOR = Actor(user_id="u1", username="alice", request_id="r1", source_ip="10.0.0.5")


# --- migrations --------------------------------------------------------------------------------


def test_fresh_upgrade_reaches_head_without_backup(tmp_path: Path) -> None:
    report = migrate.upgrade_all(tmp_path, START)

    assert report.backups == []
    for database, filename in migrate.DATABASE_FILES.items():
        assert migrate.current_revision(tmp_path / filename) == migrate.head_revision(database)


def test_upgrade_at_head_is_a_no_op(migrated_template: Path, tmp_path: Path) -> None:
    for name in (OPS_DB, TELEMETRY_DB):
        (tmp_path / name).write_bytes((migrated_template / name).read_bytes())

    report = migrate.upgrade_all(tmp_path, START)

    assert report.upgraded == {}
    assert report.backups == []


def test_pending_migration_on_existing_ops_db_is_backed_up_first(
    migrated_template: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / OPS_DB).write_bytes((migrated_template / OPS_DB).read_bytes())
    (tmp_path / TELEMETRY_DB).write_bytes((migrated_template / TELEMETRY_DB).read_bytes())
    current = migrate.head_revision("ops")
    monkeypatch.setattr(migrate, "head_revision", lambda database: "9999")
    upgraded: list[str] = []
    monkeypatch.setattr(
        command,
        "upgrade",
        lambda config, rev: upgraded.append(config.get_main_option("script_location") or ""),
    )

    report = migrate.upgrade_all(tmp_path, START)

    assert len(report.backups) == 1
    backup = report.backups[0]
    assert backup.name == f"ops-{current}-20260928T080000Z.db"
    with closing(sqlite3.connect(backup)) as copy:
        assert copy.execute("select version_num from alembic_version").fetchone() == (current,)
    assert len(upgraded) == 2


@pytest.mark.parametrize(
    ("filename", "metadata"), [(OPS_DB, OpsBase.metadata), (TELEMETRY_DB, TelemetryBase.metadata)]
)
def test_models_and_migrations_do_not_drift(
    migrated_template: Path, filename: str, metadata: object
) -> None:
    engine = create_engine(
        f"sqlite:///{(migrated_template / filename).as_posix()}", poolclass=NullPool
    )
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = compare_metadata(context, metadata)  # type: ignore[arg-type]
    engine.dispose()

    assert diff == []


def test_next_revision_id_is_sequential() -> None:
    versions = migrate.MIGRATIONS_DIR / "ops" / "versions"
    existing = len(list(versions.glob("[0-9][0-9][0-9][0-9]_*.py")))

    assert migrate.next_revision_id("ops") == f"{existing + 1:04d}"


# --- timestamps -----------------------------------------------------------------------------------


def test_utc_datetime_rejects_naive_values() -> None:
    with pytest.raises(ValueError, match="naive"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1), sqlite.dialect())  # noqa: DTZ001


def test_utc_datetime_round_trips_and_sorts_as_text() -> None:
    earlier = format_utc(START)
    later = format_utc(START.replace(microsecond=1))

    assert earlier == "2026-09-28T08:00:00.000000Z"
    assert earlier < later
    assert parse_utc(earlier) == START
    assert UTCDateTime().process_result_value(earlier, sqlite.dialect()) == START


# --- audit chain ----------------------------------------------------------------------------------


async def _record_three(context: AppContext) -> None:
    async with context.database().ops_session() as db:
        for i in range(3):
            await audit.record(
                db, ACTOR, START, f"test.event{i}", entity_type="thing", entity_id=str(i),
                details={"n": i, "password": "hunter2", "nested": {"token": "t", "ok": True}},
            )  # fmt: skip
        await db.commit()


async def test_chain_verifies_and_reports_its_head(context: AppContext) -> None:
    await _record_three(context)

    async with context.database().ops_session() as db:
        report = await audit.verify_chain(db)

    assert report.ok
    assert report.events == 3
    assert report.head_seq == 3
    assert report.head_hash is not None
    assert len(report.head_hash) == 64


async def test_secrets_never_reach_the_audit_trail(context: AppContext) -> None:
    await _record_three(context)

    async with context.database().ops_session() as db:
        details: list[str] = list(
            (await db.execute(text("select details from audit_events"))).scalars().all()
        )

    assert all("hunter2" not in d and '"token"' not in d for d in details)
    assert all('"ok": true' in d or '"ok":true' in d for d in details)


@pytest.mark.parametrize(
    ("statement", "broken_at"),
    [
        ("update audit_events set details = '{\"n\": 99}' where seq = 2", 2),
        ("update audit_events set actor_username = 'mallory' where seq = 1", 1),
        ("delete from audit_events where seq = 2", 3),
        ("update audit_events set hash = 'f' || substr(hash, 2) where seq = 3", 3),
    ],
)
async def test_tampering_breaks_the_chain(
    context: AppContext, statement: str, broken_at: int
) -> None:
    await _record_three(context)
    async with context.database().ops_session() as db:
        await db.execute(text(statement))
        await db.commit()

    async with context.database().ops_session() as db:
        report = await audit.verify_chain(db)

    assert not report.ok
    assert report.broken_at_seq == broken_at


def test_changes_lists_only_differing_fields() -> None:
    assert audit.changes({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": None}) == {"b": [2, 3]}
