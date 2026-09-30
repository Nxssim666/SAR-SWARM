# 0033. No Gazebo simulation tier

- Status: Accepted
- Date: 2026-09-30
- Supersedes: the Gazebo tier (tier 1) of [0017](0017-simulation.md); removes the M2c stop

## Context

ADR 0017 planned three simulation tiers: PX4 SITL with Gazebo Harmonic (tier 1, 1–5
aircraft, camera video), PX4 SIH (tier 2, scale), and the mock fleet (tier 3). SIH and the
mock fleet are built and run in CI (ADR 0021, ADR 0023, ADR 0026). Gazebo was moved to its
own stop, M2c, and not built. The user decided to drop it.

## Decision

- **No Gazebo tier.** The M2c stop is removed from the plan.
- **Flight behaviour** is tested against PX4 SIH (SITL in CI) and the mock fleet.
- **Video** is tested with the mock streams of `sim/video` (ffmpeg test patterns through
  MediaMTX, ADR 0026). M5 adds a callsign and timestamp overlay for latency measurement.
- **The M6 acceptance** runs on SIH aircraft and mock video instead of "2 Gazebo aircraft
  with video".

## Consequences

- No simulated camera shows a real scene. The video pipeline (streaming, the player grid,
  health, latency) is still tested end to end with synthetic streams.
- Higher-fidelity airframe dynamics than SIH (and the SIH airplane's weak climb, ADR 0023)
  are covered only by field tests.
- `drone_node` with PX4 over uXRCE-DDS and a simulated depth camera, which needed Gazebo,
  stays untested in simulation (ADR 0026). The swarm is simulated as in M2b: the onboard
  `swarm_sar` simulation on ROS 2, with the real controller and messages.
