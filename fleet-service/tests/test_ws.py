"""
The WebSocket API (ADR 0013, ADR 0020). Every server message a test receives is validated
against its model in the AsyncAPI registry (``api.ws_messages``).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx_ws import AsyncWebSocketSession, WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from fleet_service.api import ws as ws_module
from fleet_service.api.ws_messages import server_model
from fleet_service.bus import ALERTS
from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.domain.enums import Role
from live_support import Sim, register, take

from support import FakeClock, login

URL = "http://test/api/v1/ws"
MAX_MESSAGE = 1 << 20


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(station_name="test-station", data_dir=data_dir, simulation=True)


@asynccontextmanager
async def socket(app: FastAPI) -> AsyncIterator[AsyncWebSocketSession]:
    """An unauthenticated WebSocket to the app (created in the test's own task: the
    transport's task group must be entered and exited by the same task)."""
    transport = ASGIWebSocketTransport(app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as http,
        aconnect_ws(
            URL, http, max_message_size_bytes=MAX_MESSAGE, session_class=AsyncWebSocketSession
        ) as ws,
    ):
        yield ws


async def drain_until_closed(ws: AsyncWebSocketSession) -> None:
    """Receive until the server closes the socket (raises WebSocketDisconnect)."""
    for _ in range(100):
        await ws.receive_json(timeout=2)


@asynccontextmanager
async def connected(app: FastAPI, token: str) -> AsyncIterator[AsyncWebSocketSession]:
    """An authenticated WebSocket (the welcome message already consumed)."""
    async with socket(app) as ws:
        await ws.send_json({"type": "auth", "token": token})
        welcome = await recv(ws)
        assert welcome["type"] == "welcome"
        yield ws


@pytest.fixture
def sim(app: FastAPI, clock: FakeClock) -> Sim:
    context: AppContext = app.state.context
    return Sim(context.runtime(), clock)


@pytest.fixture
async def token(client: httpx.AsyncClient, user_ids: dict[Role, str]) -> str:
    return await login(client, "operator")


async def recv(ws: AsyncWebSocketSession, wait_s: float = 2.0) -> dict[str, Any]:
    """Receive one server message and check it against the protocol."""
    message: dict[str, Any] = await ws.receive_json(timeout=wait_s)
    server_model(message["type"], message.get("topic")).model_validate(message)
    return message


async def recv_until(
    ws: AsyncWebSocketSession, type_: str, topic: str | None = None, wait_s: float = 3.0
) -> dict[str, Any]:
    """Receive until a message of the given type (and topic) arrives."""
    for _ in range(50):
        message = await recv(ws, wait_s)
        if message["type"] == type_ and (topic is None or message.get("topic") == topic):
            return message
    raise AssertionError(f"no {type_} {topic} message")


async def test_welcome_after_auth(app: FastAPI, client: httpx.AsyncClient, token: str) -> None:
    async with socket(app) as ws:
        await ws.send_json({"type": "auth", "token": token})
        welcome = await recv(ws)

    assert welcome["seq"] == 1
    assert welcome["user"]["username"] == "operator"
    assert welcome["role"] == "operator"
    assert "aircraft.command" in welcome["permissions"]
    assert welcome["simulation"] is True


@pytest.mark.parametrize(
    ("first", "code"),
    [
        ({"type": "auth", "token": "sgcs_forged"}, 4401),
        ({"type": "ping"}, 4400),
        ({"type": "subscribe", "topics": ["alerts"]}, 4400),
    ],
)
async def test_the_first_message_must_authenticate(
    app: FastAPI, client: httpx.AsyncClient, first: dict[str, Any], code: int
) -> None:
    async with socket(app) as ws:
        await ws.send_json(first)
        with pytest.raises(WebSocketDisconnect) as closed:
            await ws.receive_json(timeout=2)

    assert closed.value.code == code


async def test_silence_before_auth_closes_the_socket(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ws_module, "AUTH_TIMEOUT_S", 0.1)

    async with socket(app) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            await ws.receive_json(timeout=2)

    assert closed.value.code == 4408


async def test_subscribe_sends_a_snapshot_per_topic(
    app: FastAPI, client: httpx.AsyncClient, token: str, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    await register(client, auth[Role.SUPERVISOR], "HX-1")
    await sim.fly(0.5)

    async with connected(app, token) as ws:
        await ws.send_json(
            {"type": "subscribe", "topics": ["fleet.telemetry", "alerts", "commands", "control"]}
        )
        snapshots = [await recv(ws) for _ in range(4)]

    assert [(m["type"], m["topic"]) for m in snapshots] == [
        ("snapshot", "fleet.telemetry"),
        ("snapshot", "alerts"),
        ("snapshot", "commands"),
        ("snapshot", "control"),
    ]
    assert [m["seq"] for m in snapshots] == [2, 3, 4, 5]
    assert snapshots[0]["data"]["aircraft"][0]["callsign"] == "HX-1"


async def test_telemetry_is_coalesced_to_the_newest_state(
    app: FastAPI, client: httpx.AsyncClient, token: str, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    ids = [await register(client, auth[Role.SUPERVISOR], name) for name in ("HX-1", "HX-2")]

    async with connected(app, token) as ws:
        await ws.send_json({"type": "subscribe", "topics": ["fleet.telemetry"], "telemetry_hz": 10})
        await recv(ws)  # snapshot
        for _ in range(30):  # 3 s of simulation, far faster than the 10 Hz batches
            sim.clock.advance(seconds=0.1)
            sim.runtime.step_simulation(0.1)
        batch = await recv_until(ws, "event", "fleet.telemetry")

    aircraft = batch["data"]["aircraft"]
    assert sorted(a["aircraft_id"] for a in aircraft) == sorted(ids)  # each once, not 30 times
    assert all(a["link"] == "live" for a in aircraft)


async def test_reliable_topics_deliver_every_change(
    app: FastAPI, client: httpx.AsyncClient, token: str, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    hexa = await register(client, auth[Role.SUPERVISOR], "HX-1")
    await sim.fly(0.5)

    async with connected(app, token) as ws:
        await ws.send_json({"type": "subscribe", "topics": ["alerts", "commands", "control"]})
        for _ in range(3):
            await recv(ws)
        await take(client, auth[Role.OPERATOR], hexa)
        control = await recv_until(ws, "event", "control")
        await client.post(
            "/api/v1/commands",
            json={
                "command_id": "0b6f8f2e-0000-4000-8000-000000000001",
                "kind": "hold",
                "aircraft_ids": [hexa],
            },
            headers=auth[Role.OPERATOR],
        )
        command = await recv_until(ws, "event", "commands")
        assert sim.runtime.simulator is not None
        sim.runtime.simulator.drivers[hexa].inject(battery_pct=20.0)
        await sim.fly(0.5)
        alert = await recv_until(ws, "event", "alerts")

    assert control["data"]["change"] == "control.take"
    assert control["data"]["lease"]["holder"]["username"] == "operator"
    assert command["data"]["kind"] == "hold"
    assert alert["data"]["kind"] == "battery_low"


async def test_unsubscribe_stops_telemetry(
    app: FastAPI, client: httpx.AsyncClient, token: str, auth: dict[Role, dict[str, str]], sim: Sim
) -> None:
    await register(client, auth[Role.SUPERVISOR], "HX-1")

    async with connected(app, token) as ws:
        await ws.send_json({"type": "subscribe", "topics": ["fleet.telemetry"], "telemetry_hz": 10})
        await recv(ws)
        await ws.send_json({"type": "unsubscribe", "topics": ["fleet.telemetry"]})
        await ws.send_json({"type": "ping"})
        await recv_until(ws, "pong")  # the unsubscribe has been processed
        sim.runtime.step_simulation(0.1)
        await ws.send_json({"type": "ping"})
        after = await recv(ws, wait_s=1.0)

    assert after["type"] == "pong"  # no telemetry arrived in between


async def test_ping_answers_and_counts_as_presence(
    app: FastAPI, client: httpx.AsyncClient, token: str, user_ids: dict[Role, str], sim: Sim
) -> None:
    async with connected(app, token) as ws:
        sim.clock.advance(seconds=45)
        await ws.send_json({"type": "ping"})
        pong = await recv(ws)

    assert pong["type"] == "pong"
    assert sim.runtime.presence.last_seen(user_ids[Role.OPERATOR]) == sim.clock.now()


async def test_invalid_messages_get_an_error_and_the_socket_stays(
    app: FastAPI, client: httpx.AsyncClient, token: str
) -> None:
    async with connected(app, token) as ws:
        await ws.send_json({"type": "subscribe", "topics": ["weather"]})
        error = await recv(ws)
        await ws.send_json({"type": "ping"})
        pong = await recv(ws)

    assert error["type"] == "error"
    assert error["code"] == "invalid-message"
    assert pong["type"] == "pong"


async def test_logout_ends_the_socket_of_that_session(
    app: FastAPI, client: httpx.AsyncClient, token: str
) -> None:
    async with connected(app, token) as ws:
        await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        ended = await recv(ws)
        with pytest.raises(WebSocketDisconnect) as closed:
            await ws.receive_json(timeout=2)

    assert ended["type"] == "session_ended"
    assert closed.value.code == 4401


async def test_deactivating_a_user_ends_their_sockets(
    app: FastAPI,
    client: httpx.AsyncClient,
    token: str,
    auth: dict[Role, dict[str, str]],
    user_ids: dict[Role, str],
) -> None:
    async with connected(app, token) as ws:
        await client.patch(
            f"/api/v1/users/{user_ids[Role.OPERATOR]}",
            json={"is_active": False},
            headers=auth[Role.ADMIN],
        )
        ended = await recv(ws)

    assert ended["type"] == "session_ended"


async def test_a_client_that_cannot_keep_up_is_closed_not_skipped(
    app: FastAPI, client: httpx.AsyncClient, token: str, sim: Sim, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ws_module, "RELIABLE_QUEUE", 3)

    async with connected(app, token) as ws:
        await ws.send_json({"type": "subscribe", "topics": ["alerts"]})
        await recv(ws)
        for i in range(10):  # published faster than the socket drains them
            sim.runtime.bus.publish(ALERTS, {"not": "delivered"}, key=str(i))
        with pytest.raises(WebSocketDisconnect) as closed:
            await drain_until_closed(ws)

    assert closed.value.code == 4429


async def test_silent_clients_are_closed(
    app: FastAPI, client: httpx.AsyncClient, token: str, sim: Sim, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ws_module, "SESSION_CHECK_S", 0.05)

    async with connected(app, token) as ws:
        sim.clock.advance(seconds=31)
        with pytest.raises(WebSocketDisconnect) as closed:
            await ws.receive_json(timeout=2)

    assert closed.value.code == 4408
