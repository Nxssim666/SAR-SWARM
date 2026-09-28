"""
Live fleet state (ADR 0010): the registry of what every aircraft last reported, its link
state, and the drivers behind it.

The registry is the in-memory authority on live state; the database holds the plan and
the history. Telemetry arrives through driver sinks (synchronously, in the event loop)
and is announced on the bus by aircraft id only; subscribers read the current state when
they need it, so a burst of samples costs nothing beyond keeping the newest.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.bus import TELEMETRY, EventBus
from fleet_service.db.models import Aircraft
from fleet_service.domain.commands import VehicleView
from fleet_service.domain.enums import Airframe, LinkState
from fleet_service.domain.telemetry import TelemetrySample
from fleet_service.drivers.base import VehicleDriver
from fleet_service.drivers.mock import MockFleet
from fleet_service.services.views import AircraftLive, LeaseView, TelemetryView

ControllerLookup = Callable[[str], LeaseView | None]


@dataclass
class LiveRecord:
    """What the ground station knows about one aircraft right now."""

    aircraft_id: str
    callsign: str
    airframe: Airframe
    driver: VehicleDriver | None = None
    sample: TelemetrySample | None = None
    link: LinkState = LinkState.OFFLINE


class FleetRegistry:
    """Live state of every registered aircraft."""

    def __init__(
        self,
        bus: EventBus,
        stale_after: timedelta,
        lost_after: timedelta,
        controller_of: ControllerLookup,
    ) -> None:
        self._bus = bus
        self._stale_after = stale_after
        self._lost_after = lost_after
        self._controller_of = controller_of
        self._records: dict[str, LiveRecord] = {}

    # --- membership ----------------------------------------------------------------------------

    def add(self, record: LiveRecord) -> None:
        """Track an aircraft."""
        self._records[record.aircraft_id] = record
        self.announce(record.aircraft_id)

    def remove(self, aircraft_id: str) -> LiveRecord | None:
        """Stop tracking an aircraft."""
        return self._records.pop(aircraft_id, None)

    def get(self, aircraft_id: str) -> LiveRecord | None:
        """The live record of an aircraft, if registered."""
        return self._records.get(aircraft_id)

    def ids(self) -> list[str]:
        """Registered aircraft ids, in registration order."""
        return list(self._records)

    # --- telemetry and links ---------------------------------------------------------------------

    def ingest(self, sample: TelemetrySample) -> None:
        """Driver sink: record a sample; the link becomes live."""
        record = self._records.get(sample.aircraft_id)
        if record is None:
            return
        record.sample = sample
        record.link = LinkState.LIVE
        self.announce(record.aircraft_id)

    def evaluate_links(self, now: datetime) -> list[tuple[str, LinkState, LinkState]]:
        """Age every link; return (aircraft id, old, new) for each change."""
        changes = []
        for record in self._records.values():
            if record.sample is None:
                continue  # never heard from: stays offline, which is not a loss
            age = now - record.sample.ts
            if age <= self._stale_after:
                state = LinkState.LIVE
            elif age <= self._lost_after:
                state = LinkState.STALE
            else:
                state = LinkState.LOST
            if state is not record.link:
                changes.append((record.aircraft_id, record.link, state))
                record.link = state
                self.announce(record.aircraft_id)
        return changes

    def announce(self, aircraft_id: str) -> None:
        """Tell subscribers that an aircraft's live state changed."""
        self._bus.publish(TELEMETRY, aircraft_id, key=aircraft_id)

    # --- views -------------------------------------------------------------------------------

    def vehicle_view(self, aircraft_id: str) -> VehicleView | None:
        """What the command rules need to know about an aircraft."""
        record = self._records.get(aircraft_id)
        if record is None:
            return None
        return VehicleView(
            callsign=record.callsign,
            link=record.link if record.driver is not None else LinkState.OFFLINE,
            capabilities=record.driver.capabilities if record.driver else frozenset(),
            sample=record.sample,
        )

    def live(self, aircraft_id: str) -> AircraftLive | None:
        """The live view of one aircraft."""
        record = self._records.get(aircraft_id)
        if record is None:
            return None
        return AircraftLive(
            aircraft_id=record.aircraft_id,
            callsign=record.callsign,
            airframe=record.airframe,
            link=record.link,
            last_seen_at=record.sample.ts if record.sample else None,
            telemetry=TelemetryView.of(record.sample) if record.sample else None,
            controller=self._controller_of(record.aircraft_id),
        )

    def snapshot(self) -> list[AircraftLive]:
        """Live views of every aircraft, in registration order."""
        return [view for aircraft_id in self._records if (view := self.live(aircraft_id))]


class FleetManager:
    """Keeps drivers in step with the aircraft registry in the database."""

    def __init__(self, registry: FleetRegistry, simulator: MockFleet | None) -> None:
        self.registry = registry
        self.simulator = simulator

    async def load(self, db: AsyncSession) -> None:
        """Register every aircraft in the database (at startup)."""
        for aircraft in (await db.scalars(select(Aircraft).order_by(Aircraft.id))).all():
            self.register(aircraft)

    def register(self, aircraft: Aircraft) -> None:
        """Track a new aircraft, or update the identity of a tracked one."""
        record = self.registry.get(aircraft.id)
        if record is not None:
            record.callsign = aircraft.callsign
            record.airframe = aircraft.airframe
            self.registry.announce(aircraft.id)
            return
        driver = self.simulator.add(aircraft.id, aircraft.airframe) if self.simulator else None
        record = LiveRecord(aircraft.id, aircraft.callsign, aircraft.airframe, driver)
        if driver is not None:
            driver.start(self.registry.ingest)
        self.registry.add(record)

    def unregister(self, aircraft_id: str) -> None:
        """Stop tracking an aircraft and release its driver."""
        record = self.registry.remove(aircraft_id)
        if record is not None and record.driver is not None:
            record.driver.stop()
        if self.simulator is not None:
            self.simulator.remove(aircraft_id)
