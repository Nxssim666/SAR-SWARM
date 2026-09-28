"""
The real background loops (the only test with real time, ~3 s): 50 simulated aircraft,
one console at 4 Hz, history recorded by the recorder loop.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx_ws import AsyncWebSocketSession, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport
from sqlalchemy import func, select

from fleet_service.auth.passwords import fast_passwords_for_tests
from fleet_service.config import Settings
from fleet_service.context import AppContext
from fleet_service.db.models import TelemetrySample
from fleet_service.domain.enums import Role
from fleet_service.main import create_app

from support import insert_user, login

AIRCRAFT = 50


@pytest.fixture
async def live_app(data_dir: Path) -> AsyncIterator[FastAPI]:
    settings = Settings(data_dir=data_dir, simulation=True)
    application = create_app(settings, passwords=fast_passwords_for_tests(), start_loops=True)
    async with application.router.lifespan_context(application):
        yield application


async def test_loops_stream_fifty_aircraft_and_record_history(live_app: FastAPI) -> None:
    context: AppContext = live_app.state.context
    await insert_user(context, "chief", Role.SUPERVISOR)
    transport = ASGIWebSocketTransport(live_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        token = await login(http, "chief")
        headers = {"Authorization": f"Bearer {token}"}
        for i in range(AIRCRAFT):
            response = await http.post(
                "/api/v1/aircraft",
                json={"callsign": f"SIM-{i:02d}", "airframe": "multirotor_quad"},
                headers=headers,
            )
            assert response.status_code == 201
        async with aconnect_ws(
            "http://test/api/v1/ws",
            http,
            max_message_size_bytes=1 << 22,
            session_class=AsyncWebSocketSession,
        ) as ws:
            await ws.send_json({"type": "auth", "token": token})
            await ws.receive_json(timeout=2)
            await ws.send_json(
                {"type": "subscribe", "topics": ["fleet.telemetry"], "telemetry_hz": 4}
            )
            snapshot = await ws.receive_json(timeout=2)
            seen: set[str] = set()
            batches = 0
            started = time.monotonic()
            while time.monotonic() - started < 2.5:
                message = await ws.receive_json(timeout=2)
                if message["type"] == "event":
                    batches += 1
                    seen |= {a["aircraft_id"] for a in message["data"]["aircraft"]}

    assert len(snapshot["data"]["aircraft"]) == AIRCRAFT
    assert len(seen) == AIRCRAFT
    assert 6 <= batches <= 12  # 4 Hz for 2.5 s: coalesced, not 500 messages a second
    await asyncio.sleep(1.1)  # at least one more recorder pass
    async with context.database().telemetry_session() as db:
        rows = await db.scalar(select(func.count()).select_from(TelemetrySample))
    assert (rows or 0) >= AIRCRAFT
