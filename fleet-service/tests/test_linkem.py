"""The link emulator (sim/linkem.py) over localhost UDP."""

import asyncio
import time
from collections.abc import AsyncIterator

import pytest
from linkem import Impairment, LinkEmulator

Address = tuple[str, int]


class Endpoint(asyncio.DatagramProtocol):
    """A UDP socket that queues what it receives, with the arrival time."""

    def __init__(self) -> None:
        self.received: asyncio.Queue[tuple[bytes, Address, float]] = asyncio.Queue()
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self.transport = transport

    def datagram_received(self, data: bytes, addr: Address) -> None:
        self.received.put_nowait((data, addr, time.monotonic()))

    @property
    def address(self) -> Address:
        assert self.transport is not None
        address: Address = self.transport.get_extra_info("sockname")
        return address

    def send(self, data: bytes, to: Address) -> None:
        assert self.transport is not None
        self.transport.sendto(data, to)

    async def next(self, timeout_s: float = 1.0) -> tuple[bytes, Address, float]:
        return await asyncio.wait_for(self.received.get(), timeout_s)

    def drain(self) -> list[bytes]:
        items = []
        while not self.received.empty():
            items.append(self.received.get_nowait()[0])
        return items


async def endpoint() -> Endpoint:
    loop = asyncio.get_running_loop()
    _, protocol = await loop.create_datagram_endpoint(Endpoint, local_addr=("127.0.0.1", 0))
    return protocol


Rig = tuple[LinkEmulator, Endpoint, Endpoint, Endpoint]


@pytest.fixture
async def rig() -> AsyncIterator[Rig]:
    station, first, second = await endpoint(), await endpoint(), await endpoint()
    link = LinkEmulator(("127.0.0.1", 0), station.address)
    await link.start()
    yield link, station, first, second
    link.close()
    for end in (station, first, second):
        assert end.transport is not None
        end.transport.close()


async def test_traffic_is_relayed_both_ways_per_vehicle(rig: Rig) -> None:
    link, station, first, second = rig
    relay = ("127.0.0.1", link.port)

    first.send(b"from-1", relay)
    data_1, peer_1, _ = await station.next()
    second.send(b"from-2", relay)
    data_2, peer_2, _ = await station.next()
    station.send(b"to-1", peer_1)
    station.send(b"to-2", peer_2)

    assert (data_1, data_2) == (b"from-1", b"from-2")
    assert peer_1 != peer_2  # the station sees one peer per vehicle
    assert (await first.next())[0] == b"to-1"
    assert (await second.next())[0] == b"to-2"


async def test_a_blackout_drops_everything_until_restored(rig: Rig) -> None:
    link, station, first, _ = rig
    relay = ("127.0.0.1", link.port)
    first.send(b"hello", relay)
    _, peer, _ = await station.next()

    link.impairment = Impairment(blackout=True)
    first.send(b"lost-up", relay)
    station.send(b"lost-down", peer)
    await asyncio.sleep(0.2)
    link.impairment = Impairment()
    first.send(b"back", relay)

    assert (await station.next())[0] == b"back"
    assert station.drain() == []
    assert first.drain() == []
    assert link.counters.dropped == 2


async def test_latency_delays_delivery(rig: Rig) -> None:
    link, station, first, _ = rig
    link.impairment = Impairment(latency_s=0.3)

    sent = time.monotonic()
    first.send(b"slow", ("127.0.0.1", link.port))
    _, _, arrived = await station.next()

    assert arrived - sent >= 0.29


async def test_loss_drops_about_the_given_share(rig: Rig) -> None:
    link, station, first, _ = rig
    link.impairment = Impairment(loss=0.5)
    relay = ("127.0.0.1", link.port)

    first.send(b"open", relay)  # the vehicle's first datagram opens its uplink
    await asyncio.sleep(0.1)
    for i in range(400):
        first.send(str(i).encode(), relay)
        if i % 50 == 0:
            await asyncio.sleep(0.01)
    await asyncio.sleep(0.3)

    delivered = len(station.drain())
    assert 140 <= delivered <= 260  # 50 % of ~401, with generous statistical slack


def test_impairments_are_validated() -> None:
    with pytest.raises(ValueError, match="loss"):
        Impairment(loss=1.5)
    with pytest.raises(ValueError, match="negative"):
        Impairment(latency_s=-1)
