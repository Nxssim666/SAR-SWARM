"""
Telemetry history (ADR 0007): the newest sample of each aircraft, written once per
interval (1 s by default) in one transaction. Consoles get full-rate telemetry live;
the history is for replay and incident review, where 1 Hz is plenty.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.bus import TELEMETRY, EventBus
from fleet_service.db.models import TelemetrySample as TelemetryRow
from fleet_service.services.fleet import FleetRegistry


class TelemetryRecorder:
    """Downsamples live telemetry into ``telemetry.db``."""

    def __init__(self, bus: EventBus, registry: FleetRegistry) -> None:
        self._registry = registry
        self._subscription = bus.latest([TELEMETRY])
        self._last_written: dict[str, object] = {}

    async def flush(self, db: AsyncSession) -> int:
        """Write the newest unseen sample of every aircraft; return how many rows."""
        rows = []
        for event in self._subscription.drain():
            record = self._registry.get(str(event.key))
            sample = record.sample if record else None
            if sample is None or self._last_written.get(sample.aircraft_id) is sample:
                continue  # link-state change without a new sample
            self._last_written[sample.aircraft_id] = sample
            rows.append(
                TelemetryRow(
                    aircraft_id=sample.aircraft_id,
                    ts_us=int(sample.ts.timestamp() * 1_000_000),
                    source=sample.source,
                    latitude=sample.latitude,
                    longitude=sample.longitude,
                    altitude_amsl_m=sample.altitude_amsl_m,
                    altitude_relative_m=sample.altitude_relative_m,
                    heading_deg=sample.heading_deg,
                    groundspeed_mps=sample.groundspeed_mps,
                    climb_rate_mps=sample.climb_rate_mps,
                    battery_pct=sample.battery_pct,
                    battery_v=sample.battery_v,
                    gps_fix=sample.gps_fix.code,
                    satellites=sample.satellites,
                    flight_mode=sample.flight_mode.value,
                    armed=sample.armed,
                    in_air=sample.in_air,
                )
            )
        if rows:
            db.add_all(rows)
            await db.commit()
        return len(rows)

    def close(self) -> None:
        """Stop listening."""
        self._subscription.close()
