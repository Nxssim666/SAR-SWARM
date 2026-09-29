"""
The canonical telemetry sample every driver produces (ADR 0010, ADR 0014).

Units and frames are fixed here: WGS84 degrees, metres, metres per second, degrees true
clockwise from north. Every measurement may be ``None``: an unknown value is reported
as unknown, never replaced by a plausible default (ADR 0002, S7). Without a usable GNSS
fix the position is ``None`` even if the vehicle still has a dead-reckoned estimate.

An aircraft may have two links, MAVLink to its autopilot and the swarm protocol to its
companion computer (ADR 0003); ``merge`` combines their samples (ADR 0025).
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta

from fleet_service.domain.enums import FlightMode, GpsFix, SwarmFault, SwarmHealth, SwarmPhase


@dataclass(frozen=True, slots=True)
class SurvivorSighting:
    """Where a swarm drone's estimate puts a person (the onboard "target" estimate)."""

    latitude: float
    longitude: float
    std_m: float  # 1-sigma horizontal uncertainty
    stamp: datetime


@dataclass(frozen=True, slots=True)
class SwarmState:
    """What a swarm companion reports about itself (onboard ``DroneState``)."""

    drone_id: int
    phase: SwarmPhase
    health: SwarmHealth
    faults: frozenset[SwarmFault]
    mission_sequence: int  # active mission (0: none)
    command_sequence: int  # last operator command processed
    nearest_obstacle_m: float | None
    survivor_sighting: SurvivorSighting | None


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """One observation of one aircraft."""

    aircraft_id: str
    ts: datetime
    source: str  # driver that produced it: "mock", "mavlink", "swarm", or "mavlink+swarm"
    latitude: float | None
    longitude: float | None
    altitude_amsl_m: float | None
    altitude_relative_m: float | None
    heading_deg: float | None
    groundspeed_mps: float | None
    climb_rate_mps: float | None
    battery_pct: float | None
    battery_v: float | None
    gps_fix: GpsFix | None  # None: the link does not report GNSS quality
    satellites: int | None
    flight_mode: FlightMode
    armed: bool | None
    in_air: bool | None
    home_latitude: float | None
    home_longitude: float | None
    swarm: SwarmState | None = None  # only from a swarm link

    @property
    def has_position(self) -> bool:
        """True if the position is known."""
        return self.latitude is not None and self.longitude is not None


def merge(
    mavlink: TelemetrySample | None,
    swarm: TelemetrySample | None,
    now: datetime,
    fresh_for: timedelta,
) -> TelemetrySample | None:
    """One aircraft's state from its MAVLink and swarm samples (ADR 0025).

    - While the MAVLink sample is fresh it is the state: the autopilot knows best.
    - Otherwise a fresh swarm sample gives position, heading and groundspeed; everything
      else is unknown, since the companion does not report it.
    - The swarm block is attached while the swarm sample is fresh.
    - With neither fresh, the newest sample is kept as it was (the link ages it).

    The result's timestamp is the newest used, so the link stays live while any source is.
    """

    def fresh(sample: TelemetrySample | None) -> bool:
        return sample is not None and now - sample.ts <= fresh_for

    if not fresh(mavlink) and not fresh(swarm):
        newest = [s for s in (mavlink, swarm) if s is not None]
        return max(newest, key=lambda s: s.ts) if newest else None
    if fresh(mavlink):
        assert mavlink is not None  # noqa: S101 - fresh() checked it
        if not fresh(swarm):
            return mavlink
        assert swarm is not None  # noqa: S101
        return dataclasses.replace(
            mavlink, ts=max(mavlink.ts, swarm.ts), source="mavlink+swarm", swarm=swarm.swarm
        )
    assert swarm is not None  # noqa: S101 - one of the two is fresh
    return swarm
