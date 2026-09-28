"""The aircraft registry: identity, airframe and how to reach each aircraft (ADR 0003, 0010)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import AwareDatetime, Field, StringConstraints, field_validator
from sqlalchemy import func, or_, select

from fleet_service.api.common import (
    InputModel,
    Notes,
    OutputModel,
    PageParams,
    PatchModel,
    Speed,
    apply_values,
    fetch_page,
    optional,
    page_params,
    patch_values,
)
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.api.helpers import commit_or_conflict, get_or_404
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Aircraft, Task
from fleet_service.domain.enums import Airframe
from fleet_service.errors import Conflict, problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit

router = APIRouter(
    prefix="/aircraft", tags=["aircraft"], responses=problem_responses(400, 401, 403, 404, 409, 422)
)

Callsign = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,31}$"),
    Field(description="Radio callsign, stored upper-case; unique ignoring case."),
]
MavlinkSystemId = Annotated[int, Field(strict=True, ge=1, le=254)]
MavlinkConnection = Annotated[
    str,
    StringConstraints(
        max_length=200, pattern=r"^(udp|udpin|udpout|tcp|tcpin|tcpout|serial)://\S+$"
    ),
    Field(description="MAVSDK connection string, e.g. udp://:14541 (ADR 0010)."),
]
SwarmDroneId = Annotated[
    int,
    Field(strict=True, ge=0, le=2**31 - 1, description="drone_id in the onboard swarm protocol."),
]


class AircraftOut(OutputModel):
    """A registered aircraft."""

    id: str
    callsign: str
    airframe: Airframe
    mavlink_system_id: int | None
    mavlink_connection: str | None
    swarm_drone_id: int | None
    cruise_speed_mps: float | None
    notes: str | None
    group_ids: list[str]
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def of(cls, aircraft: Aircraft) -> "AircraftOut":
        """Build from a row (group ids come from the membership relationship)."""
        return cls(
            id=aircraft.id,
            callsign=aircraft.callsign,
            airframe=aircraft.airframe,
            mavlink_system_id=aircraft.mavlink_system_id,
            mavlink_connection=aircraft.mavlink_connection,
            swarm_drone_id=aircraft.swarm_drone_id,
            cruise_speed_mps=aircraft.cruise_speed_mps,
            notes=aircraft.notes,
            group_ids=sorted(g.id for g in aircraft.groups),
            created_at=aircraft.created_at,
            updated_at=aircraft.updated_at,
        )


class AircraftPage(Page[AircraftOut]):
    """A page of aircraft."""


class AircraftCreate(InputModel):
    """A new aircraft. Links may be added later; a task needs the matching link (ADR 0003)."""

    callsign: Callsign
    airframe: Airframe
    mavlink_system_id: MavlinkSystemId | None = None
    mavlink_connection: MavlinkConnection | None = None
    swarm_drone_id: SwarmDroneId | None = None
    cruise_speed_mps: Speed | None = None
    notes: Notes | None = None

    @field_validator("callsign")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class AircraftUpdate(PatchModel):
    """Fields to change; ``null`` clears a nullable field."""

    callsign: Callsign = optional()
    airframe: Airframe = optional()
    mavlink_system_id: MavlinkSystemId | None = optional()
    mavlink_connection: MavlinkConnection | None = optional()
    swarm_drone_id: SwarmDroneId | None = optional()
    cruise_speed_mps: Speed | None = optional()
    notes: Notes | None = optional()

    @field_validator("callsign")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


async def _ensure_unique(
    db: DbSession, callsign: str, system_id: int | None, drone_id: int | None, exclude_id: str
) -> None:
    clauses = [Aircraft.callsign == callsign]
    if system_id is not None:
        clauses.append(Aircraft.mavlink_system_id == system_id)
    if drone_id is not None:
        clauses.append(Aircraft.swarm_drone_id == drone_id)
    clash = await db.scalar(select(Aircraft).where(or_(*clauses), Aircraft.id != exclude_id))
    if clash is None:
        return
    if clash.callsign == callsign:
        field, value = "callsign", str(callsign)
    elif system_id is not None and clash.mavlink_system_id == system_id:
        field, value = "mavlink_system_id", str(system_id)
    else:
        field, value = "swarm_drone_id", str(drone_id)
    raise Conflict(
        f"Aircraft {clash.callsign} already uses {field} {value}.",
        slug="aircraft-identity-taken",
        extensions={"field": field},
    )


def _snapshot(aircraft: Aircraft) -> dict[str, object]:
    return AircraftOut.of(aircraft).model_dump(mode="json", exclude={"group_ids"})


@router.get("", **requires(Permission.FLEET_VIEW))
async def list_aircraft(
    db: DbSession, page: Annotated[PageParams, Depends(page_params)]
) -> AircraftPage:
    """List registered aircraft in registration order."""
    rows, cursor = await fetch_page(db, select(Aircraft), Aircraft.id, page)
    return AircraftPage(items=[AircraftOut.of(a) for a in rows], next_cursor=cursor)


@router.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.FLEET_MANAGE))
async def create_aircraft(
    body: AircraftCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> AircraftOut:
    """Register an aircraft."""
    await _ensure_unique(db, body.callsign, body.mavlink_system_id, body.swarm_drone_id, "")
    now = context.clock.now()
    aircraft = Aircraft(id=new_id(), **body.model_dump(), created_at=now, updated_at=now)
    aircraft.groups = []
    db.add(aircraft)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "aircraft.create",
        entity_type="aircraft",
        entity_id=aircraft.id,
        details={"after": _snapshot(aircraft)},
    )
    await commit_or_conflict(db, "The callsign or a link id is already registered.")
    context.runtime().fleet.register(aircraft)
    return AircraftOut.of(aircraft)


@router.get("/{aircraft_id}", **requires(Permission.FLEET_VIEW))
async def get_aircraft(aircraft_id: str, db: DbSession) -> AircraftOut:
    """One aircraft."""
    return AircraftOut.of(await get_or_404(db, Aircraft, aircraft_id, "Aircraft"))


@router.patch("/{aircraft_id}", **requires(Permission.FLEET_MANAGE))
async def update_aircraft(
    aircraft_id: str,
    body: AircraftUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> AircraftOut:
    """Change an aircraft's registration."""
    aircraft = await get_or_404(db, Aircraft, aircraft_id, "Aircraft")
    values = patch_values(body)
    await _ensure_unique(
        db,
        values.get("callsign", aircraft.callsign),
        values.get("mavlink_system_id", aircraft.mavlink_system_id),
        values.get("swarm_drone_id", aircraft.swarm_drone_id),
        aircraft.id,
    )
    before = _snapshot(aircraft)
    now = context.clock.now()
    apply_values(aircraft, values)
    aircraft.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "aircraft.update",
        entity_type="aircraft",
        entity_id=aircraft.id,
        details={"changes": audit.changes(before, _snapshot(aircraft))},
    )
    await commit_or_conflict(db, "The callsign or a link id is already registered.")
    context.runtime().fleet.register(aircraft)
    return AircraftOut.of(aircraft)


@router.delete(
    "/{aircraft_id}", status_code=status.HTTP_204_NO_CONTENT, **requires(Permission.FLEET_MANAGE)
)
async def delete_aircraft(
    aircraft_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Remove an aircraft from the registry; refused while any task refers to it."""
    aircraft = await get_or_404(db, Aircraft, aircraft_id, "Aircraft")
    tasks = await db.scalar(
        select(func.count()).select_from(Task).where(Task.aircraft_id == aircraft.id)
    )
    if tasks:
        raise Conflict(
            f"Aircraft {aircraft.callsign} is assigned to {tasks} task(s); remove them first.",
            slug="aircraft-in-use",
        )
    before = _snapshot(aircraft)
    now = context.clock.now()
    await db.delete(aircraft)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "aircraft.delete",
        entity_type="aircraft",
        entity_id=aircraft_id,
        details={"before": before},
    )
    await commit_or_conflict(
        db, f"Aircraft {aircraft_id} has command history or other references; it is kept."
    )
    runtime = context.runtime()
    runtime.fleet.unregister(aircraft_id)
    runtime.leases.forget(aircraft_id)
