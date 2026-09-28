# SAR fleet ground control

Ground control system for **civilian search-and-rescue** drone fleets. Incident commanders,
supervisors and operators use it to task up to 50 PX4 aircraft (fixed-wing and hexacopters)
from one field ground station, with no Internet required:

- Search areas and search patterns.
- Live telemetry, alerts and video.
- Clear command authority between operators.
- A tamper-evident audit trail.

The repository also holds the **onboard `swarm_sar` companion software** (ROS 2): a
decentralized multicopter search swarm that the ground system tasks through a bridge.

> **Scope.** Civilian SAR only: locating missing persons and supporting ground teams. No
> weapons, targeting or military functionality of any kind (see
> [ADR 0002](docs/decisions/0002-scope-safety-and-assumptions.md)).

> **Status: M0.** Architecture, ADRs and scaffolds are done. The fleet service and console
> are skeletons (health and version endpoints, app shell). See [PLAN.md](PLAN.md) for
> milestones M1–M6.

## Layout

| Path | What |
|---|---|
| [`fleet-service/`](fleet-service/) | Backend: FastAPI, fleet state, tasking, commands, audit, REST + WebSocket |
| [`fleet-console/`](fleet-console/) | Operator console: React + TypeScript, MapLibre (from M3) |
| [`deploy/`](deploy/) | Docker Compose + Caddy gateway for the field ground station |
| [`src/`](src/) | ROS 2 workspace: onboard [`swarm_sar`](src/swarm_sar/README.md) + `swarm_sar_interfaces` |
| [`docs/`](docs/) | [Architecture](docs/architecture.md), [ADRs](docs/decisions/0001-record-architecture-decisions.md), [runbooks](docs/runbooks/dev-setup.md) |
| [`scripts/check.py`](scripts/check.py) | Runs every lint, type check, test and build |

## Quick start (development)

Setup details for Windows and Linux, including Node without admin rights, are in
[docs/runbooks/dev-setup.md](docs/runbooks/dev-setup.md).

```bash
python -m uv --directory fleet-service sync && (cd fleet-console && npm ci)
python scripts/check.py --fast                                  # all checks
python -m uv --directory fleet-service run fleet-service        # API  → http://127.0.0.1:8000/api/v1/docs
(cd fleet-console && npm run dev)                               # console → http://127.0.0.1:5173
```

Field deployment as containers: `docker compose -f deploy/compose.yaml up -d --build`
(TLS on https://localhost via Caddy's internal CA).

## License

MIT. See [LICENSE](LICENSE).
