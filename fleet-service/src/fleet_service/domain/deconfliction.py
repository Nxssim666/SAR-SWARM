"""
Deconfliction of planned flights (ADR 0029): pure functions, no I/O.

- **Altitude layers.** Multirotors fly the search altitude and a few layers above it, one
  layer spacing apart, round-robin in strip order (neighbouring strips differ); airplanes
  fly a band at least ``airframe_band_m`` above the highest multirotor layer. Layers are
  AMSL-consistent when the homes' altitudes are known.
- **Terrain clearance.** With terrain, every waypoint must be ``min_clearance_m`` to
  ``max_agl_m`` above the ground; without it, the altitude above home must stay under the
  station's limit.
- **4D check.** Each flight is sampled every ``sample_s``: hold where it is until its
  start delay, climb (or descend) there to its layer, fly the route at its speed, then
  (missions) return home on its layer. Two flights conflict where they are closer than
  ``horizontal_m`` horizontally **and** ``vertical_m`` vertically, at a time when at
  least one of them is moving. Aircraft already closer than that before anyone moves (at
  a launch site, say) are the present situation, which live alerts watch: for them the
  plan must not make it worse, so they conflict if they come ``PROXIMITY_MARGIN_M``
  closer than they are now. Between two samples the aircraft move in straight lines, so
  the closest approach within each interval is computed exactly (not just at samples);
  horizontal and vertical minima are taken per interval, which can only over-report.
- **Start delays.** Departures are sequenced ``departure_interval_s`` apart; while
  conflicts remain, the later-starting aircraft of the earliest conflict waits longer, up
  to ``max_start_delay_s``. What is left is reported, never hidden.

Unknown values stay unknown: a home altitude that is not known makes layers relative to
each home (reported), and a waypoint over unknown terrain is reported as unchecked.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

import numpy as np
from numpy.typing import NDArray

from fleet_service.domain.patterns.frame import LocalFrame
from fleet_service.domain.patterns.route import RoutePoint
from fleet_service.domain.terrain import TerrainSet

CLIMB_MPS = 2.5  # a conservative climb and descent rate for the departure
PROXIMITY_MARGIN_M = 10.0  # how much closer already-close aircraft may not come


@dataclass(frozen=True)
class Separation:
    """The deconfliction settings (``Settings`` provides them)."""

    horizontal_m: float = 50.0
    vertical_m: float = 15.0
    layer_spacing_m: float = 15.0
    multirotor_layers: int = 3
    airframe_band_m: float = 30.0
    min_clearance_m: float = 30.0
    max_agl_m: float = 120.0
    max_altitude_relative_m: float = 120.0
    departure_interval_s: float = 10.0
    max_start_delay_s: float = 600.0
    sample_s: float = 1.0
    max_iterations: int = 60


@dataclass(frozen=True)
class Flight:
    """One aircraft's planned flight. Positions are (latitude, longitude)."""

    aircraft_id: str
    callsign: str
    fixed_wing: bool
    route: tuple[RoutePoint, ...]
    speed_mps: float
    start: tuple[float, float] | None = None  # where it is now; None: at the route's start
    home: tuple[float, float] | None = None
    home_amsl_m: float | None = None
    start_altitude_relative_m: float | None = None  # now; None: at its first waypoint's
    start_delay_s: float = 0.0
    returns_home: bool = True  # missions end with a return; a goto holds at its target
    terrain_following: bool = False  # altitudes already per-aircraft (contour): no home align


@dataclass(frozen=True)
class Conflict:
    """Two flights too close: where and when they come closest."""

    aircraft: tuple[str, str]
    callsigns: tuple[str, str]
    t_s: float
    latitude: float
    longitude: float
    horizontal_m: float
    vertical_m: float


@dataclass(frozen=True)
class ClearanceIssue:
    """A waypoint too close to the ground, or too high."""

    aircraft_id: str
    callsign: str
    waypoint: int
    kind: str  # too-low | too-high
    height_m: float  # above ground (terrain known) or above home (not known)


@dataclass
class Report:
    """What deconfliction decided and found."""

    layers_m: dict[str, float] = field(default_factory=dict)  # added to each route's altitude
    start_delays_s: dict[str, float] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)
    clearance: list[ClearanceIssue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unchecked_terrain: int = 0

    @property
    def clear(self) -> bool:
        """No conflict and no clearance issue."""
        return not self.conflicts and not self.clearance


# --- layers --------------------------------------------------------------------------------------


def layer_offsets(flights: Sequence[Flight], sep: Separation) -> dict[str, float]:
    """Metres added to each flight's planned altitude, in the flights' (strip) order."""
    offsets: dict[str, float] = {}
    rotors = [f for f in flights if not f.fixed_wing]
    planes = [f for f in flights if f.fixed_wing]
    count = max(1, sep.multirotor_layers)
    for i, flight in enumerate(rotors):
        offsets[flight.aircraft_id] = (i % count) * sep.layer_spacing_m
    top = (min(count, len(rotors)) - 1) * sep.layer_spacing_m if rotors else -sep.airframe_band_m
    for i, flight in enumerate(planes):
        offsets[flight.aircraft_id] = top + sep.airframe_band_m + (i % 2) * sep.layer_spacing_m
    return offsets


def _home_offsets(flights: Sequence[Flight], notes: list[str]) -> dict[str, float]:
    """Per flight, metres to add so relative altitudes line up in AMSL (0 if unknown)."""
    known = [f.home_amsl_m for f in flights if f.home_amsl_m is not None]
    if len(known) < len(flights):
        missing = [f.callsign for f in flights if f.home_amsl_m is None]
        notes.append(
            "Home altitude unknown for " + ", ".join(missing) + ": their layers are taken "
            "relative to their own home, as if all homes were at the same altitude."
        )
    if not known:
        return {f.aircraft_id: 0.0 for f in flights}
    reference = max(known)  # the highest home: nobody is put below its search altitude
    return {
        f.aircraft_id: (reference - f.home_amsl_m) if f.home_amsl_m is not None else 0.0
        for f in flights
    }


def apply_layers(
    flights: Sequence[Flight], sep: Separation
) -> tuple[list[Flight], dict[str, float], list[str]]:
    """Flights with their layer added to every waypoint; the offsets; notes."""
    notes: list[str] = []
    offsets = layer_offsets(flights, sep)
    homes = _home_offsets(flights, notes)
    layered = []
    applied: dict[str, float] = {}
    for flight in flights:
        home = 0.0 if flight.terrain_following else homes[flight.aircraft_id]
        delta = offsets[flight.aircraft_id] + home
        applied[flight.aircraft_id] = delta
        layered.append(
            replace(
                flight,
                route=tuple(
                    replace(p, altitude_relative_m=round(p.altitude_relative_m + delta, 2))
                    for p in flight.route
                ),
            )
        )
    return layered, applied, notes


# --- terrain -------------------------------------------------------------------------------------


def check_clearance(
    flights: Sequence[Flight], terrain: TerrainSet | None, sep: Separation
) -> tuple[list[ClearanceIssue], int]:
    """Waypoints outside the allowed height band; how many could not be checked."""
    issues: list[ClearanceIssue] = []
    unchecked = 0
    for flight in flights:
        for i, point in enumerate(flight.route):
            ground = terrain.elevation_amsl(point.latitude, point.longitude) if terrain else None
            if ground is None or flight.home_amsl_m is None:
                unchecked += 1
                if point.altitude_relative_m > sep.max_altitude_relative_m:
                    issues.append(
                        ClearanceIssue(
                            flight.aircraft_id,
                            flight.callsign,
                            i,
                            "too-high",
                            point.altitude_relative_m,
                        )
                    )
                continue
            agl = flight.home_amsl_m + point.altitude_relative_m - ground
            if agl < sep.min_clearance_m:
                issues.append(
                    ClearanceIssue(flight.aircraft_id, flight.callsign, i, "too-low", agl)
                )
            elif agl > sep.max_agl_m:
                issues.append(
                    ClearanceIssue(flight.aircraft_id, flight.callsign, i, "too-high", agl)
                )
    return issues, unchecked


# --- 4D ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Track:
    t: NDArray[np.float64]  # knots: seconds after the plan starts
    xyz: NDArray[np.float64]  # knots: metres (x, y) and metres of altitude (z)
    depart_s: float  # moving from here on
    end_s: float  # after this the aircraft is home (landed) or holding at its target
    holds_at_end: bool


def _track(flight: Flight, frame: LocalFrame) -> _Track:
    points = [frame.xy(p.longitude, p.latitude) for p in flight.route]
    heights = [p.altitude_relative_m + (flight.home_amsl_m or 0.0) for p in flight.route]
    start_xy = frame.xy(flight.start[1], flight.start[0]) if flight.start else points[0]
    now_z = (
        flight.start_altitude_relative_m + (flight.home_amsl_m or 0.0)
        if flight.start_altitude_relative_m is not None
        else heights[0]
    )
    # Hold, then climb (or descend) on the spot to the first waypoint's altitude, then fly.
    knots_xy = [start_xy, start_xy, start_xy, *points]
    knots_z = [now_z, now_z, heights[0], *heights]
    speeds: list[float | None] = [None, None, None, *[p.speed_mps for p in flight.route]]
    if flight.returns_home and flight.home is not None:
        knots_xy.append(frame.xy(flight.home[1], flight.home[0]))
        knots_z.append(heights[-1])
        speeds.append(None)
    times = [0.0, flight.start_delay_s, flight.start_delay_s + abs(heights[0] - now_z) / CLIMB_MPS]
    for i in range(3, len(knots_xy)):
        distance = math.dist(knots_xy[i - 1], knots_xy[i])
        speed = speeds[i] or flight.speed_mps
        times.append(times[-1] + distance / max(speed, 0.1))
    return _Track(
        t=np.asarray(times),
        xyz=np.column_stack([np.asarray(knots_xy), np.asarray(knots_z)]),
        depart_s=flight.start_delay_s,
        end_s=times[-1],
        holds_at_end=not flight.returns_home,
    )


def _positions(track: _Track, times: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.column_stack([np.interp(times, track.t, track.xyz[:, k]) for k in range(3)])


def _interval_minima(d: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Per interval between samples, the least horizontal and vertical distance of a pair
    whose relative position ``d`` (T, 3) moves in a straight line within each interval."""
    a, b = d[:-1], d[1:]
    step = b[:, :2] - a[:, :2]
    length2 = np.einsum("ij,ij->i", step, step)
    u = np.where(
        length2 > 0.0,
        np.clip(
            -np.einsum("ij,ij->i", a[:, :2], step) / np.where(length2 > 0.0, length2, 1.0), 0.0, 1.0
        ),
        0.0,
    )
    nearest = a[:, :2] + step * u[:, None]
    horizontal = np.hypot(nearest[:, 0], nearest[:, 1])
    za, zb = a[:, 2], b[:, 2]
    vertical = np.where(za * zb <= 0.0, 0.0, np.minimum(np.abs(za), np.abs(zb)))
    return horizontal, vertical


def find_conflicts(flights: Sequence[Flight], frame: LocalFrame, sep: Separation) -> list[Conflict]:
    """Every pair of flights closer than the separation at some time (first contact each)."""
    if len(flights) < 2:
        return []
    tracks = [_track(f, frame) for f in flights]
    horizon = max(t.end_s for t in tracks)
    if any(t.holds_at_end for t in tracks):
        horizon += 60.0  # watch the aircraft that stay at their targets a little longer
    times = np.arange(0.0, horizon + sep.sample_s, sep.sample_s)
    positions = np.stack([_positions(t, times) for t in tracks], axis=1)  # (T, N, 3)
    active = np.stack(
        [(times <= t.end_s) | t.holds_at_end for t in tracks], axis=1
    )  # a flight that has landed back home is no longer in the air
    moving = np.stack([times >= t.depart_s for t in tracks], axis=1)
    conflicts: list[Conflict] = []
    for i in range(len(flights)):
        for j in range(i + 1, len(flights)):
            both = active[:, i] & active[:, j] & (moving[:, i] | moving[:, j])
            d = positions[:, i, :] - positions[:, j, :]
            h, v = _interval_minima(d)
            start_h = float(np.hypot(d[0, 0], d[0, 1]))
            limit = sep.horizontal_m
            if start_h < sep.horizontal_m and abs(d[0, 2]) < sep.vertical_m:  # already close
                limit = max(0.0, start_h - PROXIMITY_MARGIN_M)
            close = both[:-1] & both[1:] & (h < limit) & (v < sep.vertical_m)
            if not close.any():
                continue
            k = int(np.argmin(np.where(close, h, np.inf)))
            lon, lat = frame.lonlat(
                float((positions[k, i, 0] + positions[k, j, 0]) / 2),
                float((positions[k, i, 1] + positions[k, j, 1]) / 2),
            )
            conflicts.append(
                Conflict(
                    aircraft=(flights[i].aircraft_id, flights[j].aircraft_id),
                    callsigns=(flights[i].callsign, flights[j].callsign),
                    t_s=float(times[k]),
                    latitude=round(lat, 7),
                    longitude=round(lon, 7),
                    horizontal_m=round(float(h[k]), 1),
                    vertical_m=round(float(v[k]), 1),
                )
            )
    return sorted(conflicts, key=lambda c: c.t_s)


# --- all together --------------------------------------------------------------------------------


def deconflict(
    flights: Sequence[Flight],
    frame: LocalFrame,
    sep: Separation,
    terrain: TerrainSet | None = None,
    *,
    layered: bool = True,
    sequence: bool = True,
) -> tuple[list[Flight], Report]:
    """Layer, sequence and check flights; return the adjusted flights and the report."""
    report = Report()
    if layered:
        flights, report.layers_m, notes = apply_layers(flights, sep)
        report.notes.extend(notes)
    else:
        report.layers_m = {f.aircraft_id: 0.0 for f in flights}
    delays = {
        f.aircraft_id: max(f.start_delay_s, (i * sep.departure_interval_s) if sequence else 0.0)
        for i, f in enumerate(flights)
    }
    for _ in range(sep.max_iterations):
        scheduled = [replace(f, start_delay_s=delays[f.aircraft_id]) for f in flights]
        conflicts = find_conflicts(scheduled, frame, sep)
        if not conflicts or not sequence:
            break
        first = conflicts[0]
        a, b = first.aircraft
        later = b if delays[b] >= delays[a] else a
        wanted = delays[later] + max(sep.departure_interval_s, 30.0)
        if wanted > sep.max_start_delay_s:
            report.notes.append(
                f"Start delays would exceed {sep.max_start_delay_s:.0f} s: "
                "the remaining conflicts are reported."
            )
            break
        delays[later] = wanted
    flights = [replace(f, start_delay_s=delays[f.aircraft_id]) for f in flights]
    report.start_delays_s = dict(delays)
    report.conflicts = find_conflicts(flights, frame, sep)
    report.clearance, report.unchecked_terrain = check_clearance(flights, terrain, sep)
    if report.unchecked_terrain:
        report.notes.append(
            f"{report.unchecked_terrain} waypoint(s) over unknown terrain (or with the home "
            "altitude unknown): ground clearance not checked there."
        )
    return list(flights), report
