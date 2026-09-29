"""
The swarm bridge's messages on NATS (ADR 0024), as the fleet service reads and writes them.

Subjects, for swarm ``<swarm>``:

* ``sar.v1.swarm.<swarm>.status``: bridge -> station, one ``SwarmStatus`` per drone state
  heard, at most 5 Hz per drone;
* ``sar.v1.swarm.<swarm>.command``: request ``SwarmCommandRequest``, reply ``BridgeReply``;
* ``sar.v1.swarm.<swarm>.mission``: request ``SwarmMissionRequest``, reply ``BridgeReply``;
* ``sar.v1.swarm.<swarm>.bridge``: ``BridgeHeartbeat``, once per second.

The bridge (``src/sar_gcs_bridge``) has already converted the onboard units: headings are
degrees true, clockwise from north (the onboard ``DroneState.heading`` is radians,
counter-clockwise from east), and a target estimate in the mission frame is a survivor
sighting in WGS84. Times are seconds since the Unix epoch. Unknown values are null.

These models are the contract: the committed JSON Schema (``docs/api/swarm-bridge.json``)
is generated from them, and a test checks the bridge's own builders against them.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import models_json_schema

from fleet_service.domain.enums import SwarmFault, SwarmHealth, SwarmPhase

SUBJECT_PREFIX = "sar.v1.swarm"
# The onboard limits (swarm_sar.core.messages); the bridge validates with the onboard code.
MAX_DRONE_ID = 2**31 - 1
MAX_COMMAND_TARGETS = 1024
MAX_MISSION_ID_LENGTH = 64
MAX_AREA_VERTICES = 256
MAX_WAYPOINTS = 64

DroneId = Annotated[int, Field(ge=0, le=MAX_DRONE_ID)]
Sequence = Annotated[int, Field(ge=0, le=2**63 - 1)]


def subject(swarm: str, kind: str) -> str:
    """The NATS subject of a message kind (``status``, ``command``, ``mission``, ``bridge``)."""
    return f"{SUBJECT_PREFIX}.{swarm}.{kind}"


class Wire(BaseModel):
    """Strict: unknown fields are errors, so both sides notice a contract change."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SwarmCommandKind(StrEnum):
    """Operator commands of the onboard protocol (``SwarmCommand``)."""

    HOLD = "hold"
    RESUME = "resume"
    RETURN_TO_LAUNCH = "return_to_launch"
    LAND = "land"


class WirePoint(Wire):
    """A WGS84 position in degrees."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SurvivorSighting(Wire):
    """Where a drone's estimate puts a person, with its 1-sigma horizontal uncertainty."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    std_m: float = Field(ge=0)
    stamp: float = Field(description="When the estimate was valid [s, Unix epoch].")


class SwarmStatus(Wire):
    """One drone's state, as last broadcast by its companion."""

    drone_id: DroneId
    stamp: float = Field(description="The drone's own time of the state [s, Unix epoch].")
    received_at: float = Field(description="When the bridge heard it [s, Unix epoch].")
    phase: SwarmPhase
    health: SwarmHealth
    faults: list[SwarmFault]
    mission_sequence: Sequence = Field(description="Active mission (0: none).")
    command_sequence: Sequence = Field(description="Last operator command processed.")
    position: WirePoint | None
    heading_deg: float | None = Field(ge=0, lt=360, description="Degrees true, clockwise.")
    groundspeed_mps: float | None = Field(ge=0)
    velocity_north_mps: float | None
    velocity_east_mps: float | None
    nearest_obstacle_m: float | None = Field(ge=0, description="Null: none known.")
    survivor_sighting: SurvivorSighting | None


class SwarmCommandRequest(Wire):
    """Ask the bridge to publish an operator command to some drones."""

    kind: SwarmCommandKind
    drone_ids: list[DroneId] = Field(min_length=1, max_length=MAX_COMMAND_TARGETS)


class SwarmMissionRequest(Wire):
    """Ask the bridge to publish an area mission to the whole swarm."""

    mission_id: str = Field(min_length=1, max_length=MAX_MISSION_ID_LENGTH)
    origin: WirePoint
    altitude_relative_m: float = Field(gt=0, description="Above each drone's home.")
    grid_resolution_m: float = Field(gt=0)
    waypoints: list[WirePoint] = Field(max_length=MAX_WAYPOINTS)
    area: list[WirePoint] = Field(min_length=3, max_length=MAX_AREA_VERTICES)


class BridgeReply(Wire):
    """The sequence the bridge published under, or why it refused."""

    sequence: Sequence | None = None
    error: str | None = None


class BridgeHeartbeat(Wire):
    """The bridge is running and hears these drones."""

    bridge_version: str
    swarm: str
    stamp: float
    drones_heard: list[DroneId]


WIRE_MODELS: tuple[type[Wire], ...] = (
    SwarmStatus,
    SwarmCommandRequest,
    SwarmMissionRequest,
    BridgeReply,
    BridgeHeartbeat,
)


def json_schema() -> dict[str, Any]:
    """The contract as one JSON Schema document (committed in ``docs/api``)."""
    _, schema = models_json_schema([(m, "validation") for m in WIRE_MODELS])
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "SAR fleet: swarm bridge messages on NATS (ADR 0024)",
        "subjects": {
            "status": f"{SUBJECT_PREFIX}.<swarm>.status: SwarmStatus",
            "command": f"{SUBJECT_PREFIX}.<swarm>.command: SwarmCommandRequest -> BridgeReply",
            "mission": f"{SUBJECT_PREFIX}.<swarm>.mission: SwarmMissionRequest -> BridgeReply",
            "bridge": f"{SUBJECT_PREFIX}.<swarm>.bridge: BridgeHeartbeat",
        },
        "$defs": schema["$defs"],
    }
