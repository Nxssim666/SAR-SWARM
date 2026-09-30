# Architecture

Ground control system for a civilian search-and-rescue drone fleet: up to 50 PX4 aircraft
(fixed-wing and hexacopters, some running the onboard `swarm_sar` companion), a few operators
with different roles, one field ground station, and no cloud. This page is the living overview.
The reasons behind it are in [`decisions/`](decisions/0001-record-architecture-decisions.md).

Status: **M4**. The fleet service is built through its live core, its MAVLink link and its
swarm link:

- persistent domain, auth/RBAC and a hash-chained audit trail;
- the in-process bus, the fleet registry, and the mock driver in simulation mode;
- the MAVLink driver on MAVSDK v4, one hub per connection, with aircraft matched by system
  id (ADR 0022);
- the swarm link: `sar_gcs_bridge` (ROS 2) and NATS, swarm-wide area missions, and aircraft
  with both links merged and routed (ADR 0024, ADR 0025);
- the command pipeline, control leases and alerts;
- mission planning: search patterns, area split, deconfliction, GCS-planned missions
  uploaded and read back, progress and coverage, points of interest (ADR 0028-0031);
- REST and WebSocket APIs ([`api/README.md`](api/README.md)).

PX4 SITL (5 aircraft, and scale runs), the simulated swarm with the bridge, and mock video
run in CI (ADR 0023, ADR 0026). The operator console is usable: map, list, selection, commands
with held confirmation, control leases and alerts (ADR 0027), and incidents, search areas,
mission planning and tasking, and points of interest (ADR 0032). MediaMTX in the product (M5) is
designed but not built yet; there is no Gazebo tier (ADR 0033). Measured figures are in
[`../PLAN.md`](../PLAN.md).

## System context

```mermaid
flowchart LR
  subgraph People
    OP[Operators<br/>laptops / tablets]
    SUP[Supervisor /<br/>incident commander]
    OBS[Observers<br/>ground-team liaison]
    SP[Safety pilot<br/>RC + optional QGroundControl]
  end
  subgraph GS[Ground station host - one per incident]
    GCS[SAR ground control system]
  end
  subgraph Aircraft
    PX4[PX4 aircraft<br/>fixed-wing / hexa]
    SW[Swarm multicopters<br/>PX4 + swarm_sar companion]
  end
  OP & SUP & OBS -- HTTPS / WSS / WebRTC over LAN --> GCS
  GCS -- MAVLink 2 over radio / IP --> PX4
  GCS -- MAVLink telemetry --> SW
  GCS -- ROS 2 /swarm/v2/* --> SW
  PX4 & SW -- RTSP / RTP / SRT video --> GCS
  SP -. RC link, independent .-> PX4 & SW
  SP -. MAVLink via mavlink-router .-> GCS
```

The aircraft's own failsafes remain the primary safety layer (ADR 0002, S1). The GCS supports
operators; it is never a single point of failure for flight safety.

## Containers

```mermaid
flowchart TB
  B[Browser: fleet-console<br/>React, MapLibre, WHEP player]
  subgraph Host[Ground station host - Docker Compose]
    C[console / gateway<br/>Caddy: static console, TLS, reverse proxy]
    F[fleet-service<br/>FastAPI, asyncio]
    DB[(ops.db<br/>SQLite WAL)]
    TS[(telemetry.db<br/>SQLite WAL)]
    N[[nats]]
    M[mediamtx - M5]
    R[sar_gcs_bridge<br/>ROS 2 Jazzy, reuses swarm_sar codec]
    MR[mavlink-router<br/>sample config]
  end
  B -- HTTPS /api, WSS /api/v1/ws --> C --> F
  B -- WHEP / WebRTC --> C --> M
  F --- DB & TS
  F <--> N <--> R
  F <-- MAVLink UDP<br/>MAVSDK v4 in-process --> MR
  MR <-- radio --> AC[aircraft]
  R <-- DDS --> AC
  M <-- RTSP/RTP/SRT --- AC
  F -- health API --> M
```

## Fleet service internals

```
api/        REST routers + WebSocket gateway          ── only layer that knows HTTP
services/   fleet registry (live state, link state), command dispatcher, control leases,
            alert engine, mission service, audit writer, telemetry recorder
domain/     pure, fully unit-tested logic: command rules & preconditions, search patterns,
            deconfliction, geo validation, units/frames
drivers/    VehicleDriver implementations: mock (M1), mavlink via MAVSDK v4 (M2a),
            swarm via the bridge over NATS, and linked (mavlink + swarm) (M2b)
bus.py      EventBus: in-process fan-out to consoles (NATS only at the adapter boundary, ADR 0024)
db/         SQLAlchemy models, repositories, Alembic migrations
auth/       accounts, sessions, permissions
```

Dependencies point downward. `domain/` imports none of the others, so it is testable
without I/O, just as the onboard `swarm_sar.core` imports neither ROS nor the simulator.

## Key flows

### Telemetry: aircraft to console

```mermaid
sequenceDiagram
  participant AC as Aircraft
  participant D as Driver
  participant REG as Fleet registry (memory)
  participant REC as Telemetry recorder
  participant WS as WS gateway
  participant UI as Console
  AC->>D: MAVLink / DroneState (2–10 Hz)
  D->>REG: TelemetrySample (canonical units, ADR 0014)
  REG->>REG: merge sources, derive link state (live/stale/lost), evaluate alerts
  REG-->>REC: sample (downsampled to 1 Hz) → batch insert telemetry.db each second
  REG-->>WS: latest value per aircraft (coalesced)
  WS-->>UI: envelope {topic, seq, ts, data} at the client's requested rate
```

### Command: operator to aircraft

```mermaid
sequenceDiagram
  participant UI as Console
  participant API as Command API
  participant P as Pipeline
  participant D as Driver
  participant AU as Audit
  UI->>API: POST command {command_id, aircraft_ids, action}
  API->>P: authorize (permission, lease, capability) · preconditions
  alt risky or bulk
    P-->>UI: 428 + server summary + confirmation token
    UI->>API: same request + token (deliberate second action)
  end
  P->>AU: requested
  P->>D: execute (per aircraft, rate-limited)
  D-->>P: ack / nack(reason) / timeout
  P->>AU: outcome per aircraft
  P-->>UI: per-aircraft results; effect verified later from telemetry (mode change) or alert
```

## Budgets (verified in M5; the load tests fail if they are exceeded)

| Metric | Budget at 50 aircraft × 10 Hz, 6 consoles |
|---|---|
| Telemetry ingest → console, p95 | ≤ 250 ms (excluding radio latency) |
| Command accepted → dispatched, p95 | ≤ 100 ms |
| Link-state change → alert on console, p95 | ≤ 1 s after the threshold |
| Fleet-service CPU | ≤ 1 core average |
| Fleet-service RSS (MAVSDK runs in-process) | ≤ 500 MB |
| Console map frame rate | ≥ 30 fps on the reference laptop |
| WebSocket bandwidth per console | ≤ 150 KB/s at the default coalescing rate |

## Failure behaviour

| Failure | Behaviour |
|---|---|
| Aircraft link degraded or lost | The link state goes to *stale* then *lost*, raising an alert. Only HOLD, RTL or LAND are accepted. The aircraft follows its own PX4 data-link-loss action. |
| Console disconnects | The lease is kept for 60 s, then *orphaned* and supervisors are alerted. The aircraft continue their task, and the GCS issues nothing automatically. |
| Fleet service crashes or restarts | The aircraft are unaffected. On restart, state is reloaded from `ops.db`, links reconnect and live state resyncs from the aircraft (M6). |
| NATS down | Swarm telemetry goes stale, then lost, with alerts; swarm commands time out (never guessed). Direct MAVLink aircraft are unaffected, because their drivers run in-process. The link reconnects by itself (tested with a restarted nats-server). |
| Disk full | Telemetry recording pauses with an alert, and operational writes keep a reserved margin (M6). |
| Clock skew | The server is authoritative, and consoles show skew above 2 s (implemented in M0). |
| Video relay down | Streams show *unavailable* with the reason, and flight control is unaffected. |

## Repository map

| Path | What |
|---|---|
| `fleet-service/` | Backend (Python, FastAPI). See its `README.md`. |
| `fleet-console/` | Operator console (React, TypeScript). See its `README.md`. |
| `deploy/` | Compose file and gateway config for the ground station |
| `sim/` | PX4 SITL (SIH) fleets for CI and scale runs, link emulator, swarm simulation, mock video (no Gazebo, ADR 0033) |
| `src/` | ROS 2 colcon workspace: the onboard `swarm_sar` packages (unchanged) and `sar_gcs_bridge` (M2b) |
| `docs/` | This page, ADRs, API specs (M1), runbooks |
| `scripts/check.py` | Runs every lint, type check, test and build |
