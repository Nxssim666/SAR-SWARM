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
| M2b Scale and swarm: SIH 25/50, NATS, ROS 2 bridge, mock video | — |
| M3 Console MVP | — |
| M4 Mission planning, patterns, bulk tasking, deconfliction, alerts | — |
| M5 Video, roles, audit viewer, multi-operator, load tests | — |
| M6 Hardening, degraded comms, packaging, runbooks, acceptance | — |

M1 and M2 from the original brief are each split into two stop points (a and b), because each
is several weeks of work and a review checkpoint in the middle lowers risk.

## Decisions needed from the user

1. ~~Before M2a: where PX4 SITL runs.~~ **Decided: CI only** (GitHub Actions; ADR 0023),
   on <https://github.com/Nxssim666/SAR-SWARM>. CI results are read from the public checks
   API (annotations); job logs and artifacts need a signed-in account.
2. **Before M4:** the region(s) to prepare offline basemaps for, and whether a DEM is available
   for contour search.
3. **Any time:** confirm or override the stack (ADRs 0004–0017) and assumptions A1–A11 (ADR 0002).

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
- Gazebo (tier 1) → M2b, with camera and mock video.
- Measured tracking latency for 1 and 5 SITL aircraft → the M2b scale report.

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

**Scope**

- SIH headless profile for 25 and 50 vehicles; a scale report (latency, CPU, memory) on a
  runner or host large enough.
- Gazebo Harmonic (tier 1) with a hexacopter model (derived from x500), and camera video.
- NATS in compose, and the NATS `EventBus` implementation. The bus tests run against both
  implementations.
- `src/sar_gcs_bridge` (ament_python, a ROS 2 Jazzy container):
  - Reuses `swarm_sar.ros.codec`.
  - Maps `DroneState` to telemetry, with the heading conversion pinned by tests.
  - Maps commands and area missions to `/swarm/v2/*`, with sequencing, republishing and
    acknowledgement tracking.
  - Maps "target" to *survivor sighting*.
- Merging an aircraft's MAVLink and swarm telemetry sources.
- Mock video: ffmpeg `testsrc2` per vehicle into MediaMTX (MediaMTX is introduced here as sim
  tooling; the product integration is in M5).

**Tests**

- Bridge unit tests against the onboard `fake_msgs` fixtures.
- Bridge integration in the ROS container.
- 25 and 50 aircraft tracking tests (SIH).
- NATS reconnect tests.

**Acceptance:** 50 SIH aircraft tracked with no stale states under a nominal link. A swarm
of 3 simulated `swarm_sar` drones accepts an area mission and a HOLD from the GCS.

**Risks:** CI runner size for 50 SIH instances; DDS discovery in containers (use host
networking or a discovery server).

**Stop:** report, then wait.

---

## M3: Fleet console MVP

**Goal:** an operator can watch and safely command the fleet from the map.

**Scope**

- Login and logout, and session expiry handling.
- WebSocket client with resync, and an offline banner.
- Generated API types (openapi-typescript).
- **Map:** MapLibre, an offline PMTiles sample region with a "no basemap" fallback.
  - Aircraft symbols by type, rotated by heading, with status shown by color **and** shape.
  - Trails, the home point, and a scale bar.
  - Coordinate readout in DD, DDM or MGRS.
- **Aircraft list:** sortable and filterable (status, battery, link, mode, group), with
  stale/lost states that are obvious.
- **Selection:** click, shift/ctrl-click, lasso and box (terra-draw), by status filter, by
  group, select all, select in drawn area. The selection count is always visible.
- **Telemetry panel:** a single aircraft, or a multi-selection summary.
- **Command bar:** HOLD, RESUME, RTL, LAND, arm and takeoff, and goto (click on map).
  - The **confirmation dialog shows the server's 428 summary**, and risky actions can't be
    completed with a single key.
  - Control-lease UI: holder shown, take and release.
- Keyboard shortcuts with a help overlay.
- Role-aware UI. The server remains authoritative.

**Tests**

- Vitest: stores, selectors, confirmation flow, render-count guard under a 10 Hz update rate.
- **Playwright E2E** against the fleet service with the mock fleet: login, lasso 10 aircraft,
  HOLD, confirm, see acknowledgements, verify the audit; a lost link shows the banner and
  greys out commands.

**Acceptance**

- 50 mock aircraft at 10 Hz: map ≥ 30 fps on the reference laptop (Playwright trace).
- Usability scenarios in ADR 0015 pass.

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
  - Launch the simulation (50 SIH + 2 Gazebo with video) and connect 50 aircraft.
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
| No stock Gazebo hexa model | M2b delay | Derive from x500. SIH has `sihsim_hex` for scale |
| MAVSDK v4 is new (Sept. 2026) | Driver bugs | Loopback + SITL tests; pymavlink fallback stays open (ADR 0022) |
| CI runner too small for 50 SIH | Scale test only on a large host | Self-hosted or larger runner. Document where it was run |
| Browser video decode at many streams | Operator workload | Grid cap of 9, on-demand streams (ADR 0012) |
| Contour search without a DEM | Reduced pattern fidelity | DEM import. A labelled fallback |
| Onboard/GCS protocol drift | Swarm tasking breaks | The bridge reuses the onboard codec (ADR 0003). Bridge tests use the onboard fixtures |
