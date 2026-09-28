"""The pure command rules (domain/commands.py), row by row, and geofence containment."""

from dataclasses import replace
from typing import Any

import pytest
from shapely import Polygon

from fleet_service.domain.commands import (
    FLIGHT_COMMANDS,
    GotoTarget,
    Limits,
    VehicleView,
    authority,
    confirmation_reasons,
    expected_effect,
    precondition,
    warnings,
)
from fleet_service.domain.enums import CommandKind, FlightMode, GeofenceKind, GpsFix, LinkState
from fleet_service.domain.geofence import Fence, GeofenceSet
from fleet_service.domain.telemetry import TelemetrySample

from support import START

LIMITS = Limits(
    min_takeoff_battery_pct=40.0,
    max_altitude_relative_m=120.0,
    goto_max_distance_m=10_000.0,
    goto_confirm_distance_m=1_000.0,
)
LAT, LON = 47.3977, 8.5456

GROUND = TelemetrySample(
    aircraft_id="a1",
    ts=START,
    source="mock",
    latitude=LAT,
    longitude=LON,
    altitude_amsl_m=500.0,
    altitude_relative_m=0.0,
    heading_deg=0.0,
    groundspeed_mps=0.0,
    climb_rate_mps=0.0,
    battery_pct=95.0,
    battery_v=25.0,
    gps_fix=GpsFix.FIX_3D,
    satellites=14,
    flight_mode=FlightMode.HOLD,
    armed=False,
    in_air=False,
    home_latitude=LAT,
    home_longitude=LON,
)
ARMED = replace(GROUND, armed=True)
FLYING = replace(GROUND, armed=True, in_air=True, altitude_relative_m=40.0)


def view(sample: TelemetrySample | None, link: LinkState = LinkState.LIVE) -> VehicleView:
    return VehicleView("HX-1", link, FLIGHT_COMMANDS, sample)


def code(kind: CommandKind, sample: TelemetrySample | None, **kw: Any) -> str | None:
    link = kw.pop("link", LinkState.LIVE)
    rejection = precondition(kind, view(sample, link), LIMITS, **kw)
    return rejection.code if rejection else None


# --- preconditions -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "sample", "expected"),
    [
        (CommandKind.ARM, GROUND, None),
        (CommandKind.ARM, ARMED, "already-armed"),
        (
            CommandKind.ARM,
            replace(GROUND, armed=None),
            "already-armed",
        ),  # unknown is not "disarmed"
        (CommandKind.ARM, replace(GROUND, gps_fix=GpsFix.FIX_2D), "no-gps-fix"),
        (CommandKind.ARM, replace(GROUND, battery_pct=None), "battery-unknown"),
        (CommandKind.ARM, replace(GROUND, battery_pct=39.0), "battery-low"),
        (CommandKind.ARM, replace(GROUND, in_air=None), "in-air"),  # unknown is not "on ground"
        (CommandKind.DISARM, ARMED, None),
        (CommandKind.DISARM, GROUND, "not-armed"),
        (CommandKind.DISARM, FLYING, "in-air"),
        (CommandKind.TAKEOFF, ARMED, None),
        (CommandKind.TAKEOFF, GROUND, "not-armed"),
        (CommandKind.TAKEOFF, FLYING, "in-air"),
        (CommandKind.HOLD, FLYING, None),
        (CommandKind.HOLD, replace(FLYING, in_air=None), None),  # safe command, unknown allowed
        (CommandKind.HOLD, GROUND, "not-in-air"),
        (CommandKind.RETURN_TO_LAUNCH, FLYING, None),
        (CommandKind.LAND, FLYING, None),
        (CommandKind.LAND, GROUND, "not-in-air"),
        (CommandKind.RESUME, FLYING, None),
        (CommandKind.RESUME, replace(FLYING, flight_mode=FlightMode.GOTO), "not-holding"),
        (CommandKind.MISSION_START, FLYING, "unsupported"),
    ],
)
def test_preconditions(kind: CommandKind, sample: TelemetrySample, expected: str | None) -> None:
    assert code(kind, sample, takeoff_altitude_m=40.0) == expected


def test_takeoff_altitude_is_capped() -> None:
    assert code(CommandKind.TAKEOFF, ARMED, takeoff_altitude_m=121.0) == "altitude-limit"


@pytest.mark.parametrize(
    ("kind", "link", "expected"),
    [
        (CommandKind.HOLD, LinkState.LOST, None),
        (CommandKind.RETURN_TO_LAUNCH, LinkState.STALE, None),
        (CommandKind.LAND, LinkState.LOST, None),
        (CommandKind.GOTO, LinkState.STALE, "link-degraded"),
        (CommandKind.RESUME, LinkState.LOST, "link-degraded"),
        (CommandKind.HOLD, LinkState.OFFLINE, "no-link"),
    ],
)
def test_only_safe_commands_on_a_degraded_link(
    kind: CommandKind, link: LinkState, expected: str | None
) -> None:
    target = GotoTarget(LAT + 0.001, LON, None)
    assert code(kind, FLYING, link=link, goto=target) == expected


def test_no_telemetry_means_no_link() -> None:
    assert code(CommandKind.HOLD, None) == "no-link"


def test_a_driver_without_the_capability_refuses() -> None:
    limited = VehicleView("HX-1", LinkState.LIVE, frozenset({CommandKind.HOLD}), FLYING)

    rejection = precondition(CommandKind.LAND, limited, LIMITS)

    assert rejection is not None
    assert rejection.code == "unsupported"


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (GotoTarget(LAT + 0.01, LON, 60.0), None),
        (GotoTarget(LAT + 0.01, LON, 130.0), "altitude-limit"),
        (GotoTarget(LAT + 0.2, LON, None), "distance-limit"),  # 22 km
    ],
)
def test_goto_limits(target: GotoTarget, expected: str | None) -> None:
    assert code(CommandKind.GOTO, FLYING, goto=target) == expected


def test_goto_needs_a_known_position() -> None:
    lost = replace(FLYING, gps_fix=GpsFix.NONE, latitude=None, longitude=None)

    assert code(CommandKind.GOTO, lost, goto=GotoTarget(LAT, LON, None)) == "no-gps-fix"


# --- geofences ------------------------------------------------------------------------------------


def square(lat: float, lon: float, half: float) -> Polygon:
    return Polygon(
        [
            (lon - half, lat - half),
            (lon + half, lat - half),
            (lon + half, lat + half),
            (lon - half, lat + half),
        ]
    )


FENCES = GeofenceSet.of(
    [
        Fence("operating box", GeofenceKind.INCLUSION, square(LAT, LON, 0.05), 100.0),
        Fence("helipad", GeofenceKind.EXCLUSION, square(LAT + 0.01, LON, 0.002), None),
    ]
)


@pytest.mark.parametrize(
    ("lat", "lon", "alt", "expected"),
    [
        (LAT + 0.02, LON, 50.0, None),
        (LAT + 0.01, LON, 50.0, "inside exclusion geofence 'helipad'"),
        (LAT + 0.2, LON, 50.0, "outside every inclusion geofence"),
        (LAT + 0.02, LON, 110.0, "above the geofence ceiling of 100 m"),
    ],
)
def test_geofence_violations(lat: float, lon: float, alt: float, expected: str | None) -> None:
    assert FENCES.violation(lat, lon, alt) == expected


def test_goto_respects_geofences() -> None:
    target = GotoTarget(LAT + 0.01, LON, 50.0)

    assert code(CommandKind.GOTO, FLYING, goto=target, geofences=FENCES) == "geofence"


def test_no_geofences_allow_everything() -> None:
    assert GeofenceSet().violation(0.0, 0.0, 1000.0) is None


# --- authority, confirmation, warnings, effects ---------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "holder", "perms", "expected", "override"),
    [
        (CommandKind.HOLD, "someone-else", "operator", None, False),
        (CommandKind.HOLD, None, "observer", "forbidden", False),
        (CommandKind.LAND, "me", "operator", None, False),
        (CommandKind.LAND, "someone-else", "operator", "no-control", False),
        (CommandKind.LAND, None, "operator", "no-control", False),
        (CommandKind.LAND, "someone-else", "supervisor", None, True),
        (CommandKind.LAND, "me", "supervisor", None, False),
        (CommandKind.LAND, None, "supervisor", None, True),
        (CommandKind.ARM, "me", "observer", "forbidden", False),
    ],
)
def test_authority(
    kind: CommandKind, holder: str | None, perms: str, expected: str | None, override: bool
) -> None:
    flags = {
        "observer": (False, False, False),
        "operator": (True, True, False),
        "supervisor": (True, True, True),
    }[perms]

    rejection, is_override = authority(
        kind,
        principal_id="me",
        holder_id=holder,
        can_hold=flags[0],
        can_command=flags[1],
        can_override=flags[2],
    )

    assert (rejection.code if rejection else None) == expected
    assert is_override is override


@pytest.mark.parametrize(
    ("kind", "count", "override", "distance", "expected"),
    [
        (CommandKind.HOLD, 1, False, None, []),
        (CommandKind.ARM, 1, False, None, ["arm always needs confirmation"]),
        (CommandKind.HOLD, 3, False, None, ["sent to 3 aircraft"]),
        (CommandKind.LAND, 1, True, None, ["overrides another operator's control"]),
        (CommandKind.GOTO, 1, False, 999.0, []),
        (CommandKind.GOTO, 1, False, 1500.0, ["goto of 1500 m"]),
    ],
)
def test_confirmation_reasons(
    kind: CommandKind, count: int, override: bool, distance: float | None, expected: list[str]
) -> None:
    assert (
        confirmation_reasons(
            kind, target_count=count, any_override=override, goto_distance_m=distance, limits=LIMITS
        )
        == expected
    )


def test_warnings_name_what_the_operator_should_notice() -> None:
    weak = replace(FLYING, battery_pct=20.0, gps_fix=GpsFix.FIX_2D)

    assert warnings(view(weak, LinkState.STALE), battery_low_pct=30.0) == [
        "link stale",
        "battery 20 %",
        "no 3D GNSS fix",
    ]


@pytest.mark.parametrize(
    ("kind", "after", "verified"),
    [
        (CommandKind.ARM, ARMED, True),
        (CommandKind.ARM, GROUND, False),
        (CommandKind.TAKEOFF, FLYING, True),
        (CommandKind.RETURN_TO_LAUNCH, replace(FLYING, flight_mode=FlightMode.RETURN), True),
        (CommandKind.RETURN_TO_LAUNCH, FLYING, False),
        (CommandKind.LAND, GROUND, True),
    ],
)
def test_expected_effects(kind: CommandKind, after: TelemetrySample, verified: bool) -> None:
    effect = expected_effect(kind)

    assert effect is not None
    assert effect(after) is verified
