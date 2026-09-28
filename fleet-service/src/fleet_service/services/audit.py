"""
Tamper-evident audit trail (ADR 0007, ADR 0019).

Each event stores ``hash = sha256(prev_hash || canonical_json(fields))``, where
``fields`` include its own sequence number and ``prev_hash``. Editing, inserting or
deleting a row in the middle breaks the chain at that point. Truncating the *end*
of the chain is only detectable against a head (sequence number, hash) recorded
elsewhere; ``verify_chain`` reports the head so it can be written down or exported.

Events are appended in the caller's transaction, so a change and its audit record
commit or roll back together. Callers never pass secrets; ``scrub`` removes known
secret keys anyway, as a second line of defence.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.db.models import AuditEvent
from fleet_service.db.types import format_utc
from fleet_service.ids import new_id

GENESIS_HASH = "0" * 64
SECRET_KEYS = frozenset(
    {"password", "new_password", "current_password", "password_hash", "token", "token_hash"}
)


@dataclass(frozen=True)
class Actor:
    """Who did it, from where."""

    user_id: str | None
    username: str | None
    request_id: str | None = None
    source_ip: str | None = None


CLI_ACTOR = Actor(user_id=None, username="system:cli")


def scrub(value: Any) -> Any:
    """Return ``value`` as JSON-compatible data with secret keys removed at any depth."""
    plain = to_jsonable_python(value)
    if isinstance(plain, dict):
        return {k: scrub(v) for k, v in plain.items() if k not in SECRET_KEYS}
    if isinstance(plain, list):
        return [scrub(v) for v in plain]
    return plain


def changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Field-level diff ``{field: [old, new]}`` of two JSON snapshots."""
    return {
        key: [before.get(key), after.get(key)]
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def _hashed_fields(event: AuditEvent) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "event_id": event.event_id,
        "ts": format_utc(event.ts),
        "actor_user_id": event.actor_user_id,
        "actor_username": event.actor_username,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "request_id": event.request_id,
        "source_ip": event.source_ip,
        "details": event.details,
        "prev_hash": event.prev_hash,
    }


def compute_hash(event: AuditEvent) -> str:
    """Return the chain hash of ``event`` (its ``hash`` field is not an input)."""
    canonical = json.dumps(
        _hashed_fields(event), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256((event.prev_hash + canonical).encode()).hexdigest()


async def record(
    db: AsyncSession,
    actor: Actor,
    now: datetime,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Append an audit event in the current transaction and return it."""
    last = (
        await db.execute(
            select(AuditEvent.seq, AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)
        )
    ).first()
    event = AuditEvent(
        seq=last.seq + 1 if last else 1,
        event_id=new_id(),
        ts=now,
        actor_user_id=actor.user_id,
        actor_username=actor.username,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=actor.request_id,
        source_ip=actor.source_ip,
        details=scrub(dict(details or {})),
        prev_hash=last.hash if last else GENESIS_HASH,
        hash="",
    )
    event.hash = compute_hash(event)
    db.add(event)
    await db.flush()
    return event


@dataclass(frozen=True)
class ChainReport:
    """Result of verifying the audit chain."""

    ok: bool
    events: int
    head_seq: int | None
    head_hash: str | None
    broken_at_seq: int | None = None
    reason: str | None = None


async def verify_chain(db: AsyncSession, batch_size: int = 1000) -> ChainReport:
    """Re-walk the whole chain; report the first inconsistency, or the head if intact."""
    expected_prev = GENESIS_HASH
    expected_seq: int | None = None
    count = 0
    last_seq = 0
    while True:
        rows = (
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.seq > last_seq)
                .order_by(AuditEvent.seq)
                .limit(batch_size)
            )
        ).all()
        if not rows:
            break
        for event in rows:
            if expected_seq is not None and event.seq != expected_seq:
                return _broken(count, event.seq, f"sequence gap: expected {expected_seq}")
            if event.prev_hash != expected_prev:
                return _broken(count, event.seq, "prev_hash does not match the previous event")
            if compute_hash(event) != event.hash:
                return _broken(count, event.seq, "hash does not match the event's contents")
            expected_prev = event.hash
            expected_seq = event.seq + 1
            last_seq = event.seq
            count += 1
    return ChainReport(
        ok=True,
        events=count,
        head_seq=last_seq if count else None,
        head_hash=expected_prev if count else None,
    )


def _broken(count: int, seq: int, reason: str) -> ChainReport:
    return ChainReport(
        ok=False, events=count, head_seq=None, head_hash=None, broken_at_seq=seq, reason=reason
    )
