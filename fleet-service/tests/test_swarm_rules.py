"""
The swarm and two-link rules (ADR 0024, ADR 0025), row by row: command routing, the
swarm-aware preconditions and effects, mission starts, telemetry merging, and building
what the swarm is sent. Pure functions; no network.
"""

from dataclasses import replace
from datetime import timedelta
from typing import Any, ClassVar

import pytest

from fleet_service.domain.commands import (
    FLIGHT_COMMANDS,
    GotoTarget,
    Limits,
    VehicleView,
    expected_effect,
    precondition,
    route_command,
    swarm_mission_problem,
    warnings,
)
from fleet_service.domain.enums import (
    CommandKind,
    FlightMode,
    GpsFix,
    LinkSource,
    LinkState,
    MissionKind,
    MissionStatus,
    SwarmHealth,
    SwarmPhase,
)
from fleet_service.domain.telemetry import SwarmState, TelemetrySample, merge
from fleet_service.drivers.swarm import sample_of
from fleet_service.drivers.swarm_wire import SwarmStatus
from fleet_service.services.commands import area_mission

from support import START

LIMITS = Limits(
    min_takeoff_battery_pct=40.0,
    max_altitude_relative_m=120.0,
    goto_max_distance_m=10_000.0,
    goto_confirm_distance_m=1_000.0,
)
FRESH = timedelta(seconds=3)

STATE = SwarmState(
    drone_id=3,
    phase=SwarmPhase.SEARCH,
    health=SwarmHealth.OK,
    faults=frozenset(),
    mission_sequence=10,
    command_sequence=0,
    nearest_obstacle_m=None,
    survivor_sighting=None,
)
SWARM_ONLY = TelemetrySample(
    aircraft_id="a1",
    ts=START,
    source="swarm",
    latitude=47.3977,
    longitude=8.5456,
    altitude_amsl_m=None,
    altitude_relative_m=None,
    heading_deg=90.0,
    groundspeed_mps=2.0,
    climb_rate_mps=None,
    battery_pct=None,
    battery_v=None,
    gps_fix=None,
    satellites=None,
    flight_mode=FlightMode.UNKNOWN,
    armed=None,
    in_air=None,
    home_latitude=None,
    home_longitude=None,
    swarm=STATE,
)
AUTOPILOT = replace(
    SWARM_ONLY,
    source="mavlink",
    latitude=47.3980,
    altitude_amsl_m=530.0,
    altitude_relative_m=30.0,
    battery_pct=80.0,
    gps_fix=GpsFix.FIX_3D,
    flight_mode=FlightMode.OFFBOARD,
    armed=True,
    in_air=True,
    swarm=None,
)


def holding(sample: TelemetrySample) -> TelemetrySample:
    assert sample.swarm is not None
    return replace(sample, swarm=replace(sample.swarm, phase=SwarmPhase.HOLD))


def code(kind: CommandKind, sample: TelemetrySample, **kw: Any) -> str | None:
    view = VehicleView("SW-3", LinkState.LIVE, FLIGHT_COMMANDS, sample)
    rejection = precondition(kind, view, LIMITS, **kw)
    return rejection.code if rejection else None


# --- routing (ADR 0025) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "swarm_live", "expected"),
    [
        (CommandKind.ARM, True, LinkSource.MAVLINK),
        (CommandKind.DISARM, True, LinkSource.MAVLINK),
        (CommandKind.TAKEOFF, True, LinkSource.MAVLINK),
        (CommandKind.GOTO, True, LinkSource.MAVLINK),
        (CommandKind.HOLD, True, LinkSource.SWARM),
        (CommandKind.HOLD, False, LinkSource.MAVLINK),  # the safer command still gets through
        (CommandKind.RETURN_TO_LAUNCH, True, LinkSource.SWARM),
        (CommandKind.RETURN_TO_LAUNCH, False, LinkSource.MAVLINK),
        (CommandKind.LAND, True, LinkSource.SWARM),
        (CommandKind.LAND, False, LinkSource.MAVLINK),
        (CommandKind.RESUME, True, LinkSource.SWARM),
        (CommandKind.RESUME, False, None),
        (CommandKind.MISSION_START, True, LinkSource.SWARM),
        (CommandKind.MISSION_START, False, None),
        (CommandKind.MISSION_UPLOAD, True, None),
    ],
)
def test_route_command(kind: CommandKind, swarm_live: bool, expected: LinkSource | None) -> None:
    assert route_command(kind, swarm_live=swarm_live) is expected


# --- preconditions and effects of swarm aircraft -----------------------------------------------


@pytest.mark.parametrize(
    ("kind", "sample", "expected"),
    [
        (CommandKind.HOLD, SWARM_ONLY, None),  # in the air or unknown: allowed
        (CommandKind.RESUME, holding(SWARM_ONLY), None),
        (CommandKind.RESUME, SWARM_ONLY, "not-holding"),  # searching: nothing to resume
        (CommandKind.MISSION_START, SWARM_ONLY, None),
        (CommandKind.MISSION_START, replace(SWARM_ONLY, swarm=None), "swarm-unknown"),
        (CommandKind.ARM, replace(SWARM_ONLY, armed=False, in_air=False), "no-gps-fix"),
        (CommandKind.GOTO, AUTOPILOT, "companion-in-control"),  # ADR 0003 rule 5
        (CommandKind.RESUME, replace(AUTOPILOT, swarm=STATE), "not-holding"),
        (CommandKind.RESUME, holding(replace(AUTOPILOT, swarm=STATE)), None),
    ],
)
def test_swarm_preconditions(
    kind: CommandKind, sample: TelemetrySample, expected: str | None
) -> None:
    goto = GotoTarget(47.3990, 8.5456, 30.0) if kind is CommandKind.GOTO else None
    assert code(kind, sample, goto=goto) == expected


def test_unknown_gnss_is_a_warning_not_a_fix_lost() -> None:
    view = VehicleView("SW-3", LinkState.LIVE, FLIGHT_COMMANDS, SWARM_ONLY)
    assert warnings(view, 30.0) == ["GNSS quality unknown"]


@pytest.mark.parametrize(
    ("kind", "sample", "expected"),
    [
        (CommandKind.HOLD, holding(SWARM_ONLY), True),
        (CommandKind.HOLD, SWARM_ONLY, False),
        (CommandKind.RESUME, SWARM_ONLY, True),
        (CommandKind.RESUME, holding(SWARM_ONLY), False),
        (CommandKind.MISSION_START, SWARM_ONLY, True),
        (
            CommandKind.MISSION_START,
            replace(SWARM_ONLY, swarm=replace(STATE, phase=SwarmPhase.STANDBY)),
            False,
        ),
        (CommandKind.MISSION_START, AUTOPILOT, False),  # no swarm state: not shown
    ],
)
def test_swarm_effects(kind: CommandKind, sample: TelemetrySample, expected: bool) -> None:
    effect = expected_effect(kind)
    assert effect is not None
    assert effect(sample) is expected


SWARM, PLANNED = MissionKind.SWARM_AREA, MissionStatus.PLANNED


# --- mission starts (ADR 0024) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "status", "active", "targets", "tasked", "swarm", "expected"),
    [
        (SWARM, PLANNED, True, "ab", "ab", "ab", None),
        (MissionKind.AREA_SEARCH, PLANNED, True, "ab", "ab", "ab", "unsupported"),
        (MissionKind.WAYPOINT, PLANNED, True, "ab", "ab", "ab", "unsupported"),
        (SWARM, PLANNED, False, "ab", "ab", "ab", "incident-not-active"),
        (SWARM, MissionStatus.DRAFT, True, "ab", "ab", "ab", "mission-not-planned"),
        (SWARM, MissionStatus.ACTIVE, True, "ab", "ab", "ab", "mission-not-planned"),
        (SWARM, PLANNED, True, "a", "a", "ab", "swarm-mission-partial"),
        (SWARM, PLANNED, True, "ab", "a", "ab", "swarm-mission-tasks"),
    ],
)
def test_swarm_mission_problem(
    kind: MissionKind,
    status: MissionStatus,
    active: bool,
    targets: str,
    tasked: str,
    swarm: str,
    expected: str | None,
) -> None:
    problem = swarm_mission_problem(
        kind,
        status,
        incident_active=active,
        targets=list(targets),
        tasked=list(tasked),
        swarm_aircraft=list(swarm),
    )
    assert (problem.code if problem else None) == expected


def test_a_swarm_mission_is_built_from_the_area_ring() -> None:
    class Plan:
        id = "m1"
        default_altitude_relative_m = 25.0
        waypoints: ClassVar = [type("W", (), {"latitude": 47.40, "longitude": 8.54})()]

    ring = [[8.0, 47.0], [8.2, 47.0], [8.2, 47.2], [8.0, 47.2], [8.0, 47.0]]  # lon, lat; closed
    built = area_mission(Plan(), {"type": "Polygon", "coordinates": [ring]}, 5.0)  # type: ignore[arg-type]

    assert built.area == ((47.0, 8.0), (47.0, 8.2), (47.2, 8.2), (47.2, 8.0))  # lat, lon; open
    assert built.origin == pytest.approx((47.1, 8.1))
    assert built.waypoints == ((47.40, 8.54),)
    assert built.altitude_relative_m == 25.0
    assert built.grid_resolution_m == 5.0


# --- telemetry (ADR 0025) ------------------------------------------------------------------------


def test_a_fresh_autopilot_sample_is_the_state_with_the_swarm_block_attached() -> None:
    merged = merge(AUTOPILOT, SWARM_ONLY, START + timedelta(seconds=1), FRESH)

    assert merged is not None
    assert merged.latitude == AUTOPILOT.latitude  # the autopilot's position wins
    assert merged.battery_pct == 80.0
    assert merged.swarm == STATE
    assert merged.source == "mavlink+swarm"


def test_without_a_fresh_autopilot_only_the_swarm_s_fields_are_known() -> None:
    stale_autopilot = replace(AUTOPILOT, ts=START - timedelta(seconds=10))

    merged = merge(stale_autopilot, SWARM_ONLY, START + timedelta(seconds=1), FRESH)

    assert merged == SWARM_ONLY
    assert merged is not None
    assert merged.battery_pct is None  # not the stale 80 %


def test_a_stale_swarm_block_is_not_attached() -> None:
    old_swarm = replace(SWARM_ONLY, ts=START - timedelta(seconds=10))

    assert merge(AUTOPILOT, old_swarm, START + timedelta(seconds=1), FRESH) == AUTOPILOT


def test_with_nothing_fresh_the_newest_sample_is_kept_for_the_link_to_age() -> None:
    later = START + timedelta(minutes=5)
    assert merge(AUTOPILOT, SWARM_ONLY, later, FRESH) == AUTOPILOT  # same ts: either is newest
    assert merge(None, None, later, FRESH) is None


def test_a_drone_state_maps_to_a_sample_with_unknowns() -> None:
    status = SwarmStatus(
        drone_id=3,
        stamp=1.0,
        received_at=1.0,
        phase=SwarmPhase.TRACK,
        health=SwarmHealth.DEGRADED,
        faults=["depth_stale"],
        mission_sequence=5,
        command_sequence=6,
        position=None,
        heading_deg=None,
        groundspeed_mps=0.0,
        velocity_north_mps=0.0,
        velocity_east_mps=0.0,
        nearest_obstacle_m=4.5,
        survivor_sighting=None,
    )

    sample = sample_of("a1", status, START)

    assert sample.latitude is None
    assert sample.longitude is None
    assert sample.gps_fix is None
    assert sample.flight_mode is FlightMode.UNKNOWN
    assert sample.swarm is not None
    assert sample.swarm.phase is SwarmPhase.TRACK
    assert sample.swarm.nearest_obstacle_m == 4.5
    assert sample.swarm.faults == frozenset({"depth_stale"})
