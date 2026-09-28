# fleet-service

Backend of the SAR ground control system: fleet state, tasking, commands, alerts, audit, and
the REST and WebSocket APIs. For the design, see the repository `README.md`,
`docs/architecture.md` and `docs/decisions/`. The API guide is in `docs/api/README.md`.

```bash
python -m uv sync                                   # create .venv from uv.lock
python -m uv run fleet-service create-admin --username chief   # first admin (prompts for password)
python -m uv run fleet-service                      # serve on 127.0.0.1:8000 (migrates data/ first)
python -m uv run pytest                             # tests (~90 s including Schemathesis)
python -m uv run ruff check . && python -m uv run ruff format --check . && python -m uv run mypy
python -m uv run fleet-service export-openapi       # after API changes: docs/api/openapi.json
python -m uv run fleet-service db revision --database ops -m "add x"   # after model changes
python -m uv run fleet-service audit-verify         # check the audit hash chain
```

API docs while running: <http://127.0.0.1:8000/api/v1/docs>. This page loads Swagger UI from
a CDN, so it needs Internet until M6. Settings are `SARGCS_*` environment variables; see
`src/fleet_service/config.py`. Data (`ops.db`, `telemetry.db`, `backups/`) lives in
`SARGCS_DATA_DIR`, which defaults to `./data`.

Layout: `api/` (routers, request dependencies), `domain/` (enums, geo), `auth/`, `db/`
(models, engines, migrations), `services/` (audit), `cli.py`, `main.py` (app factory).
