"""
Scale: a PX4 SIH fleet of N aircraft on one ground station port (ADR 0026).

The fleet comes from ``sim/sitl/fleet.py`` (its ``fleet.json`` names the aircraft). Runs
only with ``SARGCS_SCALE_FLEET=<path to fleet.json>`` (the ``sitl-scale`` workflow, and
``sitl`` with the five-aircraft fleet).

Measured over a window of live tracking, through the WebSocket a console uses:

- per aircraft: updates per second and the largest gap between two samples;
- internal latency: from the driver's sample timestamp to its arrival at the console
  (MAVSDK callback, registry, bus, WebSocket coalescing at 10 Hz);
- the fleet service's CPU and peak memory, and the host's load and memory.

The report is written as JSON to ``SARGCS_SCALE_REPORT`` (if set), for the workflow's
annotations. Asserted: every aircraft stays live for the whole window with no gap
reaching the stale threshold, and a confirmed bulk arm and disarm of the whole fleet is
acked and verified.
"""

import asyncio
import itertools
import json
import os
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx_ws import AsyncWebSocketSession, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from fleet_service.config import Settings
from link_support import Station, ready

FLEET_FILE = os.environ.get("SARGCS_SCALE_FLEET")
REPORT_FILE = os.environ.get("SARGCS_SCALE_REPORT")
WINDOW_S = float(os.environ.get("SARGCS_SCALE_WINDOW_S", "60"))

pytestmark = [
    pytest.mark.sitl_scale,
    pytest.mark.skipif(
        FLEET_FILE is None, reason="needs a PX4 SIH fleet: set SARGCS_SCALE_FLEET=fleet.json"
    ),
]

GCS = "udpin://0.0.0.0:14550"
BOOT_TIMEOUT_S = 300.0  # N containers start on a small host, EKF2 converges, home is set
SETTLE_TIMEOUT_S = 90.0
PING_EVERY_S = 10.0


def _fleet() -> list[dict[str, Any]]:
    assert FLEET_FILE is not None
    fleet: list[dict[str, Any]] = json.loads(Path(FLEET_FILE).read_text(encoding="utf-8"))
    return fleet


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def _proc_kib(path: str, field: str) -> int | None:
    """A ``kB`` field of a /proc status file (Linux; None elsewhere)."""
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.startswith(field + ":"):
                return int(line.split()[1])
    except OSError:
        return None
    return None


def _loadavg() -> list[float] | None:
    try:
        return [float(v) for v in Path("/proc/loadavg").read_text(encoding="utf-8").split()[:3]]
    except OSError:
        return None


async def _register_fleet(station: Station) -> dict[int, str]:
    ids = {}
    for aircraft in _fleet():
        ids[aircraft["system_id"]] = await station.register(
            aircraft["callsign"],
            airframe=aircraft["airframe"],
            mavlink_connection=GCS,
            mavlink_system_id=aircraft["system_id"],
        )
    return ids


async def _all_ready(station: Station, ids: dict[int, str]) -> float:
    """Wait until every aircraft is ready to arm; return how long it took."""
    started = time.monotonic()
    for system_id, aircraft_id in ids.items():
        await station.wait_for(
            aircraft_id,
            ready,
            max(1.0, BOOT_TIMEOUT_S - (time.monotonic() - started)),
            f"sys {system_id} ready",
        )
    return time.monotonic() - started


async def _watch(app: FastAPI, token: str, seconds: float) -> dict[str, list[tuple[Any, ...]]]:
    """Every telemetry update per aircraft for ``seconds``: (sample ts, received, link)."""
    seen: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    transport = ASGIWebSocketTransport(app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as http,
        aconnect_ws(
            "http://test/api/v1/ws",
            http,
            max_message_size_bytes=1 << 22,
            session_class=AsyncWebSocketSession,
        ) as ws,
    ):
        await ws.send_json({"type": "auth", "token": token})
        assert (await ws.receive_json(timeout=10))["type"] == "welcome"
        await ws.send_json({"type": "subscribe", "topics": ["fleet.telemetry"], "telemetry_hz": 10})
        deadline = time.monotonic() + seconds
        next_ping = time.monotonic() + PING_EVERY_S
        while (left := deadline - time.monotonic()) > 0:
            if time.monotonic() >= next_ping:  # the station closes idle sockets
                await ws.send_json({"type": "ping"})
                next_ping += PING_EVERY_S
            try:
                message = await ws.receive_json(timeout=min(left, 2.0))
            except TimeoutError:
                continue
            if message.get("topic") != "fleet.telemetry":
                continue
            received = datetime.now(UTC)
            for aircraft in message["data"]["aircraft"]:
                telemetry = aircraft["telemetry"]
                ts = datetime.fromisoformat(telemetry["ts"]) if telemetry else None
                seen[aircraft["aircraft_id"]].append((ts, received, aircraft["link"]))
    return seen


def _analyse(
    seen: dict[str, list[tuple[Any, ...]]], ids: dict[int, str], seconds: float
) -> dict[str, Any]:
    callsigns = {a["system_id"]: a["callsign"] for a in _fleet()}
    per_aircraft: dict[str, dict[str, Any]] = {}
    latencies: list[float] = []
    for system_id, aircraft_id in ids.items():
        updates = seen.get(aircraft_id, [])
        stamps = sorted({u[0] for u in updates if u[0] is not None})
        gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(stamps)]
        first_seen: set[Any] = set()
        for ts, received, _ in updates:
            if ts is not None and ts not in first_seen:
                first_seen.add(ts)
                latencies.append((received - ts).total_seconds())
        per_aircraft[callsigns[system_id]] = {
            "samples": len(stamps),
            "rate_hz": round(len(stamps) / seconds, 2),
            "max_gap_s": round(max(gaps), 3) if gaps else None,
            "links": sorted({u[2] for u in updates}),
        }
    rates = [a["rate_hz"] for a in per_aircraft.values()]
    gaps = [a["max_gap_s"] for a in per_aircraft.values() if a["max_gap_s"] is not None]
    return {
        "aircraft": len(ids),
        "window_s": seconds,
        "rate_hz": {"min": min(rates), "median": statistics.median(rates)},
        "max_gap_s": max(gaps) if gaps else None,
        "latency_s": {
            "p50": round(_percentile(latencies, 0.50), 4),
            "p95": round(_percentile(latencies, 0.95), 4),
            "max": round(max(latencies), 4),
        }
        if latencies
        else None,
        "not_live": sorted(
            callsign for callsign, a in per_aircraft.items() if a["links"] != ["live"]
        ),
        "per_aircraft": per_aircraft,
    }


def _write_report(report: dict[str, Any]) -> None:
    if REPORT_FILE:
        path = Path(REPORT_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        path.write_text(json.dumps(existing | report, indent=2) + "\n", encoding="utf-8")


async def test_the_whole_fleet_is_tracked_without_stale_states(
    app: FastAPI, station: Station, settings: Settings
) -> None:
    ids = await _register_fleet(station)
    boot_s = await _all_ready(station, ids)

    token = station.headers["Authorization"].removeprefix("Bearer ")
    cpu_before, wall_before = time.process_time(), time.monotonic()
    seen = await _watch(app, token, WINDOW_S)
    cpu_share = (time.process_time() - cpu_before) / (time.monotonic() - wall_before)

    report = _analyse(seen, ids, WINDOW_S)
    report["boot_to_ready_s"] = round(boot_s, 1)
    report["service"] = {
        "cpu_share_of_one_core": round(cpu_share, 3),
        "rss_peak_mib": (kib // 1024) if (kib := _proc_kib("/proc/self/status", "VmHWM")) else None,
    }
    report["host"] = {
        "cpus": os.cpu_count(),
        "loadavg": _loadavg(),
        "mem_available_mib": (kib // 1024)
        if (kib := _proc_kib("/proc/meminfo", "MemAvailable"))
        else None,
    }
    _write_report({"tracking": report})

    assert report["not_live"] == [], report["not_live"]
    assert report["max_gap_s"] is not None
    assert report["max_gap_s"] < settings.link_stale_after_s, report["max_gap_s"]


async def test_a_bulk_arm_and_disarm_of_the_whole_fleet_is_verified(station: Station) -> None:
    ids = await _register_fleet(station)
    await _all_ready(station, ids)
    aircraft_ids = list(ids.values())
    for aircraft_id in aircraft_ids:
        await station.take(aircraft_id)

    timings: dict[str, float] = {}
    pending = aircraft_ids
    reasons: list[dict[str, int]] = []
    for attempt in range(1, 6):  # PX4's preflight checks may still be settling on a busy host
        started = time.monotonic()
        outcome = await station.command("arm", pending)
        states = await station.settled(outcome, SETTLE_TIMEOUT_S)
        timings.setdefault("arm_s", round(time.monotonic() - started, 2))
        pending = [a for a, state in states.items() if state != "verified"]
        timings["arm_attempts"] = attempt
        if not pending:
            break
        reasons.append(await station.reasons(outcome))
        await asyncio.sleep(5.0)
    _write_report({"bulk": timings | {"aircraft": len(aircraft_ids), "arm_failures": reasons}})
    assert pending == [], f"{len(pending)} aircraft not armed after retries; per attempt: {reasons}"

    started = time.monotonic()
    states = await station.settled(await station.command("disarm", aircraft_ids), SETTLE_TIMEOUT_S)
    timings["disarm_s"] = round(time.monotonic() - started, 2)
    _write_report({"bulk": timings | {"aircraft": len(aircraft_ids), "arm_failures": reasons}})

    assert set(states.values()) == {"verified"}, states
