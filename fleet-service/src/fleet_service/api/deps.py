"""
Request dependencies: database session, authenticated principal, permission checks.

Every request uses exactly one ops.db session (FastAPI caches dependencies per
request). With one connection per database file (ADR 0019), a second session in the
same request would wait for the first forever, so never open one.
"""

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.auth.permissions import AUTHENTICATED, Permission
from fleet_service.auth.principal import Principal
from fleet_service.auth.sessions import resolve_session
from fleet_service.bus import SESSIONS
from fleet_service.context import AppContext
from fleet_service.errors import Forbidden, Unauthorized
from fleet_service.services.audit import Actor

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Session token returned by POST /api/v1/auth/login.",
)


def get_context(request: Request) -> AppContext:
    """The application's context."""
    context: AppContext = request.app.state.context
    return context


Context = Annotated[AppContext, Depends(get_context)]


async def get_db(context: Context) -> AsyncIterator[AsyncSession]:
    """The request's ops.db session; uncommitted work is rolled back."""
    async with context.database().ops_session() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_principal(
    context: Context,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    """Resolve the bearer token to a live session, or fail with 401."""
    if credentials is None:
        raise Unauthorized("A bearer token is required.")
    resolved = await resolve_session(
        db, credentials.credentials, context.clock.now(), context.session_policy
    )
    if resolved is None:
        await db.rollback()
        raise Unauthorized("The session is invalid or has expired; log in again.")
    session, user = resolved
    await db.commit()  # persists last_seen_at and ends the transaction before the handler runs
    if context.live is not None:
        context.live.presence.touch(user.id, context.clock.now())
    return Principal(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        session_id=session.id,
        session_expires_at=session.expires_at,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def requires(permission: Permission | None) -> dict[str, Any]:
    """
    Route keyword arguments enforcing ``permission`` (None: any valid session).

    The same value is published as ``x-permission`` in the OpenAPI document, so the
    documented and the enforced permission cannot disagree.
    """

    async def check(principal: CurrentPrincipal) -> None:
        if permission is not None and not principal.can(permission):
            raise Forbidden(
                f"This action requires the {permission.value} permission.",
                extensions={"required_permission": permission.value},
            )

    marker = permission.value if permission is not None else AUTHENTICATED
    return {"dependencies": [Depends(check)], "openapi_extra": {"x-permission": marker}}


def announce_session_end(
    context: AppContext,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    keep_session_id: str | None = None,
) -> None:
    """Close the WebSockets of revoked sessions now, not at their next re-check."""
    if context.live is not None:
        context.live.bus.publish(
            SESSIONS,
            {"session_id": session_id, "user_id": user_id, "keep_session_id": keep_session_id},
        )


def source_ip(request: Request) -> str | None:
    """The client address (behind Caddy, uvicorn's proxy headers set it)."""
    return request.client.host if request.client else None


def actor(request: Request, principal: Principal | None) -> Actor:
    """The audit actor of this request."""
    return Actor(
        user_id=principal.user_id if principal else None,
        username=principal.username if principal else None,
        request_id=getattr(request.state, "request_id", None),
        source_ip=source_ip(request),
    )
