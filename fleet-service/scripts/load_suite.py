"""
Load suite (M5): the budgets of docs/architecture.md, measured and enforced.

It starts its own station in simulation mode (a fresh data directory), registers N
simulated aircraft streaming at 10 Hz, connects K consoles to the WebSocket exactly as the
console does (every topic, telemetry at 10 Hz), and measures for ``--seconds``:

* telemetry ingest -> console, p95 (the newest sample's age in each batch, same host
  clock; includes the coalescing wait by design);
* command accepted -> dispatched, p95 (sending a HOLD to an aircraft in the air -> the
  ``commands`` event that marks it dispatched, as a console sees it; published before the
  aircraft answers). The fleet takes off first; one warm-up command is not measured;
* link-state change -> alert on the console, p95 (a simulated link cut -> the
  ``link_stale`` alert event, minus the configured stale threshold);
* the fleet service's CPU (average cores) and peak RSS (Linux: /proc);
* WebSocket bandwidth per console: bytes on the wire (the connection negotiates
  per-message deflate, as browsers do), with the decompressed payload reported alongside.

It prints a table, writes a JSON report (``--report``) and exits 1 if any budget is
exceeded. Measures the ground station only: no radio links, no browser (the map frame rate
is the console's E2E perf test).

    python -m uv run python scripts/load_suite.py --aircraft 50 --consoles 6 --seconds 60
"""

import argparse
import asyncio
import contextlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import websockets

PASSWORD = "load-suite-pass"  # noqa: S105 - the throwaway station of this run
TOPICS = ["fleet.telemetry", "alerts", "commands", "control", "missions", "pois"]
LINK_STALE_AFTER_S = 3.0  # the station's default (config.py)

BUDGETS = {
    "telemetry_p95_ms": 250.0,
    "dispatch_p95_ms": 100.0,
    "alert_delay_p95_ms": 1000.0,
    "cpu_cores": 1.0,
    "rss_peak_mb": 500.0,
    "kb_per_s_per_console": 150.0,
}


@dataclass
class ConsoleStats:
    ages_ms: list[float] = field(default_factory=list)
    received_bytes: int = 0  # decompressed payload
    wire_bytes: int = 0  # what crossed the network
    aircraft_seen: set[str] = field(default_factory=set)


class Station:
    """A throwaway fleet service in simulation mode."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.data_dir = Path(tempfile.mkdtemp(prefix="sargcs-load-"))
        self.process: subprocess.Popen[bytes] | None = None

    def _env(self) -> dict[str, str]:
        return os.environ | {
            "SARGCS_SIMULATION": "true",
            "SARGCS_DATA_DIR": str(self.data_dir),
            "SARGCS_PORT": str(self.port),
            "SARGCS_STATION_NAME": "load",
            "SARGCS_LOG_LEVEL": "WARNING",
        }

    def start(self) -> None:
        run = [sys.executable, "-m", "fleet_service"]
        subprocess.run([*run, "db", "upgrade"], env=self._env(), check=True, capture_output=True)  # noqa: S603
        subprocess.run(  # noqa: S603
            [*run, "create-admin", "--username", "chief", "--password-stdin"],
            env=self._env(),
            input=PASSWORD.encode(),
            check=True,
            capture_output=True,
        )
        self.process = subprocess.Popen(run, env=self._env())  # noqa: S603
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            with contextlib.suppress(httpx.HTTPError):
                if httpx.get(f"{self.base}/api/v1/health", timeout=1).status_code == 200:
                    return
            time.sleep(0.3)
        raise SystemExit("the fleet service did not start")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=30)
        shutil.rmtree(self.data_dir, ignore_errors=True)


class ProcessMeter:
    """CPU time and resident memory of a process, from /proc (Linux only)."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.available = Path(f"/proc/{pid}/stat").exists()
        self._ticks = 100
        if sys.platform != "win32" and self.available:  # sysconf is POSIX-only (mypy on Windows)
            self._ticks = os.sysconf("SC_CLK_TCK")
        self.rss_peak_mb = 0.0

    def cpu_seconds(self) -> float:
        if not self.available:
            return 0.0
        fields = Path(f"/proc/{self.pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / self._ticks  # utime + stime

    def sample_rss(self) -> None:
        if not self.available:
            return
        for line in Path(f"/proc/{self.pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                self.rss_peak_mb = max(self.rss_peak_mb, int(line.split()[1]) / 1024)


async def seed(http: httpx.AsyncClient, headers: dict[str, str], count: int) -> list[str]:
    ids = []
    for i in range(count):
        airframe = "fixed_wing" if i % 5 == 4 else "multirotor_hexa"
        response = await http.post(
            "/api/v1/aircraft",
            json={"callsign": f"LOAD-{i:03d}", "airframe": airframe},
            headers=headers,
        )
        response.raise_for_status()
        ids.append(response.json()["id"])
    return ids


async def command(
    http: httpx.AsyncClient, headers: dict[str, str], kind: str, ids: list[str], **params: Any
) -> None:
    """Send a command, confirming it if the station asks (setup only)."""
    body = {"command_id": str(uuid.uuid4()), "kind": kind, "aircraft_ids": ids, **params}
    response = await http.post("/api/v1/commands", json=body, headers=headers)
    if response.status_code == 428:
        token = response.json()["confirmation_token"]
        response = await http.post(
            "/api/v1/commands", json={**body, "confirmation_token": token}, headers=headers
        )
    response.raise_for_status()


async def fly(http: httpx.AsyncClient, headers: dict[str, str], ids: list[str]) -> None:
    """Arm and take off every aircraft: a HOLD is only dispatched to aircraft in the air."""
    await command(http, headers, "arm", ids)
    await asyncio.sleep(1.0)
    await command(http, headers, "takeoff", ids, altitude_relative_m=20.0)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        fleet = (await http.get("/api/v1/fleet/state", headers=headers)).json()["aircraft"]
        if all((a["telemetry"] or {}).get("in_air") for a in fleet):
            return
        await asyncio.sleep(1.0)
    raise SystemExit("not every aircraft took off")


async def connect(url: str, token: str, hz: float) -> Any:
    ws = await websockets.connect(url, max_size=1 << 24)
    await ws.send(json.dumps({"type": "auth", "token": token}))
    await ws.recv()  # welcome
    await ws.send(json.dumps({"type": "subscribe", "topics": TOPICS, "telemetry_hz": hz}))
    return ws


async def console(url: str, token: str, hz: float, until: float, stats: ConsoleStats) -> None:
    ws = await connect(url, token, hz)
    received = ws.data_received  # count bytes as the transport hands them over

    def counting(data: bytes) -> None:
        stats.wire_bytes += len(data)
        received(data)

    ws.data_received = counting
    last_ping = time.monotonic()
    try:
        while time.monotonic() < until:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except TimeoutError:
                continue
            now = datetime.now().astimezone()
            stats.received_bytes += len(raw)
            message = json.loads(raw)
            if message["type"] == "event" and message["topic"] == "fleet.telemetry":
                aircraft = message["data"]["aircraft"]
                stats.aircraft_seen |= {a["aircraft_id"] for a in aircraft}
                stamps = [
                    datetime.fromisoformat(a["telemetry"]["ts"]) for a in aircraft if a["telemetry"]
                ]
                if stamps:
                    stats.ages_ms.append((now - max(stamps)).total_seconds() * 1000)
            if time.monotonic() - last_ping > 10:
                await ws.send(json.dumps({"type": "ping"}))
                last_ping = time.monotonic()
    finally:
        await ws.close()


async def dispatch_latencies(
    http: httpx.AsyncClient, headers: dict[str, str], url: str, token: str, ids: list[str], n: int
) -> list[float]:
    """Send HOLDs to one aircraft at a time; time each until its dispatched event arrives."""
    ws = await connect(url, token, 1.0)
    sent: dict[str, float] = {}
    latencies: list[float] = []

    async def listen() -> None:
        while len(latencies) < n:
            message = json.loads(await ws.recv())
            if message["type"] == "event" and message["topic"] == "commands":
                command = message["data"]
                if command["id"] in sent and any(
                    t["state"] != "pending" for t in command["targets"]
                ):
                    if command["state"] == "rejected":
                        raise SystemExit(f"a HOLD was rejected: {command['targets']}")
                    latencies.append((time.monotonic() - sent.pop(command["id"])) * 1000)

    listener = asyncio.create_task(listen())
    await http.post(  # warm-up, not measured: the first request of a process is slower
        "/api/v1/commands",
        json={"command_id": str(uuid.uuid4()), "kind": "hold", "aircraft_ids": [ids[-1]]},
        headers=headers,
    )
    await asyncio.sleep(0.3)
    for i in range(n):
        command_id = str(uuid.uuid4())
        sent[command_id] = time.monotonic()
        await http.post(
            "/api/v1/commands",
            json={"command_id": command_id, "kind": "hold", "aircraft_ids": [ids[i % len(ids)]]},
            headers=headers,
        )
        await asyncio.sleep(0.3)  # past the per-aircraft rate limit, well under the budget
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(listener, timeout=10)
    await ws.close()
    return latencies


async def alert_delays(
    http: httpx.AsyncClient, headers: dict[str, str], url: str, token: str, ids: list[str], n: int
) -> list[float]:
    """Cut a simulated link; time until its link_stale alert reaches a console."""
    ws = await connect(url, token, 1.0)
    delays = []
    try:
        for aircraft_id in ids[:n]:
            await http.post(
                f"/api/v1/simulation/aircraft/{aircraft_id}/faults",
                json={"link": False},
                headers=headers,
            )
            cut = time.monotonic()
            deadline = cut + LINK_STALE_AFTER_S + 10
            while time.monotonic() < deadline:
                try:
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
                except TimeoutError:
                    continue
                data = message.get("data") or {}
                if (
                    message["type"] == "event"
                    and message["topic"] == "alerts"
                    and data.get("kind") == "link_stale"
                    and data.get("aircraft_id") == aircraft_id
                ):
                    delays.append((time.monotonic() - cut - LINK_STALE_AFTER_S) * 1000)
                    break
            await http.post(
                f"/api/v1/simulation/aircraft/{aircraft_id}/faults",
                json={"link": True},
                headers=headers,
            )
    finally:
        await ws.close()
    return delays


def p95(values: list[float]) -> float | None:
    if len(values) < 2:
        return values[0] if values else None
    return statistics.quantiles(values, n=100)[94]


async def run(args: argparse.Namespace) -> int:
    station = Station(args.port)
    station.start()
    try:
        async with httpx.AsyncClient(base_url=station.base, timeout=30) as http:
            login = await http.post(
                "/api/v1/auth/login", json={"username": "chief", "password": PASSWORD}
            )
            token = login.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            ids = await seed(http, headers, args.aircraft)
            await asyncio.sleep(3)  # every aircraft streaming
            await fly(http, headers, ids)
            url = station.base.replace("http", "ws", 1) + "/api/v1/ws"
            assert station.process is not None  # noqa: S101
            meter = ProcessMeter(station.process.pid)

            print(
                f"{args.aircraft} simulated aircraft at 10 Hz, {args.consoles} consoles at "
                f"{args.hz:g} Hz on every topic, {args.seconds:g} s"
            )
            stats = [ConsoleStats() for _ in range(args.consoles)]
            cpu0, t0 = meter.cpu_seconds(), time.monotonic()
            until = t0 + args.seconds
            consoles = [asyncio.create_task(console(url, token, args.hz, until, s)) for s in stats]

            async def sample() -> None:
                while time.monotonic() < until:
                    meter.sample_rss()
                    await asyncio.sleep(1)

            sampler = asyncio.create_task(sample())
            await asyncio.sleep(min(10, args.seconds / 4))
            dispatch = await dispatch_latencies(http, headers, url, token, ids, 60)
            alerts = await alert_delays(http, headers, url, token, ids[-5:], 5)
            await asyncio.gather(*consoles, sampler)
            elapsed = time.monotonic() - t0
            cpu_cores = (meter.cpu_seconds() - cpu0) / elapsed
    finally:
        station.stop()

    ages = [a for s in stats for a in s.ages_ms]
    measured = {
        "telemetry_p95_ms": p95(ages),
        "dispatch_p95_ms": p95(dispatch),
        "alert_delay_p95_ms": p95(alerts),
        "cpu_cores": cpu_cores if meter.available else None,
        "rss_peak_mb": meter.rss_peak_mb if meter.available else None,
        "kb_per_s_per_console": max(s.wire_bytes / elapsed / 1024 for s in stats),
    }
    report = {
        "aircraft": args.aircraft,
        "consoles": args.consoles,
        "telemetry_hz": args.hz,
        "seconds": args.seconds,
        "measured": measured,
        "budgets": BUDGETS,
        "telemetry_p50_ms": statistics.median(ages) if ages else None,
        "dispatch_samples": len(dispatch),
        "dispatch_ms_sorted": sorted(round(d, 1) for d in dispatch),
        "alert_samples": len(alerts),
        "every_console_saw_every_aircraft": all(
            len(s.aircraft_seen) == args.aircraft for s in stats
        ),
        "consoles_detail": [
            {
                "aircraft_seen": len(s.aircraft_seen),
                "wire_kb_per_s": s.wire_bytes / elapsed / 1024,
                "payload_kb_per_s": s.received_bytes / elapsed / 1024,
            }
            for s in stats
        ],
    }
    failures = []
    print(f"{'measure':<24} {'value':>10} {'budget':>10}")
    for key, budget in BUDGETS.items():
        value = measured[key]
        shown = "n/a" if value is None else f"{value:.2f}"
        verdict = "unmeasured" if value is None else ("ok" if value <= budget else "OVER BUDGET")
        if value is not None and value > budget:
            failures.append(key)
        print(f"{key:<24} {shown:>10} {budget:>10g}  {verdict}")
    if not report["every_console_saw_every_aircraft"]:
        failures.append("aircraft_seen")
        print("SOME CONSOLE MISSED AIRCRAFT")
    if len(dispatch) < 10 or len(alerts) < 5:
        failures.append("samples")
        print(f"too few samples: {len(dispatch)} dispatches, {len(alerts)} alerts")
    report["failures"] = failures
    if args.report:
        await asyncio.to_thread(Path(args.report).write_text, json.dumps(report, indent=1))
    print("all budgets met" if not failures else f"FAILED: {', '.join(failures)}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--aircraft", type=int, default=50)
    parser.add_argument("--consoles", type=int, default=6)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument(
        "--hz", type=float, default=10.0, help="telemetry rate per console (the console's: 10)"
    )
    parser.add_argument("--port", type=int, default=8140)
    parser.add_argument("--report", default=None, help="write the JSON report here")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
