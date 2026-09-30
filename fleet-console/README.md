# fleet-console

The operator console of the SAR ground control system (React 19 + TypeScript + Vite). An
operator signs in, watches the fleet on an offline map and in a list, selects aircraft and
commands them safely. See ADR 0005, ADR 0006 and ADR 0027 (`docs/decisions/`).

```bash
npm ci                          # what package-lock.json pins
node scripts/fetch-basemap.mjs  # once: the offline Zurich sample basemap (needs the pmtiles CLI)
npm run dev                     # http://127.0.0.1:5173, proxies /api to FLEET_SERVICE_URL (default :8000)
npm run lint && npm run format:check && npm run typecheck && npm run test && npm run build
npm run e2e                     # Playwright: the built console against a simulated station
```

## What it does

- **Session:**
  - sign-in and sign-out;
  - the token lives in `sessionStorage`;
  - an expiry warning;
  - back to sign-in with the reason when the session ends.
- **Live data:** one WebSocket, with reconnect and resync. An **OFFLINE** banner shows, and
  commands are disabled while it is down. The **SIMULATION** banner shows when the station
  simulates.
- **Map** (MapLibre, offline PMTiles):
  - aircraft by airframe icon, rotated by heading;
  - link state by colour **and** shape;
  - trails, home points and the scale;
  - the cursor position in DD, DDM or MGRS;
  - a "no basemap" notice when the basemap is missing.
- **List:** sortable and filterable by callsign, link and group. Link state is shown as icon +
  word; unknown values as "—".
- **Selection:** click, shift or ctrl, box, lasso, filtered, group, all. The count is always
  shown.
- **Details:** one aircraft in full (swarm block included), or a summary of the selection;
  take and release control.
- **Commands:** hold, resume, return, land, goto (pick on the map), arm, disarm, takeoff.
  - Unavailable ones are greyed out with the reason.
  - Risky and bulk commands show the server's summary. Confirming takes a **held press**
    (1 s, pointer or Space); Enter never confirms.
  - Outcomes show per aircraft.
- **Alerts:** severity by icon + word + colour, with acknowledge.
- **Keyboard:** `?` help, `H` hold, `B` box, `L` lasso, `G` goto target, `Ctrl+A`, `Esc`.

## Layout

| Path                                        | What                                                                   |
| ------------------------------------------- | ---------------------------------------------------------------------- |
| `src/api/`                                  | REST client (problems, 401), generated types (`gen:api`), type names   |
| `src/session/`                              | Session store (`sessionStorage`), sign-in page                         |
| `src/live/`                                 | WebSocket client and messages, live store, 4 Hz throttled hook         |
| `src/map/`                                  | MapLibre map, basemap, symbology, icons, trails, coordinates           |
| `src/selection/`                            | Selection store, geometry, tools                                       |
| `src/fleet/`                                | List, filters and sorting, telemetry panel, value formatting           |
| `src/commands/`                             | Command flow, availability rules, confirmation dialog, hold-to-confirm |
| `src/control/`, `src/alerts/`, `src/shell/` | Lease buttons, alerts, layout, banners, shortcuts                      |
| `e2e/`                                      | Playwright scenarios, and `backend.py` (a seeded simulation station)   |
| `scripts/`                                  | `gen-api.ts`, `fetch-basemap.mjs`                                      |

## Tests

- **Vitest** (`npm run test`):
  - the socket client (fake WebSocket and timers) and the store;
  - availability rules, row by row;
  - hold-to-confirm and the dialog;
  - the command flow (428 and confirm, problems, 401);
  - list filtering and sorting;
  - coordinates and symbology;
  - shortcuts;
  - the WebSocket message kinds against `docs/api/asyncapi.json`;
  - a render-count guard: 50 aircraft at 10 Hz keep the list at 4 renders per second.
- **Playwright** (`npm run e2e`). It builds the console and starts `e2e/backend.py`: the fleet
  service in simulation mode with a fresh data directory, one user per role, 20 aircraft and
  a group. It runs:
  - lasso 10 aircraft and HOLD in at most 5 actions, then check the audit log;
  - risky commands name the count, and Enter never confirms;
  - a degraded link is shown by shape and text, with only safe commands offered;
  - offline, then resync;
  - an observer gets no commands;
  - a session ended elsewhere;
  - 50 aircraft at 10 Hz with the map at ≥ 30 fps.
- **The frame rate:**
  - `E2E_GPU=1` uses this machine's GPU (`scripts/check.py` sets it).
  - With software WebGL (CI) the figure is reported, not judged.
  - The report and a Chrome trace go to `test-results/`.
- **E2E backend's Python:** Windows uses `py -m uv`; set `UV` to override.

## Basemap

`scripts/fetch-basemap.mjs` extracts about 23 × 20 km around the simulator's site from a
pinned Protomaps build (OpenStreetMap data, ODbL; attributed on the map), with its fonts and
sprites, into `public/basemap/` (gitignored, about 24 MB). It needs the pmtiles CLI:
`PMTILES_BIN`, `PATH`, or `../.tools/pmtiles/` (`docs/runbooks/dev-setup.md`). Field regions
are prepared the same way (M6 runbook).
