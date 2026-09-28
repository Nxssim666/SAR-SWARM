"""
Schema migrations with Alembic, one script directory per database (ADR 0019).

The service upgrades both databases at startup. If ``ops.db`` already holds data and
migrations are pending, it is first copied with SQLite's online backup API to
``<data_dir>/backups/`` (ADR 0016: forward-only migrations, backup before upgrade).
Migrations use a plain synchronous ``sqlite://`` connection.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from fleet_service.db.engine import OPS_DB, TELEMETRY_DB

DatabaseName = Literal["ops", "telemetry"]
DATABASE_FILES: dict[DatabaseName, str] = {"ops": OPS_DB, "telemetry": TELEMETRY_DB}
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

log = logging.getLogger(__name__)


def alembic_config(database: DatabaseName, db_path: Path) -> Config:
    """Alembic configuration for one database file, without an ini file."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR / database))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    config.set_main_option(
        "file_template", "%%(rev)s_%%(slug)s"
    )  # revision ids are sequential, see next_revision_id
    return config


def current_revision(db_path: Path) -> str | None:
    """Return the revision ``db_path`` is at, or None for an empty or missing database."""
    if not db_path.exists():
        return None
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def head_revision(database: DatabaseName) -> str | None:
    """Return the newest revision of ``database``'s migrations."""
    script = ScriptDirectory.from_config(alembic_config(database, Path("unused.db")))
    return script.get_current_head()


def backup(db_path: Path, destination: Path) -> None:
    """Copy a live SQLite database consistently (online backup API)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(db_path)
    try:
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


@dataclass(frozen=True)
class UpgradeReport:
    """What ``upgrade_all`` did."""

    upgraded: dict[DatabaseName, tuple[str | None, str | None]]
    backups: list[Path]


def upgrade_all(data_dir: Path, now: datetime) -> UpgradeReport:
    """Bring both databases in ``data_dir`` to the newest schema, backing up ``ops.db`` first."""
    data_dir.mkdir(parents=True, exist_ok=True)
    upgraded: dict[DatabaseName, tuple[str | None, str | None]] = {}
    backups: list[Path] = []
    for database, filename in DATABASE_FILES.items():
        db_path = data_dir / filename
        before = current_revision(db_path)
        head = head_revision(database)
        if before == head:
            continue
        if database == "ops" and before is not None:
            stamp = now.strftime("%Y%m%dT%H%M%SZ")
            destination = data_dir / "backups" / f"ops-{before}-{stamp}.db"
            backup(db_path, destination)
            backups.append(destination)
            log.info("backed up ops.db before migrating", extra={"backup": str(destination)})
        command.upgrade(alembic_config(database, db_path), "head")
        upgraded[database] = (before, head)
        log.info("migrated %s", database, extra={"from_revision": before, "to_revision": head})
    return UpgradeReport(upgraded=upgraded, backups=backups)


def next_revision_id(database: DatabaseName) -> str:
    """Sequential revision ids (``0001``, ``0002`` …) keep the history readable."""
    versions = MIGRATIONS_DIR / database / "versions"
    numbers = [int(p.name[:4]) for p in versions.glob("[0-9][0-9][0-9][0-9]_*.py")]
    return f"{max(numbers, default=0) + 1:04d}"


def autogenerate_revision(database: DatabaseName, message: str, scratch_dir: Path) -> None:
    """Write a new migration for model changes (development tool)."""
    scratch_db = scratch_dir / DATABASE_FILES[database]
    config = alembic_config(database, scratch_db)
    for key, value in {
        "hooks": "ruff_format",
        "ruff_format.type": "module",
        "ruff_format.module": "ruff",
        "ruff_format.options": "format REVISION_SCRIPT_FILENAME",
    }.items():
        config.set_section_option("post_write_hooks", key, value)
    command.upgrade(config, "head")
    command.revision(config, message=message, autogenerate=True, rev_id=next_revision_id(database))
