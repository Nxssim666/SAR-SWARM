# 0031. M4 alerts, points of interest and survivor sightings

- Status: Accepted
- Date: 2026-09-30
- Refines: [0002](0002-scope-safety-and-assumptions.md), [0003](0003-onboard-swarm-relationship.md), [0020](0020-live-core-commands-control-websocket.md)

## Context

M1b's alert engine covers links, battery, GNSS, orphaned control and command outcomes.
Searching areas with groups of aircraft adds new risks: running out of energy far from
home, leaving the geofence, leaving the route, losing one of two links, and getting too
close to another aircraft. Operators also need somewhere to record what the search finds.

## Decision

1. **Return energy.**
   - The battery needed to reach home is estimated as distance ÷ speed × the observed
     discharge rate, plus a 10 % reserve (`return_reserve_pct`).
   - The discharge rate is learned from samples at least 5 s apart, and trusted after 30 s
     of observed flight.
   - If the battery is at or below 1.2 × the need, a warning is raised; at or below 1 × the
     need, a critical alert.
   - Without a known rate, position, home or battery there is no estimate and no alert is
     made up. The battery thresholds of M1b still apply.
2. **New condition alerts** (raised while true, cleared when not):
   - geofence breach, against the incidents' enabled geofences;
   - one of an aircraft's two links lost (`link_partial`, ADR 0025);
   - route deviation (ADR 0028);
   - collision risk: two aircraft predicted within 10 m horizontally and 5 m vertically
     (`proximity_alert_m`, `proximity_alert_vertical_m`) in the next
     `proximity_lookahead_s` (30 s), from position and velocity.
3. **Escalation.** A warning nobody acknowledged for `alert_escalate_after_s` (60 s) becomes
   critical. The console's audible cues, which come with the M4 console work, follow
   severity.
4. **Points of interest.**
   - Operators mark points of interest on an incident: POI, clue or hazard.
   - Operators confirm, dismiss or resolve them. Nothing is deleted, so the record of what
     was seen and decided stays complete.
   - Points of interest are published on the `pois` WebSocket topic.
5. **Survivor sightings.**
   - The onboard "target" estimate is translated at the bridge into a *survivor sighting*
     (ADR 0003). Each new sighting becomes a point of interest of the incident the aircraft
     works for, and raises a **critical** alert once.
   - A repeat report from the same aircraft within 25 m of its last sighting, or within
     60 s of it, updates that point instead of adding one. A drone circling a person does
     not flood the map.
   - A sighting is only a report for an operator to confirm or dismiss. The station never
     acts on it by itself (ADR 0002).

## Consequences

- Every new alert follows the M1b rules: one open alert per dedupe key, and every raise,
  acknowledgement, clear and escalation is audited.
- The return-energy estimate ignores wind and the altitude to lose. With no known rate
  there is no estimate at all, so early in a flight only the battery thresholds protect.
- Collision risk is a short-horizon, straight-line prediction. It complements the planned
  deconfliction (ADR 0029) and does not replace the pilots' and autopilots' own separation.
