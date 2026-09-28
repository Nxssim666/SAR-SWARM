"""Alerts: list the history, acknowledge the open ones."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from fleet_service.api.common import PageParams, fetch_page, page_params
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Alert
from fleet_service.domain.enums import AlertState
from fleet_service.errors import problem_responses
from fleet_service.services.views import AlertView

router = APIRouter(
    prefix="/alerts", tags=["alerts"], responses=problem_responses(400, 401, 403, 404, 409, 422)
)


class AlertPage(Page[AlertView]):
    """A page of alerts, newest first."""


@router.get("", **requires(Permission.FLEET_VIEW))
async def list_alerts(
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    state: Annotated[AlertState | None, Query()] = None,
    aircraft_id: Annotated[str | None, Query(max_length=64)] = None,
) -> AlertPage:
    """Alerts, newest first; filter by state (e.g. ``active``) and aircraft."""
    statement = select(Alert)
    if state is not None:
        statement = statement.where(Alert.state == state)
    if aircraft_id is not None:
        statement = statement.where(Alert.aircraft_id == aircraft_id)
    rows, cursor = await fetch_page(db, statement, Alert.id, page, descending=True)
    return AlertPage(items=[AlertView.model_validate(a) for a in rows], next_cursor=cursor)


@router.post("/{alert_id}/acknowledge", **requires(Permission.ALERTS_ACK))
async def acknowledge_alert(
    alert_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> AlertView:
    """Mark an alert as seen. Event alerts (e.g. a command timeout) are closed by this."""
    view = await context.runtime().alerts.acknowledge(
        db, context.clock.now(), alert_id, actor(request, principal)
    )
    await db.commit()
    return view
