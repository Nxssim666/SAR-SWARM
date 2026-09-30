# PLAN: SAR fleet ground control

Milestones, in order. **After each milestone:** run all checks (`python scripts/check.py`),
commit, update this file and `CLAUDE.md`, then **stop and report**: what was built, how to run
it, test results, what's not done, and the recommended next step. Don't start the next
milestone without confirmation.

Every milestone ships its own unit, integration, contract, E2E and load tests where relevant
(ADR 0015). Every decision or assumption not settled by the user goes into an ADR.

Legend: `[x]` done and verified · `[ ]` to do · *(unverified locally)* means it can't run on
the development host and is checked in CI.

## Status

| Milestone | State |
|---|---|
| M0 Architecture, ADRs, scaffold | **Done** (2026-09-28) |
| M1a Data model, persistence, auth/RBAC, REST, OpenAPI | **Done** (2026-09-28) |
| M1b Live fleet core: registry, mock driver, commands, leases, WebSocket | **Done** (2026-09-28) |
| M2a PX4 SITL harness + MAVLink driver (1–5 aircraft) | **Done** (2026-09-28); `sitl` and `ci` green on GitHub |
| M2b Scale and swarm: SIH 25/50, NATS, ROS 2 bridge, mock video | **Done** (2026-09-30); swarm acceptance green, tracking verified to 25 in CI; **50 SIH deferred to M5/M6 field hardware** (user) |
| M3 Console MVP | **Done** (2026-09-30); 7/7 E2E, 46–54 fps with 50 aircraft on this PC's GPU |
| M4 Mission planning, patterns, bulk tasking, deconfliction, alerts | **Done** (2026-09-30); E2E 3/3 (plan, start, complete), SITL battery and geofence |
| M5 Video, roles, audit viewer, multi-operator, load tests | — |
| M6 Hardening, degraded comms, packaging, runbooks, acceptance | — |

M1 and M2 from the original brief are each split into two stop points (a and b), because each
is several weeks of work and a review checkpoint in the middle lowers risk.

## Decisions needed from the user

1. ~~Before M2a: where PX4 SITL runs.~~ **Decided: CI only** (GitHub Actions; ADR 0023),
   on <https://github.com/Nxssim666/SAR-SWARM>. CI results are read from the public checks
   API (annotations); job logs and artifacts need a signed-in account.
2. **The field region(s).** Zurich (the simulator's site) and Kramatorsk are prepared, with
   the Copernicus GLO-30 DEM for terrain (ADR 0030); confirm or change them.
3. ~~Gazebo tier (M2c).~~ **Decided: dropped** (the user, 2026-09-30; ADR 0033). Flight is
   tested on PX4 SIH and the mock fleet, video with mock streams.
4. **Any time:** confirm or override the stack (ADRs 0004–0017) and assumptions A1–A11 (ADR 0002).

---

## M0: Architecture, stack, ADRs, repo scaffold, dev environment ✅

**Goal:** an agreed architecture and a working, tested skeleton to build on.

- [x] Git initialized. The existing onboard code is committed unchanged as the baseline.
- [x] Onboard baseline on Python 3.14: 484 passed, 3 skipped (ROS-only), no failures.
- [x] ADRs 0001–0017 (`docs/decisions/`): scope, safety and assumptions, onboard
      relationship, and every stack choice with alternatives.
- [x] `docs/architecture.md`: context, containers, flows, budgets, failure behaviour.
- [x] `fleet-service/`: uv project, FastAPI factory, settings, JSON logging, `/api/v1/health`,
      `/api/v1/version`, 7 tests, ruff + mypy strict clean, Dockerfile.
- [x] `fleet-console/`: React 19 + TypeScript 6 + Vite 8 shell with a live connection and
      clock-skew badge, 5 tests, ESLint strict + Prettier clean, production build, Dockerfile.
- [x] `deploy/compose.yaml` + `Caddyfile` (YAML syntax checked; *compose and Caddy
      unverified locally*).
- [x] `.github/workflows/ci.yml` mirroring `scripts/check.py`, plus an image build job
      (*unverified locally*).
- [x] `scripts/check.py`: one cross-platform command for all checks.
- [x] `docs/runbooks/dev-setup.md`, new root `README.md`. The onboard README moved to
      `src/swarm_sar/README.md`.
- [x] `CLAUDE.md`, `PLAN.md`.

**Known gaps:** Docker, Caddy and CI were not executed on this host. Node is used from a
portable `.tools/` venv here.

---

## M1a: Data model, persistence, auth/RBAC, REST CRUD, OpenAPI ✅

**Goal:** the fleet service's persistent domain and a secured, documented REST API. No live
aircraft yet.

**Built** (2026-09-28)

- [x] Domain model in `ops.db`: users, sessions, aircraft, groups, incidents, search areas,
      geofences, missions, waypoints, tasks, video streams, audit events, plus the schema of
      alerts, commands (with per-aircraft targets) and control leases, whose behaviour is M1b.
      `telemetry.db` holds `telemetry_samples` (schema only; the recorder is M1b).
- [x] SQLite WAL through SQLAlchemy 2 async. One connection per file, pragmas, and a
      `UTCDateTime` type that rejects naive datetimes (ADR 0019).
- [x] Alembic with one script directory per database and sequential revisions. Migrations
      **run at startup**, and `ops.db` is **backed up** first when it holds data (ADR 0016/0019).
- [x] `domain/geo.py`:
  - [x] Explicit-key points, and validated GeoJSON polygons (closed, 3–256 vertices, valid,
        no holes, no antimeridian crossing, normalized counter-clockwise).
  - [x] Geodesic area and distance with pyproj.
  - [x] The **operating-area check that catches swapped lat/lon**.
- [x] Auth:
  - [x] Argon2id hashing, kept out of transactions, with rehash on login.
  - [x] Opaque `sgcs_` tokens stored as SHA-256. 4 h idle and 12 h absolute expiry.
  - [x] Per-user and per-IP login rate limits.
  - [x] Timing-equalized unknown users.
  - [x] `create-admin` CLI.
- [x] Permission catalogue v1 (ADR 0018). `requires()` publishes `x-permission` and enforces
      it from one place.
- [x] REST v1, 54 operations: auth, users, aircraft, groups, incidents, search areas,
      geofences, missions, waypoints (PUT replaces the route), tasks, video streams, audit.
      - RFC 9457 problem+json with stable `urn:sar-gcs:problem:*` types.
      - Cursor pagination, strict input types, and PATCH with explicit-null semantics.
- [x] Consistency rules:
  - [x] Closed incidents are read-only.
  - [x] Base and radius changes can't strand geometry.
  - [x] Only empty incidents can be deleted.
  - [x] Area missions need a search area in the same incident.
  - [x] Swarm missions are capped at 64 waypoints.
  - [x] Plans are frozen outside draft or planned.
  - [x] Only drafts can be deleted.
  - [x] Tasks need a matching link.
  - [x] Aircraft in use can't be deleted.
  - [x] Users are deactivated, never deleted.
  - [x] The last admin is protected.
  - [x] Video source passwords are redacted.
- [x] **Hash-chained audit** in the same transaction as each change *(moved forward from
      M1b)*:
  - [x] `GET /audit`.
  - [x] `fleet-service audit-verify` (exit code 1 when broken; prints the head for external
        recording).
- [x] `fleet-service export-openapi` → `docs/api/openapi.json` (committed), with a drift test.
- [x] 405 responses carry a complete `Allow` header, built from the OpenAPI paths.
- [x] Console: `npm run gen:api` generates `src/api/generated/schema.d.ts` from the spec, with
      a Vitest drift test *(moved forward from M3)*. `system.ts` uses the generated types.
- [x] Docs: `docs/api/README.md`, ADR 0018 (permissions), ADR 0019 (database access).

**Tests:** fleet-service has **201 tests plus 54 Schemathesis operation runs**, all passing:

- Unit: ids, geo with Hypothesis (including the swapped-coordinate property), permissions,
  rate limiter, tokens, passwords.
- Storage: migrations, backup-before-migrate, no model/migration drift, audit tamper
  detection.
- API: every resource and every consistency rule, including session expiry, revocation and
  rate limiting.
- The **authorization matrix**: all 51 protected operations × no token and every role.
- Contract: Schemathesis in positive and negative modes, checking status codes, content types,
  schemas, `Allow` headers, rejection of negative data, and authentication. Only
  `positive_data_acceptance` is excluded; the reason is documented in the test.
- CLI.

**Manual end-to-end** (live server):

1. The CLI created an admin.
2. The admin created an operator and an observer.
3. They opened an incident, drew a search area, registered an aircraft, planned a mission with
   4 waypoints and assigned the aircraft.
4. Swapped coordinates returned 422 `outside-operating-area`.
5. The observer got 403 on POST, and the operator got 403 on the audit log.
6. `audit-verify` passed with 12 events. After one audit row was edited in SQLite, it reported
   `BROKEN at seq=7` with exit code 1.

**Known gaps**

- `/api/v1/docs` (Swagger UI) loads its assets from `cdn.jsdelivr.net`. It is blank offline,
  and the gateway's CSP would block it. It's a developer aid, not the operator console. Fix in
  M6: vendor swagger-ui-dist, or serve docs only in development.
- `openapi-typescript` 7 declares a TypeScript 5 peer. The console pins it to our TypeScript 6
  with an npm `overrides` entry; the drift test and typecheck prove the output. Revisit when
  v8 ships.
- Truncation of the *end* of the audit chain is only detectable against a head recorded
  elsewhere. M5/M6 will add periodic head export.
- Docker image builds and CI remain *unverified locally* (no Docker on this host).

---

## M1b: Live fleet core (mock driver, live state, commands, leases, alerts, WebSocket) ✅

**Goal:** live aircraft state and safe command handling end to end, against simulated aircraft.

**Built** (2026-09-28; ADR 0020, ADR 0021)

- [x] `bus.py`: in-process `EventBus` with reliable subscriptions (broken on overflow, never
      lossy) and latest-value subscriptions (ADR 0008).
- [x] `drivers/`: the `VehicleDriver` interface and canonical `TelemetrySample`.
  - [x] **Mock driver:** multirotor and fixed-wing kinematics, modes and refusals, PX4-like
        failsafes (link 10 s → return, GNSS lost → land, battery 10 % → return and 5 % →
        land), fault injection, seeded.
  - [x] **Simulation mode** is station-wide (`SARGCS_SIMULATION`, `simulation.env`) and never
        mixed with real links.
- [x] **Fleet registry and manager:** live state, link live/stale/lost/offline, drivers kept
      in step with the aircraft registry, telemetry history at 1 Hz
      (`GET /aircraft/{id}/telemetry`), `GET /fleet/state`.
- [x] **Command pipeline** (ADR 0011/0020): arm, disarm, takeoff, hold, resume, return, land
      and goto.
  - [x] Idempotent `command_id`.
  - [x] Per-aircraft authority, capability, link, state and limit rules, including goto
        geofences.
  - [x] **428 with a server summary and an HMAC token bound to the request**, re-checked at
        dispatch.
  - [x] Concurrent dispatch with a timeout, per-aircraft outcomes, and effect verification
        from telemetry.
- [x] **Control leases:** take, release, handover with a 30 s expiry, supervisor assignment
      with a reason, presence-based orphaning with an alert and no command.
- [x] **Alerts:** link, battery, GNSS, orphaned control, command timeout, unverified effect;
      acknowledge; audited raise and clear.
- [x] **WebSocket** `/api/v1/ws`:
  - [x] Auth as the first message; snapshots, then events.
  - [x] Coalesced telemetry at the client's rate; reliable topics close with 4429 rather
        than skip events.
  - [x] Revoked sessions closed immediately; idle clients closed.
- [x] **AsyncAPI 3** generated to `docs/api/asyncapi.json` (JSON, not YAML; ADR 0020), with a
      drift test.
- [x] Permissions `aircraft.hold`, `aircraft.command`, `alerts.ack` (operator) and
      `control.override` (supervisor). Migrations 0002 for ops and telemetry.
- [x] Scripts: `scripts/m1b_acceptance.py` and `scripts/load_smoke.py`.

**Tests:** fleet-service has **367 tests plus Schemathesis over 69 operations**, all
passing:

- One test per ADR 0011 rule.
- The command rules, row by row.
- Mock physics and failsafes.
- Bus delivery classes.
- Leases and handover; alerts.
- 15 WebSocket protocol tests, with every message validated against the AsyncAPI models.
- One real-loop test with 50 aircraft.

The authorization matrix covers every new operation.

**Acceptance** (live server, simulation mode): **passed.**

- 5 aircraft (3 hexa, 2 fixed-wing): take control, then arm, takeoff, hold and return as
  confirmed bulk commands.
- All 5 airborne after 13 s, landed and disarmed 33 s after the return.
- Every command acked by all 5, with 20 effects verified from telemetry.
- 132 WebSocket messages with no sequence gap.
- `audit-verify` intact over 47 events.

**Load smoke** (60 s, 50 simulated aircraft at 10 Hz, 3 consoles at 4 Hz; the GCS only, no
radio links):

| Measure | Result |
|---|---|
| Newest-telemetry age at the console (p50 / p95 / p99) | 55 / 110 / 120 ms |
| Batches per second | 3.8 |
| Bandwidth per console | 118 KB/s (budget ≤ 150 KB/s) |
| Aircraft seen by every console | all 50 |
| Server RSS / CPU after 191 s | 131 MB / 12.5 s |

**Known gaps**

- Commands answer synchronously within the 5 s timeout (ADR 0020). This must be revisited
  if real links need longer (M2).
- Presence, pending effect verifications and confirmation tokens live in memory and are
  lost on restart (resync in M6).
- The mock driver models no dynamics, wind, terrain or partial packet loss (ADR 0021).
  Vehicle realism comes with PX4 SITL in M2.
- The API docs page still loads Swagger UI from a CDN (M6).

---

## M2a: PX4 SITL harness and MAVLink driver (1–5 aircraft) ✅

**Goal:** the fleet service tracks and commands real PX4 SITL vehicles.

**Decisions** (the user): SITL runs **in CI only**, and the MAVLink driver uses **native
MAVSDK v4** (in-process, no `mavsdk_server`). See ADR 0022 and ADR 0023.

**Built** (2026-09-28)

- [x] **`drivers/mavlink.py`** (ADR 0022):
  - [x] One hub (MAVSDK instance) per connection, and aircraft matched by **MAVLink system
        id**, so one port or radio carries the whole fleet.
  - [x] Telemetry subscriptions become canonical samples, emitted only when new data
        arrived. NaN becomes `null`, and a position without a 3D fix is `null`.
  - [x] PX4 modes mapped, with a new `offboard` mode. A reposition shows as `goto` until
        arrival, and RESUME resends a held reposition.
  - [x] Commands: arm, disarm, takeoff, hold, resume, return, land and goto (home AMSL plus
        relative altitude). An aircraft's refusal becomes a nack with its reason; no answer
        becomes a timeout.
  - [x] Hubs open with the first aircraft on a connection and close, releasing the port,
        with the last one.
- [x] **Fleet manager:** outside simulation mode, a MAVLink driver per linked aircraft;
      changing the connection or system id replaces it. `SARGCS_MAVLINK_LINKS` switches links
      off (unit tests).
- [x] **API:** `mavlink_connection` requires `mavlink_system_id` (422 `system-id-required`).
- [x] **`sim/sitl/compose.yaml`:** five PX4 SIH instances (3 hexa, 1 airplane, 1 quad),
      `px4io/px4-sitl:v1.18.0-rc1` pinned by digest, homes 25 m apart, failsafe and
      failure-injection parameters (ADR 0023).
- [x] **`sim/linkem.py`:** UDP link emulator with loss, latency, jitter and blackout; Python
      API and CLI.
- [x] **`.github/workflows/sitl.yml`:** starts the fleet, runs `pytest -m sitl`, and uploads
      the JUnit results and PX4 logs.
- [x] `deploy/mavlink-router/main.conf`: a sample radio fan-out to the fleet service and a
      backup QGroundControl *(unverified)*.
- [x] Docs: ADR 0022, ADR 0023, `sim/README.md`, `docs/runbooks/simulation.md`.

**Tests**

- **Local** (any OS, in `scripts/check.py`): fleet-service has **401 tests plus
  Schemathesis over 69 operations**, all passing; 6 SITL tests are skipped locally.
  - MAVLink driver unit tests against stand-in plugins.
  - **MAVLink loopback tests: the real MAVSDK v4 binding** against minimal PX4-like pymavlink
    vehicles, through REST and the command pipeline. They cover:
    - two system ids on one port;
    - a full arm → return flight, every step verified;
    - an aircraft's refusal with its reason;
    - an unanswered command timing out;
    - relinking an aircraft, and releasing the port.
  - Link emulator tests.
  - The system-id API rule.
- **CI, against PX4 v1.18.0-rc1 SIH** (`tests/integration/test_sitl.py`): **6/6 passing**.
  Times are from the first runs, in which each test passed.
  1. five aircraft tracked on one port by system id (3 s);
  2. hexacopter full tasking: arm, takeoff, goto, hold, return, landing, all verified (84 s);
  3. confirmed bulk takeoff and hold of three hexacopters (11 s);
  4. fixed-wing takeoff and return;
  5. link loss through the emulator: stale then lost alerts; PX4 held 5 s, returned and
     landed on its own; link live again (53 s);
  6. GNSS failure injection: no fix, position `null`, `gps_lost` alert (42 s).

**Acceptance: passed.** On 2026-09-28, commit `4989a3e` ran green on GitHub in both workflows:
`sitl` (6/6) and `ci`:

- onboard, on Python 3.12 and 3.14;
- fleet-service, on Python 3.12 and 3.14;
- console;
- container images.

The `ci` workflow ran for the first time here; before, it had only been checked locally.

**Found by the first CI runs, and fixed**

- The link emulator leaked a socket when a new vehicle's first datagrams came in a burst.
  It now opens one uplink per vehicle and keeps a backlog meanwhile (regression test).
- The v1.18.0-rc1 SIH airplane cannot finish a runway takeoff. Four variants were measured
  in parallel, and the airplane now uses a launch-style takeoff (ADR 0023).
- Job logs need a signed-in account even on a public repository. The workflow therefore
  reports failed tests and PX4 console tails as annotations (`sim/sitl/annotate.py`).

**Moved out of M2a**

- Mission upload with read-back verification, and geofence upload → M4, with mission
  planning (the MAVSDK mission and geofence plugins).
- Battery-drain and geofence-breach injection in SITL → M4.
- Gazebo (tier 1) → M2b, then M2c; later dropped by the user (ADR 0033).
- Measured tracking latency for 1 and 5 SITL aircraft → the M2b scale report (done for 5).

**Known gaps**

- Flight behaviour against PX4 is verified in CI only; the development host has no Docker.
- The loopback vehicles are test doubles and prove nothing about PX4 compatibility.
- The image is PX4 v1.18.0-rc1 (no prebuilt v1.17.0 image); move to 1.18.0 when released,
  and retry the runway takeoff then.
- SIH fixed-wing flight performance is not realistic in this version (it climbs at about
  5 m/s airspeed), so no test asserts it.
- PX4 logs "Ignore command … to N/1" for MAVSDK requests on the shared port that are
  addressed to other system ids. This is harmless noise.

---

## M2b: Scale and swarm (SIH 25/50, NATS, ROS 2 bridge, mock video)

**Goal:** the station tracks a PX4 fleet at scale, and tasks a `swarm_sar` swarm through a
ROS 2 bridge.

**Decisions** (the user):

- Gazebo, with camera video, moves to a new stop, **M2c** (later dropped: ADR 0033).
- nats-server is used locally too, from `.tools/nats/`.
- **The 50-aircraft measurement is deferred to the field hardware in M5 or M6**
  (2026-09-30), after the free CI runner proved too small.

See ADR 0024, ADR 0025 and ADR 0026.

**Built** (2026-09-30)

- [x] **Swarm link over NATS** (ADR 0024):
  - [x] `drivers/swarm_wire.py`, the contract, published as `docs/api/swarm-bridge.json`
        with a drift test.
  - [x] `drivers/swarm.py`:
    - `SwarmLink`: one NATS connection, reconnecting forever.
    - `SwarmDriver`: acks from the drone's own sequence; no answer is a pipeline timeout.
    - The drones of one command go out as one swarm message.
  - [x] Settings: `nats_url`, `swarm_name`, `swarm_grid_resolution_m`.
- [x] **`src/sar_gcs_bridge`** (ament_python; the onboard code is unchanged):
  - `wire.py`: the NATS JSON, standard library only.
  - `core.py`: heading to degrees true; the target estimate becomes a survivor sighting in
    WGS84; sequencing on the ground clock, validated by the onboard messages;
    republishing until the drones catch up; a per-drone rate limit.
  - `node.py`: rclpy in a thread, NATS on asyncio.
- [x] **`mission_start` for swarm area missions:**
  - swarm-wide (every swarm aircraft, exactly the tasks), always confirmed;
  - the mission and its tasks become `active` on the first ack.
  - New codes: `swarm-mission-partial`, `swarm-mission-tasks`, `mission-not-planned`,
    `incident-not-active`, `swarm-unknown`.
- [x] **Aircraft with two links** (ADR 0025):
  - `LinkedDriver`, with `merge` and `route_command` (pure, row-tested);
  - `links` per aircraft in the live view;
  - goto refused while the companion is in control (`companion-in-control`);
  - RESUME and HOLD read the swarm phase.
- [x] **Unknown GNSS quality:** `gps_fix` is nullable, raises no `gps_lost` alert, and
      shows as a confirmation warning.
- [x] **MAVSDK thread pool** (`mavlink_threads`, 64). A regression test covers it; the first
      scale run found the problem.
- [x] **Simulation tooling:**
  - `sim/sitl/fleet.py`: generated PX4 SIH fleets.
  - `sim/swarm`: the ROS 2 Jazzy image; `swarm_sim.py`, the onboard closed-loop
    simulation on the epoch clock; compose with NATS and the bridge.
  - `sim/video`: MediaMTX with four ffmpeg test streams.
- [x] **CI:**
  - `swarm.yml`: the bridge tests and ament linters in the ROS image, the swarm
    integration, and mock video.
  - `sitl-scale.yml`: 25 aircraft (35 and 50 were run in M2b; see the results).
  - `sitl.yml`: the 5-aircraft tracking measurement.
  - `ci.yml`: a pinned, checksum-verified nats-server, with `SARGCS_REQUIRE_NATS=1`.
  - All four also run on `exp/**` branches.
- [x] `deploy/compose.yaml`: NATS (pinned), and `SARGCS_NATS_URL`.
- [x] **Docs:**
  - ADR 0024–0026;
  - the API guide (swarm fields, `links`, `mission_start`, new codes);
  - `architecture.md`, `sim/README.md`, the runbooks, and the bridge's README.

**Tests**

- **Local** (`scripts/check.py`, 12/12):
  - the swarm rules, row by row;
  - the linked driver;
  - the swarm link against a real nats-server and a fake bridge: bulk HOLD as one message,
    refusal as a nack, no reply as a timeout, mission start and rejection, partial
    missions refused, surviving a NATS restart;
  - the bridge contract, both ways;
  - the bridge core (27 tests, on the onboard message fakes);
  - the swarm simulation on the epoch clock (4 tests).
- **CI, `swarm` workflow:** **3/3**, through the real bridge and three simulated drones.

  | Test | Time |
  |---|---|
  | Tracking | 0.7 s |
  | Area mission, then HOLD and RESUME, all verified | 3.7 s |
  | NATS restart | 2.6 s |

  Mock video: four H.264 streams at 640×360.
- **CI, scale** (GitHub runner, 4 vCPU; details in ADR 0026):

  | Aircraft | Tracking over 60 s | Largest gap | Latency p95 | Fleet service |
  |---|---|---|---|---|
  | 5 | no stale state | 0.40 s | 0.10 s | 0.32 core |
  | 25 (3 runs) | no stale state | 0.60–0.61 s | 0.10 s | 0.72–0.75 core |
  | 35 (3 runs) | twice no stale state; once 2 of 35 went stale (load 56) | 0.80 s, 2.27 s | 0.10 s | 0.67–0.74 core |
  | 50 (1 run) | **27 of 50 went stale**: load 92, PX4 at about 2.8 Hz; **deferred to M5/M6** | 4.25 s | 0.13 s | 0.45 core |

  Tracking is verified to **25 aircraft** in CI. 35 is at the limit of the runner, and at
  50 the runner runs PX4 far slower than real time (about 2.8 Hz). The station's own
  latency stays near 0.1 s (p95) throughout, and it uses under one core. `sitl-scale` therefore runs 25
  aircraft; 35 and 50 are measured on the field hardware.

**Acceptance**

- [x] A swarm of 3 simulated `swarm_sar` drones accepts an area mission and a HOLD from the
      GCS: green on GitHub (`swarm`, commit `3aab5f4`).
- [ ] 50 SIH aircraft tracked with no stale states: **deferred to M5/M6** (the user), on the
      field hardware.
  - The free 4-vCPU runner is already oversubscribed at 25 PX4 instances (load 19) and at
    35 (load 41).
  - The first 50-aircraft job made the runner unresponsive until GitHub cancelled it. A
    later one ran: 27 of 50 went stale at a load of 92 (above).
  - The fleet service itself used under one core at 35 aircraft.
  - It needs a host with about 8 or more cores. `sitl-scale` now runs 25 only (above).

**Found in CI, and fixed**

- MAVSDK queued bulk commands on asyncio's 8-thread default pool (regression test).
- The station closes idle WebSockets after 30 s, so the scale watcher now pings.
- A 45-minute job limit hid all measurements, so the test step now has its own limit.
- A race in the NATS-restart test.

**Known gaps**

- 50 PX4 SIH are not measured: deferred to M5/M6 (above).
- **Bulk commands at 25 or more aircraft** on the runner: between 8 % and 96 % of the
  answers come after MAVSDK's retries, depending on the run. They are reported as timeouts,
  and every aircraft still acted, within 28–53 s. This follows the runner's load (PX4
  slower than real time), so it says nothing reliable about the station. It is measured
  again on the field hardware (M5). MAVSDK's per-command timeout is not adjustable from
  Python v4.
- **The command acknowledgement can be wrong** in one case: two separate commands close
  together to different drones, with the first one lost on the radio. The onboard protocol
  has no per-drone acknowledgement, so the station would count it as acknowledged. Effect
  verification catches it (ADR 0024); a protocol change is to be proposed.
- **No effect verification for swarm-only aircraft** on RTL and LAND; the result is
  `unverified`. `DroneState` carries no autopilot mode. Swarm aircraft should also have a
  MAVLink link (ADR 0003).
- **No alert** when one of an aircraft's two links is lost while the other is live (M4).
- **Mock video frames** carry no callsign or timestamp: the image has no fonts. That comes
  with the latency overlay in M5.
- **In the swarm simulation**, the drones start airborne at 4 m. PX4 under a companion,
  depth and radio behaviour, and DDS over Wi-Fi are not covered (field tests; no Gazebo,
  ADR 0033).

**Stop:** report, then wait.

---

## M3: Fleet console MVP ✅

**Goal:** an operator can watch and safely command the fleet from the map.

**Decisions** (the user):

- One stop, not split.
- The **Zurich sample basemap**, fetched with go-pmtiles v1.31.2 (checked against GitHub's
  SHA-256) into `.tools/`.
- **Playwright's Chromium**, installed locally.

See ADR 0027.

**Built** (2026-09-30), on branch `m3` from `exp/m2b`

- [x] **Session:**
  - sign-in page with clear failure messages (wrong password, lockout, unreachable);
  - the token in `sessionStorage`;
  - an expiry banner;
  - back to sign-in with the reason on 401, 4401 or `session_ended`.
- [x] **Live client:**
  - one WebSocket; auth in the first message, subscription to every topic at 10 Hz, pings;
  - `seq` gap or 4429 → reconnect and resync from snapshots; other losses → backoff;
  - the OFFLINE banner disables every command.
- [x] **State:** a Zustand live store written only by the socket; the map redraws per
      animation frame; React reads through a hook throttled to 4 Hz.
- [x] **Map** (MapLibre 6, PMTiles):
  - offline Protomaps basemap, or a plain background with a notice;
  - runtime-drawn airframe icons, rotated by heading (no nose when the heading is unknown);
  - link state by colour **and** shape;
  - trails (redrawn at 2 Hz), homes, selection halo, goto target;
  - scale; cursor coordinates in DD, DDM or MGRS.
- [x] **List:** sortable (lost first; unknown battery first), filterable (callsign, link,
      group); link as icon + word; unknown as "—".
- [x] **Selection:** click, shift or ctrl (map and list), box and lasso (terra-draw),
      filtered, group, all, clear; the count is always shown.
- [x] **Telemetry panel:** one aircraft in full (links, swarm block, survivor sighting), or a
      summary of the selection.
- [x] **Command bar:**
  - hold, resume, return, land, goto (pick on the map), arm, disarm, takeoff (altitude);
  - offered or greyed out with the reason;
  - the server's 428 summary in a dialog: count in the title, warnings, rejected aircraft,
    override flag;
  - **held confirmation** (1 s, pointer or Space); focus starts on Cancel; Enter never
    confirms;
  - live per-aircraft outcomes.
- [x] **Control lease:** holder in list and panel; take and release (handover and supervisor
      assignment are M5).
- [x] **Alerts:** severity by icon + word + colour; acknowledge.
- [x] **Keyboard:** `?` help overlay, `H` (hold), `B`, `L`, `G`, `Ctrl+A`, `Esc`. No risky
      command has a key.
- [x] **Role-aware:** observers get no command bar or control buttons. The server stays
      authoritative.
- [x] **Tooling:**
  - `scripts/fetch-basemap.mjs`;
  - `e2e/backend.py` (a seeded simulation station, also used for local demos);
  - the Playwright configuration.
- [x] **CI:** a new `e2e` job (Playwright with Chromium, basemap cached, results as
      annotations), and E2E in `scripts/check.py`.
- [x] **Docs:** ADR 0027; the console README; `dev-setup.md` (console walkthrough, pmtiles);
      architecture status.

**Found while building, and fixed**

- **MapLibre's worker was missing from the production build.** MapLibre computes the
  worker's URL at run time, so Vite's build could not see it. It is now bundled explicitly
  and passed with `setWorkerUrl`. This also invalidated a first frame-rate reading of 60 fps,
  taken while the production map was not rendering at all.
- **The click that closes a lasso reselected one aircraft.** The drawing tool finished,
  selected ten, and switched back to pan; the same click then landed on an aircraft icon.
  Clicks within 0.5 s of a finished drawing are now ignored.
- **MapLibre 6 under Vite's dev server:** handled by the same explicit worker bundle.
- **The fleet service accepted a goto for several aircraft to one point** (after a bulk
  confirmation), which would converge them on it; only the console refused it. A goto
  request now takes exactly one aircraft (422 otherwise), with a regression test. Bulk goto
  with spread targets comes with deconfliction (M4).
- **An E2E race:** a test pressed Return before its third control lease had arrived, and the
  server (correctly) left that aircraft out. The tests now wait for the leases and release
  them afterwards; the console scenarios pass three times in a row on one station.
- **The console image did not build** (CI `images`): its build context is `fleet-console/`,
  and `tsc -b` also checked a test that reads `docs/api/asyncapi.json`. Tests are now their
  own TypeScript project (`tsconfig.test.json`, checked by `npm run typecheck`); the build
  checks the app code only. Reproduced and verified with a copy of the context alone.

**Tests**

- **Vitest: 60 tests.**
  - the socket client (fake WebSocket and timers) and the store;
  - availability rules, row by row;
  - hold-to-confirm and the dialog;
  - the command flow (428 and confirm, problem details, 401);
  - list filtering and sorting;
  - coordinates (DDM and MGRS pinned) and symbology;
  - shortcuts;
  - WebSocket message kinds against `docs/api/asyncapi.json`;
  - a render-count guard: 50 aircraft at 10 Hz keep the list at 4 renders per second.
- **Playwright: 7 scenarios**, run against the built console and a simulation station with
  20 aircraft (16 hexacopters flown to 20 m first):
  1. lasso 10 aircraft and HOLD in **5 actions**; the dialog names 8 aircraft and 2 not
     sent (fixed-wings on the ground); 8 verified; the audit log has the dispatch;
  2. ARM names "1 aircraft", Enter cancels and the aircraft stays disarmed; a bulk RETURN
     names "3 aircraft";
  3. an injected link fault shows ◐ Stale / ✕ Lost; Arm is disabled with the reason; Land
     stays available;
  4. WebSocket dropped and reconnects refused → OFFLINE banner and commands disabled;
     restored → resynchronized;
  5. an observer sees no command bar and no control buttons;
  6. a session ended elsewhere → sign-in page with the reason;
  7. **50 aircraft at 10 Hz: 46–54 fps** over several runs (longest frame 50–67 ms).

**Acceptance: passed.**

- The frame-rate target holds: **50 mock aircraft at 10 Hz render at 46–54 fps** on this PC's
  GPU. That is an Intel HD Graphics integrated GPU (Direct3D 11), older than a current field
  laptop's. The target was ≥ 30 fps.
- **With software WebGL** (SwiftShader, as on CI runners) the same run gives about 14 fps.
  CI reports that figure and does not judge it.
- **ADR 0015's usability scenarios pass:**
  - lasso and HOLD in 5 actions;
  - every risky confirmation names the count;
  - no risky command from one keystroke or one click;
  - alerts carry icon + word, not colour alone.

**Known gaps**

- **The operator's frame rate is measured on this PC only.** Measure on the field laptop too
  (M5, with the load tests).
- **The console bundle is 1.5 MB** (411 KB gzipped), plus a 0.5 MB map worker. It is served
  locally, but splitting it is left for M6.
- **Features left for later milestones:**
  - handover requests, supervisor assignment and force (M5);
  - an audit viewer (M5);
  - alert escalation and audible cues (M4);
  - mission planning and drawing search areas (M4);
  - goto for several aircraft at once, each to its own spread point (M4);
  - video (M5).
- **Basemaps for field regions** wait for your region decision (before M4). The sample
  covers about 23 × 20 km around the simulator's site.
- **Aircraft labels hide** when aircraft overlap at low zoom (the icons never do). The list
  is the complete view.

**Stop:** report, then wait.

---

## M4: Mission planning and tasking

**Scope**

- **Waypoint mission editor:** per-waypoint altitude with an explicit reference, speed,
  loiter, validation.
- **Search areas:** drawing plus GeoJSON/GPX/KML import (CalTopo and SARTopo exports).
- **`domain/patterns`** (computed in UTM, ADR 0014):
  - Parallel track / lawnmower and creeping line.
  - Expanding square from a datum.
  - Sector search (VS).
  - Contour search from a DEM. Without a DEM, perimeter offset rings, clearly labelled
    as a fallback.
  - Lane spacing from the sensor footprint (HFOV, altitude, overlap %) or set explicitly.
  - Fixed-wing turn-radius handling.
- **Bulk tasking:**
  - Split the area among N aircraft, weighted by speed and endurance.
  - Per-aircraft overrides.
  - **Deconfliction:**
    - AMSL altitude layers, with a wider band between fixed-wing and multirotor aircraft.
    - Lane interleaving and start-time offsets.
    - A 4D conflict check on the planned trajectories.
    - Sequenced departure and return.
- Mission upload, start, pause and resume through the drivers. Swarm-area missions go
  through the bridge.
- **Bulk goto:** several aircraft to one datum, each given its own point (a spread around
  it) and altitude layer, through the same deconfliction check. Until then a goto takes one
  aircraft (M3).
- **Onboard avoidance during ground commands:** on aircraft with a companion (swarm link),
  goto and takeoff currently go straight to PX4 over MAVLink, where the companion's vision
  obstacle avoidance probably does not steer (PX4 follows it in offboard mode only).
  Verify in the swarm simulation, then route goto over the swarm link when it is live, or
  document the limit to operators.
- Progress: current waypoint, % of the area covered (flown track × sweep width), and a
  coverage overlay.
- **Alert engine:**
  - Low battery, including a return-energy estimate.
  - Link loss, GPS loss, geofence breach.
  - Mission complete, route deviation (cross-track error), stale telemetry.
  - Deconfliction risk.
  - Severity, acknowledgement, escalation, audible cues.
- POIs and survivor sightings (manual, or reported by the bridge).

**Tests**

- **Hypothesis properties for every pattern:** coverage ≥ the requested amount, every waypoint
  inside area + margin, spacing within tolerance, fixed-wing turn feasibility.
- Deconfliction invariants: minimum separation holds across generated plans.
- Alert rule unit tests.
- SITL integration: a lawnmower split across 3 mixed aircraft completes.
- E2E: plan, assign to a group, monitor progress.

**Progress** (2026-09-30): the backend half is built; the console half is not started.

**Built: backend** (commit `dc6d5d8` on `exp/m4`; ADR 0028–0031)

- [x] Region data (ADR 0030): `regions.json` (Zurich, Kramatorsk), offline basemaps per
      region, Copernicus GLO-30 terrain and a pinned Sentinel-2 image
      (`scripts/fetch_region.py`); `domain/terrain` (unknown heights stay unknown).
- [x] `domain/patterns` (ADR 0028): parallel track, creeping line, expanding square, sector,
      contour (DEM; perimeter rings as a labelled fallback), lane spacing from the camera
      footprint, fixed-wing run-ins and turn-feasible lane order.
- [x] `domain/split` and `domain/deconfliction` (ADR 0029): strips weighted by speed ×
      endurance, altitude layers with a fixed-wing band, terrain clearance, sequenced
      departures, exact 4D closest-approach check.
- [x] `POST /missions/{id}/plan` (dry run or save), plan and progress endpoints.
- [x] GCS mission start: upload, read-back, start (MAVLink driver, mock, loopback vehicle);
      pause and resume; a 4D re-check at the start; issues need a supervisor's override.
- [x] Bulk goto: each aircraft its own point and layer, 4D-checked, always confirmed.
- [x] Progress, coverage, completion; route deviation (ADR 0028).
- [x] Alerts (ADR 0031): return energy, geofence breach, one of two links lost, collision
      risk, escalation. Points of interest and survivor sightings. WebSocket topics
      `missions` and `pois`.
- [x] Migration 0003; OpenAPI, AsyncAPI and console types regenerated.

**Found in SITL, and fixed** (the first `sitl` run of `dc6d5d8` failed)

- **PX4 refuses Mission mode right after an upload** while it checks the new mission
  ("Switching to Mission is currently not available"). The driver started at once, so both
  hexacopters' starts were nacked. It now retries while PX4 answers `DENIED`/`BUSY`, for up
  to 5 s. Regression tests: the loopback vehicle refuses Mission mode for 0.5 s after an
  upload, as PX4 does; driver unit tests cover retry, final refusal and no retry for other
  refusals.
- **The SIH airplane requires a landing pattern in every mission** (`MIS_TKO_LAND_REQ=2`)
  and rejected its route. The station does not plan landings (ADR 0028), so the SITL
  airplane is set to 0, and field airplanes need 0 or 1.
- **The SIH airplane cannot fly a route** (it barely climbs; ADR 0023), so a mission that
  includes it never completes. The SITL test is now two: a lawnmower split across three
  multirotors (2 hexa, 1 quad) that must complete, and an airplane lawnmower that PX4 must
  accept and start.
- The SITL test waited 600 s before checking the start outcome; it now fails at once.

Verified: `sitl` **8/8** against PX4 v1.18.0-rc1 SIH, both locally (Docker, 9 min) and on
GitHub (run 36703251173, commit `53c40c5`); `swarm` green on GitHub; `scripts/check.py
--fast` passes (the console E2E, 7/7, with this host's preinstalled Chromium).

**Built: console** (2026-09-30; ADR 0032)

- [x] Incident picker (top bar; supervisors open incidents). Side pane tabs: Fleet,
      Missions, Points; alerts always visible.
- [x] Map layers: search areas (name and status as text), planned routes (colour and dash
      per aircraft), the edited waypoint route, datum, coverage overlay, points of interest
      (a shape per kind). Tools: draw area, add waypoints, pick datum, mark point.
- [x] Search areas drawn or imported from GeoJSON, KML and GPX (CalTopo/SARTopo exports):
      holes dropped, tracks closed, rings over 256 vertices simplified, each change shown.
- [x] Waypoint mission editor: altitude above home in every label, speed, loiter,
      reorder/remove, errors block saving, a warning over 120 m.
- [x] Plan form (patterns, spacing or camera footprint, bearing, datum, radius, contour
      height; the selection or a group), dry-run preview with the deconfliction report,
      then save.
- [x] Start, pause, resume to the planned aircraft through the confirmed command flow;
      live progress per aircraft and coverage.
- [x] Points of interest: survivor sightings first, confirm/dismiss/resolve, marking.
- [x] Bulk goto offered (spread by the server); the confirm dialog shows each aircraft's
      target, layer, start delay and conflicts.
- [x] Audible cues for new and escalated alerts, reminders while a critical is
      unacknowledged, mute per browser.
- [x] Onboard avoidance during ground commands: **documented, not verified in
      simulation.** Verifying that the companion yields when PX4 leaves offboard needs PX4
      with a companion in simulation, which needed Gazebo (dropped, ADR 0033). The station
      flags such aircraft in the plan and the confirmation (ADR 0028); field tests remain.
- [x] Battery drain and geofence breach against PX4 SITL (moved from M2a): the station
      raises battery low then critical while PX4 returns on its own, and a geofence breach
      raises a critical alert that clears when the fence is disabled.

**Tests**

- fleet-service: unchanged suite plus the two new SITL tests (below).
- Console: **88 Vitest** (new: file import, plan request and waypoint checks, map features,
  point order, alert cues, the store's missions and points).
- **E2E, new `e2e/missions.spec.ts`, 3/3** (with this host's preinstalled Chromium):
  1. import a CalTopo-style area, plan a lawnmower for the group Team North (4 hexa and
     1 fixed-wing), preview (no conflicts), save, start with the held confirmation, and
     watch it complete, with coverage of at least 80 % and the area marked searched;
  2. edit a waypoint route on the map, with a blocking error and its fix;
  3. mark a clue on the map, then dismiss it.
- The whole E2E suite, 10 tests: the M3 specs and perf pass as before. The map measured
  13-21 fps with 50 aircraft on software WebGL (reported, not judged; 46-54 on a GPU in M3).
- SITL against PX4 v1.18.0-rc1 (Docker in the development container): **10/10 in file
  order** (11 min), with the new geofence-breach and battery-drain tests.

**Stop:** report, then wait.

---

## M5: Video, roles, audit, multi-operator, 25–50 load tests

**Scope**

- **Video:**
  - MediaMTX in compose, and the `VideoStream` registry and health polling.
  - A WHEP player with a 1/4/9 grid, picture-in-picture, fullscreen and a health overlay.
  - LL-HLS fallback.
  - Viewing is audited.
- **Roles and multi-operator:**
  - User administration.
  - Operator presence and ownership colors.
  - Handover request/accept UX, supervisor assign and force, orphan alerts.
  - Observer read-only mode.
- **Audit and retention:**
  - Audit viewer with filters, chain status and export.
  - Retention settings and purge jobs.
- **Load tests:**
  - 25 and 50 aircraft (mock at 10 Hz, plus SIH) with 6 consoles.
  - **Enforce the budgets in `docs/architecture.md`.**
  - Measure the MAVLink driver at 50 SIH aircraft (CPU, memory, thread pool); decide on the pymavlink fallback if over budget.
  - **The 50-aircraft tracking acceptance deferred from M2b**, on the field hardware (≥ 8 cores),
    with `sim/sitl/fleet.py --count 50` and `tests/integration/test_scale.py`. Measure 35 as
    well, and bulk-command answer times, which the CI runner could not measure reliably.

**Tests**

- Playwright multi-context: a two-operator handover, a supervisor force, observer denial.
- Video E2E with mock streams, including latency via the timestamp overlay.
- Load suite (nightly).

**Stop:** report, then wait.

---

## M6: Hardening, degraded comms, packaging, runbooks, acceptance

**Scope**

- **Degraded communications:**
  - Link flapping hysteresis.
  - Reconnect and resync for WebSocket, NATS and drivers.
  - GCS restart resync from aircraft.
  - No automatic re-sending of flight commands.
- **Preflight safety checks:**
  - Read PX4 failsafe parameters (`NAV_DLL_ACT`, `COM_DL_LOSS_T`, `GF_ACTION`, `BAT_*`,
    `RTL_RETURN_ALT`) and compare them with the incident policy.
  - Warn about or block takeoff. A supervisor override is audited.
- **Packaging and operations:**
  - Offline bundle (image tarballs, PMTiles, checksums, install script).
  - Serve the API docs page (Swagger UI) from vendored assets, with no CDN (M1a gap).
  - Export the audit chain head periodically, so truncation is detectable (M1a gap).
  - Disk-space guard.
  - Incident export bundle.
  - Upgrade and rollback procedure.
  - Container hardening: read-only root filesystem, non-root, resource limits.
  - Security review.
- **Runbooks:** field deployment, basemap preparation, certificate trust, incident start
  and end, operator quick-reference card, recovery, backup and export.
- **Full acceptance test** (scripted and documented):
  - Launch the simulation (50 SIH + mock video) and connect 50 aircraft.
  - An operator tracks 25 and assigns an area search to a mixed group of 8.
  - Monitor telemetry and alerts under injected link loss, low battery and GPS loss.
  - View video.
  - Safely return and land every aircraft.
  - The audit chain verifies, and the incident export completes.

**Stop:** final report.

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| No Linux/Docker on the development host | SITL only in CI | Decided: CI only (ADR 0023). Loopback tests cover the MAVLink path locally |
| MAVSDK v4 is new (Sept. 2026) | Driver bugs | Loopback + SITL tests; pymavlink fallback stays open (ADR 0022) |
| CI runner too small for 50 SIH | Scale test only on a large host | **Confirmed in M2b**: 4 vCPU saturates at 25+ PX4. Decided: measure 50 on the field hardware in M5/M6 |
| Browser video decode at many streams | Operator workload | Grid cap of 9, on-demand streams (ADR 0012) |
| Contour search without a DEM | Reduced pattern fidelity | DEM import. A labelled fallback |
| Onboard/GCS protocol drift | Swarm tasking breaks | The bridge reuses the onboard codec (ADR 0003). Bridge tests use the onboard fixtures |
