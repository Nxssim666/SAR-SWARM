# 0017. Simulation: mock fleet, PX4 SITL with Gazebo and SIH

- Status: Accepted
- Date: 2026-09-28

## Context

Everything must be demonstrable without real aircraft:

- 1 to 50 vehicles, mixing fixed-wing aircraft and hexacopters.
- Mission upload and commands.
- Link degradation, battery drain, GPS loss and geofence events.
- Video.

Full Gazebo simulation of 50 vehicles won't fit on a laptop. The development host is Windows
without Docker or WSL.

## Decision

Three tiers, each with a clear purpose:

| Tier | What | Scale | Purpose | Runs on |
|---|---|---|---|---|
| 0 | **Mock driver**, in-process kinematic model (ADR 0010) | 1–100+ | Unit, API and E2E tests, console development, load tests of the GCS itself | Anywhere, including Windows |
| 1 | **PX4 SITL + Gazebo Harmonic** | 1–5 | High fidelity: real PX4 flight stack, sensors, camera video, fixed-wing and multicopter dynamics | Linux + Docker (or WSL2), GPU optional |
| 2 | **PX4 SITL with SIH** (built-in simulator, headless) | 5–50 | Real PX4 flight stack and MAVLink at fleet scale, with low CPU use and no rendering | Linux + Docker; 50 vehicles need a large host or runner |

### Harness components

These live in `sim/` and are built in M2:

- **Pinned versions:** one PX4 release tag and one Gazebo version, recorded in
  `sim/README.md`. Images are built reproducibly from a Dockerfile.
- **Multi-vehicle launch:** one PX4 instance per vehicle (`px4 -i <n>`), each with a unique
  MAVLink system ID and a deterministic UDP port (`14540 + n` for the API link), and a spawn
  pose per vehicle. The fleet service registers aircraft from a generated `fleet.yaml`.
- **Airframes:**
  - Fixed-wing: Gazebo `rc_cessna`/`advanced_plane`, and SIH airplane.
  - Hexacopter: a Gazebo model derived from `x500` with six rotors, because no stock gz hexa
    model is expected (to be verified in M2). SIH uses its multicopter model as a stand-in,
    since GCS-level scale tests don't depend on rotor count.
- **Link emulation:** a small asyncio **UDP proxy** per vehicle between PX4 and the GCS.
  Loss, latency, jitter and blackout schedules are set per vehicle from tests. It needs no
  `tc netem` or `NET_ADMIN` and works on Windows too.
- **Failure injection:**
  - GPS loss, sensor failures and similar through PX4's failure injection
    (`SYS_FAILURE_EN=1`), via MAVSDK's Failure plugin.
  - Battery drain via `SIM_BAT_DRAIN` / `SIM_BAT_MIN_PCT`.
  - Geofence breach via an uploaded geofence plus `GF_ACTION`.
  - Wind from the Gazebo world.
- **Mock video:** an ffmpeg `testsrc2` stream per vehicle, with its ID and a timestamp, sent
  to MediaMTX (ADR 0012). Gazebo camera streams go to MediaMTX in tier 1.
- **Swarm (Model B, ADR 0003):**
  - The existing onboard standalone simulator stays as it is.
  - Bridge integration tests use a ROS 2 Jazzy container that runs `drone_node` against SITL
    (the onboard README path), or a fake `DroneState` publisher when a full swarm isn't needed.

### Scale proof

Scale targets in M2 and M5: track 1, 5, 25 and then 50 aircraft. Each target is reported with
measured latency, CPU and memory, using the tier that is feasible, and the report names the
tier.

## Alternatives considered

- **Gazebo for everything:** it can't reach 50 vehicles on field-class hardware.
- **Gazebo Classic:** end-of-life. It has a stock hexa (`typhoon_h480`) but is not maintained.
- **jMAVSim:** lightweight, but multicopter-only and deprecated in PX4.
- **Only the mock driver:** it wouldn't exercise real PX4 behaviour (mission protocol, modes,
  failsafes), and the requirement explicitly asks for PX4 SITL.
- **AirSim/Colosseum:** heavy, and aimed at vision research.

## Consequences

- Tiers 1 and 2 need Linux + Docker. **This host needs WSL2 + Docker Desktop**, which requires
  admin rights and a reboot, **or a separate Linux machine, or CI-only runs.** The decision is
  needed from the user before M2.
- GitHub-hosted runners (4 vCPU) can likely run about 10 SIH vehicles. 50 needs a larger or
  self-hosted runner.
