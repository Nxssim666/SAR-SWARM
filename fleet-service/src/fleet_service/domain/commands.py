"""
Command rules (ADR 0011): who may send which command, in which vehicle state, and what
needs an explicit confirmation. Pure functions over plain data, tested row by row.

Unknown state is never assumed favourable (ADR 0002, S7): a command whose precondition
needs a known value is rejected while that value is unknown. The exceptions are HOLD,
RETURN and LAND, which only require that the aircraft is not known to be on the ground,
because they are how an operator makes a degraded situation safer.

Swarm aircraft (ADR 0003) report their companion's phase instead of an autopilot mode;
the rules read it where the autopilot's state is not reported. An aircraft with both a
MAVLink and a swarm link gets each command over the link ``route_command`` picks (ADR 0025).
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass

from fleet_service.domain.enums import (
    SWARM_WORKING,
    CommandKind,
    FlightMode,
    LinkSource,
    LinkState,
    MissionKind,
    MissionStatus,
    SwarmPhase,
)
from fleet_service.domain.geo import GeoPoint, distance_m
from fleet_service.domain.geofence import GeofenceSet
from fleet_service.domain.telemetry import TelemetrySample

# Commands dispatched to aircraft (mission_start: swarm area missions only, from M2b).
FLIGHT_COMMANDS = frozenset(
    {
        CommandKind.ARM,
        CommandKind.DISARM,
        CommandKind.TAKEOFF,
        CommandKind.HOLD,
        CommandKind.RESUME,
        CommandKind.RETURN_TO_LAUNCH,
        CommandKind.LAND,
        CommandKind.GOTO,
        CommandKind.MISSION_START,
    }
)
# What each kind of link can carry: an autopilot over MAVLink (and the simulator), and a
# swarm companion over the bridge (ADR 0003: only the operator commands and area missions).
AUTOPILOT_COMMANDS = FLIGHT_COMMANDS - {CommandKind.MISSION_START}
SWARM_COMMANDS = frozenset(
    {
        CommandKind.HOLD,
        CommandKind.RESUME,
        CommandKind.RETURN_TO_LAUNCH,
        CommandKind.LAND,
        CommandKind.MISSION_START,
    }
)
# May be attempted on a stale or lost link: they only make the situation safer.
SAFE_ON_DEGRADED_LINK = frozenset(
    {CommandKind.HOLD, CommandKind.RETURN_TO_LAUNCH, CommandKind.LAND}
)
ALWAYS_CONFIRM = frozenset({CommandKind.ARM, CommandKind.TAKEOFF, CommandKind.MISSION_START})

# Which link carries a command for an aircraft with both (ADR 0025). The safer commands go
# to the companion while it is heard (it keeps the swarm consistent), else to the autopilot.
_MAVLINK_ONLY = frozenset(
    {CommandKind.ARM, CommandKind.DISARM, CommandKind.TAKEOFF, CommandKind.GOTO}
)
_SWARM_ONLY = frozenset({CommandKind.RESUME, CommandKind.MISSION_START})


def route_command(kind: CommandKind, *, swarm_live: bool) -> LinkSource | None:
    """The link that carries ``kind`` for an aircraft with a MAVLink and a swarm link.

    None: the command cannot be sent now (it needs the swarm link, which is not live).
    """
    if kind in _MAVLINK_ONLY:
        return LinkSource.MAVLINK
    if kind in _SWARM_ONLY:
        return LinkSource.SWARM if swarm_live else None
    if kind in SAFE_ON_DEGRADED_LINK:
        return LinkSource.SWARM if swarm_live else LinkSource.MAVLINK
    return None


@dataclass(frozen=True)
class Rejection:
    """Why a command is not sent to one aircraft: a stable code and a sentence."""

    code: str
    message: str


@dataclass(frozen=True)
class Limits:
    """Configured limits (settings)."""

    min_takeoff_battery_pct: float
    max_altitude_relative_m: float
    goto_max_distance_m: float
    goto_confirm_distance_m: float


@dataclass(frozen=True)
class VehicleView:
    """What the rules know about one aircraft."""

    callsign: str
    link: LinkState
    capabilities: frozenset[CommandKind]
    sample: TelemetrySample | None


@dataclass(frozen=True)
class GotoTarget:
    """Where a goto sends an aircraft."""

    latitude: float
    longitude: float
    altitude_relative_m: float | None


def authority(
    kind: CommandKind,
    *,
    principal_id: str,
    holder_id: str | None,
    can_hold: bool,
    can_command: bool,
    can_override: bool,
) -> tuple[Rejection | None, bool]:
    """
    Decide whether the principal may send ``kind`` to an aircraft whose lease is held by
    ``holder_id``. Returns (rejection, is_override).

    HOLD is open to every operator on every aircraft. Everything else needs the lease,
    or the supervisors' override, which always requires confirmation and is audited.
    """
    if kind is CommandKind.HOLD:
        if can_hold:
            return None, False
        return Rejection("forbidden", "Your role cannot command aircraft."), False
    if can_command and holder_id == principal_id:
        return None, False
    if can_override:
        return None, True
    if not can_command:
        return Rejection("forbidden", "Your role cannot command aircraft."), False
    if holder_id is None:
        return Rejection("no-control", "Take control of the aircraft first."), False
    return Rejection("no-control", "Another operator controls this aircraft."), False


def precondition(
    kind: CommandKind,
    vehicle: VehicleView,
    limits: Limits,
    *,
    takeoff_altitude_m: float | None = None,
    goto: GotoTarget | None = None,
    geofences: GeofenceSet | None = None,
) -> Rejection | None:
    """Return why ``kind`` must not be sent to ``vehicle`` now, or None."""
    if kind not in FLIGHT_COMMANDS:
        return Rejection("unsupported", f"{kind.value} is not available yet.")
    if kind not in vehicle.capabilities:
        return Rejection("unsupported", f"{vehicle.callsign} does not support {kind.value}.")
    if vehicle.link is LinkState.OFFLINE or vehicle.sample is None:
        return Rejection("no-link", f"{vehicle.callsign} has no telemetry link.")
    if vehicle.link is not LinkState.LIVE and kind not in SAFE_ON_DEGRADED_LINK:
        return Rejection(
            "link-degraded",
            f"{vehicle.callsign}'s link is {vehicle.link.value}; only hold, return and land "
            "can be attempted.",
        )
    s = vehicle.sample
    rule = _RULES[kind]
    return rule(vehicle.callsign, s, limits, takeoff_altitude_m, goto, geofences)


def _in_air_or_unknown(callsign: str, s: TelemetrySample) -> Rejection | None:
    if s.in_air is False:
        return Rejection("not-in-air", f"{callsign} is on the ground.")
    return None


def _ready_for_flight(callsign: str, s: TelemetrySample, limits: Limits) -> Rejection | None:
    if s.in_air is not False:
        return Rejection("in-air", f"{callsign} is not known to be on the ground.")
    if s.gps_fix is None or not s.gps_fix.has_3d:
        return Rejection("no-gps-fix", f"{callsign} has no known 3D GNSS fix.")
    if s.battery_pct is None:
        return Rejection("battery-unknown", f"{callsign}'s battery level is unknown.")
    if s.battery_pct < limits.min_takeoff_battery_pct:
        return Rejection(
            "battery-low",
            f"{callsign}'s battery is {s.battery_pct:.0f} %, below the "
            f"{limits.min_takeoff_battery_pct:.0f} % needed to fly.",
        )
    return None


_Rule = Callable[
    [str, TelemetrySample, Limits, float | None, GotoTarget | None, GeofenceSet | None],
    Rejection | None,
]


def _arm(callsign: str, s: TelemetrySample, limits: Limits, *_: object) -> Rejection | None:
    if s.armed is not False:
        return Rejection("already-armed", f"{callsign} is not known to be disarmed.")
    return _ready_for_flight(callsign, s, limits)


def _disarm(callsign: str, s: TelemetrySample, *_: object) -> Rejection | None:
    if s.armed is not True:
        return Rejection("not-armed", f"{callsign} is not armed.")
    if s.in_air is not False:
        return Rejection("in-air", f"{callsign} must be on the ground to disarm.")
    return None


def _takeoff(
    callsign: str, s: TelemetrySample, limits: Limits, altitude: float | None, *_: object
) -> Rejection | None:
    if s.armed is not True:
        return Rejection("not-armed", f"{callsign} must be armed first.")
    if altitude is not None and altitude > limits.max_altitude_relative_m:
        return Rejection(
            "altitude-limit",
            f"{altitude:.0f} m exceeds the {limits.max_altitude_relative_m:.0f} m limit.",
        )
    return _ready_for_flight(callsign, s, limits)


def _airborne(callsign: str, s: TelemetrySample, *_: object) -> Rejection | None:
    return _in_air_or_unknown(callsign, s)


def _resume(callsign: str, s: TelemetrySample, *_: object) -> Rejection | None:
    if s.swarm is not None and s.flight_mode in {FlightMode.OFFBOARD, FlightMode.UNKNOWN}:
        # The companion flies it: resume means the swarm mission it holds.
        if s.swarm.phase is not SwarmPhase.HOLD:
            return Rejection("not-holding", f"{callsign} is not holding; nothing to resume.")
        return None
    if s.in_air is not True:
        return Rejection("not-in-air", f"{callsign} is not in the air.")
    if s.flight_mode is not FlightMode.HOLD:
        return Rejection("not-holding", f"{callsign} is not holding; nothing to resume.")
    return None


def _goto(
    callsign: str,
    s: TelemetrySample,
    limits: Limits,
    _altitude: float | None,
    goto: GotoTarget | None,
    geofences: GeofenceSet | None,
) -> Rejection | None:
    if goto is None:  # pragma: no cover - the API always supplies a target
        return Rejection("invalid", "A goto needs a target position.")
    if s.flight_mode is FlightMode.OFFBOARD:
        return Rejection(
            "companion-in-control",
            f"{callsign}'s onboard computer is in control; hold it first (ADR 0003).",
        )
    if s.in_air is not True:
        return Rejection("not-in-air", f"{callsign} is not in the air.")
    if s.gps_fix is None or not s.gps_fix.has_3d or s.latitude is None or s.longitude is None:
        return Rejection("no-gps-fix", f"{callsign}'s position is unknown.")
    altitude = goto.altitude_relative_m
    if altitude is not None and altitude > limits.max_altitude_relative_m:
        return Rejection(
            "altitude-limit",
            f"{altitude:.0f} m exceeds the {limits.max_altitude_relative_m:.0f} m limit.",
        )
    distance = distance_m(
        GeoPoint(latitude=s.latitude, longitude=s.longitude),
        GeoPoint(latitude=goto.latitude, longitude=goto.longitude),
    )
    if distance > limits.goto_max_distance_m:
        return Rejection(
            "distance-limit",
            f"The target is {distance:.0f} m away; the limit is "
            f"{limits.goto_max_distance_m:.0f} m.",
        )
    if geofences is not None:
        reason = geofences.violation(
            goto.latitude, goto.longitude, altitude or s.altitude_relative_m
        )
        if reason is not None:
            return Rejection("geofence", f"The target is {reason}.")
    return None


def _mission_start(callsign: str, s: TelemetrySample, *_: object) -> Rejection | None:
    if s.swarm is None:
        return Rejection("swarm-unknown", f"{callsign}'s swarm companion has not been heard.")
    return None


_RULES: dict[CommandKind, _Rule] = {
    CommandKind.ARM: _arm,
    CommandKind.DISARM: _disarm,
    CommandKind.TAKEOFF: _takeoff,
    CommandKind.HOLD: _airborne,
    CommandKind.RESUME: _resume,
    CommandKind.RETURN_TO_LAUNCH: _airborne,
    CommandKind.LAND: _airborne,
    CommandKind.GOTO: _goto,
    CommandKind.MISSION_START: _mission_start,
}


def swarm_mission_problem(
    kind: MissionKind,
    status: MissionStatus,
    *,
    incident_active: bool,
    targets: Collection[str],
    tasked: Collection[str],
    swarm_aircraft: Collection[str],
) -> Rejection | None:
    """Why a mission cannot be started for ``targets`` now (ADR 0024), or None.

    Only swarm area missions are started from M2b; GCS-planned missions follow in M4. The
    onboard protocol cannot address a mission: every drone on the swarm link adopts it, so
    the command must name every swarm aircraft, and those must be the mission's tasks.
    """
    if kind is not MissionKind.SWARM_AREA:
        return Rejection("unsupported", f"Starting a {kind.value} mission is not available yet.")
    if not incident_active:
        return Rejection("incident-not-active", "The mission's incident is not active.")
    if status is not MissionStatus.PLANNED:
        return Rejection("mission-not-planned", f"The mission is {status.value}, not planned.")
    if set(targets) != set(swarm_aircraft):
        return Rejection(
            "swarm-mission-partial",
            "Every drone on the swarm link adopts a swarm mission: send it to all "
            f"{len(swarm_aircraft)} swarm aircraft.",
        )
    if set(targets) != set(tasked):
        return Rejection(
            "swarm-mission-tasks",
            "Assign every swarm aircraft to the mission, and only them, before starting it.",
        )
    return None


def confirmation_reasons(
    kind: CommandKind,
    *,
    target_count: int,
    any_override: bool,
    goto_distance_m: float | None,
    limits: Limits,
) -> list[str]:
    """Why this command needs an explicit confirmation (empty: it doesn't)."""
    reasons = []
    if kind in ALWAYS_CONFIRM:
        reasons.append(f"{kind.value} always needs confirmation")
    if kind is CommandKind.MISSION_START:
        reasons.append("every drone on the swarm link adopts the mission")
    if target_count > 1:
        reasons.append(f"sent to {target_count} aircraft")
    if any_override:
        reasons.append("overrides another operator's control")
    if goto_distance_m is not None and goto_distance_m > limits.goto_confirm_distance_m:
        reasons.append(f"goto of {goto_distance_m:.0f} m")
    return reasons


def warnings(vehicle: VehicleView, battery_low_pct: float) -> list[str]:
    """Conditions an operator should see before confirming."""
    found = []
    s = vehicle.sample
    if vehicle.link is not LinkState.LIVE:
        found.append(f"link {vehicle.link.value}")
    if s is not None and s.battery_pct is not None and s.battery_pct < battery_low_pct:
        found.append(f"battery {s.battery_pct:.0f} %")
    if s is not None:
        if s.gps_fix is None:
            found.append("GNSS quality unknown")
        elif not s.gps_fix.has_3d:
            found.append("no 3D GNSS fix")
    return found


def expected_effect(kind: CommandKind) -> Callable[[TelemetrySample], bool] | None:
    """How telemetry shows that an acked command took effect (None: nothing to verify)."""
    effects: dict[CommandKind, Callable[[TelemetrySample], bool]] = {
        CommandKind.ARM: lambda s: s.armed is True,
        CommandKind.DISARM: lambda s: s.armed is False,
        CommandKind.TAKEOFF: lambda s: s.in_air is True,
        CommandKind.HOLD: lambda s: (
            s.flight_mode is FlightMode.HOLD
            or (s.swarm is not None and s.swarm.phase is SwarmPhase.HOLD)
        ),
        CommandKind.RESUME: lambda s: (
            s.flight_mode in {FlightMode.GOTO, FlightMode.MISSION}
            or (s.swarm is not None and s.swarm.phase in SWARM_WORKING)
        ),
        CommandKind.MISSION_START: lambda s: s.swarm is not None and s.swarm.phase in SWARM_WORKING,
        CommandKind.RETURN_TO_LAUNCH: lambda s: s.flight_mode is FlightMode.RETURN,
        CommandKind.LAND: lambda s: s.flight_mode is FlightMode.LAND or s.in_air is False,
        CommandKind.GOTO: lambda s: s.flight_mode in {FlightMode.GOTO, FlightMode.HOLD},
    }
    return effects.get(kind)
