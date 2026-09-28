"""
M1b acceptance: a live fleet service in simulation mode, driven like an operator would.

    SARGCS_SIMULATION=true SARGCS_DATA_DIR=demo fleet-service create-admin --username chief
    SARGCS_SIMULATION=true SARGCS_DATA_DIR=demo fleet-service
    python scripts/m1b_acceptance.py --password <chief's password>
    SARGCS_DATA_DIR=demo fleet-service audit-verify

Steps: the admin creates an operator, an incident and 5 aircraft (3 hexacopters, 2 fixed
wing); the operator opens a WebSocket, takes control of all five, and runs arm ->
takeoff -> hold -> return-to-launch as bulk commands, confirming each 428 with the
server's summary; the script waits for every aircraft to be airborne, then landed and
disarmed, and prints what arrived over the WebSocket and in the audit trail.
Exit status 0 only if every step behaved as specified.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections import Counter
from typing import Any

import httpx
import websockets

AIRCRAFT = [
    ("HX-1", "multirotor_hexa"),
    ("HX-2", "multirotor_hexa"),
    ("HX-3", "multirotor_hexa"),
    ("FW-1", "fixed_wing"),
    ("FW-2", "fixed_wing"),
]
OPERATOR = ("olivia", "operator-demo-password")


class AcceptanceFailedError(Exception):
    """An acceptance step did not behave as specified."""


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def check(condition: bool, text: str) -> None:
    print(f"   {'PASS' if condition else 'FAIL'}  {text}", flush=True)
    if not condition:
        raise AcceptanceFailedError(text)


async def login(http: httpx.AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await http.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def bulk(
    http: httpx.AsyncClient, headers: dict[str, str], kind: str, ids: list[str], **params: Any
) -> dict[str, Any]:
    """Send a bulk command: expect a 428 with a summary, confirm it, return the outcome."""
    body = {"command_id": str(uuid.uuid4()), "kind": kind, "aircraft_ids": ids, **params}
    first = await http.post("/api/v1/commands", json=body, headers=headers)
    check(first.status_code == 428, f"{kind}: server asks for confirmation (428)")
    summary = first.json()["summary"]
    print(f"      summary: {len(summary['aircraft'])} aircraft; reasons: {summary['reasons']}")
    second = await http.post(
        "/api/v1/commands",
        json=body | {"confirmation_token": first.json()["confirmation_token"]},
        headers=headers,
    )
    check(second.status_code == 200, f"{kind}: confirmed and dispatched")
    outcome: dict[str, Any] = second.json()
    states = Counter(t["state"] for t in outcome["targets"])
    check(
        states == Counter({"acked": len(ids)}),
        f"{kind}: acknowledged by all {len(ids)} ({dict(states)})",
    )
    return outcome


async def wait_for(
    http: httpx.AsyncClient,
    headers: dict[str, str],
    ids: list[str],
    what: str,
    predicate: Any,
    timeout_s: float,
) -> None:
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        fleet = (await http.get("/api/v1/fleet/state", headers=headers)).json()["aircraft"]
        mine = [a for a in fleet if a["aircraft_id"] in ids]
        if all(a["telemetry"] and predicate(a["telemetry"]) for a in mine):
            check(True, f"all {len(ids)} aircraft {what} after {time.monotonic() - started:.0f} s")
            return
        await asyncio.sleep(1.0)
    raise AcceptanceFailedError(f"not all aircraft {what} within {timeout_s:.0f} s")


async def listen(
    url: str, token: str, received: list[dict[str, Any]], ready: asyncio.Event
) -> None:
    async with websockets.connect(url, max_size=1 << 24) as ws:
        await ws.send(json.dumps({"type": "auth", "token": token}))
        received.append(json.loads(await ws.recv()))
        await ws.send(
            json.dumps(
                {
                    "type": "subscribe",
                    "topics": ["fleet.telemetry", "alerts", "commands", "control"],
                    "telemetry_hz": 2,
                }
            )
        )
        ready.set()
        last_ping = time.monotonic()
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                received.append(json.loads(raw))
            except TimeoutError:
                pass
            if time.monotonic() - last_ping > 10:
                await ws.send(json.dumps({"type": "ping"}))
                last_ping = time.monotonic()


async def run(base_url: str, admin_user: str, admin_password: str) -> None:
    ws_url = base_url.replace("http", "ws", 1) + "/api/v1/ws"
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as http:
        step("Admin sets up the incident, the operator and 5 aircraft")
        admin = await login(http, admin_user, admin_password)
        version = (await http.get("/api/v1/version")).json()
        check(version["simulation"] is True, "the station is in simulation mode")
        created = await http.post(
            "/api/v1/users",
            json={
                "username": OPERATOR[0],
                "display_name": "Olivia (ops)",
                "role": "operator",
                "password": OPERATOR[1],
            },
            headers=admin,
        )
        check(created.status_code in (201, 409), "operator account exists")
        incident = await http.post(
            "/api/v1/incidents",
            json={
                "name": "Acceptance: missing hikers",
                "base": {"latitude": 47.3977, "longitude": 8.5456},
            },
            headers=admin,
        )
        check(incident.status_code == 201, "incident opened")
        ids = []
        for callsign, airframe in AIRCRAFT:
            response = await http.post(
                "/api/v1/aircraft", json={"callsign": callsign, "airframe": airframe}, headers=admin
            )
            check(response.status_code == 201, f"{callsign} ({airframe}) registered")
            ids.append(response.json()["id"])
        await asyncio.sleep(1.5)

        step("Operator connects to the live feed and takes control")
        operator = await login(http, *OPERATOR)
        received: list[dict[str, Any]] = []
        ready = asyncio.Event()
        listener = asyncio.create_task(
            listen(ws_url, operator["Authorization"][7:], received, ready)
        )
        await asyncio.wait_for(ready.wait(), timeout=5)
        for aircraft_id in ids:
            response = await http.post(f"/api/v1/aircraft/{aircraft_id}/control", headers=operator)
            check(response.status_code == 200, f"control of {aircraft_id[:8]}... taken")
        await wait_for(
            http, operator, ids, "report live telemetry", lambda t: t["gps_fix"] == "3d", 10
        )

        step("Arm, take off, hold, return to launch (bulk, confirmed)")
        await bulk(http, operator, "arm", ids)
        await asyncio.sleep(1.0)
        await bulk(http, operator, "takeoff", ids, altitude_relative_m=40.0)
        await wait_for(
            http,
            operator,
            ids,
            "airborne above 35 m",
            lambda t: t["in_air"] and t["altitude_relative_m"] > 35,
            40,
        )
        await bulk(http, operator, "hold", ids)
        await asyncio.sleep(2.0)
        await bulk(http, operator, "return_to_launch", ids)
        await wait_for(
            http,
            operator,
            ids,
            "landed and disarmed",
            lambda t: not t["in_air"] and not t["armed"],
            180,
        )
        await asyncio.sleep(1.5)  # let the last events arrive
        listener.cancel()

        step("What the operator's console received over the WebSocket")
        kinds = Counter((m["type"], m.get("topic")) for m in received)
        for (kind, topic), count in sorted(kinds.items(), key=lambda kv: str(kv[0])):
            print(f"      {kind:<8} {topic or '':<16} x{count}")
        command_events = [
            m["data"] for m in received if m.get("topic") == "commands" and m["type"] == "event"
        ]
        verified = {
            c["kind"]
            for c in command_events
            if c["targets"] and all(t["state"] == "verified" for t in c["targets"])
        }
        check(kinds[("welcome", None)] == 1, "welcome received")
        check(kinds[("event", "fleet.telemetry")] > 10, "live telemetry streamed")
        check(kinds[("event", "control")] == len(ids), "every control change pushed")
        check(
            {"arm", "takeoff", "hold", "return_to_launch"} <= verified,
            f"effects verified from telemetry: {sorted(verified)}",
        )
        seqs = [m["seq"] for m in received if "seq" in m]
        check(seqs == list(range(1, len(seqs) + 1)), f"{len(seqs)} messages in sequence, no gaps")

        step("The audit trail")
        audit = (
            await http.get(
                "/api/v1/audit", params={"action": "command.", "limit": 100}, headers=admin
            )
        ).json()
        actions = Counter(e["action"] for e in audit["items"])
        for action, count in sorted(actions.items()):
            print(f"      {action:<32} x{count}")
        check(
            actions["command.dispatch"] == 4 and actions["command.complete"] == 4,
            "4 commands dispatched and completed",
        )
        check(actions["command.confirmation_request"] == 4, "4 confirmations requested")
        check(
            actions["command.verified"] == 4 * len(ids), "every aircraft verified for every command"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="chief")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.url, args.username, args.password))
    except AcceptanceFailedError as failure:
        print(f"\nACCEPTANCE FAILED: {failure}")
        return 1
    print("\nACCEPTANCE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
