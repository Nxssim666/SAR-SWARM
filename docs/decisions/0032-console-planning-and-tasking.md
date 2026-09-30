# 0032. Console: incidents, planning, tasking and points of interest

- Status: Accepted
- Date: 2026-09-30
- Refines: [0027](0027-console-architecture.md), [0028](0028-mission-planning-and-gcs-missions.md), [0029](0029-area-split-deconfliction-bulk-goto.md), [0031](0031-m4-alerts-and-points-of-interest.md)

## Context

The M4 backend plans, deconflicts and flies GCS missions, spreads bulk gotos, and reports
progress, coverage, points of interest and new alerts (ADR 0028–0031). The console of M3
(ADR 0027) could only watch aircraft and command them. This ADR records how the console
exposes planning and tasking.

## Decision

1. **The incident is the context.** The top bar picks the incident the console works on
   (open incidents only). With exactly one open incident it is picked by itself.
   Supervisors can open a new one, based at the centre of the map. The choice is a
   per-browser preference (`localStorage`); the server checks every request anyway.
2. **The side pane has tabs**: Fleet (list and telemetry, as in M3), Missions and Points.
   Alerts stay visible below the tabs whatever the tab. The Points tab shows a badge with
   the number of new survivor sightings.
3. **Planning state lives in its own store** (`planning/store.ts`): the incident's areas,
   the area or route being drawn, a datum, the routes of a plan, the coverage of the
   mission being watched, and a point being marked. The map draws it as its own layers,
   beneath the aircraft, redrawn only when that state changes (not per telemetry frame).
   Symbology follows ADR 0027: areas carry name and status as text, a searched area is
   dashed, routes differ by dash pattern as well as colour, and each point-of-interest kind
   has its own shape (survivor sighting ◆, point ●, clue ■, hazard ▲). Closed points are
   drawn hollow and faded, never removed.
4. **Map tools** extend M3's: draw an area (polygon), add waypoints (click after click
   until Esc), pick a datum, mark a point. One tool at a time; Esc returns to panning.
5. **Search areas from files**: GeoJSON, KML and GPX, as CalTopo, SARTopo and GIS tools
   export them, parsed in the browser (`planning/importArea.ts`, pure):
   - polygons, closed lines and tracks become candidate areas, named from the file;
   - holes are dropped and open tracks closed, and the operator is told;
   - rings above the server's 256-vertex limit are simplified (Douglas-Peucker) until
     they fit, and the operator is told by how much.

   The fleet service then validates the ring and the operating area, as for a drawn area.
6. **Plan, then save.**
   - The plan form builds the request (`planning/planRequest.ts`, pure and tested) and
     shows why it is incomplete before sending anything.
   - *Preview* asks the server for a dry run and draws the routes. Its report shows each
     aircraft's layer, speed, start delay, length and duration, conflicts, clearance
     issues and notes.
   - *Save plan* is offered only after a preview, so nothing is saved unseen.
7. **Starting, pausing and resuming** go through the M3 command flow, to the aircraft of
   the saved plan (not the map selection). The server's 428 summary is confirmed with a
   held press. The dialog now also shows each aircraft's own target, layer and start delay,
   and the conflicts a supervisor would override.
8. **Waypoint routes** are edited in a table: altitude **above home** (the reference in every
   label, ADR 0014), optional speed and loiter, reordering and removal. Errors block saving;
   a height above the usual 120 m ceiling is a warning, since the server applies the
   station's own limit.
9. **Bulk goto** is offered for several aircraft: the server gives each its own point and
   layer and always asks for confirmation (ADR 0029). M3's one-aircraft rule is gone from
   the console, because the server no longer needs it.
10. **Audible cues** (ADR 0031) are decided by a pure function (`alerts/cues.ts`):
    - a new or escalated warning cues once (one tone), a critical three high tones;
    - a critical alert that stays unacknowledged reminds every 30 s;
    - the snapshot of each (re)connection does not replay the backlog;
    - sound can be muted per browser, alerts never.

## Consequences

- An operator can go from an imported CalTopo area to a started, deconflicted group search
  and watch it complete without leaving the console. The E2E suite covers it.
- The console validates only to guide; every rule stays on the server (ADR 0002).
- Coverage geometry is polled from the progress endpoint every 3 s while a mission flies:
  the WebSocket carries progress numbers, not geometry, to keep telemetry light.
- Browsers allow sound only after the operator has interacted with the page, which signing
  in does. A station without audio output still shows every alert.
