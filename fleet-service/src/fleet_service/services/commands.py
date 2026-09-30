"""
The command pipeline (ADR 0011, ADR 0020).

    receive -> idempotency -> authorize + preconditions (per aircraft)
            -> confirmation (428 + token)      when the command is risky or bulk
            -> dispatch (per aircraft, concurrent, bounded by the timeout)
            -> outcome: acked / nacked / timeout / rejected (per aircraft)
            -> effect verification from telemetry: verified / unverified

Every stage is audited. The database transaction is committed before waiting for
aircraft, so no connection is held while radios answer (ADR 0019). Authorization and
preconditions run again when a confirmed command is dispatched: whatever changed during
the confirmation window can only reject more aircraft, never add risk.

Some commands differ per aircraft (M4): a GCS-planned mission sends each aircraft its own
route, and a goto to several aircraft sends each its own point and altitude layer
(ADR 0029). Both are checked in 4D from where the aircraft are when the command is sent;
conflicts reject the aircraft unless a supervisor overrides, confirmed and audited.
Aircraft with a swarm companion that the autopilot would fly (goto, GCS mission) are
flagged: onboard obstacle avoidance is not active then, and the command is confirmed.
"""

import asyncio
import hashlib
import hmac
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from pydantic import AwareDatetime, BaseModel
from shapely import Polygon
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.auth.permissions import Permission
from fleet_service.auth.principal import Principal
from fleet_service.bus import COMMANDS, EventBus
from fleet_service.clock import Clock
from fleet_service.db.models import (
    Command,
    CommandTarget,
    Geofence,
    Incident,
    Mission,
    SearchArea,
    Task,
)
from fleet_service.domain.commands import (
    GotoTarget,
    Limits,
    Rejection,
    authority,
    confirmation_reasons,
    expected_effect,
    gcs_mission_problem,
    precondition,
    swarm_mission_problem,
    warnings,
)
from fleet_service.domain.deconfliction import Flight, Separation, find_conflicts, layer_offsets
from fleet_service.domain.enums import (
    Airframe,
    AlertKind,
    AlertSeverity,
    CommandKind,
    CommandState,
    CommandTargetState,
    IncidentStatus,
    MissionKind,
    MissionStatus,
    SearchAreaStatus,
    TaskStatus,
)
from fleet_service.domain.geo import GeoPoint, distance_m
from fleet_service.domain.geofence import Fence, GeofenceSet
from fleet_service.domain.patterns import LocalFrame, RoutePoint
from fleet_service.domain.spread import spread_targets
from fleet_service.domain.telemetry import TelemetrySample
from fleet_service.drivers.base import AreaMission, DriverCommand, Outcome, RouteMission
from fleet_service.errors import Conflict, InvalidRequest, ProblemError
from fleet_service.services import audit
from fleet_service.services.alerts import AlertService
from fleet_service.services.audit import Actor
from fleet_service.services.fleet import FleetRegistry
from fleet_service.services.leases import LeaseService
from fleet_service.services.views import CommandTargetView, CommandView

log = logging.getLogger(__name__)
SYSTEM_ACTOR = Actor(user_id=None, username="system:commands")


@dataclass(frozen=True)
class CommandSpec:
    """A validated command request, as the API received it."""

    command_id: str
    kind: CommandKind
    aircraft_ids: tuple[str, ...]
    params: dict[str, Any]
    request_hash: str
    confirmation_token: str | None
    takeoff_altitude_m: float | None = None
    goto: GotoTarget | None = None
    mission_id: str | None = None
    spread_m: float | None = None  # bulk goto: distance between the aircraft's points

    def driver_command(self, mission: AreaMission | None = None) -> DriverCommand:
        """What each aircraft is told."""
        return DriverCommand(
            self.kind,
            altitude_relative_m=(
                self.goto.altitude_relative_m if self.goto else self.takeoff_altitude_m
            ),
            latitude=self.goto.latitude if self.goto else None,
            longitude=self.goto.longitude if self.goto else None,
            command_id=self.command_id,
            mission=mission,
        )


class SummaryAircraft(BaseModel):
    """An aircraft the command would be sent to, with what the operator should notice."""

    aircraft_id: str
    callsign: str
    warnings: list[str]
    target: GeoPoint | None = None  # its own point (bulk goto) or first waypoint (mission)
    altitude_relative_m: float | None = None
    start_delay_s: float | None = None


class SummaryRejection(BaseModel):
    """An aircraft the command will not be sent to, and why."""

    aircraft_id: str
    callsign: str | None
    code: str
    message: str


class ConfirmationSummary(BaseModel):
    """What the operator is asked to confirm, computed by the server."""

    kind: CommandKind
    params: dict[str, Any]
    reasons: list[str]
    override: bool
    aircraft: list[SummaryAircraft]
    rejected: list[SummaryRejection]
    conflicts: list[str] = []  # deconfliction and clearance issues a supervisor overrides


class ConfirmationRequiredError(ProblemError):
    """428: re-send the same request with ``confirmation_token`` to execute it."""

    status, slug, title = 428, "confirmation-required", "Confirmation required"

    def __init__(
        self,
        detail: str,
        command_id: str,
        token: str,
        expires_at: datetime,
        summary: ConfirmationSummary,
    ) -> None:
        super().__init__(
            detail,
            extensions={
                "command_id": command_id,
                "confirmation_token": token,
                "expires_at": expires_at.isoformat(),
                "summary": summary.model_dump(mode="json"),
            },
        )


class ConfirmationProblem(BaseModel):
    """The 428 response body (documented in the OpenAPI document)."""

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    command_id: str
    confirmation_token: str
    expires_at: AwareDatetime
    summary: ConfirmationSummary


def area_mission(mission: Mission, geometry: dict[str, Any], grid_m: float) -> AreaMission:
    """A swarm area mission from a planned mission and its search area's GeoJSON polygon.

    The mission frame's origin is the area's centroid; the polygon's closing vertex is
    dropped (the onboard protocol takes an open ring). Altitudes are above each drone's home.
    """
    ring = [(float(lat), float(lon)) for lon, lat in geometry["coordinates"][0]]
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    centroid = Polygon([(lon, lat) for lat, lon in ring]).centroid
    return AreaMission(
        mission_id=mission.id,
        origin=(round(centroid.y, 7), round(centroid.x, 7)),
        altitude_relative_m=mission.default_altitude_relative_m,
        grid_resolution_m=grid_m,
        waypoints=tuple((w.latitude, w.longitude) for w in mission.waypoints),
        area=tuple(ring),
    )


@dataclass
class _Plan:
    accepted: list[str] = field(default_factory=list)
    rejected: dict[str, Rejection] = field(default_factory=dict)
    warnings: dict[str, list[str]] = field(default_factory=dict)
    override: bool = False
    reasons: list[str] = field(default_factory=list)
    mission: AreaMission | None = None  # mission_start: what the swarm is sent
    swarm_mission: bool = False
    commands: dict[str, DriverCommand] = field(default_factory=dict)  # per aircraft
    targets: dict[str, tuple[float, float, float | None, float | None]] = field(
        default_factory=dict
    )  # latitude, longitude, altitude, start delay: for the summary
    conflicts: list[str] = field(default_factory=list)
    without_avoidance: int = 0
    timeout_s: float | None = None
    gcs_mission_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class _GcsTask:
    """What a GCS mission start sends one aircraft."""

    route: tuple[RoutePoint, ...]
    start_delay_s: float
    speed_mps: float


@dataclass(frozen=True)
class _Verification:
    command_id: str
    aircraft_id: str
    effect: Callable[[TelemetrySample], bool]
    acked_at: datetime
    deadline: datetime


class CommandService:
    """Runs commands from request to verified effect."""

    def __init__(
        self,
        *,
        bus: EventBus,
        clock: Clock,
        registry: FleetRegistry,
        leases: LeaseService,
        alerts: AlertService,
        limits: Limits,
        battery_low_pct: float,
        timeout_s: float,
        effect_timeout_s: float,
        min_interval_s: float,
        confirmation_ttl_s: float,
        swarm_grid_resolution_m: float = 5.0,
        swarm_aircraft: Callable[[], list[str]] = list,
        separation: Separation | None = None,
        goto_spread_m: float = 60.0,
        mission_timeout_s: float = 60.0,
    ) -> None:
        self._bus = bus
        self._clock = clock
        self._registry = registry
        self._leases = leases
        self._alerts = alerts
        self._limits = limits
        self._battery_low = battery_low_pct
        self._timeout = timeout_s
        self._effect_timeout = timedelta(seconds=effect_timeout_s)
        self._min_interval = timedelta(seconds=min_interval_s)
        self._ttl = timedelta(seconds=confirmation_ttl_s)
        self._grid_resolution_m = swarm_grid_resolution_m
        self._swarm_aircraft = swarm_aircraft
        self._separation = separation or Separation()
        self._goto_spread_m = goto_spread_m
        self._mission_timeout = mission_timeout_s
        self._secret = secrets.token_bytes(32)  # tokens do not survive a restart, by design
        self._last_dispatch: dict[str, datetime] = {}
        self._verifications: list[_Verification] = []

    # --- entry point --------------------------------------------------------------------------

    async def submit(
        self, db: AsyncSession, principal: Principal, actor: Actor, spec: CommandSpec
    ) -> CommandView:
        """Run a command request through the pipeline; see the module docstring."""
        now = self._clock.now()
        existing = await db.get(Command, spec.command_id)
        if existing is not None:
            if (
                existing.issued_by != principal.user_id
                or existing.request_hash != spec.request_hash
            ):
                raise Conflict(
                    "This command_id was already used for a different request; generate a new one.",
                    slug="command-id-reused",
                )
            waiting = (CommandState.AWAITING_CONFIRMATION, CommandState.EXPIRED)
            if existing.state not in waiting:
                return await self.view(db, existing)  # idempotent replay
        unknown = sorted(a for a in spec.aircraft_ids if self._registry.get(a) is None)
        if unknown:
            raise InvalidRequest(
                f"Unknown aircraft: {', '.join(unknown)}.",
                slug="unknown-reference",
                extensions={"field": "aircraft_ids", "unknown_ids": unknown},
            )
        confirmed = existing is not None and self._token_valid(existing, principal, spec, now)
        plan = await self._plan(db, now, principal, spec)
        if not plan.accepted:
            return await self._reject_all(db, now, principal, actor, spec, plan, existing)
        if plan.reasons and not confirmed:
            await self._ask_confirmation(db, now, principal, actor, spec, plan, existing)
        return await self._dispatch(db, now, principal, actor, spec, plan, existing, confirmed)

    # --- planning -----------------------------------------------------------------------------

    async def _plan(
        self, db: AsyncSession, now: datetime, principal: Principal, spec: CommandSpec
    ) -> _Plan:
        plan = _Plan()
        geofences = await self._geofences(db) if spec.kind is CommandKind.GOTO else None
        farthest: float | None = None
        mission_problem: Rejection | None = None
        gcs_tasks: dict[str, _GcsTask] | None = None
        gcs_aircraft: set[str] = set()
        if spec.kind is CommandKind.MISSION_START:
            mission = await self._mission(db, spec)
            if mission.kind is MissionKind.SWARM_AREA:
                plan.swarm_mission = True
                mission_problem, plan.mission = await self._swarm_mission(db, spec)
            else:
                mission_problem, gcs_tasks, plan.conflicts = await self._gcs_mission(db, mission)
                gcs_aircraft = set(spec.aircraft_ids)
        elif spec.kind in (CommandKind.RESUME, CommandKind.MISSION_PAUSE):
            plan.gcs_mission_ids = await self._gcs_missions_of(db, spec.aircraft_ids)
            if spec.kind is CommandKind.RESUME:
                gcs_aircraft = set(await self._gcs_aircraft(db, spec.aircraft_ids))
        companions = set(self._swarm_aircraft())
        for aircraft_id in spec.aircraft_ids:
            vehicle = self._registry.vehicle_view(aircraft_id)
            assert vehicle is not None  # noqa: S101 - unknown ids were rejected above
            rejection, override = authority(
                spec.kind,
                principal_id=principal.user_id,
                holder_id=self._leases.holder_id(aircraft_id),
                can_hold=principal.can(Permission.AIRCRAFT_HOLD),
                can_command=principal.can(Permission.AIRCRAFT_COMMAND),
                can_override=principal.can(Permission.CONTROL_OVERRIDE),
            )
            if rejection is None:
                rejection = mission_problem
            if rejection is None and gcs_tasks is not None and aircraft_id not in gcs_tasks:
                rejection = Rejection(
                    "not-tasked", f"{vehicle.callsign} has no route in this mission's plan."
                )
            if rejection is None:
                rejection = precondition(
                    spec.kind,
                    vehicle,
                    self._limits,
                    takeoff_altitude_m=spec.takeoff_altitude_m,
                    goto=spec.goto,
                    geofences=geofences,
                    gcs_mission=aircraft_id in gcs_aircraft,
                )
            last = self._last_dispatch.get(aircraft_id)
            if rejection is None and last is not None and now - last < self._min_interval:
                rejection = Rejection("rate-limited", "A command was just sent; try again.")
            if rejection is not None:
                plan.rejected[aircraft_id] = rejection
                continue
            plan.accepted.append(aircraft_id)
            plan.override |= override
            plan.warnings[aircraft_id] = warnings(vehicle, self._battery_low)
            autopilot_flies = spec.kind is CommandKind.GOTO or aircraft_id in gcs_aircraft
            if aircraft_id in companions and autopilot_flies:
                plan.warnings[aircraft_id].append(
                    "onboard obstacle avoidance not active: the autopilot flies this, not the "
                    "companion"
                )
                plan.without_avoidance += 1
            sample = vehicle.sample
            if (
                spec.goto is not None
                and sample is not None
                and sample.latitude is not None
                and sample.longitude is not None
            ):
                distance = distance_m(
                    GeoPoint(latitude=sample.latitude, longitude=sample.longitude),
                    GeoPoint(latitude=spec.goto.latitude, longitude=spec.goto.longitude),
                )
                farthest = max(farthest or 0.0, distance)
        if gcs_tasks is not None and plan.accepted:
            await self._plan_gcs_start(db, principal, spec, plan, gcs_tasks)
        elif spec.kind is CommandKind.GOTO and len(plan.accepted) > 1 and spec.goto is not None:
            await self._plan_bulk_goto(db, principal, spec, plan, geofences)
        elif spec.kind is CommandKind.RESUME:
            for aircraft_id in plan.accepted:
                if aircraft_id in gcs_aircraft:
                    plan.commands[aircraft_id] = DriverCommand(
                        CommandKind.RESUME, command_id=spec.command_id, gcs_mission=True
                    )
        plan.reasons = confirmation_reasons(
            spec.kind,
            target_count=len(plan.accepted),
            any_override=plan.override,
            goto_distance_m=farthest,
            limits=self._limits,
            swarm_mission=plan.swarm_mission,
            without_avoidance=plan.without_avoidance,
            plan_issues=len(plan.conflicts),
        )
        return plan

    async def _mission(self, db: AsyncSession, spec: CommandSpec) -> Mission:
        mission = await db.get(Mission, spec.mission_id) if spec.mission_id else None
        if mission is None:
            raise InvalidRequest(
                f"Mission {spec.mission_id} does not exist.",
                slug="unknown-reference",
                extensions={"field": "mission_id"},
            )
        return mission

    async def _gcs_mission(
        self, db: AsyncSession, mission: Mission
    ) -> tuple[Rejection | None, dict[str, _GcsTask], list[str]]:
        """Check a GCS mission start (ADR 0028); each tasked aircraft's route; plan issues."""
        incident = await db.get(Incident, mission.incident_id)
        problem = gcs_mission_problem(
            mission.kind,
            mission.status,
            incident_active=incident is not None and incident.status is IncidentStatus.ACTIVE,
            planned=mission.plan is not None,
        )
        tasks: dict[str, _GcsTask] = {}
        rows = await db.scalars(
            select(Task).where(Task.mission_id == mission.id, Task.status == TaskStatus.PENDING)
        )
        for task in rows.all():
            if not task.route:
                continue
            tasks[task.aircraft_id] = _GcsTask(
                route=tuple(
                    RoutePoint(
                        w["latitude"],
                        w["longitude"],
                        w["altitude_relative_m"],
                        w.get("speed_mps"),
                        w.get("loiter_s"),
                    )
                    for w in task.route
                ),
                start_delay_s=task.start_delay_s or 0.0,
                speed_mps=float((task.plan or {}).get("speed_mps") or 10.0),
            )
        saved = mission.plan or {}
        issues = [
            f"{' and '.join(c['callsigns'])} closer than the separation "
            f"({c['horizontal_m']:.0f} m, {c['vertical_m']:.0f} m) at {c['t_s']:.0f} s"
            for c in saved.get("conflicts", [])
        ] + [
            f"{c['callsign']} waypoint {c['waypoint']} {c['kind'].replace('-', ' ')} "
            f"({c['height_m']:.0f} m)"
            for c in saved.get("clearance", [])
        ]
        return problem, tasks, issues

    async def _gcs_missions_of(self, db: AsyncSession, aircraft_ids: tuple[str, ...]) -> set[str]:
        """The GCS missions the aircraft are flying (active tasks, active or paused missions)."""
        rows = await db.scalars(
            select(Mission.id)
            .join(Task, Task.mission_id == Mission.id)
            .where(
                Task.aircraft_id.in_(aircraft_ids),
                Task.status == TaskStatus.ACTIVE,
                Mission.kind != MissionKind.SWARM_AREA,
                Mission.status.in_((MissionStatus.ACTIVE, MissionStatus.PAUSED)),
            )
        )
        return set(rows.all())

    async def _gcs_aircraft(self, db: AsyncSession, aircraft_ids: tuple[str, ...]) -> list[str]:
        """Of ``aircraft_ids``, those flying a GCS mission (resume means that mission)."""
        rows = await db.scalars(
            select(Task.aircraft_id)
            .join(Mission, Mission.id == Task.mission_id)
            .where(
                Task.aircraft_id.in_(aircraft_ids),
                Task.status == TaskStatus.ACTIVE,
                Mission.kind != MissionKind.SWARM_AREA,
                Mission.status.in_((MissionStatus.ACTIVE, MissionStatus.PAUSED)),
            )
        )
        return list(rows.all())

    def _flight(
        self,
        aircraft_id: str,
        route: tuple[RoutePoint, ...],
        speed: float,
        delay: float,
        returns: bool,
    ) -> Flight:
        """A planned flight from where the aircraft is now."""
        record = self._registry.get(aircraft_id)
        sample = record.sample if record else None
        position = home = None
        home_amsl = altitude = None
        if sample is not None:
            if sample.latitude is not None and sample.longitude is not None:
                position = (sample.latitude, sample.longitude)
            if sample.home_latitude is not None and sample.home_longitude is not None:
                home = (sample.home_latitude, sample.home_longitude)
            altitude = sample.altitude_relative_m
            if sample.altitude_amsl_m is not None and sample.altitude_relative_m is not None:
                home_amsl = sample.altitude_amsl_m - sample.altitude_relative_m
        return Flight(
            aircraft_id=aircraft_id,
            callsign=record.callsign if record else aircraft_id,
            fixed_wing=record is not None and record.airframe is Airframe.FIXED_WING,
            route=route,
            speed_mps=speed,
            start=position,
            home=home,
            home_amsl_m=home_amsl,
            start_altitude_relative_m=altitude,
            start_delay_s=delay,
            returns_home=returns,
        )

    async def _check_flights(
        self, db: AsyncSession, principal: Principal, plan: _Plan, flights: list[Flight]
    ) -> None:
        """4D-check ``flights`` from where the aircraft are now; conflicts reject the later
        aircraft of each pair, unless a supervisor overrides (confirmed, audited)."""
        if len(flights) < 2:
            return
        frame = LocalFrame(flights[0].route[0].latitude, flights[0].route[0].longitude)
        await db.commit()  # no transaction open during the check (ADR 0019)
        conflicts = await asyncio.to_thread(find_conflicts, flights, frame, self._separation)
        if not conflicts:
            return
        described = [
            f"{c.callsigns[0]} and {c.callsigns[1]} closer than the separation "
            f"({c.horizontal_m:.0f} m, {c.vertical_m:.0f} m) at {c.t_s:.0f} s"
            for c in conflicts
        ]
        if principal.can(Permission.CONTROL_OVERRIDE):
            plan.override = True
            plan.conflicts.extend(d for d in described if d not in plan.conflicts)
            return
        for conflict, text in zip(conflicts, described, strict=True):
            later = conflict.aircraft[1]
            if later in plan.accepted:
                plan.accepted.remove(later)
                plan.rejected[later] = Rejection(
                    "deconfliction", f"{text}; a supervisor may override."
                )

    async def _plan_gcs_start(
        self,
        db: AsyncSession,
        principal: Principal,
        spec: CommandSpec,
        plan: _Plan,
        tasks: dict[str, _GcsTask],
    ) -> None:
        """Each aircraft's route, from a first item where it is (climb there to its layer,
        and wait out its start delay), then its planned route, then home."""
        if plan.conflicts and not principal.can(Permission.CONTROL_OVERRIDE):
            for aircraft_id in list(plan.accepted):  # a plan with issues needs a supervisor
                plan.accepted.remove(aircraft_id)
                plan.rejected[aircraft_id] = Rejection(
                    "plan-conflicts",
                    f"The plan has {len(plan.conflicts)} deconfliction or clearance issue(s); "
                    "re-plan, or a supervisor may override.",
                )
            return
        flights = []
        for aircraft_id in plan.accepted:
            task = tasks[aircraft_id]
            record = self._registry.get(aircraft_id)
            sample = record.sample if record else None
            first = task.route[0]
            items = task.route
            if sample is not None and sample.latitude is not None and sample.longitude is not None:
                start = RoutePoint(
                    sample.latitude,
                    sample.longitude,
                    first.altitude_relative_m,
                    None,
                    task.start_delay_s or None,
                )
                items = (start, *task.route)
            plan.commands[aircraft_id] = DriverCommand(
                CommandKind.MISSION_START,
                command_id=spec.command_id,
                route=RouteMission(spec.mission_id or "", items, return_home=True),
                gcs_mission=True,
            )
            plan.targets[aircraft_id] = (
                first.latitude,
                first.longitude,
                first.altitude_relative_m,
                task.start_delay_s,
            )
            flights.append(
                self._flight(aircraft_id, task.route, task.speed_mps, task.start_delay_s, True)
            )
        plan.timeout_s = self._mission_timeout
        if plan.conflicts:  # the saved plan's issues: only a supervisor gets here
            plan.override = True
        await self._check_flights(db, principal, plan, flights)

    async def _plan_bulk_goto(
        self,
        db: AsyncSession,
        principal: Principal,
        spec: CommandSpec,
        plan: _Plan,
        geofences: GeofenceSet | None,
    ) -> None:
        """Each aircraft its own point around the datum and its own layer (ADR 0029)."""
        assert spec.goto is not None  # noqa: S101 - checked by the caller
        positions: dict[str, tuple[float, float] | None] = {}
        altitudes: list[float] = []
        for aircraft_id in plan.accepted:
            record = self._registry.get(aircraft_id)
            sample = record.sample if record else None
            positions[aircraft_id] = None
            if sample is None:
                continue
            if sample.latitude is not None and sample.longitude is not None:
                positions[aircraft_id] = (sample.latitude, sample.longitude)
            if sample.altitude_relative_m is not None:
                altitudes.append(sample.altitude_relative_m)
        points = spread_targets(
            (spec.goto.latitude, spec.goto.longitude),
            positions,
            spec.spread_m or self._goto_spread_m,
        )
        base = spec.goto.altitude_relative_m
        if base is None:
            base = max(altitudes) if altitudes else 0.0
        order = sorted(plan.accepted, key=lambda a: points[a])
        draft = [self._flight(a, (RoutePoint(*points[a], base),), 10.0, 0.0, False) for a in order]
        offsets = layer_offsets(draft, self._separation)
        flights = []
        for flight in draft:
            altitude = base + offsets[flight.aircraft_id]
            if altitude > self._limits.max_altitude_relative_m:
                altitude = base  # no layer left under the ceiling: the spread keeps them apart
            lat, lon = points[flight.aircraft_id]
            if geofences is not None and (reason := geofences.violation(lat, lon, altitude)):
                plan.accepted.remove(flight.aircraft_id)
                plan.rejected[flight.aircraft_id] = Rejection(
                    "geofence", f"Its point near the target is {reason}."
                )
                continue
            speed = 18.0 if flight.fixed_wing else 10.0
            flights.append(
                replace(flight, route=(RoutePoint(lat, lon, altitude),), speed_mps=speed)
            )
            plan.commands[flight.aircraft_id] = DriverCommand(
                CommandKind.GOTO,
                altitude_relative_m=altitude,
                latitude=lat,
                longitude=lon,
                command_id=spec.command_id,
            )
            plan.targets[flight.aircraft_id] = (lat, lon, altitude, None)
        await self._check_flights(db, principal, plan, flights)

    async def _swarm_mission(
        self, db: AsyncSession, spec: CommandSpec
    ) -> tuple[Rejection | None, AreaMission | None]:
        """Check a mission start (ADR 0024) and build what the swarm is sent."""
        mission = await db.get(Mission, spec.mission_id) if spec.mission_id else None
        if mission is None:
            raise InvalidRequest(
                f"Mission {spec.mission_id} does not exist.",
                slug="unknown-reference",
                extensions={"field": "mission_id"},
            )
        incident = await db.get(Incident, mission.incident_id)
        tasked = (
            await db.scalars(
                select(Task.aircraft_id).where(
                    Task.mission_id == mission.id, Task.status != TaskStatus.CANCELLED
                )
            )
        ).all()
        problem = swarm_mission_problem(
            mission.kind,
            mission.status,
            incident_active=incident is not None and incident.status is IncidentStatus.ACTIVE,
            targets=spec.aircraft_ids,
            tasked=tasked,
            swarm_aircraft=self._swarm_aircraft(),
        )
        if problem is not None or mission.search_area_id is None:
            return problem, None
        area = await db.get(SearchArea, mission.search_area_id)
        assert area is not None  # noqa: S101 - a foreign key
        return None, area_mission(mission, area.geometry, self._grid_resolution_m)

    async def _geofences(self, db: AsyncSession) -> GeofenceSet:
        rows = await db.scalars(
            select(Geofence)
            .join(Incident, Incident.id == Geofence.incident_id)
            .where(Geofence.enabled.is_(True), Incident.status == IncidentStatus.ACTIVE)
        )
        return GeofenceSet.of(
            Fence(g.name, g.kind, Polygon(g.geometry["coordinates"][0]), g.max_altitude_relative_m)
            for g in rows.all()
        )

    # --- confirmation tokens ------------------------------------------------------------------

    def _token(self, user_id: str, spec: CommandSpec, expires_at: datetime) -> str:
        expiry = str(int(expires_at.timestamp() * 1000))
        message = f"{user_id}|{spec.command_id}|{spec.request_hash}|{expiry}".encode()
        return f"{expiry}.{hmac.new(self._secret, message, hashlib.sha256).hexdigest()}"

    def _token_valid(
        self, command: Command, principal: Principal, spec: CommandSpec, now: datetime
    ) -> bool:
        if spec.confirmation_token is None or command.confirmation_expires_at is None:
            return False
        if command.state is not CommandState.AWAITING_CONFIRMATION:
            return False
        if now >= command.confirmation_expires_at:
            return False
        expected = self._token(principal.user_id, spec, command.confirmation_expires_at)
        return hmac.compare_digest(expected, spec.confirmation_token)

    # --- outcomes -----------------------------------------------------------------------------

    async def _ask_confirmation(
        self,
        db: AsyncSession,
        now: datetime,
        principal: Principal,
        actor: Actor,
        spec: CommandSpec,
        plan: _Plan,
        existing: Command | None,
    ) -> None:
        expires = now + self._ttl
        command = await self._save(
            db,
            now,
            principal,
            spec,
            plan,
            existing,
            CommandState.AWAITING_CONFIRMATION,
            CommandTargetState.PENDING,
            confirmation_expires_at=expires,
        )
        summary = self._summary(spec, plan)
        await audit.record(
            db,
            actor,
            now,
            "command.confirmation_request",
            entity_type="command",
            entity_id=command.id,
            details={"summary": summary.model_dump(mode="json")},
        )
        await db.commit()
        self._publish(await self.view(db, command))
        count = len(plan.accepted)
        raise ConfirmationRequiredError(
            f"Confirm {spec.kind.value} for {count} aircraft ({'; '.join(plan.reasons)}).",
            command.id,
            self._token(principal.user_id, spec, expires),
            expires,
            summary,
        )

    async def _reject_all(
        self,
        db: AsyncSession,
        now: datetime,
        principal: Principal,
        actor: Actor,
        spec: CommandSpec,
        plan: _Plan,
        existing: Command | None,
    ) -> CommandView:
        command = await self._save(
            db,
            now,
            principal,
            spec,
            plan,
            existing,
            CommandState.REJECTED,
            CommandTargetState.REJECTED,
            completed_at=now,
        )
        await audit.record(
            db,
            actor,
            now,
            "command.reject",
            entity_type="command",
            entity_id=command.id,
            details={"kind": spec.kind.value, "rejected": self._rejected(plan)},
        )
        await db.commit()
        view = await self.view(db, command)
        self._publish(view)
        return view

    async def _dispatch(
        self,
        db: AsyncSession,
        now: datetime,
        principal: Principal,
        actor: Actor,
        spec: CommandSpec,
        plan: _Plan,
        existing: Command | None,
        confirmed: bool,
    ) -> CommandView:
        command = await self._save(
            db,
            now,
            principal,
            spec,
            plan,
            existing,
            CommandState.IN_PROGRESS,
            CommandTargetState.DISPATCHED,
            confirmed_at=now if confirmed else None,
        )
        await audit.record(
            db,
            actor,
            now,
            "command.dispatch",
            entity_type="command",
            entity_id=command.id,
            details={
                "kind": spec.kind.value,
                "params": spec.params,
                "override": plan.override,
                "confirmed": confirmed,
                "aircraft": plan.accepted,
                "rejected": self._rejected(plan),
            },
        )
        await db.commit()  # never hold a transaction while aircraft answer (ADR 0019)
        self._publish(await self.view(db, command))
        await db.commit()
        for aircraft_id in plan.accepted:
            self._last_dispatch[aircraft_id] = now
        driver_command = spec.driver_command(plan.mission)
        timeout = plan.timeout_s or self._timeout
        results = await asyncio.gather(
            *(self._send(a, plan.commands.get(a, driver_command), timeout) for a in plan.accepted)
        )

        done = self._clock.now()
        outcomes: dict[str, str] = {}
        effect = expected_effect(spec.kind)
        for aircraft_id, state, code, reason in results:
            target = await db.get(CommandTarget, (command.id, aircraft_id))
            assert target is not None  # noqa: S101 - created by _save
            target.state, target.reason_code, target.reason = state, code, reason
            target.updated_at = done
            outcomes[aircraft_id] = state.value
            if state is CommandTargetState.TIMEOUT:
                record = self._registry.get(aircraft_id)
                name = record.callsign if record else aircraft_id
                await self._alerts.raise_alert(
                    db,
                    done,
                    AlertKind.COMMAND_TIMEOUT,
                    AlertSeverity.WARNING,
                    f"{name}: no answer to {spec.kind.value} within {self._timeout:g} s.",
                    aircraft_id=aircraft_id,
                    dedupe_key=f"command_timeout:{command.id}:{aircraft_id}",
                )
            if state is CommandTargetState.ACKED and effect is not None:
                self._verifications.append(
                    _Verification(
                        command.id, aircraft_id, effect, done, done + self._effect_timeout
                    )
                )
        acked = [a for a, state, _, _ in results if state is CommandTargetState.ACKED]
        if spec.kind is CommandKind.MISSION_START and acked and spec.mission_id is not None:
            await self._activate_mission(db, actor, done, spec.mission_id, acked)
        if acked and plan.gcs_mission_ids and spec.kind is CommandKind.MISSION_PAUSE:
            await self._set_missions(db, actor, done, plan.gcs_mission_ids, MissionStatus.PAUSED)
        if acked and plan.gcs_mission_ids and spec.kind is CommandKind.RESUME:
            await self._set_missions(db, actor, done, plan.gcs_mission_ids, MissionStatus.ACTIVE)
        command = await db.merge(command)
        command.state = CommandState.COMPLETED
        command.completed_at = done
        await audit.record(
            db,
            actor,
            done,
            "command.complete",
            entity_type="command",
            entity_id=command.id,
            details={"outcomes": outcomes},
        )
        await db.commit()
        view = await self.view(db, command)
        self._publish(view)
        return view

    async def _activate_mission(
        self, db: AsyncSession, actor: Actor, now: datetime, mission_id: str, acked: list[str]
    ) -> None:
        """A swarm adopted the mission: it and the acked aircraft's tasks become active."""
        mission = await db.get(Mission, mission_id)
        if mission is None or mission.status is not MissionStatus.PLANNED:
            return
        mission.status, mission.updated_at = MissionStatus.ACTIVE, now
        tasks = await db.scalars(
            select(Task).where(Task.mission_id == mission_id, Task.aircraft_id.in_(acked))
        )
        for task in tasks.all():
            task.status, task.updated_at = TaskStatus.ACTIVE, now
        if mission.search_area_id is not None:
            area = await db.get(SearchArea, mission.search_area_id)
            if area is not None and area.status is not SearchAreaStatus.SEARCHED:
                area.status, area.updated_at = SearchAreaStatus.IN_PROGRESS, now
        await audit.record(
            db,
            actor,
            now,
            "mission.activate",
            entity_type="mission",
            entity_id=mission_id,
            details={"aircraft": sorted(acked)},
        )

    async def _set_missions(
        self,
        db: AsyncSession,
        actor: Actor,
        now: datetime,
        mission_ids: set[str],
        status: MissionStatus,
    ) -> None:
        """Paused or resumed: the GCS missions of the aircraft change status."""
        for mission_id in sorted(mission_ids):
            mission = await db.get(Mission, mission_id)
            if mission is None or mission.status is status:
                continue
            if mission.status not in (MissionStatus.ACTIVE, MissionStatus.PAUSED):
                continue
            mission.status, mission.updated_at = status, now
            await audit.record(
                db,
                actor,
                now,
                "mission.pause" if status is MissionStatus.PAUSED else "mission.resume",
                entity_type="mission",
                entity_id=mission_id,
            )

    async def _send(
        self, aircraft_id: str, command: DriverCommand, limit_s: float | None = None
    ) -> tuple[str, CommandTargetState, str | None, str | None]:
        record = self._registry.get(aircraft_id)
        if record is None or record.driver is None:
            return aircraft_id, CommandTargetState.REJECTED, "no-link", "No telemetry link."
        limit = limit_s or self._timeout
        try:
            result = await asyncio.wait_for(record.driver.execute(command), limit)
        except TimeoutError:
            return (
                aircraft_id,
                CommandTargetState.TIMEOUT,
                "timeout",
                f"No answer within {limit:g} s.",
            )
        except Exception:
            log.exception("driver failed to execute %s on %s", command.kind, aircraft_id)
            return aircraft_id, CommandTargetState.NACKED, "driver-error", "The driver failed."
        if result.outcome is Outcome.ACKED:
            return aircraft_id, CommandTargetState.ACKED, None, None
        return aircraft_id, CommandTargetState.NACKED, "refused", result.reason

    # --- evaluation (tick) --------------------------------------------------------------------

    async def evaluate(self, db: AsyncSession, now: datetime) -> None:
        """Expire unconfirmed commands; verify or flag the effect of acked ones."""
        expired = await db.scalars(
            select(Command).where(
                Command.state == CommandState.AWAITING_CONFIRMATION,
                Command.confirmation_expires_at <= now,
            )
        )
        changed: set[str] = set()
        for command in expired.all():
            command.state = CommandState.EXPIRED
            await audit.record(
                db,
                SYSTEM_ACTOR,
                now,
                "command.confirmation_expire",
                entity_type="command",
                entity_id=command.id,
            )
            changed.add(command.id)
        still_pending = []
        for check in self._verifications:
            record = self._registry.get(check.aircraft_id)
            sample = record.sample if record else None
            if sample is not None and sample.ts >= check.acked_at and check.effect(sample):
                state = CommandTargetState.VERIFIED
            elif now >= check.deadline:
                state = CommandTargetState.UNVERIFIED
            else:
                still_pending.append(check)
                continue
            target = await db.get(CommandTarget, (check.command_id, check.aircraft_id))
            if target is None:  # pragma: no cover - targets are never deleted after dispatch
                continue
            target.state = state
            target.updated_at = now
            changed.add(check.command_id)
            if state is CommandTargetState.UNVERIFIED:
                target.reason_code = "no-effect"
                target.reason = "The aircraft acknowledged, but telemetry never showed the effect."
                name = record.callsign if record else check.aircraft_id
                await self._alerts.raise_alert(
                    db,
                    now,
                    AlertKind.COMMAND_UNVERIFIED,
                    AlertSeverity.WARNING,
                    f"{name}: a command was acknowledged but did not take effect.",
                    aircraft_id=check.aircraft_id,
                    dedupe_key=f"command_unverified:{check.command_id}:{check.aircraft_id}",
                )
            await audit.record(
                db,
                SYSTEM_ACTOR,
                now,
                f"command.{state.value}",
                entity_type="command",
                entity_id=check.command_id,
                details={"aircraft_id": check.aircraft_id},
            )
        self._verifications = still_pending
        await db.commit()
        for command_id in changed:
            row = await db.get(Command, command_id)
            if row is not None:
                self._publish(await self.view(db, row))
        await db.commit()

    # --- persistence and views ----------------------------------------------------------------

    async def _save(
        self,
        db: AsyncSession,
        now: datetime,
        principal: Principal,
        spec: CommandSpec,
        plan: _Plan,
        existing: Command | None,
        state: CommandState,
        accepted_state: CommandTargetState,
        *,
        confirmation_expires_at: datetime | None = None,
        confirmed_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> Command:
        command = existing or Command(
            id=spec.command_id,
            kind=spec.kind,
            params=spec.params,
            issued_by=principal.user_id,
            request_hash=spec.request_hash,
            created_at=now,
        )
        command.state = state
        command.override = plan.override
        command.confirmation_required = bool(plan.reasons)
        command.confirmation_expires_at = confirmation_expires_at
        command.confirmed_at = confirmed_at
        command.completed_at = completed_at
        db.add(command)
        await db.execute(delete(CommandTarget).where(CommandTarget.command_id == command.id))
        for aircraft_id in spec.aircraft_ids:
            rejection = plan.rejected.get(aircraft_id)
            db.add(
                CommandTarget(
                    command_id=command.id,
                    aircraft_id=aircraft_id,
                    state=CommandTargetState.REJECTED if rejection else accepted_state,
                    reason_code=rejection.code if rejection else None,
                    reason=rejection.message if rejection else None,
                    updated_at=now,
                )
            )
        await db.flush()
        return command

    def _summary(self, spec: CommandSpec, plan: _Plan) -> ConfirmationSummary:
        def callsign(aircraft_id: str) -> str:
            record = self._registry.get(aircraft_id)
            return record.callsign if record else aircraft_id

        return ConfirmationSummary(
            kind=spec.kind,
            params=spec.params,
            reasons=plan.reasons,
            override=plan.override,
            aircraft=[
                SummaryAircraft(
                    aircraft_id=a,
                    callsign=callsign(a),
                    warnings=plan.warnings.get(a, []),
                    target=(
                        GeoPoint(latitude=plan.targets[a][0], longitude=plan.targets[a][1])
                        if a in plan.targets
                        else None
                    ),
                    altitude_relative_m=plan.targets[a][2] if a in plan.targets else None,
                    start_delay_s=plan.targets[a][3] if a in plan.targets else None,
                )
                for a in plan.accepted
            ],
            conflicts=plan.conflicts,
            rejected=[
                SummaryRejection(
                    aircraft_id=a, callsign=callsign(a), code=r.code, message=r.message
                )
                for a, r in plan.rejected.items()
            ],
        )

    @staticmethod
    def _rejected(plan: _Plan) -> dict[str, str]:
        return {aircraft_id: r.code for aircraft_id, r in plan.rejected.items()}

    async def view(self, db: AsyncSession, command: Command) -> CommandView:
        """The API view of a command and its targets."""
        targets = (
            await db.scalars(select(CommandTarget).where(CommandTarget.command_id == command.id))
        ).all()
        order = {a: i for i, a in enumerate(self._registry.ids())}
        return CommandView(
            id=command.id,
            kind=command.kind,
            params=command.params,
            issued_by=command.issued_by,
            state=command.state,
            override=command.override,
            confirmation_required=command.confirmation_required,
            created_at=command.created_at,
            confirmed_at=command.confirmed_at,
            completed_at=command.completed_at,
            targets=[
                CommandTargetView(
                    aircraft_id=t.aircraft_id,
                    callsign=(r.callsign if (r := self._registry.get(t.aircraft_id)) else None),
                    state=t.state,
                    reason_code=t.reason_code,
                    reason=t.reason,
                    updated_at=t.updated_at,
                )
                for t in sorted(targets, key=lambda t: order.get(t.aircraft_id, len(order)))
            ],
        )

    def _publish(self, view: CommandView) -> None:
        self._bus.publish(COMMANDS, view, key=view.id)

    def pending_verifications(self) -> int:
        """How many acked commands still wait for their effect (for tests and diagnostics)."""
        return len(self._verifications)
