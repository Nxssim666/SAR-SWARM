"""
Full acceptance run (M6): the brief's final scenario, scripted and repeatable.

It starts its own station in simulation mode (a fresh data directory) and plays the
scenario through the public API and the WebSocket, as consoles would:

 1. Launch: the station, a supervisor and an operator; **50 simulated aircraft**
    (40 hexacopters, 10 airplanes), all connected (live links).
 2. The operator **tracks 25**: takes control of them; a console connected to the
    WebSocket receives telemetry for all 50.
 3. An incident, a search area and a **mixed group of 8** (6 hexacopters, 2 airplanes).
    Preflight checks pass; the group arms and takes off (held confirmations, as the
    console does), and an **area search** is planned for the group and started.
 4. **Faults** while it flies: link loss (one aircraft), low battery (another), GNSS loss
    (a third). Each raises its alert on the console, the aircraft's own failsafe acts,
    and the lost link recovers and its alert clears.
 5. **Video** (``--video``: the mock relay of sim/video running on this host): every
    stream is live at the relay and a viewing ticket is issued (and audited).
 6. **Return and land**: every airborne aircraft returns home, lands and disarms.
 7. The **audit chain verifies**, the audit head is exported, and the **incident export**
    completes with every file matching its manifest. The incident is closed.

Each step prints PASS or FAIL with what it saw. It writes a JSON report (``--report``) and
exits 1 if any step failed. The 50-aircraft PX4 SIH variant needs field hardware (M2b
decision); this run uses the simulator, which the fleet service treats like any driver.

    python -m uv run python scripts/acceptance.py [--video] [--report acceptance.json]
"""

import argparse
import asyncio
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import websockets

ADMIN_PASSWORD = "acceptance-admin-pass"  # noqa: S105 - the throwaway station of this run
OPERATOR_PASSWORD = "acceptance-operator-pass"  # noqa: S105
FLEET = 50
TRACKED = 25
ORIGIN = (47.3977, 8.5456)  # the simulator's default origin (config.py)
RELAY_API = "http://127.0.0.1:9997"


@dataclass
class Step:
    name: str
    ok: bool
    detail: str
    seconds: float


@dataclass
class Run:
    steps: list[Step] = field(default_factory=list)

    async def step(self, name: str, work: Callable[[], Awaitable[str]]) -> bool:
        started = time.monotonic()
        try:
            detail = await work()
            ok = True
        except Exception as error:  # every failure is reported, then the run goes on
            detail, ok = f"{type(error).__name__}: {error}", False
        took = time.monotonic() - started
        self.steps.append(Step(name, ok, detail, round(took, 1)))
        print(f"{'PASS' if ok else 'FAIL'}  {name} ({took:.0f} s): {detail}", flush=True)
        return ok


class Station:
    """A throwaway fleet service in simulation mode."""

    def __init__(self, port: int, video: bool) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.data_dir = Path(tempfile.mkdtemp(prefix="sargcs-acceptance-"))
        self.video = video
        self.process: subprocess.Popen[bytes] | None = None

    def env(self) -> dict[str, str]:
        extra = {"SARGCS_MEDIAMTX_API_URL": RELAY_API} if self.video else {}
        return (
            os.environ
            | {
                "SARGCS_SIMULATION": "true",
                "SARGCS_DATA_DIR": str(self.data_dir),
                "SARGCS_PORT": str(self.port),
                "SARGCS_STATION_NAME": "acceptance",
                "SARGCS_LOG_LEVEL": "WARNING",
                "SARGCS_AUDIT_HEAD_INTERVAL_S": "10",
            }
            | extra
        )

    def start(self) -> None:
        run = [sys.executable, "-m", "fleet_service"]
        subprocess.run([*run, "db", "upgrade"], env=self.env(), check=True, capture_output=True)  # noqa: S603
        subprocess.run(  # noqa: S603
            [*run, "create-admin", "--username", "chief", "--password-stdin"],
            env=self.env(),
            input=ADMIN_PASSWORD.encode(),
            check=True,
            capture_output=True,
        )
        self.process = subprocess.Popen(run, env=self.env())  # noqa: S603
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            with contextlib.suppress(httpx.HTTPError):
                if httpx.get(f"{self.base}/api/v1/health", timeout=1).status_code == 200:
                    return
            time.sleep(0.3)
        raise SystemExit("the fleet service did not start")

    def stop(self, keep: bool) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=30)
        if not keep:
            shutil.rmtree(self.data_dir, ignore_errors=True)


class Client:
    """One signed-in user, over REST."""

    def __init__(self, http: httpx.AsyncClient, token: str) -> None:
        self.http = http
        self.headers = {"Authorization": f"Bearer {token}"}

    @classmethod
    async def login(cls, http: httpx.AsyncClient, username: str, password: str) -> "Client":
        response = await http.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        response.raise_for_status()
        return cls(http, response.json()["token"])

    async def get(self, path: str) -> Any:
        response = await self.http.get(f"/api/v1{path}", headers=self.headers)
        response.raise_for_status()
        return response.json()

    async def post(self, path: str, body: Any = None, expect: int | None = None) -> Any:
        response = await self.http.post(f"/api/v1{path}", json=body, headers=self.headers)
        if expect is not None and response.status_code != expect:
            raise AssertionError(f"POST {path}: HTTP {response.status_code}: {response.text}")
        if expect is None:
            response.raise_for_status()
        return response.json() if response.content else None

    async def command(self, kind: str, ids: list[str], **params: Any) -> dict[str, Any]:
        """Send a command, confirming it when asked (the console's held confirmation)."""
        body = {"command_id": str(uuid.uuid4()), "kind": kind, "aircraft_ids": ids, **params}
        response = await self.http.post("/api/v1/commands", json=body, headers=self.headers)
        if response.status_code == 428:
            body["confirmation_token"] = response.json()["confirmation_token"]
            response = await self.http.post("/api/v1/commands", json=body, headers=self.headers)
        if response.status_code != 200:
            raise AssertionError(f"{kind}: HTTP {response.status_code}: {response.text}")
        outcome: dict[str, Any] = response.json()
        return outcome

    async def fleet(self) -> dict[str, dict[str, Any]]:
        state = await self.get("/fleet/state")
        return {a["aircraft_id"]: a for a in state["aircraft"]}

    async def active_alerts(self) -> list[dict[str, Any]]:
        page = await self.get("/alerts?state=active&limit=200")
        items: list[dict[str, Any]] = page["items"]
        return items


async def until(check: Callable[[], Awaitable[Any]], limit_s: float, what: str) -> Any:
    """Poll ``check`` until it returns something truthy."""
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        found = await check()
        if found:
            return found
        await asyncio.sleep(0.5)
    raise AssertionError(f"timed out after {limit_s:.0f} s waiting for {what}")


def states(outcome: dict[str, Any]) -> dict[str, str]:
    return {t["aircraft_id"]: t["state"] for t in outcome["targets"]}


def reasons(outcome: dict[str, Any]) -> dict[str, str]:
    """Each aircraft's state, with the reason when it was not sent or refused."""
    return {
        t["aircraft_id"][-6:]: t["state"]
        + (f" ({t['reason_code']}: {t['reason']})" if t.get("reason") else "")
        for t in outcome["targets"]
    }


class Console:
    """A console's WebSocket: counts telemetry per aircraft and collects alert events."""

    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.token = token
        self.telemetry: dict[str, int] = {}
        self.alerts: list[dict[str, Any]] = []
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        async with websockets.connect(self.url, max_size=None) as socket:
            await socket.send(json.dumps({"type": "auth", "token": self.token}))
            await socket.recv()  # welcome
            await socket.send(
                json.dumps(
                    {
                        "type": "subscribe",
                        "topics": ["fleet.telemetry", "alerts"],
                        "telemetry_hz": 2,
                    }
                )
            )
            last_ping = time.monotonic()
            while True:
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                except TimeoutError:
                    raw = None
                if time.monotonic() - last_ping > 10:  # the console pings; idle sockets close
                    await socket.send(json.dumps({"type": "ping"}))
                    last_ping = time.monotonic()
                if raw is None:
                    continue
                message = json.loads(raw)
                if message.get("type") != "event":
                    continue
                if message["topic"] == "fleet.telemetry":
                    for sample in message["data"]["aircraft"]:
                        key = sample["aircraft_id"]
                        self.telemetry[key] = self.telemetry.get(key, 0) + 1
                elif message["topic"] == "alerts":
                    self.alerts.append(message["data"])


async def scenario(station: Station, run: Run) -> None:
    async with httpx.AsyncClient(base_url=station.base, timeout=60) as http:
        chief = await Client.login(http, "chief", ADMIN_PASSWORD)
        ids: list[str] = []
        context: dict[str, Any] = {}

        async def launch() -> str:
            await chief.post(
                "/users",
                {
                    "username": "op1",
                    "display_name": "Operator One",
                    "role": "operator",
                    "password": OPERATOR_PASSWORD,
                },
                expect=201,
            )
            for i in range(FLEET):
                airframe = "fixed_wing" if i % 5 == 4 else "multirotor_hexa"
                created = await chief.post(
                    "/aircraft",
                    {"callsign": f"SAR-{i + 1:02d}", "airframe": airframe},
                    expect=201,
                )
                ids.append(created["id"])
            if station.video:
                for i in range(1, 5):
                    await chief.post(
                        "/video-streams",
                        {
                            "aircraft_id": ids[i - 1],
                            "name": f"SAR-{i:02d} camera",
                            "source_url": f"rtsp://127.0.0.1:8554/aircraft-{i:02d}",
                            "relay_path": f"aircraft-{i:02d}",
                        },
                        expect=201,
                    )

            async def all_live() -> bool:
                fleet = await chief.fleet()
                live: int = sum(a["link"] == "live" for a in fleet.values())
                return live == FLEET

            await until(all_live, 60, f"{FLEET} live links")
            return f"{FLEET} aircraft registered and live (40 hexacopters, 10 airplanes)"

        if not await run.step("1. launch the station and connect 50 aircraft", launch):
            return
        op1 = await Client.login(http, "op1", OPERATOR_PASSWORD)
        console = Console(
            f"ws://127.0.0.1:{station.port}/api/v1/ws", op1.headers["Authorization"][7:]
        )
        await console.start()

        async def track() -> str:
            for aircraft_id in ids[:TRACKED]:
                await op1.post(f"/aircraft/{aircraft_id}/control")
            await asyncio.sleep(5)
            silent = [a for a in ids if console.telemetry.get(a, 0) == 0]
            if silent:
                raise AssertionError(f"no telemetry on the console for {len(silent)} aircraft")
            controlled = [a for a in (await op1.fleet()).values() if a["controller"]]
            if len(controlled) != TRACKED:
                raise AssertionError(f"{len(controlled)} aircraft controlled, not {TRACKED}")
            rate = sum(console.telemetry.values()) / FLEET / 5
            return (
                f"op1 controls {TRACKED}; the console receives telemetry for all {FLEET} "
                f"(about {rate:.1f} samples/s each at the requested 2 Hz)"
            )

        await run.step("2. an operator tracks 25 aircraft", track)
        # 6 hexacopters and the 2 airplanes among op1's aircraft (every 5th is an airplane)
        group = [ids[i] for i in (0, 1, 2, 3, 5, 6)] + [ids[4], ids[9]]

        async def search() -> str:
            lat, lon = ORIGIN[0] + 0.004, ORIGIN[1]  # ~450 m north of the launch grid
            incident = await chief.post(
                "/incidents",
                {
                    "name": "Acceptance: missing hiker",
                    "base": {"latitude": ORIGIN[0], "longitude": ORIGIN[1]},
                    "operating_radius_m": 5000.0,
                },
                expect=201,
            )
            context["incident"] = incident["id"]
            d_lat, d_lon = 0.0018, 0.0027  # ~400 m x 400 m
            ring = [
                [lon - d_lon, lat - d_lat],
                [lon + d_lon, lat - d_lat],
                [lon + d_lon, lat + d_lat],
                [lon - d_lon, lat + d_lat],
                [lon - d_lon, lat - d_lat],
            ]
            area = await chief.post(
                "/search-areas",
                {
                    "incident_id": incident["id"],
                    "name": "Sector A",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "priority": 3,
                },
                expect=201,
            )
            team = await chief.post(
                "/groups", {"name": "Team A", "aircraft_ids": group}, expect=201
            )
            for aircraft_id in group:
                report = await op1.post(f"/aircraft/{aircraft_id}/preflight")
                if not report["ready"]:
                    raise AssertionError(f"preflight blocks {aircraft_id}: {report['findings']}")
            armed = await op1.command("arm", group)
            if set(states(armed).values()) - {"acked", "verified"}:
                raise AssertionError(f"arm: {reasons(armed)}")

            async def all_armed() -> bool:  # as an operator waits for the arm to show
                fleet = await op1.fleet()
                return all((fleet[a]["telemetry"] or {}).get("armed") is True for a in group)

            await until(all_armed, 30, "the group armed")
            await asyncio.sleep(1.0)  # the station's minimum interval between commands
            takeoff = await op1.command("takeoff", group, altitude_relative_m=40.0)
            if set(states(takeoff).values()) - {"acked", "verified"}:
                raise AssertionError(f"takeoff: {reasons(takeoff)}")

            async def airborne() -> bool:
                fleet = await op1.fleet()
                return all(
                    (fleet[a]["telemetry"] or {}).get("in_air") is True
                    and ((fleet[a]["telemetry"] or {}).get("altitude_relative_m") or 0) > 20
                    for a in group
                )

            await until(airborne, 90, "the group airborne above 20 m")
            mission = await chief.post(
                "/missions",
                {
                    "incident_id": incident["id"],
                    "name": "Sector A sweep",
                    "kind": "area_search",
                    "search_area_id": area["id"],
                    "default_altitude_relative_m": 60.0,
                },
                expect=201,
            )
            context["mission"] = mission["id"]
            plan = await chief.post(
                f"/missions/{mission['id']}/plan",
                {
                    "pattern": "parallel_track",
                    "spacing_m": 40.0,
                    "group_id": team["id"],
                    "second_pass": False,
                },
            )
            started = await op1.command("mission_start", group, mission_id=mission["id"])
            if set(states(started).values()) - {"acked", "verified"}:
                raise AssertionError(f"mission start: {states(started)}")

            async def sweeping() -> Any:
                progress = await op1.get(f"/missions/{mission['id']}/progress")
                return progress if (progress.get("coverage") or 0) > 0.05 else None

            progress = await until(sweeping, 180, "5 % coverage")
            return (
                f"group of 8 (6 hexacopters, 2 airplanes) passed preflight, took off, and flies "
                f"a planned parallel-track search ({len(plan['tasks'])} routes, "
                f"{len(plan['conflicts'])} conflicts, clear: {plan['clear']}); coverage so "
                f"far {100 * progress['coverage']:.0f} %"
            )

        searching = await run.step(
            "3. an area search for a mixed group of 8: preflight, launch, plan, start", search
        )

        async def faults() -> str:
            lost, low, blind = group[0], group[1], group[2]
            fault = "/simulation/aircraft/{}/faults"
            await chief.post(fault.format(lost), {"link": False})
            # below the station's critical level (15 %) and the aircraft's return level (10 %)
            await chief.post(fault.format(low), {"battery_pct": 9.0})
            await chief.post(fault.format(blind), {"gps": False})

            async def raised() -> set[tuple[str, str]]:
                wanted = {
                    ("link_stale", lost),
                    ("battery_critical", low),
                    ("gps_lost", blind),
                }
                seen = {(a["kind"], a["aircraft_id"]) for a in await op1.active_alerts()}
                return wanted if wanted <= seen else set()

            await until(raised, 30, "link, battery and GNSS alerts")
            await until(
                lambda: _alert(op1, "link_lost", lost), 30, "link_lost after the lost threshold"
            )
            await asyncio.sleep(12)  # beyond the aircraft's own COM_DL_LOSS_T (10 s)
            await chief.post(fault.format(lost), {"link": True})

            async def failsafes() -> dict[str, Any] | None:
                fleet = await op1.fleet()
                modes = {
                    a: (fleet[a]["telemetry"] or {}).get("flight_mode") for a in (lost, low, blind)
                }
                live = fleet[lost]["link"] == "live"
                expected = modes[lost] in ("return", "land") and modes[low] in ("return", "land")
                landing = modes[blind] == "land" or not (fleet[blind]["telemetry"] or {}).get(
                    "in_air"
                )
                return modes if live and expected and landing else None

            modes = await until(failsafes, 60, "the aircraft's failsafes and the link back")
            await until(lambda: _no_alert(op1, "link_lost", lost), 30, "the link alert to clear")
            kinds = ", ".join(sorted({str(a.get("kind")) for a in console.alerts}))
            return (
                f"alerts raised and seen on the console ({kinds}); "
                f"failsafes: link loss -> {modes[lost]}, low battery -> {modes[low]}, "
                f"GNSS loss -> {modes[blind]}; the link recovered and its alert cleared"
            )

        if searching:
            await run.step("4. injected link loss, low battery and GNSS loss", faults)

        async def video() -> str:
            if not station.video:
                raise AssertionError("skipped: run with --video and the sim/video relay")

            async def live() -> Any:
                health = await op1.get("/video-health")
                states_ = {s["stream_id"]: s["state"] for s in health["streams"]}
                return states_ if states_ and set(states_.values()) == {"live"} else None

            streams = await until(live, 60, "every stream live at the relay")
            first = (await op1.get("/video-streams?limit=10"))["items"][0]
            view = await op1.post(f"/video-streams/{first['id']}/view")
            if not view.get("ticket"):
                raise AssertionError("no viewing ticket")
            return f"{len(streams)} streams live; viewing ticket issued for {first['name']}"

        await run.step("5. view video", video)

        async def recover() -> str:
            fleet = await chief.fleet()
            flying = [a for a in ids if (fleet[a]["telemetry"] or {}).get("in_air")]
            mine = [a for a in flying if a in ids[:TRACKED]]
            outcomes: dict[str, str] = {}
            if mine:
                outcomes |= reasons(await op1.command("return_to_launch", mine))
            others = [a for a in flying if a not in mine]
            if others:
                outcomes |= reasons(await chief.command("return_to_launch", others))
            grounded_armed = [
                a
                for a in ids
                if (fleet[a]["telemetry"] or {}).get("armed") is True
                and (fleet[a]["telemetry"] or {}).get("in_air") is False
            ]
            if grounded_armed:  # armed but never took off (a failed launch): disarm
                outcomes |= reasons(await chief.command("disarm", grounded_armed))

            async def up() -> dict[str, str]:
                fleet = await chief.fleet()
                return {
                    a[-6:]: f"in_air={t.get('in_air')} armed={t.get('armed')} "
                    f"mode={t.get('flight_mode')} link={fleet[a]['link']}"
                    for a in ids
                    if (t := fleet[a]["telemetry"] or {}).get("in_air") is not False
                    or t.get("armed") is not False
                }

            try:
                await until(lambda: _none(up), 300, "every aircraft landed and disarmed")
            except AssertionError as error:
                raise AssertionError(f"{error}; still up: {await up()}; sent: {outcomes}") from None
            return (
                f"{len(flying)} airborne aircraft returned, landed and disarmed; "
                f"all {FLEET} on the ground"
            )

        await run.step("6. return and land every aircraft", recover)
        await console.stop()

        async def records() -> str:
            await asyncio.sleep(11)  # one audit-head export interval (set to 10 s)
            chain = await chief.get("/audit/verify")
            if not chain["ok"]:
                raise AssertionError(f"audit chain: {chain}")
            if chain["exported_heads"] < 1:
                raise AssertionError("no audit head exported")
            if "incident" not in context:
                raise AssertionError("no incident to export")
            response = await http.get(
                f"/api/v1/incidents/{context['incident']}/export", headers=chief.headers
            )
            response.raise_for_status()
            archive = zipfile.ZipFile(io.BytesIO(response.content))
            manifest = json.loads(archive.read("manifest.json"))
            for name, entry in manifest["files"].items():
                if hashlib.sha256(archive.read(name)).hexdigest() != entry["sha256"]:
                    raise AssertionError(f"{name} does not match the manifest")
            rows = archive.read("telemetry.csv").count(b"\n") - 1
            events = archive.read("audit.jsonl").count(b"\n")
            closed = await http.patch(
                f"/api/v1/incidents/{context['incident']}",
                json={"status": "closed"},
                headers=chief.headers,
            )
            closed.raise_for_status()
            return (
                f"audit chain intact ({chain['events']} events, {chain['exported_heads']} "
                f"exported head(s)); export {len(response.content) / 1024:.0f} KB, "
                f"{len(manifest['files'])} files verified, {rows} telemetry rows of "
                f"{len(manifest['aircraft'])} aircraft, {events} audit events; incident closed"
            )

        await run.step("7. audit chain and incident export", records)


async def _none(check: Callable[[], Awaitable[dict[str, str]]]) -> bool:
    return not await check()


async def _alert(client: Client, kind: str, aircraft_id: str) -> bool:
    return any(
        a["kind"] == kind and a["aircraft_id"] == aircraft_id for a in await client.active_alerts()
    )


async def _no_alert(client: Client, kind: str, aircraft_id: str) -> bool:
    return not await _alert(client, kind, aircraft_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8150)
    parser.add_argument("--video", action="store_true", help="the sim/video relay runs here")
    parser.add_argument("--report", type=Path, default=None, help="write a JSON report")
    parser.add_argument("--keep", action="store_true", help="keep the station's data directory")
    args = parser.parse_args()

    station = Station(args.port, args.video)
    station.start()
    run = Run()
    started = time.monotonic()
    try:
        asyncio.run(scenario(station, run))
    finally:
        station.stop(keep=args.keep)
    failed = [s for s in run.steps if not s.ok]
    print(
        f"\n{len(run.steps) - len(failed)}/{len(run.steps)} steps passed "
        f"in {time.monotonic() - started:.0f} s"
        + (f"; data kept in {station.data_dir}" if args.keep else "")
    )
    if args.report:
        args.report.write_text(
            json.dumps(
                {
                    "passed": not failed and len(run.steps) == 7,
                    "steps": [s.__dict__ for s in run.steps],
                },
                indent=2,
            )
        )
    return 1 if failed or len(run.steps) < 7 else 0


if __name__ == "__main__":
    raise SystemExit(main())
