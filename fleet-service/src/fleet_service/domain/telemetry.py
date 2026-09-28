"""
The canonical telemetry sample every driver produces (ADR 0010, ADR 0014).

Units and frames are fixed here: WGS84 degrees, metres, metres per second, degrees true
clockwise from north. Every measurement may be ``None``: an unknown value is reported
as unknown, never replaced by a plausible default (ADR 0002, S7). Without a usable GNSS
fix the position is ``None`` even if the vehicle still has a dead-reckoned estimate.
"""

from dataclasses import dataclass
from datetime import datetime

from fleet_service.domain.enums import FlightMode, GpsFix


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    """One observation of one aircraft."""

    aircraft_id: str
    ts: datetime
    source: str  # driver that produced it: "mock", "mavlink", "swarm"
    latitude: float | None
    longitude: float | None
    altitude_amsl_m: float | None
    altitude_relative_m: float | None
    heading_deg: float | None
    groundspeed_mps: float | None
    climb_rate_mps: float | None
    battery_pct: float | None
    battery_v: float | None
    gps_fix: GpsFix
    satellites: int | None
    flight_mode: FlightMode
    armed: bool | None
    in_air: bool | None
    home_latitude: float | None
    home_longitude: float | None

    @property
    def has_position(self) -> bool:
        """True if the position is known."""
        return self.latitude is not None and self.longitude is not None
