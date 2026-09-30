"""
Mission plans (ADR 0028, ADR 0029): patterns, splitting, deconfliction.

``POST /missions/{id}/plan`` computes every aircraft's route from a pattern, splits an
area among the aircraft, layers and sequences them and checks the result in 4D. With
``dry_run`` it only answers; otherwise the plan is saved (the mission's tasks get their
routes) and the mission becomes ``planned``. A plan with conflicts or clearance issues is
saved as it is, reported, and cannot be started without a supervisor's override.

Planning is CPU work: the request's transaction ends before it and the plan is computed in
a worker thread (ADR 0019). If the mission changed meanwhile, saving is refused.
"""

import asyncio
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import select

from fleet_service.api.common import AltitudeRelative, EntityId, InputModel, Speed, StrictBool
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.api.helpers import ensure_incident_open, get_or_404, get_reference
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import Aircraft, AircraftGroup, Incident, Mission, SearchArea, Task
from fleet_service.domain.enums import (
    EDITABLE_MISSION_STATUSES,
    Airframe,
    MissionKind,
    MissionStatus,
    TaskStatus,
)
from fleet_service.domain.geo import GeoPoint
from fleet_service.domain.patterns import PatternError, PatternKind, RoutePoint
from fleet_service.domain.patterns.spacing import lane_spacing_m
from fleet_service.errors import Conflict, InvalidRequest, NotFound, problem_responses
from fleet_service.ids import new_id
from fleet_service.services import audit
from fleet_service.services.planning import AircraftInput, Defaults, Plan, PlanInput, plan_mission
from fleet_service.services.views import MissionProgressView

router = APIRouter(
    prefix="/missions", tags=["missions"], responses=problem_responses(400, 401, 403, 404, 409, 422)
)

Seconds = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=86_400.0)]
ROUTE_SPACING_M = 50.0  # waypoint routes: the width counted as searched along them


# --- models ----------------------------------------------------------------------------------


class Footprint(InputModel):
    """The camera, for the lane spacing: 2 · height · tan(HFOV / 2) · (1 - overlap)."""

    hfov_deg: float = Field(strict=True, allow_inf_nan=False, gt=0.0, lt=180.0)
    overlap: float = Field(strict=True, allow_inf_nan=False, ge=0.0, le=0.9)
    height_agl_m: float | None = Field(
        default=None,
        strict=True,
        allow_inf_nan=False,
        gt=0.0,
        le=1500.0,
        description="Height above ground; default: the mission's altitude above home.",
    )


class TaskOverride(InputModel):
    """Per-aircraft changes to the mission's defaults."""

    aircraft_id: EntityId
    altitude_relative_m: AltitudeRelative | None = None
    speed_mps: Speed | None = None
    start_delay_s: Seconds | None = None


class PlanRequest(InputModel):
    """What to plan. Area patterns need ``spacing_m`` or ``footprint``; aircraft come from
    ``aircraft_ids``, a ``group_id``, or (neither) the mission's current tasks."""

    pattern: PatternKind
    spacing_m: float | None = Field(
        default=None, strict=True, allow_inf_nan=False, ge=5.0, le=2000.0
    )
    footprint: Footprint | None = None
    bearing_deg: float | None = Field(
        default=None,
        strict=True,
        allow_inf_nan=False,
        ge=0.0,
        lt=360.0,
        description="Lane direction or first leg, degrees true; default: the area's long axis.",
    )
    datum: GeoPoint | None = None
    radius_m: float | None = Field(
        default=None, strict=True, allow_inf_nan=False, ge=10.0, le=50_000.0
    )
    second_pass: StrictBool = False
    height_agl_m: float | None = Field(
        default=None,
        strict=True,
        allow_inf_nan=False,
        ge=5.0,
        le=1500.0,
        description="Contour search: height above the contour lines.",
    )
    aircraft_ids: list[EntityId] | None = Field(default=None, min_length=1, max_length=254)
    group_id: EntityId | None = None
    overrides: list[TaskOverride] = Field(default_factory=list, max_length=254)

    @model_validator(mode="after")
    def _consistent(self) -> "PlanRequest":
        if self.spacing_m is not None and self.footprint is not None:
            raise ValueError("give spacing_m or footprint, not both")
        if self.aircraft_ids is not None and self.group_id is not None:
            raise ValueError("give aircraft_ids or group_id, not both")
        if self.aircraft_ids is not None and len(set(self.aircraft_ids)) != len(self.aircraft_ids):
            raise ValueError("aircraft_ids must not contain duplicates")
        return self


class PlannedWaypoint(BaseModel):
    """One waypoint of a planned route (altitude above the aircraft's home)."""

    latitude: float
    longitude: float
    altitude_relative_m: float
    speed_mps: float | None
    loiter_s: float | None


class PlannedTask(BaseModel):
    """One aircraft's part of a plan."""

    aircraft_id: str
    callsign: str
    airframe: Airframe
    companion: bool = Field(description="Has a swarm companion (onboard obstacle avoidance).")
    layer_m: float = Field(description="Metres added to the planned altitude for separation.")
    speed_mps: float
    start_delay_s: float
    strip_area_m2: float | None
    length_m: float
    duration_s: float
    fallback: bool
    infeasible_turns: int
    notes: list[str]
    waypoints: list[PlannedWaypoint]


class PlanConflict(BaseModel):
    """Two aircraft too close in the plan: where and when they come closest."""

    aircraft_ids: list[str]
    callsigns: list[str]
    t_s: float
    latitude: float
    longitude: float
    horizontal_m: float
    vertical_m: float


class PlanClearance(BaseModel):
    """A waypoint too close to the ground or too high."""

    aircraft_id: str
    callsign: str
    waypoint: int
    kind: str
    height_m: float


class PlanOut(BaseModel):
    """A mission's plan."""

    mission_id: str
    pattern: PatternKind
    spacing_m: float
    dry_run: bool
    clear: bool = Field(description="No conflict and no clearance issue: startable.")
    coverage: float | None = Field(description="Share of the area within the sweep (0-1).")
    area_m2: float | None
    duration_s: float
    tasks: list[PlannedTask]
    conflicts: list[PlanConflict]
    clearance: list[PlanClearance]
    unchecked_terrain: int
    notes: list[str]
    planned_at: AwareDatetime
    request: dict[str, Any]


# --- helpers ---------------------------------------------------------------------------------


async def _aircraft(db: DbSession, mission: Mission, body: PlanRequest) -> list[Aircraft]:
    if body.group_id is not None:
        group = await get_reference(db, AircraftGroup, body.group_id, "group_id")
        return sorted(group.members, key=lambda a: a.callsign)
    if body.aircraft_ids is not None:
        return [await get_reference(db, Aircraft, i, "aircraft_ids") for i in body.aircraft_ids]
    tasked = await db.scalars(
        select(Aircraft)
        .join(Task, Task.aircraft_id == Aircraft.id)
        .where(Task.mission_id == mission.id, Task.status != TaskStatus.CANCELLED)
        .order_by(Aircraft.callsign)
    )
    return list(tasked.all())


def _check_pattern(mission: Mission, pattern: PatternKind) -> None:
    if mission.kind is MissionKind.SWARM_AREA:
        raise Conflict(
            "Swarm-area missions are planned by the swarm itself (ADR 0003); start them with "
            "mission_start.",
            slug="swarm-plans-onboard",
        )
    if mission.kind is MissionKind.WAYPOINT and pattern is not PatternKind.ROUTE:
        raise InvalidRequest(
            "A waypoint mission flies its route: use the pattern 'route'.",
            slug="pattern-mismatch",
            extensions={"field": "pattern"},
        )
    if mission.kind is MissionKind.AREA_SEARCH and pattern is PatternKind.ROUTE:
        raise InvalidRequest(
            "An area search needs a search pattern, not 'route'.",
            slug="pattern-mismatch",
            extensions={"field": "pattern"},
        )


def _aircraft_input(
    context: Context, aircraft: Aircraft, override: TaskOverride | None
) -> AircraftInput:
    view = context.runtime().registry.vehicle_view(aircraft.id)
    sample = view.sample if view is not None else None
    position = home = None
    home_amsl = altitude = battery = None
    if sample is not None:
        if sample.latitude is not None and sample.longitude is not None:
            position = (sample.latitude, sample.longitude)
        if sample.home_latitude is not None and sample.home_longitude is not None:
            home = (sample.home_latitude, sample.home_longitude)
        altitude = sample.altitude_relative_m
        if sample.altitude_amsl_m is not None and sample.altitude_relative_m is not None:
            home_amsl = sample.altitude_amsl_m - sample.altitude_relative_m
        battery = sample.battery_pct
    return AircraftInput(
        aircraft_id=aircraft.id,
        callsign=aircraft.callsign,
        airframe=aircraft.airframe,
        companion=aircraft.swarm_drone_id is not None,
        cruise_speed_mps=aircraft.cruise_speed_mps,
        endurance_s=aircraft.endurance_s,
        position=position,
        altitude_relative_m=altitude,
        home=home,
        home_amsl_m=home_amsl,
        battery_pct=battery,
        altitude_override_m=override.altitude_relative_m if override else None,
        speed_override_mps=override.speed_mps if override else None,
        start_delay_s=override.start_delay_s if override else None,
    )


def _defaults(context: Context) -> Defaults:
    s = context.settings
    return Defaults(
        multirotor_speed_mps=s.multirotor_speed_mps,
        fixed_wing_speed_mps=s.fixed_wing_speed_mps,
        multirotor_endurance_s=s.multirotor_endurance_s,
        fixed_wing_endurance_s=s.fixed_wing_endurance_s,
        fixed_wing_max_bank_deg=s.fixed_wing_max_bank_deg,
    )


def _out(mission_id: str, plan: Plan, body: PlanRequest, dry_run: bool, now: datetime) -> PlanOut:
    report = plan.report
    return PlanOut(
        mission_id=mission_id,
        pattern=plan.pattern,
        spacing_m=round(plan.spacing_m, 2),
        dry_run=dry_run,
        clear=plan.clear,
        coverage=plan.coverage,
        area_m2=round(plan.area_m2, 1) if plan.area_m2 is not None else None,
        duration_s=round(plan.duration_s, 1),
        tasks=[
            PlannedTask(
                aircraft_id=t.aircraft.aircraft_id,
                callsign=t.aircraft.callsign,
                airframe=t.aircraft.airframe,
                companion=t.aircraft.companion,
                layer_m=round(t.layer_m, 2),
                speed_mps=t.speed_mps,
                start_delay_s=round(t.start_delay_s, 1),
                strip_area_m2=round(t.strip_area_m2, 1) if t.strip_area_m2 is not None else None,
                length_m=round(t.route.length_m, 1),
                duration_s=round(t.duration_s, 1),
                fallback=t.route.fallback,
                infeasible_turns=t.route.infeasible_turns,
                notes=t.notes,
                waypoints=[
                    PlannedWaypoint(
                        latitude=p.latitude,
                        longitude=p.longitude,
                        altitude_relative_m=p.altitude_relative_m,
                        speed_mps=p.speed_mps,
                        loiter_s=p.loiter_s,
                    )
                    for p in t.route.points
                ],
            )
            for t in plan.tasks
        ],
        conflicts=[
            PlanConflict(
                aircraft_ids=list(c.aircraft),
                callsigns=list(c.callsigns),
                t_s=c.t_s,
                latitude=c.latitude,
                longitude=c.longitude,
                horizontal_m=c.horizontal_m,
                vertical_m=c.vertical_m,
            )
            for c in report.conflicts
        ],
        clearance=[
            PlanClearance(
                aircraft_id=c.aircraft_id,
                callsign=c.callsign,
                waypoint=c.waypoint,
                kind=c.kind,
                height_m=round(c.height_m, 1),
            )
            for c in report.clearance
        ],
        unchecked_terrain=report.unchecked_terrain,
        notes=plan.notes,
        planned_at=now,
        request=body.model_dump(mode="json"),
    )


# --- routes ------------------------------------------------------------------------------------


@router.post("/{mission_id}/plan", **requires(Permission.MISSIONS_PLAN))
async def plan(
    mission_id: str,
    body: PlanRequest,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
    dry_run: Annotated[bool, Query(description="Only compute and answer; save nothing.")] = False,
) -> PlanOut:
    """Plan a mission: routes for its aircraft, split, layered, sequenced and checked."""
    mission = await get_or_404(db, Mission, mission_id, "Mission")
    incident = await get_or_404(db, Incident, mission.incident_id, "Incident")
    ensure_incident_open(incident)
    if mission.status not in EDITABLE_MISSION_STATUSES:
        raise Conflict(
            f"Mission {mission.id} is {mission.status.value}; its plan can no longer change.",
            slug="mission-not-editable",
        )
    _check_pattern(mission, body.pattern)
    aircraft = await _aircraft(db, mission, body)
    if not aircraft:
        raise InvalidRequest(
            "No aircraft to plan for: give aircraft_ids or group_id, or assign tasks first.",
            slug="no-aircraft",
        )
    for a in aircraft:
        if a.mavlink_system_id is None and not context.settings.simulation:
            raise Conflict(
                f"Aircraft {a.callsign} has no mavlink_system_id; it cannot fly a "
                f"{mission.kind.value} mission (ADR 0003).",
                slug="aircraft-incompatible",
            )
    ids = {a.id for a in aircraft}
    unknown = [o.aircraft_id for o in body.overrides if o.aircraft_id not in ids]
    if unknown:
        raise InvalidRequest(
            "Overrides name aircraft that are not in the plan.",
            slug="unknown-reference",
            extensions={"field": "overrides", "aircraft_ids": unknown},
        )
    area_ring = None
    if mission.search_area_id is not None:
        area = await db.get(SearchArea, mission.search_area_id)
        if area is not None:
            area_ring = tuple((float(x), float(y)) for x, y in area.geometry["coordinates"][0])
    spacing = body.spacing_m
    if body.footprint is not None:
        height = body.footprint.height_agl_m or mission.default_altitude_relative_m
        try:
            spacing = lane_spacing_m(height, body.footprint.hfov_deg, body.footprint.overlap)
        except PatternError as exc:
            raise InvalidRequest(
                str(exc), slug=exc.code, extensions={"field": "footprint"}
            ) from exc
    if spacing is None:
        if body.pattern is not PatternKind.ROUTE:
            raise InvalidRequest(
                "Give spacing_m or a camera footprint.",
                slug="spacing-required",
                extensions={"field": "spacing_m"},
            )
        spacing = ROUTE_SPACING_M
    overrides = {o.aircraft_id: o for o in body.overrides}
    inp = PlanInput(
        mission_kind=mission.kind,
        pattern=body.pattern,
        spacing_m=spacing,
        altitude_relative_m=mission.default_altitude_relative_m,
        aircraft=tuple(_aircraft_input(context, a, overrides.get(a.id)) for a in aircraft),
        area=area_ring,
        route=tuple(
            RoutePoint(w.latitude, w.longitude, w.altitude_relative_m, w.speed_mps, w.loiter_s)
            for w in mission.waypoints
        )
        or None,
        speed_mps=mission.default_speed_mps,
        bearing_deg=body.bearing_deg,
        datum=(body.datum.latitude, body.datum.longitude) if body.datum else None,
        radius_m=body.radius_m,
        second_pass=body.second_pass,
        height_agl_m=body.height_agl_m,
    )
    version = mission.updated_at
    await db.commit()  # no transaction open while planning (ADR 0019)

    runtime = context.runtime()
    try:
        result = await asyncio.to_thread(
            plan_mission, inp, runtime.terrain, runtime.separation, _defaults(context)
        )
    except PatternError as exc:
        raise InvalidRequest(str(exc), slug=exc.code) from exc
    now = context.clock.now()
    out = _out(mission_id, result, body, dry_run, now)
    if dry_run:
        return out

    db.expire_all()  # read the mission as it is now, not as this session cached it
    mission = await get_or_404(db, Mission, mission_id, "Mission")
    if mission.updated_at != version or mission.status not in EDITABLE_MISSION_STATUSES:
        raise Conflict(
            "The mission changed while it was planned; plan it again.", slug="plan-stale"
        )
    tasks = {
        t.aircraft_id: t
        for t in (await db.scalars(select(Task).where(Task.mission_id == mission.id))).all()
    }
    for task in tasks.values():  # aircraft no longer in the plan lose their pending task
        if task.aircraft_id not in ids and task.status is TaskStatus.PENDING:
            await db.delete(task)
    for planned in out.tasks:
        existing = tasks.get(planned.aircraft_id)
        override = overrides.get(planned.aircraft_id)
        if existing is not None:
            task = existing
        else:
            task = Task(
                id=new_id(),
                mission_id=mission.id,
                aircraft_id=planned.aircraft_id,
                status=TaskStatus.PENDING,
                created_at=now,
                updated_at=now,
            )
            db.add(task)
        task.status = TaskStatus.PENDING
        task.altitude_relative_m = override.altitude_relative_m if override else None
        task.speed_mps = override.speed_mps if override else None
        task.start_delay_s = planned.start_delay_s
        task.route = [w.model_dump(mode="json") for w in planned.waypoints]
        task.plan = planned.model_dump(mode="json", exclude={"waypoints"})
        task.updated_at = now
    mission.plan = out.model_dump(mode="json")
    mission.status = MissionStatus.PLANNED
    mission.updated_at = now
    await db.flush()
    missions = context.runtime().missions
    await audit.record(
        db,
        actor(request, principal),
        now,
        "mission.plan",
        entity_type="mission",
        entity_id=mission.id,
        details={
            "pattern": body.pattern.value,
            "aircraft": sorted(ids),
            "clear": out.clear,
            "conflicts": len(out.conflicts),
            "clearance": len(out.clearance),
            "coverage": out.coverage,
        },
    )
    await db.commit()
    missions.publish(await missions.progress(db, mission))
    await db.commit()
    return out


@router.get("/{mission_id}/plan", **requires(Permission.FLEET_VIEW))
async def get_plan(mission_id: str, db: DbSession) -> PlanOut:
    """The saved plan of a mission."""
    mission = await get_or_404(db, Mission, mission_id, "Mission")
    if mission.plan is None:
        raise NotFound(f"Mission {mission_id} has no saved plan.", slug="no-plan")
    return PlanOut.model_validate(mission.plan)


class MissionProgressOut(MissionProgressView):
    """A mission's progress, with the area swept so far (WGS84 GeoJSON MultiPolygon)."""

    coverage_geometry: dict[str, Any] | None


@router.get("/{mission_id}/progress", **requires(Permission.FLEET_VIEW))
async def get_progress(mission_id: str, db: DbSession, context: Context) -> MissionProgressOut:
    """Progress of a mission: status, per-aircraft item, coverage and its geometry."""
    mission = await get_or_404(db, Mission, mission_id, "Mission")
    missions = context.runtime().missions
    view = await missions.progress(db, mission)
    return MissionProgressOut(
        **view.model_dump(), coverage_geometry=missions.coverage_geometry(mission)
    )
