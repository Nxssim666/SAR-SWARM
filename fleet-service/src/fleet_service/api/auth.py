"""
Login, logout, current user, own password (ADR 0009).

Failed logins are rate-limited per username and per source address, audited, and
answered with one generic message, in the same time whether or not the user exists.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Request, status
from pydantic import AwareDatetime, BaseModel, StringConstraints
from sqlalchemy import select, update

from fleet_service.api.common import InputModel
from fleet_service.api.deps import (
    Context,
    CurrentPrincipal,
    DbSession,
    actor,
    announce_session_end,
    requires,
    source_ip,
)
from fleet_service.api.users import Password, UserOut
from fleet_service.auth.permissions import Permission, permissions_for
from fleet_service.auth.sessions import create_session, revoke_user_sessions
from fleet_service.db.models import User, UserSession
from fleet_service.errors import Forbidden, TooManyRequests, Unauthorized, problem_responses
from fleet_service.services import audit
from fleet_service.services.audit import Actor

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(InputModel):
    """Credentials. The username is case-insensitive."""

    username: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class LoginResponse(BaseModel):
    """A new session. The token is shown only here; send it as ``Authorization: Bearer``."""

    token: str
    token_type: Literal["bearer"]
    expires_at: AwareDatetime
    user: UserOut
    permissions: list[Permission]


class MeResponse(BaseModel):
    """The current session's user and what they may do."""

    user: UserOut
    permissions: list[Permission]
    session_expires_at: AwareDatetime


class PasswordChange(InputModel):
    """Change one's own password; other sessions of the user are revoked."""

    current_password: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    new_password: Password


@router.post("/login", responses=problem_responses(400, 401, 422, 429))
async def login(
    body: LoginRequest, request: Request, db: DbSession, context: Context
) -> LoginResponse:
    """Exchange a username and password for a session token."""
    username = body.username.lower()
    ip = source_ip(request) or "unknown"
    user_key, ip_key = f"user:{username}", f"ip:{ip}"
    waits = [
        wait
        for wait in (
            context.login_limiter_user.retry_after_s(user_key),
            context.login_limiter_ip.retry_after_s(ip_key),
        )
        if wait is not None
    ]
    if waits:
        raise TooManyRequests("Too many failed logins; try again later.", retry_after_s=max(waits))

    user = await db.scalar(select(User).where(User.username == username))
    await db.commit()  # no transaction open while hashing (ADR 0019)
    if user is None:
        await context.passwords.verify_unknown_user(body.password)
        failure: str | None = "unknown_user"
    elif not await context.passwords.verify(user.password_hash, body.password):
        failure = "bad_password"
    elif not user.is_active:
        failure = "inactive_user"
    else:
        failure = None

    now = context.clock.now()
    request_actor = actor(request, None)
    if failure is not None or user is None:
        context.login_limiter_user.record_failure(user_key)
        context.login_limiter_ip.record_failure(ip_key)
        await audit.record(
            db,
            request_actor,
            now,
            "auth.login_failed",
            details={"username": username, "reason": failure},
        )
        await db.commit()
        raise Unauthorized("Invalid username or password.", slug="invalid-credentials")

    if context.passwords.needs_rehash(user.password_hash):
        user.password_hash = await context.passwords.hash(body.password)
    token, session = await create_session(
        db, user, now, context.session_policy, request.headers.get("user-agent"), ip
    )
    user.last_login_at = now
    await audit.record(
        db,
        Actor(user.id, user.username, request_actor.request_id, ip),
        now,
        "auth.login",
        entity_type="session",
        entity_id=session.id,
    )
    await db.commit()
    context.login_limiter_user.reset(user_key)
    return LoginResponse(
        token=token,
        token_type="bearer",  # noqa: S106 - a scheme name, not a secret
        expires_at=session.expires_at,
        user=UserOut.model_validate(user),
        permissions=permissions_for(user.role),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(401, 403),
    **requires(None),
)
async def logout(
    request: Request, db: DbSession, context: Context, principal: CurrentPrincipal
) -> None:
    """End the current session."""
    now = context.clock.now()
    await db.execute(
        update(UserSession).where(UserSession.id == principal.session_id).values(revoked_at=now)
    )
    await audit.record(
        db,
        actor(request, principal),
        now,
        "auth.logout",
        entity_type="session",
        entity_id=principal.session_id,
    )
    await db.commit()
    announce_session_end(context, session_id=principal.session_id)


@router.get("/me", responses=problem_responses(401, 403), **requires(None))
async def me(db: DbSession, principal: CurrentPrincipal) -> MeResponse:
    """Who am I, and what may I do."""
    user = await db.get(User, principal.user_id)
    if user is None:  # pragma: no cover - sessions of deleted users cannot resolve
        raise Unauthorized("The session's user no longer exists.")
    return MeResponse(
        user=UserOut.model_validate(user),
        permissions=permissions_for(user.role),
        session_expires_at=principal.session_expires_at,
    )


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(400, 401, 403, 422),
    **requires(None),
)
async def change_password(
    body: PasswordChange,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Change one's own password; every other session of this user is revoked."""
    user = await db.get(User, principal.user_id)
    await db.commit()
    if user is None or not await context.passwords.verify(
        user.password_hash, body.current_password
    ):
        now = context.clock.now()
        await audit.record(
            db,
            actor(request, principal),
            now,
            "auth.password_change_failed",
            entity_type="user",
            entity_id=principal.user_id,
        )
        await db.commit()
        raise Forbidden("The current password is incorrect.", slug="invalid-credentials")
    password_hash = await context.passwords.hash(body.new_password)
    now = context.clock.now()
    user.password_hash = password_hash
    user.updated_at = now
    await revoke_user_sessions(db, user.id, now, keep_session_id=principal.session_id)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "auth.password_changed",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()
    announce_session_end(context, user_id=user.id, keep_session_id=principal.session_id)
