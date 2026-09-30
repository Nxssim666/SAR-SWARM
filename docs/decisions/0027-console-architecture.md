# 0027. Console architecture: session, live data, map symbology, confirmation

- Status: Accepted
- Date: 2026-09-30
- Refines: [0005](0005-frontend.md), [0006](0006-map-and-offline-tiles.md), [0011](0011-command-authority.md), [0015](0015-testing-strategy.md)

## Context

M3 builds the operator console on the fleet service's REST and WebSocket APIs. ADR 0005 fixed
the stack (React, Zustand for live state, TanStack Query for resources); ADR 0006 fixed the map
(MapLibre, offline PMTiles, terra-draw). This ADR records the decisions M3 made within them.

## Decision

1. **Session.** The bearer token is kept in `sessionStorage`: per browser tab, it survives a
   reload and ends with the tab. It never goes into `localStorage`, a cookie or a URL; the
   WebSocket gets it in its first message (ADR 0009). A 401, WebSocket close 4401 or a
   `session_ended` message returns the operator to the sign-in page with the reason. A
   banner warns 5 minutes before the session's expiry.
2. **Live data.**
   - One WebSocket per session. It subscribes to every topic with telemetry at 10 Hz and pings
     every 10 s.
   - `seq` must increase by one. A gap, or close code 4429, means events may be missing: the
     client reconnects at once and the new snapshots resync it. Any other loss reconnects
     with backoff (0.5 s to 8 s). Meanwhile an **OFFLINE** banner shows and every command is
     disabled.
   - The live store (Zustand) is written only by the socket. The map subscribes outside React
     and redraws **at most once per animation frame**. React components read it through a
     hook throttled to **4 renders per second**; a unit test guards it with 50 aircraft at
     10 Hz.
3. **Map symbology** (colour is never the only cue, ADR 0015):
   - Airframe by icon (fixed-wing silhouette, multirotor with a nose), drawn at runtime as
     signed-distance-field images, rotated by heading. An unknown heading draws no nose.
   - Link state by colour **and** shape: live filled, stale hollow, lost or offline hollow
     with a cross. The list repeats it as icon + word.
   - Trails (about a minute), home points, a selection halo, the goto target, a scale bar,
     and the cursor position in DD, DDM or MGRS.
   - The basemap is an offline PMTiles extract with its own fonts and sprites
     (`scripts/fetch-basemap.mjs`; a Zurich sample around the simulator's site for M3,
     OpenStreetMap data attributed on the map). Without it the map is a plain background
     with a notice.
4. **Selection.** One selection for the map and the list: click, shift (add), ctrl (toggle),
   box and lasso (terra-draw), the list's filter, a group, all. Its size is always shown next
   to the commands, which act on it.
5. **Commands.**
   - The console offers or greys out each command with the reason (a pure, tested guide:
     offline, role, control lease, degraded link, goto on one aircraft). The fleet service
     decides everything again (ADR 0002: the UI is never the safety boundary). For example,
     a goto takes one aircraft in the console *and* in the API (422 otherwise): one target
     for several aircraft would converge them on it until M4 spreads them apart.
   - A 428 opens a dialog with **the server's own summary**: the command and aircraft count
     in the title, reasons, per-aircraft warnings, the aircraft that will not be sent and
     why, and an override flag.
   - **Confirming takes a held press**: 1 s of pointer or Space. Focus starts on Cancel,
     Enter cancels, a click confirms nothing. No risky command completes from one keystroke
     or one click.
   - HOLD is the only command with a key (`H`): it only makes things safer, and a bulk HOLD
     is confirmed like any other bulk command.
   - Per-aircraft outcomes update live from the `commands` topic.
6. **Roles.** Observers get no command bar and no control buttons. Operators take and release
   control; supervisors' commands may override (the server flags it in the summary).
   Handover requests and supervisor assignment come in M5.
7. **End-to-end tests** (`e2e/`, Playwright, Chromium) run the built console against the fleet
   service in simulation mode, seeded by `e2e/backend.py` (users per role, 20 aircraft, a
   group). They cover the usability scenarios of ADR 0015 and measure the map's frame rate
   with 50 aircraft at 10 Hz. The map has one test hook, `__sargcsProject` (screen position of
   a coordinate), enabled only by `localStorage` `sargcs.test=1`.

## Consequences

- The console needs WebGL. Frame rates depend on the GPU: the E2E report names the renderer
  it measured on (hardware on the development PC, software rendering in CI).
- Offline basemaps are prepared per region with `fetch-basemap.mjs` while online (the region
  decision for the field is still open, PLAN.md).
- The token in `sessionStorage` is readable by scripts on the console's origin. The console
  serves no third-party scripts (no CDN, ADR 0006), and the gateway sends a strict
  Content-Security-Policy in M6.
