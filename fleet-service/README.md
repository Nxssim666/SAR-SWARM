# fleet-service

Backend of the SAR ground control system: fleet state, tasking, commands, alerts,
audit, REST and WebSocket APIs. See the repository `README.md`, `docs/architecture.md`
and `docs/decisions/` for the design.

```bash
python -m uv sync                                   # create .venv from uv.lock
python -m uv run fleet-service                      # serve on 127.0.0.1:8000
python -m uv run pytest                             # tests
python -m uv run ruff check . && python -m uv run ruff format --check . && python -m uv run mypy
```

API docs while running: <http://127.0.0.1:8000/api/v1/docs>. Settings are
`SARGCS_*` environment variables (see `src/fleet_service/config.py`).
