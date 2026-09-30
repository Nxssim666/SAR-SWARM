"""
Audit chain heads kept outside the database (M6): truncation becomes detectable.

The hash chain (``services.audit``) catches an edited, inserted or deleted event anywhere
but at the end: removing the newest events leaves a shorter chain that still verifies. So
the station appends the chain's head (sequence number and hash) to a JSON Lines file every
few minutes. Put that file on other media (``audit_head_file``, e.g. a USB stick) or copy
it off the station. A verification then also checks that every recorded head is still in
the chain with the same hash.

The file only ever grows by one short line per change of head; a line that cannot be
parsed is reported, never skipped silently.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.db.models import AuditEvent
from fleet_service.db.types import format_utc


@dataclass(frozen=True)
class Head:
    """The newest event of the chain when it was exported."""

    seq: int
    hash: str
    exported_at: str


@dataclass(frozen=True)
class HeadCheck:
    """The chain compared with the exported heads."""

    heads: int
    problem: str | None  # None: every exported head is in the chain


async def current_head(db: AsyncSession) -> tuple[int, str] | None:
    """The newest event's sequence number and hash (None: no events yet)."""
    row = (
        await db.execute(
            select(AuditEvent.seq, AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)
        )
    ).first()
    return (row.seq, row.hash) if row else None


def read_heads(path: Path) -> list[Head]:
    """Every head in the file, oldest first (no file: none). Raises ValueError on a bad line."""
    if not path.exists():
        return []
    heads = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            heads.append(Head(int(data["seq"]), str(data["hash"]), str(data["exported_at"])))
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"{path.name} line {number} is not a head: {error}") from error
    return heads


def append_head(path: Path, head: tuple[int, str], now: datetime) -> bool:
    """Append ``head`` unless it is the last one recorded; True if a line was written."""
    heads = read_heads(path)
    if heads and (heads[-1].seq, heads[-1].hash) == head:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"seq": head[0], "hash": head[1], "exported_at": format_utc(now)})
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")
        file.flush()
    return True


async def check_heads(db: AsyncSession, path: Path) -> HeadCheck:
    """Whether every exported head is still in the chain, with the same hash."""
    try:
        heads = read_heads(path)
    except ValueError as error:
        return HeadCheck(0, str(error))
    for head in heads:
        stored = await db.scalar(select(AuditEvent.hash).where(AuditEvent.seq == head.seq))
        if stored is None:
            return HeadCheck(
                len(heads),
                f"event {head.seq}, exported at {head.exported_at}, is missing: "
                "the chain was truncated",
            )
        if stored != head.hash:
            return HeadCheck(
                len(heads),
                f"event {head.seq} does not match the head exported at {head.exported_at}",
            )
    return HeadCheck(len(heads), None)
