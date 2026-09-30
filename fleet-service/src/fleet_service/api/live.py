"""Live fleet state, telemetry history, operator presence, preflight checks, and fault
injection in simulation mode."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import select

from fleet_service.api.common import InputModel, StrictBool
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import TelemetrySample as TelemetryRow
from fleet_service.db.models import User
from fleet_service.domain.enums import FlightMode, GpsFix, Role
from fleet_service.domain.geo import GeoPoint
from fleet_service.domain.preflight import PREFLIGHT_PARAMETERS
from fleet_service.drivers.mock import MockDriver
from fleet_service.errors import Conflict, NotFound, problem_responses
from fleet_service.services import audit
from fleet_service.services.preflight import PreflightReport
from fleet_service.services.views import AircraftLive, FleetState, UserRef

router = APIRouter(tags=["live"], responses=problem_responses(400, 401, 403, 404, 409, 422))

_GPS_BY_CODE = {fix.code: fix for fix in GpsFix} | {1: GpsFix.NONE}

# A console pings every 10 s: someone not heard for this long has left (or lost the link).
PRESENCE_WINDOW = timedelta(seconds=30)


class OperatorPresence(BaseModel):
    """Someone connected to this station (M5): who, their role, and when last heard."""

    user: UserRef
    role: Role
    last_seen_at: AwareDatetime


class PresenceList(BaseModel):
    """The users heard in the last 30 seconds, most recently heard first."""

    users: list[OperatorPresence]


@router.get("/presence", **requires(Permission.FLEET_VIEW))
async def list_presence(db: DbSession, context: Context) -> PresenceList:
    """Who is connected: users whose console was heard in the last 30 seconds."""
    recent = context.runtime().presence.recent(context.clock.now() - PRESENCE_WINDOW)
    if not recent:
        return PresenceList(users=[])
    users = (await db.scalars(select(User).where(User.id.in_(recent)))).all()
    listed = [
        OperatorPresence(
            user=UserRef(user_id=u.id, username=u.username, display_name=u.display_name),
            role=u.role,
            last_seen_at=recent[u.id],
        )
        for u in users
        if u.is_active
    ]
    listed.sort(key=lambda p: p.last_seen_at, reverse=True)
    return PresenceList(users=listed)


class TelemetryPoint(BaseModel):
    """One recorded telemetry sample (downsampled history, ADR 0007)."""

    ts: AwareDatetime
    position: GeoPoint | None
    altitude_amsl_m: float | None
    altitude_relative_m: float | None
    heading_deg: float | None
    groundspeed_mps: float | None
    climb_rate_mps: float | None
    battery_pct: float | None
    gps_fix: GpsFix | None
    flight_mode: FlightMode | None
    armed: bool | None
    in_air: bool | None


class TelemetryHistory(BaseModel):
    """Recorded telemetry of one aircraft, oldest first."""

    aircraft_id: str
    samples: list[TelemetryPoint]
    truncated: bool = Field(description="True if more samples match than ``limit`` allowed.")


class FaultInjection(InputModel):
    """Simulation only: inject faults into a simulated aircraft."""

    link: StrictBool | None = Field(default=None, description="false: the radio link goes down.")
    gps: StrictBool | None = Field(default=None, description="false: the GNSS fix is lost.")
    battery_pct: (
        Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0.0, le=100.0)] | None
    ) = None
    parameters: dict[str, Annotated[float, Field(allow_inf_nan=False)]] | None = Field(
        default=None,
        description="Autopilot parameters to set (the preflight parameters only), e.g. "
        '{"NAV_DLL_ACT": 0} for an aircraft that would do nothing on link loss.',
    )

    @model_validator(mode="after")
    def _something(self) -> "FaultInjection":
        if (
            self.link is None
            and self.gps is None
            and self.battery_pct is None
            and not self.parameters
        ):
            raise ValueError("inject at least one fault: link, gps, battery_pct or parameters")
        unknown = set(self.parameters or {}) - set(PREFLIGHT_PARAMETERS)
        if unknown:
            raise ValueError(f"not a preflight parameter: {', '.join(sorted(unknown))}")
        return self


class PreflightFindingView(BaseModel):
    """One problem with an aircraft's failsafe configuration."""

    parameter: str
    value: float | None
    severity: Literal["block", "warn"] = Field(
        description="block: arm and takeoff are refused (a supervisor may override); warn: shown."
    )
    message: str


class PreflightReportView(BaseModel):
    """An aircraft's failsafe parameters and the station's findings (M6, ADR 0035)."""

    aircraft_id: str
    checked_at: AwareDatetime | None = Field(description="None: never checked.")
    values: dict[str, float | None] = Field(description="None: could not be read.")
    findings: list[PreflightFindingView]
    ready: bool = Field(description="Checked, and nothing blocks arm and takeoff.")


def _preflight_view(aircraft_id: str, report: PreflightReport | None) -> PreflightReportView:
    if report is None:
        return PreflightReportView(
            aircraft_id=aircraft_id, checked_at=None, values={}, findings=[], ready=False
        )
    return PreflightReportView(
        aircraft_id=aircraft_id,
        checked_at=report.checked_at,
        values=report.values,
        findings=[
            PreflightFindingView(
                parameter=f.parameter, value=f.value, severity=f.severity.value, message=f.message
            )
            for f in report.findings
        ],
        ready=not report.blocking,
    )


@router.get("/fleet/state", **requires(Permission.FLEET_VIEW))
async def fleet_state(context: Context) -> FleetState:
    """Every registered aircraft's link, latest telemetry and controller."""
    runtime = context.runtime()
    return FleetState(
        simulation=context.settings.simulation,
        server_time=context.clock.now(),
        aircraft=runtime.registry.snapshot(),
    )


@router.get("/aircraft/{aircraft_id}/telemetry", **requires(Permission.FLEET_VIEW))
async def telemetry_history(
    aircraft_id: str,
    context: Context,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 3600,
) -> TelemetryHistory:
    """Recorded telemetry of an aircraft (1 sample per second by default)."""
    if context.runtime().registry.get(aircraft_id) is None:
        raise NotFound(f"Aircraft {aircraft_id} does not exist.")
    statement = select(TelemetryRow).where(TelemetryRow.aircraft_id == aircraft_id)
    if since is not None:
        statement = statement.where(TelemetryRow.ts_us >= int(since.timestamp() * 1_000_000))
    if until is not None:
        statement = statement.where(TelemetryRow.ts_us < int(until.timestamp() * 1_000_000))
    statement = statement.order_by(TelemetryRow.ts_us).limit(limit + 1)
    async with context.database().telemetry_session() as db:
        rows = list((await db.scalars(statement)).all())
    return TelemetryHistory(
        aircraft_id=aircraft_id,
        samples=[_point(row) for row in rows[:limit]],
        truncated=len(rows) > limit,
    )


def _point(row: TelemetryRow) -> TelemetryPoint:
    position = (
        GeoPoint(latitude=row.latitude, longitude=row.longitude)
        if row.latitude is not None and row.longitude is not None
        else None
    )
    return TelemetryPoint(
        ts=datetime.fromtimestamp(row.ts_us / 1_000_000, tz=UTC),
        position=position,
        altitude_amsl_m=row.altitude_amsl_m,
        altitude_relative_m=row.altitude_relative_m,
        heading_deg=row.heading_deg,
        groundspeed_mps=row.groundspeed_mps,
        climb_rate_mps=row.climb_rate_mps,
        battery_pct=row.battery_pct,
        gps_fix=_GPS_BY_CODE.get(row.gps_fix) if row.gps_fix is not None else None,
        flight_mode=FlightMode(row.flight_mode) if row.flight_mode else None,
        armed=row.armed,
        in_air=row.in_air,
    )


@router.get("/aircraft/{aircraft_id}/preflight", **requires(Permission.FLEET_VIEW))
async def preflight_report(aircraft_id: str, context: Context) -> PreflightReportView:
    """The last preflight check of an aircraft's failsafe parameters (arm and takeoff run
    one when theirs is older than a few minutes)."""
    runtime = context.runtime()
    if runtime.registry.get(aircraft_id) is None:
        raise NotFound(f"Aircraft {aircraft_id} does not exist.")
    return _preflight_view(aircraft_id, runtime.preflight.last(aircraft_id))


@router.post("/aircraft/{aircraft_id}/preflight", **requires(Permission.AIRCRAFT_COMMAND))
async def run_preflight(
    aircraft_id: str,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> PreflightReportView:
    """Read the aircraft's failsafe parameters now and check them (may take seconds)."""
    runtime = context.runtime()
    if runtime.registry.get(aircraft_id) is None:
        raise NotFound(f"Aircraft {aircraft_id} does not exist.")
    report = await runtime.preflight.report(aircraft_id, fresh=True)  # no session held
    await audit.record(
        db,
        actor(request, principal),
        context.clock.now(),
        "aircraft.preflight",
        entity_type="aircraft",
        entity_id=aircraft_id,
        details={
            "blocking": [f.parameter for f in report.blocking],
            "warnings": [f.parameter for f in report.warnings],
        },
    )
    await db.commit()
    return _preflight_view(aircraft_id, report)


@router.post("/simulation/aircraft/{aircraft_id}/faults", **requires(Permission.FLEET_MANAGE))
async def inject_fault(
    aircraft_id: str,
    body: FaultInjection,
    request: Request,
    db: DbSession,
    context: Context,
    principal: CurrentPrincipal,
) -> AircraftLive:
    """Simulation mode only: take a simulated aircraft's link or GNSS away, or set its battery."""
    runtime = context.runtime()
    if runtime.simulator is None:
        raise Conflict("The station is not in simulation mode.", slug="simulation-disabled")
    record = runtime.registry.get(aircraft_id)
    if record is None:
        raise NotFound(f"Aircraft {aircraft_id} does not exist.")
    driver = record.driver
    if not isinstance(driver, MockDriver):  # pragma: no cover - simulation backs every aircraft
        raise Conflict("This aircraft is not simulated.", slug="simulation-disabled")
    driver.inject(
        link=body.link, gps=body.gps, battery_pct=body.battery_pct, parameters=body.parameters
    )
    if body.parameters:
        runtime.preflight.forget(aircraft_id)
    await audit.record(
        db,
        actor(request, principal),
        context.clock.now(),
        "simulation.fault",
        entity_type="aircraft",
        entity_id=aircraft_id,
        details=body.model_dump(exclude_none=True),
    )
    await db.commit()
    runtime.registry.announce(aircraft_id)
    live = runtime.registry.live(aircraft_id)
    if live is None:  # pragma: no cover - checked above
        raise NotFound(f"Aircraft {aircraft_id} does not exist.")
    return live
