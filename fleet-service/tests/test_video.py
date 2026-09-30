"""Video health from the relay (M5, ADR 0012): live, stalled, offline, unknown, and the
video_down alert; the view ticket and its audit."""

from datetime import timedelta

import httpx
import pytest

from fleet_service.context import AppContext
from fleet_service.domain.enums import AlertKind, AlertSeverity, Role
from fleet_service.services.alerts import Condition
from fleet_service.services.video import (
    RelayChange,
    RelayPath,
    StreamInfo,
    StreamState,
    VideoMonitor,
    parse_paths,
    plan_reconcile,
)

from factories import aircraft
from support import START, FakeClock

STREAM = StreamInfo("s1", "HX-1 camera", "aircraft-01", "a1", True)


class Relay:
    """A stand-in relay: paths the test sets, or unreachable."""

    def __init__(self) -> None:
        self.paths: list[RelayPath] = []
        self.reachable = True

    async def fetch(self) -> list[RelayPath]:
        if not self.reachable:
            raise httpx.ConnectError("refused")
        return list(self.paths)


def path(received: int, ready: bool = True) -> RelayPath:
    return RelayPath("aircraft-01", ready, received, 2)


@pytest.fixture
def relay() -> Relay:
    return Relay()


@pytest.fixture
def monitor(relay: Relay) -> VideoMonitor:
    m = VideoMonitor(relay.fetch, stall_after_s=3.0, down_after_s=5.0)
    m.set_streams([STREAM])
    return m


def test_the_relays_paths_are_read_whatever_the_version_calls_its_fields() -> None:
    document = {
        "items": [
            {"name": "a", "ready": True, "bytesReceived": 1000, "readers": [{}, {}]},
            {"name": "b", "online": True, "inboundBytes": 5},  # newer names
            {"name": "c"},
            {"ready": True},  # no name: ignored
        ]
    }

    assert parse_paths(document) == [
        RelayPath("a", True, 1000, 2),
        RelayPath("b", True, 5, None),
        RelayPath("c", False, None, None),
    ]


async def test_a_stream_is_live_while_data_arrives_and_stalls_when_it_stops(
    relay: Relay, monitor: VideoMonitor
) -> None:
    now = START
    for received in (1_000, 26_000, 51_000):
        relay.paths = [path(received)]
        await monitor.poll(now)
        now += timedelta(seconds=2)
    live = monitor.health("s1")

    for _ in range(3):  # the same byte count: a frozen picture
        await monitor.poll(now)
        now += timedelta(seconds=2)
    stalled = monitor.health("s1")

    assert live.state is StreamState.LIVE
    assert live.bitrate_kbps == pytest.approx(100.0)  # 25 kB in 2 s
    assert live.readers == 2
    assert stalled.state is StreamState.STALLED


@pytest.mark.parametrize(
    ("paths", "reachable", "state"),
    [
        ([], True, StreamState.OFFLINE),  # the relay has no such path
        ([RelayPath("aircraft-01", False, 0, 0)], True, StreamState.OFFLINE),  # not ready
        ([RelayPath("aircraft-01", True, 10, 0)], False, StreamState.UNKNOWN),  # no answer
    ],
)
async def test_offline_and_unknown_are_never_live(
    relay: Relay,
    monitor: VideoMonitor,
    paths: list[RelayPath],
    reachable: bool,
    state: StreamState,
) -> None:
    relay.paths, relay.reachable = paths, reachable

    await monitor.poll(START)

    assert monitor.health("s1").state is state


async def test_video_down_is_raised_after_five_seconds_not_live_and_only_for_enabled_streams(
    relay: Relay, monitor: VideoMonitor
) -> None:
    disabled = StreamInfo("s2", "Spare", "aircraft-02", None, False)
    monitor.set_streams([STREAM, disabled])
    relay.paths = []
    await monitor.poll(START)
    early = monitor.conditions(START + timedelta(seconds=4))
    await monitor.poll(START + timedelta(seconds=6))
    late = monitor.conditions(START + timedelta(seconds=6))

    assert early == []
    assert [(c.kind, c.aircraft_id, c.key) for c in late] == [
        (AlertKind.VIDEO_DOWN, "a1", "video_down:s1")
    ]
    assert "no video" in late[0].message


def test_an_unpolled_stream_is_unknown(monitor: VideoMonitor) -> None:
    assert monitor.health("s1").state is StreamState.UNKNOWN
    assert monitor.conditions(START + timedelta(hours=1)) == []  # nothing known yet


async def _stream(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    relay_path: str = "aircraft-09",
    **fields: object,
) -> str:
    plane = await aircraft(client, headers, f"HX-{relay_path[-2:]}")
    body = {
        "aircraft_id": plane["id"],
        "name": "HX-9 camera",
        "source_url": "rtsp://cam:secret@10.0.0.9/stream",
        "relay_path": relay_path,
    } | fields
    response = await client.post("/api/v1/video-streams", json=body, headers=headers)
    assert response.status_code == 201, response.text
    stream_id: str = response.json()["id"]
    return stream_id


async def test_health_without_a_relay_says_unmonitored_and_unknown(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]]
) -> None:
    stream_id = await _stream(client, auth[Role.SUPERVISOR])

    health = (await client.get("/api/v1/video-health", headers=auth[Role.OBSERVER])).json()

    assert health["monitored"] is False
    assert [(s["stream_id"], s["state"]) for s in health["streams"]] == [(stream_id, "unknown")]


async def test_viewing_answers_where_to_play_and_is_audited(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], clock: FakeClock
) -> None:
    stream_id = await _stream(client, auth[Role.SUPERVISOR])
    disabled = await _stream(
        client, auth[Role.SUPERVISOR], relay_path="aircraft-10", enabled=False, aircraft_id=None
    )

    ticket = await client.post(
        f"/api/v1/video-streams/{stream_id}/view", headers=auth[Role.OBSERVER]
    )
    refused = await client.post(
        f"/api/v1/video-streams/{disabled}/view", headers=auth[Role.OBSERVER]
    )
    log = await client.get(
        "/api/v1/audit", params={"action": "video.view"}, headers=auth[Role.SUPERVISOR]
    )

    assert ticket.json() == {
        "stream_id": stream_id,
        "name": "HX-9 camera",
        "whep_url": "/video/webrtc/aircraft-09/whep",
        "hls_url": "/video/hls/aircraft-09/index.m3u8",
    }
    assert refused.status_code == 409
    [event] = log.json()["items"]
    assert event["actor_username"] == "observer"
    assert event["entity_id"] == stream_id
    assert "secret" not in str(event)  # the camera password never reaches the audit


def test_the_relay_is_told_where_each_enabled_stream_comes_from() -> None:
    cam = "rtsp://cam:secret@10.0.0.9/stream"
    streams = [
        StreamInfo("s1", "new", "p-new", None, True, cam),
        StreamInfo("s2", "moved", "p-moved", None, True, cam),
        StreamInfo("s3", "same", "p-same", None, True, cam),
        StreamInfo("s4", "off", "p-off", None, False, cam),
        StreamInfo("s5", "mock", "p-mock", None, True, cam),
        StreamInfo("s6", "off, not ours", "p-manual", None, False, cam),
    ]
    configured = {
        "p-moved": "rtsp://10.0.0.1/old",
        "p-same": cam,
        "p-off": cam,
        "p-mock": "publisher",  # pushed or made by the relay itself: never touched
        "p-manual": "rtsp://10.0.0.7/other",  # someone else's: never deleted
        "p-unknown": "rtsp://10.0.0.8/x",  # not registered: left alone
    }

    changes = plan_reconcile(streams, configured)

    assert changes == [
        RelayChange("add", "p-new", cam),
        RelayChange("replace", "p-moved", cam),
        RelayChange("delete", "p-off"),
    ]


async def test_video_down_clears_when_the_stream_is_back(
    context: AppContext, clock: FakeClock
) -> None:
    """A bug found in M6: video_down was not a condition kind, so it never cleared."""
    runtime = context.runtime()
    down = Condition(AlertKind.VIDEO_DOWN, AlertSeverity.WARNING, None, "no video", "s1")

    async with context.database().ops_session() as db:
        await runtime.alerts.evaluate(db, clock.now(), runtime.registry, [], [down])
        raised = {a.kind for a in runtime.alerts.open_alerts()}
        clock.advance(seconds=10)
        await runtime.alerts.evaluate(db, clock.now(), runtime.registry, [], [])
        after = {a.kind for a in runtime.alerts.open_alerts()}

    assert AlertKind.VIDEO_DOWN in raised
    assert AlertKind.VIDEO_DOWN not in after
