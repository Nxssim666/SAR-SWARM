"""
WebSocket protocol messages (ADR 0013, ADR 0020); the AsyncAPI document is generated
from these models (``fleet_service.asyncapi``).

Client -> server: ``auth`` (first message, within 5 s), ``subscribe``, ``unsubscribe``,
``ping``. Server -> client: ``welcome``, ``snapshot`` (once per subscribed topic, then
``event``s), ``pong``, ``error``, ``session_ended``. Every server message carries ``seq``
(per connection, starting at 1) and ``ts``.

Close codes: 4400 malformed message, 4401 not authenticated / session ended, 4403 not
permitted, 4408 no authentication or no client message in time, 4429 the client could
not keep up with reliable events (reconnect and resync; nothing was dropped silently).
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, StringConstraints

from fleet_service.api.common import InputModel
from fleet_service.auth.permissions import Permission
from fleet_service.domain.enums import Role
from fleet_service.services.views import (
    AircraftLive,
    AlertView,
    CommandView,
    ControlChange,
    LeaseView,
    MissionProgressView,
    PoiView,
    UserRef,
)

Topic = Literal["fleet.telemetry", "alerts", "commands", "control", "missions", "pois"]

CLOSE_BAD_MESSAGE = 4400
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_TIMEOUT = 4408
CLOSE_TOO_SLOW = 4429


def _unique(topics: list[Topic]) -> list[Topic]:
    if len(set(topics)) != len(topics):
        raise ValueError("topics must not repeat")
    return topics


Topics = Annotated[
    list[Topic],
    AfterValidator(_unique),
    Field(min_length=1, max_length=6, json_schema_extra={"uniqueItems": True}),
]

# --- client -> server ----------------------------------------------------------------------------


class AuthMessage(InputModel):
    """First message: the session token from POST /api/v1/auth/login."""

    type: Literal["auth"]
    token: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class SubscribeMessage(InputModel):
    """Start receiving topics: a snapshot of each, then events."""

    type: Literal["subscribe"]
    topics: Topics
    telemetry_hz: Annotated[float, Field(strict=True, ge=0.5, le=10.0)] = Field(
        default=4.0, description="Rate of fleet.telemetry batches (newest state per aircraft)."
    )


class UnsubscribeMessage(InputModel):
    """Stop receiving topics."""

    type: Literal["unsubscribe"]
    topics: Topics


class PingMessage(InputModel):
    """Keep-alive; also tells the station the operator is still here (ADR 0011 presence)."""

    type: Literal["ping"]


ClientMessage = Annotated[
    AuthMessage | SubscribeMessage | UnsubscribeMessage | PingMessage,
    Field(discriminator="type"),
]

# --- server -> client ----------------------------------------------------------------------------


class ServerMessage(BaseModel):
    seq: int = Field(ge=1, description="Per-connection sequence number; gaps never occur.")
    ts: AwareDatetime


class WelcomeMessage(ServerMessage):
    """Authentication succeeded."""

    type: Literal["welcome"] = "welcome"
    user: UserRef
    role: Role
    permissions: list[Permission]
    session_expires_at: AwareDatetime
    simulation: bool


class TelemetryBatch(BaseModel):
    """Live states of aircraft (all of them in a snapshot, the changed ones in an event)."""

    aircraft: list[AircraftLive]


class AlertsSnapshotData(BaseModel):
    """Every open (active or acknowledged) alert."""

    alerts: list[AlertView]


class CommandsSnapshotData(BaseModel):
    """The most recent commands, newest first."""

    commands: list[CommandView]


class ControlSnapshotData(BaseModel):
    """Every control lease."""

    leases: list[LeaseView]


class TelemetrySnapshot(ServerMessage):
    """Every aircraft's live state, on subscribing to fleet.telemetry."""

    type: Literal["snapshot"] = "snapshot"
    topic: Literal["fleet.telemetry"] = "fleet.telemetry"
    data: TelemetryBatch


class AlertsSnapshot(ServerMessage):
    """Open alerts, on subscribing to alerts."""

    type: Literal["snapshot"] = "snapshot"
    topic: Literal["alerts"] = "alerts"
    data: AlertsSnapshotData


class CommandsSnapshot(ServerMessage):
    """Recent commands, on subscribing to commands."""

    type: Literal["snapshot"] = "snapshot"
    topic: Literal["commands"] = "commands"
    data: CommandsSnapshotData


class ControlSnapshot(ServerMessage):
    """Control leases, on subscribing to control."""

    type: Literal["snapshot"] = "snapshot"
    topic: Literal["control"] = "control"
    data: ControlSnapshotData


class TelemetryEvent(ServerMessage):
    """Aircraft whose live state changed, at most ``telemetry_hz`` times per second."""

    type: Literal["event"] = "event"
    topic: Literal["fleet.telemetry"] = "fleet.telemetry"
    data: TelemetryBatch


class AlertEvent(ServerMessage):
    """An alert was raised, acknowledged or cleared."""

    type: Literal["event"] = "event"
    topic: Literal["alerts"] = "alerts"
    data: AlertView


class CommandEvent(ServerMessage):
    """A command changed state (confirmation, dispatch, outcome, verification)."""

    type: Literal["event"] = "event"
    topic: Literal["commands"] = "commands"
    data: CommandView


class ControlEvent(ServerMessage):
    """A control lease changed."""

    type: Literal["event"] = "event"
    topic: Literal["control"] = "control"
    data: ControlChange


class MissionsSnapshotData(BaseModel):
    """Every planned, running or paused GCS mission's progress."""

    missions: list[MissionProgressView]


class PoisSnapshotData(BaseModel):
    """The points of interest of the open incidents (dismissed and resolved ones too)."""

    pois: list[PoiView]


class MissionsSnapshot(ServerMessage):
    """Mission progress, on subscribing to missions."""

    type: Literal["snapshot"] = "snapshot"
    topic: Literal["missions"] = "missions"
    data: MissionsSnapshotData


class PoisSnapshot(ServerMessage):
    """Points of interest, on subscribing to pois."""

    type: Literal["snapshot"] = "snapshot"
    topic: Literal["pois"] = "pois"
    data: PoisSnapshotData


class MissionEvent(ServerMessage):
    """A mission's status or progress changed (at most once a second per mission)."""

    type: Literal["event"] = "event"
    topic: Literal["missions"] = "missions"
    data: MissionProgressView


class PoiEvent(ServerMessage):
    """A point of interest was marked, reported by a drone, or changed."""

    type: Literal["event"] = "event"
    topic: Literal["pois"] = "pois"
    data: PoiView


class PongMessage(ServerMessage):
    """Answer to ping."""

    type: Literal["pong"] = "pong"


class ErrorMessage(ServerMessage):
    """A message could not be processed; the connection stays open unless closed after."""

    type: Literal["error"] = "error"
    code: str
    message: str


class SessionEndedMessage(ServerMessage):
    """The session was revoked or expired; the connection closes with 4401."""

    type: Literal["session_ended"] = "session_ended"
    reason: str


CLIENT_MESSAGES: list[type[BaseModel]] = [
    AuthMessage,
    SubscribeMessage,
    UnsubscribeMessage,
    PingMessage,
]
SERVER_MESSAGES: list[type[ServerMessage]] = [
    WelcomeMessage,
    TelemetrySnapshot,
    AlertsSnapshot,
    CommandsSnapshot,
    ControlSnapshot,
    MissionsSnapshot,
    PoisSnapshot,
    TelemetryEvent,
    AlertEvent,
    CommandEvent,
    ControlEvent,
    MissionEvent,
    PoiEvent,
    PongMessage,
    ErrorMessage,
    SessionEndedMessage,
]


def server_model(type_: str, topic: str | None) -> type[ServerMessage]:
    """The model of a server message, by its ``type`` and ``topic``."""
    for model in SERVER_MESSAGES:
        fields = model.model_fields
        if fields["type"].default != type_:
            continue
        if "topic" in fields and fields["topic"].default != topic:
            continue
        return model
    raise KeyError((type_, topic))
