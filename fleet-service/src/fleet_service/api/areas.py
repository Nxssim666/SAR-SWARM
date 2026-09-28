"""
Search areas and geofences: incident polygons validated against the operating area.

Both share the rules: the incident must exist and be open, and every vertex must lie
inside the incident's operating area (ADR 0014).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import AwareDatetime, Field
from sqlalchemy import func, select

from fleet_service.api.common import (
    EntityId,
    InputModel,
    Name,
    Notes,
    OutputModel,
    PageParams,
    PatchModel,
    StrictBool,
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
    get_reference,
)
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Geofence, Incident, Mission, SearchArea
from fleet_service.domain.enums import (
    EDITABLE_MISSION_STATUSES,
    GeofenceKind,
    SearchAreaStatus,
)
from fleet_service.domain.geo import PolygonGeoJSON
from fleet_service.errors import Conflict, problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit

search_areas = APIRouter(
    prefix="/search-areas",
    tags=["search areas"],
    responses=problem_responses(400, 401, 403, 404, 409, 422),
)
geofences = APIRouter(
    prefix="/geofences",
    tags=["geofences"],
    responses=problem_responses(400, 401, 403, 404, 409, 422),
)

Priority = Annotated[int, Field(strict=True, ge=1, le=5, description="1 is the highest priority.")]
Ceiling = Annotated[
    float,
    Field(
        strict=True,
        allow_inf_nan=False,
        gt=0.0,
        le=1500.0,
        description="Maximum altitude above each aircraft's home (ADR 0014).",
    ),
]


def _check_geometry(incident: Incident, geometry: PolygonGeoJSON) -> None:
    ensure_inside_operating_area(incident, geometry.vertices(), "vertices")


# --- search areas ---------------------------------------------------------------------------


class SearchAreaOut(OutputModel):
    """An area to be searched."""

    id: str
    incident_id: str
    name: str
    geometry: PolygonGeoJSON
    area_m2: float
    priority: int
    status: SearchAreaStatus
    notes: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SearchAreaPage(Page[SearchAreaOut]):
    """A page of search areas."""


class SearchAreaCreate(InputModel):
    """A new search area; it starts ``unassigned``."""

    incident_id: EntityId
    name: Name
    geometry: PolygonGeoJSON
    priority: Priority = 3
    notes: Notes | None = None


class SearchAreaUpdate(PatchModel):
    """Fields to change. The geometry is frozen while a running mission uses the area."""

    name: Name = optional()
    geometry: PolygonGeoJSON = optional()
    priority: Priority = optional()
    status: SearchAreaStatus = optional()
    notes: Notes | None = optional()


def _area_snapshot(area: SearchArea) -> dict[str, object]:
    return SearchAreaOut.model_validate(area).model_dump(mode="json")


@search_areas.get("", **requires(Permission.FLEET_VIEW))
async def list_search_areas(
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    incident_id: Annotated[str | None, Query(max_length=64)] = None,
) -> SearchAreaPage:
    """List search areas, optionally of one incident."""
    statement = select(SearchArea)
    if incident_id is not None:
        statement = statement.where(SearchArea.incident_id == incident_id)
    rows, cursor = await fetch_page(db, statement, SearchArea.id, page)
    return SearchAreaPage(items=[SearchAreaOut.model_validate(a) for a in rows], next_cursor=cursor)


@search_areas.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.MISSIONS_PLAN))
async def create_search_area(
    body: SearchAreaCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> SearchAreaOut:
    """Define a search area inside an open incident's operating area."""
    incident = await get_reference(db, Incident, body.incident_id, "incident_id")
    ensure_incident_open(incident)
    _check_geometry(incident, body.geometry)
    now = context.clock.now()
    area = SearchArea(
        id=new_id(),
        incident_id=incident.id,
        name=body.name,
        geometry=body.geometry.model_dump(mode="json"),
        area_m2=body.geometry.area_m2(),
        priority=body.priority,
        status=SearchAreaStatus.UNASSIGNED,
        notes=body.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(area)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "search_area.create",
        entity_type="search_area",
        entity_id=area.id,
        details={"after": _area_snapshot(area)},
    )
    await db.commit()
    return SearchAreaOut.model_validate(area)


@search_areas.get("/{area_id}", **requires(Permission.FLEET_VIEW))
async def get_search_area(area_id: str, db: DbSession) -> SearchAreaOut:
    """One search area."""
    return SearchAreaOut.model_validate(await get_or_404(db, SearchArea, area_id, "Search area"))


@search_areas.patch("/{area_id}", **requires(Permission.MISSIONS_PLAN))
async def update_search_area(
    area_id: str,
    body: SearchAreaUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> SearchAreaOut:
    """Change a search area; ground teams' results can be recorded through ``status``."""
    area = await get_or_404(db, SearchArea, area_id, "Search area")
    incident = await get_or_404(db, Incident, area.incident_id, "Incident")
    ensure_incident_open(incident)
    values = patch_values(body)
    before = _area_snapshot(area)
    if "geometry" in values:
        geometry: PolygonGeoJSON = values.pop("geometry")
        _check_geometry(incident, geometry)
        running = await db.scalar(
            select(func.count())
            .select_from(Mission)
            .where(
                Mission.search_area_id == area.id,
                Mission.status.not_in(EDITABLE_MISSION_STATUSES),
            )
        )
        if running:
            raise Conflict(
                "A mission that is running or finished uses this area; its geometry is frozen.",
                slug="area-in-use",
            )
        area.geometry = geometry.model_dump(mode="json")
        area.area_m2 = geometry.area_m2()
    now = context.clock.now()
    apply_values(area, values)
    area.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "search_area.update",
        entity_type="search_area",
        entity_id=area.id,
        details={"changes": audit.changes(before, _area_snapshot(area))},
    )
    await db.commit()
    return SearchAreaOut.model_validate(area)


@search_areas.delete(
    "/{area_id}", status_code=status.HTTP_204_NO_CONTENT, **requires(Permission.MISSIONS_PLAN)
)
async def delete_search_area(
    area_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Delete a search area that no mission uses."""
    area = await get_or_404(db, SearchArea, area_id, "Search area")
    ensure_incident_open(await get_or_404(db, Incident, area.incident_id, "Incident"))
    if await db.scalar(
        select(func.count()).select_from(Mission).where(Mission.search_area_id == area.id)
    ):
        raise Conflict("Missions use this search area; delete them first.", slug="area-in-use")
    before = _area_snapshot(area)
    now = context.clock.now()
    await db.delete(area)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "search_area.delete",
        entity_type="search_area",
        entity_id=area_id,
        details={"before": before},
    )
    await db.commit()


# --- geofences ---------------------------------------------------------------------------------


class GeofenceOut(OutputModel):
    """An inclusion or exclusion zone."""

    id: str
    incident_id: str
    name: str
    kind: GeofenceKind
    geometry: PolygonGeoJSON
    max_altitude_relative_m: float | None
    enabled: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime


class GeofencePage(Page[GeofenceOut]):
    """A page of geofences."""


class GeofenceCreate(InputModel):
    """A new geofence."""

    incident_id: EntityId
    name: Name
    kind: GeofenceKind
    geometry: PolygonGeoJSON
    max_altitude_relative_m: Ceiling | None = None
    enabled: StrictBool = True


class GeofenceUpdate(PatchModel):
    """Fields to change."""

    name: Name = optional()
    kind: GeofenceKind = optional()
    geometry: PolygonGeoJSON = optional()
    max_altitude_relative_m: Ceiling | None = optional()
    enabled: StrictBool = optional()


def _fence_snapshot(fence: Geofence) -> dict[str, object]:
    return GeofenceOut.model_validate(fence).model_dump(mode="json")


@geofences.get("", **requires(Permission.FLEET_VIEW))
async def list_geofences(
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    incident_id: Annotated[str | None, Query(max_length=64)] = None,
) -> GeofencePage:
    """List geofences, optionally of one incident."""
    statement = select(Geofence)
    if incident_id is not None:
        statement = statement.where(Geofence.incident_id == incident_id)
    rows, cursor = await fetch_page(db, statement, Geofence.id, page)
    return GeofencePage(items=[GeofenceOut.model_validate(g) for g in rows], next_cursor=cursor)


@geofences.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.GEOFENCES_MANAGE))
async def create_geofence(
    body: GeofenceCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> GeofenceOut:
    """Define a geofence inside an open incident's operating area."""
    incident = await get_reference(db, Incident, body.incident_id, "incident_id")
    ensure_incident_open(incident)
    _check_geometry(incident, body.geometry)
    now = context.clock.now()
    fence = Geofence(
        id=new_id(),
        incident_id=incident.id,
        name=body.name,
        kind=body.kind,
        geometry=body.geometry.model_dump(mode="json"),
        max_altitude_relative_m=body.max_altitude_relative_m,
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )
    db.add(fence)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "geofence.create",
        entity_type="geofence",
        entity_id=fence.id,
        details={"after": _fence_snapshot(fence)},
    )
    await db.commit()
    return GeofenceOut.model_validate(fence)


@geofences.get("/{geofence_id}", **requires(Permission.FLEET_VIEW))
async def get_geofence(geofence_id: str, db: DbSession) -> GeofenceOut:
    """One geofence."""
    return GeofenceOut.model_validate(await get_or_404(db, Geofence, geofence_id, "Geofence"))


@geofences.patch("/{geofence_id}", **requires(Permission.GEOFENCES_MANAGE))
async def update_geofence(
    geofence_id: str,
    body: GeofenceUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> GeofenceOut:
    """Change a geofence."""
    fence = await get_or_404(db, Geofence, geofence_id, "Geofence")
    incident = await get_or_404(db, Incident, fence.incident_id, "Incident")
    ensure_incident_open(incident)
    values = patch_values(body)
    before = _fence_snapshot(fence)
    if "geometry" in values:
        geometry: PolygonGeoJSON = values.pop("geometry")
        _check_geometry(incident, geometry)
        fence.geometry = geometry.model_dump(mode="json")
    now = context.clock.now()
    apply_values(fence, values)
    fence.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "geofence.update",
        entity_type="geofence",
        entity_id=fence.id,
        details={"changes": audit.changes(before, _fence_snapshot(fence))},
    )
    await db.commit()
    return GeofenceOut.model_validate(fence)


@geofences.delete(
    "/{geofence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    **requires(Permission.GEOFENCES_MANAGE),
)
async def delete_geofence(
    geofence_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Delete a geofence."""
    fence = await get_or_404(db, Geofence, geofence_id, "Geofence")
    ensure_incident_open(await get_or_404(db, Incident, fence.incident_id, "Incident"))
    before = _fence_snapshot(fence)
    now = context.clock.now()
    await db.delete(fence)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "geofence.delete",
        entity_type="geofence",
        entity_id=geofence_id,
        details={"before": before},
    )
    await db.commit()
