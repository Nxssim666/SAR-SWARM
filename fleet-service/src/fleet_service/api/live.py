"""Live fleet state, telemetry history, and fault injection in simulation mode."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import select

from fleet_service.api.common import InputModel, StrictBool
from fleet_service.api.deps import Context, CurrentPrincipal, DbSession, actor, requires
from fleet_service.auth.permissions import Permission
from fleet_service.db.models import TelemetrySample as TelemetryRow
from fleet_service.domain.enums import FlightMode, GpsFix
from fleet_service.domain.geo import GeoPoint
from fleet_service.drivers.mock import MockDriver
from fleet_service.errors import Conflict, NotFound, problem_responses
from fleet_service.services import audit
from fleet_service.services.views import AircraftLive, FleetState

router = APIRouter(tags=["live"], responses=problem_responses(400, 401, 403, 404, 409, 422))

_GPS_BY_CODE = {fix.code: fix for fix in GpsFix} | {1: GpsFix.NONE}


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

    @model_validator(mode="after")
    def _something(self) -> "FaultInjection":
        if self.link is None and self.gps is None and self.battery_pct is None:
            raise ValueError("inject at least one fault: link, gps or battery_pct")
        return self


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
    driver.inject(link=body.link, gps=body.gps, battery_pct=body.battery_pct)
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
