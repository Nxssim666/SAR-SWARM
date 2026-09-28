"""
Link emulator: a UDP relay between aircraft and the ground station that can lose,
delay and cut MAVLink traffic, to test how the station and the aircraft behave on a bad
or dead radio link (ADR 0023). Standard library only.

Vehicles send to the ``listen`` port as if it were the ground station; each vehicle gets
its own socket towards the ``forward`` address, so the station sees one peer per vehicle
and its replies find their way back (like a NAT). The impairment applies to both
directions and can be changed while running::

    python sim/linkem.py --listen 14544 --forward 127.0.0.1:24544 --loss 0.2 --latency-ms 300

or from Python (tests)::

    async with LinkEmulator(("127.0.0.1", 14544), ("127.0.0.1", 24544)) as link:
        link.impairment = Impairment(blackout=True)
"""

import argparse
import asyncio
import contextlib
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType

Address = tuple[str, int]
Handler = Callable[[bytes, Address], None]


@dataclass(frozen=True)
class Impairment:
    """What happens to each datagram, in both directions."""

    loss: float = 0.0  # probability of dropping a datagram, 0..1
    latency_s: float = 0.0
    jitter_s: float = 0.0  # latency varies uniformly by up to this much either way
    blackout: bool = False  # drop everything

    def __post_init__(self) -> None:
        if not 0.0 <= self.loss <= 1.0:
            raise ValueError("loss must be between 0 and 1")
        if self.latency_s < 0 or self.jitter_s < 0:
            raise ValueError("latency and jitter must not be negative")


@dataclass
class Counters:
    """Datagrams relayed and dropped, per direction."""

    up: int = 0  # vehicle -> station
    down: int = 0  # station -> vehicle
    dropped: int = 0


class _Receiver(asyncio.DatagramProtocol):
    def __init__(self, on_datagram: Handler) -> None:
        self._on_datagram = on_datagram

    def datagram_received(self, data: bytes, addr: Address) -> None:
        self._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        pass  # ICMP unreachable while the other side is not listening yet: a radio would not care


@dataclass
class LinkEmulator:
    """The relay; use as an async context manager or call ``start``/``close``."""

    listen: Address
    forward: Address
    impairment: Impairment = field(default_factory=Impairment)
    seed: int = 0
    counters: Counters = field(default_factory=Counters)

    def __post_init__(self) -> None:
        self._random = random.Random(self.seed)  # noqa: S311 - emulation, not security
        self._vehicles: asyncio.DatagramTransport | None = None
        self._uplinks: dict[Address, asyncio.DatagramTransport] = {}
        # Vehicles whose uplink socket is being opened, with what they sent meanwhile: one
        # socket per vehicle however fast its first datagrams arrive.
        self._opening: dict[Address, list[bytes]] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._pending: set[asyncio.TimerHandle] = set()

    async def __aenter__(self) -> "LinkEmulator":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    async def start(self) -> None:
        """Open the vehicle-facing port."""
        loop = asyncio.get_running_loop()
        self._vehicles, _ = await loop.create_datagram_endpoint(
            lambda: _Receiver(self._from_vehicle), local_addr=self.listen
        )

    def close(self) -> None:
        """Close every socket; datagrams in flight are dropped."""
        for task in self._tasks:
            task.cancel()  # a cancelled create_datagram_endpoint closes its own socket
        self._tasks.clear()
        self._opening.clear()
        for handle in self._pending:
            handle.cancel()
        self._pending.clear()
        for transport in self._uplinks.values():
            transport.close()
        self._uplinks.clear()
        if self._vehicles is not None:
            self._vehicles.close()
            self._vehicles = None

    @property
    def uplink_count(self) -> int:
        """Station-facing sockets open, one per vehicle heard."""
        return len(self._uplinks)

    @property
    def port(self) -> int:
        """The vehicle-facing port actually bound (useful with port 0)."""
        assert self._vehicles is not None  # noqa: S101
        port: int = self._vehicles.get_extra_info("sockname")[1]
        return port

    def _from_vehicle(self, data: bytes, vehicle: Address) -> None:
        uplink = self._uplinks.get(vehicle)
        if uplink is not None:
            self._relay(data, lambda: uplink.sendto(data, self.forward), up=True)
            return
        backlog = self._opening.get(vehicle)
        if backlog is not None:
            backlog.append(data)
            return
        self._opening[vehicle] = [data]
        task = asyncio.get_running_loop().create_task(self._open_uplink(vehicle))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _open_uplink(self, vehicle: Address) -> None:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _Receiver(lambda data, _addr: self._from_station(data, vehicle)),
            local_addr=(self.listen[0], 0),
        )
        if self._vehicles is None:  # closed meanwhile
            transport.close()
            return
        self._uplinks[vehicle] = transport
        for data in self._opening.pop(vehicle, []):
            self._from_vehicle(data, vehicle)

    def _from_station(self, data: bytes, vehicle: Address) -> None:
        vehicles = self._vehicles
        if vehicles is not None:
            self._relay(data, lambda: vehicles.sendto(data, vehicle), up=False)

    def _relay(self, data: bytes, send: Callable[[], None], *, up: bool) -> None:
        impairment = self.impairment
        if impairment.blackout or self._random.random() < impairment.loss:
            self.counters.dropped += 1
            return
        if up:
            self.counters.up += 1
        else:
            self.counters.down += 1
        delay = impairment.latency_s + self._random.uniform(-1, 1) * impairment.jitter_s
        if delay <= 0:
            send()
            return
        loop = asyncio.get_running_loop()

        def deliver() -> None:
            self._pending.discard(handle)
            send()

        handle = loop.call_later(delay, deliver)
        self._pending.add(handle)


def _address(text: str) -> Address:
    host, _, port = text.rpartition(":")
    return host or "127.0.0.1", int(port)


async def _serve(arguments: argparse.Namespace) -> None:
    impairment = Impairment(
        loss=arguments.loss,
        latency_s=arguments.latency_ms / 1000,
        jitter_s=arguments.jitter_ms / 1000,
    )
    listen = (arguments.bind, arguments.listen)
    async with LinkEmulator(listen, _address(arguments.forward), impairment) as link:
        print(f"linkem: {listen[0]}:{link.port} <-> {arguments.forward} ({impairment})")  # noqa: T201
        if arguments.blackout_after is not None:
            await asyncio.sleep(arguments.blackout_after)
            link.impairment = Impairment(blackout=True)
            print(f"linkem: blackout for {arguments.blackout_for} s")  # noqa: T201
            await asyncio.sleep(arguments.blackout_for)
            link.impairment = impairment
            print("linkem: link restored")  # noqa: T201
        await asyncio.Event().wait()


def main() -> None:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--listen", type=int, required=True, help="port the vehicles send to")
    parser.add_argument("--bind", default="127.0.0.1", help="interface of the listen port")
    parser.add_argument("--forward", required=True, help="ground station host:port")
    parser.add_argument("--loss", type=float, default=0.0, help="drop probability, 0..1")
    parser.add_argument("--latency-ms", type=float, default=0.0)
    parser.add_argument("--jitter-ms", type=float, default=0.0)
    parser.add_argument("--blackout-after", type=float, help="cut the link after N seconds")
    parser.add_argument("--blackout-for", type=float, default=30.0, help="for N seconds")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_serve(parser.parse_args()))


if __name__ == "__main__":
    main()
