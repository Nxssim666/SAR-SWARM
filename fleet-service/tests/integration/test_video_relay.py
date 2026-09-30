"""
The fleet service against the real video relay (M5, ADR 0012): MediaMTX of
``sim/video/compose.yaml``. Runs only with ``SARGCS_VIDEO=1``.

A registered stream makes the service add the relay path (pulling from its source); the
stream goes live; disabling it removes the path; a missing source is a video_down alert.
"""

import os
from typing import Any

import httpx
import pytest

from fleet_service.config import Settings
from link_support import Station, until

pytestmark = [
    pytest.mark.video,
    pytest.mark.skipif(
        os.environ.get("SARGCS_VIDEO") != "1", reason="needs the mock video relay: SARGCS_VIDEO=1"
    ),
]

API = "http://127.0.0.1:9997"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"mediamtx_api_url": API, "video_poll_interval_s": 1.0, "mavlink_links": False}
    )


async def _configured() -> dict[str, str]:
    async with httpx.AsyncClient() as http:
        items = (await http.get(f"{API}/v3/config/paths/list")).json()["items"]
    return {i["name"]: i["source"] for i in items}


async def _health(station: Station, stream_id: str) -> dict[str, Any]:
    response = await station.client.get("/api/v1/video-health", headers=station.headers)
    return next(s for s in response.json()["streams"] if s["stream_id"] == stream_id)


async def test_a_registered_stream_is_pulled_by_the_relay_and_goes_live(station: Station) -> None:
    source = "rtsp://127.0.0.1:8554/aircraft-02"
    created = await station.client.post(
        "/api/v1/video-streams",
        json={"name": "Relay test", "source_url": source, "relay_path": "relay-test"},
        headers=station.headers,
    )
    stream_id = created.json()["id"]
    try:
        added = await until(lambda: _added(source), 15.0, "the path")
        live = await until(lambda: _measured(station, stream_id), 30.0, "a measured, live stream")
        await station.client.patch(
            f"/api/v1/video-streams/{stream_id}", json={"enabled": False}, headers=station.headers
        )
        removed = await until(_removed, 15.0, "the path to be removed")
    finally:
        async with httpx.AsyncClient() as http:
            await http.delete(f"{API}/v3/config/paths/delete/relay-test")

    assert added
    assert live["bitrate_kbps"] > 100
    assert removed


async def _added(source: str) -> bool:
    return (await _configured()).get("relay-test") == source


async def _removed() -> bool:
    return "relay-test" not in await _configured()


async def _measured(station: Station, stream_id: str) -> dict[str, Any] | None:
    """The stream's health once it is live with a bitrate (one poll after going live)."""
    health = await _health(station, stream_id)
    return health if health["state"] == "live" and health["bitrate_kbps"] is not None else None


async def test_a_stream_whose_source_is_missing_raises_video_down(station: Station) -> None:
    created = await station.client.post(
        "/api/v1/video-streams",
        json={
            "name": "Dead camera",
            "source_url": "rtsp://127.0.0.1:8554/no-such-camera",
            "relay_path": "relay-dead",
        },
        headers=station.headers,
    )
    stream_id = created.json()["id"]

    async def down() -> bool:
        response = await station.client.get(
            "/api/v1/alerts", params={"state": "active"}, headers=station.headers
        )
        return any(a["kind"] == "video_down" for a in response.json()["items"])

    try:
        raised = await until(down, 30.0, "the video_down alert")
        health = await _health(station, stream_id)
    finally:
        async with httpx.AsyncClient() as http:
            await http.delete(f"{API}/v3/config/paths/delete/relay-dead")

    assert raised
    assert health["state"] in ("offline", "stalled")
