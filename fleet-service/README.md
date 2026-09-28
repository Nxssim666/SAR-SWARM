# fleet-service

Backend of the SAR ground control system: fleet state, tasking, commands, control, alerts,
audit, and the REST and WebSocket APIs. For the design, see the repository `README.md`,
`docs/architecture.md` and `docs/decisions/`. The API guide is in `docs/api/README.md`.

```bash
python -m uv sync                                   # create .venv from uv.lock
python -m uv run fleet-service create-admin --username chief   # first admin (prompts for password)
python -m uv run fleet-service                      # serve on 127.0.0.1:8000 (migrates data/ first)
python -m uv run --env-file simulation.env fleet-service      # simulation mode (ADR 0021), data-sim/
python -m uv run pytest                             # tests (~4 min including Schemathesis)
SARGCS_SITL=1 python -m uv run pytest -m sitl tests/integration   # PX4 SITL (Linux + Docker; see sim/)
python -m uv run ruff check . && python -m uv run ruff format --check . && python -m uv run mypy
python -m uv run fleet-service export-openapi       # after API changes: docs/api/openapi.json
python -m uv run fleet-service export-asyncapi      # after WebSocket changes: docs/api/asyncapi.json
python -m uv run fleet-service db revision --database ops -m "add x"   # after model changes
python -m uv run fleet-service audit-verify         # check the audit hash chain
python -m uv run python scripts/m1b_acceptance.py --password <pw>     # live run (simulation mode)
python -m uv run python scripts/load_smoke.py --password <pw>         # 50 aircraft, 3 consoles
```

API docs while running: <http://127.0.0.1:8000/api/v1/docs>. This page loads Swagger UI from
a CDN, so it needs Internet until M6. The WebSocket is `/api/v1/ws`. Settings are
`SARGCS_*` environment variables; see `src/fleet_service/config.py`. Data (`ops.db`,
`telemetry.db`, `backups/`) lives in `SARGCS_DATA_DIR`, which defaults to `./data`.

**Layout:**

| Path | What |
|---|---|
| `api/` | Routers, request dependencies, the WebSocket and its messages |
| `domain/` | Pure rules: enums, geo, geofences, command rules, telemetry sample |
| `drivers/` | Vehicle drivers: the interface, MAVLink (MAVSDK v4, ADR 0022), and the mock used in simulation mode |
| `services/` | Fleet registry, commands, leases, alerts, recorder, audit, and the runtime that runs them |
| `bus.py` | The in-process event bus |
| `auth/` | Accounts, sessions, permissions |
| `db/` | Models, engines, migrations |
| `asyncapi.py`, `cli.py`, `main.py` | The AsyncAPI generator, the command line, the app factory |
