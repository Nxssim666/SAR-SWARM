"""
Database engines (ADR 0019).

One connection per SQLite file: every transaction in the process is serialized per
database. That rules out SQLITE_BUSY lock-upgrade failures between our own
transactions and makes the audit chain's read-last-hash-then-append atomic. Keep
transactions short, and never await slow work (password hashing, I/O to aircraft)
while one is open.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

OPS_DB = "ops.db"
TELEMETRY_DB = "telemetry.db"

Synchronous = Literal["FULL", "NORMAL"]


def create_engine_for(path: Path, synchronous: Synchronous) -> AsyncEngine:
    """Return an async engine for the SQLite file at ``path`` with our pragmas."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        pool_size=1,
        max_overflow=0,
        pool_timeout=30,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA synchronous={synchronous}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


class Database:
    """The two databases of the fleet service."""

    def __init__(self, data_dir: Path) -> None:
        self.ops_engine = create_engine_for(data_dir / OPS_DB, "FULL")
        self.telemetry_engine = create_engine_for(data_dir / TELEMETRY_DB, "NORMAL")
        self._ops_sessions = async_sessionmaker(self.ops_engine, expire_on_commit=False)
        self._telemetry_sessions = async_sessionmaker(self.telemetry_engine, expire_on_commit=False)

    @asynccontextmanager
    async def ops_session(self) -> AsyncIterator[AsyncSession]:
        """A session on ``ops.db``; uncommitted work is rolled back on exit."""
        async with self._ops_sessions() as session:
            yield session

    @asynccontextmanager
    async def telemetry_session(self) -> AsyncIterator[AsyncSession]:
        """A session on ``telemetry.db``."""
        async with self._telemetry_sessions() as session:
            yield session

    async def dispose(self) -> None:
        """Close all connections."""
        await self.ops_engine.dispose()
        await self.telemetry_engine.dispose()
