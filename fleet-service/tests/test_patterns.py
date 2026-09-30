"""
Search patterns (ADR 0028): properties over generated areas, and pinned examples.

- lane patterns cover the whole area and keep every waypoint within half a spacing (plus
  the airplane's run-in) of it; lanes are whole spacings apart;
- airplanes never get a U-turn tighter than their turn diameter when there are lanes enough;
- the contour search falls back to perimeter rings exactly when terrain is missing.
"""

import itertools
import math

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from shapely import LineString, Point, Polygon

from fleet_service.domain.patterns import (
    LocalFrame,
    PatternError,
    PatternKind,
    PatternParams,
    Route,
    build_pattern,
)
from fleet_service.domain.patterns.frame import bearing_vector
from fleet_service.domain.patterns.spacing import footprint_width_m, lane_spacing_m
from fleet_service.domain.patterns.turns import (
    infeasible_turns,
    lane_order,
    min_lane_gap,
    turn_radius_m,
)
from fleet_service.domain.terrain import TerrainGrid, TerrainSet

ORIGIN = (47.3977, 8.5456)  # the simulator's site
FRAME = LocalFrame(*ORIGIN)
X0, Y0 = FRAME.xy(ORIGIN[1], ORIGIN[0])
PROPERTY = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def areas(draw: st.DrawFn) -> Polygon:
    """Star-shaped polygons (simple by construction), 3-12 vertices, 200 m-2 km across."""
    n = draw(st.integers(3, 12))
    angles = sorted(draw(st.lists(st.floats(0, 2 * math.pi), min_size=n, max_size=n, unique=True)))
    assume(all(b - a > 0.05 for a, b in itertools.pairwise(angles)))
    assume(angles[0] + 2 * math.pi - angles[-1] > 0.05)
    radii = draw(st.lists(st.floats(200, 2000), min_size=n, max_size=n))
    polygon = Polygon(
        [(X0 + r * math.cos(a), Y0 + r * math.sin(a)) for a, r in zip(angles, radii, strict=True)]
    )
    assume(polygon.is_valid and polygon.area > 50_000)
    return polygon


def metric(route: Route) -> list[tuple[float, float]]:
    return [FRAME.xy(p.longitude, p.latitude) for p in route.points]


def coverage(route: Route, area: Polygon) -> float:
    points = metric(route)
    swept = LineString(points).buffer(route.sweep_width_m / 2.0) if len(points) > 1 else Polygon()
    return swept.intersection(area).area / area.area


def build(params: PatternParams, area: Polygon | None = None, **kwargs: object) -> Route:
    try:
        return build_pattern(params, FRAME, area, **kwargs)  # type: ignore[arg-type]
    except PatternError as exc:
        assume(exc.code != "too-many-waypoints")
        raise


# --- lane patterns ------------------------------------------------------------------------------


@PROPERTY
@given(
    area=areas(),
    spacing=st.floats(20, 200),
    kind=st.sampled_from([PatternKind.PARALLEL_TRACK, PatternKind.CREEPING_LINE]),
    bearing=st.one_of(st.none(), st.floats(0, 359)),
    turn=st.sampled_from([0.0, 40.0, 90.0]),
)
def test_lane_patterns_cover_the_area_and_stay_near_it(
    area: Polygon, spacing: float, kind: PatternKind, bearing: float | None, turn: float
) -> None:
    route = build(
        PatternParams(kind, spacing, 60.0, 12.0, bearing_deg=bearing, turn_radius_m=turn), area
    )

    assert coverage(route, area) >= 0.995
    margin = area.buffer(spacing / 2.0 + turn + 1.0)
    assert all(margin.contains(Point(p)) for p in metric(route))


@PROPERTY
@given(area=areas(), spacing=st.floats(20, 200), bearing=st.floats(0, 179))
def test_lanes_are_whole_spacings_apart(area: Polygon, spacing: float, bearing: float) -> None:
    route = build(
        PatternParams(PatternKind.PARALLEL_TRACK, spacing, 60.0, bearing_deg=bearing), area
    )

    ex, ey = bearing_vector(bearing + 90.0)  # across the lanes
    offsets = sorted({round(x * ex + y * ey, 3) for x, y in metric(route)})
    for a, b in itertools.pairwise(offsets):
        steps = (b - a) / spacing
        assert abs(steps - round(steps)) < 0.01  # 1 % of a spacing (projection rounding)


@PROPERTY
@given(count=st.integers(1, 200), gap=st.integers(1, 8))
def test_lane_order_visits_every_lane_once_and_keeps_its_gap_when_it_can(
    count: int, gap: int
) -> None:
    order = lane_order(count, gap)

    assert sorted(order) == list(range(count))
    if count >= 2 * gap + 1:
        assert infeasible_turns(order, gap) == 0


def test_an_airplane_is_never_asked_for_a_turn_tighter_than_its_diameter() -> None:
    area = Polygon([(X0, Y0), (X0 + 3000, Y0), (X0 + 3000, Y0 + 1500), (X0, Y0 + 1500), (X0, Y0)])
    radius = turn_radius_m(18.0, 30.0)  # 57 m at 18 m/s and 30° of bank
    route = build(
        PatternParams(PatternKind.PARALLEL_TRACK, 40.0, 80.0, 18.0, turn_radius_m=radius), area
    )

    assert route.infeasible_turns == 0
    points = metric(route)
    # Consecutive lanes (a lane is two points): their distance across is ≥ the turn diameter.
    lanes_y = [points[i][1] for i in range(0, len(points), 2)]
    assert min(abs(a - b) for a, b in itertools.pairwise(lanes_y)) >= 2 * radius - 1e-6
    assert min_lane_gap(40.0, radius) == 3


# --- datum patterns ------------------------------------------------------------------------------


@PROPERTY
@given(spacing=st.floats(20, 200), extent=st.floats(100, 3000), bearing=st.floats(0, 359))
def test_expanding_square_reaches_its_extent_and_no_further_than_a_spacing(
    spacing: float, extent: float, bearing: float
) -> None:
    assume(extent >= 10 * spacing)  # the IAMSAR corner pockets stay under 1 % (datum.py)
    route = build(
        PatternParams(
            PatternKind.EXPANDING_SQUARE,
            spacing,
            60.0,
            datum=ORIGIN,
            radius_m=extent,
            bearing_deg=bearing,
        )
    )

    # Tracks exactly one spacing apart: their half-spacing buffers touch, leaving hairline
    # slivers in floating point, so coverage is a ratio (as for the lane patterns).
    swept = LineString(metric(route)).buffer(spacing / 2.0)
    circle = Point(X0, Y0).buffer(extent)
    assert swept.intersection(circle).area / circle.area >= 0.99
    reach = max(math.dist((X0, Y0), p) for p in metric(route))
    assert reach <= math.sqrt(2) * (extent + 2.5 * spacing) + 1.0


@PROPERTY
@given(radius=st.floats(100, 3000), bearing=st.floats(0, 359), second=st.booleans())
def test_sector_search_legs_are_one_radius_long(
    radius: float, bearing: float, second: bool
) -> None:
    route = build(
        PatternParams(
            PatternKind.SECTOR,
            50.0,
            60.0,
            datum=ORIGIN,
            radius_m=radius,
            bearing_deg=bearing,
            second_pass=second,
        )
    )

    points = metric(route)
    assert len(points) == (19 if second else 10)
    for a, b in itertools.pairwise(points):
        assert math.dist(a, b) == pytest.approx(radius, rel=1e-3)
    assert points[0] == pytest.approx(points[-1], abs=1e-3)


# --- contour -------------------------------------------------------------------------------------


def slope_terrain(covering: bool) -> TerrainSet:
    """A plane rising 10 m per 100 m eastwards, over (or beside) the simulator's site."""
    rows, cols, step = 200, 300, 0.0003
    lon0 = ORIGIN[1] - cols * step / 2 if covering else ORIGIN[1] + 1.0
    lat0 = ORIGIN[0] + rows * step / 2
    lon_m = 111_320 * math.cos(math.radians(ORIGIN[0])) * step
    heights = np.tile(np.arange(cols, dtype=np.float32) * lon_m * 0.1 + 400.0, (rows, 1))
    return TerrainSet([TerrainGrid("test", heights, lat0, lon0, step, step)])


@pytest.mark.parametrize("covering", [True, False])
def test_contour_falls_back_to_perimeter_rings_exactly_when_terrain_is_missing(
    covering: bool,
) -> None:
    area = Polygon(
        [(X0 - 800, Y0 - 600), (X0 + 800, Y0 - 600), (X0 + 800, Y0 + 600), (X0 - 800, Y0 + 600)]
    )
    route = build_pattern(
        PatternParams(PatternKind.CONTOUR, 50.0, 60.0, height_agl_m=40.0),
        FRAME,
        area,
        terrain=slope_terrain(covering),
        home_amsl_m=450.0,
    )

    assert route.fallback is not covering
    if covering:
        # On a plane rising eastwards the contours run north-south, 50 m apart: one per lane.
        xs = sorted({round(x) for x, _ in metric(route)})
        assert len(xs) >= 25
        heights = {p.altitude_relative_m for p in route.points}
        assert len(heights) > 10  # the route follows the terrain's height
    else:
        assert "perimeter rings" in route.notes[0]
        assert coverage(route, area) >= 0.95


def test_contour_without_the_home_altitude_keeps_one_altitude_and_says_so() -> None:
    area = Polygon(
        [(X0 - 500, Y0 - 500), (X0 + 500, Y0 - 500), (X0 + 500, Y0 + 500), (X0 - 500, Y0 + 500)]
    )
    route = build_pattern(
        PatternParams(PatternKind.CONTOUR, 50.0, 60.0, height_agl_m=40.0),
        FRAME,
        area,
        terrain=slope_terrain(True),
    )

    assert {p.altitude_relative_m for p in route.points} == {60.0}
    assert "altitude above home" in route.notes[0]


# --- spacing and errors --------------------------------------------------------------------------


def test_lane_spacing_from_the_camera_footprint() -> None:
    # 60 m above ground with an 80° lens sees 100.7 m; 20 % overlap -> 80.5 m lanes.
    assert footprint_width_m(60.0, 80.0) == pytest.approx(100.69, abs=0.01)
    assert lane_spacing_m(60.0, 80.0, 0.2) == pytest.approx(80.55, abs=0.01)


@pytest.mark.parametrize(
    ("params", "code"),
    [
        (PatternParams(PatternKind.PARALLEL_TRACK, 1.0, 60.0), "invalid-spacing"),
        (PatternParams(PatternKind.PARALLEL_TRACK, 50.0, 60.0), "area-required"),
        (PatternParams(PatternKind.SECTOR, 50.0, 60.0, datum=ORIGIN), "radius-required"),
        (PatternParams(PatternKind.SECTOR, 50.0, 60.0, radius_m=500.0), "datum-required"),
    ],
)
def test_impossible_parameters_are_refused_with_a_code(params: PatternParams, code: str) -> None:
    with pytest.raises(PatternError) as refused:
        build_pattern(params, FRAME)
    assert refused.value.code == code
