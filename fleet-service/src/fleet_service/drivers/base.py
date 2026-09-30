"""
The driver interface everything above the drivers depends on (ADR 0010).

A driver reports telemetry by calling its sink with canonical ``TelemetrySample``s and
executes commands, answering ack, nack (with the aircraft's reason) or nothing: the
command pipeline bounds every ``execute`` with its own timeout, so a driver whose link
is down may simply wait.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from fleet_service.domain.enums import CommandKind
from fleet_service.domain.patterns.route import RoutePoint
from fleet_service.domain.telemetry import TelemetrySample

TelemetrySink = Callable[[TelemetrySample], None]


@dataclass(frozen=True)
class AreaMission:
    """A swarm area search, as the swarm protocol carries it (ADR 0003, ADR 0024)."""

    mission_id: str
    origin: tuple[float, float]  # latitude, longitude of the shared mission frame
    altitude_relative_m: float  # above each drone's home
    grid_resolution_m: float
    waypoints: tuple[tuple[float, float], ...]  # transit, flown first
    area: tuple[tuple[float, float], ...]  # polygon, not closed


@dataclass(frozen=True)
class RouteMission:
    """A GCS-planned mission for one aircraft (ADR 0028), flown by its autopilot.

    Altitudes are above the aircraft's home. The first item may be a loiter where the
    aircraft is: its planned start delay, flown on board so departures stay sequenced.
    """

    mission_id: str
    items: tuple[RoutePoint, ...]
    return_home: bool = True


@dataclass(frozen=True)
class DriverCommand:
    """A command for one aircraft, already authorized and checked.

    ``command_id`` is shared by every aircraft of one (bulk) command, so a link that can
    address many aircraft at once (the swarm bridge) sends it once.
    """

    kind: CommandKind
    altitude_relative_m: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    command_id: str | None = None
    mission: AreaMission | None = None
    route: RouteMission | None = None  # mission_start of a GCS-planned mission
    gcs_mission: bool = False  # the command concerns a GCS-planned (autopilot) mission


class Outcome(StrEnum):
    """What the aircraft answered."""

    ACKED = "acked"
    NACKED = "nacked"


@dataclass(frozen=True)
class CommandResult:
    """The aircraft's answer."""

    outcome: Outcome
    reason: str | None = None

    @classmethod
    def ack(cls) -> "CommandResult":
        """Accepted."""
        return cls(Outcome.ACKED)

    @classmethod
    def nack(cls, reason: str) -> "CommandResult":
        """Refused by the aircraft."""
        return cls(Outcome.NACKED, reason)


class VehicleDriver(Protocol):
    """One aircraft's link."""

    @property
    def source(self) -> str:
        """Short name of the driver, stored with each sample (``mock``, ``mavlink``)."""
        ...

    @property
    def capabilities(self) -> frozenset[CommandKind]:
        """Commands this link can carry."""
        ...

    def start(self, sink: TelemetrySink) -> None:
        """Begin delivering telemetry to ``sink``."""
        ...

    def stop(self) -> None:
        """Stop delivering telemetry and release the link."""
        ...

    async def execute(self, command: DriverCommand) -> CommandResult:
        """Send ``command``; may wait indefinitely if the link is down (callers time out)."""
        ...
