"""
Opaque, revocable session tokens (ADR 0009). Only a token's SHA-256 is stored.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.db.models import User, UserSession
from fleet_service.ids import new_id

TOKEN_PREFIX = "sgcs_"  # noqa: S105 - not a secret; makes leaked tokens recognizable to secret scanners
LAST_SEEN_RESOLUTION = timedelta(seconds=60)


def new_token() -> str:
    """Return a new bearer token (256 bits of entropy)."""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the stored form of a token."""
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class SessionPolicy:
    """How long sessions live."""

    idle_timeout: timedelta
    max_lifetime: timedelta


async def create_session(
    db: AsyncSession,
    user: User,
    now: datetime,
    policy: SessionPolicy,
    user_agent: str | None,
    source_ip: str | None,
) -> tuple[str, UserSession]:
    """Create a session for ``user``; return the token (shown once) and the row."""
    token = new_token()
    row = UserSession(
        id=new_id(),
        user_id=user.id,
        token_hash=hash_token(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + policy.max_lifetime,
        revoked_at=None,
        user_agent=user_agent[:256] if user_agent else None,
        source_ip=source_ip,
    )
    db.add(row)
    return token, row


async def resolve_session(
    db: AsyncSession, token: str, now: datetime, policy: SessionPolicy
) -> tuple[UserSession, User] | None:
    """Return the live session and its user for ``token``, or None if invalid or expired."""
    result = await db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == hash_token(token))
    )
    found = result.first()
    if found is None:
        return None
    session, user = found
    if (
        session.revoked_at is not None
        or now >= session.expires_at
        or now >= session.last_seen_at + policy.idle_timeout
        or not user.is_active
    ):
        return None
    if now - session.last_seen_at >= LAST_SEEN_RESOLUTION:
        session.last_seen_at = now
    return session, user


async def revoke_user_sessions(
    db: AsyncSession, user_id: str, now: datetime, keep_session_id: str | None = None
) -> None:
    """Revoke every live session of ``user_id`` except ``keep_session_id``."""
    statement = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if keep_session_id is not None:
        statement = statement.where(UserSession.id != keep_session_id)
    await db.execute(statement)
