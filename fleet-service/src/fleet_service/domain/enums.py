"""
Enumerations of the domain model and the state transitions the REST API may perform.

Values are stored in the database and sent over the API, so they are part of the
contract: add values freely, never rename or remove one without a migration and an ADR.
"""

from enum import StrEnum


class Role(StrEnum):
    """Operator roles, lowest to highest authority (ADR 0009)."""

    OBSERVER = "observer"
    OPERATOR = "operator"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"


ROLE_RANK: dict[Role, int] = {role: rank for rank, role in enumerate(Role)}


class Airframe(StrEnum):
    """Aircraft type; drives planning constraints (turn radius, hover ability)."""

    FIXED_WING = "fixed_wing"
    MULTIROTOR_HEXA = "multirotor_hexa"
    MULTIROTOR_QUAD = "multirotor_quad"


class IncidentStatus(StrEnum):
    """Lifecycle of an incident; ``closed`` is terminal and read-only."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


INCIDENT_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.ACTIVE: frozenset({IncidentStatus.SUSPENDED, IncidentStatus.CLOSED}),
    IncidentStatus.SUSPENDED: frozenset({IncidentStatus.ACTIVE, IncidentStatus.CLOSED}),
    IncidentStatus.CLOSED: frozenset(),
}


class SearchAreaStatus(StrEnum):
    """Search progress of an area; set by operators (ground teams too) or, from M4, missions."""

    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SEARCHED = "searched"


class GeofenceKind(StrEnum):
    """Inclusion: aircraft must stay inside. Exclusion: aircraft must stay outside."""

    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"


class MissionKind(StrEnum):
    """Waypoint route, GCS-planned area search (model A), swarm area search (model B, ADR 0003)."""

    WAYPOINT = "waypoint"
    AREA_SEARCH = "area_search"
    SWARM_AREA = "swarm_area"


class MissionStatus(StrEnum):
    """Mission lifecycle. ``active``, ``paused`` and ``completed`` are set by execution only."""

    DRAFT = "draft"
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"


# Transitions an operator may request through the REST API; execution (M1b/M4) owns the rest.
MISSION_REST_TRANSITIONS: dict[MissionStatus, frozenset[MissionStatus]] = {
    MissionStatus.DRAFT: frozenset({MissionStatus.PLANNED, MissionStatus.ABORTED}),
    MissionStatus.PLANNED: frozenset({MissionStatus.DRAFT, MissionStatus.ABORTED}),
}
EDITABLE_MISSION_STATUSES = frozenset({MissionStatus.DRAFT, MissionStatus.PLANNED})

MAX_MISSION_WAYPOINTS = 1000
# The onboard swarm protocol's limit on transit waypoints (swarm_sar.core.messages.MAX_WAYPOINTS).
MAX_SWARM_MISSION_WAYPOINTS = 64


class PoiKind(StrEnum):
    """A point of interest: a place operators mark, or a survivor sighting a drone reports."""

    POI = "poi"
    SURVIVOR_SIGHTING = "survivor_sighting"
    CLUE = "clue"
    HAZARD = "hazard"


class PoiStatus(StrEnum):
    """What operators made of a point of interest."""

    NEW = "new"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class TaskStatus(StrEnum):
    """An aircraft's assignment to a mission."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TASK_REST_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.CANCELLED}),
}


class VideoCodec(StrEnum):
    """Codec of a video source (ADR 0012: H.264 is the baseline)."""

    H264 = "h264"
    H265 = "h265"
    UNKNOWN = "unknown"


class AlertKind(StrEnum):
    """What an alert is about (engine from M1b/M4)."""

    LINK_STALE = "link_stale"
    LINK_LOST = "link_lost"
    BATTERY_LOW = "battery_low"
    BATTERY_CRITICAL = "battery_critical"
    GPS_LOST = "gps_lost"
    GEOFENCE_BREACH = "geofence_breach"
    MISSION_COMPLETE = "mission_complete"
    ROUTE_DEVIATION = "route_deviation"
    DECONFLICTION_RISK = "deconfliction_risk"
    COMMAND_TIMEOUT = "command_timeout"
    COMMAND_UNVERIFIED = "command_unverified"
    CONTROL_ORPHANED = "control_orphaned"
    VIDEO_DOWN = "video_down"
    SURVIVOR_SIGHTING = "survivor_sighting"  # a drone reports a possible survivor (M4)
    RETURN_ENERGY = "return_energy"  # the battery barely covers the way home (M4)
    LINK_PARTIAL = "link_partial"  # one of an aircraft's two links is lost (M4)


class AlertSeverity(StrEnum):
    """How urgently an operator must look."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertState(StrEnum):
    """Alert lifecycle."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"


class CommandKind(StrEnum):
    """Commands the GCS can send (ADR 0002 scope; no flight termination)."""

    ARM = "arm"
    DISARM = "disarm"
    TAKEOFF = "takeoff"
    HOLD = "hold"
    RESUME = "resume"
    RETURN_TO_LAUNCH = "return_to_launch"
    LAND = "land"
    GOTO = "goto"
    MISSION_UPLOAD = "mission_upload"
    MISSION_START = "mission_start"
    MISSION_PAUSE = "mission_pause"
    GEOFENCE_UPLOAD = "geofence_upload"


class CommandState(StrEnum):
    """Overall state of a (possibly bulk) command (ADR 0011)."""

    AWAITING_CONFIRMATION = "awaiting_confirmation"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CommandTargetState(StrEnum):
    """Outcome of a command for one aircraft."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    ACKED = "acked"
    NACKED = "nacked"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    VERIFIED = "verified"  # acked, and telemetry showed the expected effect
    UNVERIFIED = "unverified"  # acked, but the effect never showed within the timeout


FINAL_TARGET_STATES = frozenset(
    {
        CommandTargetState.NACKED,
        CommandTargetState.TIMEOUT,
        CommandTargetState.REJECTED,
        CommandTargetState.VERIFIED,
        CommandTargetState.UNVERIFIED,
    }
)


class LeaseState(StrEnum):
    """Control lease of an aircraft (ADR 0011)."""

    HELD = "held"
    ORPHANED = "orphaned"


class FlightMode(StrEnum):
    """Autopilot-agnostic flight mode shown to operators (drivers map to it)."""

    HOLD = "hold"  # hover / loiter at the current position
    TAKEOFF = "takeoff"
    GOTO = "goto"  # flying to an operator-given position
    MISSION = "mission"
    RETURN = "return"
    LAND = "land"
    MANUAL = "manual"  # a pilot flies it (RC)
    OFFBOARD = "offboard"  # an onboard computer steers it (the swarm companion, ADR 0003)
    UNKNOWN = "unknown"


class LinkState(StrEnum):
    """Freshness of an aircraft's telemetry (ADR 0010)."""

    LIVE = "live"
    STALE = "stale"
    LOST = "lost"
    OFFLINE = "offline"  # no driver, or no telemetry received yet


class GpsFix(StrEnum):
    """GNSS fix quality; MAVLink GPS_FIX_TYPE codes are kept for storage."""

    NONE = "none"
    FIX_2D = "2d"
    FIX_3D = "3d"
    DGPS = "dgps"
    RTK_FLOAT = "rtk_float"
    RTK_FIXED = "rtk_fixed"

    @property
    def code(self) -> int:
        """MAVLink GPS_FIX_TYPE value."""
        return _GPS_CODES[self]

    @property
    def has_3d(self) -> bool:
        """True for fixes good enough to navigate by."""
        return self not in (GpsFix.NONE, GpsFix.FIX_2D)


_GPS_CODES = {
    GpsFix.NONE: 0,
    GpsFix.FIX_2D: 2,
    GpsFix.FIX_3D: 3,
    GpsFix.DGPS: 4,
    GpsFix.RTK_FLOAT: 5,
    GpsFix.RTK_FIXED: 6,
}


class SwarmPhase(StrEnum):
    """What a swarm companion is doing (onboard ``DroneState.PHASE_*``, ADR 0003)."""

    STANDBY = "standby"  # no mission
    TRANSIT = "transit"
    SEARCH = "search"
    TRACK = "track"  # converging on a survivor sighting
    HOLD = "hold"


# Phases in which a companion is working a mission (what RESUME and a mission start lead to).
SWARM_WORKING = frozenset({SwarmPhase.TRANSIT, SwarmPhase.SEARCH, SwarmPhase.TRACK})


class SwarmHealth(StrEnum):
    """A swarm companion's own health verdict (onboard ``DroneState.HEALTH_*``)."""

    OK = "ok"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class SwarmFault(StrEnum):
    """Bits of the onboard ``DroneState.faults``, by name."""

    FC_LINK = "fc_link"
    POSE_STALE = "pose_stale"
    POSE_INVALID = "pose_invalid"
    ATTITUDE_STALE = "attitude_stale"
    NO_GLOBAL_REFERENCE = "no_global_reference"
    DEPTH_STALE = "depth_stale"
    DEPTH_BLIND = "depth_blind"
    OUTSIDE_GEOFENCE = "outside_geofence"
    ALTITUDE_MISMATCH = "altitude_mismatch"
    WAYPOINT_UNREACHABLE = "waypoint_unreachable"
    MISSION_REJECTED = "mission_rejected"
    CONTROL_OVERRUN = "control_overrun"
    RADIO_SILENT = "radio_silent"


class LinkSource(StrEnum):
    """The links an aircraft can have (ADR 0025)."""

    MAVLINK = "mavlink"
    SWARM = "swarm"
