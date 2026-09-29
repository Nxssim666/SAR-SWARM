"""Helpers for tests over real MAVLink links (loopback vehicles, PX4 SITL): real time."""

import asyncio
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx


def free_udp_port() -> int:
    """A UDP port nobody is using right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


async def until[T](
    probe: Callable[[], Awaitable[T | None]], timeout_s: float, what: str, every_s: float = 0.2
) -> T:
    """Poll ``probe`` until it returns something truthy; fail with ``what`` after the timeout."""
    deadline = time.monotonic() + timeout_s
    last: T | None = None
    while time.monotonic() < deadline:
        last = await probe()
        if last:
            return last
        await asyncio.sleep(every_s)
    raise AssertionError(f"timed out after {timeout_s} s waiting for {what}; last: {last!r}")


def ready(telemetry: dict[str, Any]) -> bool:
    """PX4 accepts arming once it has a 3D fix, a position and a home."""
    return (
        telemetry["gps_fix"] in ("3d", "dgps", "rtk_float", "rtk_fixed")
        and telemetry["position"] is not None
        and telemetry["home"] is not None
        and telemetry["flight_mode"] != "unknown"  # a heartbeat has been heard
    )


class Station:
    """The fleet service as a console sees it, over REST."""

    def __init__(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers

    async def register(self, callsign: str, **fields: Any) -> str:
        body = {"callsign": callsign, "airframe": "multirotor_hexa"} | fields
        response = await self.client.post("/api/v1/aircraft", json=body, headers=self.headers)
        assert response.status_code == 201, response.text
        aircraft_id: str = response.json()["id"]
        return aircraft_id

    async def take(self, aircraft_id: str) -> None:
        response = await self.client.post(
            f"/api/v1/aircraft/{aircraft_id}/control", headers=self.headers
        )
        assert response.status_code == 200, response.text

    async def aircraft(self, aircraft_id: str) -> dict[str, Any]:
        response = await self.client.get("/api/v1/fleet/state", headers=self.headers)
        assert response.status_code == 200, response.text
        found: dict[str, Any] = next(
            a for a in response.json()["aircraft"] if a["aircraft_id"] == aircraft_id
        )
        return found

    async def telemetry(self, aircraft_id: str) -> dict[str, Any] | None:
        """Latest telemetry, once the link is live."""
        state = await self.aircraft(aircraft_id)
        telemetry: dict[str, Any] | None = state["telemetry"] if state["link"] == "live" else None
        return telemetry

    async def wait_for(
        self,
        aircraft_id: str,
        check: Callable[[dict[str, Any]], bool],
        timeout_s: float,
        what: str,
    ) -> dict[str, Any]:
        """Wait until the aircraft's live telemetry satisfies ``check``.

        On timeout the error shows the last state seen (link and telemetry), which is often
        all a CI log has to explain why.
        """
        seen: dict[str, Any] = {}

        async def probe() -> dict[str, Any] | None:
            state = await self.aircraft(aircraft_id)
            seen.update(link=state["link"], telemetry=state["telemetry"])
            telemetry: dict[str, Any] | None = state["telemetry"]
            live = state["link"] == "live" and telemetry is not None
            return telemetry if live and telemetry is not None and check(telemetry) else None

        try:
            return await until(probe, timeout_s, what)
        except AssertionError as error:
            raise AssertionError(f"{error}; last seen: {seen}") from None

    async def command(self, kind: str, aircraft_ids: list[str], **params: Any) -> dict[str, Any]:
        """Send a command, confirming it if the station asks to; return the outcome."""
        body: dict[str, Any] = {
            "command_id": str(uuid.uuid4()),
            "kind": kind,
            "aircraft_ids": aircraft_ids,
            **params,
        }
        response = await self.client.post("/api/v1/commands", json=body, headers=self.headers)
        if response.status_code == 428:
            body["confirmation_token"] = response.json()["confirmation_token"]
            response = await self.client.post("/api/v1/commands", json=body, headers=self.headers)
        assert response.status_code == 200, response.text
        outcome: dict[str, Any] = response.json()
        return outcome

    async def settled(self, outcome: dict[str, Any], timeout_s: float) -> dict[str, str]:
        """Per-aircraft states once effect verification has finished."""
        command_id = outcome["id"]

        async def probe() -> dict[str, str] | None:
            response = await self.client.get(f"/api/v1/commands/{command_id}", headers=self.headers)
            states = {t["aircraft_id"]: t["state"] for t in response.json()["targets"]}
            final = {"verified", "unverified", "nacked", "timeout", "rejected"}
            return states if set(states.values()) <= final else None

        return await until(probe, timeout_s, f"{outcome['kind']} to settle")

    async def active_alerts(self, aircraft_id: str) -> set[str]:
        response = await self.client.get(
            "/api/v1/alerts", params={"state": "active"}, headers=self.headers
        )
        return {a["kind"] for a in response.json()["items"] if a["aircraft_id"] == aircraft_id}
