"""Relay access control (M6, ADR 0036): viewing tickets, and the relay's auth hook."""

from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from fleet_service.config import Settings
from fleet_service.domain.enums import Role
from fleet_service.services.video_access import Publisher, RelayRequest, Tickets, decide

from factories import aircraft
from support import START, FakeClock

KEY = b"k" * 32


def read(path: str = "aircraft-01", token: str = "", query: str = "") -> RelayRequest:
    return RelayRequest("read", path, "webrtc", "", "", token, query, "10.0.0.5")


def publish(user: str, password: str) -> RelayRequest:
    return RelayRequest("publish", "cam-1", "rtsp", user, password, "", "", "10.0.0.9")


def test_a_ticket_plays_its_own_path_until_it_expires() -> None:
    tickets = Tickets(timedelta(hours=1), KEY)
    ticket, expires = tickets.issue("aircraft-01", "user-1", START)

    assert expires == START + timedelta(hours=1)
    assert tickets.check(ticket, "aircraft-01", START + timedelta(minutes=59)) == "user-1"
    assert tickets.check(ticket, "aircraft-02", START) is None  # another stream
    assert tickets.check(ticket, "aircraft-01", START + timedelta(hours=1, seconds=1)) is None


@pytest.mark.parametrize(
    "forged",
    [
        "",
        "garbage",
        "v1.a.b.c.d",
        "v2.YWlyY3JhZnQtMDE.dXNlci0x.9999999999.x",
    ],
)
def test_forged_tickets_are_refused(forged: str) -> None:
    assert Tickets(timedelta(hours=1), KEY).check(forged, "aircraft-01", START) is None


def test_a_ticket_from_another_key_or_a_restart_is_refused() -> None:
    ticket, _ = Tickets(timedelta(hours=1), KEY).issue("aircraft-01", "user-1", START)

    assert Tickets(timedelta(hours=1)).check(ticket, "aircraft-01", START) is None


def test_a_tampered_ticket_is_refused() -> None:
    tickets = Tickets(timedelta(hours=1), KEY)
    ticket, _ = tickets.issue("aircraft-01", "user-1", START)
    version, path, user, expiry, signature = ticket.split(".")
    longer = f"{version}.{path}.{user}.{int(expiry) + 86_400}.{signature}"

    assert tickets.check(longer, "aircraft-01", START) is None


@pytest.mark.parametrize(
    ("request_", "publisher", "allowed"),
    [
        (read(), None, False),  # no ticket
        (read(token="nope"), None, False),
        (publish("cam", "secret"), None, False),  # publishing not configured
        (publish("cam", "secret"), Publisher("cam", "secret"), True),
        (publish("cam", "wrong"), Publisher("cam", "secret"), False),
        (RelayRequest("api", "", "", "", "", "", "", ""), None, False),
    ],
)
def test_the_relay_is_answered_row_by_row(
    request_: RelayRequest, publisher: Publisher | None, allowed: bool
) -> None:
    tickets = Tickets(timedelta(hours=1), KEY)

    assert decide(request_, tickets, publisher, START)[0] is allowed


def test_a_ticket_in_the_header_or_the_query_plays() -> None:
    tickets = Tickets(timedelta(hours=1), KEY)
    ticket, _ = tickets.issue("aircraft-01", "user-1", START)

    assert decide(read(token=ticket), tickets, None, START)[0] is True
    assert decide(read(query=f"ticket={ticket}"), tickets, None, START)[0] is True


# --- through the API ------------------------------------------------------------------------


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(station_name="test-station", data_dir=data_dir, video_ticket_ttl_s=600)


async def test_the_view_ticket_opens_the_relay_for_that_stream_only(
    client: httpx.AsyncClient, auth: dict[Role, dict[str, str]], clock: FakeClock
) -> None:
    plane = await aircraft(client, auth[Role.SUPERVISOR], "HX-1")
    stream = await client.post(
        "/api/v1/video-streams",
        json={
            "aircraft_id": plane["id"],
            "name": "HX-1 camera",
            "source_url": "rtsp://10.0.0.9/stream",
            "relay_path": "aircraft-01",
        },
        headers=auth[Role.SUPERVISOR],
    )
    view = await client.post(
        f"/api/v1/video-streams/{stream.json()['id']}/view", headers=auth[Role.OBSERVER]
    )
    ticket = view.json()["ticket"]

    def hook(path: str, token: str) -> dict[str, str]:
        return {"action": "read", "path": path, "protocol": "hls", "token": token, "id": "x"}

    own = await client.post("/api/v1/internal/video-auth", json=hook("aircraft-01", ticket))
    other = await client.post("/api/v1/internal/video-auth", json=hook("aircraft-02", ticket))
    anonymous = await client.post("/api/v1/internal/video-auth", json=hook("aircraft-01", ""))
    clock.advance(seconds=601)
    expired = await client.post("/api/v1/internal/video-auth", json=hook("aircraft-01", ticket))

    assert view.json()["expires_at"] is not None
    assert own.status_code == 204
    assert other.status_code == 403
    assert anonymous.status_code == 403
    assert anonymous.headers["content-type"] == "application/problem+json"
    assert expired.status_code == 403


async def test_the_hook_is_not_part_of_the_public_api(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/api/v1/openapi.json")).json()

    assert not any("internal" in path for path in schema["paths"])
