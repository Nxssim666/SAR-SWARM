"""
Points of interest of an incident: marked by operators, or survivor sightings reported by
drones (``services.pois``). Operators confirm, dismiss or resolve them; nothing is deleted,
so the record of what was seen and decided stays complete (ADR 0012).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import Field
from sqlalchemy import select

from fleet_service.api.common import (
    InputModel,
    Notes,
    PageParams,
    PatchModel,
    apply_values,
    fetch_page,
    optional,
    page_params,
    patch_values,
)
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.api.helpers import (
    ensure_incident_open,
    ensure_inside_operating_area,
    get_or_404,
)
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Incident, Poi
from fleet_service.domain.enums import PoiKind, PoiStatus
from fleet_service.domain.geo import GeoPoint
from fleet_service.errors import problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit
from fleet_service.services.views import PoiView

router = APIRouter(tags=["pois"], responses=problem_responses(400, 401, 403, 404, 409, 422))

Uncertainty = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=10_000.0)]


class PoiPage(Page[PoiView]):
    """A page of points of interest."""


class PoiCreate(InputModel):
    """A point an operator marks."""

    kind: PoiKind = PoiKind.POI
    position: GeoPoint
    uncertainty_m: Uncertainty | None = None
    notes: Notes | None = None


class PoiUpdate(PatchModel):
    """What operators decide about a point, or add to it."""

    kind: PoiKind = optional()
    status: PoiStatus = optional()
    notes: Notes | None = optional()


def _snapshot(poi: Poi) -> dict[str, object]:
    return PoiView.model_validate(poi).model_dump(mode="json")


@router.get("/incidents/{incident_id}/pois", **requires(Permission.FLEET_VIEW))
async def list_pois(
    incident_id: str,
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    status_filter: Annotated[PoiStatus | None, Query(alias="status")] = None,
) -> PoiPage:
    """An incident's points of interest, optionally by status."""
    await get_or_404(db, Incident, incident_id, "Incident")
    statement = select(Poi).where(Poi.incident_id == incident_id)
    if status_filter is not None:
        statement = statement.where(Poi.status == status_filter)
    rows, cursor = await fetch_page(db, statement, Poi.id, page)
    return PoiPage(items=[PoiView.model_validate(p) for p in rows], next_cursor=cursor)


@router.post(
    "/incidents/{incident_id}/pois",
    status_code=status.HTTP_201_CREATED,
    **requires(Permission.MISSIONS_PLAN),
)
async def create_poi(
    incident_id: str,
    body: PoiCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> PoiView:
    """Mark a point of interest in an open incident."""
    incident = await get_or_404(db, Incident, incident_id, "Incident")
    ensure_incident_open(incident)
    ensure_inside_operating_area(incident, [body.position], "position")
    now = context.clock.now()
    poi = Poi(
        id=new_id(),
        incident_id=incident.id,
        kind=body.kind,
        status=PoiStatus.NEW,
        latitude=body.position.latitude,
        longitude=body.position.longitude,
        uncertainty_m=body.uncertainty_m,
        aircraft_id=None,
        reported_at=None,
        notes=body.notes,
        created_by=principal.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(poi)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "poi.create",
        entity_type="poi",
        entity_id=poi.id,
        details={"after": _snapshot(poi)},
    )
    await db.commit()
    return context.runtime().pois.publish(poi)


@router.get("/pois/{poi_id}", **requires(Permission.FLEET_VIEW))
async def get_poi(poi_id: str, db: DbSession) -> PoiView:
    """One point of interest."""
    return PoiView.model_validate(await get_or_404(db, Poi, poi_id, "Point of interest"))


@router.patch("/pois/{poi_id}", **requires(Permission.MISSIONS_PLAN))
async def update_poi(
    poi_id: str,
    body: PoiUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> PoiView:
    """Confirm, dismiss or resolve a point, change its kind, or add notes."""
    poi = await get_or_404(db, Poi, poi_id, "Point of interest")
    ensure_incident_open(await get_or_404(db, Incident, poi.incident_id, "Incident"))
    before = _snapshot(poi)
    now = context.clock.now()
    apply_values(poi, patch_values(body))
    poi.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "poi.update",
        entity_type="poi",
        entity_id=poi.id,
        details={"changes": audit.changes(before, _snapshot(poi))},
    )
    await db.commit()
    return context.runtime().pois.publish(poi)
