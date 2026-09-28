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
  `docs/api/` (from M1a). CI checks for drift.
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
docs/            architecture.md, decisions/, runbooks/, api/ (from M1a)
scripts/check.py every lint/type/test/build, cross-platform
sim/             PX4 SITL/Gazebo/SIH harness (from M2a)
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

# fleet-console (from fleet-console/)
npm ci
npm run dev            # http://127.0.0.1:5173, proxies /api → :8000 (FLEET_SERVICE_URL)
npm run lint && npm run format:check && npm run typecheck && npm run test && npm run build

# onboard swarm_sar (from repo root)
python -m uv run --no-project --with-requirements requirements-standalone.txt python -m pytest -q
python -m uv run --no-project --with-requirements requirements-standalone.txt python run_standalone.py --help

# containers (Linux / Docker Desktop only; not available on the current dev host)
docker compose -f deploy/compose.yaml up -d --build
```

**Simulation (PX4 SITL/Gazebo/SIH):** arrives in M2a in `sim/`. Until then, the onboard
standalone simulator (`run_standalone.py`) is the only simulator, and the fleet service will use
its `mock` driver from M1b.

## Milestone status

| Milestone | State |
|---|---|
| M0 Architecture, ADRs, scaffold | Done |
| M1a Data model, persistence, auth/RBAC, REST, OpenAPI | Next |
| M1b Live core: registry, mock driver, commands, leases, WS, audit | — |
| M2a PX4 SITL + MAVSDK (1–5) | Needs a Linux/Docker decision |
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
