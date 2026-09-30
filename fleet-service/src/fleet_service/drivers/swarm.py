"""
Swarm aircraft (ADR 0003) through the ROS 2 bridge, over NATS (ADR 0024).

``SwarmLink`` is the one NATS connection for a swarm: it routes each drone's status to
its ``SwarmDriver`` by the onboard ``drone_id``, and sends commands and missions to the
bridge as requests. The bridge assigns the protocol's sequence numbers and republishes;
a driver acknowledges a command once its own drone reports that sequence as processed
(``DroneState.command_sequence`` / ``mission_sequence``). No reply, or no catch-up, is
no answer: the command pipeline's timeout applies, never a guessed outcome.

The onboard protocol advances a drone's command sequence for commands addressed to other
drones too, so the drones of one (bulk) command are sent together, in one message; the
command pipeline then verifies each command's effect (the swarm phase).

``LinkedDriver`` combines a MAVLink driver and a swarm driver for an aircraft that has
both links (ADR 0025): merged telemetry, and each command over the link
``route_command`` picks.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import nats
from nats.aio.client import Client
from nats.aio.msg import Msg
from nats.errors import Error as NatsError
from pydantic import BaseModel, ValidationError

from fleet_service.clock import Clock
from fleet_service.domain.commands import SWARM_COMMANDS, route_command
from fleet_service.domain.enums import CommandKind, FlightMode, LinkSource, SwarmFault
from fleet_service.domain.telemetry import (
    SurvivorSighting,
    SwarmState,
    TelemetrySample,
    merge,
)
from fleet_service.drivers.base import (
    AreaMission,
    CommandResult,
    DriverCommand,
    TelemetrySink,
    VehicleDriver,
)
from fleet_service.drivers.swarm_wire import (
    BridgeHeartbeat,
    BridgeReply,
    SwarmCommandKind,
    SwarmCommandRequest,
    SwarmMissionRequest,
    SwarmStatus,
    WirePoint,
    subject,
)

log = logging.getLogger(__name__)

CONNECT_RETRY_S = 2.0
REQUEST_TIMEOUT_S = 2.0
MISSION_MEMORY_S = 60.0  # a straggler of a bulk mission start reuses the first reply
REJECTION_GRACE_S = 1.0  # an older mission_rejected fault clears within it (states at 5 Hz)

_COMMAND_KINDS = {
    CommandKind.HOLD: SwarmCommandKind.HOLD,
    CommandKind.RESUME: SwarmCommandKind.RESUME,
    CommandKind.RETURN_TO_LAUNCH: SwarmCommandKind.RETURN_TO_LAUNCH,
    CommandKind.LAND: SwarmCommandKind.LAND,
}


async def _no_answer() -> CommandResult:
    await asyncio.Future()  # never resolves; the pipeline's timeout applies
    raise AssertionError("unreachable")  # pragma: no cover


@dataclass
class _Batch:
    """Drones of one command, sent in one request."""

    drone_ids: list[int] = field(default_factory=list)
    reply: "asyncio.Future[BridgeReply | None] | None" = None


class SwarmLink:
    """The NATS connection to one swarm's bridge."""

    def __init__(self, url: str, swarm: str, clock: Clock) -> None:
        self.url = url
        self.swarm = swarm
        self._clock = clock
        self._drivers: dict[int, SwarmDriver] = {}
        self._nc: Client | None = None
        self._connecting: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._batches: dict[tuple[object, SwarmCommandKind], _Batch] = {}
        self._missions: dict[object, asyncio.Future[BridgeReply | None]] = {}
        self.heartbeat: BridgeHeartbeat | None = None
        self.heartbeat_at: datetime | None = None

    # --- drivers ---------------------------------------------------------------------------

    def driver(self, aircraft_id: str, drone_id: int) -> "SwarmDriver":
        """The driver of one drone (connects on first use)."""
        if self._connecting is None:
            self._connecting = asyncio.get_running_loop().create_task(
                self._connect(), name=f"swarm-{self.swarm}-connect"
            )
        driver = SwarmDriver(self, aircraft_id, drone_id, self._clock)
        self._drivers[drone_id] = driver
        return driver

    def release(self, driver: "SwarmDriver") -> None:
        """Forget a driver (its aircraft was unregistered or changed its link)."""
        driver.stop()
        if self._drivers.get(driver.drone_id) is driver:
            del self._drivers[driver.drone_id]

    @property
    def connected(self) -> bool:
        """True while the NATS connection is up."""
        return self._nc is not None and self._nc.is_connected

    async def close(self) -> None:
        """Stop connecting, cancel requests in flight, close the connection."""
        pending = [t for t in (self._connecting, *self._tasks) if t is not None]
        for task in pending:
            task.cancel()
        for task in pending:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._nc is not None and not self._nc.is_closed:
            await self._nc.close()
        self._nc = None

    # --- connection ------------------------------------------------------------------------

    async def _connect(self) -> None:
        """Connect, retrying until it works; nats-py reconnects (and resubscribes) after."""
        while True:
            try:
                nc = await nats.connect(
                    self.url,
                    name="fleet-service",
                    connect_timeout=2,
                    reconnect_time_wait=1,
                    max_reconnect_attempts=-1,
                    allow_reconnect=True,
                    error_cb=self._on_error,
                    disconnected_cb=self._on_disconnected,
                    reconnected_cb=self._on_reconnected,
                )
            except (OSError, NatsError, TimeoutError) as error:
                log.warning(
                    "swarm %s: NATS %s unreachable (%s); retrying", self.swarm, self.url, error
                )
                await asyncio.sleep(CONNECT_RETRY_S)
                continue
            await nc.subscribe(subject(self.swarm, "status"), cb=self._on_status)
            await nc.subscribe(subject(self.swarm, "bridge"), cb=self._on_heartbeat)
            self._nc = nc
            log.info("swarm %s: connected to NATS %s", self.swarm, self.url)
            return

    async def _on_error(self, error: Exception) -> None:
        log.warning("swarm %s: NATS error: %s", self.swarm, error)

    async def _on_disconnected(self) -> None:
        log.warning("swarm %s: NATS disconnected; reconnecting", self.swarm)

    async def _on_reconnected(self) -> None:
        log.info("swarm %s: NATS reconnected", self.swarm)

    async def _on_status(self, msg: Msg) -> None:
        try:
            status = SwarmStatus.model_validate_json(msg.data)
        except ValidationError as error:
            log.warning("swarm %s: invalid status dropped: %s", self.swarm, error)
            return
        driver = self._drivers.get(status.drone_id)
        if driver is not None:
            driver.on_status(status)

    async def _on_heartbeat(self, msg: Msg) -> None:
        try:
            self.heartbeat = BridgeHeartbeat.model_validate_json(msg.data)
        except ValidationError as error:
            log.warning("swarm %s: invalid bridge heartbeat dropped: %s", self.swarm, error)
            return
        self.heartbeat_at = self._clock.now()

    # --- requests --------------------------------------------------------------------------

    async def command(
        self, command_id: str | None, kind: SwarmCommandKind, drone_id: int
    ) -> BridgeReply | None:
        """Send ``kind`` to ``drone_id``, together with the other drones of the same command.

        None: no answer from the bridge (not connected, not running, or too slow).
        """
        key = (command_id if command_id is not None else object(), kind)
        batch = self._batches.get(key)
        if batch is None:
            batch = _Batch(reply=asyncio.get_running_loop().create_future())
            self._batches[key] = batch
            # Every drone of one command registers before the loop's next iteration.
            asyncio.get_running_loop().call_soon(self._flush, key, kind)
        batch.drone_ids.append(drone_id)
        assert batch.reply is not None  # noqa: S101 - set above
        return await asyncio.shield(batch.reply)

    def _flush(self, key: tuple[object, SwarmCommandKind], kind: SwarmCommandKind) -> None:
        batch = self._batches.pop(key)
        request = SwarmCommandRequest(kind=kind, drone_ids=sorted(set(batch.drone_ids)))
        assert batch.reply is not None  # noqa: S101
        self._spawn(self._answer(batch.reply, "command", request))

    async def mission(self, command_id: str | None, mission: AreaMission) -> BridgeReply | None:
        """Publish an area mission to the whole swarm, once per command. None: no answer."""
        key: object = command_id if command_id is not None else object()
        reply = self._missions.get(key)
        if reply is None:
            reply = asyncio.get_running_loop().create_future()
            self._missions[key] = reply
            self._spawn(self._answer(reply, "mission", _mission_request(mission)))
            asyncio.get_running_loop().call_later(MISSION_MEMORY_S, self._missions.pop, key, None)
        return await asyncio.shield(reply)

    async def _answer(
        self, reply: "asyncio.Future[BridgeReply | None]", kind: str, request: BaseModel
    ) -> None:
        answer = await self._request(kind, request)
        if not reply.done():
            reply.set_result(answer)

    async def _request(self, kind: str, request: BaseModel) -> BridgeReply | None:
        nc = self._nc
        if nc is None or not nc.is_connected:
            log.warning("swarm %s: %s not sent, NATS is not connected", self.swarm, kind)
            return None
        try:
            msg = await nc.request(
                subject(self.swarm, kind),
                request.model_dump_json().encode(),
                timeout=REQUEST_TIMEOUT_S,
            )
        except (NatsError, TimeoutError) as error:
            log.warning("swarm %s: no answer from the bridge to %s: %r", self.swarm, kind, error)
            return None
        try:
            return BridgeReply.model_validate_json(msg.data)
        except ValidationError as error:
            log.warning("swarm %s: invalid bridge reply to %s: %s", self.swarm, kind, error)
            return None

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _mission_request(mission: AreaMission) -> SwarmMissionRequest:
    def point(p: tuple[float, float]) -> WirePoint:
        return WirePoint(latitude=p[0], longitude=p[1])

    return SwarmMissionRequest(
        mission_id=mission.mission_id,
        origin=point(mission.origin),
        altitude_relative_m=mission.altitude_relative_m,
        grid_resolution_m=mission.grid_resolution_m,
        waypoints=[point(p) for p in mission.waypoints],
        area=[point(p) for p in mission.area],
    )


def sample_of(aircraft_id: str, status: SwarmStatus, ts: datetime) -> TelemetrySample:
    """A sample from a drone state: what the companion reports, the rest unknown."""
    sighting = status.survivor_sighting
    return TelemetrySample(
        aircraft_id=aircraft_id,
        ts=ts,
        source="swarm",
        latitude=status.position.latitude if status.position else None,
        longitude=status.position.longitude if status.position else None,
        altitude_amsl_m=None,
        altitude_relative_m=None,
        heading_deg=status.heading_deg,
        groundspeed_mps=status.groundspeed_mps,
        climb_rate_mps=None,
        battery_pct=None,
        battery_v=None,
        gps_fix=None,
        satellites=None,
        flight_mode=FlightMode.UNKNOWN,  # the companion does not report the autopilot's mode
        armed=None,
        in_air=None,
        home_latitude=None,
        home_longitude=None,
        swarm=SwarmState(
            drone_id=status.drone_id,
            phase=status.phase,
            health=status.health,
            faults=frozenset(status.faults),
            mission_sequence=status.mission_sequence,
            command_sequence=status.command_sequence,
            nearest_obstacle_m=status.nearest_obstacle_m,
            survivor_sighting=SurvivorSighting(
                latitude=sighting.latitude,
                longitude=sighting.longitude,
                std_m=sighting.std_m,
                stamp=datetime.fromtimestamp(sighting.stamp, UTC),
            )
            if sighting
            else None,
        ),
    )


# Decides a pending command from a drone state heard at a time: ack, nack, or not yet.
_Check = Callable[[SwarmStatus, datetime], CommandResult | None]


class SwarmDriver:
    """One swarm drone, identified by its onboard ``drone_id``."""

    source = "swarm"
    capabilities = SWARM_COMMANDS

    def __init__(self, link: SwarmLink, aircraft_id: str, drone_id: int, clock: Clock) -> None:
        self.aircraft_id = aircraft_id
        self.drone_id = drone_id
        self._link = link
        self._clock = clock
        self._sink: TelemetrySink | None = None
        self.latest: SwarmStatus | None = None
        self._waiters: list[tuple[_Check, asyncio.Future[CommandResult]]] = []

    def start(self, sink: TelemetrySink) -> None:
        """Deliver this drone's samples to ``sink``."""
        self._sink = sink

    def stop(self) -> None:
        """Stop delivering samples."""
        self._sink = None

    def on_status(self, status: SwarmStatus) -> None:
        """A state of this drone arrived from the bridge."""
        now = self._clock.now()
        self.latest = status
        if self._sink is not None:
            self._sink(sample_of(self.aircraft_id, status, now))
        for check, waiter in tuple(self._waiters):
            if not waiter.done() and (result := check(status, now)) is not None:
                waiter.set_result(result)

    async def execute(self, command: DriverCommand) -> CommandResult:
        """Send a command or a mission; ack once this drone reports it processed."""
        if command.kind is CommandKind.MISSION_START:
            return await self._start_mission(command)
        kind = _COMMAND_KINDS.get(command.kind)
        if kind is None:
            return CommandResult.nack(f"A swarm drone cannot {command.kind.value}.")
        reply = await self._link.command(command.command_id, kind, self.drone_id)
        if reply is None:
            return await _no_answer()
        if reply.sequence is None:
            return CommandResult.nack(f"The swarm bridge refused it: {reply.error}")
        sequence = reply.sequence

        def processed(status: SwarmStatus, _: datetime) -> CommandResult | None:
            return CommandResult.ack() if status.command_sequence >= sequence else None

        return await self._wait(processed)

    async def _start_mission(self, command: DriverCommand) -> CommandResult:
        if command.mission is None:  # pragma: no cover - the pipeline always attaches it
            return CommandResult.nack("No mission to start.")
        sent_at = self._clock.now()
        reply = await self._link.mission(command.command_id, command.mission)
        if reply is None:
            return await _no_answer()
        if reply.sequence is None:
            return CommandResult.nack(f"The swarm bridge refused the mission: {reply.error}")
        sequence = reply.sequence
        grace = timedelta(seconds=REJECTION_GRACE_S)

        def adopted(status: SwarmStatus, at: datetime) -> CommandResult | None:
            if status.mission_sequence >= sequence:
                return CommandResult.ack()
            if SwarmFault.MISSION_REJECTED in status.faults and at - sent_at >= grace:
                return CommandResult.nack("The drone rejected the mission (see its log).")
            return None

        return await self._wait(adopted)

    async def _wait(self, check: _Check) -> CommandResult:
        waiter: asyncio.Future[CommandResult] = asyncio.get_running_loop().create_future()
        if self.latest is not None and (result := check(self.latest, self._clock.now())):
            return result
        entry = (check, waiter)
        self._waiters.append(entry)
        try:
            return await waiter
        finally:
            self._waiters.remove(entry)


class LinkedDriver:
    """An aircraft with a MAVLink link to its autopilot and a swarm link to its companion."""

    source = "mavlink+swarm"

    def __init__(
        self, mavlink: VehicleDriver, swarm: SwarmDriver, clock: Clock, fresh_for: timedelta
    ) -> None:
        self.mavlink = mavlink
        self.swarm = swarm
        self._clock = clock
        self._fresh_for = fresh_for
        self._sink: TelemetrySink | None = None
        self._samples: dict[LinkSource, TelemetrySample] = {}

    @property
    def capabilities(self) -> frozenset[CommandKind]:
        """What either link can carry now (the swarm-only commands need the swarm link live)."""
        kinds = self.mavlink.capabilities | self.swarm.capabilities
        swarm_live = self._fresh(LinkSource.SWARM)
        return frozenset(k for k in kinds if route_command(k, swarm_live=swarm_live) is not None)

    def last_heard(self) -> dict[LinkSource, datetime | None]:
        """When each link last delivered a sample."""
        return {
            source: sample.ts if (sample := self._samples.get(source)) else None
            for source in LinkSource
        }

    def start(self, sink: TelemetrySink) -> None:
        """Deliver merged samples to ``sink``."""
        self._sink = sink
        self.mavlink.start(lambda s: self._on_sample(LinkSource.MAVLINK, s))
        self.swarm.start(lambda s: self._on_sample(LinkSource.SWARM, s))

    def stop(self) -> None:
        """Stop both links' samples."""
        self._sink = None
        self.mavlink.stop()
        self.swarm.stop()

    def _fresh(self, source: LinkSource) -> bool:
        sample = self._samples.get(source)
        return sample is not None and self._clock.now() - sample.ts <= self._fresh_for

    def _on_sample(self, source: LinkSource, sample: TelemetrySample) -> None:
        self._samples[source] = sample
        merged = merge(
            self._samples.get(LinkSource.MAVLINK),
            self._samples.get(LinkSource.SWARM),
            self._clock.now(),
            self._fresh_for,
        )
        if merged is not None and self._sink is not None:
            self._sink(merged)

    async def execute(self, command: DriverCommand) -> CommandResult:
        """Send ``command`` over the link ``route_command`` picks (ADR 0025)."""
        route = route_command(
            command.kind,
            swarm_live=self._fresh(LinkSource.SWARM),
            gcs_mission=command.gcs_mission or command.route is not None,
        )
        if route is LinkSource.SWARM:
            return await self.swarm.execute(command)
        if route is LinkSource.MAVLINK:
            return await self.mavlink.execute(command)
        return CommandResult.nack(f"{command.kind.value} needs the swarm link, which is not live.")
