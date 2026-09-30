"""
The fleet service for the console's E2E tests and local demos: simulation mode (every
aircraft simulated, ADR 0021), a fresh data directory, one user per role, N aircraft and a
group, and an open incident around the fleet (for mission planning). Run in the fleet
service's environment:

    python -m uv --directory ../fleet-service run python ../fleet-console/e2e/backend.py \
        --port 8123 --aircraft 20 [--video]

With ``--video``, the first four aircraft get video streams from the mock relay of
``sim/video`` (MediaMTX on this host, started separately), and the station monitors it.

The accounts are test accounts of this throwaway station (TEST_PASSWORD below); the data
directory is deleted and recreated on every start. Never point this at a real station.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

TEST_PASSWORD = "e2e-console-pass"  # noqa: S105 - test accounts of a throwaway station
USERS = [
    ("op1", "Operator One", "operator"),
    ("op2", "Operator Two", "operator"),
    ("sup", "Supervisor", "supervisor"),
    ("obs", "Observer", "observer"),
]


def fleet_service(*args: str, env: dict[str, str], stdin: str | None = None) -> None:
    subprocess.run(  # noqa: S603 - our own CLI
        [sys.executable, "-m", "fleet_service", *args],
        env=env,
        input=stdin,
        text=True,
        check=True,
    )


def seed(base: str, aircraft: int, video: bool) -> None:
    with httpx.Client(base_url=base, timeout=10.0) as http:
        token = http.post(
            "/api/v1/auth/login", json={"username": "chief", "password": TEST_PASSWORD}
        ).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        for username, name, role in USERS:
            http.post(
                "/api/v1/users",
                json={
                    "username": username,
                    "display_name": name,
                    "role": role,
                    "password": TEST_PASSWORD,
                },
                headers=headers,
            ).raise_for_status()
        ids = []
        for i in range(1, aircraft + 1):
            airframe = "fixed_wing" if i % 5 == 0 else "multirotor_hexa"
            prefix = "FW" if airframe == "fixed_wing" else "HX"
            response = http.post(
                "/api/v1/aircraft",
                json={"callsign": f"{prefix}-{i:02d}", "airframe": airframe},
                headers=headers,
            )
            response.raise_for_status()
            ids.append(response.json()["id"])
        http.post(
            "/api/v1/groups",
            json={"name": "Team North", "aircraft_ids": ids[: max(1, len(ids) // 4)]},
            headers=headers,
        ).raise_for_status()
        if video:
            for i, aircraft_id in enumerate(ids[:4], start=1):
                http.post(
                    "/api/v1/video-streams",
                    json={
                        "aircraft_id": aircraft_id,
                        "name": f"HX-{i:02d} camera",
                        "source_url": f"rtsp://127.0.0.1:8554/aircraft-{i:02d}",
                        "relay_path": f"aircraft-{i:02d}",
                    },
                    headers=headers,
                ).raise_for_status()
            http.post(  # VP9, for browsers without H.264 (sim/video/mediamtx.yml)
                "/api/v1/video-streams",
                json={
                    "aircraft_id": ids[4] if len(ids) > 4 else None,
                    "name": "Test pattern VP9",
                    "source_url": "rtsp://127.0.0.1:8554/test-vp9",
                    "relay_path": "test-vp9",
                    "codec": "unknown",
                },
                headers=headers,
            ).raise_for_status()
        http.post(
            "/api/v1/incidents",
            json={
                "name": "Missing hiker",
                "base": {"latitude": 47.3977, "longitude": 8.5456},  # the simulated fleet's site
                "operating_radius_m": 5000.0,
            },
            headers=headers,
        ).raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--aircraft", type=int, default=20)
    parser.add_argument("--data-dir", type=Path, default=None, help="default: a temp dir per port")
    parser.add_argument("--video", action="store_true", help="streams from the sim/video relay")
    args = parser.parse_args()
    data_dir: Path = args.data_dir or Path(tempfile.gettempdir()) / f"sargcs-e2e-{args.port}"

    shutil.rmtree(data_dir, ignore_errors=True)
    if data_dir.exists():
        raise SystemExit(f"cannot clear {data_dir}: is another test station using it?")
    data_dir.mkdir(parents=True)
    env = os.environ | {
        "SARGCS_SIMULATION": "true",
        "SARGCS_DATA_DIR": str(data_dir),
        "SARGCS_PORT": str(args.port),
        "SARGCS_STATION_NAME": "e2e",
    }
    if args.video:
        env["SARGCS_MEDIAMTX_API_URL"] = "http://127.0.0.1:9997"
    fleet_service("db", "upgrade", env=env)
    fleet_service(
        "create-admin", "--username", "chief", "--password-stdin", env=env, stdin=TEST_PASSWORD
    )

    server = subprocess.Popen([sys.executable, "-m", "fleet_service"], env=env)
    base = f"http://127.0.0.1:{args.port}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/api/v1/health", timeout=1.0).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        server.terminate()
        raise SystemExit("the fleet service did not start")
    seed(base, args.aircraft, args.video)
    print(f"e2e backend ready on {base} with {args.aircraft} aircraft", flush=True)  # noqa: T201

    def stop(*_: object) -> None:
        server.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return server.wait()


if __name__ == "__main__":
    sys.exit(main())
