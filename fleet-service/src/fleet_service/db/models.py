"""
ORM models of ``ops.db`` (operational data and audit) and ``telemetry.db`` (samples).

Timestamps are set by the application from the injected clock, never by database
defaults, so tests control them and every row agrees with the audit trail.
Ids are UUIDv7 strings (``fleet_service.ids``). The schema of ``alerts``,
``commands``, ``command_targets``, ``control_leases`` and ``telemetry_samples`` is
defined here; their behaviour arrives in M1b (which may amend them by migration).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from fleet_service.db.types import UTCDateTime, enum_type
from fleet_service.domain.enums import (
    Airframe,
    AlertKind,
    AlertSeverity,
    AlertState,
    CommandKind,
    CommandState,
    CommandTargetState,
    GeofenceKind,
    IncidentStatus,
    LeaseState,
    MissionKind,
    MissionStatus,
    PoiKind,
    PoiStatus,
    Role,
    SearchAreaStatus,
    TaskStatus,
    VideoCodec,
)

# Named constraints, so SQLite batch migrations can find and alter them later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ID = String(36)


class OpsBase(DeclarativeBase):
    """Declarative base of ``ops.db``."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: UTCDateTime()}  # noqa: RUF012 - SQLAlchemy ClassVar


class TelemetryBase(DeclarativeBase):
    """Declarative base of ``telemetry.db``."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: UTCDateTime()}  # noqa: RUF012 - SQLAlchemy ClassVar


# --- people and access -----------------------------------------------------------------


class User(OpsBase):
    """An operator account. Never deleted (audit attribution); deactivated instead."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(enum_type(Role))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    last_login_at: Mapped[datetime | None]


class UserSession(OpsBase):
    """A login session. Only the SHA-256 of the bearer token is stored (ADR 0009)."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    user_agent: Mapped[str | None] = mapped_column(String(256))
    source_ip: Mapped[str | None] = mapped_column(String(64))


# --- fleet -------------------------------------------------------------------------------

aircraft_group_members = Table(
    "aircraft_group_members",
    OpsBase.metadata,
    Column("group_id", ForeignKey("aircraft_groups.id", ondelete="CASCADE"), primary_key=True),
    Column("aircraft_id", ForeignKey("aircraft.id", ondelete="CASCADE"), primary_key=True),
)


class Aircraft(OpsBase):
    """A registered aircraft and how to reach it (ADR 0003: both links may exist)."""

    __tablename__ = "aircraft"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    callsign: Mapped[str] = mapped_column(String(32), unique=True)
    airframe: Mapped[Airframe] = mapped_column(enum_type(Airframe))
    mavlink_system_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    mavlink_connection: Mapped[str | None] = mapped_column(String(200))
    swarm_drone_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    cruise_speed_mps: Mapped[float | None] = mapped_column(Float)
    endurance_s: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    groups: Mapped[list["AircraftGroup"]] = relationship(
        secondary=aircraft_group_members, back_populates="members", lazy="selectin"
    )


class AircraftGroup(OpsBase):
    """A named set of aircraft, for selection and bulk tasking."""

    __tablename__ = "aircraft_groups"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    members: Mapped[list[Aircraft]] = relationship(
        secondary=aircraft_group_members, back_populates="groups", lazy="selectin"
    )


# --- incident, areas, missions -------------------------------------------------------------


class Incident(OpsBase):
    """A SAR incident: the scope of areas, geofences and missions, with an operating area."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IncidentStatus] = mapped_column(enum_type(IncidentStatus))
    base_latitude: Mapped[float] = mapped_column(Float)
    base_longitude: Mapped[float] = mapped_column(Float)
    base_altitude_amsl_m: Mapped[float | None] = mapped_column(Float)
    operating_radius_m: Mapped[float] = mapped_column(Float)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]


class SearchArea(OpsBase):
    """A polygon to be searched (GeoJSON, validated against the incident's operating area)."""

    __tablename__ = "search_areas"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON)
    area_m2: Mapped[float] = mapped_column(Float)
    priority: Mapped[int] = mapped_column(Integer)
    status: Mapped[SearchAreaStatus] = mapped_column(enum_type(SearchAreaStatus))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Geofence(OpsBase):
    """An inclusion or exclusion polygon with an optional altitude ceiling."""

    __tablename__ = "geofences"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[GeofenceKind] = mapped_column(enum_type(GeofenceKind))
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON)
    max_altitude_relative_m: Mapped[float | None] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Mission(OpsBase):
    """What to fly: a waypoint route, a GCS-planned area search, or a swarm area search."""

    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[MissionKind] = mapped_column(enum_type(MissionKind))
    status: Mapped[MissionStatus] = mapped_column(enum_type(MissionStatus))
    search_area_id: Mapped[str | None] = mapped_column(ForeignKey("search_areas.id"), index=True)
    default_altitude_relative_m: Mapped[float] = mapped_column(Float)
    default_speed_mps: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    # The saved plan (ADR 0028/0029): pattern parameters and the deconfliction report.
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    waypoints: Mapped[list["Waypoint"]] = relationship(
        order_by="Waypoint.seq", cascade="all, delete-orphan", lazy="selectin"
    )


class Waypoint(OpsBase):
    """One point of a mission route; altitude is relative to each aircraft's home (ADR 0014)."""

    __tablename__ = "waypoints"
    __table_args__ = (UniqueConstraint("mission_id", "seq"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("missions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    altitude_relative_m: Mapped[float] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    loiter_s: Mapped[float | None] = mapped_column(Float)


class Task(OpsBase):
    """An aircraft assigned to a mission, with per-aircraft overrides."""

    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("mission_id", "aircraft_id"),)

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("missions.id", ondelete="CASCADE"), index=True
    )
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id"), index=True)
    status: Mapped[TaskStatus] = mapped_column(enum_type(TaskStatus))
    altitude_relative_m: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    start_delay_s: Mapped[float | None] = mapped_column(Float)
    # The planned route (list of waypoints, altitudes above home) and how it was made.
    route: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Poi(OpsBase):
    """A point of interest of an incident, marked by an operator or reported by a drone."""

    __tablename__ = "pois"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    kind: Mapped[PoiKind] = mapped_column(enum_type(PoiKind))
    status: Mapped[PoiStatus] = mapped_column(enum_type(PoiStatus))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    uncertainty_m: Mapped[float | None] = mapped_column(Float)
    aircraft_id: Mapped[str | None] = mapped_column(
        ForeignKey("aircraft.id", ondelete="SET NULL"), index=True
    )  # the reporting aircraft (None: marked by an operator)
    reported_at: Mapped[datetime | None]  # when the aircraft saw it
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class VideoStream(OpsBase):
    """Where an aircraft's (or fixed camera's) video comes from and its relay path (ADR 0012)."""

    __tablename__ = "video_streams"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    aircraft_id: Mapped[str | None] = mapped_column(
        ForeignKey("aircraft.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(500))
    relay_path: Mapped[str] = mapped_column(String(64), unique=True)
    codec: Mapped[VideoCodec] = mapped_column(enum_type(VideoCodec))
    enabled: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


# --- live operations (schema now, behaviour in M1b) ----------------------------------------


class Alert(OpsBase):
    """An operator-facing alert."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    kind: Mapped[AlertKind] = mapped_column(enum_type(AlertKind))
    severity: Mapped[AlertSeverity] = mapped_column(enum_type(AlertSeverity))
    state: Mapped[AlertState] = mapped_column(enum_type(AlertState), index=True)
    aircraft_id: Mapped[str | None] = mapped_column(
        ForeignKey("aircraft.id", ondelete="SET NULL"), index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(128), index=True)
    message: Mapped[str] = mapped_column(Text)
    raised_at: Mapped[datetime]
    acknowledged_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None]
    cleared_at: Mapped[datetime | None]
    escalated_at: Mapped[datetime | None]  # a warning left unacknowledged became critical


class Command(OpsBase):
    """An operator command, possibly to many aircraft; ``id`` is the client's command_id."""

    __tablename__ = "commands"

    id: Mapped[str] = mapped_column(ID, primary_key=True)
    kind: Mapped[CommandKind] = mapped_column(enum_type(CommandKind))
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    issued_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[CommandState] = mapped_column(enum_type(CommandState))
    confirmation_required: Mapped[bool] = mapped_column(Boolean)
    confirmation_expires_at: Mapped[datetime | None]
    override: Mapped[bool] = mapped_column(Boolean, server_default=false())
    confirmed_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]


class CommandTarget(OpsBase):
    """The outcome of one command for one aircraft."""

    __tablename__ = "command_targets"

    command_id: Mapped[str] = mapped_column(
        ForeignKey("commands.id", ondelete="CASCADE"), primary_key=True
    )
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id"), primary_key=True)
    state: Mapped[CommandTargetState] = mapped_column(enum_type(CommandTargetState))
    reason_code: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime]


class ControlLease(OpsBase):
    """Which operator controls an aircraft (ADR 0011); at most one lease per aircraft."""

    __tablename__ = "control_leases"

    aircraft_id: Mapped[str] = mapped_column(
        ForeignKey("aircraft.id", ondelete="CASCADE"), primary_key=True
    )
    holder_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[LeaseState] = mapped_column(enum_type(LeaseState))
    acquired_at: Mapped[datetime]
    holder_seen_at: Mapped[datetime]
    pending_request_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    pending_request_at: Mapped[datetime | None]


# --- audit -----------------------------------------------------------------------------------


class AuditEvent(OpsBase):
    """
    Append-only, hash-chained audit record (ADR 0007).

    No foreign keys: the audit trail must never be blocked or altered by other tables.
    ``seq`` uses SQLite AUTOINCREMENT semantics, so a sequence number is never reused.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        {"sqlite_autoincrement": True},
    )

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ID, unique=True)
    ts: Mapped[datetime] = mapped_column(index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ID, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(ID)
    request_id: Mapped[str | None] = mapped_column(String(64))
    source_ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


# --- telemetry.db ------------------------------------------------------------------------------


class TelemetrySample(TelemetryBase):
    """
    One stored telemetry sample (downsampled, ADR 0007). Every measurement is nullable:
    an unknown value is stored as unknown, never as a plausible default (ADR 0002, S7).
    """

    __tablename__ = "telemetry_samples"
    __table_args__ = (Index("ix_telemetry_samples_aircraft_ts", "aircraft_id", "ts_us"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aircraft_id: Mapped[str] = mapped_column(ID)
    ts_us: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(16))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    altitude_amsl_m: Mapped[float | None] = mapped_column(Float)
    altitude_relative_m: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    groundspeed_mps: Mapped[float | None] = mapped_column(Float)
    climb_rate_mps: Mapped[float | None] = mapped_column(Float)
    battery_pct: Mapped[float | None] = mapped_column(Float)
    battery_v: Mapped[float | None] = mapped_column(Float)
    gps_fix: Mapped[int | None] = mapped_column(Integer)
    satellites: Mapped[int | None] = mapped_column(Integer)
    flight_mode: Mapped[str | None] = mapped_column(String(32))
    armed: Mapped[bool | None] = mapped_column(Boolean)
    in_air: Mapped[bool | None] = mapped_column(Boolean)
