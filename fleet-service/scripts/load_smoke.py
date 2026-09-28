"""
Load smoke test (M1b): N simulated aircraft at 10 Hz, K consoles on the WebSocket.

    SARGCS_SIMULATION=true SARGCS_DATA_DIR=load fleet-service create-admin --username chief
    SARGCS_SIMULATION=true SARGCS_DATA_DIR=load fleet-service
    python scripts/load_smoke.py --password <password> --aircraft 50 --clients 3 --seconds 60

For each console it measures the age of the newest telemetry in every batch it receives
(server sample time -> client receive time, same host clock), batches per second, bytes
per second, and how many aircraft it saw. The age includes the up-to-one-period wait of
the coalescing (1/telemetry_hz) by design. M1b records these numbers; M5 enforces the
budgets in docs/architecture.md. This measures the ground station only: no radio links.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime

import httpx
import websockets


async def ensure_aircraft(http: httpx.AsyncClient, headers: dict[str, str], count: int) -> None:
    existing = (await http.get("/api/v1/aircraft", params={"limit": 500}, headers=headers)).json()[
        "items"
    ]
    for i in range(len(existing), count):
        airframe = "fixed_wing" if i % 5 == 4 else "multirotor_quad"
        response = await http.post(
            "/api/v1/aircraft",
            json={"callsign": f"LOAD-{i:03d}", "airframe": airframe},
            headers=headers,
        )
        response.raise_for_status()


async def console(url: str, token: str, hz: float, seconds: float) -> dict[str, float]:
    ages: list[float] = []
    batches = 0
    received_bytes = 0
    seen: set[str] = set()
    async with websockets.connect(url, max_size=1 << 24) as ws:
        await ws.send(json.dumps({"type": "auth", "token": token}))
        await ws.recv()
        await ws.send(
            json.dumps({"type": "subscribe", "topics": ["fleet.telemetry"], "telemetry_hz": hz})
        )
        await ws.recv()  # snapshot
        started = time.monotonic()
        last_ping = started
        while time.monotonic() - started < seconds:
            raw = await ws.recv()
            now = datetime.now().astimezone()
            received_bytes += len(raw)
            message = json.loads(raw)
            if message["type"] == "event" and message["topic"] == "fleet.telemetry":
                batches += 1
                stamps = [
                    datetime.fromisoformat(a["telemetry"]["ts"])
                    for a in message["data"]["aircraft"]
                    if a["telemetry"]
                ]
                seen |= {a["aircraft_id"] for a in message["data"]["aircraft"]}
                if stamps:
                    ages.append((now - max(stamps)).total_seconds() * 1000)
            if time.monotonic() - last_ping > 10:
                await ws.send(json.dumps({"type": "ping"}))
                last_ping = time.monotonic()
        elapsed = time.monotonic() - started
    quantiles = statistics.quantiles(ages, n=100)
    return {
        "p50_ms": statistics.median(ages),
        "p95_ms": quantiles[94],
        "p99_ms": quantiles[98],
        "batches_per_s": batches / elapsed,
        "kb_per_s": received_bytes / elapsed / 1024,
        "aircraft_seen": len(seen),
    }


async def run(args: argparse.Namespace) -> int:
    async with httpx.AsyncClient(base_url=args.url, timeout=30) as http:
        login = await http.post(
            "/api/v1/auth/login", json={"username": args.username, "password": args.password}
        )
        login.raise_for_status()
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        await ensure_aircraft(http, headers, args.aircraft)
        await asyncio.sleep(2)
    url = args.url.replace("http", "ws", 1) + "/api/v1/ws"
    print(
        f"{args.aircraft} simulated aircraft at 10 Hz, "
        f"{args.clients} consoles at {args.hz} Hz, {args.seconds} s"
    )
    results = await asyncio.gather(
        *(console(url, token, args.hz, args.seconds) for _ in range(args.clients))
    )
    print(
        f"{'console':<8} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8} "
        f"{'batch/s':>8} {'KB/s':>8} {'aircraft':>9}"
    )
    for i, r in enumerate(results, 1):
        print(
            f"{i:<8} {r['p50_ms']:>8.0f} {r['p95_ms']:>8.0f} {r['p99_ms']:>8.0f} "
            f"{r['batches_per_s']:>8.2f} {r['kb_per_s']:>8.1f} {r['aircraft_seen']:>9.0f}"
        )
    complete = all(r["aircraft_seen"] == args.aircraft for r in results)
    print("every console saw every aircraft" if complete else "SOME AIRCRAFT WERE NEVER SEEN")
    return 0 if complete else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="chief")
    parser.add_argument("--password", required=True)
    parser.add_argument("--aircraft", type=int, default=50)
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--hz", type=float, default=4.0)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
