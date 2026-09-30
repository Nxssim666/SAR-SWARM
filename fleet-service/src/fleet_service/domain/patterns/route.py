"""The output of every pattern: an ordered route in WGS84, with what it covers (ADR 0028)."""

from dataclasses import dataclass, field
from enum import StrEnum


class PatternKind(StrEnum):
    """Search patterns (IAMSAR names where they exist)."""

    PARALLEL_TRACK = "parallel_track"  # lawnmower: lanes along the area's long axis
    CREEPING_LINE = "creeping_line"  # lanes across the long axis, from a start side
    EXPANDING_SQUARE = "expanding_square"  # from a datum outwards
    SECTOR = "sector"  # VS: three triangles through a datum
    CONTOUR = "contour"  # along terrain contours (DEM); perimeter rings as a fallback
    ROUTE = "route"  # an operator's waypoint route (waypoint missions)


class PatternError(ValueError):
    """The pattern cannot be built from these parameters (a stable code and a sentence)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RoutePoint:
    """One waypoint; the altitude is above the aircraft's home (ADR 0014)."""

    latitude: float
    longitude: float
    altitude_relative_m: float
    speed_mps: float | None = None
    loiter_s: float | None = None


@dataclass(frozen=True)
class Route:
    """A pattern's route.

    ``sweep_width_m`` is the width searched along the route (the lane spacing), used for
    coverage. ``fallback`` marks a substitute pattern (contour without terrain), and
    ``notes`` says what the operator should know (for example infeasible turns).
    """

    pattern: PatternKind
    points: tuple[RoutePoint, ...]
    sweep_width_m: float
    length_m: float
    fallback: bool = False
    infeasible_turns: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)
