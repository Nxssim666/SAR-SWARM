# 0021. Simulation mode and the mock driver

- Status: Accepted
- Date: 2026-09-28
- Refines: [0010](0010-vehicle-drivers.md), [0017](0017-simulation.md)

## Context

M1b needs live aircraft for tests, demos, console development (M3) and GCS load tests, on a
host without Docker, PX4 or ROS. ADR 0017 planned a tier-0 "mock" simulation. Two questions
were open: how simulated aircraft are switched on, and what the mock must and must not model.

## Decision

### Simulation is a station-wide mode

- `SARGCS_SIMULATION=true` (see `fleet-service/simulation.env`) backs **every** registered
  aircraft with a simulated one. **No real link is opened in this mode.**
- Simulated and real aircraft are never mixed in one incident: operators must never wonder
  which aircraft on the map are real.
- The mode is visible everywhere a console looks: `GET /version`, `GET /fleet/state` and the
  WebSocket `welcome` message all carry `simulation`. The console must show a banner (M3).
- Simulated aircraft spawn on a 15 m grid at the configured origin
  (`SARGCS_SIM_ORIGIN_*`), in registration order. They are deterministic for
  `SARGCS_SIM_SEED`.
- `POST /simulation/aircraft/{id}/faults` injects link loss, GNSS loss or a battery level.
  It requires `fleet.manage`, is audited, and returns 409 outside simulation mode.

### What the mock models (`drivers/mock.py`)

- **Kinematics:** multirotors (hexa and quad) hover, accelerate with braking, climb at
  3 m/s and descend at 2 m/s. Fixed-wing aircraft fly at 18 m/s, loiter clockwise on a 60 m
  radius, and "land" by descending on that circle.
- **Modes:** hold, takeoff, goto, return (climb to at least 50 m, fly home, land) and land.
  Landing auto-disarms.
- **Command refusals like an autopilot's:** e.g. "takeoff denied: not armed", "disarm
  denied: in flight", "nothing to resume".
- **PX4-like failsafes that act without the ground station** (ADR 0002, S1):
  - link lost for 10 s → return;
  - GNSS lost → land;
  - battery at 10 % → return;
  - battery at 5 % → land.
- **Battery drain** over a realistic endurance (25 min for a hexa, 60 min for fixed-wing),
  plus cell voltage.
- **Faults:** with the link down, telemetry stops and commands wait (so they time out). With
  GNSS lost, the position is reported as unknown (`null`), never as a stale guess.

### What it does not model (fidelity limits)

It does not model:

- flight dynamics;
- wind;
- terrain or obstacles;
- sensor noise;
- radio latency or partial packet loss (the link is on or off);
- mission upload or geofence upload to the aircraft;
- takeoff and landing performance;
- fixed-wing stall and turn constraints beyond the loiter circle.

Latency figures measured with it cover **the ground station only**. PX4 SITL (M2) is the
reference for vehicle behaviour.

## Alternatives considered

- **Per-aircraft simulation flag** (mixing real and simulated aircraft for training): useful
  for exercises, but it risks confusion in a live incident. It would need its own ADR and
  strong UI cues.
- **A MAVLink-speaking mock** (pymavlink vehicle emulator): exercises the future MAVLink
  driver, but PX4 SITL does that better in M2, and this mock would be slower to build.

## Consequences

- M1b, M3 and M4 can be developed and demonstrated fully on Windows without Docker.
- The GCS load tests (M5) can run 50+ aircraft cheaply; PX4 SIH supplies realism at scale.
- Anyone reading a result must know which tier produced it. Reports name the tier.
