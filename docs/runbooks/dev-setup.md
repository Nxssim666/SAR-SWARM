# Development setup

The fleet service and console run natively on Windows, Linux and macOS. PX4 SITL
(M2 onwards) needs Linux with Docker. On Windows that means WSL2 with Docker Desktop.

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Git | any recent | — |
| Python | ≥ 3.12 (3.14 used on the reference Windows host) | python.org / distro |
| uv | ≥ 0.12 | `python -m pip install --user uv` (then use `python -m uv …` or add the user Scripts dir to PATH), or the installer at docs.astral.sh/uv |
| Node.js | 24 LTS | Windows: `winget install OpenJS.NodeJS.LTS` · Linux: nodesource or fnm |
| Docker | Engine + Compose v2 | For images and SITL. Windows 10/11: enable WSL2, then install Docker Desktop (admin rights and a reboot) |

**No admin rights?** A portable Node can live in the repo's gitignored `.tools/` directory:

```bash
python -m uv venv .tools
python -m uv pip install --python .tools/Scripts/python.exe "nodejs-wheel==24.*"   # Linux: .tools/bin/python
```

`scripts/check.py` finds it automatically. For manual use, put the **real** binary's directory
first on PATH and the shim directory second, for `npm`:

```bash
# Git Bash on Windows
export PATH="$PWD/.tools/Lib/site-packages/nodejs_wheel:$PWD/.tools/Scripts:$PATH"
```

> Why the real binary: the `node.exe` console-script shim re-launches Node through Python,
> which breaks tools that fork Node workers. Vitest times out starting its workers.

## First run

```bash
git clone <repo> swarm_sar_ws && cd swarm_sar_ws
python -m uv --directory fleet-service sync          # backend venv from uv.lock
(cd fleet-console && npm ci)                         # console deps from package-lock.json
python scripts/check.py                              # everything; add --fast to skip slow onboard sims
```

## Running locally

```bash
python -m uv --directory fleet-service run fleet-service     # API on http://127.0.0.1:8000
(cd fleet-console && npm run dev)                            # console on http://127.0.0.1:5173
```

- The console's dev server proxies `/api` to the fleet service. Set `FLEET_SERVICE_URL` to
  point it elsewhere.
- Interactive API docs are at <http://127.0.0.1:8000/api/v1/docs>.
- Settings are environment variables with the `SARGCS_` prefix; see
  `fleet-service/src/fleet_service/config.py`.

## First admin and the API

```bash
python -m uv --directory fleet-service run fleet-service create-admin --username chief
```

This prompts for a password of 10 or more characters. Log in through `/api/v1/docs`
(Authorize → Bearer token from `POST /auth/login`), or see `docs/api/README.md`. Data lives in
`fleet-service/data/`, which is gitignored. Delete that directory to start over.

After changing the API, run `fleet-service export-openapi`, then `npm run gen:api` in
`fleet-console/`. The tests fail until both generated files are committed.

## Container stack (Linux or Docker Desktop)

```bash
docker compose -f deploy/compose.yaml up -d --build
# https://localhost  (Caddy internal CA: accept or trust its root certificate once)
docker compose -f deploy/compose.yaml exec fleet-service fleet-service create-admin --username chief
```

## Onboard swarm_sar packages

These are unchanged; see `src/swarm_sar/README.md`. The pure-Python tests run anywhere:

```bash
python -m uv run --no-project --with-requirements requirements-standalone.txt python -m pytest -q
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `uv: command not found` | Use `python -m uv`, or add `%APPDATA%\Python\Python3xx\Scripts` to PATH |
| Vitest: "Timeout waiting for worker to respond" | The real `node` binary isn't first on PATH (see above) |
| Console badge "Fleet service offline" | Start the fleet service. Check that `FLEET_SERVICE_URL` matches its port |
| Console badge "clock off by N s" | Fix the client device's time (NTP), because alert ages and timestamps depend on it |
| Git warns about CRLF | `.gitattributes` forces LF; run `git add --renormalize .` once if you see mixed endings |
