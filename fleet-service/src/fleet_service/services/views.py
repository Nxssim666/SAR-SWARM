"""
Live-state views shared by the REST API and the WebSocket API (one shape, both channels).

These are output models: built from in-memory state and rows, never parsed from clients.
"""

from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict

from fleet_service.domain.enums import (
    Airframe,
    AlertKind,
    AlertSeverity,
    AlertState,
    CommandKind,
    CommandState,
    CommandTargetState,
    FlightMode,
    GpsFix,
    LeaseState,
    LinkState,
)
from fleet_service.domain.geo import GeoPoint
from fleet_service.domain.telemetry import TelemetrySample


class View(BaseModel):
    """Base of live views."""

    model_config = ConfigDict(from_attributes=True)


class TelemetryView(View):
    """The latest telemetry of an aircraft; unknown values are null (ADR 0002, S7)."""

    ts: AwareDatetime
    source: str
    position: GeoPoint | None
    altitude_amsl_m: float | None
    altitude_relative_m: float | None
    heading_deg: float | None
    groundspeed_mps: float | None
    climb_rate_mps: float | None
    battery_pct: float | None
    battery_v: float | None
    gps_fix: GpsFix
    satellites: int | None
    flight_mode: FlightMode
    armed: bool | None
    in_air: bool | None
    home: GeoPoint | None

    @classmethod
    def of(cls, s: TelemetrySample) -> "TelemetryView":
        """Build from a sample."""
        position = (
            GeoPoint(latitude=s.latitude, longitude=s.longitude)
            if s.latitude is not None and s.longitude is not None
            else None
        )
        home = (
            GeoPoint(latitude=s.home_latitude, longitude=s.home_longitude)
            if s.home_latitude is not None and s.home_longitude is not None
            else None
        )
        return cls(
            ts=s.ts,
            source=s.source,
            position=position,
            altitude_amsl_m=s.altitude_amsl_m,
            altitude_relative_m=s.altitude_relative_m,
            heading_deg=s.heading_deg,
            groundspeed_mps=s.groundspeed_mps,
            climb_rate_mps=s.climb_rate_mps,
            battery_pct=s.battery_pct,
            battery_v=s.battery_v,
            gps_fix=s.gps_fix,
            satellites=s.satellites,
            flight_mode=s.flight_mode,
            armed=s.armed,
            in_air=s.in_air,
            home=home,
        )


class UserRef(View):
    """A user, as shown next to what they do."""

    user_id: str
    username: str
    display_name: str


class HandoverRequestView(View):
    """A pending request to take over control."""

    requested_by: UserRef
    requested_at: AwareDatetime
    expires_at: AwareDatetime


class LeaseView(View):
    """Who controls an aircraft (ADR 0011)."""

    aircraft_id: str
    holder: UserRef
    state: LeaseState
    acquired_at: AwareDatetime
    pending_request: HandoverRequestView | None


class ControlChange(View):
    """A change of an aircraft's control lease (the lease after it, or null if none)."""

    aircraft_id: str
    change: str
    lease: LeaseView | None


class AircraftLive(View):
    """One aircraft's live state: link, latest telemetry, controller."""

    aircraft_id: str
    callsign: str
    airframe: Airframe
    link: LinkState
    last_seen_at: AwareDatetime | None
    telemetry: TelemetryView | None
    controller: LeaseView | None


class FleetState(View):
    """Every registered aircraft's live state."""

    simulation: bool
    server_time: AwareDatetime
    aircraft: list[AircraftLive]


class AlertView(View):
    """An operator-facing alert."""

    id: str
    kind: AlertKind
    severity: AlertSeverity
    state: AlertState
    aircraft_id: str | None
    message: str
    raised_at: AwareDatetime
    acknowledged_by: str | None
    acknowledged_at: AwareDatetime | None
    cleared_at: AwareDatetime | None


class CommandTargetView(View):
    """The outcome of a command for one aircraft."""

    aircraft_id: str
    callsign: str | None
    state: CommandTargetState
    reason_code: str | None
    reason: str | None
    updated_at: AwareDatetime


class CommandView(View):
    """A command and its per-aircraft outcome."""

    id: str
    kind: CommandKind
    params: dict[str, Any]
    issued_by: str
    state: CommandState
    override: bool
    confirmation_required: bool
    created_at: AwareDatetime
    confirmed_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    targets: list[CommandTargetView]
