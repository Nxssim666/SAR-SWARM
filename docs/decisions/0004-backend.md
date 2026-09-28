# 0004. Backend: Python, FastAPI, asyncio

- Status: Accepted
- Date: 2026-09-28

## Context

The fleet service ingests telemetry from up to 50 aircraft at 2–10 Hz, which is at most about
500 messages per second. It serves REST and WebSocket to a handful of consoles, runs the command
pipeline and talks to PX4 (MAVLink/MAVSDK) and ROS 2. It must be maintainable by a small team
that already writes the onboard software in Python.

## Decision

- **Python ≥ 3.12**, a single asyncio process. Containers use Python 3.12, matching ROS 2 Jazzy
  on Ubuntu 24.04. CI also tests 3.14, the development host's version.
- **FastAPI** for REST and WebSocket, and **Pydantic v2** for every boundary model. Models
  forbid unknown fields, following the onboard `mission_file.py` rule that a typo must not
  silently fall back to a default.
- **uvicorn** as the ASGI server, and **pydantic-settings** for configuration through
  `SARGCS_*` environment variables.
- **uv** for dependencies, with a committed `uv.lock` for reproducible images.
- **ruff** for lint and format, and **mypy --strict**.
- Module layout (grows from M1):

  ```
  fleet_service/
    api/        REST routers, WebSocket gateway, request/response models
    domain/     pure logic: aircraft state, command rules, search patterns, deconfliction
    services/   fleet registry, command dispatcher, alert engine, audit, missions
    drivers/    vehicle drivers (mock, mavsdk, bus-backed swarm bridge)   (ADR 0010)
    bus/        event bus interface and implementations                (ADR 0008)
    db/         SQLAlchemy models, repositories, migrations            (ADR 0007)
    auth/       accounts, sessions, permissions                        (ADR 0009)
  ```
- Live aircraft state is **held in memory** and is authoritative for the running process.
  The database gives durability, replay and audit.

## Alternatives considered

- **Go:** fast and deploys as a single binary, but MAVSDK-Go is unofficial, the ROS 2 client
  (rclgo) is immature, and it's a different language from the onboard code.
- **Rust:** excellent MAVLink crates, but the ROS 2 client (rclrs/r2r) is early and iteration
  is slower for a small team.
- **TypeScript/Node:** would share types with the console, but the MAVSDK and ROS 2 bindings
  are weaker, and the geospatial libraries (shapely, pyproj) are Python's strength.
- **Java/Kotlin (Spring):** mature, but heavy for a field laptop, and far from the robotics stack.

## Consequences

- Throughput is ample for this scale. CPU-heavy work such as pattern generation or 4D conflict
  checks over long plans goes to a process pool if it exceeds its latency budget (measured in M4/M5).
- There is one process and one writer, which keeps consistency simple (ADR 0007). Scaling past a
  single host is explicitly out of scope (ADR 0002, A1).
- mavsdk_server and grpcio wheels must exist for the target platforms. This is checked in M2.
