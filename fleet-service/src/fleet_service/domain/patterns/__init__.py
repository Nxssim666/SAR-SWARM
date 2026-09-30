"""
Search patterns (ADR 0028): pure functions from an area or a datum to a route.

Geometry is computed in the area's UTM frame (``frame.LocalFrame``) and returned in WGS84
with explicit keys. Every pattern takes a lane spacing (``spacing``: from the sensor
footprint or set explicitly) and, for airplanes, a turn radius (``turns``).
"""

import itertools
import math
from dataclasses import dataclass

import numpy as np
from shapely import MultiPolygon, Polygon

from fleet_service.domain.enums import MAX_MISSION_WAYPOINTS
from fleet_service.domain.patterns.contour import contour_lines, contour_route, perimeter_rings
from fleet_service.domain.patterns.datum import expanding_square, sector_search
from fleet_service.domain.patterns.frame import LocalFrame, long_axis_bearing
from fleet_service.domain.patterns.lanes import lane_route
from fleet_service.domain.patterns.route import PatternError, PatternKind, Route, RoutePoint
from fleet_service.domain.patterns.spacing import check_spacing
from fleet_service.domain.terrain import TerrainSet

__all__ = [
    "LocalFrame",
    "PatternError",
    "PatternKind",
    "PatternParams",
    "Route",
    "RoutePoint",
    "build_pattern",
    "route_length_m",
]

AREA_PATTERNS = frozenset(
    {PatternKind.PARALLEL_TRACK, PatternKind.CREEPING_LINE, PatternKind.CONTOUR}
)
DATUM_PATTERNS = frozenset({PatternKind.EXPANDING_SQUARE, PatternKind.SECTOR})


@dataclass(frozen=True)
class PatternParams:
    """What to fly. Bearings in degrees true; ``datum`` is (latitude, longitude)."""

    kind: PatternKind
    spacing_m: float
    altitude_relative_m: float
    speed_mps: float | None = None
    bearing_deg: float | None = None  # lane direction / first leg; None: along the long axis
    datum: tuple[float, float] | None = None
    radius_m: float | None = None  # sector radius; expanding-square extent
    second_pass: bool = False  # sector: a second pass rotated 30°
    turn_radius_m: float = 0.0  # 0 for multirotors
    height_agl_m: float | None = None  # contour: height above the contour


def route_length_m(points: list[tuple[float, float]]) -> float:
    """The length of a metric polyline."""
    return float(sum(math.dist(a, b) for a, b in itertools.pairwise(points)))


def build_pattern(
    params: PatternParams,
    frame: LocalFrame,
    area: Polygon | MultiPolygon | None = None,
    *,
    terrain: TerrainSet | None = None,
    home_amsl_m: float | None = None,
    start: tuple[float, float] | None = None,
) -> Route:
    """The route of ``params`` over ``area`` (metric, in ``frame``), starting near ``start``
    (metric). Raises ``PatternError`` for parameters no route can satisfy."""
    spacing = check_spacing(params.spacing_m)
    notes: list[str] = []
    fallback = False
    infeasible = 0
    altitudes: list[float] | None = None

    if params.kind in AREA_PATTERNS and area is None:
        raise PatternError("area-required", f"A {params.kind.value} search needs a search area.")

    if params.kind in (PatternKind.PARALLEL_TRACK, PatternKind.CREEPING_LINE):
        assert area is not None  # noqa: S101 - checked above
        bearing = params.bearing_deg
        if bearing is None:
            bearing = long_axis_bearing(area)
            if params.kind is PatternKind.CREEPING_LINE:
                bearing = (bearing + 90.0) % 360.0
        points, infeasible = lane_route(area, spacing, bearing, params.turn_radius_m, start)
    elif params.kind is PatternKind.CONTOUR:
        assert area is not None  # noqa: S101 - checked above
        lines = None
        if terrain is not None and terrain.grids:

            def heights(x: np.ndarray, y: np.ndarray) -> np.ndarray:
                lon, lat = frame.lonlat_arrays(x, y)
                return terrain.sample(lat, lon)

            lines = contour_lines(area, spacing, heights)
        if lines is None:
            fallback = True
            notes.append(
                "No terrain covers the whole area: flying perimeter rings instead of contours."
            )
            points = perimeter_rings(area, spacing, start)
        elif not lines:
            raise PatternError(
                "no-contours", "The area is too flat or too small for contour lines."
            )
        else:
            ordered = contour_route(lines, start)
            points = [p for _, line in ordered for p in line]
            if home_amsl_m is not None and params.height_agl_m is not None:
                altitudes = [
                    level + params.height_agl_m - home_amsl_m
                    for level, line in ordered
                    for _ in line
                ]
            else:
                notes.append(
                    "Home altitude or height above the contour unknown: the route keeps one "
                    "altitude above home instead of following the contours' heights."
                )
    elif params.kind in DATUM_PATTERNS:
        datum_xy = _datum(params, frame, area, notes)
        bearing = params.bearing_deg if params.bearing_deg is not None else 0.0
        if params.kind is PatternKind.EXPANDING_SQUARE:
            extent = params.radius_m
            if extent is None:
                if area is None:
                    raise PatternError(
                        "radius-required", "An expanding square needs an extent or an area."
                    )
                extent = max(
                    math.dist(datum_xy, (float(x), float(y)))
                    for x, y in area.envelope.boundary.coords
                )
            points = expanding_square(datum_xy, spacing, extent, bearing)
            if params.turn_radius_m > 0.0 and spacing < 2.0 * params.turn_radius_m:
                infeasible = 2  # the first legs are shorter than a turn diameter
        else:
            if params.radius_m is None:
                raise PatternError("radius-required", "A sector search needs a radius.")
            points = sector_search(datum_xy, params.radius_m, bearing, params.second_pass)
            if params.turn_radius_m > 0.0 and params.radius_m < 2.0 * params.turn_radius_m:
                infeasible = 6 if params.second_pass else 3
    else:
        raise PatternError("unsupported-pattern", f"{params.kind.value} is not an area pattern.")

    if infeasible:
        notes.append(
            f"{infeasible} turn(s) are tighter than the airplane's turn radius; "
            "PX4 will widen them."
        )
    if len(points) > MAX_MISSION_WAYPOINTS:
        raise PatternError(
            "too-many-waypoints",
            f"The route needs {len(points)} waypoints (at most {MAX_MISSION_WAYPOINTS}): "
            "widen the spacing or split the area.",
        )
    route_points = []
    for i, (x, y) in enumerate(points):
        lon, lat = frame.lonlat(x, y)
        route_points.append(
            RoutePoint(
                latitude=round(lat, 7),
                longitude=round(lon, 7),
                altitude_relative_m=round(
                    altitudes[i] if altitudes is not None else params.altitude_relative_m, 2
                ),
                speed_mps=params.speed_mps,
            )
        )
    return Route(
        pattern=params.kind,
        points=tuple(route_points),
        sweep_width_m=spacing,
        length_m=route_length_m(points),
        fallback=fallback,
        infeasible_turns=infeasible,
        notes=tuple(notes),
    )


def _datum(
    params: PatternParams, frame: LocalFrame, area: Polygon | MultiPolygon | None, notes: list[str]
) -> tuple[float, float]:
    if params.datum is not None:
        lat, lon = params.datum
        return frame.xy(lon, lat)
    if area is None:
        raise PatternError("datum-required", f"A {params.kind.value} search needs a datum.")
    notes.append("No datum given: the search starts at the area's centre.")
    centre = area.centroid
    return float(centre.x), float(centre.y)
