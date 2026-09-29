"""
A real nats-server for tests, and a fake swarm bridge that speaks the wire contract.

The server binary is found through ``NATS_SERVER_BIN``, then ``PATH``, then the repo's
``.tools/nats/`` (docs/runbooks/dev-setup.md). Without it the NATS tests are skipped,
unless ``SARGCS_REQUIRE_NATS=1`` (CI, and ``scripts/check.py`` when it finds the binary),
where a missing server fails them instead of hiding them.

The fake bridge answers requests like ``src/sar_gcs_bridge`` does and simulates its
drones: a command reaches the addressed drones (their ``command_sequence`` catches up and
the phase follows), a mission is adopted by every drone, or rejected. It can also be told
to refuse, or to stay silent.
"""

import asyncio
import contextlib
import os
import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import nats
import pytest
from nats.aio.client import Client
from nats.aio.msg import Msg

from fleet_service.domain.enums import SwarmFault, SwarmHealth, SwarmPhase
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

REPO = Path(__file__).resolve().parents[2]
STATUS_PERIOD_S = 0.2


def nats_server_binary() -> str | None:
    """Path of a nats-server executable, or None."""
    for candidate in (
        os.environ.get("NATS_SERVER_BIN"),
        shutil.which("nats-server"),
        str(REPO / ".tools" / "nats" / "nats-server.exe"),
        str(REPO / ".tools" / "nats" / "nats-server"),
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def require_nats_server() -> str:
    """The binary, or skip (fail if SARGCS_REQUIRE_NATS=1)."""
    binary = nats_server_binary()
    if binary is None:
        message = "nats-server not found (NATS_SERVER_BIN, PATH or .tools/nats)"
        if os.environ.get("SARGCS_REQUIRE_NATS") == "1":
            pytest.fail(message)
        pytest.skip(message)
    return binary


def free_tcp_port() -> int:
    """A TCP port nobody is listening on right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


class NatsServer:
    """One nats-server process on a fixed local port, which can be stopped and restarted."""

    def __init__(self, binary: str, port: int) -> None:
        self.binary = binary
        self.port = port
        self.url = f"nats://127.0.0.1:{port}"
        self._process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        """Start the server and wait until it accepts connections."""
        self._process = subprocess.Popen(  # noqa: S603 - our own test binary
            [self.binary, "-a", "127.0.0.1", "-p", str(self.port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError(f"nats-server did not start on port {self.port}")

    def stop(self) -> None:
        """Stop the server (idempotent)."""
        if self._process is not None:
            self._process.terminate()
            self._process.wait(timeout=10)
            self._process = None


@dataclass
class FakeDrone:
    """What the fake bridge reports for one drone."""

    drone_id: int
    latitude: float
    longitude: float
    phase: SwarmPhase = SwarmPhase.STANDBY
    faults: set[SwarmFault] = field(default_factory=set)
    mission_sequence: int = 0
    command_sequence: int = 0
    heard: bool = True  # False: the bridge stops publishing it

    def status(self) -> SwarmStatus:
        now = time.time()
        return SwarmStatus(
            drone_id=self.drone_id,
            stamp=now,
            received_at=now,
            phase=self.phase,
            health=SwarmHealth.OK,
            faults=sorted(self.faults),
            mission_sequence=self.mission_sequence,
            command_sequence=self.command_sequence,
            position=WirePoint(latitude=self.latitude, longitude=self.longitude),
            heading_deg=90.0,
            groundspeed_mps=2.5,
            velocity_north_mps=0.0,
            velocity_east_mps=2.5,
            nearest_obstacle_m=None,
            survivor_sighting=None,
        )


_AFTER_COMMAND = {
    SwarmCommandKind.HOLD: SwarmPhase.HOLD,
    SwarmCommandKind.RESUME: SwarmPhase.SEARCH,
}


class FakeBridge:
    """Answers the station's requests and publishes drone states, like the real bridge."""

    def __init__(self, url: str, swarm: str = "default") -> None:
        self.url = url
        self.swarm = swarm
        self.drones: dict[int, FakeDrone] = {}
        self.commands: list[SwarmCommandRequest] = []
        self.missions: list[SwarmMissionRequest] = []
        self.refuse: str | None = None  # an error for every request
        self.silent = False  # never reply
        self.reject_missions = False  # drones refuse missions (the mission_rejected fault)
        self._sequence = 0
        self._nc: Client | None = None
        self._task: asyncio.Task[None] | None = None

    def add(self, drone_id: int, latitude: float = 47.3977, longitude: float = 8.5456) -> None:
        """Simulate a drone."""
        self.drones[drone_id] = FakeDrone(drone_id, latitude, longitude)

    async def start(self) -> None:
        """Connect, answer requests, publish states every STATUS_PERIOD_S."""
        self._nc = await nats.connect(
            self.url, max_reconnect_attempts=-1, reconnect_time_wait=0.2, name="fake-bridge"
        )
        await self._nc.subscribe(subject(self.swarm, "command"), cb=self._on_command)
        await self._nc.subscribe(subject(self.swarm, "mission"), cb=self._on_mission)
        self._task = asyncio.get_running_loop().create_task(self._publish())

    async def close(self) -> None:
        """Stop publishing and disconnect."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._nc is not None:
            await self._nc.close()

    def _next_sequence(self) -> int:
        self._sequence = max(int(time.time() * 1000), self._sequence + 1)
        return self._sequence

    async def _reply(self, msg: Msg, sequence: int | None) -> None:
        if self.silent:
            return
        reply = BridgeReply(error=self.refuse) if self.refuse else BridgeReply(sequence=sequence)
        await msg.respond(reply.model_dump_json().encode())

    async def _on_command(self, msg: Msg) -> None:
        request = SwarmCommandRequest.model_validate_json(msg.data)
        self.commands.append(request)
        if self.refuse or self.silent:
            await self._reply(msg, None)
            return
        sequence = self._next_sequence()
        await self._reply(msg, sequence)
        for drone in self.drones.values():  # like the onboard protocol: every drone hears it
            drone.command_sequence = max(drone.command_sequence, sequence)
            if drone.drone_id in request.drone_ids and request.kind in _AFTER_COMMAND:
                drone.phase = _AFTER_COMMAND[request.kind]

    async def _on_mission(self, msg: Msg) -> None:
        request = SwarmMissionRequest.model_validate_json(msg.data)
        self.missions.append(request)
        if self.refuse or self.silent:
            await self._reply(msg, None)
            return
        sequence = self._next_sequence()
        await self._reply(msg, sequence)
        for drone in self.drones.values():
            if self.reject_missions:
                drone.faults.add(SwarmFault.MISSION_REJECTED)
            else:
                drone.mission_sequence, drone.phase = sequence, SwarmPhase.TRANSIT

    async def _publish(self) -> None:
        assert self._nc is not None
        while True:
            if self._nc.is_connected:
                for drone in self.drones.values():
                    if drone.heard:
                        payload = drone.status().model_dump_json().encode()
                        await self._nc.publish(subject(self.swarm, "status"), payload)
                heartbeat = BridgeHeartbeat(
                    bridge_version="fake",
                    swarm=self.swarm,
                    stamp=time.time(),
                    drones_heard=sorted(self.drones),
                )
                await self._nc.publish(
                    subject(self.swarm, "bridge"), heartbeat.model_dump_json().encode()
                )
            await asyncio.sleep(STATUS_PERIOD_S)


@asynccontextmanager
async def fake_bridge(url: str) -> AsyncIterator[FakeBridge]:
    """A running fake bridge."""
    bridge = FakeBridge(url)
    await bridge.start()
    try:
        yield bridge
    finally:
        await bridge.close()
