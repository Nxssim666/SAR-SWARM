"""
Missions, their waypoints, and tasks (aircraft assigned to a mission).

Planning happens in ``draft`` and ``planned``; from ``active`` on, execution (M1b/M4)
owns the mission and the plan is frozen. Swarm missions follow the onboard protocol's
limits (ADR 0003).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select

from fleet_service.api.common import (
    AltitudeRelative,
    EntityId,
    InputModel,
    Name,
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
from fleet_service.api.helpers import (
    commit_or_conflict,
    ensure_incident_open,
    ensure_inside_operating_area,
    get_or_404,
    get_reference,
)
from fleet_service.api.pages import Page
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Aircraft, Incident, Mission, SearchArea, Task, Waypoint
from fleet_service.domain.enums import (
    EDITABLE_MISSION_STATUSES,
    MAX_MISSION_WAYPOINTS,
    MAX_SWARM_MISSION_WAYPOINTS,
    MISSION_REST_TRANSITIONS,
    TASK_REST_TRANSITIONS,
    MissionKind,
    MissionStatus,
    TaskStatus,
)
from fleet_service.domain.geo import GeoPoint, Latitude, Longitude
from fleet_service.errors import Conflict, InvalidRequest, problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit

missions = APIRouter(
    prefix="/missions", tags=["missions"], responses=problem_responses(400, 401, 403, 404, 409, 422)
)
tasks = APIRouter(
    prefix="/tasks", tags=["tasks"], responses=problem_responses(400, 401, 403, 404, 409, 422)
)

DefaultAltitude = Annotated[
    float,
    Field(
        strict=True,
        allow_inf_nan=False,
        gt=0.0,
        le=1500.0,
        description="Default altitude above each aircraft's home (ADR 0014).",
    ),
]
Seconds = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=86_400.0)]
NEEDS_SEARCH_AREA = frozenset({MissionKind.AREA_SEARCH, MissionKind.SWARM_AREA})


# --- models ----------------------------------------------------------------------------------


class MissionOut(OutputModel):
    """A mission."""

    id: str
    incident_id: str
    name: str
    kind: MissionKind
    status: MissionStatus
    search_area_id: str | None
    default_altitude_relative_m: float
    default_speed_mps: float | None
    notes: str | None
    waypoint_count: int
    created_by: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @classmethod
    def of(cls, mission: Mission) -> "MissionOut":
        """Build from a row."""
        return cls(
            id=mission.id,
            incident_id=mission.incident_id,
            name=mission.name,
            kind=mission.kind,
            status=mission.status,
            search_area_id=mission.search_area_id,
            default_altitude_relative_m=mission.default_altitude_relative_m,
            default_speed_mps=mission.default_speed_mps,
            notes=mission.notes,
            waypoint_count=len(mission.waypoints),
            created_by=mission.created_by,
            created_at=mission.created_at,
            updated_at=mission.updated_at,
        )


class MissionPage(Page[MissionOut]):
    """A page of missions."""


class MissionCreate(InputModel):
    """A new mission; it starts as ``draft``. Area missions need a search area."""

    incident_id: EntityId
    name: Name
    kind: MissionKind
    search_area_id: EntityId | None = None
    default_altitude_relative_m: DefaultAltitude
    default_speed_mps: Speed | None = None
    notes: Notes | None = None


class MissionUpdate(PatchModel):
    """Fields to change. Plan fields change only in draft/planned; ``status`` may go
    draft↔planned or to aborted."""

    name: Name = optional()
    notes: Notes | None = optional()
    search_area_id: EntityId | None = optional()
    default_altitude_relative_m: DefaultAltitude = optional()
    default_speed_mps: Speed | None = optional()
    status: MissionStatus = optional()


class WaypointIn(InputModel):
    """One route point."""

    latitude: Latitude
    longitude: Longitude
    altitude_relative_m: AltitudeRelative
    speed_mps: Speed | None = None
    loiter_s: (
        Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=3600.0)] | None
    ) = None


class WaypointOut(OutputModel):
    """One route point and its position in the route."""

    seq: int
    latitude: float
    longitude: float
    altitude_relative_m: float
    speed_mps: float | None
    loiter_s: float | None


class WaypointsIn(InputModel):
    """The complete, ordered route (replaces the previous one)."""

    waypoints: list[WaypointIn] = Field(max_length=MAX_MISSION_WAYPOINTS)


class WaypointsOut(BaseModel):
    """A mission's route."""

    mission_id: str
    waypoints: list[WaypointOut]


class TaskOut(OutputModel):
    """An aircraft's assignment to a mission."""

    id: str
    mission_id: str
    aircraft_id: str
    status: TaskStatus
    altitude_relative_m: float | None
    speed_mps: float | None
    start_delay_s: float | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class TaskPage(Page[TaskOut]):
    """A page of tasks."""


class TaskCreate(InputModel):
    """Assign an aircraft to a mission, optionally overriding its defaults."""

    mission_id: EntityId
    aircraft_id: EntityId
    altitude_relative_m: AltitudeRelative | None = None
    speed_mps: Speed | None = None
    start_delay_s: Seconds | None = None


class TaskUpdate(PatchModel):
    """Overrides change only while the mission is being planned; ``status`` may go to cancelled."""

    altitude_relative_m: AltitudeRelative | None = optional()
    speed_mps: Speed | None = optional()
    start_delay_s: Seconds | None = optional()
    status: TaskStatus = optional()


# --- rules -----------------------------------------------------------------------------------


def _ensure_editable(mission: Mission) -> None:
    if mission.status not in EDITABLE_MISSION_STATUSES:
        raise Conflict(
            f"Mission {mission.id} is {mission.status.value}; its plan can no longer change.",
            slug="mission-not-editable",
        )


async def _check_search_area(
    db: DbSession, kind: MissionKind, incident_id: str, search_area_id: str | None
) -> None:
    if search_area_id is None:
        if kind in NEEDS_SEARCH_AREA:
            raise InvalidRequest(
                f"A {kind.value} mission needs a search_area_id.", slug="search-area-required"
            )
        return
    area = await get_reference(db, SearchArea, search_area_id, "search_area_id")
    if area.incident_id != incident_id:
        raise InvalidRequest(
            "The search area belongs to another incident.",
            slug="reference-mismatch",
            extensions={"field": "search_area_id"},
        )


def _compatible(kind: MissionKind, aircraft: Aircraft) -> bool:
    if kind is MissionKind.SWARM_AREA:
        return aircraft.swarm_drone_id is not None
    return aircraft.mavlink_system_id is not None


async def _mission_context(db: DbSession, mission_id: str) -> tuple[Mission, Incident]:
    mission = await get_or_404(db, Mission, mission_id, "Mission")
    incident = await get_or_404(db, Incident, mission.incident_id, "Incident")
    return mission, incident


def _mission_snapshot(mission: Mission) -> dict[str, object]:
    return MissionOut.of(mission).model_dump(mode="json")


def _task_snapshot(task: Task) -> dict[str, object]:
    return TaskOut.model_validate(task).model_dump(mode="json")


# --- missions ---------------------------------------------------------------------------------


@missions.get("", **requires(Permission.FLEET_VIEW))
async def list_missions(
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    incident_id: Annotated[str | None, Query(max_length=64)] = None,
    status_filter: Annotated[MissionStatus | None, Query(alias="status")] = None,
) -> MissionPage:
    """List missions, optionally by incident and status."""
    statement = select(Mission)
    if incident_id is not None:
        statement = statement.where(Mission.incident_id == incident_id)
    if status_filter is not None:
        statement = statement.where(Mission.status == status_filter)
    rows, cursor = await fetch_page(db, statement, Mission.id, page)
    return MissionPage(items=[MissionOut.of(m) for m in rows], next_cursor=cursor)


@missions.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.MISSIONS_PLAN))
async def create_mission(
    body: MissionCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> MissionOut:
    """Create a draft mission in an open incident."""
    incident = await get_reference(db, Incident, body.incident_id, "incident_id")
    ensure_incident_open(incident)
    await _check_search_area(db, body.kind, incident.id, body.search_area_id)
    now = context.clock.now()
    mission = Mission(
        id=new_id(),
        **body.model_dump(),
        status=MissionStatus.DRAFT,
        created_by=principal.user_id,
        created_at=now,
        updated_at=now,
    )
    mission.waypoints = []
    db.add(mission)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "mission.create",
        entity_type="mission",
        entity_id=mission.id,
        details={"after": _mission_snapshot(mission)},
    )
    await db.commit()
    return MissionOut.of(mission)


@missions.get("/{mission_id}", **requires(Permission.FLEET_VIEW))
async def get_mission(mission_id: str, db: DbSession) -> MissionOut:
    """One mission."""
    return MissionOut.of(await get_or_404(db, Mission, mission_id, "Mission"))


@missions.patch("/{mission_id}", **requires(Permission.MISSIONS_PLAN))
async def update_mission(
    mission_id: str,
    body: MissionUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> MissionOut:
    """Change a mission's plan, name or planning status."""
    mission, incident = await _mission_context(db, mission_id)
    ensure_incident_open(incident)
    values = patch_values(body)
    plan_fields = {"search_area_id", "default_altitude_relative_m", "default_speed_mps"}
    if plan_fields & set(values):
        _ensure_editable(mission)
    if "search_area_id" in values:
        await _check_search_area(db, mission.kind, incident.id, values["search_area_id"])
    new_status = values.pop("status", mission.status)
    if new_status is not mission.status and new_status not in MISSION_REST_TRANSITIONS.get(
        mission.status, frozenset()
    ):
        raise Conflict(
            f"A mission cannot be moved from {mission.status.value} to {new_status.value} "
            "through the API.",
            slug="invalid-transition",
        )
    before = _mission_snapshot(mission)
    now = context.clock.now()
    apply_values(mission, values)
    mission.status = new_status
    mission.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "mission.update",
        entity_type="mission",
        entity_id=mission.id,
        details={"changes": audit.changes(before, _mission_snapshot(mission))},
    )
    await db.commit()
    return MissionOut.of(mission)


@missions.delete(
    "/{mission_id}", status_code=status.HTTP_204_NO_CONTENT, **requires(Permission.MISSIONS_PLAN)
)
async def delete_mission(
    mission_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Delete a draft mission with its waypoints and tasks; later missions are aborted instead."""
    mission, incident = await _mission_context(db, mission_id)
    ensure_incident_open(incident)
    if mission.status is not MissionStatus.DRAFT:
        raise Conflict(
            f"Only draft missions can be deleted; this one is {mission.status.value}.",
            slug="mission-not-deletable",
        )
    before = _mission_snapshot(mission)
    now = context.clock.now()
    await db.delete(mission)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "mission.delete",
        entity_type="mission",
        entity_id=mission_id,
        details={"before": before},
    )
    await db.commit()


@missions.get("/{mission_id}/waypoints", **requires(Permission.FLEET_VIEW))
async def get_waypoints(mission_id: str, db: DbSession) -> WaypointsOut:
    """A mission's route, in order."""
    mission = await get_or_404(db, Mission, mission_id, "Mission")
    return WaypointsOut(
        mission_id=mission.id,
        waypoints=[WaypointOut.model_validate(w) for w in mission.waypoints],
    )


@missions.put("/{mission_id}/waypoints", **requires(Permission.MISSIONS_PLAN))
async def replace_waypoints(
    mission_id: str,
    body: WaypointsIn,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> WaypointsOut:
    """Replace a mission's whole route atomically."""
    mission, incident = await _mission_context(db, mission_id)
    ensure_incident_open(incident)
    _ensure_editable(mission)
    if mission.kind is MissionKind.SWARM_AREA and len(body.waypoints) > MAX_SWARM_MISSION_WAYPOINTS:
        raise InvalidRequest(
            f"Swarm missions take at most {MAX_SWARM_MISSION_WAYPOINTS} transit waypoints "
            "(onboard protocol limit).",
            slug="too-many-waypoints",
        )
    ensure_inside_operating_area(
        incident,
        [GeoPoint(latitude=w.latitude, longitude=w.longitude) for w in body.waypoints],
        "waypoints",
    )
    before_count = len(mission.waypoints)
    mission.waypoints.clear()
    await db.flush()  # delete the old route first: (mission_id, seq) is unique
    mission.waypoints.extend(
        Waypoint(id=new_id(), mission_id=mission.id, seq=seq, **w.model_dump())
        for seq, w in enumerate(body.waypoints)
    )
    now = context.clock.now()
    mission.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "mission.waypoints_replace",
        entity_type="mission",
        entity_id=mission.id,
        details={"before_count": before_count, "after_count": len(body.waypoints)},
    )
    await db.commit()
    return WaypointsOut(
        mission_id=mission.id,
        waypoints=[WaypointOut.model_validate(w) for w in mission.waypoints],
    )


# --- tasks --------------------------------------------------------------------------------------


@tasks.get("", **requires(Permission.FLEET_VIEW))
async def list_tasks(
    db: DbSession,
    page: Annotated[PageParams, Depends(page_params)],
    mission_id: Annotated[str | None, Query(max_length=64)] = None,
    aircraft_id: Annotated[str | None, Query(max_length=64)] = None,
) -> TaskPage:
    """List tasks, optionally by mission and aircraft."""
    statement = select(Task)
    if mission_id is not None:
        statement = statement.where(Task.mission_id == mission_id)
    if aircraft_id is not None:
        statement = statement.where(Task.aircraft_id == aircraft_id)
    rows, cursor = await fetch_page(db, statement, Task.id, page)
    return TaskPage(items=[TaskOut.model_validate(t) for t in rows], next_cursor=cursor)


@tasks.post("", status_code=status.HTTP_201_CREATED, **requires(Permission.MISSIONS_PLAN))
async def create_task(
    body: TaskCreate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> TaskOut:
    """Assign an aircraft to a mission that is being planned."""
    mission = await get_reference(db, Mission, body.mission_id, "mission_id")
    aircraft = await get_reference(db, Aircraft, body.aircraft_id, "aircraft_id")
    ensure_incident_open(await get_or_404(db, Incident, mission.incident_id, "Incident"))
    _ensure_editable(mission)
    if not _compatible(mission.kind, aircraft):
        needed = "swarm_drone_id" if mission.kind is MissionKind.SWARM_AREA else "mavlink_system_id"
        raise Conflict(
            f"Aircraft {aircraft.callsign} has no {needed}; it cannot fly a "
            f"{mission.kind.value} mission (ADR 0003).",
            slug="aircraft-incompatible",
        )
    if await db.scalar(
        select(Task.id).where(Task.mission_id == mission.id, Task.aircraft_id == aircraft.id)
    ):
        raise Conflict(
            f"Aircraft {aircraft.callsign} is already assigned to this mission.",
            slug="task-exists",
        )
    now = context.clock.now()
    task = Task(
        id=new_id(),
        **body.model_dump(),
        status=TaskStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "task.create",
        entity_type="task",
        entity_id=task.id,
        details={"after": _task_snapshot(task)},
    )
    await commit_or_conflict(db, "The aircraft is already assigned to this mission.")
    return TaskOut.model_validate(task)


@tasks.get("/{task_id}", **requires(Permission.FLEET_VIEW))
async def get_task(task_id: str, db: DbSession) -> TaskOut:
    """One task."""
    return TaskOut.model_validate(await get_or_404(db, Task, task_id, "Task"))


@tasks.patch("/{task_id}", **requires(Permission.MISSIONS_PLAN))
async def update_task(
    task_id: str,
    body: TaskUpdate,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> TaskOut:
    """Change a task's overrides, or cancel it."""
    task = await get_or_404(db, Task, task_id, "Task")
    mission, incident = await _mission_context(db, task.mission_id)
    ensure_incident_open(incident)
    values = patch_values(body)
    new_status = values.pop("status", task.status)
    if values:
        _ensure_editable(mission)
    if new_status is not task.status and new_status not in TASK_REST_TRANSITIONS.get(
        task.status, frozenset()
    ):
        raise Conflict(
            f"A task cannot be moved from {task.status.value} to {new_status.value} "
            "through the API.",
            slug="invalid-transition",
        )
    before = _task_snapshot(task)
    now = context.clock.now()
    apply_values(task, values)
    task.status = new_status
    task.updated_at = now
    await db.flush()
    await audit.record(
        db,
        actor(request, principal),
        now,
        "task.update",
        entity_type="task",
        entity_id=task.id,
        details={"changes": audit.changes(before, _task_snapshot(task))},
    )
    await db.commit()
    return TaskOut.model_validate(task)


@tasks.delete(
    "/{task_id}", status_code=status.HTTP_204_NO_CONTENT, **requires(Permission.MISSIONS_PLAN)
)
async def delete_task(
    task_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> None:
    """Remove an assignment while the mission is being planned."""
    task = await get_or_404(db, Task, task_id, "Task")
    mission, incident = await _mission_context(db, task.mission_id)
    ensure_incident_open(incident)
    _ensure_editable(mission)
    before = _task_snapshot(task)
    now = context.clock.now()
    await db.delete(task)
    await audit.record(
        db,
        actor(request, principal),
        now,
        "task.delete",
        entity_type="task",
        entity_id=task_id,
        details={"before": before},
    )
    await db.commit()
