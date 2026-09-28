"""Reading the audit trail (supervisors and admins). Writing happens in each handler."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy import select

from fleet_service.api.common import OutputModel, PageParams, fetch_page, page_params
from fleet_service.api.deps import DbSession, requires
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import AuditEvent
from fleet_service.errors import problem_responses

router = APIRouter(prefix="/audit", tags=["audit"], responses=problem_responses(401, 403, 422))


class AuditEventOut(OutputModel):
    """One audit event, including its chain hashes."""

    seq: int
    event_id: str
    ts: AwareDatetime
    actor_user_id: str | None
    actor_username: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    request_id: str | None
    source_ip: str | None
    details: dict[str, Any]
    prev_hash: str
    hash: str


class AuditPage(Page[AuditEventOut]):
    """A page of audit events, newest first."""


@router.get("", **requires(Permission.AUDIT_READ))
async def list_audit_events(
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    actor_user_id: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[
        str | None, Query(max_length=64, description="Prefix, e.g. 'auth.' or 'mission.update'.")
    ] = None,
    entity_type: Annotated[str | None, Query(max_length=32)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
) -> AuditPage:
    """Search the audit trail, newest first."""
    statement = select(AuditEvent)
    if actor_user_id is not None:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if action is not None:
        statement = statement.where(AuditEvent.action.startswith(action, autoescape=True))
    if entity_type is not None:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(AuditEvent.entity_id == entity_id)
    if since is not None:
        statement = statement.where(AuditEvent.ts >= since)
    if until is not None:
        statement = statement.where(AuditEvent.ts < until)
    rows, cursor = await fetch_page(db, statement, AuditEvent.seq, page, descending=True)
    return AuditPage(items=[AuditEventOut.model_validate(e) for e in rows], next_cursor=cursor)
