"""
Splitting an area and deconflicting the flights (ADR 0029): properties and examples.

The central invariant: when ``deconflict`` reports no conflict, an independent check at a
ten times finer time step, with the exact separation limits, finds none either.
"""

import itertools
import math
from dataclasses import replace

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from shapely import Polygon, unary_union

from fleet_service.domain.deconfliction import (
    Flight,
    Separation,
    deconflict,
    find_conflicts,
    layer_offsets,
)
from fleet_service.domain.patterns import (
    LocalFrame,
    PatternKind,
    PatternParams,
    RoutePoint,
    build_pattern,
)
from fleet_service.domain.split import Share, split_area
from fleet_service.domain.terrain import TerrainGrid, TerrainSet

ORIGIN = (47.3977, 8.5456)
FRAME = LocalFrame(*ORIGIN)
X0, Y0 = FRAME.xy(ORIGIN[1], ORIGIN[0])
SEP = Separation()
PROPERTY = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def areas(draw: st.DrawFn) -> Polygon:
    n = draw(st.integers(3, 10))
    angles = sorted(draw(st.lists(st.floats(0, 2 * math.pi), min_size=n, max_size=n, unique=True)))
    assume(all(b - a > 0.1 for a, b in itertools.pairwise(angles)))
    assume(angles[0] + 2 * math.pi - angles[-1] > 0.1)
    radii = draw(st.lists(st.floats(300, 1500), min_size=n, max_size=n))
    polygon = Polygon(
        [(X0 + r * math.cos(a), Y0 + r * math.sin(a)) for a, r in zip(angles, radii, strict=True)]
    )
    assume(polygon.is_valid and polygon.area > 200_000)
    return polygon


# --- split ---------------------------------------------------------------------------------------


@PROPERTY
@given(
    area=areas(),
    weights=st.lists(st.floats(0.5, 3.0), min_size=1, max_size=6),
    bearing=st.floats(0, 179),
)
def test_strips_tile_the_area_in_proportion_to_the_weights(
    area: Polygon, weights: list[float], bearing: float
) -> None:
    shares = [Share(f"a{i}", w) for i, w in enumerate(weights)]
    strips = split_area(area, bearing, shares)

    total = sum(weights)
    by_id = dict(strips)
    for share in shares:
        target = area.area * share.weight / total
        assert by_id[share.aircraft_id].area == pytest.approx(target, rel=0.02, abs=1.0)
    for i, (_, a) in enumerate(strips):
        for _, b in strips[i + 1 :]:
            assert a.intersection(b).area < 1e-6 * area.area
    union = unary_union([strip for _, strip in strips])
    assert union.symmetric_difference(area).area < 1e-4 * area.area


def test_strips_follow_the_aircraft_starting_positions() -> None:
    area = Polygon([(X0, Y0), (X0 + 2000, Y0), (X0 + 2000, Y0 + 900), (X0, Y0 + 900)])
    # Lanes run east (90°): strips are stacked north-south. "north" starts north.
    shares = [
        Share("north", 1.0, (X0 + 1000, Y0 + 2000)),
        Share("south", 1.0, (X0 + 1000, Y0 - 2000)),
        Share("unknown", 1.0),
    ]

    strips = split_area(area, 90.0, shares)

    assert [aircraft for aircraft, _ in strips] == ["south", "north", "unknown"]
    assert strips[0][1].centroid.y < strips[1][1].centroid.y < strips[2][1].centroid.y


# --- layers --------------------------------------------------------------------------------------


def flight(aircraft: str, fixed_wing: bool = False, **kwargs: object) -> Flight:
    return Flight(
        aircraft_id=aircraft,
        callsign=aircraft.upper(),
        fixed_wing=fixed_wing,
        route=(RoutePoint(*ORIGIN, 60.0),),
        speed_mps=18.0 if fixed_wing else 10.0,
        **kwargs,  # type: ignore[arg-type]
    )


def test_layers_round_robin_multirotors_and_put_airplanes_a_band_above() -> None:
    flights = [flight(f"r{i}") for i in range(5)] + [flight("p0", True), flight("p1", True)]

    offsets = layer_offsets(flights, SEP)

    assert [offsets[f"r{i}"] for i in range(5)] == [0.0, 15.0, 30.0, 0.0, 15.0]
    assert offsets["p0"] == 30.0 + SEP.airframe_band_m
    assert offsets["p1"] == offsets["p0"] + SEP.layer_spacing_m


def test_unknown_home_altitudes_are_reported_not_assumed() -> None:
    flights = [flight("a", home_amsl_m=400.0), flight("b")]

    _, report = deconflict(flights, FRAME, SEP)

    assert any("Home altitude unknown for B" in note for note in report.notes)


def test_homes_at_different_altitudes_fly_one_amsl_search_altitude() -> None:
    flights = [flight("low", home_amsl_m=400.0), flight("high", home_amsl_m=450.0)]

    adjusted, report = deconflict(flights, FRAME, replace(SEP, multirotor_layers=1))

    by_id = {f.aircraft_id: f for f in adjusted}
    amsl = {a: f.home_amsl_m + f.route[0].altitude_relative_m for a, f in by_id.items()}  # type: ignore[operator]
    assert amsl["low"] == amsl["high"] == 510.0
    assert report.layers_m == {"low": 50.0, "high": 0.0}


# --- 4D ------------------------------------------------------------------------------------------


def line(
    ax: float, ay: float, bx: float, by: float, altitude: float = 60.0
) -> tuple[RoutePoint, ...]:
    points = []
    for x, y in ((ax, ay), (bx, by)):
        lon, lat = FRAME.lonlat(X0 + x, Y0 + y)
        points.append(RoutePoint(lat, lon, altitude))
    return tuple(points)


def test_crossing_routes_on_one_layer_conflict_and_a_start_delay_resolves_it() -> None:
    a = Flight("a", "A", False, line(-1000, 0, 1000, 0), 10.0, returns_home=False)
    b = Flight("b", "B", False, line(0, -1000, 0, 1000), 10.0, returns_home=False)

    assert find_conflicts([a, b], FRAME, SEP)  # both reach the crossing at 100 s

    _adjusted, report = deconflict([a, b], FRAME, SEP, layered=False)

    assert report.conflicts == []
    assert report.start_delays_s["b"] > 0.0


def test_a_route_past_a_waiting_aircraft_is_resolved_by_letting_it_leave_first() -> None:
    # An airplane loiters at 30 m right on a multirotor's way to the area (the multirotor
    # flies at 40 m). Delaying the airplane only keeps it there longer; the multirotor
    # must wait until the airplane has left instead.
    rotor = Flight(
        "r",
        "R",
        False,
        line(0, 200, 0, 1000, 40.0),
        10.0,
        returns_home=False,
        start_altitude_relative_m=40.0,
    )
    plane = Flight(
        "p",
        "P",
        True,
        line(0, 300, 800, 300, 70.0),
        18.0,
        start=(FRAME.lonlat(X0, Y0 + 300)[1], FRAME.lonlat(X0, Y0 + 300)[0]),
        returns_home=False,
        start_altitude_relative_m=30.0,
    )
    assert find_conflicts(
        [rotor, replace(plane, start_delay_s=SEP.departure_interval_s)], FRAME, SEP
    )

    adjusted, report = deconflict([rotor, plane], FRAME, SEP, layered=False)

    assert report.conflicts == []
    assert fine_violations(adjusted, SEP) == []
    assert report.start_delays_s["r"] > report.start_delays_s["p"]


def test_the_same_crossing_on_different_layers_does_not_conflict() -> None:
    a = Flight("a", "A", False, line(-1000, 0, 1000, 0, 60.0), 10.0, returns_home=False)
    b = Flight("b", "B", False, line(0, -1000, 0, 1000, 75.0), 10.0, returns_home=False)

    assert find_conflicts([a, b], FRAME, SEP) == []


def fine_violations(flights: list[Flight], sep: Separation) -> list[tuple[str, str, float]]:
    """An independent check: 0.1 s steps, exact limits, the same flight model."""
    fine = replace(sep, sample_s=0.1, horizontal_m=sep.horizontal_m)
    found = []
    for c in find_conflicts(flights, FRAME, replace(fine, sample_s=0.1)):
        # find_conflicts widens by speed · sample (1-2 m at 0.1 s): re-check exact limits.
        if c.horizontal_m < sep.horizontal_m and c.vertical_m < sep.vertical_m:
            found.append((c.aircraft[0], c.aircraft[1], c.t_s))
    return found


@PROPERTY
@given(
    area=areas(),
    count=st.integers(2, 6),
    planes=st.integers(0, 2),
    spacing=st.floats(60, 150),
    bearing=st.floats(0, 179),
)
def test_a_plan_reported_clear_keeps_separation_everywhere(
    area: Polygon, count: int, planes: int, spacing: float, bearing: float
) -> None:
    ids = [f"a{i}" for i in range(count)]
    fixed = set(ids[: min(planes, count)])
    home = (ORIGIN[0] - 0.02, ORIGIN[1])  # a launch site 2 km south
    starts = {a: FRAME.xy(home[1] + 0.0005 * i, home[0]) for i, a in enumerate(ids)}
    strips = split_area(area, bearing, [Share(a, 1.0, starts[a]) for a in ids])
    flights = []
    for aircraft, strip in strips:
        fw = aircraft in fixed
        route = build_pattern(
            PatternParams(
                PatternKind.PARALLEL_TRACK,
                spacing,
                60.0,
                18.0 if fw else 10.0,
                bearing_deg=bearing,
                turn_radius_m=60.0 if fw else 0.0,
            ),
            FRAME,
            strip,
            start=starts[aircraft],
        )
        start_lon, start_lat = FRAME.lonlat(*starts[aircraft])
        flights.append(
            Flight(
                aircraft,
                aircraft.upper(),
                fw,
                route.points,
                18.0 if fw else 10.0,
                start=(start_lat, start_lon),
                home=(start_lat, start_lon),
                home_amsl_m=450.0,
                start_altitude_relative_m=20.0,
            )
        )

    adjusted, report = deconflict(flights, FRAME, SEP)

    if report.conflicts:  # reported, never hidden: nothing to verify beyond that
        return
    assert fine_violations(adjusted, SEP) == []
    offsets = report.layers_m
    rotors = [offsets[a] for a in ids if a not in fixed]
    for a in fixed:
        assert offsets[a] >= max(rotors, default=-SEP.airframe_band_m) + SEP.airframe_band_m


def test_six_aircraft_from_one_launch_site_get_a_clear_sequenced_plan() -> None:
    area = Polygon(
        [(X0 - 1000, Y0), (X0 + 1000, Y0), (X0 + 1000, Y0 + 1500), (X0 - 1000, Y0 + 1500)]
    )
    ids = [f"a{i}" for i in range(6)]
    # Hovering 40 m apart at 20 m, 2 km south of the area: already closer than 50 m.
    starts = {a: (X0 - 100 + 40 * i, Y0 - 2000) for i, a in enumerate(ids)}
    flights = []
    for aircraft, strip in split_area(area, 90.0, [Share(a, 1.0, starts[a]) for a in ids]):
        plane = aircraft == "a5"
        speed = 18.0 if plane else 10.0
        route = build_pattern(
            PatternParams(
                PatternKind.PARALLEL_TRACK,
                80.0,
                60.0,
                speed,
                bearing_deg=90.0,
                turn_radius_m=60.0 if plane else 0.0,
            ),
            FRAME,
            strip,
            start=starts[aircraft],
        )
        lon, lat = FRAME.lonlat(*starts[aircraft])
        flights.append(
            Flight(
                aircraft,
                aircraft.upper(),
                plane,
                route.points,
                speed,
                start=(lat, lon),
                home=(lat, lon),
                home_amsl_m=450.0,
                start_altitude_relative_m=20.0,
            )
        )

    adjusted, report = deconflict(flights, FRAME, SEP)

    assert report.conflicts == []
    assert fine_violations(adjusted, SEP) == []
    delays = sorted(report.start_delays_s.values())
    assert all(b - a >= SEP.departure_interval_s for a, b in itertools.pairwise(delays))


def test_already_close_aircraft_may_not_come_closer() -> None:
    # Two aircraft hover 30 m apart on one layer; B's route passes right over A.
    a = Flight(
        "a",
        "A",
        False,
        line(0, 0, 0, 1),
        10.0,
        returns_home=False,
        start_altitude_relative_m=60.0,
        start_delay_s=10_000.0,
    )
    b = Flight(
        "b",
        "B",
        False,
        line(30, 0, -500, 0),
        10.0,
        returns_home=False,
        start_altitude_relative_m=60.0,
    )

    conflicts = find_conflicts([a, b], FRAME, SEP)

    assert [c.callsigns for c in conflicts] == [("A", "B")]


# --- terrain -------------------------------------------------------------------------------------


def test_clearance_is_checked_against_terrain_and_unknown_terrain_is_reported() -> None:
    rows, cols, step = 50, 50, 0.001
    grid = TerrainGrid(
        "test",
        np.full((rows, cols), 500.0, dtype=np.float32),
        ORIGIN[0] + 0.02,
        ORIGIN[1] - 0.02,
        step,
        step,
    )
    terrain = TerrainSet([grid])
    far = (ORIGIN[0] + 1.0, ORIGIN[1])  # outside the grid
    route = (
        RoutePoint(*ORIGIN, 60.0),  # 460 + 60 - 500 = 20 m above ground: too low
        RoutePoint(*ORIGIN, 100.0),  # 60 m: fine
        RoutePoint(*ORIGIN, 200.0),  # 160 m: too high
        RoutePoint(*far, 60.0),  # unknown terrain
    )
    f = Flight("a", "A", False, route, 10.0, home_amsl_m=460.0, returns_home=False)

    _, report = deconflict([f], FRAME, SEP, terrain, layered=False)

    assert [(c.waypoint, c.kind) for c in report.clearance] == [(0, "too-low"), (2, "too-high")]
    assert report.unchecked_terrain == 1
    assert any("unknown terrain" in n for n in report.notes)
