"""
The live side of the fleet service, composed and scheduled (ADR 0020).

Three periodic activities:

* simulation step, 10 Hz (simulation mode only);
* evaluation, 2 Hz: link states, control leases, alerts, command confirmations and
  effect verification;
* telemetry recording, once per ``telemetry_record_interval_s``.

In production they run as asyncio tasks. Tests create the app with ``start_loops=False``
and call ``step_simulation``/``evaluate``/``record`` themselves with a fake clock, so
nothing depends on real time. Each loop survives errors in a single iteration: a bug in
one evaluation must not stop link monitoring for the rest of the incident.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from fleet_service.bus import EventBus
from fleet_service.clock import Clock
from fleet_service.config import Settings
from fleet_service.db.engine import Database
from fleet_service.domain.commands import Limits
from fleet_service.domain.geo import GeoPoint
from fleet_service.drivers.mock import MockFleet
from fleet_service.services.alerts import AlertService
from fleet_service.services.commands import CommandService
from fleet_service.services.fleet import FleetManager, FleetRegistry
from fleet_service.services.leases import LeaseService, Presence
from fleet_service.services.recorder import TelemetryRecorder

log = logging.getLogger(__name__)

SIMULATION_STEP_S = 0.1
EVALUATION_PERIOD_S = 0.5


class Runtime:
    """Owns the bus, the live registry, drivers and the services built on them."""

    def __init__(self, settings: Settings, clock: Clock, database: Database) -> None:
        self.settings = settings
        self.clock = clock
        self.database = database
        self.bus = EventBus()
        self.presence = Presence()
        self.simulator = (
            MockFleet(
                GeoPoint(
                    latitude=settings.sim_origin_latitude, longitude=settings.sim_origin_longitude
                ),
                settings.sim_origin_altitude_amsl_m,
                settings.sim_seed,
            )
            if settings.simulation
            else None
        )
        self.leases = LeaseService(
            self.bus,
            self.presence,
            handover_timeout=timedelta(seconds=settings.handover_timeout_s),
            grace=timedelta(seconds=settings.control_grace_s),
        )
        self.registry = FleetRegistry(
            self.bus,
            stale_after=timedelta(seconds=settings.link_stale_after_s),
            lost_after=timedelta(seconds=settings.link_lost_after_s),
            controller_of=self.leases.view,
        )
        self.fleet = FleetManager(self.registry, self.simulator)
        self.alerts = AlertService(
            self.bus, settings.battery_low_pct, settings.battery_critical_pct
        )
        self.commands = CommandService(
            bus=self.bus,
            clock=clock,
            registry=self.registry,
            leases=self.leases,
            alerts=self.alerts,
            limits=Limits(
                min_takeoff_battery_pct=settings.min_takeoff_battery_pct,
                max_altitude_relative_m=settings.max_altitude_relative_m,
                goto_max_distance_m=settings.goto_max_distance_m,
                goto_confirm_distance_m=settings.goto_confirm_distance_m,
            ),
            battery_low_pct=settings.battery_low_pct,
            timeout_s=settings.command_timeout_s,
            effect_timeout_s=settings.command_effect_timeout_s,
            min_interval_s=settings.command_min_interval_s,
            confirmation_ttl_s=settings.confirmation_ttl_s,
        )
        self.recorder = TelemetryRecorder(self.bus, self.registry)
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self, start_loops: bool) -> None:
        """Load live state from the database and, unless testing, start the loops."""
        async with self.database.ops_session() as db:
            await self.fleet.load(db)
            await self.leases.load(db, self.clock.now())
            await self.alerts.load(db)
        if start_loops:
            if self.simulator is not None:
                self._spawn("simulation", SIMULATION_STEP_S, self._simulation_tick)
            self._spawn("evaluation", EVALUATION_PERIOD_S, self.evaluate)
            self._spawn("recorder", self.settings.telemetry_record_interval_s, self.record)

    async def stop(self) -> None:
        """Cancel the loops and release drivers."""
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        for aircraft_id in self.registry.ids():
            self.fleet.unregister(aircraft_id)
        self.recorder.close()

    # --- the periodic work (called by the loops, or directly by tests) ------------------------

    def step_simulation(self, dt: float) -> None:
        """Advance the simulated aircraft by ``dt`` seconds."""
        if self.simulator is not None:
            self.simulator.step(dt, self.clock.now())

    async def evaluate(self) -> None:
        """Links, leases, alerts, confirmations, command effects."""
        now = self.clock.now()
        self.registry.evaluate_links(now)
        async with self.database.ops_session() as db:
            await self.leases.evaluate(db, now)
            await self.alerts.evaluate(db, now, self.registry, self.leases.orphaned())
            await self.commands.evaluate(db, now)

    async def record(self) -> None:
        """Write the newest telemetry to the history."""
        async with self.database.telemetry_session() as db:
            await self.recorder.flush(db)

    async def _simulation_tick(self) -> None:
        self.step_simulation(SIMULATION_STEP_S)

    def _spawn(self, name: str, period_s: float, work: Callable[[], Awaitable[None]]) -> None:
        async def loop() -> None:
            while True:
                try:
                    await work()
                except Exception:
                    log.exception("%s loop iteration failed; continuing", name)
                await asyncio.sleep(period_s)

        self._tasks.append(asyncio.create_task(loop(), name=f"runtime-{name}"))
