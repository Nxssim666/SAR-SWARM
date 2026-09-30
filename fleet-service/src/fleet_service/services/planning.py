"""
Mission planning (ADR 0028, ADR 0029): from a mission, its area and aircraft to routes.

``plan_mission`` is pure and CPU-bound: the API gathers its inputs, ends its database
transaction, and runs it in a worker thread. It

1. picks each aircraft's speed (task override, aircraft, mission, airframe default) and,
   for airplanes, the turn radius;
2. splits an area among the aircraft in proportion to speed times endurance, strips in
   the order of where the aircraft are now (``domain.split``), or gives a waypoint route
   to every aircraft;
3. builds each aircraft's pattern (``domain.patterns``);
4. layers, sequences and checks the flights (``domain.deconfliction``);
5. adds what the operator should know: companion aircraft (onboard avoidance does not fly
   a ground-planned mission), endurance shortfalls, fallbacks, infeasible turns.
"""

import math
from dataclasses import dataclass, field, replace

import numpy as np
from shapely import LineString, Polygon, unary_union

from fleet_service.domain.deconfliction import Flight, Report, Separation, deconflict
from fleet_service.domain.enums import Airframe, MissionKind
from fleet_service.domain.patterns import (
    LocalFrame,
    PatternError,
    PatternKind,
    PatternParams,
    Route,
    RoutePoint,
    build_pattern,
    route_length_m,
)
from fleet_service.domain.patterns.frame import long_axis_bearing
from fleet_service.domain.patterns.turns import turn_radius_m
from fleet_service.domain.split import Share, split_area
from fleet_service.domain.terrain import TerrainSet

ONE_AIRCRAFT_PATTERNS = frozenset({PatternKind.EXPANDING_SQUARE, PatternKind.SECTOR})
COMPANION_NOTE = (
    "has a swarm companion: its onboard obstacle avoidance does not fly a ground-planned "
    "mission (the autopilot does). A swarm-area mission keeps avoidance active."
)


@dataclass(frozen=True)
class Defaults:
    """Airframe defaults from the settings."""

    multirotor_speed_mps: float = 10.0
    fixed_wing_speed_mps: float = 18.0
    multirotor_endurance_s: float = 1500.0
    fixed_wing_endurance_s: float = 3600.0
    fixed_wing_max_bank_deg: float = 30.0


@dataclass(frozen=True)
class AircraftInput:
    """One aircraft to plan for, with what is known of it now."""

    aircraft_id: str
    callsign: str
    airframe: Airframe
    companion: bool = False
    cruise_speed_mps: float | None = None
    endurance_s: float | None = None
    position: tuple[float, float] | None = None  # (latitude, longitude), now
    altitude_relative_m: float | None = None  # now
    home: tuple[float, float] | None = None
    home_amsl_m: float | None = None
    battery_pct: float | None = None
    altitude_override_m: float | None = None
    speed_override_mps: float | None = None
    start_delay_s: float | None = None

    @property
    def fixed_wing(self) -> bool:
        """True for airplanes."""
        return self.airframe is Airframe.FIXED_WING


@dataclass(frozen=True)
class PlanInput:
    """Everything a plan is made from."""

    mission_kind: MissionKind
    pattern: PatternKind
    spacing_m: float
    altitude_relative_m: float
    aircraft: tuple[AircraftInput, ...]
    area: tuple[tuple[float, float], ...] | None = None  # closed [longitude, latitude] ring
    route: tuple[RoutePoint, ...] | None = None  # waypoint missions
    speed_mps: float | None = None  # the mission's default
    bearing_deg: float | None = None
    datum: tuple[float, float] | None = None
    radius_m: float | None = None
    second_pass: bool = False
    height_agl_m: float | None = None


@dataclass
class PlannedTask:
    """One aircraft's part of the plan."""

    aircraft: AircraftInput
    route: Route
    speed_mps: float
    start_delay_s: float
    layer_m: float
    strip_area_m2: float | None
    duration_s: float
    notes: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """The result: tasks, the deconfliction report, and plan-wide notes."""

    pattern: PatternKind
    spacing_m: float
    tasks: list[PlannedTask]
    report: Report
    notes: list[str]
    area_m2: float | None
    coverage: float | None  # share of the area within half a sweep width of a route
    duration_s: float

    @property
    def clear(self) -> bool:
        """Startable without an override."""
        return self.report.clear


def _speed(a: AircraftInput, inp: PlanInput, defaults: Defaults) -> float:
    for value in (a.speed_override_mps, a.cruise_speed_mps, inp.speed_mps):
        if value is not None:
            return value
    return defaults.fixed_wing_speed_mps if a.fixed_wing else defaults.multirotor_speed_mps


def _endurance(a: AircraftInput, defaults: Defaults) -> float:
    if a.endurance_s is not None:
        return a.endurance_s
    return defaults.fixed_wing_endurance_s if a.fixed_wing else defaults.multirotor_endurance_s


def _frame(inp: PlanInput) -> LocalFrame:
    if inp.area:
        return LocalFrame.around(list(inp.area))
    if inp.datum is not None:
        return LocalFrame(*inp.datum)
    if inp.route:
        return LocalFrame(inp.route[0].latitude, inp.route[0].longitude)
    raise PatternError("area-required", "The plan needs a search area, a datum or a route.")


def plan_mission(
    inp: PlanInput, terrain: TerrainSet | None, sep: Separation, defaults: Defaults
) -> Plan:
    """Plan ``inp``; raises ``PatternError`` for parameters no plan can satisfy."""
    if not inp.aircraft:
        raise PatternError("no-aircraft", "Assign at least one aircraft to plan the mission.")
    if inp.pattern in ONE_AIRCRAFT_PATTERNS and len(inp.aircraft) > 1:
        raise PatternError(
            "one-aircraft-pattern",
            f"A {inp.pattern.value.replace('_', ' ')} is flown by one aircraft; plan one "
            "mission per aircraft.",
        )
    frame = _frame(inp)
    area = frame.polygon(inp.area) if inp.area else None
    speeds = {a.aircraft_id: _speed(a, inp, defaults) for a in inp.aircraft}

    def xy(a: AircraftInput) -> tuple[float, float] | None:
        where = a.position or a.home
        return frame.xy(where[1], where[0]) if where else None

    def altitude(a: AircraftInput) -> float:
        return (
            a.altitude_override_m if a.altitude_override_m is not None else inp.altitude_relative_m
        )

    def params(a: AircraftInput) -> PatternParams:
        speed = speeds[a.aircraft_id]
        return PatternParams(
            kind=inp.pattern,
            spacing_m=inp.spacing_m,
            altitude_relative_m=altitude(a),
            speed_mps=speed,
            bearing_deg=inp.bearing_deg,
            datum=inp.datum,
            radius_m=inp.radius_m,
            second_pass=inp.second_pass,
            turn_radius_m=(
                turn_radius_m(speed, defaults.fixed_wing_max_bank_deg) if a.fixed_wing else 0.0
            ),
            height_agl_m=inp.height_agl_m,
        )

    routes: dict[str, Route] = {}
    strip_areas: dict[str, float | None] = {}
    if inp.pattern is PatternKind.ROUTE:
        if not inp.route:
            raise PatternError("route-required", "Add waypoints to the route first.")
        points = [frame.xy(p.longitude, p.latitude) for p in inp.route]
        for a in inp.aircraft:
            route_points = tuple(
                RoutePoint(
                    p.latitude,
                    p.longitude,
                    a.altitude_override_m
                    if a.altitude_override_m is not None
                    else p.altitude_relative_m,
                    a.speed_override_mps if a.speed_override_mps is not None else p.speed_mps,
                    p.loiter_s,
                )
                for p in inp.route
            )
            routes[a.aircraft_id] = Route(
                PatternKind.ROUTE, route_points, inp.spacing_m, route_length_m(points)
            )
            strip_areas[a.aircraft_id] = None
    elif area is not None and inp.pattern not in ONE_AIRCRAFT_PATTERNS:
        lane_bearing = inp.bearing_deg
        if lane_bearing is None:
            lane_bearing = long_axis_bearing(area)
            if inp.pattern is PatternKind.CREEPING_LINE:
                lane_bearing = (lane_bearing + 90.0) % 360.0
            elif inp.pattern is PatternKind.CONTOUR and terrain is not None:
                # Strips along the contours: each aircraft searches a band of heights, and
                # its contour lines run the strip's full length.
                lane_bearing = contour_bearing(area, frame, terrain) or lane_bearing
        shares = [
            Share(a.aircraft_id, speeds[a.aircraft_id] * _endurance(a, defaults), xy(a))
            for a in inp.aircraft
        ]
        by_id = {a.aircraft_id: a for a in inp.aircraft}
        for aircraft_id, strip in split_area(area, lane_bearing, shares):
            a = by_id[aircraft_id]
            p = params(a)
            if inp.bearing_deg is None and inp.pattern is not PatternKind.CONTOUR:
                p = replace(p, bearing_deg=lane_bearing)
            routes[aircraft_id] = build_pattern(
                p, frame, strip, terrain=terrain, home_amsl_m=a.home_amsl_m, start=xy(a)
            )
            strip_areas[aircraft_id] = strip.area
    else:
        a = inp.aircraft[0]
        routes[a.aircraft_id] = build_pattern(
            params(a), frame, area, terrain=terrain, home_amsl_m=a.home_amsl_m, start=xy(a)
        )
        strip_areas[a.aircraft_id] = area.area if area is not None else None

    order = list(routes)  # strip order: neighbouring strips get different layers
    by_id = {a.aircraft_id: a for a in inp.aircraft}
    flights = []
    for aircraft_id in order:
        a = by_id[aircraft_id]
        route = routes[aircraft_id]
        if not route.points:
            raise PatternError("empty-route", f"{a.callsign}'s part of the area is empty.")
        flights.append(
            Flight(
                aircraft_id=aircraft_id,
                callsign=a.callsign,
                fixed_wing=a.fixed_wing,
                route=route.points,
                speed_mps=speeds[aircraft_id],
                start=a.position,
                home=a.home,
                home_amsl_m=a.home_amsl_m,
                start_altitude_relative_m=a.altitude_relative_m,
                start_delay_s=a.start_delay_s or 0.0,
                terrain_following=inp.pattern is PatternKind.CONTOUR and not route.fallback,
            )
        )
    adjusted, report = deconflict(flights, frame, sep, terrain)

    tasks = []
    for flight in adjusted:
        a = by_id[flight.aircraft_id]
        route = routes[flight.aircraft_id]
        layered = Route(
            route.pattern,
            flight.route,
            route.sweep_width_m,
            route.length_m,
            route.fallback,
            route.infeasible_turns,
            route.notes,
        )
        speed = speeds[flight.aircraft_id]
        duration = _duration(flight, frame, speed)
        notes = list(route.notes)
        if a.companion and inp.mission_kind is not MissionKind.SWARM_AREA:
            notes.append(f"{a.callsign} {COMPANION_NOTE}")
        endurance = _endurance(a, defaults)
        available = endurance * (a.battery_pct / 100.0) if a.battery_pct is not None else endurance
        if duration + flight.start_delay_s > 0.8 * available:
            notes.append(
                f"{a.callsign} needs about {(duration + flight.start_delay_s) / 60:.0f} min; "
                f"it has about {available / 60:.0f} min"
                + ("" if a.battery_pct is not None else " (battery unknown: full assumed)")
                + ". Reduce its share or the area."
            )
        tasks.append(
            PlannedTask(
                aircraft=a,
                route=layered,
                speed_mps=speed,
                start_delay_s=flight.start_delay_s,
                layer_m=report.layers_m.get(flight.aircraft_id, 0.0),
                strip_area_m2=strip_areas.get(flight.aircraft_id),
                duration_s=duration,
                notes=notes,
            )
        )

    coverage = None
    if area is not None:
        swept = unary_union(
            [
                LineString([frame.xy(p.longitude, p.latitude) for p in t.route.points]).buffer(
                    t.route.sweep_width_m / 2.0
                )
                for t in tasks
                if len(t.route.points) > 1
            ]
        )
        coverage = round(float(swept.intersection(area).area / area.area), 4)
    plan_notes = list(report.notes)
    if inp.pattern is PatternKind.CONTOUR and any(t.route.fallback for t in tasks):
        plan_notes.insert(0, "Contour search without terrain: perimeter rings (a fallback).")
    return Plan(
        pattern=inp.pattern,
        spacing_m=inp.spacing_m,
        tasks=tasks,
        report=report,
        notes=plan_notes,
        area_m2=area.area if isinstance(area, Polygon) else None,
        coverage=coverage,
        duration_s=max((t.start_delay_s + t.duration_s for t in tasks), default=0.0),
    )


def contour_bearing(area: Polygon, frame: LocalFrame, terrain: TerrainSet) -> float | None:
    """The bearing along which the terrain's contours run over ``area`` (0-180°), from the
    mean slope; None where the terrain is unknown or flat."""
    min_x, min_y, max_x, max_y = area.bounds
    xs = np.linspace(min_x, max_x, 12)
    ys = np.linspace(min_y, max_y, 12)
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = frame.lonlat_arrays(gx, gy)
    z = terrain.sample(lat, lon)
    if np.isnan(z).any():
        return None
    dz_dy, dz_dx = np.gradient(z, ys[1] - ys[0], xs[1] - xs[0])
    east, north = float(np.mean(dz_dx)), float(np.mean(dz_dy))
    if math.hypot(east, north) < 0.01:  # under 1 % of slope: no direction to follow
        return None
    uphill = math.degrees(math.atan2(east, north))  # bearing of the steepest ascent
    return (uphill + 90.0) % 180.0


def _duration(flight: Flight, frame: LocalFrame, speed: float) -> float:
    """Transit, route and return, at the planned speed (turns and climbs not counted)."""
    points = [frame.xy(p.longitude, p.latitude) for p in flight.route]
    if flight.start is not None:
        points.insert(0, frame.xy(flight.start[1], flight.start[0]))
    if flight.returns_home and flight.home is not None:
        points.append(frame.xy(flight.home[1], flight.home[0]))
    return route_length_m(points) / max(speed, 0.1) if len(points) > 1 else 0.0


__all__ = [
    "AircraftInput",
    "Defaults",
    "Plan",
    "PlanInput",
    "PlannedTask",
    "plan_mission",
]
