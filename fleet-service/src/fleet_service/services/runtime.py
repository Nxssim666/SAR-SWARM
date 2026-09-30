"""
The live side of the fleet service, composed and scheduled (ADR 0020).

Three periodic activities:

* simulation step, 10 Hz (simulation mode only);
* evaluation, 2 Hz: link states, control leases, alerts, command confirmations and
  effect verification;
* telemetry recording, once per ``telemetry_record_interval_s``;
* video relay polling (M5, when ``mediamtx_api_url`` is set): stream health and
  ``video_down`` alerts (``services.video``);
* data retention (M5), every six hours: old telemetry, cleared alerts and finished
  commands are purged (``services.retention``);
* the audit chain's head, appended to a file outside the database every few minutes, so
  truncation is detectable (M6, ``services.audit_heads``).

Evaluation also watches the data disk (M6, ``services.station_health``): ``disk_low``, and
telemetry history pauses when space is critical.

In production they run as asyncio tasks. Tests create the app with ``start_loops=False``
and call ``step_simulation``/``evaluate``/``record`` themselves with a fake clock, so
nothing depends on real time. Each loop survives errors in a single iteration: a bug in
one evaluation must not stop link monitoring for the rest of the incident.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import select

from fleet_service.bus import EventBus
from fleet_service.clock import Clock
from fleet_service.config import Settings
from fleet_service.db.engine import Database
from fleet_service.db.models import VideoStream
from fleet_service.domain.commands import Limits
from fleet_service.domain.deconfliction import Separation
from fleet_service.domain.geo import GeoPoint
from fleet_service.domain.preflight import PreflightPolicy
from fleet_service.domain.terrain import TerrainSet
from fleet_service.drivers.mavlink import MavlinkLinks
from fleet_service.drivers.mock import MockFleet
from fleet_service.drivers.swarm import SwarmLink
from fleet_service.services import audit_heads
from fleet_service.services.alerts import AlertService, AlertTuning
from fleet_service.services.audit import Actor
from fleet_service.services.commands import CommandService
from fleet_service.services.fleet import FleetManager, FleetRegistry
from fleet_service.services.leases import LeaseService, Presence
from fleet_service.services.missions import MissionService
from fleet_service.services.pois import PoiService
from fleet_service.services.preflight import PreflightService
from fleet_service.services.recorder import TelemetryRecorder
from fleet_service.services.retention import PurgeReport, RetentionPolicy, purge
from fleet_service.services.station_health import (
    disk_condition,
    free_bytes,
    recording_allowed,
)
from fleet_service.services.video import RelayConfig, StreamInfo, VideoMonitor, mediamtx_fetch

log = logging.getLogger(__name__)

SIMULATION_STEP_S = 0.1
EVALUATION_PERIOD_S = 0.5
RETENTION_PERIOD_S = 6 * 3600.0
RETENTION_ACTOR = Actor(user_id=None, username="system:retention")


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
            recover_after=timedelta(seconds=settings.link_recover_after_s),
        )
        self.links = (
            MavlinkLinks(clock) if settings.mavlink_links and not settings.simulation else None
        )
        self.swarm = (
            SwarmLink(settings.nats_url, settings.swarm_name, clock)
            if settings.nats_url and not settings.simulation
            else None
        )
        self.fleet = FleetManager(
            self.registry,
            self.simulator,
            self.links,
            self.swarm,
            clock=clock,
            fresh_for=timedelta(seconds=settings.link_stale_after_s),
        )
        self.alerts = AlertService(
            self.bus,
            settings.battery_low_pct,
            settings.battery_critical_pct,
            AlertTuning(
                reserve_pct=settings.return_reserve_pct,
                escalate_after_s=settings.alert_escalate_after_s,
                proximity_m=settings.proximity_alert_m,
                proximity_vertical_m=settings.proximity_alert_vertical_m,
                lookahead_s=settings.proximity_lookahead_s,
                multirotor_speed_mps=settings.multirotor_speed_mps,
                fixed_wing_speed_mps=settings.fixed_wing_speed_mps,
            ),
        )
        self.separation = separation_of(settings)
        self.preflight = PreflightService(
            self.registry,
            preflight_policy(settings),
            clock,
            timeout_s=settings.preflight_timeout_s,
            max_age=timedelta(seconds=settings.preflight_max_age_s),
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
            swarm_grid_resolution_m=settings.swarm_grid_resolution_m,
            swarm_aircraft=self.fleet.swarm_aircraft,
            separation=self.separation,
            goto_spread_m=settings.goto_spread_m,
            mission_timeout_s=settings.mission_upload_timeout_s,
            preflight=self.preflight,
        )
        self.recorder = TelemetryRecorder(self.bus, self.registry)
        self.pois = PoiService(self.bus, self.alerts)
        self.missions = MissionService(self.bus, self.alerts, self.registry)
        self.terrain = TerrainSet.load(settings.terrain_directory)
        self.video = (
            VideoMonitor(
                mediamtx_fetch(settings.mediamtx_api_url),
                config=RelayConfig(settings.mediamtx_api_url),
            )
            if settings.mediamtx_api_url
            else None
        )
        # Free space on the data disk; tests replace it.
        self.free_bytes: Callable[[], int | None] = lambda: free_bytes(settings.data_dir)
        self._recording_paused = False
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self, start_loops: bool) -> None:
        """Load live state from the database and, unless testing, start the loops."""
        if self.links is not None:
            # MAVSDK's asyncio API runs each blocking call in the loop's default executor;
            # asyncio's default pool (8 threads on 4 cores) queued bulk commands (M2b).
            asyncio.get_running_loop().set_default_executor(
                ThreadPoolExecutor(self.settings.mavlink_threads, thread_name_prefix="mavsdk")
            )
        async with self.database.ops_session() as db:
            await self.fleet.load(db)
            await self.leases.load(db, self.clock.now())
            await self.alerts.load(db)
            interrupted = await self.commands.load(db, self.clock.now())
            if interrupted:
                log.warning("%d command(s) interrupted by the restart; not re-sent", interrupted)
        if start_loops:
            if self.simulator is not None:
                self._spawn("simulation", SIMULATION_STEP_S, self._simulation_tick)
            self._spawn("evaluation", EVALUATION_PERIOD_S, self.evaluate)
            self._spawn("recorder", self.settings.telemetry_record_interval_s, self.record)
            self._spawn("retention", RETENTION_PERIOD_S, self._retention_tick)
            self._spawn("audit-head", self.settings.audit_head_interval_s, self.export_audit_head)
            if self.video is not None:
                self._spawn("video", self.settings.video_poll_interval_s, self.poll_video)

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
        if self.links is not None:
            await self.links.close()
        if self.swarm is not None:
            await self.swarm.close()
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
            await self.missions.evaluate(db, now)
            video = self.video.conditions(now) if self.video is not None else []
            disk = disk_condition(
                self.free_bytes(),
                self.settings.disk_warn_free_mb,
                self.settings.disk_critical_free_mb,
            )
            await self.alerts.evaluate(
                db,
                now,
                self.registry,
                self.leases.orphaned(),
                [*self.missions.deviations(), *video, *([disk] if disk else [])],
            )
            await self.commands.evaluate(db, now)
            await self.pois.evaluate(db, now, self.registry)

    async def record(self) -> None:
        """Write the newest telemetry to the history, unless the disk is nearly full."""
        allowed = recording_allowed(self.free_bytes(), self.settings.disk_critical_free_mb)
        if allowed == self._recording_paused:
            self._recording_paused = not allowed
            log.warning("telemetry history %s", "resumed" if allowed else "paused: disk full")
        if not allowed:
            self.recorder.skip()
            return
        async with self.database.telemetry_session() as db:
            await self.recorder.flush(db)

    async def export_audit_head(self) -> bool:
        """Append the audit chain's head to the head file (a short session, then the file)."""
        async with self.database.ops_session() as db:
            head = await audit_heads.current_head(db)
        if head is None:
            return False
        return await asyncio.to_thread(
            audit_heads.append_head, self.settings.audit_heads_path, head, self.clock.now()
        )

    async def purge(self, *, dry_run: bool = False) -> PurgeReport:
        """Apply the retention policy (short sessions of its own)."""
        async with (
            self.database.ops_session() as ops,
            self.database.telemetry_session() as telemetry,
        ):
            return await purge(
                ops,
                telemetry,
                retention_policy(self.settings),
                self.clock.now(),
                RETENTION_ACTOR,
                dry_run=dry_run,
            )

    async def poll_video(self) -> None:
        """Read the registered streams (a short session), then ask the relay (no session)."""
        if self.video is None:
            return
        async with self.database.ops_session() as db:
            rows = (await db.scalars(select(VideoStream))).all()
            streams = [
                StreamInfo(r.id, r.name, r.relay_path, r.aircraft_id, r.enabled, r.source_url)
                for r in rows
            ]
        self.video.set_streams(streams)
        await self.video.poll(self.clock.now())

    async def _retention_tick(self) -> None:
        report = await self.purge()
        if report.telemetry_samples or report.alerts or report.commands:
            log.info("retention purge: %s", report)

    async def _simulation_tick(self) -> None:
        self.step_simulation(SIMULATION_STEP_S)

    def _spawn(self, name: str, period_s: float, work: Callable[[], Awaitable[object]]) -> None:
        async def loop() -> None:
            while True:
                try:
                    await work()
                except Exception:
                    log.exception("%s loop iteration failed; continuing", name)
                await asyncio.sleep(period_s)

        self._tasks.append(asyncio.create_task(loop(), name=f"runtime-{name}"))


def preflight_policy(settings: Settings) -> PreflightPolicy:
    """The preflight settings."""
    return PreflightPolicy(
        max_link_loss_s=settings.preflight_max_link_loss_s,
        max_altitude_relative_m=settings.max_altitude_relative_m,
        min_return_altitude_m=settings.preflight_min_return_altitude_m,
        min_critical_battery_pct=settings.preflight_min_critical_battery_pct,
    )


def retention_policy(settings: Settings) -> RetentionPolicy:
    """The retention settings."""
    return RetentionPolicy(
        telemetry_days=settings.telemetry_retention_days,
        alert_days=settings.alert_retention_days,
        command_days=settings.command_retention_days,
    )


def separation_of(settings: Settings) -> Separation:
    """The deconfliction settings."""
    return Separation(
        horizontal_m=settings.separation_horizontal_m,
        vertical_m=settings.separation_vertical_m,
        layer_spacing_m=settings.layer_spacing_m,
        multirotor_layers=settings.multirotor_layers,
        airframe_band_m=settings.airframe_band_m,
        min_clearance_m=settings.min_terrain_clearance_m,
        max_agl_m=settings.max_height_agl_m,
        max_altitude_relative_m=settings.max_altitude_relative_m,
        departure_interval_s=settings.departure_interval_s,
        max_start_delay_s=settings.max_start_delay_s,
    )
