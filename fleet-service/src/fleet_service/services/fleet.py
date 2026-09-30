"""
Live fleet state (ADR 0010): the registry of what every aircraft last reported, its link
state, and the drivers behind it.

The registry is the in-memory authority on live state; the database holds the plan and
the history. Telemetry arrives through driver sinks (synchronously, in the event loop)
and is announced on the bus by aircraft id only; subscribers read the current state when
they need it, so a burst of samples costs nothing beyond keeping the newest.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.bus import TELEMETRY, EventBus
from fleet_service.clock import Clock
from fleet_service.db.models import Aircraft
from fleet_service.domain.commands import VehicleView
from fleet_service.domain.enums import Airframe, LinkSource, LinkState
from fleet_service.domain.links import LinkThresholds, next_link_state
from fleet_service.domain.telemetry import TelemetrySample
from fleet_service.drivers.base import VehicleDriver
from fleet_service.drivers.mavlink import MavlinkDriver, MavlinkLinks, normalize_url
from fleet_service.drivers.mock import MockFleet
from fleet_service.drivers.swarm import LinkedDriver, SwarmDriver, SwarmLink
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
    route: "Route | None" = None  # the links behind the driver
    links: dict[LinkSource, LinkState] = field(default_factory=dict)  # both links: each one
    # When samples started flowing again after the link degraded (hysteresis, M6).
    recovering_since: datetime | None = None


@dataclass(frozen=True)
class Route:
    """An aircraft's links: MAVLink (connection, system id) and swarm drone id."""

    mavlink: tuple[str, int] | None
    swarm_drone_id: int | None


class FleetRegistry:
    """Live state of every registered aircraft."""

    def __init__(
        self,
        bus: EventBus,
        stale_after: timedelta,
        lost_after: timedelta,
        controller_of: ControllerLookup,
        recover_after: timedelta = timedelta(seconds=2),
    ) -> None:
        self._bus = bus
        self._stale_after = stale_after
        self._lost_after = lost_after
        self._thresholds = LinkThresholds(stale_after, lost_after, recover_after)
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
        """Driver sink: record a sample. A live (or first) link stays live at once; a degraded
        one starts recovering, and turns live only once data has held (``domain.links``)."""
        record = self._records.get(sample.aircraft_id)
        if record is None:
            return
        record.sample = sample
        if record.link in (LinkState.LIVE, LinkState.OFFLINE):
            record.link = LinkState.LIVE
        elif record.recovering_since is None:
            record.recovering_since = sample.ts
        self.announce(record.aircraft_id)

    def evaluate_links(self, now: datetime) -> list[tuple[str, LinkState, LinkState]]:
        """Age every link; return (aircraft id, old, new) for each change."""
        changes = []
        for record in self._records.values():
            if record.sample is None:
                continue  # never heard from: stays offline, which is not a loss
            age = now - record.sample.ts
            if age > self._stale_after:
                record.recovering_since = None  # a gap: recovery starts over
            recovering = now - record.recovering_since if record.recovering_since else None
            state = next_link_state(record.link, age, recovering, self._thresholds)
            if state is LinkState.LIVE:
                record.recovering_since = None
            links = self._source_links(record, now)
            if state is not record.link or links != record.links:
                if state is not record.link:
                    changes.append((record.aircraft_id, record.link, state))
                record.link, record.links = state, links
                self.announce(record.aircraft_id)
        return changes

    def _age_state(self, age: timedelta) -> LinkState:
        if age <= self._stale_after:
            return LinkState.LIVE
        if age <= self._lost_after:
            return LinkState.STALE
        return LinkState.LOST

    def _source_links(self, record: LiveRecord, now: datetime) -> dict[LinkSource, LinkState]:
        if not isinstance(record.driver, LinkedDriver):
            return {}
        return {
            source: LinkState.OFFLINE if heard is None else self._age_state(now - heard)
            for source, heard in record.driver.last_heard().items()
        }

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
            links=record.links,
            last_seen_at=record.sample.ts if record.sample else None,
            telemetry=TelemetryView.of(record.sample) if record.sample else None,
            controller=self._controller_of(record.aircraft_id),
        )

    def snapshot(self) -> list[AircraftLive]:
        """Live views of every aircraft, in registration order."""
        return [view for aircraft_id in self._records if (view := self.live(aircraft_id))]


class FleetManager:
    """Keeps drivers in step with the aircraft registry in the database.

    In simulation mode every aircraft gets a simulated one (ADR 0021). Otherwise an aircraft
    gets a driver for each link its registration names: MAVLink (connection and system id,
    on that connection's hub, ADR 0022) and swarm (drone id, through the bridge, ADR 0024);
    with both, one ``LinkedDriver`` merges them (ADR 0025). Changing a link replaces the
    driver and forgets the old telemetry. Simulated and real links are never mixed.
    """

    def __init__(
        self,
        registry: FleetRegistry,
        simulator: MockFleet | None,
        links: MavlinkLinks | None,
        swarm: SwarmLink | None = None,
        *,
        clock: Clock | None = None,
        fresh_for: timedelta = timedelta(seconds=3),
    ) -> None:
        self.registry = registry
        self.simulator = simulator
        self.links = links if simulator is None else None
        self.swarm = swarm if simulator is None else None
        self._clock = clock
        self._fresh_for = fresh_for

    async def load(self, db: AsyncSession) -> None:
        """Register every aircraft in the database (at startup)."""
        for aircraft in (await db.scalars(select(Aircraft).order_by(Aircraft.id))).all():
            self.register(aircraft)

    def register(self, aircraft: Aircraft) -> None:
        """Track a new aircraft, or update the identity and links of a tracked one."""
        route = self._route(aircraft)
        record = self.registry.get(aircraft.id)
        if record is not None:
            record.callsign = aircraft.callsign
            record.airframe = aircraft.airframe
            if self.simulator is None and route != record.route:
                self._release(record)
                record.sample, record.link, record.links = None, LinkState.OFFLINE, {}
                self._attach(record, aircraft, route)
            elif self.simulator is not None:
                record.route = route  # informational: which aircraft have a companion
            self.registry.announce(aircraft.id)
            return
        record = LiveRecord(aircraft.id, aircraft.callsign, aircraft.airframe)
        if self.simulator is not None:
            record.driver = self.simulator.add(aircraft.id, aircraft.airframe)
            record.route = route  # informational: the simulator stands in for every link
            record.driver.start(self.registry.ingest)
        else:
            self._attach(record, aircraft, route)
        self.registry.add(record)

    def unregister(self, aircraft_id: str) -> None:
        """Stop tracking an aircraft and release its driver."""
        record = self.registry.remove(aircraft_id)
        if record is not None:
            self._release(record)
        if self.simulator is not None:
            self.simulator.remove(aircraft_id)

    def swarm_aircraft(self) -> list[str]:
        """Aircraft with a swarm link: the drones a swarm mission reaches (ADR 0024)."""
        return [
            aircraft_id
            for aircraft_id in self.registry.ids()
            if (record := self.registry.get(aircraft_id))
            and record.route is not None
            and record.route.swarm_drone_id is not None
        ]

    def _route(self, aircraft: Aircraft) -> Route:
        mavlink = None
        if aircraft.mavlink_connection is not None and aircraft.mavlink_system_id is not None:
            mavlink = (normalize_url(aircraft.mavlink_connection), aircraft.mavlink_system_id)
        return Route(mavlink=mavlink, swarm_drone_id=aircraft.swarm_drone_id)

    def _attach(self, record: LiveRecord, aircraft: Aircraft, route: Route) -> None:
        record.route = route
        mavlink: MavlinkDriver | None = None
        swarm: SwarmDriver | None = None
        if self.links is not None and route.mavlink is not None:
            url, system_id = route.mavlink
            mavlink = self.links.driver(aircraft.id, url, system_id, aircraft.airframe)
        if self.swarm is not None and route.swarm_drone_id is not None:
            swarm = self.swarm.driver(aircraft.id, route.swarm_drone_id)
        driver: VehicleDriver | None = mavlink or swarm
        if mavlink is not None and swarm is not None:
            assert self._clock is not None  # noqa: S101 - the runtime passes it with links
            driver = LinkedDriver(mavlink, swarm, self._clock, self._fresh_for)
        record.driver = driver
        if driver is not None:
            driver.start(self.registry.ingest)

    def _release(self, record: LiveRecord) -> None:
        driver, record.driver, record.route = record.driver, None, None
        parts = [driver.mavlink, driver.swarm] if isinstance(driver, LinkedDriver) else [driver]
        for part in parts:
            if isinstance(part, MavlinkDriver) and self.links is not None:
                self.links.release(part)
            elif isinstance(part, SwarmDriver) and self.swarm is not None:
                self.swarm.release(part)
            elif part is not None:
                part.stop()
