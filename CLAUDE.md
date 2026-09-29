# CLAUDE.md

Guidance for AI agents and developers working in this repository.

## Project

Ground control system for **civilian search-and-rescue** drone fleets: up to 50 PX4 aircraft
(fixed-wing and hexacopters), a few operators with roles, one offline field ground station.
It has two applications:

- `fleet-service`: FastAPI backend.
- `fleet-console`: React console.

It also holds the pre-existing **onboard** ROS 2 swarm software in `src/`. Milestones and
status are in `PLAN.md`, the design is in `docs/architecture.md`, and the reasons are in
`docs/decisions/` (ADRs).

## Hard rules

- **Civilian SAR scope only.** No weapons, targeting, strike, military features or offensive
  payload control, ever (ADR 0002). Use SAR terms: incident, search area, sector, tasking, POI,
  survivor sighting. The onboard code's "target" is translated at the bridge; don't spread it.
- **Safety** (ADR 0002, S1–S7; ADR 0011):
  - The server validates every command; the UI is never the safety boundary.
  - Risky or bulk commands go through the 428 confirmation flow.
  - Only the controller or a supervisor commands an aircraft. HOLD is open to all operators.
  - Everything is audited.
  - Never auto-issue flight commands because someone disconnected.
  - No silent defaults: unknown is shown as unknown.
  - The GCS never offers flight termination.
- **Don't modify `src/swarm_sar` or `src/swarm_sar_interfaces`** for ground-system work
  (ADR 0003). The bridge reuses their codec.
- **Units and frames** (ADR 0014):
  - WGS84.
  - Points use explicit `latitude`/`longitude` keys; areas are GeoJSON checked against the
    incident's operating area.
  - An altitude field always carries its reference: `_amsl_m`, `_relative_m`, `_agl_m`.
  - Headings are degrees true, clockwise from north.
  - SI units.
- **Pydantic models forbid unknown fields.** Every API change updates the committed specs in
  `docs/api/` (`export-openapi`) and the console types (`npm run gen:api`). Tests fail on drift.
- **Fleet-service API patterns** (see `docs/api/README.md`, ADR 0018, ADR 0019):
  - Protect every route with `**requires(Permission.X)`. The authorization-matrix test fails
    for a route without one.
  - Raise `errors.NotFound`, `Conflict` or `InvalidRequest` with a stable `slug`; never return
    ad-hoc error bodies.
  - Mutations write `services.audit.record(...)` in the same transaction, then commit.
  - PATCH bodies subclass `PatchModel`, and fields default to `optional()`. Read
    `patch_values()`.
  - Use exactly **one DB session per request** (one connection per SQLite file), and never
    await slow work (hashing, aircraft I/O) inside a transaction.
  - Model changes need `db revision` (sequential ids). The drift test compares models with
    migrations.
- **Live core patterns** (ADR 0020, ADR 0021; code in `services/`, `drivers/`, `bus.py`):
  - Command rules are pure functions in `domain/commands.py`. Add a rule there with a
    row-by-row test, not in a handler.
  - Unknown vehicle state is never assumed favourable.
  - Services take the caller's `AsyncSession`. Tick-driven work (`Runtime.evaluate`) opens
    short sessions of its own.
  - WebSocket connections and background loops must **never** hold a session: there is one
    connection per SQLite file.
  - Publish live changes on the bus (`bus.TELEMETRY`, `ALERTS`, `COMMANDS`, `CONTROL`,
    `SESSIONS`) after committing. After registry changes, call `registry.announce(id)`.
  - Tests use `create_app(start_loops=False)` with `FakeClock` and drive the runtime with
    `tests/live_support.Sim` (`fly`, `idle`). Only `test_runtime_loops.py` uses real time.
  - WebSocket tests create the httpx-ws transport inside the test task, not in a fixture.
  - WebSocket message models are in `api/ws_messages.py`. After changing them, run
    `export-asyncapi`.
- **MAVLink patterns** (ADR 0022, ADR 0023; `drivers/mavlink.py`):
  - One hub (MAVSDK instance) per connection URL; aircraft are matched by
    `mavlink_system_id`, never by port.
  - Telemetry is emitted only when new data arrived. MAVSDK NaN becomes `None`.
  - "No answer" (MAVSDK `TIMEOUT`/`NO_SYSTEM`) must stay a pipeline timeout, not a nack.
  - The driver's plugin subscriptions must be released (`aclose`) before a hub destroys its
    MAVSDK instance.
  - Unit-test apps set `mavlink_links=False` (conftest does), so they never bind UDP ports.
    Tests that need links use `tests/link_support.py` and `tests/mavlink_vehicle.py`
    (loopback) or `tests/integration` (PX4 SITL, CI only, marker `sitl`).
  - With links on, the runtime sizes the loop's default executor (`mavlink_threads`):
    MAVSDK runs every blocking call there, and a bulk command must not queue.
- **Swarm patterns** (ADR 0024, ADR 0025; `drivers/swarm.py`, `drivers/swarm_wire.py`,
  `src/sar_gcs_bridge`):
  - The internal bus stays in-process; NATS is only the adapter boundary
    (`sar.v1.swarm.<swarm>.*`).
  - The wire contract lives in two places: `swarm_wire.py` (pydantic) and the bridge's
    `wire.py` (stdlib). `test_bridge_contract.py` checks them against each other, and
    `export-bridge-schema` writes `docs/api/swarm-bridge.json` (drift test).
  - The bridge sequences and republishes. The station acks only from the drone's own
    reported sequence; no answer is a pipeline timeout. The drivers of one command are
    one swarm message (`DriverCommand.command_id`).
  - A swarm mission is swarm-wide: `mission_start` names every swarm aircraft.
  - Two-link aircraft use `merge` and `route_command` (pure, domain). Unknown GNSS is
    `gps_fix=None`, never a fix.
  - The bridge and `sim/swarm` are ROS code in onboard style (single quotes, 99 columns,
    pep257). They are linted with `src/sar_gcs_bridge/ruff.toml` and tested in the
    onboard environment (`pytest.ini` collects them); `sim/swarm` is excluded from mypy.
  - NATS tests need a `nats-server` (`.tools/nats/` or `NATS_SERVER_BIN`).
    `SARGCS_REQUIRE_NATS=1` makes a missing server fail instead of skip.
- **Tests go in the same change** (ADR 0015):
  - A bug fix starts with a failing test.
  - Each safety rule has a regression test.
  - Time and randomness are injected, and fleet-service warnings are errors.
- A significant decision or assumption gets an ADR (`docs/decisions/NNNN-*.md`, immutable;
  supersede instead of editing).

## Layout

```
fleet-service/   Python ≥3.12, FastAPI, uv (pyproject.toml, uv.lock); code in src/fleet_service/
fleet-console/   React 19 + TS 6 + Vite 8; code in src/
deploy/          compose.yaml, Caddyfile (gateway: TLS, static console, /api proxy)
src/             ROS 2 colcon workspace: swarm_sar, swarm_sar_interfaces (onboard; unchanged)
docs/            architecture.md, decisions/ (ADRs), runbooks/, api/ (openapi.json, asyncapi.json, README)
scripts/check.py every lint/type/test/build, cross-platform
src/sar_gcs_bridge  ROS 2 bridge: swarm protocol <-> NATS (ground-side; ADR 0024)
sim/             sitl/ (PX4 SIH fleets: compose.yaml, fleet.py), linkem.py, swarm/ (ROS image,
                 swarm simulation, bridge, NATS), video/ (MediaMTX mock streams); sim/README.md
.github/workflows/  ci.yml (mirrors check.py), sitl.yml, sitl-scale.yml (25/35/50), swarm.yml
```

## Commands

On the Windows dev host, `uv` isn't on PATH, so use `python -m uv`. Node comes from the
portable `.tools/` venv: put `.tools/Lib/site-packages/nodejs_wheel` (the real `node.exe`)
**first** on PATH and `.tools/Scripts` (for `npm`) second. The `node.exe` shim breaks Vitest.
See `docs/runbooks/dev-setup.md`.

```bash
# everything (what CI runs); --fast skips the ~2 min onboard closed-loop sims
python scripts/check.py [--fast] [--only onboard,service,console]

# fleet-service
python -m uv --directory fleet-service sync
python -m uv --directory fleet-service run fleet-service          # http://127.0.0.1:8000/api/v1/docs
python -m uv --directory fleet-service run pytest -q
python -m uv --directory fleet-service run ruff check . && python -m uv --directory fleet-service run ruff format --check .
python -m uv --directory fleet-service run mypy
python -m uv --directory fleet-service run fleet-service create-admin --username chief   # first admin
python -m uv --directory fleet-service run fleet-service export-openapi   # after any API change
python -m uv --directory fleet-service run fleet-service export-asyncapi  # after WebSocket message changes
python -m uv --directory fleet-service run fleet-service export-bridge-schema  # after swarm_wire changes
python -m uv --directory fleet-service run fleet-service db revision --database ops -m "..."  # after model changes
python -m uv --directory fleet-service run fleet-service audit-verify

# fleet-console (from fleet-console/)
npm ci
npm run dev            # http://127.0.0.1:5173, proxies /api → :8000 (FLEET_SERVICE_URL)
npm run lint && npm run format:check && npm run typecheck && npm run test && npm run build
npm run gen:api        # regenerate src/api/generated/schema.d.ts after export-openapi

# onboard swarm_sar (from repo root)
python -m uv run --no-project --with-requirements requirements-standalone.txt python -m pytest -q
python -m uv run --no-project --with-requirements requirements-standalone.txt python run_standalone.py --help

# containers (Linux / Docker Desktop only; not available on the current dev host)
docker compose -f deploy/compose.yaml up -d --build
```

**Simulation mode** (ADR 0021): every registered aircraft is simulated. From `fleet-service/`:

```bash
python -m uv run --env-file simulation.env fleet-service create-admin --username chief
python -m uv run --env-file simulation.env fleet-service          # data in data-sim/
python -m uv run python scripts/m1b_acceptance.py --password <pw>  # live end-to-end run
python -m uv run python scripts/load_smoke.py --password <pw> --aircraft 50 --clients 3 --seconds 60
```

**PX4 SITL** (ADR 0023) runs in CI (`sitl` workflow), or on a Linux host with Docker:

```bash
docker compose -f sim/sitl/compose.yaml up -d                      # 5 PX4 SIH instances
cd fleet-service && SARGCS_SITL=1 uv run pytest -m sitl tests/integration -v
python sim/linkem.py --listen 14544 --forward 127.0.0.1:24544 --loss 0.2   # link emulator
python sim/sitl/fleet.py --count 50 --out sim/sitl/generated                 # a scale fleet
docker compose -f sim/swarm/compose.yaml up -d --build                        # swarm + bridge + NATS
cd fleet-service && SARGCS_SWARM=1 uv run pytest -m swarm tests/integration/test_swarm.py -v
```

See `docs/runbooks/simulation.md`. The onboard standalone simulator (`run_standalone.py`) is
separate and simulates the swarm_sar companions.

## Milestone status

| Milestone | State |
|---|---|
| M0 Architecture, ADRs, scaffold | Done |
| M1a Data model, persistence, auth/RBAC, REST, OpenAPI | Done |
| M1b Live core: registry, mock driver, commands, leases, WS | Done |
| M2a PX4 SITL + MAVLink driver (1–5) | Done (`sitl` 6/6 and `ci` green on GitHub) |
| M2b SIH 25/50, NATS, ROS 2 bridge, mock video | — |
| M3 Console MVP | — |
| M4 Mission planning, patterns, deconfliction, alerts | — |
| M5 Video, roles, audit viewer, multi-operator, load | — |
| M6 Hardening, packaging, runbooks, acceptance | — |

## Working conventions

- **Milestone loop:**
  1. Plan mode for large changes.
  2. Implement with tests.
  3. Run `python scripts/check.py`.
  4. Update `PLAN.md` checkboxes and this status table.
  5. Commit.
  6. **Stop and report**: built, how to run, test results, gaps, next step.
  7. Don't start the next milestone without confirmation.
- **Report honestly.** Anything that couldn't run locally (Docker, CI, SITL) is reported as
  unverified, never as passing.
- **Code style:**
  - Match the surrounding code. The onboard package has its own style (flake8/pep257,
    single quotes); the fleet service uses ruff (line length 100) and mypy strict.
  - The console uses ESLint strict type-checked and Prettier (single quotes, width 100).
- **Dependencies:**
  - Add with `uv add` or `npm install`, and commit the lock files.
  - Prefer the standard library or an existing dependency over a new one.
  - Licenses must be permissive (MIT/BSD/Apache).
- **Commits:** imperative subject, prefixed with the milestone when relevant (`M1a: …`),
  with a body explaining why.
- **Line endings:** LF is enforced by `.gitattributes`.
