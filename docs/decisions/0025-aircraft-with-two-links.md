# 0025. Aircraft with two links: merged telemetry, routed commands

- Status: Accepted
- Date: 2026-09-30
- Refines: [0003](0003-onboard-swarm-relationship.md) (rules 4 and 5), [0011](0011-command-authority.md)

## Context

ADR 0003 asks swarm aircraft to have a MAVLink link to their autopilot as well as the swarm
link to their companion computer. `DroneState` lacks altitude, battery, GNSS and the
autopilot's mode, and it says nothing when the companion is down. The registry already maps
`mavlink_system_id` and `swarm_drone_id` explicitly. M2b defines how one aircraft state and
one command path come out of two links.

## Decision

1. **One driver per aircraft.** With both links, `LinkedDriver` wraps the MAVLink driver
   and the swarm driver.
2. **Telemetry: `merge(mavlink, swarm, now, fresh_for)`,** a pure function, where "fresh"
   means within the stale threshold.
   - **MAVLink fresh:** its sample is the state; the autopilot knows best. The swarm block
     (phase, health, faults, sequences, sighting) is attached while the swarm sample is
     fresh.
   - **Only the swarm fresh:** the swarm sample is the state. That is position, heading
     and groundspeed, and nothing else: no stale battery or altitude is carried over.
   - **Neither fresh:** the newest sample stays, and its age drives the link state.
   - **Link states:** the overall link is live while either link is. The live view adds
     `links: {mavlink, swarm}` for these aircraft, so a lost link is visible even while
     the other keeps the aircraft live.
3. **Commands: `route_command(kind, swarm_live)`,** a pure function tested row by row.

   | Command | Link |
   |---|---|
   | arm, disarm, takeoff, goto | MAVLink |
   | hold, return, land | swarm while it is live (the companion keeps the swarm consistent and can resume), else MAVLink, so the safer command still gets through |
   | resume, mission_start | swarm only; while the swarm link is not live, not offered (capabilities) and nacked if it races |

4. **The companion in control blocks goto (ADR 0003 rule 5).** A goto is rejected while
   the autopilot's mode is `offboard` (`companion-in-control`): hold it first. RESUME of an
   aircraft whose companion flies it means the swarm mission. It needs the swarm phase
   `hold`, not the autopilot's HOLD mode.
5. **Effects are read from both.** HOLD is verified by the autopilot's HOLD mode *or* the
   swarm phase `hold`. RESUME and mission_start are verified by a working swarm phase
   (transit, search, track).

## Consequences

- An operator sees one aircraft, with its swarm phase and both links, and never has to
  pick a link.
- HOLD over the swarm link keeps PX4 in offboard, so RESUME works. HOLD over MAVLink (the
  fallback) takes PX4 out of offboard, and only the pilot can re-engage the companion.
  This is the intended safety behaviour of the onboard design.
- Not yet covered: an alert for losing one of the two links while the other stays live.
  The per-link state is shown, but it raises no alert (M4, alert engine).
