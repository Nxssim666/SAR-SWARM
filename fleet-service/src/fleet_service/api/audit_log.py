"""
Reading the audit trail (supervisors and admins). Writing happens in each handler.

Besides searching, supervisors can verify the hash chain (the same check as
``fleet-service audit-verify``) and export events as CSV or JSON Lines; an export takes
the trail off the station, so it is itself audited (M5).
"""

import csv
import io
import json
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AwareDatetime, Field
from sqlalchemy import Select, select

from fleet_service.api.common import OutputModel, PageParams, fetch_page, page_params
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import AuditEvent
from fleet_service.errors import InvalidRequest, problem_responses
from fleet_service.services import audit, audit_heads

MAX_EXPORT_EVENTS = 100_000

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


class AuditFilters:
    """The search filters shared by listing and exporting."""

    def __init__(
        self,
        actor_user_id: Annotated[str | None, Query(max_length=64)] = None,
        action: Annotated[
            str | None,
            Query(max_length=64, description="Prefix, e.g. 'auth.' or 'mission.update'."),
        ] = None,
        entity_type: Annotated[str | None, Query(max_length=32)] = None,
        entity_id: Annotated[str | None, Query(max_length=64)] = None,
        since: AwareDatetime | None = None,
        until: AwareDatetime | None = None,
    ) -> None:
        self.actor_user_id = actor_user_id
        self.action = action
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.since = since
        self.until = until

    def apply(self, statement: Select[tuple[AuditEvent]]) -> Select[tuple[AuditEvent]]:
        """Narrow ``statement`` to the events these filters select."""
        if self.actor_user_id is not None:
            statement = statement.where(AuditEvent.actor_user_id == self.actor_user_id)
        if self.action is not None:
            statement = statement.where(AuditEvent.action.startswith(self.action, autoescape=True))
        if self.entity_type is not None:
            statement = statement.where(AuditEvent.entity_type == self.entity_type)
        if self.entity_id is not None:
            statement = statement.where(AuditEvent.entity_id == self.entity_id)
        if self.since is not None:
            statement = statement.where(AuditEvent.ts >= self.since)
        if self.until is not None:
            statement = statement.where(AuditEvent.ts < self.until)
        return statement

    def described(self) -> dict[str, str]:
        """The filters in use, for the export's own audit event."""
        values = {
            "actor_user_id": self.actor_user_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
        }
        return {k: v for k, v in values.items() if v is not None}


Filters = Annotated[AuditFilters, Depends()]


@router.get("", **requires(Permission.AUDIT_READ))
async def list_audit_events(
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    filters: Filters,
) -> AuditPage:
    """Search the audit trail, newest first."""
    statement = filters.apply(select(AuditEvent))
    rows, cursor = await fetch_page(db, statement, AuditEvent.seq, page, descending=True)
    return AuditPage(items=[AuditEventOut.model_validate(e) for e in rows], next_cursor=cursor)


class ChainStatus(OutputModel):
    """Whether the audit hash chain is intact, and its head (to record elsewhere)."""

    ok: bool
    events: int
    head_seq: int | None
    head_hash: str | None
    broken_at_seq: int | None
    reason: str | None
    exported_heads: int = Field(
        description="Heads recorded outside the database (M6); each was found in the chain "
        "unless ``reason`` says otherwise."
    )
    verified_at: AwareDatetime


@router.get("/verify", **requires(Permission.AUDIT_READ))
async def verify_audit_chain(db: DbSession, context: Context) -> ChainStatus:
    """Re-walk the whole chain: the first inconsistency, or the head if intact. The heads
    exported outside the database must all still be in it (truncation, M6)."""
    report = await audit.verify_chain(db)
    heads = await audit_heads.check_heads(db, context.settings.audit_heads_path)
    return ChainStatus(
        ok=report.ok and heads.problem is None,
        events=report.events,
        head_seq=report.head_seq,
        head_hash=report.head_hash,
        broken_at_seq=report.broken_at_seq,
        reason=report.reason or heads.problem,
        exported_heads=heads.heads,
        verified_at=context.clock.now(),
    )


class ExportFormat(StrEnum):
    """Audit export formats."""

    CSV = "csv"
    JSONL = "jsonl"


CSV_COLUMNS = [
    "seq",
    "event_id",
    "ts",
    "actor_user_id",
    "actor_username",
    "action",
    "entity_type",
    "entity_id",
    "request_id",
    "source_ip",
    "details",
    "prev_hash",
    "hash",
]


@router.get(
    "/export",
    **requires(Permission.AUDIT_READ),
    response_class=Response,
    responses={
        200: {
            "description": "The selected events, oldest first, with their chain hashes.",
            "content": {
                "text/csv": {"schema": {"type": "string"}},
                "application/x-ndjson": {"schema": {"type": "string"}},
            },
        }
    },
)
async def export_audit_events(
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
    filters: Filters,
    format: ExportFormat = ExportFormat.CSV,
) -> Response:
    """Export the selected events (oldest first); the export itself is audited."""
    statement = filters.apply(select(AuditEvent)).order_by(AuditEvent.seq)
    rows = (await db.scalars(statement.limit(MAX_EXPORT_EVENTS + 1))).all()
    if len(rows) > MAX_EXPORT_EVENTS:
        raise InvalidRequest(
            f"More than {MAX_EXPORT_EVENTS} events match: narrow the filters (e.g. by time).",
            slug="export-too-large",
        )
    events = [AuditEventOut.model_validate(e).model_dump(mode="json") for e in rows]
    now = context.clock.now()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "audit.export",
        details={"format": format.value, "events": len(events), "filters": filters.described()},
    )
    await db.commit()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    if format is ExportFormat.JSONL:
        body = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events)
        media, extension = "application/x-ndjson", "jsonl"
    else:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for e in events:
            writer.writerow({**e, "details": json.dumps(e["details"], ensure_ascii=False)})
        body, media, extension = buffer.getvalue(), "text/csv", "csv"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="audit-{stamp}.{extension}"'},
    )
