"""
Incidents: the scope of search areas, geofences and missions, with an operating area
(a radius around the base) that every geometry must fit in (ADR 0014).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import AwareDatetime, Field
from sqlalchemy import func, select

from fleet_service.api.common import (
    InputModel,
    Name,
    Notes,
    OutputModel,
    PageParams,
    PatchModel,
    fetch_page,
    optional,
    page_params,
    patch_values,
)
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.api.helpers import ensure_incident_open, get_or_404
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Geofence, Incident, Mission, SearchArea
from fleet_service.domain.enums import INCIDENT_TRANSITIONS, IncidentStatus
from fleet_service.domain.geo import GeoPoint, PolygonGeoJSON, outside_operating_area
from fleet_service.errors import Conflict, problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit

router = APIRouter(
    prefix="/incidents",
    tags=["incidents"],
    responses=problem_responses(400, 401, 403, 404, 409, 422),
)

AltitudeAmsl = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-500.0, le=9000.0)]
OperatingRadius = Annotated[
    float,
    Field(
        strict=True,
        allow_inf_nan=False,
        ge=100.0,
        le=100_000.0,
        description="Every geometry of the incident must lie within this distance of the base.",
    ),
]


class IncidentOut(OutputModel):
    """A SAR incident."""

    id: str
    name: str
    description: str | None
    status: IncidentStatus
    base: GeoPoint
    base_altitude_amsl_m: float | None
    operating_radius_m: float
    created_by: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    closed_at: AwareDatetime | None

    @classmethod
    def of(cls, incident: Incident) -> "IncidentOut":
        """Build from a row."""
        return cls(
            id=incident.id,
            name=incident.name,
            description=incident.description,
            status=incident.status,
            base=GeoPoint(latitude=incident.base_latitude, longitude=incident.base_longitude),
            base_altitude_amsl_m=incident.base_altitude_amsl_m,
            operating_radius_m=incident.operating_radius_m,
            created_by=incident.created_by,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            closed_at=incident.closed_at,
        )


class IncidentPage(Page[IncidentOut]):
    """A page of incidents."""


class IncidentCreate(InputModel):
    """A new incident; it starts ``active``."""

    name: Name
    description: Notes | None = None
    base: GeoPoint
    base_altitude_amsl_m: AltitudeAmsl | None = None
    operating_radius_m: OperatingRadius = 25_000.0


class IncidentUpdate(PatchModel):
    """Fields to change. ``closed`` is terminal; moving the base or shrinking the radius
    is refused while any geometry of the incident would end up outside."""

    name: Name = optional()
    description: Notes | None = optional()
    base: GeoPoint = optional()
    base_altitude_amsl_m: AltitudeAmsl | None = optional()
    operating_radius_m: OperatingRadius = optional()
    status: IncidentStatus = optional()


async def _children_outside(
    db: DbSession, incident_id: str, base: GeoPoint, radius_m: float
) -> list[dict[str, Any]]:
    offending: list[dict[str, Any]] = []
    areas = (
        await db.scalars(select(SearchArea).where(SearchArea.incident_id == incident_id))
    ).all()
    fences = (await db.scalars(select(Geofence).where(Geofence.incident_id == incident_id))).all()
    polygons = [("search_area", a.id, a.geometry) for a in areas] + [
        ("geofence", f.id, f.geometry) for f in fences
    ]
    for entity_type, entity_id, geometry in polygons:
        vertices = PolygonGeoJSON.model_validate(geometry).vertices()
        if outside_operating_area(vertices, base, radius_m):
            offending.append({"entity_type": entity_type, "entity_id": entity_id})
    missions = (await db.scalars(select(Mission).where(Mission.incident_id == incident_id))).all()
    for mission in missions:
        points = [GeoPoint(latitude=w.latitude, longitude=w.longitude) for w in mission.waypoints]
        if outside_operating_area(points, base, radius_m):
            offending.append({"entity_type": "mission", "entity_id": mission.id})
    return offending


@router.get("", **requires(Permission.FLEET_VIEW))
async def list_incidents(
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
) -> IncidentPage:
    """List incidents, optionally by status."""
    statement = select(Incident)
    if status_filter is not None:
        statement = statement.where(Incident.status == status_filter)
    rows, cursor = await fetch_page(db, statement, Incident.id, page)
    return IncidentPage(items=[IncidentOut.of(i) for i in rows], next_cursor=cursor)


@router.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.INCIDENTS_MANAGE))
async def create_incident(
    body: IncidentCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> IncidentOut:
    """Open an incident."""
    now = context.clock.now()
    incident = Incident(
        id=new_id(),
        name=body.name,
        description=body.description,
        status=IncidentStatus.ACTIVE,
        base_latitude=body.base.latitude,
        base_longitude=body.base.longitude,
        base_altitude_amsl_m=body.base_altitude_amsl_m,
        operating_radius_m=body.operating_radius_m,
        created_by=principal.user_id,
        created_at=now,
        updated_at=now,
        closed_at=None,
    )
    db.add(incident)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "incident.create",
        entity_type="incident",
        entity_id=incident.id,
        details={"after": IncidentOut.of(incident).model_dump(mode="json")},
    )
    await db.commit()
    return IncidentOut.of(incident)


@router.get("/{incident_id}", **requires(Permission.FLEET_VIEW))
async def get_incident(incident_id: str, db: DbSession) -> IncidentOut:
    """One incident."""
    return IncidentOut.of(await get_or_404(db, Incident, incident_id, "Incident"))


@router.patch("/{incident_id}", **requires(Permission.INCIDENTS_MANAGE))
async def update_incident(
    incident_id: str,
    body: IncidentUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> IncidentOut:
    """Change an incident's details, operating area or status."""
    incident = await get_or_404(db, Incident, incident_id, "Incident")
    ensure_incident_open(incident)
    values = patch_values(body)
    now = context.clock.now()

    new_status = values.pop("status", incident.status)
    if (
        new_status is not incident.status
        and new_status not in INCIDENT_TRANSITIONS[incident.status]
    ):
        raise Conflict(
            f"An incident cannot go from {incident.status.value} to {new_status.value}.",
            slug="invalid-transition",
        )
    base = values.pop("base", None)
    new_base = base or GeoPoint(latitude=incident.base_latitude, longitude=incident.base_longitude)
    new_radius = values.get("operating_radius_m", incident.operating_radius_m)
    if base is not None or new_radius < incident.operating_radius_m:
        offending = await _children_outside(db, incident.id, new_base, new_radius)
        if offending:
            raise Conflict(
                f"{len(offending)} geometries of this incident would lie outside the new "
                "operating area.",
                slug="children-outside-operating-area",
                extensions={"entities": offending},
            )

    before = IncidentOut.of(incident).model_dump(mode="json")
    for name, value in values.items():
        setattr(incident, name, value)
    incident.base_latitude, incident.base_longitude = new_base.latitude, new_base.longitude
    if new_status is not incident.status:
        incident.status = new_status
        if new_status is IncidentStatus.CLOSED:
            incident.closed_at = now
    incident.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "incident.update",
        entity_type="incident",
        entity_id=incident.id,
        details={
            "changes": audit.changes(before, IncidentOut.of(incident).model_dump(mode="json"))
        },
    )
    await db.commit()
    return IncidentOut.of(incident)


@router.delete(
    "/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    **requires(Permission.INCIDENTS_MANAGE),
)
async def delete_incident(
    incident_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Delete an empty incident (for one opened by mistake); otherwise close it instead."""
    incident = await get_or_404(db, Incident, incident_id, "Incident")
    children = 0
    for model in (SearchArea, Geofence, Mission):
        children += (
            await db.scalar(
                select(func.count()).select_from(model).where(model.incident_id == incident.id)
            )
            or 0
        )
    if children:
        raise Conflict(
            "The incident has search areas, geofences or missions; close it instead.",
            slug="incident-not-empty",
        )
    before = IncidentOut.of(incident).model_dump(mode="json")
    now = context.clock.now()
    await db.delete(incident)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "incident.delete",
        entity_type="incident",
        entity_id=incident_id,
        details={"before": before},
    )
    await db.commit()
